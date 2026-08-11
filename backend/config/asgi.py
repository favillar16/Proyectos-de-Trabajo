"""
ASGI config — soporte HTTP + WebSocket
"""
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django_asgi_app = get_asgi_application()

from apps.usuarios.ws_auth import JWTAuthMiddleware
from apps.ventas.routing import websocket_urlpatterns as ventas_ws
from apps.caja.routing import websocket_urlpatterns as caja_ws

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    # JWT (no sesión/cookie) — el mismo token que usa la API REST.
    'websocket': JWTAuthMiddleware(
        URLRouter(
            ventas_ws + caja_ws
        )
    ),
})
