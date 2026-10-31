"""
Comisiones bancarias (apps/caja/comisiones.py).

Lo que tiene que quedar bien:
  · la cuenta reproduce la liquidación del banco que mandó la propietaria,
    guaraní por guaraní;
  · el QR débito descuenta 1,3 % en total, con el IVA adentro;
  · una tasa nueva rige desde su fecha y no reescribe los cobros viejos;
  · la ganancia neta resta comisión + IVA, no las retenciones;
  · efectivo, cheque y transferencia no pagan comisión, ni la parte en
    efectivo de un pago mixto.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.caja import comisiones, ganancias, reportes
from apps.caja.models import ComisionBancaria, Pago, PagoMedio
from apps.caja.tests.test_devoluciones import BaseDevolucionTests
from apps.facturacion import codigos
from apps.facturacion.tests.factories import crear_usuario


def _tasa(medio, dia=None):
    return comisiones.Tasas().vigente(medio, dia or timezone.localdate())


class CalculoTests(TestCase):
    """La cuenta sola, con las tasas que carga la migración."""

    def test_reproduce_la_liquidacion_del_banco(self):
        # El Excel del banco: QR crédito de 2.778.000 → 2.633.291 acreditados.
        d = comisiones.calcular(Decimal('2778000'), _tasa('qr_credito'))
        self.assertEqual(d.comision, Decimal('83340'))
        self.assertEqual(d.iva_comision, Decimal('8334'))
        self.assertEqual(d.retencion_renta, Decimal('27780'))
        self.assertEqual(d.retencion_iva, Decimal('25255'))
        self.assertEqual(d.neto, Decimal('2633291'))

    def test_tasas_cargadas(self):
        esperadas = {'debito': ('2', True), 'credito': ('3', True),
                     'qr_debito': ('1.3', False), 'qr_credito': ('3', True),
                     'pix': ('2', True)}
        for medio, (pct, iva_aparte) in esperadas.items():
            t = _tasa(medio)
            self.assertEqual(t.porcentaje, Decimal(pct), medio)
            self.assertEqual(t.iva_aparte, iva_aparte, medio)
            self.assertEqual(t.retencion_renta, Decimal('1'), medio)
            self.assertEqual(t.retencion_iva, Decimal('10'), medio)
        self.assertIsNone(_tasa('efectivo'))
        self.assertIsNone(_tasa('transferencia'))

    def test_qr_debito_trae_el_iva_adentro(self):
        d = comisiones.calcular(Decimal('1000000'), _tasa('qr_debito'))
        self.assertEqual(d.costo, Decimal('13000'))          # 1,3 % en total
        self.assertEqual(d.iva_comision, Decimal('1182'))    # 13.000 / 11
        self.assertEqual(d.comision, Decimal('11818'))

    def test_debito_es_2_mas_iva(self):
        d = comisiones.calcular(Decimal('1000000'), _tasa('debito'))
        self.assertEqual(d.comision, Decimal('20000'))
        self.assertEqual(d.iva_comision, Decimal('2000'))

    def test_sin_tasa_no_descuenta_nada(self):
        d = comisiones.calcular(Decimal('500000'), None)
        self.assertEqual(d.descuento, Decimal('0'))
        self.assertEqual(d.neto, Decimal('500000'))

    def test_pix_es_transferencia_para_el_sifen(self):
        self.assertEqual(codigos.MEDIO_PAGO['pix'], codigos.PAGO_TRANSFERENCIA)


class CobrosTests(BaseDevolucionTests):

    def setUp(self):
        super().setUp()
        self.hoy = timezone.localdate()
        self.porcelanato.producto.precio_costo = Decimal('100000')
        self.porcelanato.producto.save(update_fields=['precio_costo'])

    def test_solo_los_medios_bancarios_pagan_comision(self):
        self._vender([(self.porcelanato, '2', '150000')], medio='efectivo')
        self._vender([(self.porcelanato, '1', '150000')], medio='credito')
        r = comisiones.resumen(self.hoy, self.hoy)
        self.assertEqual(r['total'].cobrado, Decimal('150000'))
        self.assertEqual(list(r['por_medio']), ['credito'])
        self.assertEqual(r['total'].comision, Decimal('4500'))

    def test_en_un_pago_mixto_solo_la_parte_bancaria(self):
        pago = self._vender([(self.porcelanato, '2', '150000')], medio='efectivo')
        PagoMedio.objects.filter(pago=pago).delete()
        PagoMedio.objects.create(pago=pago, medio='efectivo', monto=Decimal('100000'))
        PagoMedio.objects.create(pago=pago, medio='qr_credito', monto=Decimal('200000'))
        r = comisiones.resumen(self.hoy, self.hoy)
        self.assertEqual(r['total'].cobrado, Decimal('200000'))
        self.assertEqual(r['total'].comision, Decimal('6000'))

    def test_ganancia_neta_resta_comision_y_no_retenciones(self):
        self._vender([(self.porcelanato, '2', '150000')], medio='qr_credito')
        r = ganancias.resumen(self.hoy, self.hoy)
        # 300.000 cobrados: comisión 9.000 + IVA 900; retenciones 3.000 + 2.727
        self.assertEqual(r['comisiones_bancarias'], Decimal('9900'))
        self.assertEqual(r['retenciones_bancarias'], Decimal('5727'))
        self.assertEqual(r['ganancia_neta'], r['ganancia_bruta'] - r['gastos'] - Decimal('9900'))

    def test_una_tasa_nueva_no_reescribe_cobros_viejos(self):
        pago = self._vender([(self.porcelanato, '1', '150000')], medio='credito')
        ayer = timezone.now() - timedelta(days=1)
        Pago.objects.filter(pk=pago.pk).update(fecha=ayer)
        ComisionBancaria.objects.create(medio='credito', vigente_desde=self.hoy,
                                        porcentaje=Decimal('5'))
        dia = timezone.localdate(ayer)
        self.assertEqual(comisiones.resumen(dia, dia)['total'].comision, Decimal('4500'))

        self._vender([(self.porcelanato, '1', '150000')], medio='credito')
        self.assertEqual(comisiones.resumen(self.hoy, self.hoy)['total'].comision,
                         Decimal('7500'))

    def test_arqueo_muestra_lo_que_acredita_el_banco(self):
        self._vender([(self.porcelanato, '2', '150000')], medio='qr_credito')
        r = reportes.reporte_arqueo(self.hoy)
        conceptos = [f[0].strip() for f in r['filas']]
        self.assertIn('Neto que acreditan los bancos', conceptos)
        # 300.000 − 9.900 − 5.727
        self.assertEqual(r['totales']['Neto que acreditan los bancos'], reportes._gs(284373))

    def test_reporte_de_comisiones(self):
        self._vender([(self.porcelanato, '1', '150000')], medio='pix')
        r = reportes.reporte_comisiones(self.hoy, self.hoy)
        self.assertEqual(len(r['filas']), 1)
        self.assertEqual(r['filas'][0][3], 'PIX')
        self.assertEqual(r['totales']['Comisiones + IVA (costo del local)'], reportes._gs(3300))


class ApiTasasTests(TestCase):

    def setUp(self):
        self.admin = crear_usuario('admin_comisiones', rol='admin')
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def test_lista_las_vigentes(self):
        r = self.api.get('/api/v1/caja/comisiones/')
        self.assertEqual(r.status_code, 200)
        medios = [t['medio'] for t in r.data['vigentes']]
        self.assertEqual(medios, ['debito', 'credito', 'qr_debito', 'qr_credito', 'pix'])

    def test_una_tasa_nueva_queda_vigente_desde_hoy(self):
        r = self.api.post('/api/v1/caja/comisiones/',
                          {'medio': 'pix', 'porcentaje': '2.5', 'iva_aparte': True}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(_tasa('pix').porcentaje, Decimal('2.5'))
        # La anterior sigue rigiendo para ayer.
        self.assertEqual(_tasa('pix', timezone.localdate() - timedelta(days=1)).porcentaje,
                         Decimal('2'))

    def test_rechaza_un_medio_sin_banco(self):
        r = self.api.post('/api/v1/caja/comisiones/',
                          {'medio': 'efectivo', 'porcentaje': '1'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_solo_admin(self):
        cajero = crear_usuario('cajero_comisiones', rol='cajero')
        self.api.force_authenticate(cajero)
        self.assertEqual(self.api.get('/api/v1/caja/comisiones/').status_code, 403)
