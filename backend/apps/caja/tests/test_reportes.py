"""
Tests de los dos reportes que pidió la propietaria: "Productos
comercializados" y "Arqueo de Caja".

No comparan píxeles del PDF. Verifican lo que hace útil a cada reporte:

  · que el de productos abra la venta en los productos que la componen —que
    es justamente lo que el Balance de Ventas no muestra— y que la cantidad
    salga exacta y con su unidad, no redondeada;
  · que el arqueo separe el efectivo del resto y calcule la diferencia
    contra lo declarado al cerrar, que es el número por el que existe.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.caja import reportes as rep
from apps.caja.models import Pago, SesionCaja
from apps.facturacion.tests.factories import (crear_pago, crear_pedido,
                                              crear_sesion, crear_usuario,
                                              crear_variante)


class ReporteProductosTests(TestCase):
    # El alta de catálogo escribe en el registro de cambios del sync,
    # que vive en otra base.
    databases = {'default', 'sync'}

    def setUp(self):
        self.cajero = crear_usuario('cajera_reportes')
        self.sesion = crear_sesion(self.cajero)
        self.hoy = date.today()

        self.porcelanato = crear_variante('Porcelanato Roma', Decimal('150000'))
        self.ceramica = crear_variante('Cerámica Bahía', Decimal('90000'))

        # 12,60 m² de porcelanato (cinco cajas de 2,52) y 3 m² de cerámica.
        pedido = crear_pedido(self.cajero, [
            (self.porcelanato, '12.60', '150000'),
            (self.ceramica,    '3',     '90000'),
        ])
        crear_pago(pedido, self.sesion, self.cajero, Decimal('2160000'))

    def _reporte(self, detalle=False):
        return rep.reporte_productos(self.hoy, self.hoy, detalle=detalle)

    def test_agregado_lista_una_fila_por_variante(self):
        reporte = self._reporte()
        self.assertEqual(len(reporte['filas']), 2)
        self.assertEqual(reporte['totales']['Variantes distintas vendidas'], 2)

    def test_la_cantidad_sale_exacta_y_con_unidad(self):
        """
        12,60 m² no son "13". El reporte es el que usa la propietaria para
        reponer: redondear cambia lo que compra.
        """
        reporte = self._reporte()
        fila = next(f for f in reporte['filas'] if f[0] == 'Porcelanato Roma')
        self.assertEqual(fila[3], '12,60 m²')

    def test_ordena_por_ingresos(self):
        reporte = self._reporte()
        self.assertEqual(reporte['filas'][0][0], 'Porcelanato Roma')

    def test_detalle_trae_la_fecha_de_la_venta(self):
        reporte = self._reporte(detalle=True)
        self.assertEqual(reporte['columnas'][0], 'Fecha')
        self.assertTrue(
            all(f[0].startswith(self.hoy.strftime('%d/%m/%Y'))
                for f in reporte['filas']))

    def test_un_cobro_no_confirmado_no_cuenta_como_venta(self):
        pedido = crear_pedido(self.cajero, [(self.ceramica, '5', '90000')])
        Pago.objects.create(
            pedido=pedido, sesion_caja=self.sesion, cajero=self.cajero,
            medio_pago='efectivo', monto=Decimal('450000'),
            estado=Pago.ESTADO_PENDIENTE,
        )
        reporte = self._reporte()
        fila = next(f for f in reporte['filas'] if f[0] == 'Cerámica Bahía')
        self.assertEqual(fila[3], '3,00 m²')  # sigue siendo la venta cobrada

    def test_fuera_del_rango_no_aparece(self):
        ayer = self.hoy - timedelta(days=1)
        reporte = rep.reporte_productos(ayer, ayer)
        self.assertEqual(reporte['filas'], [])

    def test_el_pdf_se_genera(self):
        self.assertTrue(rep.render_pdf(self._reporte()).startswith(b'%PDF'))

    def test_el_excel_se_genera(self):
        self.assertTrue(rep.render_xlsx(self._reporte(detalle=True)))


class ReporteArqueoTests(TestCase):
    databases = {'default', 'sync'}

    def setUp(self):
        self.cajero = crear_usuario('cajera_arqueo')
        self.variante = crear_variante('Inodoro Vitra', Decimal('500000'))
        self.hoy = date.today()

    def _cobrar(self, sesion, monto, medio='efectivo'):
        pedido = crear_pedido(self.cajero, [(self.variante, '1', str(monto))])
        return crear_pago(pedido, sesion, self.cajero, Decimal(str(monto)), medio)

    def _conceptos(self, reporte):
        return {f[0].strip(): f[2] for f in reporte['filas']}

    def test_sin_sesiones_lo_dice_y_igual_trae_la_planilla(self):
        reporte = rep.reporte_arqueo(self.hoy)
        textos = [f[0] for f in reporte['filas']]
        self.assertIn('No hubo sesiones de caja este día', textos)
        self.assertIn('CONTEO FÍSICO DEL EFECTIVO', textos)

    def test_el_efectivo_esperado_suma_apertura_y_cobros_en_efectivo(self):
        sesion = SesionCaja.objects.create(
            cajero=self.cajero, monto_apertura=Decimal('500000'))
        self._cobrar(sesion, 300000, 'efectivo')
        self._cobrar(sesion, 900000, 'credito')

        conceptos = self._conceptos(rep.reporte_arqueo(self.hoy))
        self.assertEqual(conceptos['Efectivo que debe haber en el cajón'],
                         'Gs. 800.000')
        self.assertEqual(conceptos['Total cobrado en el turno'], 'Gs. 1.200.000')

    def test_la_tarjeta_no_entra_en_el_efectivo_esperado(self):
        """
        Una tarjeta no está en el cajón. Sumarla haría que un arqueo
        correcto aparezca descuadrado todos los días.
        """
        sesion = SesionCaja.objects.create(
            cajero=self.cajero, monto_apertura=Decimal('0'))
        self._cobrar(sesion, 1000000, 'debito')
        conceptos = self._conceptos(rep.reporte_arqueo(self.hoy))
        self.assertEqual(conceptos['Efectivo que debe haber en el cajón'], 'Gs. 0')

    def test_marca_faltante_cuando_lo_declarado_es_menor(self):
        sesion = SesionCaja.objects.create(
            cajero=self.cajero, monto_apertura=Decimal('100000'))
        self._cobrar(sesion, 400000, 'efectivo')
        sesion.monto_cierre = Decimal('450000')   # faltan 50.000
        sesion.estado = SesionCaja.ESTADO_CERRADA
        sesion.fecha_cierre = timezone.now()
        sesion.save()

        reporte = rep.reporte_arqueo(self.hoy)
        fila = next(f for f in reporte['filas'] if f[0].strip() == 'Diferencia')
        self.assertEqual(fila[1], 'faltante')
        self.assertEqual(fila[2], 'Gs. 50.000')

    def test_caja_abierta_deja_la_diferencia_en_blanco(self):
        sesion = SesionCaja.objects.create(
            cajero=self.cajero, monto_apertura=Decimal('100000'))
        self._cobrar(sesion, 200000, 'efectivo')
        fila = next(f for f in rep.reporte_arqueo(self.hoy)['filas']
                    if f[0].strip() == 'Diferencia')
        self.assertEqual(fila[1], 'se calcula al cerrar')

    def test_trae_la_grilla_de_denominaciones_para_contar_a_mano(self):
        reporte = rep.reporte_arqueo(self.hoy)
        etiquetas = [f[0].strip() for f in reporte['filas']]
        for valor in (100000, 50000, 1000, 50):
            self.assertIn(rep._gs(valor), etiquetas)

    def test_el_pdf_se_genera(self):
        sesion = SesionCaja.objects.create(
            cajero=self.cajero, monto_apertura=Decimal('100000'))
        self._cobrar(sesion, 200000, 'efectivo')
        self.assertTrue(rep.render_pdf(rep.reporte_arqueo(self.hoy)).startswith(b'%PDF'))
