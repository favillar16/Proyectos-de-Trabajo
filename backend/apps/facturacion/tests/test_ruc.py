"""
Tests del validador de RUC.

Nota sobre qué se puede y qué no se puede probar acá: estos tests verifican
que el algoritmo sea **coherente consigo mismo** (que el DV que calcula sea
el que después valida, y que el parseo aguante las mil formas en que se
escribe un RUC en el mostrador). Lo que NO pueden probar es que el algoritmo
coincida con el del DNIT — para eso hace falta un RUC real con su DV real.

Ese contraste se hace con `python manage.py verificar_fiscal` una vez
cargado el RUC del negocio. Ver docs/facturacion_electronica.md §5.2.
"""
from django.test import SimpleTestCase

from apps.facturacion.ruc import (
    RucInvalido, calcular_dv, es_valido, formatear, separar, validar,
)


class SepararRucTests(SimpleTestCase):
    """El RUC se escribe de cualquier forma; el parseo tiene que normalizar."""

    def test_las_tres_formas_de_escribirlo_dan_lo_mismo(self):
        for texto in ('80012345-6', '800123456', '80012345 6', ' 80012345-6 '):
            with self.subTest(texto=texto):
                self.assertEqual(separar(texto), ('80012345', 6))

    def test_con_guion_respeta_lo_que_se_escribio_despues_del_guion(self):
        # Sin guión el último dígito es el DV; con guión, manda el guión.
        self.assertEqual(separar('8001234-56'), ('8001234', 5))

    def test_rechaza_vacio_y_demasiado_corto(self):
        for texto in ('', '   ', None, '5'):
            with self.subTest(texto=texto):
                with self.assertRaises(RucInvalido):
                    separar(texto)

    def test_rechaza_guion_sin_digitos_de_un_lado(self):
        for texto in ('-6', '80012345-'):
            with self.subTest(texto=texto):
                with self.assertRaises(RucInvalido):
                    separar(texto)


class CalcularDvTests(SimpleTestCase):

    def test_es_determinista(self):
        self.assertEqual(calcular_dv('80012345'), calcular_dv('80012345'))

    def test_ignora_separadores(self):
        self.assertEqual(calcular_dv('80012345'), calcular_dv('800-123.45'))

    def test_siempre_devuelve_un_solo_digito(self):
        # El módulo 11 puede dar 10, que se mapea a 0. Si alguna base
        # devolviera 10 se colaría un CDC de 45 dígitos.
        for n in range(1, 3000):
            with self.subTest(base=n):
                self.assertIn(calcular_dv(str(n)), range(10))

    def test_sin_digitos_lanza(self):
        with self.assertRaises(RucInvalido):
            calcular_dv('abc')


class CoherenciaTests(SimpleTestCase):
    """Lo que calcular_dv produce, es_valido lo tiene que aceptar."""

    def test_el_dv_calculado_siempre_valida(self):
        for n in range(1, 2000):
            base = str(n)
            ruc = f'{base}-{calcular_dv(base)}'
            with self.subTest(ruc=ruc):
                self.assertTrue(es_valido(ruc))

    def test_un_dv_equivocado_no_valida(self):
        base = '80012345'
        correcto = calcular_dv(base)
        for dv in range(10):
            if dv == correcto:
                continue
            with self.subTest(dv=dv):
                self.assertFalse(es_valido(f'{base}-{dv}'))

    def test_es_valido_no_lanza_nunca(self):
        for basura in ('', None, 'hola', '-', '999', 'ghp_token'):
            with self.subTest(basura=basura):
                self.assertFalse(es_valido(basura))


class ValidarTests(SimpleTestCase):

    def test_devuelve_base_y_dv_normalizados(self):
        base = '80012345'
        ruc = f'{base}-{calcular_dv(base)}'
        self.assertEqual(validar(ruc), (base, calcular_dv(base)))

    def test_el_mensaje_de_error_dice_cual_seria_el_correcto(self):
        # La cajera tiene que poder corregir el RUC sin llamar a nadie.
        base = '80012345'
        malo = (calcular_dv(base) + 1) % 10
        with self.assertRaises(RucInvalido) as ctx:
            validar(f'{base}-{malo}')
        self.assertIn(str(calcular_dv(base)), str(ctx.exception))


class FormatearTests(SimpleTestCase):

    def test_normaliza_a_base_guion_dv(self):
        self.assertEqual(formatear('800123456'), '80012345-6')

    def test_no_valida_el_dv(self):
        # formatear() es presentación, no validación: no debe rechazar un
        # RUC mal escrito, solo darle forma.
        self.assertEqual(formatear('80012345-9'), '80012345-9')
