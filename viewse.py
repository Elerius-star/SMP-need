from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import (
    Notification, Report, Follow, FollowRequest, Reaction,
    Conversation, Message, TypingIndicator, Like,
)
from .serializers import (
    NotificationSerializer, ReportSerializer, ConversationSerializer,
    MessageSerializer, ReactionSerializer, FollowSerializer, FollowRequestSerializer,
)

User = get_user_model()


@api_view(['POST'])
def toggle_follow(request, user_id):
    target = get_object_or_404(User, id=user_id)
    if target == request.user:
        return Response({'detail': "Can't follow yourself."}, status=400)
    if target.is_private:
        req, created = FollowRequest.objects.get_or_create(
            requester=request.user, target=target)
        if not created and req.accepted is None:
            req.delete()
            return Response({'following': False, 'requested': False})
        Notification.objects.create(recipient=target, actor=request.user,
                                    type='follow_request')
        return Response({'requested': True, 'following': False})
    f, created = Follow.objects.get_or_create(follower=request.user, following=target)
    if not created:
        f.delete()
        request.user.update_counters()
        target.update_counters()
        return Response({'following': False})
    request.user.update_counters()
    target.update_counters()
    Notification.objects.create(recipient=target, actor=request.user, type='follow')
    return Response({'following': True})


@api_view(['POST'])
def accept_follow_request(request, req_id):
    req = get_object_or_404(FollowRequest, id=req_id, target=request.user)
    req.accepted = True
    req.save(update_fields=['accepted'])
    Follow.objects.get_or_create(follower=req.requester, following=req.target)
    req.requester.update_counters()
    req.target.update_counters()
    return Response({'accepted': True})


@api_view(['POST'])
def reject_follow_request(request, req_id):
    req = get_object_or_404(FollowRequest, id=req_id, target=request.user)
    req.accepted = False
    req.save(update_fields=['accepted'])
    return Response({'rejected': True})


@api_view(['GET'])
def pending_follow_requests(request):
    reqs = FollowRequest.objects.filter(target=request.user, accepted__isnull=True)
    return Response(FollowRequestSerializer(reqs, many=True).data)


@api_view(['GET'])
def user_followers(request, username):
    u = get_object_or_404(User, username=username)
    followers = [f.follower for f in u.followers_set.select_related('follower')]
    from accounts.serializers import UserMiniSerializer
    return Response(UserMiniSerializer(followers, many=True).data)


@api_view(['GET'])
def user_following(request, username):
    u = get_object_or_404(User, username=username)
    following = [f.following for f in u.following_set.select_related('following')]
    from accounts.serializers import UserMiniSerializer
    return Response(UserMiniSerializer(following, many=True).data)


@api_view(['GET'])
def notifications(request):
    ns = Notification.objects.filter(recipient=request.user).select_related('actor')[:50]
    return Response(NotificationSerializer(ns, many=True).data)


@api_view(['POST'])
def mark_read(request, pk=None):
    qs = Notification.objects.filter(recipient=request.user)
    if pk:
        qs = qs.filter(pk=pk)
    qs.update(is_read=True)
    return Response({'status': 'ok'})


@api_view(['POST'])
def create_report(request):
    serializer = ReportSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(reporter=request.user)
    return Response(serializer.data, status=201)


@api_view(['POST'])
def react_to_post(request, post_id):
    from posts.models import Post
    post = get_object_or_404(Post, id=post_id)
    kind = request.data.get('kind', 'like')
    r, created = Reaction.objects.update_or_create(
        user=request.user, post=post, defaults={'kind': kind})
    return Response(ReactionSerializer(r).data)


# ─── DM endpoints ─────────────────────────────────────────────
@api_view(['GET', 'POST'])
def conversations(request):
    if request.method == 'GET':
        qs = request.user.conversations.all().prefetch_related('participants')
        return Response(ConversationSerializer(qs, many=True, context={'request': request}).data)
    # create new
    user_ids = request.data.get('user_ids', [])
    is_group = request.data.get('is_group', False)
    name = request.data.get('name', '')
    if not user_ids:
        return Response({'detail': 'user_ids required'}, status=400)
    users = User.objects.filter(id__in=user_ids)
    if not is_group and users.count() == 1:
        # find existing 1:1
        existing = Conversation.objects.filter(is_group=False,
                                               participants=request.user).filter(
                                               participants=users.first()).first()
        if existing:
            return Response(ConversationSerializer(existing, context={'request': request}).data)
    conv = Conversation.objects.create(is_group=is_group, name=name)
    conv.participants.add(request.user, *users)
    if is_group:
        conv.admins.add(request.user)
    return Response(ConversationSerializer(conv, context={'request': request}).data, status=201)


@api_view(['GET'])
def conversation_messages(request, conv_id):
    conv = get_object_or_404(Conversation, id=conv_id, participants=request.user)
    msgs = conv.messages.all().select_related('sender')
    Message.objects.filter(conversation=conv, is_read=False).exclude(
        sender=request.user).update(is_read=True, read_at=timezone.now())
    return Response(MessageSerializer(msgs, many=True).data)


@api_view(['POST'])
def send_message(request, conv_id):
    conv = get_object_or_404(Conversation, id=conv_id, participants=request.user)
    serializer = MessageSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    msg = serializer.save(sender=request.user, conversation=conv)
    conv.updated_at = timezone.now()
    conv.save(update_fields=['updated_at'])
    for p in conv.participants.exclude(id=request.user.id):
        Notification.objects.create(recipient=p, actor=request.user, type='dm')
    return Response(MessageSerializer(msg).data, status=201)


@api_view(['POST'])
def upload_message_media(request, conv_id):
    conv = get_object_or_404(Conversation, id=conv_id, participants=request.user)
    f = request.FILES.get('file')
    if not f:
        return Response({'detail': 'No file.'}, status=400)
    m = Message.objects.create(conversation=conv, sender=request.user, file=f)
    return Response(MessageSerializer(m).data, status=201)


@api_view(['POST'])
def typing(request, conv_id):
    conv = get_object_or_404(Conversation, id=conv_id, participants=request.user)
    TypingIndicator.objects.update_or_create(conversation=conv, user=request.user)
    return Response({'ok': True})


@api_view(['GET'])
def who_is_typing(request, conv_id):
    conv = get_object_or_404(Conversation, id=conv_id, participants=request.user)
    cutoff = timezone.now() - timezone.timedelta(seconds=5)
    active = TypingIndicator.objects.filter(conversation=conv, updated_at__gte=cutoff)\
        .exclude(user=request.user).values_list('user__username', flat=True)
    return Response({'typing': list(active)})