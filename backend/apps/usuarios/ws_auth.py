"""
Middleware de Channels para autenticar conexiones WebSocket con el mismo
JWT que usa la API REST (djangorestframework-simplejwt).

AuthMiddlewareStack de Channels espera sesión/cookie de Django, pero este
frontend guarda el JWT en localStorage (ver services/api.js) y nunca manda
cookie de sesión — con AuthMiddlewareStack, scope['user'] llegaba siempre
anónimo y cualquier dispositivo en la red podía conectarse a cualquier room
(rol_admin, pedido_<id> ajeno, etc.) sin acreditar quién es.

El frontend manda el access token como query param al abrir el socket:
ws://host/ws/pedidos/rol/admin/?token=<access_token>
"""
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _usuario_desde_token(token):
    from django.contrib.auth import get_user_model
    from rest_framework_simplejwt.tokens import AccessToken

    if not token:
        return AnonymousUser()
    try:
        validado = AccessToken(token)
        Usuario = get_user_model()
        usuario = Usuario.objects.get(pk=validado['user_id'])
    except Exception:
        return AnonymousUser()
    return usuario if usuario.activo else AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """Autentica la conexión WS leyendo ?token=<access_token> de la URL."""

    async def __call__(self, scope, receive, send):
        query_string = scope.get('query_string', b'').decode()
        token = parse_qs(query_string).get('token', [None])[0]
        scope['user'] = await _usuario_desde_token(token)
        return await super().__call__(scope, receive, send)
