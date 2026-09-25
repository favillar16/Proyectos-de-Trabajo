"""
Tests del registro de ajustes de stock.

Después de guardar un ajuste no quedaba ningún lugar donde ver qué se había
cambiado: el aviso duraba dos segundos y el cuadro se cerraba. Ahora el POST
devuelve el movimiento como constancia y el GET lista todos los ajustes
manuales, con su motivo, de cualquier producto.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.inventario.models import MovimientoStock, Stock
from apps.productos.tests.factories import (crear_producto, crear_usuario,
                                            crear_variante)
from apps.usuarios.models import Usuario


class RegistroDeAjustesTests(TestCase):
    # El alta de catálogo escribe en el registro de cambios del sync.
    databases = {'default', 'sync'}

    def setUp(self):
        self.admin = crear_usuario('admin_ajustes', rol=Usuario.ROL_ADMIN)
        self.cliente_api = APIClient()
        self.cliente_api.force_authenticate(self.admin)
        self.variante = crear_variante(producto=crear_producto(nombre='Piso 71220'))
        Stock.objects.get(variante=self.variante).registrar_movimiento(
            tipo=MovimientoStock.TIPO_ENTRADA, cantidad=Decimal('143'), usuario=self.admin)

    def _ajustar(self, cantidad, motivo, tipo='ajuste'):
        return self.cliente_api.post(reverse('stock-ajuste'), {
            'variante_id': self.variante.id, 'tipo': tipo,
            'cantidad': cantidad, 'observaciones': motivo,
        }, format='json')

    def test_el_ajuste_devuelve_la_constancia(self):
        respuesta = self._ajustar('220', 'Reposición')
        self.assertEqual(respuesta.status_code, 200)
        mov = respuesta.data['movimiento']
        self.assertEqual(Decimal(mov['cantidad_anterior']), Decimal('143'))
        self.assertEqual(Decimal(mov['cantidad_posterior']), Decimal('220'))
        self.assertEqual(mov['observaciones'], 'Reposición')
        self.assertEqual(mov['usuario_nombre'], self.admin.nombre_completo)

    def test_el_registro_lista_solo_los_ajustes_manuales(self):
        self._ajustar('220', 'Reposición')
        self._ajustar('5', 'Rotura en depósito', tipo='salida')
        respuesta = self.cliente_api.get(reverse('stock-ajuste'))
        self.assertEqual(respuesta.status_code, 200)
        # La entrada del setUp no es un ajuste manual: no aparece.
        self.assertEqual(respuesta.data['count'], 2)
        primero = respuesta.data['results'][0]
        self.assertEqual(primero['observaciones'], 'Rotura en depósito')
        self.assertEqual(primero['sku'], self.variante.sku)
        self.assertIn('Piso 71220', primero['descripcion'])

    def test_busca_por_motivo_o_producto(self):
        self._ajustar('220', 'Reposición')
        self._ajustar('5', 'Rotura en depósito', tipo='salida')
        por_motivo = self.cliente_api.get(reverse('stock-ajuste'), {'buscar': 'rotura'})
        self.assertEqual(por_motivo.data['count'], 1)
        por_producto = self.cliente_api.get(reverse('stock-ajuste'), {'buscar': '71220'})
        self.assertEqual(por_producto.data['count'], 2)

    def test_fecha_invalida(self):
        respuesta = self.cliente_api.get(reverse('stock-ajuste'), {'desde': '25/09/2026'})
        self.assertEqual(respuesta.status_code, 400)

    def test_el_reporte_sale_en_pdf_y_excel(self):
        self._ajustar('220', 'Reposición')
        pdf = self.cliente_api.get(reverse('stock-ajuste'), {'formato': 'pdf'})
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')
        self.assertTrue(pdf.content.startswith(b'%PDF'))
        xlsx = self.cliente_api.get(reverse('stock-ajuste'), {'formato': 'xlsx'})
        self.assertEqual(xlsx.status_code, 200)
        self.assertIn('registro_ajustes_', xlsx['Content-Disposition'])

    def test_el_reporte_respeta_los_filtros(self):
        from apps.inventario.reportes import reporte_ajustes
        self._ajustar('220', 'Reposición')
        self._ajustar('5', '', tipo='salida')
        qs = MovimientoStock.objects.filter(referencia_tipo='ajuste_manual').order_by('-fecha')
        reporte = reporte_ajustes(qs.filter(observaciones__icontains='repos'), buscar='repos')
        self.assertEqual(len(reporte['filas']), 1)
        self.assertIn('Reposición', reporte['filas'][0])
        self.assertIn('"repos"', reporte['subtitulo'])
        completo = reporte_ajustes(qs)
        self.assertEqual(completo['totales']['Sin motivo cargado'], 1)

    def test_un_vendedor_no_ve_el_registro(self):
        self.cliente_api.force_authenticate(
            crear_usuario('vendedor_ajustes', rol=Usuario.ROL_VENDEDOR))
        self.assertEqual(self.cliente_api.get(reverse('stock-ajuste')).status_code, 403)
