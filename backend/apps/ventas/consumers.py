"""
consumers.py — WebSocket para Notas de Pedido
"""
import json
from decimal import Decimal
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder que convierte Decimal a float."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _dumps(data):
    return json.dumps(data, cls=DecimalEncoder)


def _usuario_autenticado(scope):
    usuario = scope.get('user')
    return bool(usuario and not isinstance(usuario, AnonymousUser))


def _ocultar_montos(data):
    """
    Depósito prepara pedidos pero no ve montos (regla documentada en
    funcionalidades_sistema.md). El REST ya lo respeta a nivel de
    serializer; acá se replica para que un push por WebSocket no pise el
    dato oculto en la cache del frontend con el monto real.
    """
    data = dict(data)
    pedido = data.get('pedido')
    if isinstance(pedido, dict):
        pedido = dict(pedido)
        for campo in ('subtotal', 'descuento', 'total', 'total_ajustado', 'monto_a_cobrar'):
            if campo in pedido:
                pedido[campo] = None
        items = pedido.get('items')
        if isinstance(items, list):
            pedido['items'] = [
                {**item, **{c: None for c in ('precio_unitario', 'descuento_item', 'subtotal') if c in item}}
                for item in items
            ]
        data['pedido'] = pedido
    return data


class PedidoConsumer(AsyncWebsocketConsumer):
    """
    Canal de un pedido específico — room: pedido_<id>
    """

    async def connect(self):
        if not _usuario_autenticado(self.scope):
            await self.close(code=4401)
            return
        self.pedido_id = self.scope['url_route']['kwargs']['pedido_id']
        self.room = f'pedido_{self.pedido_id}'
        await self.channel_layer.group_add(self.room, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, 'room'):
            await self.channel_layer.group_discard(self.room, self.channel_name)

    async def receive(self, text_data):
        pass

    def _preparar(self, data):
        usuario = self.scope.get('user')
        if usuario and getattr(usuario, 'rol', None) == 'deposito':
            return _ocultar_montos(data)
        return data

    async def pedido_actualizado(self, event):
        await self.send(text_data=_dumps(self._preparar(event['data'])))

    # Alias — por si algún emit llega con este type
    async def pedido_estado_cambio(self, event):
        await self.send(text_data=_dumps(self._preparar(event['data'])))


class RolConsumer(AsyncWebsocketConsumer):
    """
    Canal por rol — room: rol_<rol>
    """

    async def connect(self):
        if not _usuario_autenticado(self.scope):
            await self.close(code=4401)
            return

        self.rol = self.scope['url_route']['kwargs']['rol']
        usuario_rol = getattr(self.scope['user'], 'rol', None)
        # Solo el propio rol (o admin, que ve todo) puede suscribirse a un
        # canal por rol — evita que cualquier usuario autenticado escuche
        # las alertas/pedidos de un rol ajeno (ej. rol_admin, rol_cajero).
        if usuario_rol != self.rol and usuario_rol != 'admin':
            await self.close(code=4403)
            return

        self.room = f'rol_{self.rol}'
        await self.channel_layer.group_add(self.room, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, 'room'):
            await self.channel_layer.group_discard(self.room, self.channel_name)

    async def receive(self, text_data):
        pass

    def _preparar(self, data):
        usuario = self.scope.get('user')
        if usuario and getattr(usuario, 'rol', None) == 'deposito':
            return _ocultar_montos(data)
        return data

    async def nuevo_pedido(self, event):
        await self.send(text_data=_dumps(self._preparar(event['data'])))

    async def pedido_estado_cambio(self, event):
        await self.send(text_data=_dumps(self._preparar(event['data'])))

    # Alias — acepta también mensajes tipo pedido_actualizado
    async def pedido_actualizado(self, event):
        await self.send(text_data=_dumps(self._preparar(event['data'])))
