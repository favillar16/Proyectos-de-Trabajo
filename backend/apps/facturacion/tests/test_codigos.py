"""
Tests de las tablas de códigos y del desglose de IVA.

El desglose es lo más delicado de acá: el SIFEN valida que la suma de bases
e impuestos dé EXACTAMENTE el total declarado, y en guaraníes (sin
centavos) los redondeos se notan.
"""
from decimal import Decimal

from django.test import SimpleTestCase

from apps.facturacion import codigos


class TraduccionDeCodigosTests(SimpleTestCase):

    def test_cubre_todos_los_medios_de_pago_del_sistema(self):
        # Si alguien agrega un medio de pago a Pago.MEDIOS y se olvida de
        # mapearlo acá, el DE saldría declarando "efectivo" por default.
        from apps.caja.models import Pago
        for valor, _etiqueta in Pago.MEDIOS:
            with self.subTest(medio=valor):
                self.assertIn(
                    valor, codigos.MEDIO_PAGO,
                    f'El medio de pago {valor!r} existe en Pago.MEDIOS pero no '
                    f'está mapeado en codigos.MEDIO_PAGO')

    def test_medios_de_pago_conocidos(self):
        self.assertEqual(codigos.codigo_medio_pago('efectivo'), 1)
        self.assertEqual(codigos.codigo_medio_pago('credito'), 3)
        self.assertEqual(codigos.codigo_medio_pago('debito'), 4)
        self.assertEqual(codigos.codigo_medio_pago('transferencia'), 5)

    def test_medio_desconocido_cae_en_efectivo(self):
        for entrada in ('', None, 'cheque', '  '):
            with self.subTest(entrada=entrada):
                self.assertEqual(codigos.codigo_medio_pago(entrada),
                                 codigos.PAGO_EFECTIVO)

    def test_condicion_de_venta_tolera_mayusculas_y_tilde(self):
        # La caja manda 'Contado'/'Crédito' como texto de pantalla.
        self.assertEqual(codigos.codigo_condicion_venta('Contado'), 1)
        self.assertEqual(codigos.codigo_condicion_venta('contado'), 1)
        self.assertEqual(codigos.codigo_condicion_venta('Crédito'), 2)
        self.assertEqual(codigos.codigo_condicion_venta('credito'), 2)

    def test_condicion_desconocida_cae_en_contado(self):
        self.assertEqual(codigos.codigo_condicion_venta('vaya a saber'), 1)

    def test_naturaleza_del_receptor_depende_del_ruc_no_del_tipo(self):
        # Una persona física puede tener RUC, y una venta de mostrador puede
        # no identificar a nadie.
        self.assertEqual(codigos.naturaleza_receptor('80012345-6'),
                         codigos.RECEPTOR_CONTRIBUYENTE)
        for sin_ruc in ('', '   ', None):
            with self.subTest(ruc=sin_ruc):
                self.assertEqual(codigos.naturaleza_receptor(sin_ruc),
                                 codigos.RECEPTOR_NO_CONTRIBUYENTE)

    def test_tipo_de_operacion_acompana_a_la_naturaleza(self):
        self.assertEqual(codigos.tipo_operacion('80012345-6'), codigos.OPERACION_B2B)
        self.assertEqual(codigos.tipo_operacion(''), codigos.OPERACION_B2C)


class DesglosarIvaTests(SimpleTestCase):
    """En Paraguay el precio ya viene con IVA: el desglose es hacia atrás."""

    def test_casos_exactos(self):
        self.assertEqual(codigos.desglosar_iva(1_100_000, 10),
                         (Decimal('1000000'), Decimal('100000')))
        self.assertEqual(codigos.desglosar_iva(1_050_000, 5),
                         (Decimal('1000000'), Decimal('50000')))

    def test_exento_no_genera_impuesto(self):
        base, iva = codigos.desglosar_iva(500_000, 0)
        self.assertEqual(base, Decimal('500000'))
        self.assertEqual(iva, Decimal('0'))

    def test_base_mas_iva_siempre_devuelve_el_total(self):
        # La propiedad que importa: no se puede perder ni inventar un guaraní.
        for monto in range(1, 5000, 7):
            for tasa in codigos.TASAS_VALIDAS:
                with self.subTest(monto=monto, tasa=tasa):
                    base, iva = codigos.desglosar_iva(monto, tasa)
                    self.assertEqual(base + iva, Decimal(monto))

    def test_devuelve_guaranies_enteros(self):
        # El guaraní no tiene centavos; un decimal en el DE es un rechazo.
        for monto in ('333333.33', '1', '999999.99'):
            for tasa in codigos.TASAS_VALIDAS:
                with self.subTest(monto=monto, tasa=tasa):
                    base, iva = codigos.desglosar_iva(monto, tasa)
                    self.assertEqual(base, base.to_integral_value())
                    self.assertEqual(iva, iva.to_integral_value())

    def test_rechaza_tasas_que_el_sifen_no_conoce(self):
        for tasa in (7, 21, -1, 100):
            with self.subTest(tasa=tasa):
                with self.assertRaises(ValueError):
                    codigos.desglosar_iva(100_000, tasa)

    def test_monto_cero(self):
        for tasa in codigos.TASAS_VALIDAS:
            with self.subTest(tasa=tasa):
                self.assertEqual(codigos.desglosar_iva(0, tasa),
                                 (Decimal('0'), Decimal('0')))
