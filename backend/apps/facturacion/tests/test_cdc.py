"""
Tests del CDC — Código de Control del documento electrónico.

Igual que con el RUC: acá se prueba la coherencia interna (que los 44
dígitos se armen, se descompongan y se validen entre sí). Que la
composición coincida con la del Manual Técnico vigente del DNIT es algo que
hay que contrastar contra la fuente, no se puede deducir del código.
Ver docs/facturacion_electronica.md §5.2.
"""
from datetime import date

from django.test import SimpleTestCase

from apps.facturacion import cdc as cdc_mod
from apps.facturacion import codigos
from apps.facturacion.cdc import CdcInvalido
from apps.facturacion.ruc import calcular_dv

BASE_RUC = '80012345'
RUC = f'{BASE_RUC}-{calcular_dv(BASE_RUC)}'


def _generar(**kwargs):
    datos = dict(
        ruc_emisor=RUC,
        establecimiento='1',
        punto_expedicion='1',
        numero='1',
        tipo_contribuyente=2,
        fecha_emision=date(2026, 8, 23),
    )
    datos.update(kwargs)
    return cdc_mod.generar(**datos)


class GenerarTests(SimpleTestCase):

    def test_tiene_exactamente_44_digitos(self):
        cdc = _generar()
        self.assertEqual(len(cdc), cdc_mod.LARGO_CDC)
        self.assertTrue(cdc.isdigit())

    def test_el_largo_no_depende_de_los_datos(self):
        # Un dato corto no debe descolocar las posiciones: todo va con ceros
        # a la izquierda. Si esto falla, el SIFEN rechaza todo.
        combinaciones = [
            dict(establecimiento='1', punto_expedicion='1', numero='1'),
            dict(establecimiento='999', punto_expedicion='999', numero='9999999'),
            dict(establecimiento='7', punto_expedicion='42', numero='12345'),
        ]
        for kw in combinaciones:
            with self.subTest(**kw):
                self.assertEqual(len(_generar(**kw)), cdc_mod.LARGO_CDC)

    def test_dos_llamadas_dan_cdc_distintos(self):
        # El código de seguridad es aleatorio: dos documentos con los mismos
        # datos no pueden compartir CDC.
        self.assertNotEqual(_generar(), _generar())

    def test_con_codigo_de_seguridad_fijo_es_reproducible(self):
        # Hace falta para poder recalcular el CDC de un documento ya emitido.
        uno = _generar(codigo_seguridad='123456789')
        otro = _generar(codigo_seguridad='123456789')
        self.assertEqual(uno, otro)

    def test_rechaza_ruc_con_dv_incorrecto(self):
        from apps.facturacion.ruc import RucInvalido
        malo = (calcular_dv(BASE_RUC) + 1) % 10
        with self.assertRaises(RucInvalido):
            _generar(ruc_emisor=f'{BASE_RUC}-{malo}')

    def test_rechaza_codigo_de_seguridad_de_largo_equivocado(self):
        for codigo in ('123', '1234567890', 'abcdefghi'):
            with self.subTest(codigo=codigo):
                with self.assertRaises(CdcInvalido):
                    _generar(codigo_seguridad=codigo)

    def test_rechaza_ruc_de_mas_de_8_digitos(self):
        base = '123456789'
        with self.assertRaises(CdcInvalido):
            _generar(ruc_emisor=f'{base}-{calcular_dv(base)}')


class ValidarTests(SimpleTestCase):

    def test_un_cdc_recien_generado_es_valido(self):
        self.assertTrue(cdc_mod.es_valido(_generar()))

    def test_detecta_cualquier_digito_alterado(self):
        # Es el punto del dígito verificador: un error de tipeo o de
        # transmisión no puede pasar desapercibido.
        cdc = _generar()
        for pos in range(cdc_mod.LARGO_CDC):
            alterado = cdc[:pos] + str((int(cdc[pos]) + 1) % 10) + cdc[pos + 1:]
            if alterado == cdc:
                continue
            with self.subTest(posicion=pos):
                self.assertFalse(cdc_mod.es_valido(alterado))

    def test_rechaza_largos_distintos_de_44(self):
        cdc = _generar()
        for malo in (cdc[:-1], cdc + '0', '', '123'):
            with self.subTest(largo=len(malo)):
                self.assertFalse(cdc_mod.es_valido(malo))

    def test_es_valido_no_lanza_nunca(self):
        for basura in (None, '', 'x' * 44, '  '):
            with self.subTest(basura=basura):
                self.assertFalse(cdc_mod.es_valido(basura))


class ProteccionDelDigitoVerificadorTests(SimpleTestCase):
    """
    El DV tiene que proteger todas las POSICIONES del CDC.

    Hay que distinguir dos cosas que parecen la misma y no lo son:

    1. **Posición estructuralmente ciega**: el dígito no aporta nada al
       checksum, así que *cualquier* cambio pasa desapercibido, siempre.
       Esto es un defecto y acá se encontró uno real: con el ciclo de pesos
       2..11 (el mismo de `ruc.py`), un peso de 11 anula el aporte del
       dígito (11·d ≡ 0 mod 11), y en 43 dígitos el ciclo pasa cuatro veces
       por el 11 — quedaban 8 posiciones ciegas por CDC, de forma
       determinista. Corregido bajando PESO_MAX a 9.

    2. **Colisión aislada**: para un valor puntual, dos cadenas distintas
       dan el mismo DV. Es inherente a este módulo 11, porque la regla
       "dv = 0 si resto < 2" hace que resto 0 y resto 1 den el mismo
       dígito. Ronda el 2% de los cambios de un dígito y no se puede
       eliminar sin apartarse del algoritmo. Un DV de un dígito nunca
       detecta el 100%.

    Estos tests exigen (1) y toleran (2).
    """
    # Código de seguridad fijo: si se dejara el aleatorio, el test pasaría o
    # fallaría según el CDC que tocara. Ya pasó.
    CODIGO_FIJO = '123456789'

    def _cuerpos_de_prueba(self, cantidad=40):
        return [_generar(numero=str(n + 1), codigo_seguridad=self.CODIGO_FIJO)[:-1]
                for n in range(cantidad)]

    def test_ninguna_posicion_queda_estructuralmente_ciega(self):
        for cuerpo in self._cuerpos_de_prueba():
            original = cdc_mod.calcular_dv(cuerpo)
            for pos in range(len(cuerpo)):
                no_detectados = 0
                for delta in range(1, 10):
                    alterado = (cuerpo[:pos]
                                + str((int(cuerpo[pos]) + delta) % 10)
                                + cuerpo[pos + 1:])
                    if cdc_mod.calcular_dv(alterado) == original:
                        no_detectados += 1
                self.assertLess(
                    no_detectados, 9,
                    f'La posición {pos} es ciega: los 9 cambios posibles pasan '
                    f'sin que el DV se entere. Revisar cdc.PESO_MAX — un peso '
                    f'múltiplo de 11 anula el dígito.')

    def test_la_tasa_de_colisiones_se_mantiene_baja(self):
        # Guardarraíl: si alguien toca el algoritmo y la tasa se dispara, es
        # señal de que rompió algo aunque no haya posiciones ciegas.
        total = colisiones = 0
        for cuerpo in self._cuerpos_de_prueba():
            original = cdc_mod.calcular_dv(cuerpo)
            for pos in range(len(cuerpo)):
                for delta in range(1, 10):
                    alterado = (cuerpo[:pos]
                                + str((int(cuerpo[pos]) + delta) % 10)
                                + cuerpo[pos + 1:])
                    total += 1
                    if cdc_mod.calcular_dv(alterado) == original:
                        colisiones += 1
        tasa = colisiones / total
        self.assertLess(tasa, 0.05,
                        f'La tasa de cambios no detectados subió a {tasa:.1%}; '
                        f'lo esperable con este módulo 11 es ~2%.')

    def test_el_peso_maximo_no_es_multiplo_de_11(self):
        # Guardarraíl explícito: si alguien sube PESO_MAX a 11 "para que
        # coincida con ruc.py", este test lo frena antes de que se emitan
        # documentos con CDC débiles.
        for peso in range(cdc_mod.PESO_MIN, cdc_mod.PESO_MAX + 1):
            with self.subTest(peso=peso):
                self.assertNotEqual(peso % 11, 0)


class DescomponerTests(SimpleTestCase):

    def test_devuelve_exactamente_lo_que_se_paso(self):
        cdc = _generar(establecimiento='7', punto_expedicion='42',
                       numero='12345', tipo_contribuyente=1,
                       fecha_emision=date(2026, 1, 5),
                       codigo_seguridad='987654321')
        campos = cdc_mod.descomponer(cdc)
        self.assertEqual(campos['tipo_documento'], codigos.TIPO_DE_FACTURA)
        self.assertEqual(campos['ruc_emisor'], BASE_RUC)
        self.assertEqual(campos['dv_ruc_emisor'], calcular_dv(BASE_RUC))
        self.assertEqual(campos['establecimiento'], '007')
        self.assertEqual(campos['punto_expedicion'], '042')
        self.assertEqual(campos['numero'], '0012345')
        self.assertEqual(campos['tipo_contribuyente'], 1)
        self.assertEqual(campos['fecha_emision'], '2026-01-05')
        self.assertEqual(campos['tipo_emision'], codigos.EMISION_NORMAL)
        self.assertEqual(campos['codigo_seguridad'], '987654321')

    def test_lanza_ante_un_cdc_invalido(self):
        with self.assertRaises(CdcInvalido):
            cdc_mod.descomponer('123')


class FormatearLegibleTests(SimpleTestCase):

    def test_agrupa_de_a_cuatro_sin_perder_digitos(self):
        cdc = _generar()
        legible = cdc_mod.formatear_legible(cdc)
        self.assertEqual(legible.replace(' ', ''), cdc)

    def test_entra_en_dos_lineas_de_papel_de_80mm(self):
        # El KuDE se imprime en papel térmico de 80mm (~48 caracteres). El
        # CDC no entra en una línea y hay que partirlo.
        legible = cdc_mod.formatear_legible(_generar())
        mitad = len(legible) // 2
        corte = legible.rfind(' ', 0, mitad + 3)
        self.assertNotEqual(corte, -1)
        for linea in (legible[:corte], legible[corte + 1:]):
            with self.subTest(linea=linea):
                self.assertLessEqual(len(linea), 48)


class CodigoSeguridadTests(SimpleTestCase):
    """
    Reglas del campo dCodSeg — Manual Técnico del SIFEN v150, §10.3.
    Verificadas contra el documento oficial, no deducidas.
    """

    def test_siempre_nueve_digitos(self):
        for _ in range(200):
            codigo = cdc_mod.generar_codigo_seguridad()
            self.assertEqual(len(codigo), cdc_mod.LARGO_CODIGO_SEGURIDAD)
            self.assertTrue(codigo.isdigit())

    def test_nunca_sale_del_rango_1_a_999999999(self):
        # El manual dice "rango entre 000000001 y 999999999": el cero NO es
        # válido. La primera versión usaba randbelow(10**9), que arranca en 0.
        for _ in range(20000):
            valor = int(cdc_mod.generar_codigo_seguridad())
            self.assertGreaterEqual(valor, cdc_mod.CODIGO_SEGURIDAD_MIN)
            self.assertLessEqual(valor, cdc_mod.CODIGO_SEGURIDAD_MAX)

    def test_no_puede_ser_igual_al_numero_de_documento(self):
        # "No debe ser igual al número de documento campo dNumDoc" (§10.3).
        for numero in (1, 5, 123456):
            with self.subTest(numero=numero):
                for _ in range(300):
                    codigo = cdc_mod.generar_codigo_seguridad(numero)
                    self.assertNotEqual(int(codigo), numero)

    def test_un_numero_de_documento_invalido_no_rompe(self):
        for basura in (None, '', 'abc', object()):
            with self.subTest(basura=basura):
                codigo = cdc_mod.generar_codigo_seguridad(basura)
                self.assertEqual(len(codigo), 9)

    def test_no_se_repite_seguido(self):
        codigos_generados = {cdc_mod.generar_codigo_seguridad() for _ in range(500)}
        self.assertGreater(len(codigos_generados), 490)

    def test_generar_rechaza_un_codigo_fuera_de_rango(self):
        with self.assertRaises(CdcInvalido):
            _generar(codigo_seguridad='000000000')


class ContraElManualTecnicoTests(SimpleTestCase):
    """
    Contraste contra el CDC de ejemplo publicado en el Manual Técnico del
    SIFEN v150, §10.1. Es la única forma de verificar que la composición de
    los 44 dígitos coincide con la del DNIT sin tener el documento a mano.

    El ejemplo aparece en el manual agrupado de a cuatro, tal como debe
    imprimirse en el KuDE.
    """
    CDC_OFICIAL = '0144 4444 0170 0100 1001 4528 2201 7012 5158 7326 0988'

    def setUp(self):
        self.cdc = self.CDC_OFICIAL.replace(' ', '')

    def test_el_ejemplo_oficial_tiene_44_digitos(self):
        self.assertEqual(len(self.cdc), cdc_mod.LARGO_CDC)

    def test_nuestra_composicion_lo_parsea_coherentemente(self):
        # Se parsea a mano con nuestros cortes (no con descomponer(), que
        # exige que el DV cierre: el DV del ejemplo depende del algoritmo de
        # pesos, que es justamente lo que no se pudo verificar todavía).
        self.assertEqual(self.cdc[0:2], '01', 'tipo de documento: 01 = factura')
        self.assertEqual(self.cdc[11:14], '001', 'establecimiento')
        self.assertEqual(self.cdc[14:17], '001', 'punto de expedición')
        self.assertEqual(self.cdc[24], '2', 'tipo de contribuyente')
        self.assertEqual(self.cdc[33], '1', 'tipo de emisión: normal')

    def test_la_fecha_del_ejemplo_es_una_fecha_valida(self):
        # Si nuestros cortes estuvieran corridos, acá saldría cualquier cosa.
        # Que parsee como fecha real es la mejor evidencia de que el orden
        # de los campos coincide con el del manual.
        from datetime import datetime
        fecha = datetime.strptime(self.cdc[25:33], '%Y%m%d').date()
        self.assertEqual(fecha.isoformat(), '2017-01-25')

    def test_el_codigo_de_seguridad_del_ejemplo_respeta_el_rango(self):
        valor = int(self.cdc[34:43])
        self.assertGreaterEqual(valor, cdc_mod.CODIGO_SEGURIDAD_MIN)
        self.assertLessEqual(valor, cdc_mod.CODIGO_SEGURIDAD_MAX)

    def test_el_kude_lo_muestra_agrupado_de_a_cuatro(self):
        # "debe ser expuesto en grupos de cuatro caracteres" (§10.1).
        self.assertEqual(cdc_mod.formatear_legible(self.cdc), self.CDC_OFICIAL)
