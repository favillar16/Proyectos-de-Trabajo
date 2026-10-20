"""
Resumen de clientes (apps/caja/clientes.py) y medios de pago QR.

Lo que tiene que quedar bien del resumen:
  · cuenta lo cobrado, no lo presupuestado: un pedido sin cobrar no suma;
  · el mismo cliente con el CI tipeado de dos formas es uno solo, y si está
    en el padrón se junta con su ficha;
  · una devolución con reintegro resta, y un cambio no cuenta como compra
    ni duplica lo invertido;
  · solo el admin lo ve.
"""
from decimal import Decimal

from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.caja import clientes, pos
from apps.caja.models import Pago
from apps.caja.tests.test_devoluciones import BaseDevolucionTests
from apps.facturacion import codigos
from apps.facturacion.tests.factories import SIFEN_APAGADO, crear_pedido, crear_usuario
from apps.ventas.models import Cliente


@override_settings(**SIFEN_APAGADO)
class ResumenClientesTests(BaseDevolucionTests):

    def setUp(self):
        super().setUp()
        self.hoy = timezone.localdate()

    def _vender_a(self, nombre, ruc='', monto='150000', cliente=None):
        pago = self._vender([(self.porcelanato, '1', monto)])
        pedido = pago.pedido
        pedido.cliente_nombre = nombre
        pedido.cliente_ruc = ruc
        pedido.cliente = cliente
        pedido.save()
        return pago

    def _resumen(self, buscar=''):
        return clientes.resumen_clientes(self.hoy, self.hoy, buscar)

    def test_suma_lo_cobrado_y_ordena_de_mayor_a_menor(self):
        self._vender_a('Ana Benítez', monto='150000')
        self._vender_a('Carlos Duarte', monto='450000')
        self._vender_a('Ana Benítez', monto='150000')

        filas = self._resumen()['clientes']
        self.assertEqual([r['nombre'] for r in filas], ['Carlos Duarte', 'Ana Benítez'])
        self.assertEqual(filas[1]['total'], 300000)
        self.assertEqual(filas[1]['compras'], 2)
        self.assertEqual(filas[1]['ticket_promedio'], 150000)

    def test_un_pedido_sin_cobrar_no_suma(self):
        crear_pedido(self.cajero, [(self.porcelanato, '1', '150000')])
        self.assertEqual(self._resumen()['clientes'], [])

    def test_el_mismo_documento_tipeado_distinto_es_un_cliente(self):
        self._vender_a('Ana Benítez', ruc='4.567.890')
        self._vender_a('ANA BENITEZ', ruc='4567890-1')
        filas = self._resumen()['clientes']
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['total'], 300000)

    def test_el_documento_se_junta_con_la_ficha_del_padron(self):
        ficha = Cliente.objects.create(razon_social='Constructora Sur S.A.', ruc='80012345-6')
        self._vender_a('Constructora Sur', cliente=ficha)
        self._vender_a('Const. Sur', ruc='80012345')
        filas = self._resumen()['clientes']
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['nombre'], 'Constructora Sur S.A.')
        self.assertTrue(filas[0]['en_padron'])
        self.assertEqual(filas[0]['total'], 300000)

    def test_la_venta_sin_nombre_ni_documento_va_aparte(self):
        self._vender_a('', monto='90000')
        r = self._resumen()
        self.assertEqual(r['clientes'], [])
        self.assertEqual(r['totales']['sin_identificar'], 90000)

    def test_el_reintegro_de_una_devolucion_resta(self):
        pago = self._vender_a('Ana Benítez', monto='150000')
        self._devolver(pago, [(self.porcelanato, Decimal('1'), True)], medio_pago='efectivo')
        fila = self._resumen()['clientes'][0]
        self.assertEqual(fila['total'], 0)
        self.assertEqual(fila['reintegrado'], 150000)

    def test_un_cambio_no_cuenta_como_compra_ni_duplica(self):
        pago = self._vender_a('Ana Benítez', monto='150000')
        # Devuelve el porcelanato (150.000) y se lleva cerámica (90.000):
        # le reintegran 60.000.
        self._devolver(pago, [(self.porcelanato, Decimal('1'), True)],
                       motivo='cambio', medio_pago='efectivo',
                       items_cambio=[{'variante_id': self.ceramica.id, 'cantidad': '1'}])
        fila = self._resumen()['clientes'][0]
        self.assertEqual(fila['compras'], 1)
        self.assertEqual(fila['total'], 90000)

    def test_buscar_por_documento_o_nombre(self):
        self._vender_a('Ana Benítez', ruc='4567890')
        self._vender_a('Carlos Duarte')
        self.assertEqual([r['nombre'] for r in self._resumen('4.567.890')['clientes']],
                         ['Ana Benítez'])
        self.assertEqual([r['nombre'] for r in self._resumen('carlos')['clientes']],
                         ['Carlos Duarte'])

    def test_solo_el_admin_lo_ve(self):
        api = APIClient()
        api.force_authenticate(self.cajero)
        self.assertEqual(api.get('/api/v1/caja/clientes/').status_code, 403)

        api.force_authenticate(crear_usuario('duenia', rol='admin'))
        self._vender_a('Ana Benítez')
        resp = api.get('/api/v1/caja/clientes/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['clientes'][0]['nombre'], 'Ana Benítez')
        self.assertEqual(api.get('/api/v1/caja/clientes/', {'formato': 'xlsx'}).status_code, 200)


class MediosQRTests(SimpleTestCase):

    def test_el_qr_es_tarjeta_para_el_sifen(self):
        self.assertEqual(codigos.codigo_medio_pago(Pago.MEDIO_QR_DEBITO),
                         codigos.PAGO_TARJETA_DEBITO)
        self.assertEqual(codigos.codigo_medio_pago(Pago.MEDIO_QR_CREDITO),
                         codigos.PAGO_TARJETA_CREDITO)
        self.assertTrue(pos.requiere_datos_de_tarjeta(Pago.MEDIO_QR_DEBITO))

    def test_el_qr_no_se_declara_como_pos(self):
        resultado = pos.TerminalManual().cobrar(
            Decimal('100000'), medio=Pago.MEDIO_QR_CREDITO,
            datos={'denominacion': codigos.TARJETA_VISA})
        self.assertEqual(resultado.forma_procesamiento, codigos.PROCESAMIENTO_OTRO)
        resultado = pos.TerminalManual().cobrar(
            Decimal('100000'), medio=Pago.MEDIO_TARJETA_CREDITO,
            datos={'denominacion': codigos.TARJETA_VISA})
        self.assertEqual(resultado.forma_procesamiento, codigos.PROCESAMIENTO_POS)
