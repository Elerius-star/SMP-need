"""
accounts/models_extras.py
─────────────────────────
Audit logs, follow suggestion cache, activity feed cache,
user trust scores, and rate-limit tracking.
"""
import hashlib
import json
from datetime import timedelta
from django.db import models
from django.conf import settings
from django.utils import timezone


class AuditLog(models.Model):
    """Immutable audit trail for admin and security actions."""
    ACTIONS = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('register', 'Register'),
        ('password_change', 'Password Change'),
        ('password_reset', 'Password Reset'),
        ('email_verify', 'Email Verify'),
        ('block', 'Block'),
        ('unblock', 'Unblock'),
        ('mute', 'Mute'),
        ('unmute', 'Unmute'),
        ('delete_post', 'Delete Post'),
        ('delete_account', 'Delete Account'),
        ('deactivate', 'Deactivate'),
        ('reactivate', 'Reactivate'),
        ('report', 'Report'),
        ('admin_action', 'Admin Action'),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=30, choices=ACTIONS)
    target_type = models.CharField(max_length=50, blank=True)
    target_id = models.CharField(max_length=50, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['action', '-created_at']),
        ]

    def __str__(self):
        return f"{self.user_id} {self.action} {self.created_at}"


class FollowSuggestionCache(models.Model):
    """
    Cached follow suggestions. Recomputed periodically by a background
    task — cheap reads for the API.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='follow_suggestions')
    suggestions = models.JSONField(default=list, blank=True)
    computed_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()

    def is_stale(self):
        return self.expires_at <= timezone.now()

    @classmethod
    def default_expiry(cls):
        return timezone.now() + timedelta(hours=6)

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = self.default_expiry()
        super().save(*args, **kwargs)


class ActivityFeedCache(models.Model):
    """
    Precomputed activity feed per user (mutual activity from followed
    accounts). Speeds up dashboard load and enables "you missed this".
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='activity_cache')
    entries = models.JSONField(default=list, blank=True)
    last_seen_post_id = models.PositiveIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def append(self, entry, cap=200):
        entries = list(self.entries or [])
        entries.insert(0, entry)
        self.entries = entries[:cap]
        self.save(update_fields=['entries', 'updated_at'])

    def clear(self):
        self.entries = []
        self.save(update_fields=['entries', 'updated_at'])


class UserTrustScore(models.Model):
    """
    Heuristic trust score used to prioritize content in feeds and
    shadow-ban obvious spam. Recomputed nightly.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='trust_score')
    score = models.FloatField(default=50.0)
    account_age_days = models.PositiveIntegerField(default=0)
    follower_ratio = models.FloatField(default=0)
    reports_received = models.PositiveIntegerField(default=0)
    reports_made = models.PositiveIntegerField(default=0)
    posts_removed = models.PositiveIntegerField(default=0)
    verified_bonus = models.FloatField(default=0)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-score']

    def recompute(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        age = (timezone.now() - self.user.date_joined).days
        followers = getattr(self.user, 'followers_count', 0)
        following = max(getattr(self.user, 'following_count', 1), 1)
        ratio = followers / following
        base = 50.0
        base += min(age, 365) * 0.05
        base += min(ratio, 10) * 2
        base -= self.reports_received * 1.5
        base += self.verified_bonus
        base -= self.posts_removed * 3
        self.score = max(0.0, min(100.0, base))
        self.account_age_days = age
        self.follower_ratio = ratio
        self.save()


class RateLimitBucket(models.Model):
    """
    Generic token-bucket rate limit tracking for sensitive endpoints
    (login attempts, post creation, DM sends).
    """
    key = models.CharField(max_length=200, db_index=True)
    count = models.PositiveIntegerField(default=0)
    window_start = models.DateTimeField(default=timezone.now)
    window_seconds = models.PositiveIntegerField(default=60)
    limit = models.PositiveIntegerField(default=60)

    class Meta:
        unique_together = ('key', 'window_start')
        indexes = [models.Index(fields=['key', '-window_start'])]

    def is_window_active(self):
        return (timezone.now() - self.window_start).total_seconds() < self.window_seconds

    @classmethod
    def check(cls, key, limit=60, window_seconds=60):
        now = timezone.now()
        window_start = now - timedelta(seconds=window_seconds)
        bucket = cls.objects.filter(key=key, window_start__gte=window_start).first()
        if not bucket:
            bucket = cls.objects.create(key=key, limit=limit,
                                        window_seconds=window_seconds,
                                        window_start=now)
        if bucket.count >= bucket.limit:
            return False, bucket
        bucket.count += 1
        bucket.save(update_fields=['count'])
        return True, bucket


class EmailDigest(models.Model):
    """Weekly digest email queue — batched to avoid spamming."""
    FREQUENCIES = [('daily', 'Daily'), ('weekly', 'Weekly'), ('never', 'Never')]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='digests')
    frequency = models.CharField(max_length=10, choices=FREQUENCIES, default='weekly')
    last_sent_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def due(self):
        if not self.last_sent_at:
            return True
        delta = timezone.now() - self.last_sent_at
        if self.frequency == 'daily':
            return delta > timedelta(days=1)
        if self.frequency == 'weekly':
            return delta > timedelta(days=7)
        return False


class ContentFingerprint(models.Model):
    """
    Hash of a post's content for duplicate/spam detection.
    Prevents obvious re-post spam.
    """
    post = models.OneToOneField(
        'posts.Post', on_delete=models.CASCADE, related_name='fingerprint')
    hash = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def make_hash(content, author_id):
        normalized = ' '.join((content or '').lower().split())
        raw = f"{author_id}:{normalized}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def is_duplicate(cls, content, author_id, window_hours=24):
        h = cls.make_hash(content, author_id)
        cutoff = timezone.now() - timedelta(hours=window_hours)
        return cls.objects.filter(hash=h, created_at__gte=cutoff).exists()