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

    def test_ninguna_posicion_util_pasa_desapercibida_del_todo(self):
        """
        Fuera de las cuatro posiciones ciegas, alterar un dígito se nota.

        Ojo con cómo está escrito, porque la versión obvia de este test es
        **flaky** y así estuvo hasta que lo destapó una corrida sobre un
        commit aislado. Afirmar "cambiar un dígito por +1 siempre se detecta"
        es falso: las posiciones 4, 14, 24 y 34 reciben peso 10, y un +1 ahí
        mueve el total en 10 ≡ −1 (mod 11). Si el resto valía 1 pasa a 0, y
        la regla "dv = 0 si resto < 2" devuelve el mismo dígito. Como el
        código de seguridad del CDC es aleatorio, el resto vale 1 en ~1 de
        cada 11 documentos: el test fallaba el 10% de las veces.

        Lo que sí se puede afirmar, y es lo que importa, es que la posición
        no sea ciega: que NO todas las alteraciones posibles pasen. Eso es
        determinista.
        """
        ciegas = ProteccionDelDigitoVerificadorTests.POSICIONES_CIEGAS
        cdc = _generar()
        for pos in range(cdc_mod.LARGO_CDC - 1):
            if pos in ciegas:
                continue
            detectadas = sum(
                1 for delta in range(1, 10)
                if not cdc_mod.es_valido(
                    cdc[:pos] + str((int(cdc[pos]) + delta) % 10) + cdc[pos + 1:]))
            with self.subTest(posicion=pos):
                self.assertGreaterEqual(
                    detectadas, 8,
                    f'La posición {pos} detecta solo {detectadas} de 9 '
                    f'alteraciones; lo esperable es 8 o 9 (una sola puede '
                    f'colisionar por la regla resto<2 del módulo 11).')

    def test_alterar_el_propio_digito_verificador_se_detecta(self):
        cdc = _generar()
        for delta in range(1, 10):
            alterado = cdc[:-1] + str((int(cdc[-1]) + delta) % 10)
            with self.subTest(delta=delta):
                self.assertFalse(cdc_mod.es_valido(alterado))

    def test_las_posiciones_ciegas_efectivamente_no_se_detectan(self):
        # El complemento del anterior, escrito como afirmación y no como
        # excepción: si alguna de las cuatro empezara a detectarse, el
        # algoritmo cambió y hay que revisarlo contra la DNIT.
        cdc = _generar()
        for pos in ProteccionDelDigitoVerificadorTests.POSICIONES_CIEGAS:
            alterado = cdc[:pos] + str((int(cdc[pos]) + 1) % 10) + cdc[pos + 1:]
            with self.subTest(posicion=pos):
                self.assertTrue(cdc_mod.es_valido(alterado))

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
    Qué protege y qué NO protege el DV de la DNIT.

    Hasta el 14/09/2026 esta clase exigía que ninguna posición del CDC
    quedara "ciega" (o sea, que ningún dígito pudiera alterarse sin que el DV
    cambiara), y para lograrlo el proyecto usaba PESO_MAX=9 en vez de 11.
    La exigencia era razonable como criterio de diseño y **equivocada como
    requisito**: el DV es un protocolo compartido con el SIFEN, no una
    decisión nuestra. Ver el bloque de PESO_MAX en cdc.py.

    Estos tests ahora documentan el algoritmo real en lugar de pelearse con
    él: miden la debilidad, la dejan escrita, y se aseguran de que nadie
    "arregle" el peso máximo sin darse cuenta de que eso rompe la
    interoperabilidad.
    """
    # Código de seguridad fijo: si se dejara el aleatorio, el test pasaría o
    # fallaría según el CDC que tocara. Ya pasó.
    CODIGO_FIJO = '123456789'

    def _cuerpos_de_prueba(self, cantidad=40):
        return [_generar(numero=str(n + 1), codigo_seguridad=self.CODIGO_FIJO)[:-1]
                for n in range(cantidad)]

    def _posiciones_ciegas(self, cuerpo):
        """Posiciones donde los 9 cambios posibles pasan sin alterar el DV."""
        original = cdc_mod.calcular_dv(cuerpo)
        ciegas = []
        for pos in range(len(cuerpo)):
            no_detectados = sum(
                1 for delta in range(1, 10)
                if cdc_mod.calcular_dv(
                    cuerpo[:pos] + str((int(cuerpo[pos]) + delta) % 10)
                    + cuerpo[pos + 1:]) == original)
            if no_detectados == 9:
                ciegas.append(pos)
        return ciegas

    def test_el_peso_maximo_es_el_de_la_dnit(self):
        # Es el guardarraíl central. Bajarlo "para que el DV sea más fuerte"
        # es exactamente el error que se cometió en agosto de 2026: produce
        # documentos que el SIFEN rechaza en bloque.
        self.assertEqual(
            cdc_mod.PESO_MAX, 11,
            'PESO_MAX tiene que ser 11: es lo que usan el ejemplo del Manual '
            'Técnico §10.1 y las dos librerías de referencia de la DNIT. '
            'Cualquier otro valor genera CDC que el SIFEN rechaza.')
        self.assertEqual(cdc_mod.PESO_MIN, 2)

    # Medido, no deducido. El ciclo de pesos 2..11 tiene período 10 y se
    # aplica de derecha a izquierda, así que sobre 43 dígitos el peso 11 cae
    # cuatro veces: en las posiciones 3, 13, 23 y 33 contando desde la
    # izquierda, base 0.
    POSICIONES_CIEGAS = [3, 13, 23, 33]

    def test_las_posiciones_ciegas_son_las_que_reciben_peso_11(self):
        # Propiedad del algoritmo de la DNIT, no un defecto nuestro:
        # 11·d ≡ 0 (mod 11) anula el aporte de ese dígito.
        #
        # Se deja medido a propósito, por dos motivos: documenta hasta dónde
        # llega el DV, y si algún día la DNIT corrige el algoritmo este test
        # es el que va a avisar que algo cambió.
        #
        # (La documentación de agosto de 2026 decía "8 dígitos sin
        # protección". Son 4. El error de conteo no cambia la conclusión.)
        for cuerpo in self._cuerpos_de_prueba(10):
            with self.subTest(cuerpo=cuerpo[:12] + '...'):
                self.assertEqual(self._posiciones_ciegas(cuerpo),
                                 self.POSICIONES_CIEGAS)

    def test_las_posiciones_ciegas_coinciden_con_el_ciclo_de_pesos(self):
        # La explicación, verificada aparte del efecto: se reconstruye el
        # ciclo de pesos y se comprueba que las posiciones ciegas son
        # exactamente aquellas a las que les toca un peso múltiplo de 11.
        pesos = []
        peso = cdc_mod.PESO_MIN
        for _ in range(cdc_mod.LARGO_CDC - 1):
            if peso > cdc_mod.PESO_MAX:
                peso = cdc_mod.PESO_MIN
            pesos.append(peso)
            peso += 1
        # pesos[0] es el dígito de más a la derecha; se pasa a índice
        # contando desde la izquierda.
        largo = cdc_mod.LARGO_CDC - 1
        anuladas = sorted(largo - 1 - i
                          for i, w in enumerate(pesos) if w % 11 == 0)
        self.assertEqual(anuladas, self.POSICIONES_CIEGAS)

    def test_una_posicion_ciega_cae_en_el_tipo_de_emision(self):
        # Vale saber qué queda desprotegido, no solo cuánto. La posición 33
        # es el tipo de emisión (normal / contingencia): se puede cambiar sin
        # que el DV lo note. No es algo que podamos arreglar —el SIFEN valida
        # ese campo por su cuenta—, pero sí algo que conviene no ignorar.
        cdc = _generar()
        self.assertEqual(cdc_mod.descomponer(cdc)['tipo_emision'],
                         int(cdc[33]))
        self.assertIn(33, self.POSICIONES_CIEGAS)

    def test_fuera_de_las_posiciones_ciegas_el_dv_detecta_casi_todo(self):
        # Lo que el DV sí aporta. En las 35 posiciones restantes la única
        # forma de pasar desapercibido es la colisión aislada del módulo 11
        # (la regla "dv = 0 si resto < 2" hace que resto 0 y resto 1 den el
        # mismo dígito), que ronda el 2%.
        total = colisiones = 0
        for cuerpo in self._cuerpos_de_prueba():
            ciegas = set(self._posiciones_ciegas(cuerpo))
            original = cdc_mod.calcular_dv(cuerpo)
            for pos in range(len(cuerpo)):
                if pos in ciegas:
                    continue
                for delta in range(1, 10):
                    alterado = (cuerpo[:pos]
                                + str((int(cuerpo[pos]) + delta) % 10)
                                + cuerpo[pos + 1:])
                    total += 1
                    if cdc_mod.calcular_dv(alterado) == original:
                        colisiones += 1
        tasa = colisiones / total
        self.assertLess(tasa, 0.05,
                        f'La tasa de cambios no detectados fuera de las '
                        f'posiciones ciegas subió a {tasa:.1%}; lo esperable '
                        f'con este módulo 11 es ~2%.')


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

    def test_el_dv_del_ejemplo_oficial_cierra_con_nuestro_algoritmo(self):
        """
        La prueba decisiva del módulo 11, y la que faltaba hasta el
        14/09/2026.

        El manual publica el CDC completo, DV incluido. Si nuestro cálculo
        reprodujera otro dígito, cada documento que emitamos saldría con un
        CDC que el SIFEN considera corrupto.

        Con PESO_MAX=11 da 8, que es lo que dice el manual.
        Con PESO_MAX=9 —lo que había hasta hoy— daba 2.
        """
        cuerpo, dv_publicado = self.cdc[:-1], int(self.cdc[-1])
        self.assertEqual(cdc_mod.calcular_dv(cuerpo), dv_publicado)

    def test_el_ejemplo_oficial_pasa_nuestra_validacion(self):
        # Corolario del anterior: validar() tiene que aceptar el CDC del
        # manual tal cual, sin excepciones ni tolerancias.
        self.assertTrue(cdc_mod.es_valido(self.cdc))

    def test_descomponer_lee_el_ejemplo_oficial(self):
        # Ahora que el DV cierra se puede usar descomponer(), que valida el
        # dígito antes de cortar. Es bastante más fuerte que parsear a mano:
        # comprueba composición Y checksum contra el documento oficial.
        campos = cdc_mod.descomponer(self.cdc)
        self.assertEqual(campos['tipo_documento'], codigos.TIPO_DE_FACTURA)
        self.assertEqual(campos['establecimiento'], '001')
        self.assertEqual(campos['punto_expedicion'], '001')
        self.assertEqual(campos['tipo_contribuyente'], 2)
        self.assertEqual(campos['fecha_emision'], '2017-01-25')
        self.assertEqual(campos['tipo_emision'], codigos.EMISION_NORMAL)

    def test_nuestra_composicion_lo_parsea_coherentemente(self):
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
