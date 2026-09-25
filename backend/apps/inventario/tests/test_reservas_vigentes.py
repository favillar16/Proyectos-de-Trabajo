"""
Tests de GET /inventario/reservas/: para quién está apartada la mercadería.

Todo pedido reserva su stock al crearse, pero eso no se veía: otro vendedor
encontraba menos disponible sin saber para quién estaba guardado.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.inventario.models import MovimientoStock, Stock
from apps.productos.tests.factories import (crear_producto, crear_usuario,
                                            crear_variante)
from apps.usuarios.models import Usuario
from apps.ventas.models import ItemPedido, NotaPedido


class ReservasVigentesTests(TestCase):
    # El alta de catálogo escribe en el registro de cambios del sync.
    databases = {'default', 'sync'}

    def setUp(self):
        self.vendedor = crear_usuario('vendedor_reservas', rol=Usuario.ROL_VENDEDOR)
        self.cliente_api = APIClient()
        self.cliente_api.force_authenticate(self.vendedor)
        self.producto = crear_producto(nombre='Piso 71220')
        self.arena = crear_variante(producto=self.producto, color='Arena')
        self.gris = crear_variante(producto=self.producto, color='Gris')
        for v in (self.arena, self.gris):
            Stock.objects.get(variante=v).registrar_movimiento(
                tipo=MovimientoStock.TIPO_ENTRADA, cantidad=Decimal('100'),
                usuario=self.vendedor)

    def _pedido(self, variante, cantidad, cliente, estado=None):
        pedido = NotaPedido.objects.create(vendedor=self.vendedor, cliente_nombre=cliente)
        ItemPedido.objects.create(pedido=pedido, variante=variante,
                                  cantidad=Decimal(cantidad), precio_unitario=Decimal('1000'))
        pedido.reservar_stock(usuario=self.vendedor)
        if estado:
            pedido.estado = estado
            pedido.save(update_fields=['estado'])
        return pedido

    def _reservas(self, **params):
        respuesta = self.cliente_api.get(reverse('stock-reservas'), params)
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.data['results']

    def test_muestra_para_quien_esta_reservado(self):
        pedido = self._pedido(self.arena, '12.5', 'Juan Pérez')
        reservas = self._reservas(producto_id=self.producto.id)
        self.assertEqual(len(reservas), 1)
        self.assertEqual(reservas[0]['cliente_nombre'], 'Juan Pérez')
        self.assertEqual(reservas[0]['pedido_numero'], pedido.numero)
        self.assertEqual(Decimal(reservas[0]['cantidad']), Decimal('12.5'))
        self.assertEqual(reservas[0]['vendedor_nombre'], self.vendedor.nombre_completo)

    def test_listo_para_cobrar_sigue_reservado(self):
        self._pedido(self.arena, '5', 'Ana', estado=NotaPedido.ESTADO_LISTO)
        self.assertEqual(len(self._reservas(producto_id=self.producto.id)), 1)

    def test_cobrados_y_cancelados_no_figuran(self):
        self._pedido(self.arena, '5', 'Ana', estado=NotaPedido.ESTADO_PAGADO)
        self._pedido(self.arena, '5', 'Luis', estado=NotaPedido.ESTADO_CANCELADO)
        self.assertEqual(self._reservas(producto_id=self.producto.id), [])

    def test_filtra_por_variante(self):
        self._pedido(self.arena, '5', 'Ana')
        self._pedido(self.gris, '7', 'Luis')
        reservas = self._reservas(variante_id=self.gris.id)
        self.assertEqual([r['cliente_nombre'] for r in reservas], ['Luis'])

    def test_sin_filtro_es_error(self):
        self.assertEqual(self.cliente_api.get(reverse('stock-reservas')).status_code, 400)
