"""
Tests de la nota de crédito electrónica.

Lo que más importa que esté bien:

  · que la nota referencie el CDC de la factura que corrige — sin eso no
    significa nada, ni para el SIFEN ni para la contadora;
  · que lleve su propia numeración, separada de la de facturas;
  · que no se pueda emitir dos veces sobre la misma factura (sería devolver
    la mercadería dos veces);
  · que reponga el stock cuando el motivo es una devolución, y **solo**
    entonces.
"""
from decimal import Decimal

from django.test import TestCase, override_settings

from apps.facturacion import codigos, nota_credito, payload
from apps.facturacion.emisor import crear_documento
from apps.facturacion.models import DocumentoElectronico
from apps.inventario.models import MovimientoStock, Stock

from .factories import (DATOS_FISCALES_COMPLETOS, RUC_RECEPTOR, SIFEN_PRENDIDO,
                        crear_pago, crear_pedido, crear_sesion, crear_usuario,
                        crear_variante)


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class BaseNotaCreditoTests(TestCase):
    databases = {'default', 'sync'}
    _secuencia = 0

    def _factura(self, cantidad=2, precio=50000):
        BaseNotaCreditoTests._secuencia += 1
        n = BaseNotaCreditoTests._secuencia
        self.usuario = crear_usuario(username=f'admin_nc{n}', rol='admin')
        self.variante = crear_variante(nombre=f'Piso NC {n}')
        pedido = crear_pedido(self.usuario,
                              [(self.variante, cantidad, precio)])
        sesion = crear_sesion(self.usuario)
        pago = crear_pago(pedido, sesion, self.usuario,
                          Decimal(str(cantidad)) * Decimal(str(precio)))
        return crear_documento(
            pago, receptor={'ruc': RUC_RECEPTOR, 'razon_social': 'Cliente SRL'})


class EmisionTests(BaseNotaCreditoTests):

    def test_referencia_el_cdc_de_la_factura(self):
        factura = self._factura()
        nota = nota_credito.emitir(factura, motivo=codigos.MOTIVO_DEVOLUCION,
                                   usuario=self.usuario)

        self.assertEqual(nota.documento_asociado_cdc, factura.cdc)
        self.assertEqual(nota.motivo_nota, codigos.MOTIVO_DEVOLUCION)
        self.assertEqual(nota.tipo_documento, codigos.TIPO_DE_NOTA_CREDITO)

    def test_tiene_numeracion_propia_separada_de_las_facturas(self):
        # Factura 001-001-0000001 y nota 001-001-0000001 conviven: son
        # talonarios distintos. Compartir el correlativo sería un error
        # grave frente a la DNIT.
        factura = self._factura()
        nota = nota_credito.emitir(factura, motivo=codigos.MOTIVO_DEVOLUCION,
                                   usuario=self.usuario)
        self.assertEqual(nota.numero, 1)
        self.assertEqual(nota.establecimiento, factura.establecimiento)
        self.assertEqual(nota.punto_expedicion, factura.punto_expedicion)

    def test_el_cdc_de_la_nota_declara_el_tipo_5(self):
        factura = self._factura()
        nota = nota_credito.emitir(factura, motivo=codigos.MOTIVO_DEVOLUCION,
                                   usuario=self.usuario)
        self.assertEqual(nota.cdc[:2], '05')
        self.assertNotEqual(nota.cdc, factura.cdc)

    def test_copia_el_timbrado_de_la_factura_y_no_el_de_hoy(self):
        # La nota tiene que declarar el mismo timbrado con el que se emitió
        # el documento que corrige, aunque el negocio ya esté usando otro.
        factura = self._factura()
        factura.emisor_timbrado = '11111111'
        factura.save(update_fields=['emisor_timbrado'])

        nota = nota_credito.emitir(factura, motivo=codigos.MOTIVO_DEVOLUCION,
                                   usuario=self.usuario)
        self.assertEqual(nota.emisor_timbrado, '11111111')

    def test_conserva_el_receptor_y_los_totales(self):
        factura = self._factura()
        nota = nota_credito.emitir(factura, motivo=codigos.MOTIVO_DEVOLUCION,
                                   usuario=self.usuario)

        self.assertEqual(nota.receptor_ruc, factura.receptor_ruc)
        self.assertEqual(nota.total, factura.total)
        self.assertEqual(nota.iva_10, factura.iva_10)

    def test_queda_pendiente_de_transmitir(self):
        factura = self._factura()
        nota = nota_credito.emitir(factura, motivo=codigos.MOTIVO_DEVOLUCION,
                                   usuario=self.usuario)
        self.assertEqual(nota.estado, DocumentoElectronico.ESTADO_PENDIENTE)
        self.assertTrue(nota.pendiente_de_envio)

    def test_la_factura_y_la_nota_conviven_en_el_mismo_cobro(self):
        # Esto era imposible cuando la relación era OneToOne.
        factura = self._factura()
        nota = nota_credito.emitir(factura, motivo=codigos.MOTIVO_DEVOLUCION,
                                   usuario=self.usuario)
        pago = factura.pago

        self.assertEqual(pago.documentos_electronicos.count(), 2)
        self.assertEqual(pago.documento_electronico, factura)
        self.assertEqual(pago.nota_credito, nota)


class ValidacionesTests(BaseNotaCreditoTests):

    def test_no_se_puede_emitir_dos_veces_sobre_la_misma_factura(self):
        # Sería devolver la mercadería dos veces.
        factura = self._factura()
        nota_credito.emitir(factura, motivo=codigos.MOTIVO_DEVOLUCION,
                            usuario=self.usuario)

        with self.assertRaises(nota_credito.NotaCreditoInvalida) as caso:
            nota_credito.emitir(factura, motivo=codigos.MOTIVO_DEVOLUCION,
                                usuario=self.usuario)
        self.assertIn('ya tiene la nota', str(caso.exception))

    def test_no_se_emite_sobre_una_factura_rechazada(self):
        # Una factura rechazada no existe como documento tributario: no hay
        # nada que anular.
        factura = self._factura()
        factura.estado = DocumentoElectronico.ESTADO_RECHAZADO
        factura.save(update_fields=['estado'])

        with self.assertRaises(nota_credito.NotaCreditoInvalida) as caso:
            nota_credito.emitir(factura, motivo=codigos.MOTIVO_DEVOLUCION,
                                usuario=self.usuario)
        self.assertIn('rechazada', str(caso.exception))

    def test_no_se_emite_sobre_otra_nota_de_credito(self):
        factura = self._factura()
        nota = nota_credito.emitir(factura, motivo=codigos.MOTIVO_DEVOLUCION,
                                   usuario=self.usuario)
        with self.assertRaises(nota_credito.NotaCreditoInvalida):
            nota_credito.emitir(nota, motivo=codigos.MOTIVO_DEVOLUCION,
                                usuario=self.usuario)

    def test_rechaza_un_motivo_que_el_sifen_no_conoce(self):
        factura = self._factura()
        with self.assertRaises(nota_credito.NotaCreditoInvalida):
            nota_credito.emitir(factura, motivo=77, usuario=self.usuario)

    def test_no_deja_hueco_en_el_correlativo_si_algo_falla(self):
        # Mismo cuidado que en la emisión de facturas: el número se toma
        # dentro de la transacción, así que un fallo lo devuelve.
        from apps.facturacion.models import SecuenciaComprobante
        factura = self._factura()

        with self.assertRaises(nota_credito.NotaCreditoInvalida):
            nota_credito.emitir(factura, motivo=999, usuario=self.usuario)

        self.assertFalse(SecuenciaComprobante.objects.filter(
            tipo_documento=codigos.TIPO_DE_NOTA_CREDITO,
            ultimo_numero__gt=0).exists())


class ReposicionDeStockTests(BaseNotaCreditoTests):

    def _stock(self):
        return Stock.objects.get(variante=self.variante)

    def test_una_devolucion_repone_el_stock(self):
        factura = self._factura(cantidad=3)
        stock = self._stock()
        stock.registrar_movimiento(
            MovimientoStock.TIPO_ENTRADA, Decimal('10'), self.usuario)
        antes = self._stock().cantidad

        nota_credito.emitir(factura, motivo=codigos.MOTIVO_DEVOLUCION,
                            usuario=self.usuario)

        self.assertEqual(self._stock().cantidad, antes + Decimal('3'))

    def test_un_descuento_posterior_no_repone_nada(self):
        # La mercadería no volvió: reponerla inventaría existencias que no
        # están en el depósito.
        factura = self._factura(cantidad=3)
        stock = self._stock()
        stock.registrar_movimiento(
            MovimientoStock.TIPO_ENTRADA, Decimal('10'), self.usuario)
        antes = self._stock().cantidad

        nota_credito.emitir(factura, motivo=codigos.MOTIVO_DESCUENTO,
                            usuario=self.usuario)

        self.assertEqual(self._stock().cantidad, antes)

    def test_se_puede_forzar_a_no_reponer(self):
        # Caso real: mercadería devuelta rota. Vuelve la plata, no el stock
        # vendible.
        factura = self._factura(cantidad=3)
        stock = self._stock()
        stock.registrar_movimiento(
            MovimientoStock.TIPO_ENTRADA, Decimal('10'), self.usuario)
        antes = self._stock().cantidad

        nota_credito.emitir(factura, motivo=codigos.MOTIVO_DEVOLUCION,
                            usuario=self.usuario, reponer_stock=False)

        self.assertEqual(self._stock().cantidad, antes)

    def test_la_reposicion_deja_su_movimiento_de_auditoria(self):
        # Regla del proyecto: nunca tocar Stock.cantidad sin el
        # MovimientoStock que lo explica.
        factura = self._factura(cantidad=3)
        nota = nota_credito.emitir(factura, motivo=codigos.MOTIVO_DEVOLUCION,
                                   usuario=self.usuario)

        movimiento = MovimientoStock.objects.filter(
            variante=self.variante,
            tipo=MovimientoStock.TIPO_DEVOLUCION).first()
        self.assertIsNotNone(movimiento)
        self.assertEqual(movimiento.referencia_id, nota.pk)
        self.assertIn(nota.numero_completo, movimiento.observaciones)


class PayloadDeLaNotaTests(BaseNotaCreditoTests):

    def test_el_payload_lleva_el_grupo_de_nota_y_el_documento_asociado(self):
        factura = self._factura()
        nota = nota_credito.emitir(factura, motivo=codigos.MOTIVO_DEVOLUCION,
                                   usuario=self.usuario)

        data = payload.construir_data(nota)
        self.assertEqual(data['tipoDocumento'], codigos.TIPO_DE_NOTA_CREDITO)
        self.assertEqual(data['notaCreditoDebito']['motivo'],
                         codigos.MOTIVO_DEVOLUCION)
        self.assertEqual(data['documentoAsociado']['cdc'], factura.cdc)
        self.assertEqual(data['documentoAsociado']['formato'],
                         codigos.DOCUMENTO_ASOCIADO_ELECTRONICO)

    def test_la_nota_no_declara_el_grupo_de_factura(self):
        factura = self._factura()
        nota = nota_credito.emitir(factura, motivo=codigos.MOTIVO_DEVOLUCION,
                                   usuario=self.usuario)
        data = payload.construir_data(nota)
        self.assertNotIn('factura', data)
