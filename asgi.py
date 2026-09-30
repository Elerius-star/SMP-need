"""
ASGI config with Channels + JWT authentication over WebSocket.
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smpneed.settings')
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from social.routing import websocket_urlpatterns


class JWTAuthMiddleware:
    """Authenticate WebSocket connections using a ?token= query param."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        token = self._get_token(scope)
        scope['user'] = await self._get_user(token)
        return await self.inner(scope, receive, send)

    def _get_token(self, scope):
        qs = scope.get('query_string', b'').decode()
        for pair in qs.split('&'):
            if pair.startswith('token='):
                return pair[6:]
        return None

    @database_sync_to_async
    def _get_user(self, token):
        if not token:
            return AnonymousUser()
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            from django.contrib.auth import get_user_model
            access = AccessToken(token)
            return get_user_model().objects.get(id=access['user_id'])
        except Exception:
            return AnonymousUser()


application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': JWTAuthMiddleware(
        AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
    ),
})