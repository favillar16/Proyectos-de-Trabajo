"""
Tests de la integración entre caja y facturación electrónica.

Cubren el punto de unión: qué sale impreso, con qué número, y —sobre todo—
que con el SIFEN apagado el comportamiento sea **idéntico** al que el
negocio tiene hoy. Ese último punto es el que permite dejar todo este código
en producción antes de tener certificado y habilitación.
"""
from decimal import Decimal

from django.test import TestCase, override_settings

from apps.caja.printer import FacturaBuilder, TicketBuilder
from apps.caja.views import _datos_ticket
from apps.facturacion import emisor

from . import factories as f


class BaseCaja(TestCase):
    def setUp(self):
        self.cajero = f.crear_usuario()
        self.variante = f.crear_variante(precio=Decimal('110000'))
        self.pedido = f.crear_pedido(self.cajero, [(self.variante, 1, '110000')])
        self.sesion = f.crear_sesion(self.cajero)
        self.pago = f.crear_pago(self.pedido, self.sesion, self.cajero, '110000')

    def datos(self, **kwargs):
        base = dict(tipo_comprobante='factura', cliente_ruc=f.RUC_RECEPTOR,
                    cliente_razon_social='CONSTRUCTORA X SA')
        base.update(kwargs)
        return _datos_ticket(self.pedido, self.pago, self.sesion, **base)


@override_settings(SIFEN=f.SIFEN_APAGADO)
class SifenApagadoTests(BaseCaja):
    """Con el interruptor apagado nada puede cambiar respecto de hoy."""

    def test_no_se_emite_documento(self):
        self.assertIsNone(emisor.emitir_para_pago(
            self.pago, receptor={'ruc': f.RUC_RECEPTOR, 'razon_social': 'X'}))

    def test_la_factura_usa_el_numero_de_ticket_interno(self):
        d = self.datos()
        self.assertEqual(d['factura_numero'], self.pago.numero_ticket)
        self.assertTrue(d['factura_numero'].startswith('T-'))

    def test_la_factura_no_lleva_cdc(self):
        d = self.datos()
        self.assertIsNone(d.get('cdc'))

    def test_la_factura_sigue_imprimiendo(self):
        papel = FacturaBuilder(self.datos()).build()
        self.assertGreater(len(papel), 0)
        self.assertIn(b'No es una factura electr', papel,
                      'Debe avisar que no es una factura electrónica válida')
        self.assertNotIn(b'CDC:', papel)

    def test_la_factura_sin_documento_no_lleva_timbrado_ni_se_dice_legal(self):
        """
        Regresión: con SIFEN apagado no puede haber un DocumentoElectronico,
        así que este papel no puede imprimir el timbrado real de la DNIT ni
        decir "COMPROBANTE LEGAL" — ese timbrado es del portal, no de esta PC.
        Antes de esta corrección el papel llegaba a mostrar el timbrado real
        en la cabecera y "no válido" en el pie, contradiciéndose.
        """
        d = self.datos()
        self.assertFalse(d.get('timbrado'))
        papel = FacturaBuilder(d).build()
        self.assertNotIn(b'COMPROBANTE LEGAL', papel)
        self.assertNotIn(b'Timbrado N:', papel)
        self.assertIn(b'COMPROBANTE DE VENTA', papel)

    def test_el_ticket_sigue_imprimiendo(self):
        d = _datos_ticket(self.pedido, self.pago, self.sesion)
        self.assertGreater(len(TicketBuilder(d).build()), 0)
        self.assertIsNone(d.get('cdc'))


@override_settings(DATOS_FISCALES=f.DATOS_FISCALES_COMPLETOS, SIFEN=f.SIFEN_PRENDIDO)
class SifenPrendidoTests(BaseCaja):

    def setUp(self):
        super().setUp()
        self.de = emisor.emitir_para_pago(
            self.pago,
            receptor={'ruc': f.RUC_RECEPTOR, 'razon_social': 'CONSTRUCTORA X SA'},
            condicion_venta='Contado')
        self.assertIsNotNone(self.de)

    def test_el_papel_lleva_el_numero_legal_no_el_ticket_interno(self):
        d = self.datos(documento=self.de)
        self.assertEqual(d['factura_numero'], '001-001-0000001')
        self.assertNotEqual(d['factura_numero'], self.pago.numero_ticket)

    def test_los_datos_fiscales_salen_del_snapshot(self):
        d = self.datos(documento=self.de)
        self.assertEqual(d['timbrado'], '12345678')
        self.assertEqual(d['ruc_negocio'], f.RUC_EMISOR)

    def test_el_desglose_de_iva_sale_del_documento(self):
        # No del cálculo global viejo (total/11), que no sirve para un DE.
        d = self.datos(documento=self.de)
        self.assertEqual(Decimal(str(d['iva_10'])), self.de.iva_10)
        self.assertEqual(Decimal(str(d['iva_5'])), self.de.iva_5)

    def test_el_papel_es_un_kude_con_cdc_y_portal(self):
        papel = FacturaBuilder(self.datos(documento=self.de)).build()
        self.assertIn(b'CDC:', papel)
        self.assertIn(b'ekuatia', papel)
        self.assertNotIn(b'Documento no', papel,
                         'Con CDC ya no corresponde la leyenda de "no válido"')

    def test_el_cdc_del_papel_es_el_del_documento(self):
        d = self.datos(documento=self.de)
        self.assertEqual(d['cdc'], self.de.cdc)
        self.assertEqual(d['cdc_legible'].replace(' ', ''), self.de.cdc)

    def test_el_ticket_nunca_lleva_cdc_aunque_haya_documento(self):
        d = _datos_ticket(self.pedido, self.pago, self.sesion,
                          tipo_comprobante='ticket', documento=self.de)
        self.assertIsNone(d.get('cdc'))


@override_settings(DATOS_FISCALES=f.DATOS_FISCALES_COMPLETOS, SIFEN=f.SIFEN_PRENDIDO)
class ReimpresionTests(BaseCaja):
    """
    Reimprimir un pago facturado tiene que sacar la FACTURA, no un ticket:
    un ticket no tiene valor fiscal y el cliente pidió copia de su factura.
    """

    def test_un_pago_sin_documento_no_expone_el_accessor(self):
        # De esto depende la lógica de ReimprimirTicketView. Django hace que
        # RelatedObjectDoesNotExist herede de AttributeError justamente para
        # que getattr con default funcione.
        self.assertIsNone(getattr(self.pago, 'documento_electronico', None))

    def test_un_pago_con_documento_lo_expone(self):
        de = emisor.emitir_para_pago(
            self.pago, receptor={'ruc': f.RUC_RECEPTOR, 'razon_social': 'X SA'})
        self.pago.refresh_from_db()
        self.assertEqual(getattr(self.pago, 'documento_electronico', None), de)

    def test_select_related_no_rompe_cuando_no_hay_documento(self):
        # Es el caso de TODOS los pagos mientras el SIFEN esté apagado.
        from apps.caja.models import Pago
        pago = (Pago.objects
                .select_related('pedido', 'cajero', 'sesion_caja',
                                'documento_electronico')
                .get(pk=self.pago.pk))
        self.assertIsNone(getattr(pago, 'documento_electronico', None))

    def test_la_reimpresion_conserva_numero_y_timbrado_originales(self):
        de = emisor.emitir_para_pago(
            self.pago,
            receptor={'ruc': f.RUC_RECEPTOR, 'razon_social': 'CONSTRUCTORA X SA'})
        self.pago.refresh_from_db()

        # Replica lo que hace ReimprimirTicketView con un pago facturado.
        d = _datos_ticket(self.pago.pedido, self.pago, self.pago.sesion_caja,
                          tipo_comprobante='factura',
                          cliente_ruc=de.receptor_ruc,
                          cliente_razon_social=de.receptor_razon_social,
                          documento=de)
        self.assertEqual(d['factura_numero'], de.numero_completo)
        self.assertEqual(d['timbrado'], de.emisor_timbrado)
        self.assertIn(b'CDC:', FacturaBuilder(d).build())


@override_settings(SIFEN=f.SIFEN_APAGADO)
class DatosFacturaPersistidosTests(TestCase):
    """
    Antes de esto, cobrar como factura no dejaba rastro del RUC en el Pago:
    vivía de paso en la request (ConfirmarPago) y se perdía apenas se
    imprimía el papel. Sin eso, reimprimir un pago viejo salía siempre como
    ticket liso —perdiendo el valor de factura— y no había forma de buscar
    cobros por RUC. Estos tests pegan contra la API real (no contra
    _datos_ticket directo) para cubrir el camino completo: registrar el
    pago, listarlo/buscarlo, y reimprimirlo.
    """

    def setUp(self):
        from rest_framework.test import APIClient

        self.cajero = f.crear_usuario()
        self.variante = f.crear_variante(precio=Decimal('110000'))
        self.variante.stock.cantidad = Decimal('10')
        self.variante.stock.save(update_fields=['cantidad'])
        self.pedido = f.crear_pedido(self.cajero, [(self.variante, 1, '110000')])
        self.sesion = f.crear_sesion(self.cajero)
        self.client = APIClient()
        self.client.force_authenticate(self.cajero)

    def _cobrar_como_factura(self):
        return self.client.post('/api/v1/caja/pagos/', {
            'pedido_id':            self.pedido.id,
            'medio_pago':           'efectivo',
            'monto_recibido':       '110000',
            'tipo_comprobante':     'factura',
            'cliente_ruc':          f.RUC_RECEPTOR,
            'cliente_razon_social': 'CONSTRUCTORA X SA',
            'condicion_venta':      'Contado',
        }, format='json')

    def test_el_pago_guarda_el_ruc_y_el_tipo_de_comprobante(self):
        from apps.caja.models import Pago
        resp = self._cobrar_como_factura()
        self.assertEqual(resp.status_code, 201, resp.data)
        pago = Pago.objects.get(pedido=self.pedido)
        self.assertEqual(pago.tipo_comprobante, Pago.COMPROBANTE_FACTURA)
        self.assertEqual(pago.cliente_ruc, f.RUC_RECEPTOR)
        self.assertEqual(pago.cliente_razon_social, 'CONSTRUCTORA X SA')

    def test_un_ticket_normal_no_guarda_ruc(self):
        from apps.caja.models import Pago
        resp = self.client.post('/api/v1/caja/pagos/', {
            'pedido_id':      self.pedido.id,
            'medio_pago':     'efectivo',
            'monto_recibido': '110000',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        pago = Pago.objects.get(pedido=self.pedido)
        self.assertEqual(pago.tipo_comprobante, Pago.COMPROBANTE_TICKET)
        self.assertEqual(pago.cliente_ruc, '')

    def test_la_lista_de_pagos_se_puede_filtrar_por_ruc(self):
        self._cobrar_como_factura()
        resp = self.client.get('/api/v1/caja/pagos/lista/', {
            'sesion': self.sesion.id, 'ruc': f.RUC_RECEPTOR[:6],
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 1)
        self.assertEqual(resp.data['results'][0]['cliente_ruc'], f.RUC_RECEPTOR)

    def test_un_ruc_que_no_coincide_no_devuelve_nada(self):
        self._cobrar_como_factura()
        resp = self.client.get('/api/v1/caja/pagos/lista/', {
            'sesion': self.sesion.id, 'ruc': '99999999',
        })
        self.assertEqual(resp.data['count'], 0)

    def test_reimprimir_un_pago_facturado_sin_documento_sigue_siendo_factura(self):
        """
        Regresión: antes de persistir estos datos en el Pago, reimprimir un
        pago cobrado como factura (sin DE real detrás, el caso de hoy con
        SIFEN apagado) volvía a salir como 'ticket' liso, sin RUC ni razón
        social en el papel reimpreso.
        """
        from apps.caja.models import Pago
        self._cobrar_como_factura()
        pago = Pago.objects.get(pedido=self.pedido)

        resp = self.client.post(f'/api/v1/caja/pagos/{pago.id}/reimprimir/')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['tipo_comprobante'], 'factura')
        self.assertEqual(resp.data['ticket']['cliente_ruc'], f.RUC_RECEPTOR)
        self.assertEqual(resp.data['ticket']['cliente_razon_social'], 'CONSTRUCTORA X SA')

    def test_reimprimir_un_ticket_normal_sigue_siendo_ticket(self):
        from apps.caja.models import Pago
        self.client.post('/api/v1/caja/pagos/', {
            'pedido_id':      self.pedido.id,
            'medio_pago':     'efectivo',
            'monto_recibido': '110000',
        }, format='json')
        pago = Pago.objects.get(pedido=self.pedido)

        resp = self.client.post(f'/api/v1/caja/pagos/{pago.id}/reimprimir/')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['tipo_comprobante'], 'ticket')
