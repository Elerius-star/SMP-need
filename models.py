from django.db import models
from django.conf import settings
from django.utils import timezone


class Post(models.Model):
    VISIBILITY = [('public', 'Public'), ('followers', 'Followers'), ('private', 'Private')]
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name='posts')
    content = models.TextField(max_length=2000, blank=True)
    image = models.ImageField(upload_to='posts/', blank=True, null=True)
    image_thumb = models.ImageField(upload_to='posts/thumbs/', blank=True, null=True)
    image_medium = models.ImageField(upload_to='posts/medium/', blank=True, null=True)
    video = models.FileField(upload_to='videos/', blank=True, null=True)
    link_url = models.URLField(blank=True)
    link_title = models.CharField(max_length=200, blank=True)
    link_description = models.CharField(max_length=500, blank=True)
    link_image = models.URLField(blank=True)
    visibility = models.CharField(max_length=10, choices=VISIBILITY, default='public')
    is_draft = models.BooleanField(default=False)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(default=timezone.now)
    is_repost = models.BooleanField(default=False)
    is_quote = models.BooleanField(default=False)
    original_post = models.ForeignKey('self', null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name='reposts')
    hashtags = models.CharField(max_length=500, blank=True)
    mentions = models.CharField(max_length=500, blank=True)
    likes_count = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    reposts_count = models.PositiveIntegerField(default=0)
    views_count = models.PositiveIntegerField(default=0)
    is_pinned = models.BooleanField(default=False)
    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    language = models.CharField(max_length=8, default='en')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['author', '-created_at']),
            models.Index(fields=['hashtags']),
            models.Index(fields=['visibility', '-created_at']),
        ]

    def __str__(self):
        return f"{self.author.username}: {self.content[:40]}"

    def save(self, *args, **kwargs):
        from .utils import extract_hashtags, extract_mentions, extract_first_url
        if self.content:
            self.hashtags = ','.join(extract_hashtags(self.content))
            self.mentions = ','.join(extract_mentions(self.content))
            url = extract_first_url(self.content)
            if url and not self.link_url:
                self.link_url = url
        super().save(*args, **kwargs)

    def update_counters(self):
        self.likes_count = self.likes.count()
        self.comments_count = self.comments.count()
        self.reposts_count = self.reposts.count()
        self.save(update_fields=['likes_count', 'comments_count', 'reposts_count'])


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    parent = models.ForeignKey('self', null=True, blank=True,
                               on_delete=models.CASCADE, related_name='replies')
    content = models.TextField(max_length=1000)
    likes_count = models.PositiveIntegerField(default=0)
    is_edited = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['post', 'created_at'])]


class CommentLike(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'comment')


class Bookmark(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='bookmarks')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='bookmarked_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'post')
        ordering = ['-created_at']


class Hashtag(models.Model):
    name = models.CharField(max_length=100, unique=True)
    post_count = models.PositiveIntegerField(default=0)
    trend_score = models.FloatField(default=0)
    last_used = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-trend_score', '-post_count']

    def __str__(self):
        return f"#{self.name}"


class Poll(models.Model):
    post = models.OneToOneField(Post, on_delete=models.CASCADE, related_name='poll')
    question = models.CharField(max_length=200)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_open(self):
        return self.ends_at is None or self.ends_at > timezone.now()


class PollOption(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=100)
    votes_count = models.PositiveIntegerField(default=0)


class PollVote(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='votes')
    option = models.ForeignKey(PollOption, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'poll')


class SavedSearch(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='saved_searches')
    query = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('user', 'query')


class PostAnalytics(models.Model):
    post = models.OneToOneField(Post, on_delete=models.CASCADE, related_name='analytics')
    impressions = models.PositiveIntegerField(default=0)
    profile_clicks = models.PositiveIntegerField(default=0)
    link_clicks = models.PositiveIntegerField(default=0)
    detail_expands = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)