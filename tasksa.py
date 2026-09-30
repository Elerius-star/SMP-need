"""
posts/tasks.py
──────────────
Background jobs: publish scheduled posts, recompute trends, cleanup
old drafts, purge soft-deleted content, compute trust scores.
Works with Celery if installed, otherwise a management command
can call the functions directly.
"""
import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Q, F
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_post_model():
    from .models import Post
    return Post


def _get_hashtag_model():
    from .models import Hashtag
    return Hashtag


def _get_analytics_model():
    from .models import PostAnalytics
    return PostAnalytics


def publish_scheduled_posts():
    """
    Publish any post whose scheduled_for <= now and is still a draft.
    Run every minute via cron / Celery beat.
    """
    Post = _get_post_model()
    now = timezone.now()
    due = Post.objects.filter(
        scheduled_for__lte=now,
        is_draft=True,
        scheduled_for__isnull=False,
    )
    count = 0
    for post in due:
        post.is_draft = False
        post.published_at = now
        post.save(update_fields=['is_draft', 'published_at'])

        # Hashtag counters
        for tag in (post.hashtags.split(',') if post.hashtags else []):
            if not tag:
                continue
            tag_obj, _ = _get_hashtag_model().objects.get_or_create(name=tag)
            tag_obj.post_count = F('post_count') + 1
            tag_obj.save(update_fields=['post_count'])

        # Mentions
        try:
            from .utils import notify_mentions
            notify_mentions(post)
        except Exception as e:
            logger.warning('publish_scheduled_posts: mention notify failed: %s', e)

        count += 1

    if count:
        logger.info('Published %d scheduled posts', count)
    return count


def recompute_trend_scores():
    """
    Recompute trending hashtags: recency-weighted frequency.
    Run every 10 minutes.
    """
    Hashtag = _get_hashtag_model()
    Post = _get_post_model()

    cutoff = timezone.now() - timedelta(hours=48)
    recent_posts = Post.objects.filter(
        published_at__gte=cutoff, is_draft=False).only('hashtags')

    counters = {}
    for p in recent_posts.iterator(chunk_size=500):
        for tag in (p.hashtags.split(',') if p.hashtags else []):
            if tag:
                counters[tag] = counters.get(tag, 0) + 1

    for tag_name, recent_count in counters.items():
        obj, _ = Hashtag.objects.get_or_create(name=tag_name)
        obj.trend_score = recent_count * 0.8 + obj.post_count * 0.2
        obj.save(update_fields=['trend_score'])

    logger.info('Recomputed trend scores for %d hashtags', len(counters))
    return len(counters)


def cleanup_old_drafts(days=30):
    """Delete drafts older than N days that were never published."""
    Post = _get_post_model()
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = Post.objects.filter(
        is_draft=True, updated_at__lt=cutoff).delete()
    logger.info('Deleted %d stale drafts', deleted)
    return deleted


def cleanup_stale_notifications(days=90):
    """Trim old read notifications to keep table small."""
    try:
        from social.models import Notification
    except ImportError:
        return 0
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = Notification.objects.filter(
        is_read=True, created_at__lt=cutoff).delete()
    logger.info('Deleted %d stale notifications', deleted)
    return deleted


def recompute_all_user_counters():
    """
    Safety net: fix drifted counters (posts/followers/following).
    Run nightly.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    fixed = 0
    for user in User.objects.all().iterator(chunk_size=200):
        real_posts = user.posts.filter(is_draft=False).count()
        real_followers = user.followers_set.count()
        real_following = user.following_set.count()
        if (user.posts_count != real_posts or
                user.followers_count != real_followers or
                user.following_count != real_following):
            user.posts_count = real_posts
            user.followers_count = real_followers
            user.following_count = real_following
            user.save(update_fields=['posts_count', 'followers_count', 'following_count'])
            fixed += 1
    logger.info('Recomputed counters for %d users', fixed)
    return fixed


def recompute_trust_scores():
    """Refresh user trust scores for ranking."""
    try:
        from accounts.models_extras import UserTrustScore
    except ImportError:
        return 0
    from django.contrib.auth import get_user_model
    User = get_user_model()
    updated = 0
    for user in User.objects.all().iterator(chunk_size=200):
        ts, _ = UserTrustScore.objects.get_or_create(user=user)
        try:
            ts.recompute()
            updated += 1
        except Exception as e:
            logger.warning('trust score failed for %s: %s', user.id, e)
    logger.info('Recomputed %d trust scores', updated)
    return updated


def compute_follow_suggestions(limit=20, ttl_hours=6):
    """
    Compute "who to follow" per user. Simple heuristic:
    friends-of-friends weighted by mutual count.
    """
    try:
        from accounts.models_extras import FollowSuggestionCache
    except ImportError:
        return 0
    from django.contrib.auth import get_user_model
    from social.models import Follow, Block
    User = get_user_model()

    now = timezone.now()
    processed = 0

    for user in User.objects.all().iterator(chunk_size=100):
        following_ids = set(user.following_set.values_list('following_id', flat=True))
        blocked_ids = set(user.blocking.values_list('blocked_id', flat=True))

        candidates = {}
        for f in Follow.objects.filter(follower_id__in=following_ids).iterator():
            fid = f.following_id
            if fid == user.id or fid in following_ids or fid in blocked_ids:
                continue
            candidates[fid] = candidates.get(fid, 0) + 1

        ranked = sorted(candidates.items(), key=lambda x: -x[1])[:limit]
        suggestions = [{'user_id': uid, 'mutual': count} for uid, count in ranked]

        FollowSuggestionCache.objects.update_or_create(
            user=user,
            defaults={
                'suggestions': suggestions,
                'expires_at': now + timedelta(hours=ttl_hours),
            },
        )
        processed += 1

    logger.info('Computed suggestions for %d users', processed)
    return processed


def refresh_activity_feeds(per_user_limit=30):
    """
    Build activity cache per user from recent posts by who they follow.
    """
    try:
        from accounts.models_extras import ActivityFeedCache
    except ImportError:
        return 0
    from django.contrib.auth import get_user_model
    User = get_user_model()
    Post = _get_post_model()

    refreshed = 0
    for user in User.objects.all().iterator(chunk_size=100):
        following_ids = list(user.following_set.values_list('following_id', flat=True))
        if not following_ids:
            continue
        recent = Post.objects.filter(
            author_id__in=following_ids,
            is_draft=False,
        ).select_related('author').order_by('-published_at')[:per_user_limit]

        entries = [{
            'post_id': p.id,
            'author': p.author.username,
            'author_id': p.author.id,
            'content': p.content[:140],
            'created_at': p.published_at.isoformat() if p.published_at else None,
        } for p in recent]

        ActivityFeedCache.objects.update_or_create(
            user=user, defaults={'entries': entries},
        )
        refreshed += 1
    logger.info('Refreshed activity feeds for %d users', refreshed)
    return refreshed


def export_post_analytics_csv(days=7):
    """Snapshot analytics — returns rows for CSV export."""
    PostAnalytics = _get_analytics_model()
    cutoff = timezone.now() - timedelta(days=days)
    rows = []
    for a in PostAnalytics.objects.filter(updated_at__gte=cutoff).select_related('post__author'):
        rows.append({
            'post_id': a.post_id,
            'author': a.post.author.username,
            'impressions': a.impressions,
            'profile_clicks': a.profile_clicks,
            'link_clicks': a.link_clicks,
            'detail_expands': a.detail_expands,
        })
    return rows