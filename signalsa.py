"""
posts/signals.py
────────────────
Post-save / post-delete signals: sync hashtags, mentions,
fingerprints, analytics rows, and delete orphaned media.
"""
import logging
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


@receiver(post_save, sender='posts.Post')
def post_saved(sender, instance, created, **kwargs):
    """When a post is created or updated, sync related side effects."""
    from .models import Post, Hashtag, PostAnalytics
    from .utils import notify_mentions, extract_hashtags

    # 1. Analytics row (only for real posts, not drafts)
    if not instance.is_draft:
        PostAnalytics.objects.get_or_create(post=instance)

    # 2. Hashtag counters — only recount on publish, not every save
    if created and not instance.is_draft:
        for tag in extract_hashtags(instance.content or ''):
            tag_obj, _ = Hashtag.objects.get_or_create(name=tag)
            tag_obj.post_count = tag_obj.post_count + 1
            tag_obj.save(update_fields=['post_count'])

    # 3. Mentions — only on create to avoid spam
    if created and not instance.is_draft:
        try:
            notify_mentions(instance)
        except Exception as e:
            logger.warning('notify_mentions failed: %s', e)

    # 4. Duplicate fingerprint
    try:
        from accounts.models_extras import ContentFingerprint
        if instance.content and not instance.is_repost:
            ContentFingerprint.objects.update_or_create(
                post=instance,
                defaults={
                    'hash': ContentFingerprint.make_hash(
                        instance.content, instance.author_id),
                },
            )
    except ImportError:
        pass


@receiver(post_delete, sender='posts.Post')
def post_deleted(sender, instance, **kwargs):
    """Adjust hashtag counters when a post is deleted."""
    from .models import Hashtag
    if instance.is_draft:
        return
    for tag in (instance.hashtags.split(',') if instance.hashtags else []):
        if not tag:
            continue
        try:
            tag_obj = Hashtag.objects.get(name=tag)
            tag_obj.post_count = max(0, tag_obj.post_count - 1)
            tag_obj.save(update_fields=['post_count'])
        except Hashtag.DoesNotExist:
            continue


@receiver(post_save, sender='posts.Comment')
def comment_saved(sender, instance, created, **kwargs):
    """Update post.comments_count when a comment is added."""
    if not created:
        return
    from .models import Post
    Post.objects.filter(pk=instance.post_id).update(
        comments_count=instance.post.comments.count())


@receiver(post_delete, sender='posts.Comment')
def comment_deleted(sender, instance, **kwargs):
    from .models import Post
    try:
        Post.objects.filter(pk=instance.post_id).update(
            comments_count=instance.post.comments.count())
    except Post.DoesNotExist:
        pass


@receiver(post_save, sender='social.Like')
def like_created(sender, instance, created, **kwargs):
    if not created:
        return
    from posts.models import Post
    Post.objects.filter(pk=instance.post_id).update(
        likes_count=instance.post.likes.count())
    # Notification
    try:
        from social.models import Notification
        if instance.post.author_id != instance.user_id:
            Notification.objects.create(
                recipient=instance.post.author,
                actor=instance.user,
                type='like',
                post=instance.post,
            )
    except Exception as e:
        logger.warning('like notification failed: %s', e)


@receiver(post_delete, sender='social.Like')
def like_deleted(sender, instance, **kwargs):
    from posts.models import Post
    try:
        Post.objects.filter(pk=instance.post_id).update(
            likes_count=instance.post.likes.count())
    except Post.DoesNotExist:
        pass


@receiver(post_save, sender='social.Follow')
def follow_created(sender, instance, created, **kwargs):
    if not created:
        return
    instance.follower.update_counters()
    instance.following.update_counters()
    try:
        from social.models import Notification
        Notification.objects.create(
            recipient=instance.following,
            actor=instance.follower,
            type='follow',
        )
    except Exception as e:
        logger.warning('follow notification failed: %s', e)


@receiver(post_delete, sender='social.Follow')
def follow_deleted(sender, instance, **kwargs):
    try:
        instance.follower.update_counters()
        instance.following.update_counters()
    except Exception as e:
        logger.warning('follow counter update failed: %s', e)


@receiver(post_save, sender='posts.Bookmark')
def bookmark_created(sender, instance, created, **kwargs):
    """No counter table for bookmarks — silently succeed."""


@receiver(post_save, sender='posts.PollVote')
def poll_vote_created(sender, instance, created, **kwargs):
    """Increment option count when a new vote row is written."""
    if created:
        from posts.models import PollOption
        PollOption.objects.filter(pk=instance.option_id).update(
            votes_count=instance.option.votes.count())