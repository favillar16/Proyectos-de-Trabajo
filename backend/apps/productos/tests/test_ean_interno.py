"""
Tests del EAN-13 interno (apps/productos/codigo_barras.py).

Separado de test_codigo_barras.py, que prueba el campo y la búsqueda: acá se
prueba solo la aritmética de GS1, que es lo que decide si una etiqueta
impresa se puede leer o no.

El dígito verificador se contrasta contra EAN-13 **reales y publicados**, no
contra sí mismo: un test que solo verifique que `generar_ean_interno` y
`es_ean_valido` coinciden pasa igual aunque el algoritmo esté al revés, y un
código mal calculado no lo lee ningún lector.
"""
from django.test import SimpleTestCase

from apps.productos import codigo_barras as cb


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
            self.assertFalse(cb.es_ean_valido(roto), f'{roto} no debería validar')

    def test_los_pesos_arrancan_por_la_derecha(self):
        """
        El peso 3 va en el dígito de más a la derecha del cuerpo. Calcularlo
        al revés da un DV que parece plausible pero que ningún lector acepta.
        Este test falla si alguien invierte el orden.
        """
        # Para 000000000001 el algoritmo correcto da DV=7 (1 × peso 3 = 3;
        # 10 - 3 = 7). Invertido daría 9.
        self.assertEqual(cb.digito_verificador_ean('000000000001'), '7')

    def test_rechaza_largos_que_no_son_de_ean(self):
        self.assertFalse(cb.es_ean_valido('12345'))
        self.assertFalse(cb.es_ean_valido('123456789012345'))

    def test_un_sku_no_pasa_por_ean(self):
        """
        Es lo que decide la simbología de la etiqueta: si un SKU se colara
        como EAN-13, se imprimiría con la simbología equivocada y no se
        leería.
        """
        self.assertFalse(cb.es_ean_valido('POR-001-60X60'))

    def test_vacio_y_none_no_revientan(self):
        self.assertFalse(cb.es_ean_valido(''))
        self.assertFalse(cb.es_ean_valido(None))


class CodigoInternoTests(SimpleTestCase):

    def test_el_interno_es_un_ean13_valido(self):
        for numero in (0, 1, 42, 130, 999_999_999):
            codigo = cb.generar_ean_interno(numero)
            self.assertEqual(len(codigo), 13)
            self.assertTrue(cb.es_ean_valido(codigo), f'{codigo} tiene el DV mal')

    def test_usa_el_rango_reservado_de_gs1(self):
        """
        El prefijo 200-299 es el que GS1 reserva para uso interno del
        comercio. Si el generador saliera de ahí, un código interno podría
        colisionar con el EAN real de otro fabricante y la caja terminaría
        cobrando otra cosa.
        """
        codigo = cb.generar_ean_interno(7)
        self.assertTrue(codigo.startswith('200'))
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
