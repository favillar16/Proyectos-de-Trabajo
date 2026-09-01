"""
Tests de la emisión de documentos electrónicos.

La regla que más importa acá: **emitir nunca puede hacer fallar un cobro**.
Cuando se llega a este código la venta ya ocurrió, el stock ya se descontó y
el cliente está en el mostrador esperando su comprobante.
"""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.facturacion import cdc as cdc_mod
from apps.facturacion import codigos, emisor
from apps.facturacion.emisor import DatosFiscalesIncompletos
from apps.facturacion.models import DocumentoElectronico, SecuenciaComprobante
from apps.productos.models import Producto

from . import factories as f


class InterruptorTests(TestCase):
    """SIFEN_HABILITADO es lo que permite tener este código en producción."""
    # El catálogo dispara el registro de cambios del sync, que vive en su
    # propia base (ver apps/sync/routers.py). Sin declararla, Django la
    # bloquea y el signal falla en silencio.
    databases = {'default', 'sync'}


    @override_settings(SIFEN=f.SIFEN_APAGADO)
    def test_apagado_no_emite_y_no_toca_la_base(self):
        self.assertFalse(emisor.sifen_activo())
        self.assertIsNone(emisor.emitir_para_pago(None, receptor={}))
        self.assertEqual(DocumentoElectronico.objects.count(), 0)
        self.assertEqual(SecuenciaComprobante.objects.count(), 0)

    @override_settings(SIFEN=f.SIFEN_PRENDIDO)
    def test_prendido_se_activa(self):
        self.assertTrue(emisor.sifen_activo())


class ValidarConfiguracionTests(TestCase):
    # El catálogo dispara el registro de cambios del sync, que vive en su
    # propia base (ver apps/sync/routers.py). Sin declararla, Django la
    # bloquea y el signal falla en silencio.
    databases = {'default', 'sync'}


    @override_settings(DATOS_FISCALES={})
    def test_sin_datos_lanza_y_dice_cuales_faltan(self):
        with self.assertRaises(DatosFiscalesIncompletos) as ctx:
            emisor.validar_configuracion()
        mensaje = str(ctx.exception)
        for clave in ('FISCAL_RUC', 'FISCAL_TIMBRADO'):
            self.assertIn(clave, mensaje)
        # Tiene que decir cómo diagnosticar, no solo que falta algo.
        self.assertIn('verificar_fiscal', mensaje)

    @override_settings(DATOS_FISCALES=f.DATOS_FISCALES_COMPLETOS)
    def test_con_datos_completos_no_lanza(self):
        emisor.validar_configuracion()


@override_settings(DATOS_FISCALES=f.DATOS_FISCALES_COMPLETOS, SIFEN=f.SIFEN_PRENDIDO)
class CrearDocumentoTests(TestCase):
    # El catálogo dispara el registro de cambios del sync, que vive en su
    # propia base (ver apps/sync/routers.py). Sin declararla, Django la
    # bloquea y el signal falla en silencio.
    databases = {'default', 'sync'}


    def setUp(self):
        self.cajero = f.crear_usuario()
        self.variante = f.crear_variante(precio=Decimal('110000'))
        self.pedido = f.crear_pedido(self.cajero, [(self.variante, 1, '110000')])
        self.sesion = f.crear_sesion(self.cajero)
        self.pago = f.crear_pago(self.pedido, self.sesion, self.cajero, '110000')

    def _emitir(self, **kwargs):
        datos = dict(receptor={'ruc': f.RUC_RECEPTOR,
                               'razon_social': 'CONSTRUCTORA X SA'},
                     condicion_venta='Contado')
        datos.update(kwargs)
        return emisor.crear_documento(self.pago, **datos)

    def test_genera_numero_legal_y_cdc_valido(self):
        de = self._emitir()
        self.assertEqual(de.numero_completo, '001-001-0000001')
        self.assertTrue(cdc_mod.es_valido(de.cdc))
        self.assertEqual(len(de.cdc), 44)

    def test_el_cdc_codifica_los_datos_del_comprobante(self):
        de = self._emitir()
        campos = cdc_mod.descomponer(de.cdc)
        self.assertEqual(campos['ruc_emisor'], f.BASE_RUC_EMISOR)
        self.assertEqual(campos['establecimiento'], '001')
        self.assertEqual(campos['punto_expedicion'], '001')
        self.assertEqual(campos['numero'], '0000001')

    def test_queda_encolado_sin_transmitir(self):
        # El local puede estar sin internet: la emisión no espera a la red.
        de = self._emitir()
        self.assertEqual(de.estado, DocumentoElectronico.ESTADO_PENDIENTE)
        self.assertTrue(de.pendiente_de_envio)
        self.assertEqual(de.intentos_envio, 0)
        self.assertIsNone(de.ultimo_intento)

    def test_guarda_el_snapshot_fiscal_del_emisor(self):
        # Reimprimir una factura vieja tiene que sacar el timbrado que
        # estaba vigente al emitir, no el de hoy.
        de = self._emitir()
        self.assertEqual(de.emisor_timbrado, '12345678')
        self.assertEqual(de.emisor_ruc, f.RUC_EMISOR)
        self.assertEqual(de.emisor_razon_social, 'OGA PORA SRL')

    def test_un_cambio_de_timbrado_posterior_no_altera_el_de_emitido(self):
        de = self._emitir()
        nuevos = dict(f.DATOS_FISCALES_COMPLETOS, timbrado='99999999')
        with override_settings(DATOS_FISCALES=nuevos):
            de.refresh_from_db()
            self.assertEqual(de.emisor_timbrado, '12345678')

    def test_persiste_los_datos_del_receptor(self):
        de = self._emitir()
        self.assertEqual(de.receptor_ruc, f.RUC_RECEPTOR)
        self.assertEqual(de.receptor_razon_social, 'CONSTRUCTORA X SA')
        self.assertEqual(de.receptor_naturaleza, codigos.RECEPTOR_CONTRIBUYENTE)

    def test_receptor_sin_ruc_es_consumidor_final(self):
        de = self._emitir(receptor={'ruc': '', 'razon_social': ''})
        self.assertEqual(de.receptor_razon_social, 'Consumidor Final')
        self.assertEqual(de.receptor_naturaleza, codigos.RECEPTOR_NO_CONTRIBUYENTE)

    def test_traduce_medio_de_pago_y_condicion(self):
        self.pago.medio_pago = 'debito'
        self.pago.save()
        de = self._emitir(condicion_venta='Crédito')
        self.assertEqual(de.medio_pago, codigos.PAGO_TARJETA_DEBITO)
        self.assertEqual(de.condicion_venta, codigos.CONDICION_CREDITO)

    def test_un_pago_no_puede_tener_dos_documentos(self):
        from django.db import IntegrityError, transaction
        self._emitir()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._emitir()


@override_settings(DATOS_FISCALES=f.DATOS_FISCALES_COMPLETOS, SIFEN=f.SIFEN_PRENDIDO)
class DesgloseDeIvaTests(TestCase):
    """El SIFEN valida que el desglose sume exactamente el total declarado."""
    # El catálogo dispara el registro de cambios del sync, que vive en su
    # propia base (ver apps/sync/routers.py). Sin declararla, Django la
    # bloquea y el signal falla en silencio.
    databases = {'default', 'sync'}


    def setUp(self):
        self.cajero = f.crear_usuario()
        self.sesion = f.crear_sesion(self.cajero)

    def _totales(self, items, cobrado):
        pedido = f.crear_pedido(self.cajero, items)
        pago = f.crear_pago(pedido, self.sesion, self.cajero, cobrado)
        return emisor.calcular_totales_iva(pedido, pago.monto)

    def test_todo_al_10_por_ciento(self):
        v = f.crear_variante(tasa_iva=Producto.IVA_10)
        t = self._totales([(v, 1, '1100000')], '1100000')
        self.assertEqual(t['total_gravado_10'], Decimal('1000000'))
        self.assertEqual(t['iva_10'], Decimal('100000'))
        self.assertEqual(t['iva_5'], Decimal('0'))

    def test_mezcla_de_tasas(self):
        v10 = f.crear_variante('A', tasa_iva=Producto.IVA_10)
        v5 = f.crear_variante('B', tasa_iva=Producto.IVA_5)
        exento = f.crear_variante('C', tasa_iva=Producto.IVA_EXENTO)
        t = self._totales(
            [(v10, 1, '1100000'), (v5, 1, '1050000'), (exento, 1, '500000')],
            '2650000')
        self.assertEqual(t['iva_10'], Decimal('100000'))
        self.assertEqual(t['iva_5'], Decimal('50000'))
        self.assertEqual(t['total_exento'], Decimal('500000'))

    def test_el_desglose_siempre_suma_el_total_cobrado(self):
        # La propiedad crítica. Se probó con montos "feos" y descuentos que
        # no dividen bien, que es donde aparecían descuadres de 1 Gs.
        v10 = f.crear_variante('X', tasa_iva=Producto.IVA_10)
        v5 = f.crear_variante('Y', tasa_iva=Producto.IVA_5)
        casos = [
            ([(v10, 1, '333333'), (v5, 1, '333333')], '666666'),
            ([(v10, 1, '333333'), (v5, 1, '333333')], '580000'),   # con descuento
            ([(v10, 3, '99999'), (v5, 7, '11111')], '300000'),
            ([(v10, 1, '1')], '1'),
            ([(v10, 1, '999999'), (v5, 1, '7')], '888888'),
        ]
        for items, cobrado in casos:
            with self.subTest(cobrado=cobrado):
                t = self._totales(items, cobrado)
                suma = (t['total_gravado_10'] + t['iva_10']
                        + t['total_gravado_5'] + t['iva_5'] + t['total_exento'])
                self.assertEqual(suma, Decimal(cobrado))

    def test_pedido_sin_items_no_rompe(self):
        t = self._totales([], '110000')
        self.assertEqual(t['total_gravado_10'] + t['iva_10'], Decimal('110000'))


@override_settings(DATOS_FISCALES=f.DATOS_FISCALES_COMPLETOS, SIFEN=f.SIFEN_PRENDIDO)
class EmitirNoRompeElCobroTests(TestCase):
    """
    emitir_para_pago() no puede lanzar nunca: la venta ya está hecha.
    """
    # El catálogo dispara el registro de cambios del sync, que vive en su
    # propia base (ver apps/sync/routers.py). Sin declararla, Django la
    # bloquea y el signal falla en silencio.
    databases = {'default', 'sync'}


    def setUp(self):
        self.cajero = f.crear_usuario()
        self.variante = f.crear_variante()
        self.pedido = f.crear_pedido(self.cajero, [(self.variante, 1, '110000')])
        self.sesion = f.crear_sesion(self.cajero)
        self.pago = f.crear_pago(self.pedido, self.sesion, self.cajero, '110000')

    def test_camino_feliz_devuelve_el_documento(self):
        de = emisor.emitir_para_pago(
            self.pago, receptor={'ruc': f.RUC_RECEPTOR, 'razon_social': 'X SA'})
        self.assertIsNotNone(de)
        self.assertEqual(DocumentoElectronico.objects.count(), 1)

    @override_settings(DATOS_FISCALES={})
    def test_sin_datos_fiscales_devuelve_none_en_vez_de_lanzar(self):
        # assertLogs además de silenciar el traceback esperado: si el fallo
        # no quedara registrado, nadie se enteraría de que hubo una venta
        # sin documento electrónico.
        with self.assertLogs('apps.facturacion.emisor', level='ERROR') as log:
            de = emisor.emitir_para_pago(self.pago, receptor={})
        self.assertIsNone(de)
        self.assertEqual(DocumentoElectronico.objects.count(), 0)
        self.assertIn('El cobro se completó igual', str(log.output))

    def test_un_error_inesperado_no_se_propaga(self):
        with patch.object(emisor, 'crear_documento',
                          side_effect=RuntimeError('la base explotó')):
            with self.assertLogs('apps.facturacion.emisor', level='ERROR') as log:
                de = emisor.emitir_para_pago(self.pago, receptor={})
        self.assertIsNone(de)
        self.assertIn('la base explotó', str(log.output))

    def test_si_falla_no_deja_hueco_en_el_correlativo(self):
        # crear_documento es atómico: al fallar devuelve el número tomado.
        emisor.emitir_para_pago(
            self.pago, receptor={'ruc': f.RUC_RECEPTOR, 'razon_social': 'X SA'})
        secuencia = SecuenciaComprobante.objects.get()
        self.assertEqual(secuencia.ultimo_numero, 1)

        otro_pedido = f.crear_pedido(self.cajero, [(self.variante, 1, '110000')])
        otro_pago = f.crear_pago(otro_pedido, self.sesion, self.cajero, '110000')
        with patch.object(DocumentoElectronico.objects, 'create',
                          side_effect=RuntimeError('falla después de numerar')):
            with self.assertLogs('apps.facturacion.emisor', level='ERROR'):
                self.assertIsNone(emisor.emitir_para_pago(otro_pago, receptor={}))

        secuencia.refresh_from_db()
        self.assertEqual(secuencia.ultimo_numero, 1,
                         'El número tomado por un DE fallido no se devolvió')
