from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import (
    User, Block, Mute, MutedWord, EmailVerificationToken,
    PasswordResetToken, LoginHistory, DeviceSession,
    ProfileVerificationRequest, UserSettings,
)


class UserMiniSerializer(serializers.ModelSerializer):
    is_online = serializers.BooleanField(read_only=True)
    class Meta:
        model = User
        fields = ['id', 'username', 'avatar', 'is_verified', 'is_online']


class UserSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSettings
        exclude = ['user', 'updated_at']


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, validators=[validate_password])
    is_following = serializers.SerializerMethodField()
    is_blocked = serializers.SerializerMethodField()
    is_muted = serializers.SerializerMethodField()
    settings = UserSettingsSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'password', 'bio', 'avatar', 'banner',
            'location', 'website', 'birth_date', 'is_verified', 'is_private',
            'is_deactivated', 'email_verified', 'followers_count', 'following_count',
            'posts_count', 'last_seen', 'date_joined', 'is_following',
            'is_blocked', 'is_muted', 'theme_preference', 'settings',
        ]
        read_only_fields = ['id', 'followers_count', 'following_count',
                            'posts_count', 'date_joined', 'is_verified',
                            'email_verified', 'last_seen']

    def get_is_following(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.followers_set.filter(follower=request.user).exists()

    def get_is_blocked(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return Block.objects.filter(blocker=request.user, blocked=obj).exists()

    def get_is_muted(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return Mute.objects.filter(muter=request.user, muted=obj).exists()

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        UserSettings.objects.create(user=user)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2']

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('Username taken.')
        if not value.replace('_', '').isalnum():
            raise serializers.ValidationError('Only letters, digits, underscores.')
        if len(value) < 3:
            raise serializers.ValidationError('Too short.')
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password': 'Passwords do not match.'})
        if User.objects.filter(email__iexact=attrs['email']).exists():
            raise serializers.ValidationError({'email': 'Email already registered.'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        UserSettings.objects.create(user=user)
        return user


class BlockSerializer(serializers.ModelSerializer):
    blocked_user = UserMiniSerializer(source='blocked', read_only=True)
    class Meta:
        model = Block
        fields = ['id', 'blocked_user', 'created_at']


class MuteSerializer(serializers.ModelSerializer):
    muted_user = UserMiniSerializer(source='muted', read_only=True)
    class Meta:
        model = Mute
        fields = ['id', 'muted_user', 'created_at', 'until', 'is_active']


class MutedWordSerializer(serializers.ModelSerializer):
    class Meta:
        model = MutedWord
        fields = ['id', 'word', 'created_at']


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not User.objects.filter(email__iexact=value).exists():
            # Don't leak existence — return OK
            return value
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    password = serializers.CharField(validators=[validate_password])
    password2 = serializers.CharField()

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password': 'Mismatch.'})
        try:
            t = PasswordResetToken.objects.get(token=attrs['token'])
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError({'token': 'Invalid.'})
        if not t.is_valid():
            raise serializers.ValidationError({'token': 'Expired or used.'})
        attrs['token_obj'] = t
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(validators=[validate_password])
    new_password2 = serializers.CharField()

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({'new_password': 'Mismatch.'})
        return attrs


class LoginHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginHistory
        fields = '__all__'


class DeviceSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceSession
        fields = ['id', 'device_name', 'ip_address', 'last_active',
                  'created_at', 'is_revoked']


class ProfileVerificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfileVerificationRequest
        fields = ['id', 'reason', 'document', 'status',
                  'reviewer_note', 'created_at', 'reviewed_at']
        read_only_fields = ['status', 'reviewer_note', 'reviewed_at']