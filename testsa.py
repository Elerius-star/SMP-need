"""
posts/tests.py
──────────────
Tests for posts, comments, likes, bookmarks, polls, reposts,
quotes, drafts, scheduling, hashtags, analytics.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from .models import (
    Post, Comment, CommentLike, Bookmark, Hashtag,
    Poll, PollOption, PollVote, SavedSearch, PostAnalytics,
)
from .utils import extract_hashtags, extract_mentions, extract_first_url

User = get_user_model()


class UtilsTests(TestCase):
    def test_extract_hashtags(self):
        self.assertEqual(sorted(extract_hashtags('hi #Python #django')), ['django', 'python'])

    def test_extract_mentions(self):
        self.assertEqual(sorted(extract_mentions('@alice @bob hello')), ['alice', 'bob'])

    def test_extract_first_url(self):
        self.assertEqual(extract_first_url('check https://x.com here'), 'https://x.com')

    def test_extract_no_url(self):
        self.assertEqual(extract_first_url('no url here'), '')


class PostModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')

    def test_create_post(self):
        p = Post.objects.create(author=self.user, content='hello world')
        self.assertEqual(p.author, self.user)
        self.assertEqual(p.likes_count, 0)

    def test_hashtag_extracted_on_save(self):
        p = Post.objects.create(author=self.user, content='hi #python #django')
        self.assertIn('python', p.hashtags)
        self.assertIn('django', p.hashtags)

    def test_mention_extracted_on_save(self):
        p = Post.objects.create(author=self.user, content='hi @alice')
        self.assertIn('alice', p.mentions)

    def test_update_counters(self):
        p = Post.objects.create(author=self.user, content='x')
        p.update_counters()
        self.assertEqual(p.likes_count, 0)


class PostCRUDTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_create_post(self):
        resp = self.client.post('/api/posts/', {'content': 'hello'}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Post.objects.count(), 1)

    def test_create_post_too_long(self):
        resp = self.client.post('/api/posts/', {'content': 'x' * 2100}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_list_posts(self):
        Post.objects.create(author=self.user, content='a')
        Post.objects.create(author=self.user, content='b')
        resp = self.client.get('/api/posts/')
        results = resp.data.get('results', resp.data)
        self.assertEqual(len(results), 2)

    def test_delete_own_post(self):
        p = Post.objects.create(author=self.user, content='x')
        resp = self.client.delete(f'/api/posts/{p.id}/')
        self.assertEqual(resp.status_code, 204)

    def test_cannot_delete_other_post(self):
        other = User.objects.create_user(username='b', email='b@x.com', password='Str0ng!Pass')
        p = Post.objects.create(author=other, content='x')
        resp = self.client.delete(f'/api/posts/{p.id}/')
        self.assertEqual(resp.status_code, 403)

    def test_edit_own_post(self):
        p = Post.objects.create(author=self.user, content='old')
        resp = self.client.patch(f'/api/posts/{p.id}/', {'content': 'new'}, format='json')
        self.assertEqual(resp.status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.content, 'new')
        self.assertTrue(p.is_edited)


class LikeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        self.post = Post.objects.create(author=self.user, content='x')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_like_post(self):
        resp = self.client.post(f'/api/posts/{self.post.id}/like/')
        self.assertTrue(resp.data['liked'])
        self.assertEqual(resp.data['count'], 1)

    def test_unlike_post(self):
        self.client.post(f'/api/posts/{self.post.id}/like/')
        resp = self.client.post(f'/api/posts/{self.post.id}/like/')
        self.assertFalse(resp.data['liked'])


class BookmarkTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        self.post = Post.objects.create(author=self.user, content='x')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_bookmark_toggle(self):
        resp = self.client.post(f'/api/posts/{self.post.id}/bookmark/')
        self.assertTrue(resp.data['bookmarked'])
        resp = self.client.post(f'/api/posts/{self.post.id}/bookmark/')
        self.assertFalse(resp.data['bookmarked'])

    def test_list_bookmarks(self):
        Bookmark.objects.create(user=self.user, post=self.post)
        resp = self.client.get('/api/posts/bookmarks/')
        self.assertEqual(len(resp.data), 1)


class CommentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        self.post = Post.objects.create(author=self.user, content='x')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_create_comment(self):
        resp = self.client.post(f'/api/posts/{self.post.id}/comments/', {'content': 'nice'}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.post.refresh_from_db()
        self.assertEqual(self.post.comments_count, 1)

    def test_list_comments(self):
        Comment.objects.create(post=self.post, author=self.user, content='a')
        Comment.objects.create(post=self.post, author=self.user, content='b')
        resp = self.client.get(f'/api/posts/{self.post.id}/comments/')
        results = resp.data.get('results', resp.data)
        self.assertEqual(len(results), 2)

    def test_delete_own_comment(self):
        c = Comment.objects.create(post=self.post, author=self.user, content='x')
        resp = self.client.delete(f'/api/posts/comments/{c.id}/')
        self.assertEqual(resp.status_code, 204)

    def test_comment_like_toggle(self):
        c = Comment.objects.create(post=self.post, author=self.user, content='x')
        resp = self.client.post(f'/api/posts/comments/{c.id}/like/')
        self.assertTrue(resp.data['liked'])
        resp = self.client.post(f'/api/posts/comments/{c.id}/like/')
        self.assertFalse(resp.data['liked'])


class RepostQuoteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        self.post = Post.objects.create(author=self.user, content='original')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_repost(self):
        resp = self.client.post(f'/api/posts/{self.post.id}/repost/')
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data['is_repost'])

    def test_quote_post(self):
        resp = self.client.post(f'/api/posts/{self.post.id}/quote/', {'content': 'my take'}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data['is_quote'])


class DraftTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_create_draft(self):
        resp = self.client.post('/api/posts/drafts/', {'content': 'draft'}, format='json')
        self.assertEqual(resp.status_code, 201)

    def test_list_drafts(self):
        Post.objects.create(author=self.user, content='d', is_draft=True)
        resp = self.client.get('/api/posts/drafts/')
        self.assertEqual(len(resp.data), 1)


class ScheduleTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_schedule_post(self):
        future = (timezone.now() + timedelta(days=1)).isoformat()
        resp = self.client.post('/api/posts/scheduled/', {
            'content': 'later', 'scheduled_for': future}, format='json')
        self.assertEqual(resp.status_code, 201)


class HashtagTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_trending(self):
        Hashtag.objects.create(name='python', post_count=10)
        resp = self.client.get('/api/posts/trending/')
        self.assertEqual(len(resp.data), 1)

    def test_by_hashtag(self):
        Post.objects.create(author=self.user, content='#python rocks')
        resp = self.client.get('/api/posts/hashtag/python/')
        results = resp.data.get('results', resp.data)
        self.assertGreaterEqual(len(results), 1)


class PollTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        self.post = Post.objects.create(author=self.user, content='vote')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_create_poll(self):
        resp = self.client.post(f'/api/posts/{self.post.id}/poll/', {
            'question': 'Best?', 'options': ['A', 'B']}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(PollOption.objects.count(), 2)

    def test_create_poll_too_few_options(self):
        resp = self.client.post(f'/api/posts/{self.post.id}/poll/', {
            'question': 'Best?', 'options': ['A']}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_vote_poll(self):
        poll = Poll.objects.create(post=self.post, question='Best?')
        a = PollOption.objects.create(poll=poll, text='A')
        PollOption.objects.create(poll=poll, text='B')
        resp = self.client.post(f'/api/posts/polls/{poll.id}/vote/', {'option_id': a.id}, format='json')
        self.assertEqual(resp.status_code, 200)
        a.refresh_from_db()
        self.assertEqual(a.votes_count, 1)

    def test_vote_changes(self):
        poll = Poll.objects.create(post=self.post, question='Best?')
        a = PollOption.objects.create(poll=poll, text='A')
        b = PollOption.objects.create(poll=poll, text='B')
        self.client.post(f'/api/posts/polls/{poll.id}/vote/', {'option_id': a.id}, format='json')
        self.client.post(f'/api/posts/polls/{poll.id}/vote/', {'option_id': b.id}, format='json')
        self.assertEqual(PollVote.objects.filter(poll=poll).count(), 1)


class AnalyticsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        self.post = Post.objects.create(author=self.user, content='x')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_analytics_owner_only(self):
        resp = self.client.get(f'/api/posts/{self.post.id}/analytics/')
        self.assertEqual(resp.status_code, 200)

    def test_analytics_not_owner(self):
        other = User.objects.create_user(username='b', email='b@x.com', password='Str0ng!Pass')
        other_post = Post.objects.create(author=other, content='x')
        resp = self.client.get(f'/api/posts/{other_post.id}/analytics/')
        self.assertEqual(resp.status_code, 403)


class PinTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        self.p = Post.objects.create(author=self.user, content='x')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_pin_post(self):
        resp = self.client.post(f'/api/posts/{self.p.id}/pin/')
        self.p.refresh_from_db()
        self.assertTrue(self.p.is_pinned)

    def test_only_one_pinned(self):
        p2 = Post.objects.create(author=self.user, content='y')
        self.client.post(f'/api/posts/{self.p.id}/pin/')
        self.client.post(f'/api/posts/{p2.id}/pin/')
        self.p.refresh_from_db()
        p2.refresh_from_db()
        self.assertFalse(self.p.is_pinned)
        self.assertTrue(p2.is_pinned)


class SavedSearchTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_save_search(self):
        resp = self.client.post('/api/posts/searches/', {'query': 'python'}, format='json')
        self.assertEqual(resp.status_code, 201)

    def test_list_searches(self):
        SavedSearch.objects.create(user=self.user, query='x')
        resp = self.client.get('/api/posts/searches/')
        self.assertEqual(len(resp.data), 1)

    def test_delete_search(self):
        s = SavedSearch.objects.create(user=self.user, query='x')
        resp = self.client.delete(f'/api/posts/searches/{s.id}/')
        self.assertEqual(resp.status_code, 204)