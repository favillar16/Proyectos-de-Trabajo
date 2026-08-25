"""
Tests del código de barras de las variantes (lector FTX-LC123BH5).

Dos cosas distintas se prueban acá:

1. El algoritmo del dígito verificador EAN. Se contrasta contra EAN-13 reales
   y publicados, no contra sí mismo: un test que solo verifique que
   `generar` y `validar` coinciden pasa igual aunque el algoritmo esté al
   revés, y un código mal calculado no lo lee ningún lector.
2. Que un código no pueda apuntar a dos variantes. Si pasara, la caja
   cobraría el producto equivocado ante un escaneo.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from apps.productos import codigo_barras as cb
from apps.productos.models import Categoria, Producto, Variante


# EAN-13 reales, tomados de productos de góndola. Sirven de oráculo externo
# del algoritmo del dígito verificador.
EAN_REALES = [
    '4006381333931',   # Staedtler
    '7501031311309',   # Nestlé México
    '5449000000996',   # Coca-Cola
    '0012345678905',   # ejemplo canónico de GS1
]


class DigitoVerificadorTests(SimpleTestCase):

    def test_valida_ean13_reales(self):
        for ean in EAN_REALES:
            self.assertTrue(cb.es_ean_valido(ean), f'{ean} debería ser válido')

    def test_detecta_un_digito_cambiado(self):
        for ean in EAN_REALES:
            # Cambiar el primer dígito rompe el DV en todos estos casos.
            roto = ('9' if ean[0] != '9' else '8') + ean[1:]
            self.assertFalse(cb.es_ean_valido(roto),
                             f'{roto} no debería validar')

    def test_los_pesos_arrancan_por_la_derecha(self):
        """
        El peso 3 va en el dígito de más a la derecha del cuerpo. Calcularlo
        al revés da un DV que parece plausible pero que ningún lector acepta.
        Este test falla si alguien invierte el orden.
        """
        # Para 000000000001 el algoritmo correcto da DV=7 (1 * peso 3 = 3;
        # 10 - 3 = 7). Invertido daría 9.
        self.assertEqual(cb.digito_verificador_ean('000000000001'), '7')

    def test_rechaza_largos_que_no_son_de_ean(self):
        self.assertFalse(cb.es_ean_valido('12345'))
        self.assertFalse(cb.es_ean_valido('123456789012345'))

    def test_no_confunde_un_code128_con_un_ean(self):
        self.assertFalse(cb.parece_ean('POR-001-60x60'))


class CodigoInternoTests(SimpleTestCase):

    def test_el_interno_es_un_ean13_valido(self):
        for numero in (0, 1, 42, 130, 999_999_999):
            codigo = cb.generar_ean_interno(numero)
            self.assertEqual(len(codigo), 13)
            self.assertTrue(cb.es_ean_valido(codigo),
                            f'{codigo} tiene el DV mal')

    def test_usa_el_rango_reservado_de_gs1(self):
        """
        El prefijo 200-299 es el que GS1 reserva para uso interno del
        comercio. Si el generador saliera de ahí, un código interno podría
        colisionar con el EAN real de otro fabricante.
        """
        codigo = cb.generar_ean_interno(7)
        self.assertTrue(codigo.startswith('2'))
        self.assertTrue(cb.es_interno(codigo))

    def test_numeros_distintos_dan_codigos_distintos(self):
        codigos = {cb.generar_ean_interno(n) for n in range(200)}
        self.assertEqual(len(codigos), 200)

    def test_un_ean_de_fabrica_no_se_marca_como_interno(self):
        self.assertFalse(cb.es_interno('7501031311309'))

    def test_rechaza_numeros_fuera_de_rango(self):
        with self.assertRaises(ValueError):
            cb.generar_ean_interno(1_000_000_000)
        with self.assertRaises(ValueError):
            cb.generar_ean_interno(-1)


class NormalizacionTests(SimpleTestCase):

    def test_saca_el_salto_de_linea_que_manda_el_lector(self):
        """
        El FTX-LC123BH5 manda un Enter como sufijo. Si ese \\r\\n llegara a la
        base, la búsqueda exacta del escaneo siguiente no matchearía nunca.
        """
        self.assertEqual(cb.normalizar('7501031311309\r\n'), '7501031311309')

    def test_pasa_a_mayusculas_y_saca_espacios(self):
        self.assertEqual(cb.normalizar('  por-001-beige '), 'POR-001-BEIGE')

    def test_none_es_cadena_vacia(self):
        self.assertEqual(cb.normalizar(None), '')


class ValidadorTests(SimpleTestCase):

    def test_vacio_es_valido(self):
        cb.validar_codigo_barras('')      # no debe lanzar
        cb.validar_codigo_barras(None)

    def test_acepta_code128_alfanumerico(self):
        cb.validar_codigo_barras('POR-001-60X60-BEIGE')

    def test_rechaza_un_ean_con_el_dv_mal(self):
        with self.assertRaises(ValidationError) as ctx:
            cb.validar_codigo_barras('4006381333930')
        # El mensaje tiene que decir cuál era el dígito esperado: sin eso
        # nadie sabe si el problema es el código o el sistema.
        self.assertIn('1', str(ctx.exception))

    def test_rechaza_un_escaneo_cortado(self):
        with self.assertRaises(ValidationError):
            cb.validar_codigo_barras('75')

    def test_rechaza_caracteres_de_control(self):
        with self.assertRaises(ValidationError):
            cb.validar_codigo_barras('750103\x01131')


class VarianteCodigoBarrasTests(TestCase):
    """El campo en el modelo: normalización y unicidad."""

    def setUp(self):
        categoria = Categoria.objects.create(nombre='Porcelanatos')
        self.producto = Producto.objects.create(
            nombre='Porcelanato Prueba', categoria=categoria,
            precio_base=Decimal('185000'),
        )

    def _variante(self, color, codigo=''):
        return Variante.objects.create(
            producto=self.producto, color=color, codigo_barras=codigo)

    def test_se_guarda_normalizado(self):
        v = self._variante('Beige', '  7501031311309\r\n')
        v.refresh_from_db()
        self.assertEqual(v.codigo_barras, '7501031311309')

    def test_el_default_es_vacio_y_se_permite_repetido(self):
        """
        La mayoría del catálogo arranca sin código. El constraint tiene que
        ignorar los vacíos, o la segunda variante sin código no se podría
        guardar.
        """
        self._variante('Beige')
        self._variante('Gris')
        self.assertEqual(
            Variante.objects.filter(codigo_barras='').count(), 2)

    def test_no_admite_dos_variantes_con_el_mismo_codigo(self):
        self._variante('Beige', '7501031311309')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._variante('Gris', '7501031311309')

    def test_clean_avisa_de_quien_es_el_codigo(self):
        """
        El error tiene que nombrar el producto que ya lo tiene: el caso real
        es que alguien reusó una etiqueta y necesita saber de dónde salía.
        """
        self._variante('Beige', '7501031311309')
        otra = Variante(producto=self.producto, color='Gris',
                        codigo_barras='7501031311309')
        with self.assertRaises(ValidationError) as ctx:
            otra.clean()
        self.assertIn('Porcelanato Prueba', str(ctx.exception))
