"""
Tests del canal `stock` por WebSocket: el Showroom se entera al instante de
lo que reserva otra tablet, cobra caja o ajusta depósito.
"""
from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.test import SimpleTestCase, TestCase

from apps.inventario.consumers import ROOM_STOCK, StockConsumer
from apps.inventario.models import MovimientoStock, Stock
from apps.productos.tests.factories import (crear_producto, crear_usuario,
                                            crear_variante)
from apps.usuarios.models import Usuario
from apps.ventas.models import ItemPedido, NotaPedido, StockInsuficienteError


class AvisoDeMovimientoTests(TestCase):
    # El alta de catálogo escribe en el registro de cambios del sync.
    databases = {'default', 'sync'}

    def setUp(self):
        self.usuario = crear_usuario('vendedor_vivo', rol=Usuario.ROL_VENDEDOR)
        self.producto = crear_producto(nombre='Piso En Vivo')
        self.variante = crear_variante(producto=self.producto, color='Arena')
        self.stock = Stock.objects.get(variante=self.variante)
        self.stock.registrar_movimiento(
            tipo=MovimientoStock.TIPO_ENTRADA, cantidad=Decimal('10'),
            usuario=self.usuario)

        self.layer = get_channel_layer()
        self.canal = async_to_sync(self.layer.new_channel)()
        async_to_sync(self.layer.group_add)(ROOM_STOCK, self.canal)

    def tearDown(self):
        async_to_sync(self.layer.group_discard)(ROOM_STOCK, self.canal)
        async_to_sync(self.layer.flush)()

    def _recibido(self):
        return async_to_sync(self.layer.receive)(self.canal)

    def _hay_mensaje(self):
        # InMemoryChannelLayer guarda la cola por canal; sin mensajes no hay clave.
        return bool(self.layer.channels.get(self.canal))

    def test_un_movimiento_avisa_con_lo_que_queda(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.stock.registrar_movimiento(
                tipo=MovimientoStock.TIPO_RESERVA, cantidad=Decimal('4'),
                usuario=self.usuario)

        mensaje = self._recibido()
        self.assertEqual(mensaje['type'], 'stock_actualizado')
        self.assertEqual(mensaje['data'], {
            'tipo':        'stock_actualizado',
            'variante_id': self.variante.id,
            'producto_id': self.producto.id,
            'disponible':  6.0,
            'estado':      self.stock.estado,
        })

    def test_no_avisa_antes_del_commit(self):
        with self.captureOnCommitCallbacks(execute=False) as pendientes:
            self.stock.registrar_movimiento(
                tipo=MovimientoStock.TIPO_ENTRADA, cantidad=Decimal('1'),
                usuario=self.usuario)
            self.assertFalse(self._hay_mensaje())
        self.assertEqual(len(pendientes), 1)

    def test_un_pedido_revertido_no_avisa(self):
        pedido = NotaPedido.objects.create(vendedor=self.usuario, cliente_nombre='Ana')
        ItemPedido.objects.create(pedido=pedido, variante=self.variante,
                                  cantidad=Decimal('999'), precio_unitario=Decimal('1'))

        with self.captureOnCommitCallbacks(execute=True) as ejecutados:
            with self.assertRaises(StockInsuficienteError):
                with transaction.atomic():
                    pedido.reservar_stock(usuario=self.usuario)

        self.assertEqual(ejecutados, [])
        self.assertFalse(self._hay_mensaje())


class StockConsumerTests(SimpleTestCase):

    async def test_rechaza_sin_autenticar(self):
        comunicador = WebsocketCommunicator(StockConsumer.as_asgi(), '/ws/stock/')
        comunicador.scope['user'] = AnonymousUser()
        conectado, codigo = await comunicador.connect()
        self.assertFalse(conectado)
        self.assertEqual(codigo, 4401)

    async def test_cualquier_rol_recibe_el_aviso(self):
        # El Showroom lo usan vendedor, encargada y admin: no se filtra por rol.
        usuario = Usuario(username='encargada_vivo', rol=Usuario.ROL_ENCARGADA_VENTAS)
        comunicador = WebsocketCommunicator(StockConsumer.as_asgi(), '/ws/stock/')
        comunicador.scope['user'] = usuario
        conectado, _ = await comunicador.connect()
        self.assertTrue(conectado)

        datos = {'tipo': 'stock_actualizado', 'variante_id': 1,
                 'producto_id': 1, 'disponible': 5.0, 'estado': 'disponible'}
        await get_channel_layer().group_send(
            ROOM_STOCK, {'type': 'stock_actualizado', 'data': datos})
        self.assertEqual(await comunicador.receive_json_from(), datos)
        await comunicador.disconnect()
