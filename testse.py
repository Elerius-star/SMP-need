"""
social/tests.py
───────────────
Tests for follows, follow requests, notifications, DMs,
typing indicators, reports, reactions.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from .models import (
    Follow, FollowRequest, Notification, Report,
    Reaction, Conversation, Message, TypingIndicator, Like,
)
from posts.models import Post

User = get_user_model()


class FollowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.a = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        self.b = User.objects.create_user(username='b', email='b@x.com', password='Str0ng!Pass')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_follow_public(self):
        resp = self.client.post(f'/api/social/follow/{self.b.id}/')
        self.assertTrue(resp.data['following'])
        self.assertTrue(Follow.objects.filter(follower=self.a, following=self.b).exists())

    def test_unfollow(self):
        self.client.post(f'/api/social/follow/{self.b.id}/')
        resp = self.client.post(f'/api/social/follow/{self.b.id}/')
        self.assertFalse(resp.data['following'])

    def test_follow_self_blocked(self):
        resp = self.client.post(f'/api/social/follow/{self.a.id}/')
        self.assertEqual(resp.status_code, 400)

    def test_follow_private_creates_request(self):
        self.b.is_private = True
        self.b.save()
        resp = self.client.post(f'/api/social/follow/{self.b.id}/')
        self.assertTrue(resp.data['requested'])
        self.assertTrue(FollowRequest.objects.filter(requester=self.a, target=self.b).exists())

    def test_counters_update(self):
        self.client.post(f'/api/social/follow/{self.b.id}/')
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual(self.a.following_count, 1)
        self.assertEqual(self.b.followers_count, 1)

    def test_followers_list(self):
        Follow.objects.create(follower=self.a, following=self.b)
        resp = self.client.get('/api/social/followers/b/')
        self.assertEqual(len(resp.data), 1)

    def test_following_list(self):
        Follow.objects.create(follower=self.a, following=self.b)
        resp = self.client.get('/api/social/following/a/')
        self.assertEqual(len(resp.data), 1)


class FollowRequestTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.a = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        self.b = User.objects.create_user(username='b', email='b@x.com', password='Str0ng!Pass')
        self.b.is_private = True
        self.b.save()
        self.req = FollowRequest.objects.create(requester=self.a, target=self.b)
        resp = self.client.post('/api/auth/login/', {'username': 'b', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_accept_request(self):
        resp = self.client.post(f'/api/social/follow/accept/{self.req.id}/')
        self.assertTrue(resp.data['accepted'])
        self.assertTrue(Follow.objects.filter(follower=self.a, following=self.b).exists())

    def test_reject_request(self):
        resp = self.client.post(f'/api/social/follow/reject/{self.req.id}/')
        self.assertTrue(resp.data['rejected'])
        self.req.refresh_from_db()
        self.assertFalse(self.req.accepted)

    def test_pending_list(self):
        resp = self.client.get('/api/social/follow/requests/')
        self.assertEqual(len(resp.data), 1)


class NotificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.a = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        self.b = User.objects.create_user(username='b', email='b@x.com', password='Str0ng!Pass')
        Notification.objects.create(recipient=self.a, actor=self.b, type='follow')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_list_notifications(self):
        resp = self.client.get('/api/social/notifications/')
        self.assertEqual(len(resp.data), 1)

    def test_mark_all_read(self):
        self.client.post('/api/social/notifications/read/')
        n = Notification.objects.get(recipient=self.a)
        self.assertTrue(n.is_read)

    def test_mark_one_read(self):
        n = Notification.objects.get(recipient=self.a)
        self.client.post(f'/api/social/notifications/read/{n.id}/')
        n.refresh_from_db()
        self.assertTrue(n.is_read)


class ReportTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.a = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        self.b = User.objects.create_user(username='b', email='b@x.com', password='Str0ng!Pass')
        self.post = Post.objects.create(author=self.b, content='bad')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_create_report(self):
        resp = self.client.post('/api/social/report/', {
            'post': self.post.id, 'reason': 'spam'}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Report.objects.filter(reporter=self.a).exists())


class ReactionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.a = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        self.post = Post.objects.create(author=self.a, content='x')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_react(self):
        resp = self.client.post(f'/api/social/react/{self.post.id}/', {'kind': 'love'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['kind'], 'love')

    def test_react_override(self):
        self.client.post(f'/api/social/react/{self.post.id}/', {'kind': 'love'}, format='json')
        resp = self.client.post(f'/api/social/react/{self.post.id}/', {'kind': 'haha'}, format='json')
        self.assertEqual(resp.data['kind'], 'haha')


class ConversationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.a = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        self.b = User.objects.create_user(username='b', email='b@x.com', password='Str0ng!Pass')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_create_1to1(self):
        resp = self.client.post('/api/social/conversations/', {'user_ids': [self.b.id]}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertFalse(resp.data['is_group'])

    def test_create_returns_existing(self):
        r1 = self.client.post('/api/social/conversations/', {'user_ids': [self.b.id]}, format='json')
        r2 = self.client.post('/api/social/conversations/', {'user_ids': [self.b.id]}, format='json')
        self.assertEqual(r1.data['id'], r2.data['id'])

    def test_create_group(self):
        c = User.objects.create_user(username='c', email='c@x.com', password='Str0ng!Pass')
        resp = self.client.post('/api/social/conversations/', {
            'user_ids': [self.b.id, c.id], 'is_group': True, 'name': 'Team'}, format='json')
        self.assertTrue(resp.data['is_group'])
        self.assertEqual(resp.data['name'], 'Team')

    def test_list_conversations(self):
        self.client.post('/api/social/conversations/', {'user_ids': [self.b.id]}, format='json')
        resp = self.client.get('/api/social/conversations/')
        self.assertEqual(len(resp.data), 1)

    def test_send_message(self):
        conv = self.client.post('/api/social/conversations/', {'user_ids': [self.b.id]}, format='json').data
        resp = self.client.post(f"/api/social/conversations/{conv['id']}/send/",
                                {'content': 'hi'}, format='json')
        self.assertEqual(resp.status_code, 201)

    def test_list_messages(self):
        conv = self.client.post('/api/social/conversations/', {'user_ids': [self.b.id]}, format='json').data
        self.client.post(f"/api/social/conversations/{conv['id']}/send/", {'content': 'hi'}, format='json')
        resp = self.client.get(f"/api/social/conversations/{conv['id']}/messages/")
        self.assertEqual(len(resp.data), 1)

    def test_send_marks_notification(self):
        conv = self.client.post('/api/social/conversations/', {'user_ids': [self.b.id]}, format='json').data
        self.client.post(f"/api/social/conversations/{conv['id']}/send/", {'content': 'hi'}, format='json')
        self.assertTrue(Notification.objects.filter(recipient=self.b, type='dm').exists())

    def test_mark_read_on_fetch(self):
        conv_data = self.client.post('/api/social/conversations/', {'user_ids': [self.b.id]}, format='json').data
        # b sends a message
        client2 = APIClient()
        r = client2.post('/api/auth/login/', {'username': 'b', 'password': 'Str0ng!Pass'}, format='json')
        client2.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        client2.post(f"/api/social/conversations/{conv_data['id']}/send/", {'content': 'yo'}, format='json')
        # a fetches messages
        self.client.get(f"/api/social/conversations/{conv_data['id']}/messages/")
        self.assertTrue(Message.objects.filter(conversation_id=conv_data['id'], is_read=True).exists())


class TypingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.a = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        self.b = User.objects.create_user(username='b', email='b@x.com', password='Str0ng!Pass')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
        self.conv = self.client.post('/api/social/conversations/', {'user_ids': [self.b.id]}, format='json').data

    def test_set_typing(self):
        resp = self.client.post(f"/api/social/conversations/{self.conv['id']}/typing/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(TypingIndicator.objects.filter(conversation_id=self.conv['id']).exists())

    def test_who_typing(self):
        client2 = APIClient()
        r = client2.post('/api/auth/login/', {'username': 'b', 'password': 'Str0ng!Pass'}, format='json')
        client2.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        client2.post(f"/api/social/conversations/{self.conv['id']}/typing/")
        resp = self.client.get(f"/api/social/conversations/{self.conv['id']}/typing/who/")
        self.assertIn('b', resp.data['typing'])


class LikeCreationTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        self.post = Post.objects.create(author=self.a, content='x')

    def test_like_unique(self):
        Like.objects.create(user=self.a, post=self.post)
        with self.assertRaises(Exception):
            Like.objects.create(user=self.a, post=self.post)