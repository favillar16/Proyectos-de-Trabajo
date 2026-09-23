"""
Dónde corre la impresión respecto de la transacción del cobro.

`RegistrarPagoView` toma el pedido con `select_for_update()`: mientras la
transacción esté abierta, ese pedido queda bloqueado y la conexión ocupada.
La impresión se hacía adentro, y `win32print` no tiene timeout — una
impresora colgada (apagada no: eso devuelve error enseguida; colgada, con el
spooler sin contestar) mantenía la transacción viva sin límite, y con varias
tablets cobrando a la vez un cobro trabado podía frenar a los demás.

El test usa `TransactionTestCase` y no `TestCase` a propósito: `TestCase`
envuelve cada prueba en su propia transacción, así que `in_atomic_block`
daría True siempre y la prueba pasaría sin probar nada.
"""
from decimal import Decimal
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.caja.models import Pago
from apps.facturacion.tests.factories import (crear_pedido, crear_sesion,
                                              crear_usuario, crear_variante)
from apps.inventario.models import MovimientoStock, Stock
from apps.ventas.models import NotaPedido


class ImpresionFueraDeLaTransaccionTests(TransactionTestCase):
    databases = {'default', 'sync'}

    def setUp(self):
        self.cajero = crear_usuario('cajera_tx', rol='cajero')
        self.sesion = crear_sesion(self.cajero)
        variante = crear_variante(nombre='Piso TX')
        stock = Stock.objects.get(variante=variante)
        stock.registrar_movimiento(
            MovimientoStock.TIPO_ENTRADA, Decimal('50'), self.cajero,
            observaciones='carga inicial')

        self.pedido = crear_pedido(self.cajero, [(variante, 2, 50000)])
        self.pedido.reservar_stock(usuario=self.cajero)
        self.pedido.estado = NotaPedido.ESTADO_LISTO
        self.pedido.save(update_fields=['estado'])

        self.api = APIClient()
        self.api.force_authenticate(self.cajero)

    def _cobrar(self, **extra):
        cuerpo = {
            'pedido_id': self.pedido.pk,
            'medio_pago': 'efectivo',
            'monto_recibido': 200000,
        }
        cuerpo.update(extra)
        return self.api.post(reverse('registrar-pago'), cuerpo, format='json')

    def test_el_ticket_se_imprime_con_la_transaccion_ya_cerrada(self):
        visto = {}

        def espia(datos):
            visto['en_transaccion'] = connection.in_atomic_block
            return {'ok': True, 'modo': 'espia'}

        with patch('apps.caja.views.imprimir_ticket', side_effect=espia):
            respuesta = self._cobrar()

        self.assertEqual(respuesta.status_code, 201)
        self.assertIn('en_transaccion', visto, 'no se llamó a la impresora')
        self.assertFalse(
            visto['en_transaccion'],
            'La impresión corrió dentro de la transacción: el pedido queda '
            'bloqueado por select_for_update() mientras el spooler no conteste.')

    def test_la_factura_tambien_se_imprime_afuera(self):
        visto = {}

        def espia(datos):
            visto['en_transaccion'] = connection.in_atomic_block
            return {'ok': True, 'modo': 'espia'}

        with patch('apps.caja.views.imprimir_factura', side_effect=espia):
            respuesta = self._cobrar(
                tipo_comprobante='factura',
                cliente_ruc='80099887-6',
                cliente_razon_social='Constructora Sur SRL')

        self.assertEqual(respuesta.status_code, 201)
        self.assertFalse(visto.get('en_transaccion', True))

    def test_si_la_impresora_falla_el_cobro_igual_queda_hecho(self):
        # Es la contracara de sacar la impresión de la transacción: el papel
        # no puede revertir una venta que ya ocurrió. Se reimprime después
        # desde "Cobros del turno".
        with patch('apps.caja.views.imprimir_ticket',
                   return_value={'ok': False, 'error': 'impresora colgada'}):
            respuesta = self._cobrar()

        self.assertEqual(respuesta.status_code, 201)
        self.assertFalse(respuesta.data['impresion']['ok'])

        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, NotaPedido.ESTADO_PAGADO)
        self.assertTrue(
            Pago.objects.filter(pedido=self.pedido,
                                estado=Pago.ESTADO_CONFIRMADO).exists())

    def test_el_stock_se_descuenta_dentro_de_la_transaccion(self):
        # Lo que NO hay que sacar afuera. Si el descuento de stock quedara
        # fuera del bloque, una caída entre el cobro y el descuento dejaría
        # mercadería vendida y todavía en existencias.
        antes = Stock.objects.get(variante=self.pedido.items.first().variante)
        disponible_antes = antes.cantidad

        with patch('apps.caja.views.imprimir_ticket',
                   return_value={'ok': True, 'modo': 'espia'}):
            self._cobrar()

        despues = Stock.objects.get(variante=self.pedido.items.first().variante)
        self.assertEqual(despues.cantidad, disponible_antes - Decimal('2'))
