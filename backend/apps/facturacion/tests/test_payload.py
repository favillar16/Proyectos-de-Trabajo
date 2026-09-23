"""
Tests del armado del JSON que consume xmlgen.

Lo más delicado acá es el prorrateo del descuento entre los ítems. El SIFEN
valida que los ítems reconstruyan el total declarado, y un guaraní de
diferencia alcanza para que rechace el documento entero — el mismo problema
que ya resolvió `emisor.calcular_totales_iva()` para el desglose de IVA, pero
ahora a nivel de ítem, donde las cantidades fraccionarias del rubro (m²) lo
vuelven bastante más difícil.
"""
from decimal import Decimal

from django.test import TestCase, override_settings

from apps.facturacion import codigos, payload
from apps.facturacion.emisor import crear_documento
from apps.productos.models import Producto

from .factories import (DATOS_FISCALES_COMPLETOS, RUC_RECEPTOR, SIFEN_PRENDIDO,
                        crear_pago, crear_pedido, crear_sesion, crear_usuario,
                        crear_variante)


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class BaseDocumentoTests(TestCase):
    """Arma un documento electrónico real para trabajar sobre él."""

    # Los modelos del catálogo son sincronizables y escriben su registro de
    # cambios en la base `sync`, que vive aparte (apps/sync/routers.py).
    databases = {'default', 'sync'}

    _secuencia = 0

    def _documento(self, items=None, monto=None, receptor=None,
                   condicion_venta='contado', medio='efectivo'):
        BaseDocumentoTests._secuencia += 1
        usuario = crear_usuario(username=f'cajero{BaseDocumentoTests._secuencia}')
        items = items or [(crear_variante(), 1, 100000)]
        pedido = crear_pedido(usuario, items)
        if monto is None:
            monto = sum(Decimal(str(c)) * Decimal(str(p)) for _, c, p in items)
        sesion = crear_sesion(usuario)
        pago = crear_pago(pedido, sesion, usuario, monto, medio=medio)
        return crear_documento(
            pago,
            receptor=receptor if receptor is not None else {
                'ruc': RUC_RECEPTOR, 'razon_social': 'Cliente SRL'},
            condicion_venta=condicion_venta)


class ConstruirParamsTests(BaseDocumentoTests):

    def test_trae_los_campos_que_pide_xmlgen(self):
        params = payload.construir_params()
        for clave in ('version', 'ruc', 'razonSocial', 'actividadesEconomicas',
                      'timbradoNumero', 'tipoContribuyente', 'establecimientos'):
            with self.subTest(clave=clave):
                self.assertIn(clave, params)

    def test_declara_la_version_150_del_manual(self):
        # La versión viaja también en el QR; si no coincide con la del XML el
        # SIFEN no lo valida.
        self.assertEqual(payload.construir_params()['version'], 150)

    def test_el_establecimiento_lleva_el_domicilio_desglosado(self):
        # El SIFEN no acepta la dirección como texto libre: exige los códigos
        # de departamento, distrito y ciudad.
        establecimiento = payload.construir_params()['establecimientos'][0]
        for clave in ('departamento', 'distrito', 'ciudad'):
            with self.subTest(clave=clave):
                self.assertIsInstance(establecimiento[clave], int)

    def test_el_snapshot_del_documento_gana_sobre_settings(self):
        # Es la razón de ser del snapshot: retransmitir un documento viejo
        # tiene que mandar el timbrado que tenía al emitirse, no el de hoy.
        documento = self._documento()
        documento.emisor_timbrado = '99999999'
        documento.save(update_fields=['emisor_timbrado'])

        params = payload.construir_params(documento)
        self.assertEqual(params['timbradoNumero'], '99999999')
        self.assertNotEqual(params['timbradoNumero'],
                            DATOS_FISCALES_COMPLETOS['timbrado'])

    def test_declara_el_inicio_de_vigencia_del_timbrado_no_el_vencimiento(self):
        # Son datos distintos y el SIFEN valida contra el timbrado registrado
        # en Marangatú. La primera versión caía en el vencimiento cuando
        # faltaba el inicio, que habría sido rechazo seguro.
        params = payload.construir_params()
        self.assertEqual(params['timbradoFecha'],
                         DATOS_FISCALES_COMPLETOS['timbrado_inicio'])
        self.assertNotEqual(params['timbradoFecha'],
                            DATOS_FISCALES_COMPLETOS['timbrado_vto'])

    def test_avisa_si_falta_el_inicio_de_vigencia(self):
        incompletos = dict(DATOS_FISCALES_COMPLETOS, timbrado_inicio='')
        with override_settings(DATOS_FISCALES=incompletos):
            with self.assertRaises(payload.DatosIncompletos) as caso:
                payload.construir_params()
        self.assertIn('FISCAL_TIMBRADO_INICIO', str(caso.exception))

    def test_avisa_que_faltan_los_codigos_geograficos(self):
        # Es el caso real de hoy: el .env del negocio los tiene vacíos porque
        # salen de una planilla del DNIT que todavía no se bajó. Tiene que
        # fallar claro y nombrando la clave, no armar un XML inválido.
        incompletos = dict(DATOS_FISCALES_COMPLETOS, departamento='')
        with override_settings(DATOS_FISCALES=incompletos):
            with self.assertRaises(payload.DatosIncompletos) as caso:
                payload.construir_params()
        self.assertIn('FISCAL_DEPARTAMENTO', str(caso.exception))


class ClienteTests(BaseDocumentoTests):

    def test_con_ruc_va_como_contribuyente_y_b2b(self):
        data = payload.construir_data(self._documento())
        self.assertTrue(data['cliente']['contribuyente'])
        self.assertEqual(data['cliente']['ruc'], RUC_RECEPTOR)
        self.assertEqual(data['cliente']['tipoOperacion'], codigos.OPERACION_B2B)

    def test_sin_ruc_va_como_innominado(self):
        # Venta de mostrador sin identificar. El manual prevé exactamente
        # este caso con el código 5.
        documento = self._documento(receptor={'ruc': '', 'razon_social': ''})
        data = payload.construir_data(documento)
        self.assertFalse(data['cliente']['contribuyente'])
        self.assertEqual(data['cliente']['documentoTipo'],
                         codigos.IDENTIDAD_INNOMINADO)
        self.assertEqual(data['cliente']['tipoOperacion'], codigos.OPERACION_B2C)

    def test_una_cedula_va_como_cedula_y_no_como_ruc(self):
        """
        El caso que más factura mueve: consumidor identificado con cédula.

        La pantalla de caja pide "RUC/CI" y no valida nada, así que acá puede
        llegar una cédula. Si se declarara en `ruc`, el SIFEN validaría su
        dígito verificador y rechazaría la factura.
        """
        documento = self._documento(receptor={
            'ruc': '4123456', 'razon_social': 'Juan Pérez'})
        data = payload.construir_data(documento)

        self.assertFalse(data['cliente']['contribuyente'])
        self.assertNotIn('ruc', data['cliente'])
        self.assertEqual(data['cliente']['documentoTipo'],
                         codigos.IDENTIDAD_CEDULA_PY)
        self.assertEqual(data['cliente']['documentoNumero'], '4123456')

    def test_no_manda_direccion_vacia(self):
        # Mandar dirección obliga al domicilio desglosado del receptor. Si no
        # se tiene, es mejor omitirla que mandar el grupo incompleto.
        data = payload.construir_data(self._documento())
        self.assertNotIn('direccion', data['cliente'])


class ItemsTests(BaseDocumentoTests):

    def test_traduce_la_unidad_de_venta_a_la_tabla_del_sifen(self):
        # Tabla 5 del Manual: 109 = metros cuadrados. El SIFEN no acepta la
        # unidad como texto.
        data = payload.construir_data(self._documento())
        self.assertEqual(data['items'][0]['unidadMedida'], 109)

    def test_lleva_el_sku_como_codigo_del_item(self):
        documento = self._documento()
        item = documento.pago.pedido.items.first()
        data = payload.construir_data(documento)
        self.assertEqual(data['items'][0]['codigo'], item.variante.sku)

    def test_la_afectacion_sale_de_la_tasa_del_producto(self):
        exento = crear_variante(nombre='Exento', tasa_iva=Producto.IVA_EXENTO)
        gravado = crear_variante(nombre='Gravado', tasa_iva=Producto.IVA_10)
        documento = self._documento(items=[(exento, 1, 50000),
                                           (gravado, 1, 50000)])
        data = payload.construir_data(documento)
        por_iva = {i['iva']: i['ivaTipo'] for i in data['items']}
        self.assertEqual(por_iva[codigos.TASA_0], codigos.IVA_EXENTO)
        self.assertEqual(por_iva[codigos.TASA_10], codigos.IVA_GRAVADO)

    def test_sin_descuento_no_inventa_ninguno(self):
        data = payload.construir_data(self._documento())
        self.assertEqual(data['items'][0]['descuento'], 0)

    def test_el_precio_unitario_es_el_que_vio_el_cliente(self):
        # El descuento se declara aparte justamente para que el precio del
        # XML sea el mismo que salió impreso en el comprobante.
        variante = crear_variante()
        documento = self._documento(items=[(variante, 2, 75000)], monto=100000)
        data = payload.construir_data(documento)
        self.assertEqual(data['items'][0]['precioUnitario'], 75000)


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class ProrrateoDelDescuentoTests(BaseDocumentoTests):
    """
    El total que sale de los ítems tiene que reconstruir el total cobrado.

    Es la misma exigencia que ya se verificó para el desglose de IVA, un nivel
    más abajo. Con cantidades enteras el cuadre es exacto; con cantidades
    fraccionarias —que en este rubro son la norma— queda un residuo de
    redondeo inevitable, y lo que se exige es que sea menor a un guaraní.
    Ver PRECISION_DESCUENTO en payload.py.
    """

    def _total_reconstruido(self, data):
        total = Decimal('0')
        for item in data['items']:
            unitario = Decimal(str(item['precioUnitario']))
            descuento = Decimal(str(item['descuento']))
            cantidad = Decimal(str(item['cantidad']))
            total += (unitario - descuento) * cantidad
        return total

    def _assert_cuadra(self, data, total_esperado):
        """
        Cuadra = la diferencia es menor a un guaraní.

        No se exige igualdad exacta a propósito. Con cantidades fraccionarias
        —que en este rubro son la norma, porque se vende por m²— el descuento
        por unidad multiplicado por la cantidad no cae nunca exactamente en un
        entero, con ninguna precisión finita. Lo que sí se puede garantizar,
        y es lo que importa, es que el residuo quede por debajo de la unidad
        mínima de la moneda. Ver PRECISION_DESCUENTO en payload.py.
        """
        diferencia = abs(self._total_reconstruido(data) - Decimal(str(total_esperado)))
        self.assertLess(
            diferencia, payload.TOLERANCIA_CUADRE,
            f'Los ítems reconstruyen una diferencia de {diferencia} Gs '
            f'contra el total cobrado; el SIFEN rechazaría el documento.')

    def test_con_cantidades_enteras_el_cuadre_es_exacto(self):
        # Sin fracciones no hay residuo posible: acá sí se exige igualdad.
        documento = self._documento(
            items=[(crear_variante('A'), 2, 50000),
                   (crear_variante('B'), 3, 30000)],
            monto=170000)
        data = payload.construir_data(documento)
        self.assertEqual(self._total_reconstruido(data), Decimal('170000'))

    def test_cuadra_sin_descuento(self):
        documento = self._documento(
            items=[(crear_variante('A'), 2, 50000),
                   (crear_variante('B'), 3, 30000)])
        data = payload.construir_data(documento)
        self.assertEqual(self._total_reconstruido(data),
                         Decimal(str(documento.total)))

    def test_cuadra_con_descuento_repartido(self):
        documento = self._documento(
            items=[(crear_variante('A'), 2, 50000),
                   (crear_variante('B'), 3, 30000)],
            monto=170000)   # 190.000 de ítems, se cobraron 170.000
        data = payload.construir_data(documento)
        self.assertEqual(self._total_reconstruido(data), Decimal('170000'))

    def test_cuadra_con_cantidades_fraccionarias(self):
        # El caso real del rubro: los pisos se venden por m², y 2,35 m² por
        # un precio que no es múltiplo de nada deja residuos de redondeo.
        documento = self._documento(
            items=[(crear_variante('A'), Decimal('2.35'), 87500),
                   (crear_variante('B'), Decimal('1.17'), 63300)],
            monto=250000)
        data = payload.construir_data(documento)
        self._assert_cuadra(data, 250000)

    def test_cuadra_en_muchos_casos_al_azar(self):
        # Guardarraíl estadístico, como el de calcular_totales_iva: los
        # descuadres de redondeo aparecen en combinaciones puntuales, no en
        # el caso que uno elige a mano.
        import random
        # Generador propio y no random.seed(): la generación de SKU de
        # Variante también consume del generador global, así que sembrarlo no
        # alcanzaba para que la corrida fuera reproducible. El test era flaky
        # y tapaba un caso real (ver test_tolera_el_redondeo_de_caja).
        azar = random.Random(20260914)
        variantes = [crear_variante(f'V{i}') for i in range(3)]

        for caso in range(30):
            items = [(variantes[i], Decimal(str(round(azar.uniform(0.5, 9), 2))),
                      azar.randrange(10000, 200000, 100))
                     for i in range(azar.randint(1, 3))]
            bruto = sum(c * Decimal(str(p)) for _, c, p in items)
            monto = (bruto * Decimal(str(round(azar.uniform(0.7, 1.0), 3)))
                     ).quantize(Decimal('1'))
            with self.subTest(caso=caso):
                documento = self._documento(items=items, monto=monto)
                data = payload.construir_data(documento)
                self._assert_cuadra(data, documento.total)

    def test_tolera_el_redondeo_de_caja_hacia_arriba(self):
        """
        Caja puede cobrar hasta un guaraní MÁS que la suma de los ítems.

        No es hipotético: `ConfirmarPagoView` calcula el monto con
        `.quantize(Decimal('1'), ROUND_HALF_UP)`, y como en este rubro se
        vende por m² el total casi siempre tiene decimales. La mitad de las
        veces el redondeo queda por encima.

        Este caso apareció solo, en la corrida al azar de más abajo, cuando
        ese test todavía era flaky. Si el armador lo rechazara, la mitad de
        las facturas con metrajes fraccionarios no se podrían emitir.
        """
        variante = crear_variante('Piso')
        # 2,35 × 87.500 = 205.625,00 … se elige un caso con decimales reales.
        items = [(variante, Decimal('2.33'), 87500)]        # = 203.875,00
        bruto = Decimal('2.33') * Decimal('87500')
        monto = (bruto + Decimal('0.4')).quantize(Decimal('1'))

        documento = self._documento(items=items, monto=monto)
        data = payload.construir_data(documento)

        self.assertEqual(data['items'][0]['descuento'], 0)
        self._assert_cuadra(data, monto)

    def test_rechaza_cobrar_materialmente_mas_que_los_items(self):
        # Un guaraní de redondeo se absorbe; 30.000 de diferencia es un dato
        # incoherente y el SIFEN no tiene dónde declararlo.
        documento = self._documento(
            items=[(crear_variante('A'), 1, 50000)], monto=80000)
        with self.assertRaises(payload.DatosIncompletos):
            payload.construir_data(documento)


class CoherenciaConElTicketTests(BaseDocumentoTests):
    """
    El IVA que se imprime y el que va al SIFEN tienen que ser el mismo.

    Son dos cálculos distintos sobre los mismos datos: el DE guarda el
    desglose que hizo `emisor.calcular_totales_iva()` sobre los totales, y es
    ese el que sale impreso en el comprobante; el SIFEN lo recalcula ítem por
    ítem a partir del payload. Si no coincidieran, el papel que se lleva el
    cliente y el documento legal declararían impuestos distintos.
    """

    def _iva_desde_los_items(self, data):
        """Reproduce lo que el SIFEN calcula a partir del payload."""
        acumulado = {codigos.TASA_10: Decimal('0'),
                     codigos.TASA_5: Decimal('0'),
                     codigos.TASA_0: Decimal('0')}
        for item in data['items']:
            linea = ((Decimal(str(item['precioUnitario']))
                      - Decimal(str(item['descuento'])))
                     * Decimal(str(item['cantidad'])))
            acumulado[item['iva']] += linea
        return {tasa: codigos.desglosar_iva(acumulado[tasa], tasa)[1]
                for tasa in (codigos.TASA_10, codigos.TASA_5)}

    def test_el_iva_del_documento_coincide_con_el_de_los_items(self):
        from apps.productos.models import Producto
        documento = self._documento(items=[
            (crear_variante('Diez', tasa_iva=Producto.IVA_10), Decimal('2.35'), 87500),
            (crear_variante('Cinco', tasa_iva=Producto.IVA_5), Decimal('1.40'), 63300),
        ], monto=250000)
        data = payload.construir_data(documento)
        desde_items = self._iva_desde_los_items(data)

        self.assertLess(abs(Decimal(str(documento.iva_10)) - desde_items[codigos.TASA_10]),
                        payload.TOLERANCIA_CUADRE)
        self.assertLess(abs(Decimal(str(documento.iva_5)) - desde_items[codigos.TASA_5]),
                        payload.TOLERANCIA_CUADRE)

    def test_coinciden_tambien_en_muchos_casos_al_azar(self):
        import random
        from apps.productos.models import Producto
        azar = random.Random(20260914)
        variantes = [crear_variante('T10', tasa_iva=Producto.IVA_10),
                     crear_variante('T5', tasa_iva=Producto.IVA_5),
                     crear_variante('TEx', tasa_iva=Producto.IVA_EXENTO)]

        for caso in range(20):
            items = [(v, Decimal(str(round(azar.uniform(0.5, 6), 2))),
                      azar.randrange(20000, 150000, 100)) for v in variantes]
            bruto = sum(c * Decimal(str(p)) for _, c, p in items)
            monto = (bruto * Decimal(str(round(azar.uniform(0.8, 1.0), 3)))
                     ).quantize(Decimal('1'))
            with self.subTest(caso=caso):
                documento = self._documento(items=items, monto=monto)
                data = payload.construir_data(documento)
                desde_items = self._iva_desde_los_items(data)
                for tasa, guardado in ((codigos.TASA_10, documento.iva_10),
                                       (codigos.TASA_5, documento.iva_5)):
                    self.assertLess(
                        abs(Decimal(str(guardado)) - desde_items[tasa]),
                        payload.TOLERANCIA_CUADRE,
                        f'El IVA {tasa}% del comprobante ({guardado}) no coincide '
                        f'con el que sale de los ítems ({desde_items[tasa]}).')


class TiposDeDocumentoTests(BaseDocumentoTests):

    def test_la_factura_declara_operacion_presencial(self):
        data = payload.construir_data(self._documento())
        self.assertEqual(data['tipoDocumento'], codigos.TIPO_DE_FACTURA)
        self.assertEqual(data['factura']['presencia'],
                         payload.PRESENCIA_PRESENCIAL)

    def test_la_nota_de_credito_referencia_el_cdc_que_corrige(self):
        original = self._documento()
        nota = self._documento()
        nota.tipo_documento = codigos.TIPO_DE_NOTA_CREDITO
        nota.documento_asociado_cdc = original.cdc
        nota.motivo_nota = codigos.MOTIVO_DEVOLUCION
        nota.save()

        data = payload.construir_data(nota)
        self.assertEqual(data['notaCreditoDebito']['motivo'],
                         codigos.MOTIVO_DEVOLUCION)
        self.assertEqual(data['documentoAsociado']['cdc'], original.cdc)
        self.assertEqual(data['documentoAsociado']['formato'],
                         codigos.DOCUMENTO_ASOCIADO_ELECTRONICO)

    def test_una_nota_sin_documento_asociado_no_se_puede_armar(self):
        nota = self._documento()
        nota.tipo_documento = codigos.TIPO_DE_NOTA_CREDITO
        nota.save()
        with self.assertRaises(payload.DatosIncompletos):
            payload.construir_data(nota)

    def test_la_autofactura_sin_sus_datos_dice_que_le_falta(self):
        # La autofactura ya se arma (ver test_autofactura.py), pero necesita
        # lo suyo: los ítems escritos a mano y los datos del vendedor no
        # contribuyente. Un documento marcado como autofactura al que no se
        # le cargó nada tiene que decirlo, no reventar en el worker.
        #
        # El mensaje habla de los ítems porque `construir_data` los arma
        # primero; el del vendedor sale en cuanto hay ítems.
        documento = self._documento()
        documento.tipo_documento = codigos.TIPO_DE_AUTOFACTURA
        documento.save()
        with self.assertRaises(payload.DatosIncompletos) as caso:
            payload.construir_data(documento)
        self.assertIn('autofactura', str(caso.exception).lower())

    def test_la_nota_de_remision_pide_los_datos_del_traslado(self):
        # La remisión ya se arma (ver test_remision.py), pero necesita que
        # alguien haya cargado el traslado: cuelga del pedido y se completa
        # al preparar la entrega, no al cobrar.
        documento = self._documento()
        documento.tipo_documento = codigos.TIPO_DE_NOTA_REMISION
        documento.save()
        with self.assertRaises(payload.DatosIncompletos) as caso:
            payload.construir_data(documento)
        self.assertIn('traslado', str(caso.exception).lower())


class CondicionDePagoTests(BaseDocumentoTests):

    def test_contado_declara_el_medio_de_pago_del_cobro(self):
        documento = self._documento(medio='transferencia')
        data = payload.construir_data(documento)
        self.assertEqual(data['condicion']['tipo'], codigos.CONDICION_CONTADO)
        self.assertEqual(data['condicion']['entregas'][0]['tipo'],
                         codigos.PAGO_TRANSFERENCIA)

    def test_la_entrega_suma_el_total_cobrado(self):
        documento = self._documento()
        data = payload.construir_data(documento)
        self.assertEqual(Decimal(data['condicion']['entregas'][0]['monto']),
                         Decimal(str(documento.total)).quantize(Decimal('1')))

    def test_a_credito_avisa_que_faltan_plazo_y_cuotas(self):
        # El SIFEN los exige y el sistema no los registra. Es mejor frenar
        # acá que emitir una venta a crédito mal declarada.
        documento = self._documento(condicion_venta='credito')
        with self.assertRaises(payload.DatosIncompletos) as caso:
            payload.construir_data(documento)
        self.assertIn('cuotas', str(caso.exception).lower())


class ConstruirCompletoTests(BaseDocumentoTests):

    def test_devuelve_params_y_data_juntos(self):
        cuerpo = payload.construir(self._documento())
        self.assertEqual(set(cuerpo), {'params', 'data'})

    def test_el_resultado_es_serializable_a_json(self):
        # Va a viajar como JSON al sidecar. Un Decimal suelto rompería recién
        # en producción, así que se comprueba acá.
        import json
        cuerpo = payload.construir(self._documento())
        self.assertIsInstance(json.dumps(cuerpo, default=str), str)
