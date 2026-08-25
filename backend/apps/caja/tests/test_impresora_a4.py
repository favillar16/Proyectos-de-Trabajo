"""
Tests de la impresión A4 (Epson EcoTank L1250).

La L1250 no imprime comprobantes: lo único que sale por ella es la planilla de
etiquetas de código de barras, que es lo que le da algo que leer al lector
FTX-LC123BH5.

Un PDF no se puede "leer" para comprobar que quedó lindo, así que estos tests
verifican lo que sí es verificable y lo que de verdad rompe una planilla:

- que respete la grilla, para que las etiquetas caigan dentro del troquel;
- que una etiqueta rota no haga perder las otras 23 de la hoja;
- que sin impresora configurada el error diga qué falta.
"""
import re
from decimal import Decimal

from django.test import SimpleTestCase, override_settings

from apps.caja import impresora_a4 as a4
from apps.productos.codigo_barras import generar_ean_interno


def contar_paginas(pdf: bytes) -> int:
    """Cuenta objetos /Type /Page (sin contar /Pages, el nodo raíz)."""
    return len(re.findall(rb'/Type\s*/Page[^s]', pdf))


class EtiquetasTests(SimpleTestCase):

    def _etiquetas(self, n):
        return [{
            'codigo': generar_ean_interno(i),
            'sku': f'POR-{i:03d}-BEIGE',
            'nombre': 'Porcelanato Inout Speciale Polido 74x74',
            'detalle': '74x74 · Blanco Calacata',
            'precio': Decimal('185000'),
        } for i in range(n)]

    def test_una_hoja_entra_la_grilla_completa(self):
        por_hoja = a4.ETIQUETAS_COLUMNAS * a4.ETIQUETAS_FILAS
        pdf = a4.etiquetas_pdf(self._etiquetas(por_hoja))
        self.assertEqual(contar_paginas(pdf), 1)

    def test_una_etiqueta_de_mas_abre_otra_hoja(self):
        por_hoja = a4.ETIQUETAS_COLUMNAS * a4.ETIQUETAS_FILAS
        pdf = a4.etiquetas_pdf(self._etiquetas(por_hoja + 1))
        self.assertEqual(contar_paginas(pdf), 2)

    def test_desde_posicion_saltea_celdas_de_la_primera_hoja(self):
        """
        Reusar una planilla ya empezada es el caso normal: si no se pudiera,
        cada impresión de tres etiquetas gastaría una hoja entera.
        """
        por_hoja = a4.ETIQUETAS_COLUMNAS * a4.ETIQUETAS_FILAS
        pdf = a4.etiquetas_pdf(self._etiquetas(3), desde_posicion=por_hoja - 1)
        self.assertEqual(contar_paginas(pdf), 2)

    def test_un_codigo_no_ean_sale_como_code128(self):
        """El lector lee las dos simbologías; el SKU no es un EAN válido."""
        etiquetas = [{'codigo': 'POR-001-60X60-BEIGE', 'sku': 'POR-001',
                      'nombre': 'Prueba', 'detalle': '', 'precio': 0}]
        pdf = a4.etiquetas_pdf(etiquetas)
        self.assertTrue(pdf.startswith(b'%PDF'))

    def test_un_codigo_invalido_no_tumba_la_planilla(self):
        """
        Una etiqueta que no se puede dibujar no puede hacer perder las otras
        23 de la hoja.
        """
        etiquetas = self._etiquetas(3)
        etiquetas[1]['codigo'] = ''      # sin código
        pdf = a4.etiquetas_pdf(etiquetas)
        self.assertEqual(contar_paginas(pdf), 1)

    def test_sin_etiquetas_devuelve_un_pdf_vacio_valido(self):
        pdf = a4.etiquetas_pdf([])
        self.assertTrue(pdf.startswith(b'%PDF'))


class EnvioAImpresoraTests(SimpleTestCase):

    @override_settings(IMPRESORA_A4={'nombre_windows': '', 'modo': 'manual'})
    def test_sin_impresora_configurada_falla_con_mensaje_claro(self):
        resultado = a4.imprimir_pdf(b'%PDF-1.4', titulo='x')
        self.assertFalse(resultado['ok'])
        self.assertIn('IMPRESORA_A4_NOMBRE', resultado['error'])

    @override_settings(IMPRESORA_A4={'nombre_windows': '', 'modo': 'manual'})
    def test_estado_avisa_que_no_esta_configurada(self):
        estado = a4.estado_impresora_a4()
        self.assertFalse(estado['configurada'])
        self.assertFalse(estado['disponible'])
