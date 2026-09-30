"""
social/consumers.py
───────────────────
WebSocket consumers for chat, typing indicators, notifications,
and WebRTC signaling.
"""
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Conversation, Message, TypingIndicator, Notification

User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    """Per-conversation WebSocket. Group name: chat_<conversation_id>."""

    async def connect(self):
        self.user = self.scope.get('user')
        if not self.user or self.user.is_anonymous:
            await self.close()
            return
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        if not await self._is_participant():
            await self.close()
            return
        self.group_name = f"chat_{self.conversation_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.channel_layer.group_send(self.group_name, {
            'type': 'presence.join',
            'username': self.user.username,
        })

    async def disconnect(self, code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_send(self.group_name, {
                'type': 'presence.leave',
                'username': self.user.username,
            })
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or '{}')
        except json.JSONDecodeError:
            return
        msg_type = data.get('type', 'message')
        if msg_type == 'message':
            content = (data.get('content') or '').strip()
            if not content:
                return
            msg = await self._save_message(content)
            await self.channel_layer.group_send(self.group_name, {
                'type': 'chat.message',
                'id': msg['id'],
                'sender': self.user.username,
                'sender_id': self.user.id,
                'content': content,
                'created_at': msg['created_at'],
            })
        elif msg_type == 'typing':
            await self._mark_typing()
            await self.channel_layer.group_send(self.group_name, {
                'type': 'chat.typing',
                'username': self.user.username,
            })
        elif msg_type == 'read':
            await self._mark_read()
            await self.channel_layer.group_send(self.group_name, {
                'type': 'chat.read',
                'username': self.user.username,
            })

    # ── Group handlers ─────────────────────────────────────
    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message',
            'id': event['id'],
            'sender': event['sender'],
            'sender_id': event['sender_id'],
            'content': event['content'],
            'created_at': event['created_at'],
        }))

    async def chat_typing(self, event):
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'username': event['username'],
        }))

    async def chat_read(self, event):
        await self.send(text_data=json.dumps({
            'type': 'read',
            'username': event['username'],
        }))

    async def presence_join(self, event):
        await self.send(text_data=json.dumps({
            'type': 'presence',
            'event': 'join',
            'username': event['username'],
        }))

    async def presence_leave(self, event):
        await self.send(text_data=json.dumps({
            'type': 'presence',
            'event': 'leave',
            'username': event['username'],
        }))

    # ── DB helpers ─────────────────────────────────────────
    @database_sync_to_async
    def _is_participant(self):
        return Conversation.objects.filter(
            id=self.conversation_id, participants=self.user).exists()

    @database_sync_to_async
    def _save_message(self, content):
        conv = Conversation.objects.get(id=self.conversation_id)
        msg = Message.objects.create(conversation=conv, sender=self.user, content=content)
        conv.updated_at = timezone.now()
        conv.save(update_fields=['updated_at'])
        return {'id': msg.id, 'created_at': msg.created_at.isoformat()}

    @database_sync_to_async
    def _mark_typing(self):
        TypingIndicator.objects.update_or_create(
            conversation_id=self.conversation_id, user=self.user)

    @database_sync_to_async
    def _mark_read(self):
        Message.objects.filter(
            conversation_id=self.conversation_id, is_read=False
        ).exclude(sender=self.user).update(is_read=True, read_at=timezone.now())


class NotificationConsumer(AsyncWebsocketConsumer):
    """Personal notification stream per user."""

    async def connect(self):
        self.user = self.scope.get('user')
        if not self.user or self.user.is_anonymous:
            await self.close()
            return
        self.group_name = f"notif_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notify(self, event):
        await self.send(text_data=json.dumps(event['payload']))


class SignalingConsumer(AsyncWebsocketConsumer):
    """WebRTC signaling for a call room. Group: call_<room>."""

    async def connect(self):
        self.user = self.scope.get('user')
        if not self.user or self.user.is_anonymous:
            await self.close()
            return
        self.room = self.scope['url_route']['kwargs']['room']
        self.group_name = f"call_{self.room}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.channel_layer.group_send(self.group_name, {
            'type': 'signal.peer_joined',
            'peer_id': self.channel_name,
            'username': self.user.username,
        })

    async def disconnect(self, code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_send(self.group_name, {
                'type': 'signal.peer_left',
                'peer_id': self.channel_name,
                'username': self.user.username,
            })
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or '{}')
        except json.JSONDecodeError:
            return
        data['peer_id'] = self.channel_name
        data['username'] = self.user.username
        await self.channel_layer.group_send(self.group_name, {
            'type': 'signal.relay',
            'payload': data,
            'sender': self.channel_name,
        })

    async def signal_relay(self, event):
        if event['sender'] == self.channel_name:
            return
        await self.send(text_data=json.dumps(event['payload']))

    async def signal_peer_joined(self, event):
        if event['peer_id'] == self.channel_name:
            return
        await self.send(text_data=json.dumps({
            'type': 'peer-joined',
            'peer_id': event['peer_id'],
            'username': event['username'],
        }))

    async def signal_peer_left(self, event):
        if event['peer_id'] == self.channel_name:
            return
        await self.send(text_data=json.dumps({
            'type': 'peer-left',
            'peer_id': event['peer_id'],
            'username': event['username'],
        }))