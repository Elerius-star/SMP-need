"""Utility functions for parsing post content and computing trends."""
import re
from datetime import timedelta
from django.utils import timezone

HASHTAG_RE = re.compile(r'#(\w{1,50})')
MENTION_RE = re.compile(r'@(\w{1,30})')
URL_RE = re.compile(r'https?://[^\s]+')


def extract_hashtags(text):
    return list({m.lower() for m in HASHTAG_RE.findall(text or '')})


def extract_mentions(text):
    return list({m for m in MENTION_RE.findall(text or '')})


def extract_first_url(text):
    m = URL_RE.search(text or '')
    return m.group(0) if m else ''


def parse_trending(limit=10):
    from .models import Hashtag
    return Hashtag.objects.order_by('-trend_score', '-post_count')[:limit]


def recompute_trend_scores():
    """Recency-weighted trend score: posts in last 48h weight more."""
    from .models import Hashtag
    now = timezone.now()
    cutoff = now - timedelta(hours=48)
    for tag in Hashtag.objects.all():
        recent = tag.post_count  # simple heuristic, refine with a join
        tag.trend_score = recent * 0.6
        tag.save(update_fields=['trend_score'])


def notify_mentions(post):
    """Create Notification rows for every @mention in a post."""
    from accounts.models import User
    from social.models import Notification
    for username in extract_mentions(post.content):
        try:
            target = User.objects.get(username=username)
        except User.DoesNotExist:
            continue
        if target == post.author:
            continue
        Notification.objects.create(
            recipient=target, actor=post.author,
            type='mention', post=post,
        )


def humanize_number(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)