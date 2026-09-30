"""
accounts/models.py
─────────────────
Custom user model, blocks, mutes, muted words, email verification tokens,
login history, device sessions, and profile verification requests.
"""
import secrets
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from datetime import timedelta


class User(AbstractUser):
    """Custom user with profile fields and social counters."""
    email = models.EmailField(unique=True)
    bio = models.CharField(max_length=280, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    banner = models.ImageField(upload_to='banners/', blank=True, null=True)
    location = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    birth_date = models.DateField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    is_private = models.BooleanField(default=False)
    is_deactivated = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    last_seen = models.DateTimeField(default=timezone.now)
    followers_count = models.PositiveIntegerField(default=0)
    following_count = models.PositiveIntegerField(default=0)
    posts_count = models.PositiveIntegerField(default=0)
    theme_preference = models.CharField(max_length=10, default='light')
    notification_prefs = models.JSONField(default=dict, blank=True)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        ordering = ['-date_joined']
        indexes = [
            models.Index(fields=['username']),
            models.Index(fields=['email']),
            models.Index(fields=['-date_joined']),
        ]

    def __str__(self):
        return self.username

    def update_counters(self):
        self.followers_count = self.followers_set.count()
        self.following_count = self.following_set.count()
        self.posts_count = self.posts.count()
        self.save(update_fields=['followers_count', 'following_count', 'posts_count'])

    def touch_last_seen(self):
        self.last_seen = timezone.now()
        self.save(update_fields=['last_seen'])

    @property
    def is_online(self):
        return (timezone.now() - self.last_seen) < timedelta(minutes=5)


class Block(models.Model):
    blocker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocking')
    blocked = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('blocker', 'blocked')
        indexes = [models.Index(fields=['blocker', 'blocked'])]

    def __str__(self):
        return f"{self.blocker} blocked {self.blocked}"


class Mute(models.Model):
    """Mute: see less of someone without blocking them."""
    muter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='muting')
    muted = models.ForeignKey(User, on_delete=models.CASCADE, related_name='muted_by')
    created_at = models.DateTimeField(auto_now_add=True)
    until = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('muter', 'muted')

    def is_active(self):
        if self.until is None:
            return True
        return self.until > timezone.now()


class MutedWord(models.Model):
    """Mute specific words from your feed."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='muted_words')
    word = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'word')
        indexes = [models.Index(fields=['user', 'word'])]


class EmailVerificationToken(models.Model):
    """One-time token for verifying an email address."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_tokens')
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(48)
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=24)
        super().save(*args, **kwargs)

    def is_valid(self):
        return not self.used and self.expires_at > timezone.now()


class PasswordResetToken(models.Model):
    """One-time token for resetting a password."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reset_tokens')
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(48)
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=2)
        super().save(*args, **kwargs)

    def is_valid(self):
        return not self.used and self.expires_at > timezone.now()


class LoginHistory(models.Model):
    """Track every login for security review."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='login_history')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    device = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=200, blank=True)
    success = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', '-created_at'])]


class DeviceSession(models.Model):
    """Active device sessions that can be revoked by the user."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='device_sessions')
    token = models.CharField(max_length=128, unique=True)
    device_name = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    last_active = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_revoked = models.BooleanField(default=False)

    class Meta:
        ordering = ['-last_active']

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(64)
        super().save(*args, **kwargs)


class ProfileVerificationRequest(models.Model):
    """User applies for verified badge; admins approve."""
    STATUS = [('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='verification_requests')
    reason = models.TextField()
    document = models.FileField(upload_to='verifications/', blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS, default='pending')
    reviewer_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)


class UserSettings(models.Model):
    """Extended per-user settings separate from User table."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='settings')
    email_notifications = models.BooleanField(default=True)
    push_notifications = models.BooleanField(default=True)
    show_online_status = models.BooleanField(default=True)
    allow_dm_from = models.CharField(max_length=20, default='everyone')  # everyone | followers | none
    autoplay_videos = models.BooleanField(default=True)
    sensitive_content_filter = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)