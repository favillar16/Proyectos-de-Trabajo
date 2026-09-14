"""
Reglas que vienen de las Notas Técnicas, no del Manual base.

El Manual Técnico V150 tiene pie de página de septiembre de 2019. La DNIT no
lo reemplaza: le publica **Notas Técnicas** encima, y al 14/09/2026 hay 27.
Varias cambian reglas que el sistema ya implementaba siguiendo el manual, y
un par cambian umbrales de negocio.

Cada test dice de qué NT sale. Si algún día aparece la NT 028 y mueve algo de
esto, el test es el que va a avisar.
"""
from decimal import Decimal

from django.test import TestCase, override_settings

from apps.facturacion import codigos, nota_credito, payload
from apps.facturacion.emisor import crear_documento

from .factories import (DATOS_FISCALES_COMPLETOS, RUC_RECEPTOR, SIFEN_PRENDIDO,
                        crear_pago, crear_pedido, crear_sesion, crear_usuario,
                        crear_variante)


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class BaseNT(TestCase):
    databases = {'default', 'sync'}
    _secuencia = 0

    def _documento(self, monto=100000, receptor=None, tipo=None):
        BaseNT._secuencia += 1
        n = BaseNT._secuencia
        usuario = crear_usuario(username=f'user_nt{n}')
        variante = crear_variante(nombre=f'Producto NT {n}')
        pedido = crear_pedido(usuario, [(variante, 1, monto)])
        sesion = crear_sesion(usuario)
        pago = crear_pago(pedido, sesion, usuario, monto)
        documento = crear_documento(
            pago,
            receptor=receptor if receptor is not None else {
                'ruc': RUC_RECEPTOR, 'razon_social': 'Cliente SRL'})
        if tipo is not None:
            documento.tipo_documento = tipo
            documento.save(update_fields=['tipo_documento'])
        return documento


class NT006TipoDeTransaccionTests(BaseNT):
    """
    NT 006: "No informar el tipo de transacción cuando C002≠1 o 4".

    La primera versión del payload lo mandaba siempre. En una nota de crédito,
    de débito o de remisión eso es rechazo — validación D011a, código 1216.
    """

    def test_la_factura_si_declara_el_tipo_de_transaccion(self):
        data = payload.construir_data(self._documento())
        self.assertEqual(data['tipoTransaccion'],
                         codigos.TRANSACCION_VENTA_MERCADERIA)

    def test_la_nota_de_credito_no_lo_declara(self):
        usuario = crear_usuario(username='admin_nt006', rol='admin')
        factura = self._documento()
        nota = nota_credito.emitir(factura, motivo=codigos.MOTIVO_DEVOLUCION,
                                   usuario=usuario)
        self.assertNotIn('tipoTransaccion', payload.construir_data(nota))

    def test_la_nota_de_remision_no_lo_declara(self):
        from datetime import date
        from apps.facturacion.models import DatosTraslado
        documento = self._documento(tipo=codigos.TIPO_DE_NOTA_REMISION)
        DatosTraslado.objects.create(
            pedido=documento.pago.pedido,
            creado_por=documento.creado_por,
            motivo=codigos.TRASLADO_POR_VENTA,
            fecha_inicio_traslado=date(2026, 9, 15),
            kilometros=10, vehiculo_matricula='ABC123',
            direccion_entrega='Calle cualquiera')
        self.assertNotIn('tipoTransaccion', payload.construir_data(documento))


class NT021y024ReceptorIdentificadoTests(BaseNT):
    """
    NT 021 y NT 024: el receptor no puede ser innominado a partir de cierto
    monto. La NT 021 lo puso en 35.000.000 (enero 2024) y la NT 024 lo bajó a
    **7.000.000** (enero 2025).

    Para este rubro no es un caso de borde: siete millones son los pisos de un
    baño. Es la NT con más impacto sobre la operación del negocio.
    """

    def test_el_umbral_es_el_de_la_nt_024(self):
        self.assertEqual(codigos.MONTO_EXIGE_IDENTIFICAR_RECEPTOR, 7_000_000)

    def test_una_venta_chica_sin_identificar_pasa(self):
        documento = self._documento(
            monto=500000, receptor={'ruc': '', 'razon_social': ''})
        cliente = payload.construir_data(documento)['cliente']
        self.assertEqual(cliente['documentoTipo'], codigos.IDENTIDAD_INNOMINADO)

    def test_una_venta_de_siete_millones_sin_identificar_no_pasa(self):
        documento = self._documento(
            monto=7_000_000, receptor={'ruc': '', 'razon_social': ''})
        with self.assertRaises(payload.DatosIncompletos) as caso:
            payload.construir_data(documento)
        self.assertIn('7.000.000', str(caso.exception))

    def test_justo_por_debajo_del_umbral_todavia_pasa(self):
        documento = self._documento(
            monto=6_999_999, receptor={'ruc': '', 'razon_social': ''})
        cliente = payload.construir_data(documento)['cliente']
        self.assertEqual(cliente['documentoTipo'], codigos.IDENTIDAD_INNOMINADO)

    def test_con_cedula_pasa_cualquier_monto(self):
        # Identificar no significa tener RUC: alcanza la cédula.
        documento = self._documento(
            monto=50_000_000,
            receptor={'ruc': '4123456', 'razon_social': 'Juan Perez'})
        cliente = payload.construir_data(documento)['cliente']
        self.assertEqual(cliente['documentoTipo'], codigos.IDENTIDAD_CEDULA_PY)


class NT023NotasSiempreIdentificadasTests(BaseNT):
    """
    NT 023: una nota de crédito, débito o remisión nunca puede ir a un
    receptor innominado, sin importar el monto (validación D208e, 1331).
    """

    def test_una_nota_de_credito_sin_receptor_no_se_arma(self):
        documento = self._documento(
            monto=100000, receptor={'ruc': '', 'razon_social': ''},
            tipo=codigos.TIPO_DE_NOTA_CREDITO)
        documento.documento_asociado_cdc = '0' * 44
        documento.motivo_nota = codigos.MOTIVO_DEVOLUCION
        documento.save()

        with self.assertRaises(payload.DatosIncompletos) as caso:
            payload.construir_data(documento)
        self.assertIn('receptor', str(caso.exception).lower())

    def test_el_monto_chico_no_la_salva(self):
        # A diferencia de la factura, acá el umbral de la NT 024 no aplica:
        # la regla es por tipo de documento.
        documento = self._documento(
            monto=1000, receptor={'ruc': '', 'razon_social': ''},
            tipo=codigos.TIPO_DE_NOTA_DEBITO)
        with self.assertRaises(payload.DatosIncompletos):
            payload.construir_data(documento)


class NT009LongitudesDeItemTests(BaseNT):
    """
    NT 009: el código interno del ítem (E701) admite 1-50 caracteres y la
    descripción (E708) llega a 2000.
    """

    def test_el_codigo_del_item_se_recorta_a_50(self):
        # Variante.sku admite 100 caracteres: el SIFEN solo 50.
        self.assertEqual(codigos.LARGO_MAX_CODIGO_ITEM, 50)
        documento = self._documento()
        item = documento.pago.pedido.items.first()
        item.variante.sku = 'X' * 100
        item.variante.save(update_fields=['sku'])

        codigo = payload.construir_data(documento)['items'][0]['codigo']
        self.assertEqual(len(codigo), 50)

    def test_la_descripcion_usa_el_tope_real_del_campo(self):
        # Recortar el nombre de un producto en un comprobante legal es peor
        # que mandarlo largo. Antes se truncaba a 120 por nada.
        self.assertEqual(codigos.LARGO_MAX_DESCRIPCION_ITEM, 2000)


class NT005y010RemisionTests(BaseNT):
    """
    NT 005: la matrícula del vehículo (E965) pasa de 6 a 6-7 caracteres.
    NT 010: los kilómetros de recorrido (E505) pasan a OBLIGATORIOS.
    """

    def test_la_matricula_admite_siete_caracteres(self):
        from apps.facturacion.models import DatosTraslado
        campo = DatosTraslado._meta.get_field('vehiculo_matricula')
        self.assertEqual(campo.max_length, 7)

    def test_los_kilometros_son_obligatorios(self):
        from datetime import date
        from django.core.exceptions import ValidationError
        from apps.facturacion.models import DatosTraslado

        usuario = crear_usuario(username='user_km')
        pedido = crear_pedido(usuario, [(crear_variante('KM'), 1, 1000)])
        traslado = DatosTraslado(
            pedido=pedido, creado_por=usuario,
            fecha_inicio_traslado=date(2026, 9, 15),
            vehiculo_matricula='ABC1234',
            direccion_entrega='Alguna calle')

        with self.assertRaises(ValidationError) as caso:
            traslado.clean()
        self.assertIn('kilometros', caso.exception.message_dict)


class NT007LeyendaDeRemisionTests(BaseNT):
    """
    NT 007: en la nota de remisión el campo de información al Fisco (B006
    dInfoFisc) es obligatorio y lleva la leyenda del art. 3 inc. 7 de la
    RG 41/2014.

    Es un texto legal. El sistema no lo inventa: lo pide por configuración y
    frena si no está.
    """

    def _remision(self):
        from datetime import date
        from apps.facturacion.models import DatosTraslado
        documento = self._documento(tipo=codigos.TIPO_DE_NOTA_REMISION)
        DatosTraslado.objects.create(
            pedido=documento.pago.pedido,
            creado_por=documento.creado_por,
            motivo=codigos.TRASLADO_POR_VENTA,
            fecha_inicio_traslado=date(2026, 9, 15),
            kilometros=10, vehiculo_matricula='ABC123',
            direccion_entrega='Calle cualquiera')
        return documento

    def test_la_leyenda_viaja_en_el_campo_del_fisco(self):
        # En xmlgen ese campo se llama 'descripcion' (verificado en el código
        # de la librería, no deducido del README).
        data = payload.construir_data(self._remision())
        self.assertEqual(data['descripcion'],
                         DATOS_FISCALES_COMPLETOS['leyenda_remision'])

    def test_sin_leyenda_configurada_no_se_arma_la_remision(self):
        documento = self._remision()
        sin_leyenda = dict(DATOS_FISCALES_COMPLETOS, leyenda_remision='')
        with override_settings(DATOS_FISCALES=sin_leyenda):
            with self.assertRaises(payload.DatosIncompletos) as caso:
                payload.construir_data(documento)
        self.assertIn('FISCAL_LEYENDA_REMISION', str(caso.exception))

    def test_la_factura_no_necesita_esa_leyenda(self):
        sin_leyenda = dict(DATOS_FISCALES_COMPLETOS, leyenda_remision='')
        documento = self._documento()
        with override_settings(DATOS_FISCALES=sin_leyenda):
            data = payload.construir_data(documento)
        self.assertNotIn('descripcion', data)


class NT013CalculoDelIvaTests(BaseNT):
    """
    NT 013 fijó la fórmula de la base gravada por ítem:

        dBasGravIVA = [100 * EA008 * E733] / [10000 + (E734 * E733)]

    con E733 = proporción gravada (%) y E734 = tasa. Con proporción 100 y tasa
    10 da `total * 10/11`, que es exactamente lo que hace `desglosar_iva()`.
    El test deja constancia de que las dos cuentas coinciden.
    """

    def test_nuestra_cuenta_coincide_con_la_formula_de_la_nt(self):
        for tasa in (codigos.TASA_10, codigos.TASA_5):
            for total in (1_100_000, 250_000, 87_431):
                with self.subTest(tasa=tasa, total=total):
                    base, _iva = codigos.desglosar_iva(total, tasa)
                    proporcion = 100
                    formula = (Decimal(100) * Decimal(total) * proporcion) / (
                        Decimal(10000) + (Decimal(tasa) * proporcion))
                    self.assertLess(abs(base - formula), payload.TOLERANCIA_CUADRE)

    def test_mandamos_la_proporcion_gravada_que_pide_la_formula(self):
        # E733: 100 = el ítem está gravado por completo.
        data = payload.construir_data(self._documento())
        self.assertEqual(data['items'][0]['ivaProporcion'], 100)
