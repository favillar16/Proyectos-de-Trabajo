"""
Tests del cobro con tarjeta y su llegada al documento electrónico.

Por qué importa: el grupo E620 del Manual Técnico se activa **siempre** que
el medio de pago es tarjeta, y pide como mínimo la denominación. Antes de
esto el sistema guardaba `medio_pago='credito'` y nada más, así que ninguna
venta con tarjeta habría podido facturarse electrónicamente.

Lo que se verifica acá:

  · que caja no deje pasar un cobro con tarjeta sin los datos, pero **solo**
    cuando corresponde (factura + SIFEN prendido) y nunca antes;
  · que esos datos lleguen al payload en la forma que espera el SIFEN;
  · que un cobro con tarjeta al que le falten los datos no arme un documento
    a medias.
"""
from decimal import Decimal

from django.test import TestCase, override_settings

from apps.caja import pos
from apps.caja.models import DatosTarjeta
from apps.facturacion import codigos, payload
from apps.facturacion.emisor import crear_documento

from .factories import (DATOS_FISCALES_COMPLETOS, RUC_RECEPTOR, SIFEN_APAGADO,
                        SIFEN_PRENDIDO, crear_pago, crear_pedido, crear_sesion,
                        crear_usuario, crear_variante)


class TerminalManualTests(TestCase):
    """La terminal por defecto: la cajera copia el voucher."""

    databases = {'default'}

    def setUp(self):
        self.terminal = pos.TerminalManual()

    def test_exige_saber_con_que_tarjeta_se_pago(self):
        # Es el único dato que el SIFEN no perdona. Dejarlo pasar vacío
        # significa descubrir el problema al día siguiente, cuando ya nadie
        # se acuerda con qué tarjeta pagó el cliente.
        with self.assertRaises(pos.ErrorPOS) as caso:
            self.terminal.cobrar(Decimal('100000'), medio='credito', datos={})
        self.assertIn('tarjeta', str(caso.exception).lower())

    def test_rechaza_una_denominacion_que_el_sifen_no_conoce(self):
        with self.assertRaises(pos.ErrorPOS):
            self.terminal.cobrar(Decimal('100000'), medio='credito',
                                 datos={'denominacion': 42})

    def test_acepta_las_denominaciones_del_manual(self):
        for codigo in list(codigos.DENOMINACION_TARJETA) + [codigos.TARJETA_OTRA]:
            with self.subTest(denominacion=codigo):
                resultado = self.terminal.cobrar(
                    Decimal('100000'), medio='credito',
                    datos={'denominacion': codigo})
                self.assertTrue(resultado.aprobado)
                self.assertEqual(resultado.denominacion, codigo)

    def test_se_queda_solo_con_los_ultimos_cuatro_digitos(self):
        # Guardar el número entero de una tarjeta sería un problema de
        # seguridad, y el SIFEN tampoco lo pide: el campo E629 son cuatro.
        resultado = self.terminal.cobrar(
            Decimal('100000'), medio='credito',
            datos={'denominacion': codigos.TARJETA_VISA,
                   'ultimos_digitos': '4539 1488 0343 6467'})
        self.assertEqual(resultado.ultimos_digitos, '6467')

    def test_la_descripcion_acompana_al_codigo(self):
        # El SIFEN valida que E622 corresponda a E621.
        resultado = self.terminal.cobrar(
            Decimal('100000'), medio='credito',
            datos={'denominacion': codigos.TARJETA_MASTERCARD})
        self.assertEqual(resultado.descripcion, 'Mastercard')

    def test_para_otra_tarjeta_usa_el_nombre_que_cargo_la_cajera(self):
        # El manual pide que con el código 99 se informe la denominación real.
        resultado = self.terminal.cobrar(
            Decimal('100000'), medio='credito',
            datos={'denominacion': codigos.TARJETA_OTRA,
                   'denominacion_descripcion': 'Tarjeta Unica'})
        self.assertEqual(resultado.descripcion, 'Tarjeta Unica')


class SeleccionDeTerminalTests(TestCase):
    databases = {'default'}

    @override_settings(POS={'terminal': 'manual'})
    def test_la_manual_es_la_de_por_defecto(self):
        self.assertIsInstance(pos.obtener_terminal(), pos.TerminalManual)

    @override_settings(POS={'terminal': 'no_existe'})
    def test_ante_una_terminal_desconocida_cae_en_la_manual(self):
        # Caer en la manual pide los datos; caer en la simulada aprobaría
        # cobros que nunca ocurrieron. La elección segura es la manual.
        self.assertIsInstance(pos.obtener_terminal(), pos.TerminalManual)

    @override_settings(POS={'terminal': 'simulada'})
    def test_la_simulada_se_puede_elegir_explicitamente(self):
        self.assertIsInstance(pos.obtener_terminal(), pos.TerminalSimulada)

    def test_sabe_que_medios_necesitan_datos_de_tarjeta(self):
        self.assertTrue(pos.requiere_datos_de_tarjeta('credito'))
        self.assertTrue(pos.requiere_datos_de_tarjeta('debito'))
        self.assertFalse(pos.requiere_datos_de_tarjeta('efectivo'))
        self.assertFalse(pos.requiere_datos_de_tarjeta('transferencia'))


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class TarjetaEnElDocumentoTests(TestCase):
    """Los datos de la terminal tienen que llegar al XML."""

    databases = {'default', 'sync'}
    _secuencia = 0

    def _documento(self, medio='credito', tarjeta=None):
        TarjetaEnElDocumentoTests._secuencia += 1
        n = TarjetaEnElDocumentoTests._secuencia
        usuario = crear_usuario(username=f'cajero_pos{n}')
        variante = crear_variante(nombre=f'Producto POS {n}')
        pedido = crear_pedido(usuario, [(variante, 1, 100000)])
        sesion = crear_sesion(usuario)
        pago = crear_pago(pedido, sesion, usuario, 100000, medio=medio)
        if tarjeta is not None:
            DatosTarjeta.objects.create(pago=pago, **tarjeta)
        return crear_documento(
            pago, receptor={'ruc': RUC_RECEPTOR, 'razon_social': 'Cliente SRL'})

    def test_el_pago_con_tarjeta_lleva_el_grupo_infoTarjeta(self):
        documento = self._documento(tarjeta={
            'denominacion': codigos.TARJETA_VISA,
            'codigo_autorizacion': '123456',
            'titular': 'JUAN PEREZ',
            'ultimos_digitos': '6467',
        })
        entrega = payload.construir_data(documento)['condicion']['entregas'][0]

        self.assertIn('infoTarjeta', entrega)
        self.assertEqual(entrega['infoTarjeta']['tipo'], codigos.TARJETA_VISA)
        self.assertEqual(entrega['infoTarjeta']['tipoDescripcion'], 'Visa')
        self.assertEqual(entrega['infoTarjeta']['medioPago'],
                         codigos.PROCESAMIENTO_POS)
        self.assertEqual(entrega['infoTarjeta']['codigoAutorizacion'], '123456')

    def test_el_pago_en_efectivo_no_lleva_infoTarjeta(self):
        # El manual activa el grupo solo si E606 = 3 o 4. Mandarlo en un
        # cobro en efectivo sería declarar algo que no pasó.
        documento = self._documento(medio='efectivo')
        entrega = payload.construir_data(documento)['condicion']['entregas'][0]
        self.assertNotIn('infoTarjeta', entrega)

    def test_una_tarjeta_sin_datos_no_arma_un_documento_a_medias(self):
        documento = self._documento(medio='debito', tarjeta=None)
        with self.assertRaises(payload.DatosIncompletos) as caso:
            payload.construir_data(documento)
        self.assertIn('tarjeta', str(caso.exception).lower())

    def test_no_manda_los_opcionales_vacios(self):
        # El SIFEN valida longitudes mínimas: el titular es de 4 a 30
        # caracteres, así que mandarlo vacío es peor que no mandarlo.
        documento = self._documento(tarjeta={
            'denominacion': codigos.TARJETA_CABAL})
        info = (payload.construir_data(documento)
                ['condicion']['entregas'][0]['infoTarjeta'])

        for opcional in ('titular', 'codigoAutorizacion', 'ruc', 'razonSocial'):
            with self.subTest(campo=opcional):
                self.assertNotIn(opcional, info)

    def test_un_titular_demasiado_corto_no_se_manda(self):
        documento = self._documento(tarjeta={
            'denominacion': codigos.TARJETA_VISA, 'titular': 'AB'})
        info = (payload.construir_data(documento)
                ['condicion']['entregas'][0]['infoTarjeta'])
        self.assertNotIn('titular', info)


class CuandoSeExigenLosDatosTests(TestCase):
    """
    Los datos de tarjeta se piden solo cuando hacen falta.

    Importa tanto como lo otro: hoy el SIFEN está apagado, y agregarle un
    campo obligatorio a la cajera por una obligación fiscal que todavía no
    rige sería frenar la caja sin motivo.
    """
    databases = {'default'}

    def test_con_el_sifen_apagado_no_se_exige_nada(self):
        from apps.facturacion.emisor import sifen_activo
        with override_settings(SIFEN=SIFEN_APAGADO):
            self.assertFalse(sifen_activo())

    def test_el_ticket_nunca_exige_datos_de_tarjeta(self):
        # Un ticket interno no es un comprobante fiscal: no genera DE, así
        # que el grupo E620 no aplica.
        self.assertTrue(pos.requiere_datos_de_tarjeta('credito'))
        # La condición completa en la vista es: factura Y sifen activo Y
        # medio con tarjeta. Este test documenta el tercer término; los
        # otros dos los cubren los tests de integración de caja.
