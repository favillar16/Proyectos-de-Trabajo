"""
consumers.py — WebSocket para Notas de Pedido
"""
import json
from decimal import Decimal
from channels.generic.websocket import AsyncWebsocketConsumer


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder que convierte Decimal a float."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _dumps(data):
    return json.dumps(data, cls=DecimalEncoder)


class PedidoConsumer(AsyncWebsocketConsumer):
    """
    Canal de un pedido específico — room: pedido_<id>
    """

    async def connect(self):
        self.pedido_id = self.scope['url_route']['kwargs']['pedido_id']
        self.room = f'pedido_{self.pedido_id}'
        await self.channel_layer.group_add(self.room, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.room, self.channel_name)

    async def receive(self, text_data):
        pass

    async def pedido_actualizado(self, event):
        await self.send(text_data=_dumps(event['data']))

    # Alias — por si algún emit llega con este type
    async def pedido_estado_cambio(self, event):
        await self.send(text_data=_dumps(event['data']))


class RolConsumer(AsyncWebsocketConsumer):
    """
    Canal por rol — room: rol_<rol>
    """

    async def connect(self):
        self.rol = self.scope['url_route']['kwargs']['rol']
        self.room = f'rol_{self.rol}'
        await self.channel_layer.group_add(self.room, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.room, self.channel_name)

    async def receive(self, text_data):
        pass

    async def nuevo_pedido(self, event):
        await self.send(text_data=_dumps(event['data']))

    async def pedido_estado_cambio(self, event):
        await self.send(text_data=_dumps(event['data']))

    # Alias — acepta también mensajes tipo pedido_actualizado
    async def pedido_actualizado(self, event):
        await self.send(text_data=_dumps(event['data']))
