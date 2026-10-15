"""
Pago mixto y cobro con varios cheques.

La propietaria cobra ventas grandes con dos o tres cheques, o con cheque y
el resto en efectivo, y la caja admitía un solo medio por cobro. Un cobro
sigue siendo un `Pago` (un ticket, una factura) con líneas `PagoMedio`; lo
que tiene que quedar bien es:

  · que las líneas sumen el total, sin margen;
  · que cada cheque guarde sus datos en su línea;
  · que el cierre y el arqueo cuenten en el cajón solo la parte en efectivo;
  · que la factura declare una entrega por línea, cada cheque con lo suyo.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.caja import reportes
from apps.caja.models import DatosCheque, Pago, PagoMedio
from apps.facturacion import codigos, payload
from apps.facturacion.emisor import crear_documento
from apps.facturacion.tests.factories import (
    RUC_RECEPTOR, SIFEN_APAGADO, crear_pago, crear_pedido, crear_sesion,
    crear_usuario, crear_variante)


TOTAL = Decimal('1000000')


def _cheque(numero, banco='Banco Continental'):
    return {'numero': numero, 'banco': banco}


@override_settings(SIFEN=SIFEN_APAGADO)
class CobroMixtoEnCajaTests(TestCase):
    databases = {'default', 'sync'}

    def setUp(self):
        self.cajero = crear_usuario(username='cajero_mixto')
        self.variante = crear_variante(nombre='Producto mixto', precio=TOTAL)
        self.variante.stock.cantidad = Decimal('10')
        self.variante.stock.save(update_fields=['cantidad'])
        self.pedido = crear_pedido(self.cajero, [(self.variante, 1, TOTAL)])
        self.pedido.recalcular_totales()
        self.sesion = crear_sesion(self.cajero)
        self.client = APIClient()
        self.client.force_authenticate(self.cajero)

    def _cobrar(self, medios, **extra):
        cuerpo = {'pedido_id': self.pedido.id, 'medios': medios}
        cuerpo.update(extra)
        return self.client.post('/api/v1/caja/pagos/', cuerpo, format='json')

    def _sin_cobro(self):
        self.assertFalse(Pago.objects.filter(pedido=self.pedido).exists())

    # ── Lo que entra ─────────────────────────────────────────────────────

    def test_dos_cheques_que_suman_el_total(self):
        resp = self._cobrar([
            {'medio': 'cheque', 'monto': 600000, 'datos_cheque': _cheque('111')},
            {'medio': 'cheque', 'monto': 400000, 'datos_cheque': _cheque('222', 'Banco Itaú')},
        ])
        self.assertEqual(resp.status_code, 201, resp.data)

        pago = Pago.objects.get(pedido=self.pedido)
        # Varios cheques siguen siendo un cobro "con cheque", no mixto
        self.assertEqual(pago.medio_pago, Pago.MEDIO_CHEQUE)
        self.assertEqual(pago.medios.count(), 2)
        self.assertEqual(
            sorted((l.monto, l.datos_cheque.numero) for l in pago.medios.all()),
            [(Decimal('400000'), '00000222'), (Decimal('600000'), '00000111')])
        self.assertEqual(len(resp.data['ticket']['medios']), 2)

    def test_cheque_y_efectivo_con_vuelto(self):
        resp = self._cobrar([
            {'medio': 'cheque', 'monto': 700000, 'datos_cheque': _cheque('333')},
            {'medio': 'efectivo', 'monto': 300000, 'monto_recibido': 350000},
        ])
        self.assertEqual(resp.status_code, 201, resp.data)

        pago = Pago.objects.get(pedido=self.pedido)
        self.assertEqual(pago.medio_pago, Pago.MEDIO_MIXTO)
        self.assertEqual(pago.monto, TOTAL)
        self.assertEqual(pago.monto_recibido, Decimal('350000'))
        self.assertEqual(pago.vuelto, Decimal('50000'))
        efectivo = pago.medios.get(medio='efectivo')
        self.assertEqual(efectivo.vuelto, Decimal('50000'))

    def test_el_cobro_de_un_solo_medio_sigue_igual(self):
        resp = self.client.post('/api/v1/caja/pagos/', {
            'pedido_id': self.pedido.id, 'medio_pago': 'efectivo',
            'monto_recibido': 1200000}, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        pago = Pago.objects.get(pedido=self.pedido)
        linea = pago.medios.get()
        self.assertEqual((linea.medio, linea.monto, linea.vuelto),
                         ('efectivo', TOTAL, Decimal('200000')))
        self.assertEqual(resp.data['ticket']['medios'], [])

    # ── Lo que se frena con el cliente presente ──────────────────────────

    def test_si_no_suman_el_total_no_se_cobra(self):
        resp = self._cobrar([
            {'medio': 'cheque', 'monto': 600000, 'datos_cheque': _cheque('111')},
            {'medio': 'transferencia', 'monto': 300000},
        ])
        self.assertEqual(resp.status_code, 400)
        self.assertIn('faltan', resp.data['error'])
        self._sin_cobro()

    def test_el_efectivo_va_en_una_sola_linea(self):
        resp = self._cobrar([
            {'medio': 'efectivo', 'monto': 500000, 'monto_recibido': 500000},
            {'medio': 'efectivo', 'monto': 500000, 'monto_recibido': 500000},
        ])
        self.assertEqual(resp.status_code, 400)
        self._sin_cobro()

    def test_cada_cheque_exige_sus_datos(self):
        resp = self._cobrar([
            {'medio': 'cheque', 'monto': 600000, 'datos_cheque': _cheque('111')},
            {'medio': 'cheque', 'monto': 400000},
        ])
        self.assertEqual(resp.status_code, 400)
        self.assertIn('cheque', resp.data['error'].lower())
        self._sin_cobro()

    def test_dos_cheques_con_el_mismo_numero(self):
        resp = self._cobrar([
            {'medio': 'cheque', 'monto': 600000, 'datos_cheque': _cheque('111')},
            {'medio': 'cheque', 'monto': 400000, 'datos_cheque': _cheque('0111')},
        ])
        self.assertEqual(resp.status_code, 400)
        self._sin_cobro()

    def test_efectivo_recibido_menor_a_su_parte(self):
        resp = self._cobrar([
            {'medio': 'cheque', 'monto': 700000, 'datos_cheque': _cheque('333')},
            {'medio': 'efectivo', 'monto': 300000, 'monto_recibido': 200000},
        ])
        self.assertEqual(resp.status_code, 400)
        self._sin_cobro()

    # ── Cierre y arqueo: solo el efectivo está en el cajón ───────────────

    def test_el_cierre_cuenta_solo_la_parte_en_efectivo(self):
        self._cobrar([
            {'medio': 'cheque', 'monto': 700000, 'datos_cheque': _cheque('333')},
            {'medio': 'efectivo', 'monto': 300000, 'monto_recibido': 300000},
        ])
        resp = self.client.post(
            f'/api/v1/caja/sesiones/{self.sesion.id}/cerrar/',
            {'monto_cierre': '300000'}, format='json')

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['resumen_medios'],
                         {'cheque': 700000.0, 'efectivo': 300000.0})
        self.assertEqual(resp.data['total_efectivo'], 300000)
        self.assertEqual(resp.data['diferencia'], 0)

    def test_el_arqueo_separa_los_medios_del_pago_mixto(self):
        self._cobrar([
            {'medio': 'cheque', 'monto': 700000, 'datos_cheque': _cheque('333')},
            {'medio': 'efectivo', 'monto': 300000, 'monto_recibido': 300000},
        ])
        filas = reportes.reporte_arqueo(timezone.localdate())['filas']
        textos = [f[0].strip() for f in filas]
        self.assertIn('Cobrado en efectivo', textos)
        self.assertIn('Cobrado en cheque', textos)
        esperado = next(f for f in filas
                        if f[0].strip() == 'Efectivo que debe haber en el cajón')
        self.assertEqual(esperado[2], reportes._gs(300000))


class LineaAutomaticaTests(TestCase):
    """Un `Pago` creado sin saber de líneas igual queda con la suya."""

    databases = {'default', 'sync'}

    def test_un_pago_de_un_medio_arma_su_linea(self):
        usuario = crear_usuario(username='cajero_linea')
        pedido = crear_pedido(usuario, [(crear_variante(nombre='P linea'), 1, 5000)])
        pago = crear_pago(pedido, crear_sesion(usuario), usuario, 5000, medio='debito')
        linea = pago.medios.get()
        self.assertEqual((linea.medio, linea.monto), ('debito', Decimal('5000')))

    def test_un_cheque_creado_a_la_antigua_se_engancha_a_la_linea(self):
        usuario = crear_usuario(username='cajero_linea2')
        pedido = crear_pedido(usuario, [(crear_variante(nombre='P linea2'), 1, 5000)])
        pago = crear_pago(pedido, crear_sesion(usuario), usuario, 5000, medio='cheque')
        cheque = DatosCheque.objects.create(pago=pago, numero='9', banco='Banco Basa')
        self.assertEqual(cheque.linea, pago.medios.get())


@override_settings(SIFEN=SIFEN_APAGADO)
class FacturaDelPagoMixtoTests(TestCase):
    """La factura declara una entrega por línea (grupo E605)."""

    databases = {'default', 'sync'}

    def test_una_entrega_por_linea_cada_cheque_con_sus_datos(self):
        usuario = crear_usuario(username='cajero_fact_mixto')
        pedido = crear_pedido(usuario, [(crear_variante(nombre='P fact'), 1, 1000000)])
        sesion = crear_sesion(usuario)
        pago = Pago(pedido=pedido, sesion_caja=sesion, cajero=usuario,
                    medio_pago=Pago.MEDIO_MIXTO, monto=TOTAL,
                    estado=Pago.ESTADO_CONFIRMADO)
        pago.save()
        for monto, numero in ((Decimal('600000'), '111'), (Decimal('300000'), '222')):
            linea = PagoMedio.objects.create(pago=pago, medio='cheque', monto=monto)
            DatosCheque.objects.create(pago=pago, linea=linea, numero=numero,
                                       banco='Banco Continental')
        PagoMedio.objects.create(pago=pago, medio='efectivo',
                                 monto=Decimal('100000'), monto_recibido=Decimal('100000'))

        documento = crear_documento(
            pago, receptor={'ruc': RUC_RECEPTOR, 'razon_social': 'Cliente SRL'})
        entregas = payload.construir_data(documento)['condicion']['entregas']

        self.assertEqual(len(entregas), 3)
        self.assertEqual([e['tipo'] for e in entregas],
                         [codigos.PAGO_CHEQUE, codigos.PAGO_CHEQUE, codigos.PAGO_EFECTIVO])
        self.assertEqual([e['monto'] for e in entregas], ['600000', '300000', '100000'])
        self.assertEqual(entregas[0]['infoCheque']['numeroCheque'], '00000111')
        self.assertEqual(entregas[1]['infoCheque']['numeroCheque'], '00000222')
        self.assertNotIn('infoCheque', entregas[2])
        # El código único del documento es el del medio con más plata
        self.assertEqual(documento.medio_pago, codigos.PAGO_CHEQUE)
