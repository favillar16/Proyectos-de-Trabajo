"""
Tests del historial de movimientos de una variante, en Inventario.

La propietaria quiere entrar a un producto y ver qué se vendió, cuándo y a
quién —lo tenía anotado en papel— para controlar que el sistema descontó bien
y saber qué sale más. Por eso cada movimiento de un pedido trae el cliente y
el número, y ?tipo=salida deja solo las ventas con el total vendido.
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


class HistorialDeVentasTests(TestCase):
    # El alta de catálogo escribe en el registro de cambios del sync.
    databases = {'default', 'sync'}

    def setUp(self):
        self.admin = crear_usuario('admin_historial', rol=Usuario.ROL_ADMIN)
        self.cliente_api = APIClient()
        self.cliente_api.force_authenticate(self.admin)

        self.variante = crear_variante(producto=crear_producto(nombre='Piso 71220'))
        Stock.objects.get(variante=self.variante).registrar_movimiento(
            tipo=MovimientoStock.TIPO_ENTRADA, cantidad=Decimal('220'),
            usuario=self.admin, observaciones='reposición',
        )

    def _vender(self, cliente, cantidad):
        pedido = NotaPedido.objects.create(vendedor=self.admin, cliente_nombre=cliente)
        ItemPedido.objects.create(
            pedido=pedido, variante=self.variante,
            cantidad=Decimal(cantidad), precio_unitario=Decimal('150000'),
        )
        pedido.reservar_stock(usuario=self.admin)
        pedido.descontar_stock(usuario=self.admin, numero_ticket='T-1')
        return pedido

    def _historial(self, **params):
        respuesta = self.cliente_api.get(
            reverse('stock-movimientos'), {'variante_id': self.variante.id, **params})
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.data

    def test_la_venta_trae_el_cliente_y_el_pedido(self):
        pedido = self._vender('María Benítez', '141')
        venta = next(m for m in self._historial()['results'] if m['tipo'] == 'salida')
        self.assertEqual(venta['cliente_nombre'], 'María Benítez')
        self.assertEqual(venta['pedido_numero'], pedido.numero)

    def test_un_ajuste_no_trae_cliente(self):
        entrada = self._historial()['results'][-1]
        self.assertEqual(entrada['cliente_nombre'], '')
        self.assertIsNone(entrada['pedido_numero'])

    def test_solo_ventas_con_el_total_vendido(self):
        self._vender('Ana', '10.5')
        self._vender('Luis', '20')
        datos = self._historial(tipo='salida')
        self.assertEqual({m['tipo'] for m in datos['results']}, {'salida'})
        self.assertEqual([m['cliente_nombre'] for m in datos['results']], ['Luis', 'Ana'])
        self.assertEqual(Decimal(datos['total']), Decimal('30.5'))
