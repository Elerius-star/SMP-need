from rest_framework import serializers
from accounts.serializers import UserMiniSerializer
from .models import (
    Notification, Report, Follow, FollowRequest, Reaction,
    Conversation, Message, TypingIndicator,
)


class NotificationSerializer(serializers.ModelSerializer):
    actor = UserMiniSerializer(read_only=True)
    class Meta:
        model = Notification
        fields = ['id', 'recipient', 'actor', 'type', 'post', 'comment',
                  'is_read', 'created_at']
        read_only_fields = ['id', 'recipient', 'actor', 'type', 'post',
                            'comment', 'created_at']


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = ['id', 'post', 'comment', 'user_reported', 'reason',
                  'details', 'is_resolved', 'created_at']
        read_only_fields = ['id', 'is_resolved', 'created_at']


class FollowSerializer(serializers.ModelSerializer):
    follower = UserMiniSerializer(read_only=True)
    following = UserMiniSerializer(read_only=True)
    class Meta:
        model = Follow
        fields = ['id', 'follower', 'following', 'created_at']


class FollowRequestSerializer(serializers.ModelSerializer):
    requester = UserMiniSerializer(read_only=True)
    class Meta:
        model = FollowRequest
        fields = ['id', 'requester', 'target', 'created_at', 'accepted']


class ReactionSerializer(serializers.ModelSerializer):
    user = UserMiniSerializer(read_only=True)
    class Meta:
        model = Reaction
        fields = ['id', 'user', 'post', 'kind', 'created_at']


class MessageSerializer(serializers.ModelSerializer):
    sender = UserMiniSerializer(read_only=True)
    class Meta:
        model = Message
        fields = ['id', 'conversation', 'sender', 'content', 'image', 'file',
                  'reply_to', 'is_read', 'read_at', 'edited', 'created_at']
        read_only_fields = ['id', 'sender', 'is_read', 'read_at', 'created_at']


class ConversationSerializer(serializers.ModelSerializer):
    participants = UserMiniSerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'is_group', 'name', 'avatar', 'participants',
                  'created_at', 'updated_at', 'last_message', 'unread_count']

    def get_last_message(self, obj):
        m = obj.messages.last()
        return MessageSerializer(m).data if m else None

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        return obj.messages.filter(is_read=False).exclude(sender=request.user).count()