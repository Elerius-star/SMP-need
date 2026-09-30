from django.contrib.auth import authenticate
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from .models import (
    User, Block, Mute, MutedWord, EmailVerificationToken,
    PasswordResetToken, LoginHistory, DeviceSession,
    ProfileVerificationRequest, UserSettings,
)
from .serializers import (
    UserSerializer, UserMiniSerializer, RegisterSerializer,
    BlockSerializer, MuteSerializer, MutedWordSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    ChangePasswordSerializer, LoginHistorySerializer,
    DeviceSessionSerializer, ProfileVerificationSerializer,
    UserSettingsSerializer,
)


def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _record_login(request, user, success=True):
    LoginHistory.objects.create(
        user=user,
        ip_address=_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        device=request.META.get('HTTP_SEC_CH_UA_PLATFORM', '')[:100],
        success=success,
    )


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        # create email verification token
        token = EmailVerificationToken.objects.create(user=user)
        # (In production, send email here.)
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user, context={'request': request}).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'verify_token': token.token,  # dev convenience
        }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(username=username, password=password)
    if not user or user.is_deactivated:
        return Response({'detail': 'Invalid credentials.'},
                        status=status.HTTP_401_UNAUTHORIZED)
    _record_login(request, user, True)
    user.touch_last_seen()
    refresh = RefreshToken.for_user(user)
    return Response({
        'user': UserSerializer(user, context={'request': request}).data,
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    })


@api_view(['GET'])
def me_view(request):
    request.user.touch_last_seen()
    return Response(UserSerializer(request.user, context={'request': request}).data)


@api_view(['PATCH'])
def update_me_view(request):
    serializer = UserSerializer(request.user, data=request.data, partial=True,
                                context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(['POST'])
def upload_avatar(request):
    f = request.FILES.get('avatar')
    if not f:
        return Response({'detail': 'No file.'}, status=400)
    request.user.avatar = f
    request.user.save(update_fields=['avatar'])
    return Response({'avatar': request.user.avatar.url})


@api_view(['POST'])
def upload_banner(request):
    f = request.FILES.get('banner')
    if not f:
        return Response({'detail': 'No file.'}, status=400)
    request.user.banner = f
    request.user.save(update_fields=['banner'])
    return Response({'banner': request.user.banner.url})


class UserDetailView(generics.RetrieveAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    lookup_field = 'username'


@api_view(['GET'])
def search_users(request):
    q = request.query_params.get('q', '').strip()
    if not q:
        return Response([])
    users = User.objects.filter(
        Q(username__icontains=q) | Q(bio__icontains=q) | Q(location__icontains=q)
    ).exclude(is_deactivated=True)[:20]
    return Response(UserMiniSerializer(users, many=True, context={'request': request}).data)


@api_view(['POST'])
def toggle_block(request, user_id):
    target = get_object_or_404(User, id=user_id)
    if target == request.user:
        return Response({'detail': "Can't block yourself."}, status=400)
    block, created = Block.objects.get_or_create(blocker=request.user, blocked=target)
    if not created:
        block.delete()
        return Response({'blocked': False})
    return Response({'blocked': True})


@api_view(['GET'])
def blocked_list(request):
    blocks = Block.objects.filter(blocker=request.user).select_related('blocked')
    return Response(BlockSerializer(blocks, many=True).data)


@api_view(['POST'])
def toggle_mute(request, user_id):
    target = get_object_or_404(User, id=user_id)
    mute, created = Mute.objects.get_or_create(muter=request.user, muted=target)
    if not created:
        mute.delete()
        return Response({'muted': False})
    return Response({'muted': True})


@api_view(['GET', 'POST'])
def muted_words(request):
    if request.method == 'GET':
        words = MutedWord.objects.filter(user=request.user)
        return Response(MutedWordSerializer(words, many=True).data)
    serializer = MutedWordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(user=request.user)
    return Response(serializer.data, status=201)


@api_view(['DELETE'])
def delete_muted_word(request, pk):
    MutedWord.objects.filter(user=request.user, pk=pk).delete()
    return Response(status=204)


# ─── Password reset ─────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def password_reset_request(request):
    serializer = PasswordResetRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data['email']
    user = User.objects.filter(email__iexact=email).first()
    if user:
        token = PasswordResetToken.objects.create(user=user)
        send_mail(
            'Reset your SMP-Need password',
            f'Use this token: {token.token}',
            'noreply@smp-need.app',
            [email],
            fail_silently=True,
        )
        return Response({'token': token.token})  # dev convenience
    return Response({'detail': 'If the email exists, we sent a link.'})


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def password_reset_confirm(request):
    serializer = PasswordResetConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    token = serializer.validated_data['token_obj']
    user = token.user
    user.set_password(serializer.validated_data['password'])
    user.save()
    token.used = True
    token.save(update_fields=['used'])
    return Response({'detail': 'Password updated.'})


@api_view(['POST'])
def change_password(request):
    serializer = ChangePasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if not request.user.check_password(serializer.validated_data['old_password']):
        return Response({'old_password': 'Incorrect.'}, status=400)
    request.user.set_password(serializer.validated_data['new_password'])
    request.user.save()
    return Response({'detail': 'Password changed.'})


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def verify_email(request):
    token_str = request.data.get('token')
    try:
        t = EmailVerificationToken.objects.get(token=token_str)
    except EmailVerificationToken.DoesNotExist:
        return Response({'detail': 'Invalid token.'}, status=400)
    if not t.is_valid():
        return Response({'detail': 'Expired or used.'}, status=400)
    t.user.email_verified = True
    t.user.save(update_fields=['email_verified'])
    t.used = True
    t.save(update_fields=['used'])
    return Response({'detail': 'Email verified.'})


@api_view(['POST'])
def deactivate_account(request):
    request.user.is_deactivated = True
    request.user.save(update_fields=['is_deactivated'])
    return Response({'detail': 'Account deactivated.'})


@api_view(['POST'])
def reactivate_account(request):
    request.user.is_deactivated = False
    request.user.save(update_fields=['is_deactivated'])
    return Response({'detail': 'Account reactivated.'})


@api_view(['GET'])
def login_history(request):
    hist = LoginHistory.objects.filter(user=request.user)[:50]
    return Response(LoginHistorySerializer(hist, many=True).data)


@api_view(['GET'])
def device_sessions(request):
    sessions = DeviceSession.objects.filter(user=request.user, is_revoked=False)
    return Response(DeviceSessionSerializer(sessions, many=True).data)


@api_view(['POST'])
def revoke_session(request, pk):
    DeviceSession.objects.filter(user=request.user, pk=pk).update(is_revoked=True)
    return Response(status=204)


@api_view(['POST'])
def request_verification(request):
    serializer = ProfileVerificationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(user=request.user)
    return Response(serializer.data, status=201)


@api_view(['GET', 'PATCH'])
def my_settings(request):
    s, _ = UserSettings.objects.get_or_create(user=request.user)
    if request.method == 'GET':
        return Response(UserSettingsSerializer(s).data)
    ser = UserSettingsSerializer(s, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    ser.save()
    return Response(ser.data)