"""
consumers.py — WebSocket del stock

Room `stock`: avisa a cualquier pantalla que muestre disponibles que una
variante cambió. Es un canal aparte de `rol_<rol>` a propósito: el stock lo
mira todo el mundo (el Showroom lo usan vendedor, encargada y admin), y
RolConsumer solo deja entrar al propio rol. El mensaje no lleva montos ni
datos del cliente — solo qué variante cambió y cuánto queda —, así que no
hace falta filtrarlo por rol como a los pedidos.
"""
import json

from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

ROOM_STOCK = 'stock'


class StockConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        usuario = self.scope.get('user')
        if not usuario or isinstance(usuario, AnonymousUser):
            await self.close(code=4401)
            return
        await self.channel_layer.group_add(ROOM_STOCK, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(ROOM_STOCK, self.channel_name)

    async def receive(self, text_data):
        pass

    async def stock_actualizado(self, event):
        await self.send(text_data=json.dumps(event['data']))
