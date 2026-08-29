"""
Tests del comando `cargar_lote_facturas`.

Lo que se protege acá es la carga del día del lanzamiento: 184 filas
transcriptas de facturas escaneadas que se dan de alta de una sola pasada.
Los errores que importan son los silenciosos — cargar el doble de stock al
repetir el comando, o poner un precio de venta igual al costo.
"""
import csv
import io
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.inventario.models import MovimientoStock, Stock
from apps.productos.models import Producto, Variante
from apps.productos.tests.factories import crear_usuario

COLUMNAS = [
    'pagina', 'proveedor', 'factura', 'fecha', 'cod_proveedor',
    'descripcion_factura', 'categoria_sugerida', 'marca', 'nombre_producto',
    'color', 'largo_cm', 'ancho_cm', 'unidad_venta', 'm2_por_caja',
    'piezas_por_caja', 'cantidad_factura', 'unidad_cantidad', 'cajas',
    'costo_unitario_gs', 'total_linea_gs', 'observaciones',
]


def fila(**campos):
    base = dict.fromkeys(COLUMNAS, '')
    base.update({
        'pagina': '1',
        'proveedor': 'PROVEEDOR S.A.',
        'factura': '001-001-0000001',
        'fecha': '2026-08-01',
        'cod_proveedor': 'X1',
        'categoria_sugerida': 'sanitario',
        'nombre_producto': 'Inodoro Prueba',
        'unidad_venta': 'pieza',
        'cantidad_factura': '2',
        'unidad_cantidad': 'un',
        'costo_unitario_gs': '100000',
    })
    base.update(campos)
    return base


class BaseLoteTests(TestCase):
    # Crear catalogo dispara el registro de cambios del sync (base aparte).
    databases = {'default', 'sync'}

    def setUp(self):
        self.usuario = crear_usuario(username='admin-lote')
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def csv_con(self, filas):
        ruta = Path(self._tmp.name) / 'lote.csv'
        with open(ruta, 'w', encoding='utf-8-sig', newline='') as f:
            escritor = csv.DictWriter(f, fieldnames=COLUMNAS, delimiter=';')
            escritor.writeheader()
            escritor.writerows(filas)
        return str(ruta)

    def cargar(self, filas, **opciones):
        salida = io.StringIO()
        opciones.setdefault('margen', '40')
        call_command('cargar_lote_facturas', archivo=self.csv_con(filas),
                     stdout=salida, stderr=salida, **opciones)
        return salida.getvalue()


class PrecioTests(BaseLoteTests):
    def test_sin_margen_no_carga_nada(self):
        """El CSV solo trae costos: cargar sin margen dejaría el precio mal."""
        with self.assertRaises(CommandError) as ctx:
            call_command('cargar_lote_facturas',
                         archivo=self.csv_con([fila()]), stdout=io.StringIO())
        self.assertIn('margen', str(ctx.exception).lower())
        self.assertEqual(Producto.objects.count(), 0)

    def test_margen_general_se_aplica_sobre_el_costo(self):
        self.cargar([fila(costo_unitario_gs='100000')], margen='40')
        producto = Producto.objects.get(nombre='Inodoro Prueba')
        self.assertEqual(producto.precio_costo, Decimal('100000'))
        self.assertEqual(producto.precio_base, Decimal('140000'))

    def test_margen_por_rubro_pisa_al_general(self):
        self.cargar(
            [fila(categoria_sugerida='pastina', nombre_producto='Pastina X',
                  costo_unitario_gs='10000')],
            margen='40', margen_rubro='pastina=100')
        self.assertEqual(
            Producto.objects.get(nombre='Pastina X').precio_base,
            Decimal('20000'))

    def test_redondea_hacia_arriba_al_millar(self):
        """140.140 Gs no es un precio de mostrador; 141.000 sí."""
        self.cargar([fila(costo_unitario_gs='100100')], margen='40')
        self.assertEqual(
            Producto.objects.get(nombre='Inodoro Prueba').precio_base,
            Decimal('141000'))

    def test_sin_redondeo_deja_el_valor_exacto(self):
        self.cargar([fila(costo_unitario_gs='100100')], margen='40', redondeo=0)
        self.assertEqual(
            Producto.objects.get(nombre='Inodoro Prueba').precio_base,
            Decimal('140140'))

    def test_rubro_desconocido_en_margen_rubro_se_rechaza(self):
        with self.assertRaises(CommandError):
            call_command('cargar_lote_facturas',
                         archivo=self.csv_con([fila()]),
                         margen='40', margen_rubro='inventado=30',
                         stdout=io.StringIO())


class AgrupacionTests(BaseLoteTests):
    def test_mismo_nombre_distinto_color_es_un_producto_con_varias_variantes(self):
        self.cargar([
            fila(color='Blanco', cod_proveedor='A'),
            fila(color='Beige', cod_proveedor='B'),
            fila(color='Gris', cod_proveedor='C'),
        ])
        self.assertEqual(Producto.objects.count(), 1)
        self.assertEqual(Variante.objects.count(), 3)
        self.assertEqual(
            sorted(Variante.objects.values_list('color', flat=True)),
            ['Beige', 'Blanco', 'Gris'])

    def test_cada_variante_recibe_su_propio_sku(self):
        self.cargar([fila(color='Blanco'), fila(color='Beige')])
        skus = set(Variante.objects.values_list('sku', flat=True))
        self.assertEqual(len(skus), 2)
        self.assertNotIn('', skus)

    def test_avisa_cuando_dos_filas_del_mismo_producto_traen_distinto_costo(self):
        salida = self.cargar([
            fila(color='Blanco', costo_unitario_gs='100000'),
            fila(color='Beige', costo_unitario_gs='120000'),
        ])
        self.assertIn('otro costo', salida)
        # Queda el de la primera fila; el aviso es para revisarlo a mano.
        self.assertEqual(Producto.objects.get().precio_costo, Decimal('100000'))


class IdempotenciaTests(BaseLoteTests):
    """Repetir el comando no puede duplicar productos ni inflar el stock."""

    def test_segunda_corrida_no_duplica_ni_suma_stock(self):
        filas = [fila(color='Blanco', cantidad_factura='2')]
        self.cargar(filas)
        variante = Variante.objects.get()
        self.assertEqual(variante.stock.cantidad, Decimal('2'))

        salida = self.cargar(filas)

        self.assertEqual(Producto.objects.count(), 1)
        self.assertEqual(Variante.objects.count(), 1)
        variante.stock.refresh_from_db()
        self.assertEqual(variante.stock.cantidad, Decimal('2'))
        self.assertEqual(MovimientoStock.objects.count(), 1)
        self.assertIn('ya existe', salida)


class StockTests(BaseLoteTests):
    def test_la_cantidad_facturada_entra_como_movimiento_de_entrada(self):
        self.cargar([fila(cantidad_factura='7')])
        movimiento = MovimientoStock.objects.get()
        self.assertEqual(movimiento.tipo, MovimientoStock.TIPO_ENTRADA)
        self.assertEqual(movimiento.cantidad, Decimal('7'))
        self.assertEqual(Stock.objects.get().cantidad, Decimal('7'))

    def test_sin_stock_carga_el_catalogo_sin_tocar_inventario(self):
        self.cargar([fila(cantidad_factura='7')], sin_stock=True)
        self.assertEqual(Producto.objects.count(), 1)
        self.assertEqual(MovimientoStock.objects.count(), 0)
        self.assertEqual(Stock.objects.get().cantidad, Decimal('0'))

    def test_marcada_no_cargar_al_stock_entra_al_catalogo_en_cero(self):
        """Un espejo roto existe como producto, pero no hay mercadería."""
        self.cargar([fila(cantidad_factura='1',
                          observaciones='MANUSCRITO: "ROTO" - no cargar al stock')])
        self.assertEqual(Producto.objects.count(), 1)
        self.assertEqual(Stock.objects.get().cantidad, Decimal('0'))
        self.assertEqual(MovimientoStock.objects.count(), 0)


class DecisionesPendientesTests(BaseLoteTests):
    OBS = 'Mueble de exhibicion, NO es mercaderia - confirmar si se carga'

    def test_se_saltea_por_defecto(self):
        salida = self.cargar([fila(observaciones=self.OBS)])
        self.assertEqual(Producto.objects.count(), 0)
        self.assertIn('decisión pendiente', salida)

    def test_incluir_dudosos_la_carga_con_su_cantidad(self):
        self.cargar([fila(observaciones=self.OBS, cantidad_factura='3')],
                    incluir_dudosos=True)
        self.assertEqual(Producto.objects.count(), 1)
        self.assertEqual(Stock.objects.get().cantidad, Decimal('3'))


class MedidasTests(BaseLoteTests):
    """
    El CSV describe la factura y Variante.clean() es más estricto. El comando
    adapta las dos diferencias reales del lote en vez de perder la fila.
    """

    def test_una_sola_medida_se_descarta_y_la_fila_igual_entra(self):
        salida = self.cargar([fila(nombre_producto='Conjunto KS 65cm',
                                   largo_cm='65')])
        variante = Variante.objects.get()
        self.assertIsNone(variante.largo_cm)
        self.assertIsNone(variante.ancho_cm)
        self.assertIn('una sola medida', salida)

    def test_m2_por_caja_del_fabricante_gana_sobre_las_piezas(self):
        """57×57×10 da 3,249 m²; la caja dice 3,30. Manda la factura."""
        salida = self.cargar([fila(
            categoria_sugerida='ceramica', nombre_producto='Rochaforte 57x57',
            largo_cm='57', ancho_cm='57', m2_por_caja='3.30',
            piezas_por_caja='10', unidad_venta='m2')])
        variante = Variante.objects.get()
        self.assertEqual(variante.m2_por_caja, Decimal('3.3000'))
        self.assertIsNone(variante.piezas_por_caja)
        self.assertIn('no cierra', salida)

    def test_medidas_coherentes_conservan_las_piezas_por_caja(self):
        self.cargar([fila(
            categoria_sugerida='ceramica', nombre_producto='Malibu 20x20',
            largo_cm='20', ancho_cm='20', m2_por_caja='0.64',
            piezas_por_caja='16', unidad_venta='m2')])
        variante = Variante.objects.get()
        self.assertEqual(variante.piezas_por_caja, 16)


class TrazabilidadTests(BaseLoteTests):
    def test_las_notas_internas_llevan_de_vuelta_al_papel(self):
        self.cargar([fila(pagina='27', proveedor='PROLAR SHOP',
                          factura='001-001-0110787', cod_proveedor='6ES0270D',
                          descripcion_factura='ESPEJO REDONDO 70CM')])
        notas = Producto.objects.get().notas_internas
        for dato in ('27', 'PROLAR SHOP', '001-001-0110787', '6ES0270D',
                     'ESPEJO REDONDO 70CM'):
            self.assertIn(dato, notas)

    def test_los_atributos_anotados_en_observaciones_se_cargan(self):
        self.cargar([fila(categoria_sugerida='inodoro',
                          observaciones='tipo_cisterna=alta')])
        self.assertEqual(Variante.objects.get().tipo_cisterna, 'alta')


class DryRunTests(BaseLoteTests):
    def test_no_escribe_nada_pero_valida_de_verdad(self):
        """
        El --dry-run recorre el camino real y deshace: si una fila no pasa la
        validación del modelo, se entera antes de la carga de verdad.
        """
        salida = self.cargar([
            fila(color='Blanco'),
            fila(nombre_producto='Conjunto KS 65cm', largo_cm='65'),
        ], dry_run=True)

        self.assertEqual(Producto.objects.count(), 0)
        self.assertEqual(Variante.objects.count(), 0)
        self.assertEqual(MovimientoStock.objects.count(), 0)
        self.assertIn('DRY-RUN', salida)
        self.assertIn('2 variantes se crearían', salida)
        self.assertIn('una sola medida', salida)
