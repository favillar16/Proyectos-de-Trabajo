"""
Tests del camino asincrónico (lotes) y de los web services que faltaban.

Lo que hace distinto al lote es que **el SIFEN no contesta si aprobó**:
contesta un número y procesa después. Son dos viajes, y entre uno y otro el
sistema tiene que guardar ese número — si se pierde, los documentos quedan
transmitidos y sin forma de saber qué pasó con ellos.

Acá no se toca la red: se reemplazan las funciones del cliente por dobles.
Lo que se prueba es el flujo, que es lo que el sidecar no puede probar.
"""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.facturacion import codigos, transmision
from apps.facturacion.emisor import crear_documento
from apps.facturacion.models import DocumentoElectronico, LoteTransmision

from .factories import (DATOS_FISCALES_COMPLETOS, RUC_RECEPTOR, SIFEN_PRENDIDO,
                        crear_pago, crear_pedido, crear_sesion, crear_usuario,
                        crear_variante)


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class LoteTests(TestCase):
    databases = {'default', 'sync'}
    _n = 0

    def _documento(self):
        LoteTests._n += 1
        n = LoteTests._n
        usuario = crear_usuario(username=f'caj_lote{n}', rol='cajero')
        variante = crear_variante(nombre=f'Piso LOTE {n}')
        pedido = crear_pedido(usuario, [(variante, 1, 100000)])
        sesion = crear_sesion(usuario)
        pago = crear_pago(pedido, sesion, usuario, 100000)
        return crear_documento(pago, receptor={'ruc': RUC_RECEPTOR,
                                               'razon_social': 'Cliente SRL'})

    def setUp(self):
        self.admin = crear_usuario(username='admin_lote', rol='admin')

    def _firmado(self, documento):
        """Doble de `_firmar`: deja el XML como si se hubiera firmado."""
        documento.xml_firmado = f'<xml>{documento.cdc}</xml>'
        documento.estado = DocumentoElectronico.ESTADO_FIRMADO
        documento.save(update_fields=['xml_firmado', 'estado'])
        return documento.xml_firmado

    def test_guarda_el_numero_de_lote(self):
        # Lo primero que hay que no perder: sin el número no se puede volver
        # a preguntar por el resultado.
        doc = self._documento()
        with patch.object(transmision, '_firmar', side_effect=self._firmado), \
             patch.object(transmision.sifen_client, 'enviar_lote',
                          return_value={'lote': '778899', 'codigo': '0300',
                                        'mensaje': 'Lote recibido',
                                        'respuesta': '{}'}):
            lote = transmision.transmitir_lote([doc], usuario=self.admin)

        self.assertEqual(lote.numero, '778899')
        self.assertEqual(lote.cantidad, 1)
        self.assertEqual(lote.estado, LoteTransmision.ESTADO_ENVIADO)

    def test_los_documentos_quedan_enviados_y_apuntando_al_lote(self):
        doc = self._documento()
        with patch.object(transmision, '_firmar', side_effect=self._firmado), \
             patch.object(transmision.sifen_client, 'enviar_lote',
                          return_value={'lote': '1', 'codigo': '', 'mensaje': '',
                                        'respuesta': '{}'}):
            lote = transmision.transmitir_lote([doc], usuario=self.admin)

        doc.refresh_from_db()
        self.assertEqual(doc.estado, DocumentoElectronico.ESTADO_ENVIADO)
        self.assertEqual(doc.lote_id, lote.pk)

    def test_un_documento_roto_no_frena_al_lote(self):
        # Lo contrario haría que un dato mal cargado en una venta dejara sin
        # transmitir a las otras cuarenta y nueve.
        bueno, malo = self._documento(), self._documento()

        def firmar(documento):
            if documento.pk == malo.pk:
                raise transmision.payload_mod.DatosIncompletos('falta algo')
            return self._firmado(documento)

        with patch.object(transmision, '_firmar', side_effect=firmar), \
             patch.object(transmision.sifen_client, 'enviar_lote',
                          return_value={'lote': '55', 'codigo': '', 'mensaje': '',
                                        'respuesta': '{}'}):
            lote = transmision.transmitir_lote([bueno, malo], usuario=self.admin)

        self.assertEqual(lote.cantidad, 1)
        malo.refresh_from_db()
        self.assertEqual(malo.estado, DocumentoElectronico.ESTADO_RECHAZADO)
        bueno.refresh_from_db()
        self.assertEqual(bueno.estado, DocumentoElectronico.ESTADO_ENVIADO)

    def test_el_resultado_se_reparte_por_cdc(self):
        # El SIFEN no garantiza devolver los resultados en el orden del
        # envío: se indexa por CDC, que es lo único que identifica al
        # documento de los dos lados.
        uno, dos = self._documento(), self._documento()
        with patch.object(transmision, '_firmar', side_effect=self._firmado), \
             patch.object(transmision.sifen_client, 'enviar_lote',
                          return_value={'lote': '90', 'codigo': '', 'mensaje': '',
                                        'respuesta': '{}'}):
            lote = transmision.transmitir_lote([uno, dos], usuario=self.admin)

        # A propósito al revés del orden de envío.
        respuesta = {'codigo': '0400', 'mensaje': '', 'respuesta': '{}',
                     'documentos': [
                         {'cdc': dos.cdc, 'estado': 'rechazado',
                          'codigo': '0160', 'mensaje': 'CDC duplicado'},
                         {'cdc': uno.cdc, 'estado': 'aprobado',
                          'codigo': '0260', 'mensaje': 'Aprobado'},
                     ]}
        with patch.object(transmision.sifen_client, 'consultar_lote',
                          return_value=respuesta):
            resumen = transmision.consultar_lote(lote)

        uno.refresh_from_db()
        dos.refresh_from_db()
        self.assertEqual(uno.estado, DocumentoElectronico.ESTADO_APROBADO)
        self.assertEqual(dos.estado, DocumentoElectronico.ESTADO_RECHAZADO)
        self.assertEqual(resumen['resueltos'], 2)

    def test_el_aprobado_por_lote_guarda_la_fecha_de_aprobacion(self):
        # Desde ahí corre el plazo para cancelar. Si el camino de lote no la
        # guardara, un documento aprobado por lote no se podría cancelar.
        doc = self._documento()
        with patch.object(transmision, '_firmar', side_effect=self._firmado), \
             patch.object(transmision.sifen_client, 'enviar_lote',
                          return_value={'lote': '7', 'codigo': '', 'mensaje': '',
                                        'respuesta': '{}'}):
            lote = transmision.transmitir_lote([doc], usuario=self.admin)

        with patch.object(transmision.sifen_client, 'consultar_lote',
                          return_value={'documentos': [
                              {'cdc': doc.cdc, 'estado': 'aprobado',
                               'codigo': '0260', 'mensaje': 'ok'}]}):
            transmision.consultar_lote(lote)

        doc.refresh_from_db()
        self.assertIsNotNone(doc.fecha_aprobacion)

    def test_si_el_sifen_todavia_procesa_no_es_error(self):
        # Es el flujo normal del asincrónico: se vuelve a preguntar después.
        doc = self._documento()
        with patch.object(transmision, '_firmar', side_effect=self._firmado), \
             patch.object(transmision.sifen_client, 'enviar_lote',
                          return_value={'lote': '3', 'codigo': '', 'mensaje': '',
                                        'respuesta': '{}'}):
            lote = transmision.transmitir_lote([doc], usuario=self.admin)

        with patch.object(transmision.sifen_client, 'consultar_lote',
                          return_value={'documentos': [], 'codigo': '0300'}):
            resumen = transmision.consultar_lote(lote)

        lote.refresh_from_db()
        self.assertEqual(lote.estado, LoteTransmision.ESTADO_ENVIADO)
        self.assertEqual(resumen['resueltos'], 0)
        self.assertEqual(lote.consultas, 1)
        doc.refresh_from_db()
        self.assertEqual(doc.estado, DocumentoElectronico.ESTADO_ENVIADO)

    def test_el_lote_se_marca_procesado_cuando_no_queda_ninguno(self):
        doc = self._documento()
        with patch.object(transmision, '_firmar', side_effect=self._firmado), \
             patch.object(transmision.sifen_client, 'enviar_lote',
                          return_value={'lote': '11', 'codigo': '', 'mensaje': '',
                                        'respuesta': '{}'}):
            lote = transmision.transmitir_lote([doc], usuario=self.admin)

        with patch.object(transmision.sifen_client, 'consultar_lote',
                          return_value={'documentos': [
                              {'cdc': doc.cdc, 'estado': 'aprobado',
                               'codigo': '', 'mensaje': ''}]}):
            transmision.consultar_lote(lote)

        lote.refresh_from_db()
        self.assertEqual(lote.estado, LoteTransmision.ESTADO_PROCESADO)
        self.assertIsNotNone(lote.fecha_resultado)

    def test_no_se_pueden_mandar_mas_del_maximo(self):
        with self.assertRaises(ValueError):
            transmision.transmitir_lote(
                [None] * (transmision.MAXIMO_POR_LOTE + 1))

    def test_un_lote_vacio_no_se_manda(self):
        with self.assertRaises(ValueError):
            transmision.transmitir_lote([])

    def test_lotes_sin_resultado_solo_trae_los_enviados(self):
        LoteTransmision.objects.create(numero='A', cantidad=1)
        LoteTransmision.objects.create(
            numero='B', cantidad=1, estado=LoteTransmision.ESTADO_PROCESADO)
        numeros = [l.numero for l in transmision.lotes_sin_resultado()]
        self.assertEqual(numeros, ['A'])
