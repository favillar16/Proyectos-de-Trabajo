"""
Tests del resumen de ventas de la ficha de producto
(GET /api/v1/productos/<id>/ventas/).

Es la trazabilidad que usa la propietaria para decidir cuánto volver a
comprar, así que verifican que el número sea el que salió del local: solo
cobros confirmados, devoluciones restando, y nada de precios ni clientes.
"""
from decimal import Decimal

from rest_framework.test import APIClient

from apps.caja.models import Pago
from apps.caja.tests.test_devoluciones import BaseDevolucionTests
from apps.facturacion.tests.factories import crear_pedido, crear_usuario
from apps.productos.models import Variante


class VentasProductoTests(BaseDevolucionTests):

    def setUp(self):
        super().setUp()
        self.admin = crear_usuario('admin_ventas', rol='admin')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.producto = self.porcelanato.producto
        # Segunda variante del mismo producto, para el desglose.
        self.gris = Variante.objects.create(producto=self.producto, color='Gris')

    def _ventas(self, usuario=None):
        if usuario:
            self.client.force_authenticate(usuario)
        return self.client.get(f'/api/v1/productos/{self.producto.id}/ventas/')

    def test_suma_las_ventas_cobradas_por_variante(self):
        self._vender([(self.porcelanato, '12.60', '150000')])
        self._vender([(self.porcelanato, '2.52', '150000'),
                      (self.ceramica, '3', '90000')])  # otro producto: no cuenta

        data = self._ventas().json()
        self.assertEqual(data['unidad'], 'm²')
        self.assertEqual(data['ventas'], 2)
        self.assertAlmostEqual(data['total'], 15.12)
        self.assertEqual(len(data['movimientos']), 2)
        self.assertEqual(len(data['variantes']), 1)

    def test_solo_cantidades_sin_precio_ni_cliente(self):
        self._vender([(self.porcelanato, '1', '150000')])
        mov = self._ventas().json()['movimientos'][0]
        self.assertEqual(set(mov), {'fecha', 'tipo', 'variante_id', 'variante', 'cantidad'})

    def test_un_cobro_no_confirmado_no_cuenta(self):
        pedido = crear_pedido(self.cajero, [(self.porcelanato, '5', '150000')])
        Pago.objects.create(
            pedido=pedido, sesion_caja=self.sesion, cajero=self.cajero,
            medio_pago='efectivo', monto=Decimal('750000'),
            estado=Pago.ESTADO_PENDIENTE,
        )
        data = self._ventas().json()
        self.assertEqual(data['ventas'], 0)
        self.assertEqual(data['movimientos'], [])

    def test_la_devolucion_resta(self):
        pago = self._vender([(self.porcelanato, '4', '150000')])
        self._devolver(pago, [(self.porcelanato, '1', True)], medio_pago='efectivo')

        data = self._ventas().json()
        self.assertAlmostEqual(data['total'], 3)
        self.assertEqual(data['ventas'], 1)
        self.assertEqual(data['movimientos'][0]['tipo'], 'devolucion')
        self.assertEqual(data['movimientos'][0]['cantidad'], -1)

    def test_cajero_y_deposito_no_lo_ven(self):
        self.assertEqual(self._ventas(self.cajero).status_code, 403)
        deposito = crear_usuario('deposito_ventas', rol='deposito')
        self.assertEqual(self._ventas(deposito).status_code, 403)

    def test_vendedor_lo_ve(self):
        vendedor = crear_usuario('vendedor_ventas', rol='vendedor')
        self.assertEqual(self._ventas(vendedor).status_code, 200)
