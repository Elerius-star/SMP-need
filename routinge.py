"""WebSocket URL routing for social consumers."""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'^ws/chat/(?P<conversation_id>\d+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'^ws/notifications/$', consumers.NotificationConsumer.as_asgi()),
    re_path(r'^ws/call/(?P<room>[\w-]+)/$', consumers.SignalingConsumer.as_asgi()),
]