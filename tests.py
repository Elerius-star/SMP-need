"""
accounts/tests.py
─────────────────
Tests for registration, login, password reset, blocks, mutes,
verification, sessions, and profile updates.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from rest_framework import status
from .models import (
    Block, Mute, MutedWord, EmailVerificationToken,
    PasswordResetToken, LoginHistory, DeviceSession,
    ProfileVerificationRequest, UserSettings,
)

User = get_user_model()


class UserModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com', password='Str0ng!Pass')

    def test_user_creation(self):
        self.assertEqual(self.user.username, 'alice')
        self.assertEqual(self.user.email, 'alice@example.com')
        self.assertTrue(self.user.check_password('Str0ng!Pass'))
        self.assertFalse(self.user.is_verified)
        self.assertFalse(self.user.email_verified)

    def test_user_default_counters(self):
        self.assertEqual(self.user.followers_count, 0)
        self.assertEqual(self.user.following_count, 0)
        self.assertEqual(self.user.posts_count, 0)

    def test_is_online_recent(self):
        self.user.last_seen = timezone.now()
        self.user.save()
        self.assertTrue(self.user.is_online)

    def test_is_online_old(self):
        self.user.last_seen = timezone.now() - timedelta(hours=1)
        self.user.save()
        self.assertFalse(self.user.is_online)

    def test_touch_last_seen(self):
        old = self.user.last_seen
        self.user.touch_last_seen()
        self.assertGreater(self.user.last_seen, old)

    def test_update_counters(self):
        self.user.update_counters()
        self.assertEqual(self.user.posts_count, 0)


class RegisterViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_success(self):
        resp = self.client.post('/api/auth/register/', {
            'username': 'bob',
            'email': 'bob@example.com',
            'password': 'Str0ng!Pass',
            'password2': 'Str0ng!Pass',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', resp.data)
        self.assertIn('refresh', resp.data)
        self.assertTrue(User.objects.filter(username='bob').exists())

    def test_register_password_mismatch(self):
        resp = self.client.post('/api/auth/register/', {
            'username': 'carl',
            'email': 'carl@example.com',
            'password': 'Str0ng!Pass',
            'password2': 'Different!',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_duplicate_username(self):
        User.objects.create_user(username='dave', email='dave@example.com', password='X!y2z3w4')
        resp = self.client.post('/api/auth/register/', {
            'username': 'dave',
            'email': 'other@example.com',
            'password': 'Str0ng!Pass',
            'password2': 'Str0ng!Pass',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_duplicate_email(self):
        User.objects.create_user(username='e', email='e@example.com', password='X!y2z3w4')
        resp = self.client.post('/api/auth/register/', {
            'username': 'e2',
            'email': 'e@example.com',
            'password': 'Str0ng!Pass',
            'password2': 'Str0ng!Pass',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_weak_password(self):
        resp = self.client.post('/api/auth/register/', {
            'username': 'weak',
            'email': 'weak@example.com',
            'password': '123',
            'password2': '123',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_invalid_username_chars(self):
        resp = self.client.post('/api/auth/register/', {
            'username': 'bad user!',
            'email': 'x@example.com',
            'password': 'Str0ng!Pass',
            'password2': 'Str0ng!Pass',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_settings_autocreated(self):
        self.client.post('/api/auth/register/', {
            'username': 'withsettings',
            'email': 'ws@example.com',
            'password': 'Str0ng!Pass',
            'password2': 'Str0ng!Pass',
        }, format='json')
        u = User.objects.get(username='withsettings')
        self.assertTrue(UserSettings.objects.filter(user=u).exists())

    def test_email_token_created(self):
        self.client.post('/api/auth/register/', {
            'username': 'withtoken',
            'email': 'wt@example.com',
            'password': 'Str0ng!Pass',
            'password2': 'Str0ng!Pass',
        }, format='json')
        u = User.objects.get(username='withtoken')
        self.assertTrue(EmailVerificationToken.objects.filter(user=u).exists())


class LoginViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com', password='Str0ng!Pass')

    def test_login_success(self):
        resp = self.client.post('/api/auth/login/', {
            'username': 'alice', 'password': 'Str0ng!Pass'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('access', resp.data)

    def test_login_bad_password(self):
        resp = self.client.post('/api/auth/login/', {
            'username': 'alice', 'password': 'wrong'}, format='json')
        self.assertEqual(resp.status_code, 401)

    def test_login_unknown_user(self):
        resp = self.client.post('/api/auth/login/', {
            'username': 'ghost', 'password': 'x'}, format='json')
        self.assertEqual(resp.status_code, 401)

    def test_login_records_history(self):
        self.client.post('/api/auth/login/', {
            'username': 'alice', 'password': 'Str0ng!Pass'}, format='json')
        self.assertTrue(LoginHistory.objects.filter(user=self.user).exists())

    def test_login_deactivated(self):
        self.user.is_deactivated = True
        self.user.save()
        resp = self.client.post('/api/auth/login/', {
            'username': 'alice', 'password': 'Str0ng!Pass'}, format='json')
        self.assertEqual(resp.status_code, 401)


class MeViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com', password='Str0ng!Pass')
        resp = self.client.post('/api/auth/login/', {
            'username': 'alice', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_me_returns_user(self):
        resp = self.client.get('/api/auth/me/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['username'], 'alice')

    def test_update_me_bio(self):
        resp = self.client.patch('/api/auth/me/update/', {'bio': 'hello world'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.bio, 'hello world')

    def test_change_password(self):
        resp = self.client.post('/api/auth/password/change/', {
            'old_password': 'Str0ng!Pass',
            'new_password': 'N3w!Passw0rd',
            'new_password2': 'N3w!Passw0rd',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('N3w!Passw0rd'))

    def test_change_password_wrong_old(self):
        resp = self.client.post('/api/auth/password/change/', {
            'old_password': 'wrong',
            'new_password': 'N3w!Passw0rd',
            'new_password2': 'N3w!Passw0rd',
        }, format='json')
        self.assertEqual(resp.status_code, 400)


class PasswordResetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com', password='Str0ng!Pass')

    def test_request_reset_creates_token(self):
        self.client.post('/api/auth/password/reset/', {'email': 'alice@example.com'}, format='json')
        self.assertTrue(PasswordResetToken.objects.filter(user=self.user).exists())

    def test_request_reset_unknown_email_ok(self):
        resp = self.client.post('/api/auth/password/reset/', {'email': 'nobody@example.com'}, format='json')
        self.assertEqual(resp.status_code, 200)

    def test_confirm_reset(self):
        token = PasswordResetToken.objects.create(user=self.user)
        resp = self.client.post('/api/auth/password/reset/confirm/', {
            'token': token.token,
            'password': 'N3w!Passw0rd',
            'password2': 'N3w!Passw0rd',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('N3w!Passw0rd'))

    def test_confirm_reset_expired(self):
        token = PasswordResetToken.objects.create(user=self.user)
        token.expires_at = timezone.now() - timedelta(hours=1)
        token.save()
        resp = self.client.post('/api/auth/password/reset/confirm/', {
            'token': token.token,
            'password': 'N3w!Passw0rd',
            'password2': 'N3w!Passw0rd',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_confirm_reset_bad_token(self):
        resp = self.client.post('/api/auth/password/reset/confirm/', {
            'token': 'nonsense',
            'password': 'N3w!Passw0rd',
            'password2': 'N3w!Passw0rd',
        }, format='json')
        self.assertEqual(resp.status_code, 400)


class EmailVerificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com', password='Str0ng!Pass')

    def test_verify_email_success(self):
        token = EmailVerificationToken.objects.create(user=self.user)
        resp = self.client.post('/api/auth/email/verify/', {'token': token.token}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)

    def test_verify_email_invalid(self):
        resp = self.client.post('/api/auth/email/verify/', {'token': 'nonsense'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_verify_email_used(self):
        token = EmailVerificationToken.objects.create(user=self.user)
        token.used = True
        token.save()
        resp = self.client.post('/api/auth/email/verify/', {'token': token.token}, format='json')
        self.assertEqual(resp.status_code, 400)


class BlockMuteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.a = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        self.b = User.objects.create_user(username='b', email='b@x.com', password='Str0ng!Pass')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_block_and_unblock(self):
        resp = self.client.post(f'/api/auth/users/{self.b.id}/block/')
        self.assertTrue(resp.data['blocked'])
        self.assertTrue(Block.objects.filter(blocker=self.a, blocked=self.b).exists())
        resp = self.client.post(f'/api/auth/users/{self.b.id}/block/')
        self.assertFalse(resp.data['blocked'])

    def test_cannot_block_self(self):
        resp = self.client.post(f'/api/auth/users/{self.a.id}/block/')
        self.assertEqual(resp.status_code, 400)

    def test_blocked_list(self):
        Block.objects.create(blocker=self.a, blocked=self.b)
        resp = self.client.get('/api/auth/blocks/')
        self.assertEqual(len(resp.data), 1)

    def test_mute_toggle(self):
        resp = self.client.post(f'/api/auth/users/{self.b.id}/mute/')
        self.assertTrue(resp.data['muted'])
        resp = self.client.post(f'/api/auth/users/{self.b.id}/mute/')
        self.assertFalse(resp.data['muted'])

    def test_add_muted_word(self):
        resp = self.client.post('/api/auth/muted-words/', {'word': 'spoiler'}, format='json')
        self.assertEqual(resp.status_code, 201)

    def test_delete_muted_word(self):
        w = MutedWord.objects.create(user=self.a, word='spoiler')
        resp = self.client.delete(f'/api/auth/muted-words/{w.id}/')
        self.assertEqual(resp.status_code, 204)


class DeviceSessionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_sessions_list(self):
        DeviceSession.objects.create(user=self.user, device_name='iPhone')
        resp = self.client.get('/api/auth/me/sessions/')
        self.assertEqual(len(resp.data), 1)

    def test_revoke_session(self):
        s = DeviceSession.objects.create(user=self.user, device_name='iPhone')
        resp = self.client.post(f'/api/auth/me/sessions/{s.id}/revoke/')
        self.assertEqual(resp.status_code, 204)
        s.refresh_from_db()
        self.assertTrue(s.is_revoked)


class SearchUsersTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='alice', email='a@x.com', password='Str0ng!Pass')
        User.objects.create_user(username='bob', email='b@x.com', password='Str0ng!Pass', bio='bobcat')
        resp = self.client.post('/api/auth/login/', {'username': 'alice', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_search_by_username(self):
        resp = self.client.get('/api/auth/users/search/?q=bob')
        self.assertEqual(len(resp.data), 1)

    def test_search_by_bio(self):
        resp = self.client.get('/api/auth/users/search/?q=bobcat')
        self.assertEqual(len(resp.data), 1)

    def test_search_empty(self):
        resp = self.client.get('/api/auth/users/search/?q=')
        self.assertEqual(resp.data, [])


class DeactivationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_deactivate(self):
        resp = self.client.post('/api/auth/me/deactivate/')
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_deactivated)

    def test_reactivate(self):
        self.user.is_deactivated = True
        self.user.save()
        self.client.post('/api/auth/me/reactivate/')
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_deactivated)


class VerificationRequestTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_request_verification(self):
        resp = self.client.post('/api/auth/me/verification/', {'reason': 'I am public figure'}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(ProfileVerificationRequest.objects.filter(user=self.user).exists())


class SettingsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='a', email='a@x.com', password='Str0ng!Pass')
        UserSettings.objects.create(user=self.user)
        resp = self.client.post('/api/auth/login/', {'username': 'a', 'password': 'Str0ng!Pass'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_get_settings(self):
        resp = self.client.get('/api/auth/me/settings/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('email_notifications', resp.data)

    def test_patch_settings(self):
        resp = self.client.patch('/api/auth/me/settings/', {'email_notifications': False}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data['email_notifications'])