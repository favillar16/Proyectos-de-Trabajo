"""
Ganancia real: precio cobrado contra costo de adquisición (apps/caja/ganancias.py).

Lo que tiene que quedar bien:
  · el costo se congela al cobrar — cambiar el costo después no reescribe
    la ganancia de una venta vieja;
  · el ingreso es lo cobrado de verdad, con el descuento de caja aplicado;
  · un producto sin costo cargado no infla la ganancia: va aparte;
  · una devolución resta ingreso y costo, salvo mercadería dañada, cuyo
    costo queda como pérdida;
  · los gastos del período no incluyen los pagos a proveedor (esa
    mercadería ya entra como costo de lo vendido).
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.caja import ganancias, reportes
from apps.caja.models import Devolucion
from apps.caja.tests.test_devoluciones import BaseDevolucionTests
from apps.costos.models import CategoriaGasto, GastoOperativo
from apps.facturacion.tests.factories import SIFEN_APAGADO
from apps.inventario.models import MovimientoStock, Stock
from apps.ventas.models import NotaPedido


def _con_costo(variante, costo):
    variante.producto.precio_costo = Decimal(costo)
    variante.producto.save(update_fields=['precio_costo'])


class GananciaTests(BaseDevolucionTests):

    def setUp(self):
        super().setUp()
        # Porcelanato: se vende a 150.000 y costó 100.000 → 50.000 por m²
        _con_costo(self.porcelanato, '100000')
        self.hoy = timezone.localdate()

    def _resumen(self):
        return ganancias.resumen(self.hoy, self.hoy)

    def test_ganancia_de_una_venta_simple(self):
        self._vender([(self.porcelanato, '2', '150000')])
        r = self._resumen()
        self.assertEqual(r['ingresos'], Decimal('300000'))
        self.assertEqual(r['costo'], Decimal('200000'))
        self.assertEqual(r['ganancia_bruta'], Decimal('100000'))
        self.assertAlmostEqual(float(r['margen']), 33.33, places=2)

    def test_el_costo_queda_congelado_al_cobrar(self):
        pago = self._vender([(self.porcelanato, '2', '150000')])
        self.assertEqual(self._item(pago, self.porcelanato).costo_unitario, Decimal('100000'))

        # Llega una factura nueva del proveedor, más cara
        _con_costo(self.porcelanato, '130000')
        self.assertEqual(self._resumen()['ganancia_bruta'], Decimal('100000'))

    def test_el_ingreso_es_lo_cobrado_no_el_precio_de_lista(self):
        # Cobrado con 10% de descuento en caja: 270.000 por algo de 300.000
        self._vender([(self.porcelanato, '2', '150000')], monto=Decimal('270000'))
        r = self._resumen()
        self.assertEqual(r['ingresos'], Decimal('270000'))
        self.assertEqual(r['ganancia_bruta'], Decimal('70000'))

    def test_sin_costo_cargado_no_infla_la_ganancia(self):
        self._vender([(self.porcelanato, '1', '150000'), (self.ceramica, '1', '90000')])
        r = self._resumen()
        self.assertEqual(r['ingresos'], Decimal('240000'))
        self.assertEqual(r['ingresos_sin_costo'], Decimal('90000'))
        self.assertEqual(r['ganancia_bruta'], Decimal('50000'))

    def test_devolucion_que_vuelve_al_stock_anula_la_ganancia(self):
        pago = self._vender([(self.porcelanato, '2', '150000')])
        self._devolver(pago, [(self.porcelanato, Decimal('1'), True)], medio_pago='efectivo')
        r = self._resumen()
        self.assertEqual(r['ingresos'], Decimal('150000'))
        self.assertEqual(r['costo'], Decimal('100000'))
        self.assertEqual(r['ganancia_bruta'], Decimal('50000'))

    def test_devolucion_danada_deja_el_costo_como_perdida(self):
        pago = self._vender([(self.porcelanato, '2', '150000')])
        self._devolver(pago, [(self.porcelanato, Decimal('1'), False)], medio_pago='efectivo')
        r = self._resumen()
        # Se devolvió la plata de 1 m², pero la mercadería no se puede vender
        self.assertEqual(r['ingresos'], Decimal('150000'))
        self.assertEqual(r['costo'], Decimal('200000'))
        self.assertEqual(r['ganancia_bruta'], Decimal('-50000'))

    def test_los_pagos_a_proveedor_no_son_gasto_del_periodo(self):
        prov = CategoriaGasto.objects.create(nombre='Prov test', tipo=CategoriaGasto.TIPO_PROVEEDOR)
        luz = CategoriaGasto.objects.create(nombre='Luz test', tipo=CategoriaGasto.TIPO_SERVICIO)
        for cat, monto in ((prov, '9000000'), (luz, '300000')):
            GastoOperativo.objects.create(
                categoria=cat, descripcion='x', monto=Decimal(monto),
                anio=2026, mes=9, registrado_por=self.cajero)
        # Septiembre entero: solo la luz
        self.assertEqual(ganancias.gastos_operativos(date(2026, 9, 1), date(2026, 9, 30)),
                         Decimal('300000'))
        # Medio mes: la mitad
        self.assertEqual(ganancias.gastos_operativos(date(2026, 9, 1), date(2026, 9, 15)),
                         Decimal('150000'))

    def test_el_reporte_muestra_costo_cobrado_y_ganancia(self):
        self._vender([(self.porcelanato, '2', '150000')])
        rep = reportes.reporte_ganancias(self.hoy, self.hoy)
        fila = rep['filas'][0]
        self.assertEqual(fila[3], reportes._gs(100000))   # costo unitario
        self.assertEqual(fila[4], reportes._gs(150000))   # cobrado unitario
        self.assertEqual(fila[7], reportes._gs(100000))   # ganancia
        self.assertEqual(rep['totales']['Ganancia bruta'], reportes._gs(100000))

        detalle = reportes.reporte_ganancias(self.hoy, self.hoy, detalle=True)
        self.assertEqual(len(detalle['filas']), 1)


class ReporteGananciasApiTests(TestCase):
    databases = {'default', 'sync'}

    def test_solo_admin_y_en_los_dos_formatos(self):
        from apps.facturacion.tests.factories import crear_usuario
        admin = crear_usuario('admin_gan', rol='admin')
        vendedor = crear_usuario('vend_gan', rol='vendedor')
        api = APIClient()
        api.force_authenticate(vendedor)
        self.assertEqual(api.get('/api/v1/caja/reportes/ganancias/').status_code, 403)
        api.force_authenticate(admin)
        for formato in ('pdf', 'xlsx'):
            r = api.get(f'/api/v1/caja/reportes/ganancias/?formato={formato}&detalle=1')
            self.assertEqual(r.status_code, 200, formato)

    def test_el_dashboard_trae_la_ganancia_del_mes(self):
        from apps.facturacion.tests.factories import crear_usuario
        api = APIClient()
        api.force_authenticate(crear_usuario('admin_kpi', rol='admin'))
        r = api.get('/api/v1/caja/kpis/')
        self.assertIn('ganancia_mes', r.data)
        self.assertIn('ganancia_neta', r.data['ganancia_mes'])
