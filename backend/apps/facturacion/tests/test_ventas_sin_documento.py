"""
El reporte de cobros facturados que no generaron documento electrónico.

Es el punto ciego que tenía el sistema: `emitir_para_pago()` no lanza nunca y
devuelve `None` si algo falla, así que la venta se completaba, el ticket salía
sin CDC y no quedaba registro visible en ninguna pantalla — la cola de
documentos lista los `DocumentoElectronico` que existen, y uno que nunca se
creó no está.
"""
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.caja.models import Pago
from apps.facturacion import codigos
from apps.facturacion.emisor import crear_documento

from .factories import (DATOS_FISCALES_COMPLETOS, RUC_RECEPTOR, SIFEN_APAGADO,
                        SIFEN_PRENDIDO, crear_pago, crear_pedido, crear_sesion,
                        crear_usuario, crear_variante)


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class VentasSinDocumentoTests(TestCase):
    databases = {'default', 'sync'}
    _n = 0

    def setUp(self):
        self.admin = crear_usuario(username='admin_sin_de', rol='admin')
        self.api = APIClient()
        self.api.force_authenticate(self.admin)
        self.url = reverse('fe-ventas-sin-documento')

    def _cobro(self, *, tipo='factura', con_documento=False):
        VentasSinDocumentoTests._n += 1
        n = VentasSinDocumentoTests._n
        usuario = crear_usuario(username=f'caj_sd{n}', rol='cajero')
        variante = crear_variante(nombre=f'Piso SD {n}')
        pedido = crear_pedido(usuario, [(variante, 1, 100000)])
        sesion = crear_sesion(usuario)
        pago = crear_pago(pedido, sesion, usuario, 100000)
        pago.tipo_comprobante = tipo
        pago.cliente_ruc = RUC_RECEPTOR
        pago.cliente_razon_social = 'Cliente SRL'
        pago.save(update_fields=['tipo_comprobante', 'cliente_ruc',
                                 'cliente_razon_social'])
        if con_documento:
            crear_documento(pago, receptor={'ruc': RUC_RECEPTOR,
                                            'razon_social': 'Cliente SRL'})
        return pago

    def test_aparece_el_cobro_facturado_sin_documento(self):
        pago = self._cobro()
        r = self.api.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['total'], 1)
        self.assertEqual(r.data['resultados'][0]['numero_ticket'],
                         pago.numero_ticket)

    def test_el_cobro_que_si_emitio_no_aparece(self):
        self._cobro(con_documento=True)
        r = self.api.get(self.url)
        self.assertEqual(r.data['total'], 0)

    def test_un_ticket_no_cuenta(self):
        # Un ticket interno no es un comprobante fiscal: que no tenga
        # documento electrónico es lo normal, no una falta.
        self._cobro(tipo='ticket')
        r = self.api.get(self.url)
        self.assertEqual(r.data['total'], 0)

    def test_una_nota_de_credito_no_tapa_la_factura_faltante(self):
        # La nota de crédito cuelga del mismo cobro. Si el filtro mirara
        # "tiene algún documento" en vez de "tiene factura", un cobro con
        # nota y sin factura pasaría desapercibido.
        from apps.facturacion.models import DocumentoElectronico
        pago = self._cobro()
        DocumentoElectronico.objects.create(
            pago=pago, cdc='0' * 44,
            tipo_documento=codigos.TIPO_DE_NOTA_CREDITO,
            establecimiento='001', punto_expedicion='001', numero=1,
            numero_completo='001-001-0000001', codigo_seguridad='123456789',
            fecha_emision=pago.fecha, emisor_ruc='80173107-0',
            emisor_razon_social='X', receptor_razon_social='Y',
            total=Decimal('1'), creado_por=self.admin)

        r = self.api.get(self.url)
        self.assertEqual(r.data['total'], 1)

    def test_dice_si_el_sifen_esta_prendido(self):
        # Cambia el significado de la lista: apagado es "a cargar en el
        # portal", prendido es "alarma".
        r = self.api.get(self.url)
        self.assertTrue(r.data['sifen_habilitado'])

        with override_settings(SIFEN=SIFEN_APAGADO):
            r2 = self.api.get(self.url)
        self.assertFalse(r2.data['sifen_habilitado'])

    def test_solo_admin(self):
        self.api.force_authenticate(
            crear_usuario(username='caj_no_admin', rol='cajero'))
        self.assertEqual(self.api.get(self.url).status_code, 403)

    def test_filtra_por_fecha_desde(self):
        self._cobro()
        r = self.api.get(self.url, {'desde': '2099-01-01'})
        self.assertEqual(r.data['total'], 0)
