from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Sum
from django.utils import timezone
from datetime import timedelta
from .models import (
    Post, Comment, CommentLike, Bookmark, Hashtag,
    Poll, PollOption, PollVote, SavedSearch, PostAnalytics,
)
from .serializers import (
    PostSerializer, CommentSerializer, BookmarkSerializer,
    HashtagSerializer, PollSerializer, SavedSearchSerializer,
    CommentLikeSerializer, PostAnalyticsSerializer,
)
from .utils import notify_mentions, recompute_trend_scores, humanize_number


class FeedView(generics.ListAPIView):
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        qs = Post.objects.filter(is_draft=False, published_at__lte=timezone.now())
        if user.is_authenticated:
            following_ids = user.following_set.values_list('following_id', flat=True)
            qs = qs.filter(Q(author__in=following_ids) | Q(author=user))
            qs = qs.exclude(author__in=user.blocking.values_list('blocked_id', flat=True))
            muted_ids = user.muting.values_list('muted_id', flat=True)
            qs = qs.exclude(author__in=muted_ids)
            muted_words = list(user.muted_words.values_list('word', flat=True))
            for w in muted_words:
                qs = qs.exclude(content__icontains=w)
        return qs.select_related('author').prefetch_related('likes', 'comments', 'poll')


class PostListCreate(generics.ListCreateAPIView):
    serializer_class = PostSerializer

    def get_queryset(self):
        return Post.objects.filter(is_draft=False, published_at__lte=timezone.now()) \
                           .select_related('author')

    def perform_create(self, serializer):
        publish_now = not serializer.validated_data.get('scheduled_for')
        post = serializer.save(
            author=self.request.user,
            published_at=timezone.now() if publish_now else serializer.validated_data.get('scheduled_for'),
        )
        self.request.user.update_counters()
        for tag in (post.hashtags.split(',') if post.hashtags else []):
            if tag:
                obj, _ = Hashtag.objects.get_or_create(name=tag)
                obj.post_count += 1
                obj.save(update_fields=['post_count'])
        notify_mentions(post)
        PostAnalytics.objects.get_or_create(post=post)


class PostDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Post.objects.all()
    serializer_class = PostSerializer

    def retrieve(self, request, *args, **kwargs):
        post = self.get_object()
        PostAnalytics.objects.get_or_create(post=post)
        PostAnalytics.objects.filter(post=post).update(impressions=Count('post') + 0)  # placeholder
        Post.objects.filter(pk=post.pk).update(views_count=post.views_count + 1)
        return super().retrieve(request, *args, **kwargs)

    def perform_destroy(self, instance):
        if instance.author != self.request.user:
            raise permissions.PermissionDenied()
        instance.delete()
        self.request.user.update_counters()

    def perform_update(self, serializer):
        serializer.save(is_edited=True, edited_at=timezone.now())


@api_view(['POST'])
def toggle_like(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    from social.models import Like, Notification
    like, created = Like.objects.get_or_create(user=request.user, post=post)
    if not created:
        like.delete()
        post.update_counters()
        return Response({'liked': False, 'count': post.likes_count})
    post.update_counters()
    if post.author != request.user:
        Notification.objects.create(recipient=post.author, actor=request.user,
                                    type='like', post=post)
    return Response({'liked': True, 'count': post.likes_count})


@api_view(['POST'])
def toggle_comment_like(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    like, created = CommentLike.objects.get_or_create(user=request.user, comment=comment)
    if not created:
        like.delete()
    comment.likes_count = comment.likes.count()
    comment.save(update_fields=['likes_count'])
    return Response({'liked': created, 'count': comment.likes_count})


@api_view(['POST'])
def toggle_bookmark(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    bm, created = Bookmark.objects.get_or_create(user=request.user, post=post)
    if not created:
        bm.delete()
        return Response({'bookmarked': False})
    return Response({'bookmarked': True})


@api_view(['GET'])
def my_bookmarks(request):
    bms = Bookmark.objects.filter(user=request.user).select_related('post__author')
    return Response(BookmarkSerializer(bms, many=True, context={'request': request}).data)


class CommentListCreate(generics.ListCreateAPIView):
    serializer_class = CommentSerializer

    def get_queryset(self):
        return Comment.objects.filter(post_id=self.kwargs['post_id'], parent=None)

    def perform_create(self, serializer):
        post = get_object_or_404(Post, id=self.kwargs['post_id'])
        serializer.save(author=self.request.user, post=post)
        post.update_counters()
        from social.models import Notification
        if post.author != self.request.user:
            Notification.objects.create(recipient=post.author, actor=self.request.user,
                                        type='comment', post=post)


@api_view(['DELETE'])
def delete_comment(request, pk):
    comment = get_object_or_404(Comment, id=pk)
    if comment.author != request.user:
        return Response({'detail': 'Not allowed.'}, status=403)
    post = comment.post
    comment.delete()
    post.update_counters()
    return Response(status=204)


@api_view(['POST'])
def repost(request, post_id):
    original = get_object_or_404(Post, id=post_id)
    new_post = Post.objects.create(author=request.user, content='',
                                   is_repost=True, original_post=original)
    original.update_counters()
    from social.models import Notification
    if original.author != request.user:
        Notification.objects.create(recipient=original.author, actor=request.user,
                                    type='repost', post=original)
    return Response(PostSerializer(new_post, context={'request': request}).data, status=201)


@api_view(['POST'])
def quote_post(request, post_id):
    original = get_object_or_404(Post, id=post_id)
    content = request.data.get('content', '')
    post = Post.objects.create(author=request.user, content=content,
                               is_quote=True, original_post=original)
    original.update_counters()
    return Response(PostSerializer(post, context={'request': request}).data, status=201)


@api_view(['GET'])
def trending_hashtags(request):
    recompute_trend_scores()
    tags = Hashtag.objects.order_by('-trend_score', '-post_count')[:10]
    return Response(HashtagSerializer(tags, many=True).data)


@api_view(['GET'])
def by_hashtag(request, tag):
    posts = Post.objects.filter(hashtags__icontains=tag, is_draft=False)[:50]
    return Response(PostSerializer(posts, many=True, context={'request': request}).data)


@api_view(['GET'])
def user_posts(request, username):
    posts = Post.objects.filter(author__username=username, is_draft=False)
    return Response(PostSerializer(posts, many=True, context={'request': request}).data)


@api_view(['GET'])
def user_likes(request, username):
    from social.models import Like
    likes = Like.objects.filter(user__username=username).select_related('post__author')[:50]
    return Response(PostSerializer([l.post for l in likes], many=True,
                                   context={'request': request}).data)


@api_view(['GET'])
def user_media(request, username):
    posts = Post.objects.filter(author__username=username, is_draft=False).exclude(
        Q(image='') & Q(video=''))
    return Response(PostSerializer(posts, many=True, context={'request': request}).data)


@api_view(['GET', 'POST'])
def drafts(request):
    if request.method == 'GET':
        ds = Post.objects.filter(author=request.user, is_draft=True)
        return Response(PostSerializer(ds, many=True).data)
    serializer = PostSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(author=request.user, is_draft=True)
    return Response(serializer.data, status=201)


@api_view(['GET', 'POST'])
def schedule(request):
    if request.method == 'GET':
        s = Post.objects.filter(author=request.user, scheduled_for__gt=timezone.now())
        return Response(PostSerializer(s, many=True).data)
    serializer = PostSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(author=request.user, is_draft=True)
    return Response(serializer.data, status=201)


@api_view(['GET', 'POST'])
def saved_searches(request):
    if request.method == 'GET':
        ss = SavedSearch.objects.filter(user=request.user)
        return Response(SavedSearchSerializer(ss, many=True).data)
    ser = SavedSearchSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    ser.save(user=request.user)
    return Response(ser.data, status=201)


@api_view(['DELETE'])
def delete_saved_search(request, pk):
    SavedSearch.objects.filter(user=request.user, pk=pk).delete()
    return Response(status=204)


# ─── Polls ────────────────────────────────────────────────────
@api_view(['POST'])
def create_poll(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if post.author != request.user:
        return Response({'detail': 'Not allowed.'}, status=403)
    question = request.data.get('question', '')
    options = request.data.get('options', [])
    ends_at = request.data.get('ends_at')
    if not question or len(options) < 2:
        return Response({'detail': 'Question + 2 options required.'}, status=400)
    poll = Poll.objects.create(post=post, question=question, ends_at=ends_at)
    for text in options[:4]:
        PollOption.objects.create(poll=poll, text=text)
    return Response(PollSerializer(poll).data, status=201)


@api_view(['POST'])
def vote_poll(request, poll_id):
    poll = get_object_or_404(Poll, id=poll_id)
    if not poll.is_open():
        return Response({'detail': 'Poll closed.'}, status=400)
    option_id = request.data.get('option_id')
    option = get_object_or_404(PollOption, id=option_id, poll=poll)
    vote, created = PollVote.objects.get_or_create(user=request.user, poll=poll)
    if not created:
        vote.option = option
        vote.save()
    else:
        option.votes_count += 1
        option.save(update_fields=['votes_count'])
    return Response(PollSerializer(poll).data)


@api_view(['GET'])
def post_analytics(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if post.author != request.user:
        return Response({'detail': 'Not allowed.'}, status=403)
    analytics, _ = PostAnalytics.objects.get_or_create(post=post)
    return Response({
        'impressions': analytics.impressions,
        'profile_clicks': analytics.profile_clicks,
        'link_clicks': analytics.link_clicks,
        'detail_expands': analytics.detail_expands,
        'likes': post.likes_count,
        'comments': post.comments_count,
        'reposts': post.reposts_count,
        'views': post.views_count,
        'humanized_views': humanize_number(post.views_count),
    })


@api_view(['POST'])
def pin_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if post.author != request.user:
        return Response({'detail': 'Not allowed.'}, status=403)
    Post.objects.filter(author=request.user).update(is_pinned=False)
    post.is_pinned = True
    post.save(update_fields=['is_pinned'])
    return Response({'pinned': True})