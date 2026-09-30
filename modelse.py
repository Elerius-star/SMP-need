from django.db import models
from django.conf import settings


class Like(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='likes')
    post = models.ForeignKey('posts.Post', on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'post')


class Reaction(models.Model):
    """Emoji reaction on a post."""
    KINDS = [('like', '👍'), ('love', '❤️'), ('haha', '😂'),
             ('wow', '😮'), ('sad', '😢'), ('angry', '😡')]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='reactions')
    post = models.ForeignKey('posts.Post', on_delete=models.CASCADE, related_name='reactions')
    kind = models.CharField(max_length=10, choices=KINDS, default='like')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'post')


class Follow(models.Model):
    follower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='following_set')
    following = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name='followers_set')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('follower', 'following')
        indexes = [models.Index(fields=['follower', 'following'])]

    def __str__(self):
        return f"{self.follower} → {self.following}"


class FollowRequest(models.Model):
    """For private accounts: pending follow requests."""
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name='sent_follow_requests')
    target = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name='received_follow_requests')
    created_at = models.DateTimeField(auto_now_add=True)
    accepted = models.BooleanField(null=True)

    class Meta:
        unique_together = ('requester', 'target')


class Notification(models.Model):
    TYPES = [
        ('like', 'Like'), ('comment', 'Comment'), ('follow', 'Follow'),
        ('mention', 'Mention'), ('repost', 'Repost'), ('dm', 'DM'),
        ('reaction', 'Reaction'), ('follow_request', 'Follow Request'),
    ]
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name='notifications')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name='acted_notifications')
    type = models.CharField(max_length=20, choices=TYPES)
    post = models.ForeignKey('posts.Post', null=True, blank=True, on_delete=models.CASCADE)
    comment = models.ForeignKey('posts.Comment', null=True, blank=True, on_delete=models.CASCADE)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['recipient', '-created_at'])]


class Report(models.Model):
    REASONS = [('spam', 'Spam'), ('abuse', 'Abuse'), ('nudity', 'Nudity'),
               ('misinformation', 'Misinformation'), ('other', 'Other')]
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    post = models.ForeignKey('posts.Post', null=True, blank=True, on_delete=models.CASCADE)
    comment = models.ForeignKey('posts.Comment', null=True, blank=True, on_delete=models.CASCADE)
    user_reported = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                      on_delete=models.CASCADE, related_name='reports_against')
    reason = models.CharField(max_length=20, choices=REASONS)
    details = models.TextField(blank=True)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


# ─── Direct messages & groups ────────────────────────────────
class Conversation(models.Model):
    """1:1 or group conversation."""
    is_group = models.BooleanField(default=False)
    name = models.CharField(max_length=100, blank=True)
    avatar = models.ImageField(upload_to='group_avatars/', blank=True, null=True)
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='conversations')
    admins = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='admin_conversations',
                                    blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.name or f"Conversation #{self.pk}"


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField(blank=True)
    image = models.ImageField(upload_to='dm_images/', blank=True, null=True)
    file = models.FileField(upload_to='dm_files/', blank=True, null=True)
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    edited = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['conversation', 'created_at'])]


class TypingIndicator(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('conversation', 'user')