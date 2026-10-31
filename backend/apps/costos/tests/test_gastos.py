"""
Gastos operativos: varios cheques por pago, el buscador y los avisos.

Pedidos de la propietaria del 30/10/2026:
  · pagar a un proveedor con más de un cheque, cada uno con su plazo;
  · buscar "San Carlos" y ver todo lo que se le pagó, de cualquier mes;
  · ver la fecha de cada gasto.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.costos.models import CategoriaGasto, ChequeGasto, Empleado, GastoOperativo, Proveedor
from apps.facturacion.tests.factories import crear_usuario

URL = '/api/v1/costos/gastos/'


class BaseGastos(TestCase):
    # Proveedor es sincronizable: su alta escribe en el registro del sync.
    databases = {'default', 'sync'}

    def setUp(self):
        self.admin = crear_usuario('admin_gastos', rol='admin')
        self.api = APIClient()
        self.api.force_authenticate(self.admin)
        self.cat_prov = CategoriaGasto.objects.create(nombre='Pago a proveedor', tipo='proveedor')
        self.cat_sal = CategoriaGasto.objects.create(nombre='Salario', tipo='salario')
        self.san_carlos = Proveedor.objects.create(nombre='San Carlos S.R.L Construccion y Ferreteria')
        self.otro = Proveedor.objects.create(nombre='Distribuidora Imperial S.A.')
        self.hoy = date.today()

    def _datos(self, **extra):
        datos = {'descripcion': 'Pago fact. 001', 'monto': '1000000',
                 'categoria_id': self.cat_prov.id, 'proveedor_id': self.san_carlos.id,
                 'anio': 2026, 'mes': 10, 'estado': 'pagado'}
        datos.update(extra)
        return datos

    def _gasto(self, **extra):
        r = self.api.post(URL, self._datos(**extra), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        return r.data


class ChequesTests(BaseGastos):

    def test_un_pago_con_varios_cheques(self):
        g = self._gasto(metodo_pago='cheque', cheques=[
            {'numero': 'CS 378244', 'banco': 'Continental', 'fecha_cobro': '2026-11-20', 'monto': '600000'},
            {'numero': 'CS 378245', 'banco': 'Continental', 'fecha_cobro': '2026-12-20', 'monto': '400000'},
        ])
        self.assertEqual(len(g['cheques']), 2)
        self.assertEqual(ChequeGasto.objects.filter(gasto_id=g['id']).count(), 2)

    def test_un_solo_cheque_vale_el_gasto_entero(self):
        g = self._gasto(metodo_pago='cheque', cheques=[
            {'numero': '1', 'banco': 'Itaú', 'fecha_cobro': '2026-11-20'}])
        self.assertEqual(Decimal(g['cheques'][0]['monto']), Decimal('1000000'))

    def test_los_cheques_tienen_que_sumar_el_gasto(self):
        r = self.api.post(URL, self._datos(metodo_pago='cheque', cheques=[
            {'fecha_cobro': '2026-11-20', 'monto': '600000'},
            {'fecha_cobro': '2026-12-20', 'monto': '300000'}]), format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('cheques', r.data)
        self.assertFalse(GastoOperativo.objects.exists())

    def test_cada_cheque_lleva_su_fecha(self):
        r = self.api.post(URL, self._datos(metodo_pago='cheque', cheques=[
            {'numero': '1', 'monto': '1000000'}]), format='json')
        self.assertEqual(r.status_code, 400)

    def test_sin_cheques_no_se_registra_un_pago_con_cheque(self):
        r = self.api.post(URL, self._datos(metodo_pago='cheque'), format='json')
        self.assertEqual(r.status_code, 400)

    def test_numeros_repetidos(self):
        r = self.api.post(URL, self._datos(metodo_pago='cheque', cheques=[
            {'numero': '7', 'fecha_cobro': '2026-11-20', 'monto': '500000'},
            {'numero': '7', 'fecha_cobro': '2026-12-20', 'monto': '500000'}]), format='json')
        self.assertEqual(r.status_code, 400)

    def test_formato_viejo_de_un_cheque(self):
        g = self._gasto(metodo_pago='cheque', cheque_numero='99', cheque_banco='Atlas',
                        cheque_fecha_cobro='2026-11-05')
        self.assertEqual(len(g['cheques']), 1)
        self.assertEqual(g['cheques'][0]['numero'], '99')
        self.assertEqual(g['proximo_cobro'], '2026-11-05')

    def test_marcar_pagado_no_toca_los_cheques(self):
        g = self._gasto(estado='pendiente', metodo_pago='cheque', cheques=[
            {'fecha_cobro': '2026-11-20', 'monto': '600000'},
            {'fecha_cobro': '2026-12-20', 'monto': '400000'}])
        r = self.api.patch(f'{URL}{g["id"]}/', {'estado': 'pagado', 'fecha_pago': '2026-10-30'},
                           format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(len(r.data['cheques']), 2)
        self.assertEqual(r.data['fecha_pago'], '2026-10-30')

    def test_cambiar_el_monto_sin_ajustar_los_cheques(self):
        g = self._gasto(metodo_pago='cheque', cheques=[
            {'fecha_cobro': '2026-11-20', 'monto': '600000'},
            {'fecha_cobro': '2026-12-20', 'monto': '400000'}])
        r = self.api.patch(f'{URL}{g["id"]}/', {'monto': '1200000'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_pasar_a_efectivo_borra_los_cheques(self):
        g = self._gasto(metodo_pago='cheque', cheques=[{'fecha_cobro': '2026-11-20'}])
        r = self.api.patch(f'{URL}{g["id"]}/', {'metodo_pago': 'efectivo'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['cheques'], [])

    def test_avisos_agrupados_por_proveedor(self):
        en_3 = (self.hoy + timedelta(days=3)).isoformat()
        en_5 = (self.hoy + timedelta(days=5)).isoformat()
        lejos = (self.hoy + timedelta(days=60)).isoformat()
        viejo = (self.hoy - timedelta(days=40)).isoformat()
        self._gasto(metodo_pago='cheque', cheques=[
            {'numero': '1', 'fecha_cobro': en_3, 'monto': '300000'},
            {'numero': '2', 'fecha_cobro': en_5, 'monto': '300000'},
            {'numero': '3', 'fecha_cobro': lejos, 'monto': '300000'},
            {'numero': '4', 'fecha_cobro': viejo, 'monto': '100000'}])
        r = self.api.get('/api/v1/costos/alertas/')
        grupos = r.data['cheques_agrupados']
        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0]['cantidad'], 2)          # ni el lejano ni el viejo
        self.assertEqual(grupos[0]['monto_total'], 600000.0)
        self.assertEqual(grupos[0]['proximo_dias'], 3)


class BuscadorTests(BaseGastos):

    def test_busca_por_proveedor_en_todos_los_meses(self):
        self._gasto(descripcion='Arreglo 13/10', mes=10)
        self._gasto(descripcion='Pago 15/09', mes=9)
        self._gasto(descripcion='Otra factura', proveedor_id=self.otro.id)
        r = self.api.get(URL, {'buscar': 'san carlos'})
        self.assertEqual(r.data['count'], 2)
        self.assertEqual(r.data['total'], 2000000.0)

    def test_busca_por_funcionario(self):
        empleado = Empleado.objects.create(nombre_completo='María Benítez', salario_base=3000000)
        self._gasto(categoria_id=self.cat_sal.id, proveedor_id=None, empleado_id=empleado.id,
                    descripcion='Sueldo octubre')
        self._gasto()
        r = self.api.get(URL, {'buscar': 'Benítez'})
        self.assertEqual(r.data['count'], 1)

    def test_filtra_por_tipo_y_mes(self):
        self._gasto()
        self._gasto(mes=9)
        r = self.api.get(URL, {'tipo': 'proveedor', 'anio': 2026, 'mes': 10})
        self.assertEqual(r.data['count'], 1)
        self.assertEqual(self.api.get(URL, {'tipo': 'salario'}).data['count'], 0)

    def test_por_numero_de_cheque_sin_repetir_el_gasto(self):
        self._gasto(metodo_pago='cheque', cheques=[
            {'numero': 'CS 1', 'fecha_cobro': '2026-11-20', 'monto': '500000'},
            {'numero': 'CS 2', 'fecha_cobro': '2026-12-20', 'monto': '500000'}])
        self.assertEqual(self.api.get(URL, {'buscar': 'CS'}).data['count'], 1)

    def test_el_total_no_cuenta_los_cancelados(self):
        self._gasto()
        self._gasto(estado='cancelado')
        r = self.api.get(URL, {'anio': 2026, 'mes': 10})
        self.assertEqual(r.data['count'], 2)
        self.assertEqual(r.data['total'], 1000000.0)
