from rest_framework import serializers
from accounts.serializers import UserMiniSerializer
from .models import (
    Post, Comment, CommentLike, Bookmark, Hashtag,
    Poll, PollOption, PollVote, SavedSearch, PostAnalytics,
)


class PollOptionSerializer(serializers.ModelSerializer):
    percent = serializers.SerializerMethodField()
    class Meta:
        model = PollOption
        fields = ['id', 'text', 'votes_count', 'percent']

    def get_percent(self, obj):
        total = obj.poll.options.aggregate(s=serializers.models.Sum('votes_count'))['s'] or 0
        if not total:
            return 0
        return round(obj.votes_count / total * 100, 1)


class PollSerializer(serializers.ModelSerializer):
    options = PollOptionSerializer(many=True)
    total_votes = serializers.SerializerMethodField()
    class Meta:
        model = Poll
        fields = ['id', 'question', 'ends_at', 'options', 'total_votes', 'is_open']

    def get_total_votes(self, obj):
        return sum(o.votes_count for o in obj.options.all())


class CommentLikeSerializer(serializers.ModelSerializer):
    user = UserMiniSerializer(read_only=True)
    class Meta:
        model = CommentLike
        fields = ['id', 'user', 'created_at']


class CommentSerializer(serializers.ModelSerializer):
    author = UserMiniSerializer(read_only=True)
    replies = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    likes = CommentLikeSerializer(source='likes', many=True, read_only=True)

    class Meta:
        model = Comment
        fields = ['id', 'post', 'author', 'parent', 'content',
                  'likes_count', 'created_at', 'updated_at',
                  'is_edited', 'replies', 'is_liked', 'likes']
        read_only_fields = ['id', 'author', 'likes_count', 'created_at', 'updated_at']

    def get_replies(self, obj):
        if obj.replies.exists():
            return CommentSerializer(obj.replies.all(), many=True,
                                     context=self.context).data
        return []

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.likes.filter(user=request.user).exists()

    def validate_content(self, value):
        if len(value) > 1000:
            raise serializers.ValidationError("Max 1000 characters.")
        if len(value.strip()) == 0:
            raise serializers.ValidationError("Cannot be empty.")
        return value


class PostAnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostAnalytics
        fields = '__all__'


class PostSerializer(serializers.ModelSerializer):
    author = UserMiniSerializer(read_only=True)
    is_liked = serializers.SerializerMethodField()
    is_bookmarked = serializers.SerializerMethodField()
    original = serializers.SerializerMethodField()
    poll = PollSerializer(read_only=True)
    analytics = PostAnalyticsSerializer(read_only=True)
    like_preview = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = ['id', 'author', 'content', 'image', 'image_thumb',
                  'image_medium', 'video', 'link_url', 'link_title',
                  'link_description', 'link_image', 'visibility',
                  'is_draft', 'scheduled_for', 'published_at', 'is_repost',
                  'is_quote', 'original_post', 'original', 'hashtags',
                  'mentions', 'likes_count', 'comments_count', 'reposts_count',
                  'views_count', 'is_pinned', 'is_edited', 'edited_at',
                  'language', 'created_at', 'updated_at', 'is_liked',
                  'is_bookmarked', 'poll', 'analytics', 'like_preview']
        read_only_fields = ['id', 'author', 'likes_count', 'comments_count',
                            'reposts_count', 'views_count', 'created_at',
                            'updated_at', 'hashtags', 'mentions', 'published_at']

    def validate_content(self, value):
        if len(value) > 2000:
            raise serializers.ValidationError("Max 2000 characters.")
        return value

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.likes.filter(user=request.user).exists()

    def get_is_bookmarked(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.bookmarked_by.filter(user=request.user).exists()

    def get_original(self, obj):
        if obj.original_post:
            return {
                'id': obj.original_post.id,
                'author': UserMiniSerializer(obj.original_post.author).data,
                'content': obj.original_post.content,
                'image': obj.original_post.image.url if obj.original_post.image else None,
                'created_at': obj.original_post.created_at,
            }
        return None

    def get_like_preview(self, obj):
        likes = obj.likes.select_related('user')[:5]
        return [UserMiniSerializer(l.user).data for l in likes]


class BookmarkSerializer(serializers.ModelSerializer):
    post = PostSerializer(read_only=True)
    class Meta:
        model = Bookmark
        fields = ['id', 'post', 'created_at']


class HashtagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hashtag
        fields = ['id', 'name', 'post_count', 'trend_score', 'last_used']


class SavedSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedSearch
        fields = ['id', 'query', 'created_at']