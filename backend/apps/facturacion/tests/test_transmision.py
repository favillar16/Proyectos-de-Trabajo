"""
Tests del worker que transmite la cola al SIFEN.

El sidecar se simula: acá no se prueba que la librería de la DNIT funcione
—eso solo se puede probar contra su ambiente, que necesita la habilitación—
sino que **nosotros** hagamos lo correcto con cada respuesta posible.

Lo que importa que esté bien:

  · un corte de red no puede dar un documento por rechazado;
  · un rechazo del SIFEN no puede reintentarse para siempre;
  · un documento aprobado no puede volver a mandarse;
  · un fallo a mitad de la cola no puede deshacer lo ya transmitido.
"""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.facturacion import sifen_client, transmision
from apps.facturacion.emisor import crear_documento
from apps.facturacion.models import DocumentoElectronico

from .factories import (DATOS_FISCALES_COMPLETOS, RUC_RECEPTOR, SIFEN_PRENDIDO,
                        crear_pago, crear_pedido, crear_sesion, crear_usuario,
                        crear_variante)

RESPUESTA_APROBADA = {
    'estado': 'aprobado',
    'codigo': '0260',
    'mensaje': 'Autorizado el uso del DE',
    'respuesta': '<xml>respuesta cruda del SIFEN</xml>',
}


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class BaseTransmisionTests(TestCase):
    databases = {'default', 'sync'}
    _secuencia = 0

    def _documento(self, monto=100000):
        BaseTransmisionTests._secuencia += 1
        n = BaseTransmisionTests._secuencia
        usuario = crear_usuario(username=f'cajero_tx{n}')
        variante = crear_variante(nombre=f'Producto {n}')
        pedido = crear_pedido(usuario, [(variante, 1, monto)])
        sesion = crear_sesion(usuario)
        pago = crear_pago(pedido, sesion, usuario, monto)
        return crear_documento(
            pago, receptor={'ruc': RUC_RECEPTOR, 'razon_social': 'Cliente SRL'})

    def _simular_sidecar(self, *, enviar=None, error_en=None):
        """
        Parchea el cliente del sidecar.

        `enviar` es lo que devuelve el envío; `error_en` permite hacer fallar
        una etapa concreta con la excepción que se le pase.
        """
        parches = []
        for etapa, retorno in (('generar_xml', '<xml/>'),
                               ('firmar_xml', '<xml firmado/>'),
                               ('generar_qr', '<xml con-qr/>')):
            if error_en and error_en[0] == etapa:
                parche = patch.object(sifen_client, etapa, side_effect=error_en[1])
            else:
                parche = patch.object(sifen_client, etapa, return_value=retorno)
            parches.append(parche)

        if error_en and error_en[0] == 'enviar':
            parches.append(patch.object(sifen_client, 'enviar',
                                        side_effect=error_en[1]))
        else:
            parches.append(patch.object(
                sifen_client, 'enviar',
                return_value=enviar or dict(RESPUESTA_APROBADA)))

        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)


class TransmitirTests(BaseTransmisionTests):

    def test_un_documento_aprobado_queda_aprobado(self):
        self._simular_sidecar()
        documento = self._documento()

        resultado = transmision.transmitir(documento)

        documento.refresh_from_db()
        self.assertTrue(resultado.ok)
        self.assertEqual(documento.estado, DocumentoElectronico.ESTADO_APROBADO)
        self.assertEqual(documento.codigo_respuesta, '0260')
        self.assertIn('respuesta cruda', documento.respuesta_sifen)

    def test_guarda_el_xml_firmado_antes_de_enviar(self):
        # Si el envío se corta a mitad de camino, el próximo intento no tiene
        # que volver a firmar: firmar es lo caro y lo que toca el certificado.
        self._simular_sidecar()
        documento = self._documento()
        transmision.transmitir(documento)

        documento.refresh_from_db()
        self.assertEqual(documento.xml_generado, '<xml/>')
        self.assertEqual(documento.xml_firmado, '<xml con-qr/>')

    def test_cuenta_los_intentos(self):
        self._simular_sidecar()
        documento = self._documento()
        self.assertEqual(documento.intentos_envio, 0)

        transmision.transmitir(documento)

        documento.refresh_from_db()
        self.assertEqual(documento.intentos_envio, 1)
        self.assertIsNotNone(documento.ultimo_intento)


class FallosReintentablesTests(BaseTransmisionTests):

    def test_el_sidecar_caido_no_rechaza_el_documento(self):
        # Es el error más importante de no cometer: un problema de red no
        # dice NADA sobre la validez del documento.
        self._simular_sidecar(error_en=(
            'generar_xml', sifen_client.ErrorSidecar('conexión rechazada')))
        documento = self._documento()

        resultado = transmision.transmitir(documento)

        documento.refresh_from_db()
        self.assertTrue(resultado.reintentable)
        self.assertNotEqual(documento.estado,
                            DocumentoElectronico.ESTADO_RECHAZADO)
        self.assertTrue(documento.pendiente_de_envio)

    def test_un_corte_al_enviar_deja_el_documento_en_cola(self):
        self._simular_sidecar(error_en=(
            'enviar', sifen_client.ErrorSidecar('timeout')))
        documento = self._documento()

        transmision.transmitir(documento)

        documento.refresh_from_db()
        self.assertTrue(documento.pendiente_de_envio)
        self.assertIn(documento, list(transmision.pendientes()))

    def test_un_error_inesperado_tambien_se_reintenta(self):
        # Ante algo que no previmos es más seguro reintentar que dar por
        # perdido un documento que podría ser válido.
        self._simular_sidecar(error_en=('firmar_xml', RuntimeError('vaya')))
        documento = self._documento()

        resultado = transmision.transmitir(documento)

        documento.refresh_from_db()
        self.assertTrue(resultado.reintentable)
        self.assertNotEqual(documento.estado,
                            DocumentoElectronico.ESTADO_RECHAZADO)

    def test_deja_de_reintentar_al_llegar_al_tope(self):
        self._simular_sidecar(error_en=(
            'enviar', sifen_client.ErrorSidecar('sigue caído')))
        documento = self._documento()
        tope = SIFEN_PRENDIDO.get('max_intentos', 10)

        documento.intentos_envio = tope
        documento.save(update_fields=['intentos_envio'])

        self.assertNotIn(documento, list(transmision.pendientes()))


class RechazosTests(BaseTransmisionTests):

    def test_un_rechazo_del_sifen_es_terminal(self):
        # Reenviar lo mismo da el mismo rechazo: insistir solo gasta la cola.
        self._simular_sidecar(error_en=('enviar', sifen_client.RechazoSifen(
            'CDC duplicado', codigo='0160', respuesta='<r>detalle</r>')))
        documento = self._documento()

        resultado = transmision.transmitir(documento)

        documento.refresh_from_db()
        self.assertFalse(resultado.reintentable)
        self.assertEqual(documento.estado, DocumentoElectronico.ESTADO_RECHAZADO)
        self.assertEqual(documento.codigo_respuesta, '0160')
        self.assertFalse(documento.pendiente_de_envio)
        self.assertNotIn(documento, list(transmision.pendientes()))

    def test_guarda_el_detalle_del_rechazo(self):
        # Sin el crudo de la respuesta no hay forma de entender por qué el
        # SIFEN rechazó, y el rechazo hay que corregirlo a mano.
        self._simular_sidecar(error_en=('enviar', sifen_client.RechazoSifen(
            'falta un campo', codigo='0999', respuesta='<r>campo X ausente</r>')))
        documento = self._documento()
        transmision.transmitir(documento)

        documento.refresh_from_db()
        self.assertIn('campo X ausente', documento.respuesta_sifen)

    def test_un_documento_que_no_se_puede_armar_no_se_reintenta(self):
        # Falta un dato fiscal: reintentarlo cada cinco minutos para siempre
        # no lo va a arreglar.
        self._simular_sidecar()
        documento = self._documento()
        incompletos = dict(DATOS_FISCALES_COMPLETOS, ciudad='')

        with override_settings(DATOS_FISCALES=incompletos):
            resultado = transmision.transmitir(documento)

        documento.refresh_from_db()
        self.assertFalse(resultado.reintentable)
        self.assertEqual(documento.estado, DocumentoElectronico.ESTADO_RECHAZADO)
        self.assertEqual(documento.codigo_respuesta, 'PAYLOAD')


class ColaTests(BaseTransmisionTests):

    def test_solo_levanta_los_transmitibles(self):
        self._simular_sidecar()
        pendiente = self._documento()
        aprobado = self._documento()
        aprobado.estado = DocumentoElectronico.ESTADO_APROBADO
        aprobado.save(update_fields=['estado'])

        cola = list(transmision.pendientes())
        self.assertIn(pendiente, cola)
        self.assertNotIn(aprobado, cola)

    def test_los_mas_viejos_salen_primero(self):
        # Son los que están más cerca de agotar la ventana de transmisión
        # que da la DNIT.
        self._simular_sidecar()
        primero = self._documento()
        segundo = self._documento()

        cola = list(transmision.pendientes())
        self.assertLess(cola.index(primero), cola.index(segundo))

    def test_un_rechazo_no_deshace_lo_ya_transmitido(self):
        # Cada documento va en su propia transacción. Si la cola entera
        # fuera una sola, un rechazo al final revertiría envíos que el SIFEN
        # ya aceptó y el sistema creería que no los mandó.
        documento_ok = self._documento()
        documento_malo = self._documento()

        def enviar_falso(xml):
            # El primero pasa, el segundo lo rechazan.
            if enviar_falso.llamadas == 0:
                enviar_falso.llamadas += 1
                return dict(RESPUESTA_APROBADA)
            raise sifen_client.RechazoSifen('rechazado', codigo='0160')
        enviar_falso.llamadas = 0

        self._simular_sidecar()
        with patch.object(sifen_client, 'enviar', side_effect=enviar_falso):
            transmision.transmitir_pendientes()

        documento_ok.refresh_from_db()
        documento_malo.refresh_from_db()
        self.assertEqual(documento_ok.estado,
                         DocumentoElectronico.ESTADO_APROBADO)
        self.assertEqual(documento_malo.estado,
                         DocumentoElectronico.ESTADO_RECHAZADO)

    def test_respeta_el_limite(self):
        self._simular_sidecar()
        for _ in range(3):
            self._documento()

        resultados = transmision.transmitir_pendientes(limite=2)
        self.assertEqual(len(resultados), 2)


class ClienteDelSidecarTests(TestCase):
    """
    El cliente traduce respuestas del sidecar a excepciones nuestras. Que la
    traducción sea correcta decide si un documento se reintenta o se descarta.
    """
    databases = {'default'}

    @override_settings(SIFEN=dict(SIFEN_PRENDIDO, sidecar_url='http://x.invalid'))
    def test_una_respuesta_de_rechazo_lanza_RechazoSifen(self):
        with patch.object(sifen_client, '_postear', return_value={
                'estado': 'rechazado', 'codigo': '0160',
                'mensaje': 'CDC duplicado'}):
            with self.assertRaises(sifen_client.RechazoSifen) as caso:
                sifen_client.enviar('<xml/>')
        self.assertEqual(caso.exception.codigo, '0160')

    @override_settings(SIFEN=dict(SIFEN_PRENDIDO, sidecar_url='http://x.invalid'))
    def test_una_respuesta_que_no_entendemos_se_trata_como_reintentable(self):
        # Ante lo desconocido, reintentar es más seguro que descartar.
        with patch.object(sifen_client, '_postear',
                          return_value={'estado': 'vaya_a_saber'}):
            with self.assertRaises(sifen_client.ErrorSidecar):
                sifen_client.enviar('<xml/>')

    @override_settings(SIFEN=dict(SIFEN_PRENDIDO, sidecar_url='http://x.invalid'))
    def test_una_aprobacion_devuelve_los_campos_esperados(self):
        with patch.object(sifen_client, '_postear',
                          return_value=dict(RESPUESTA_APROBADA)):
            respuesta = sifen_client.enviar('<xml/>')
        self.assertEqual(respuesta['estado'], 'aprobado')
        self.assertEqual(respuesta['codigo'], '0260')

    @override_settings(SIFEN=dict(SIFEN_PRENDIDO, sidecar_url=''))
    def test_sin_url_de_sidecar_avisa_claro(self):
        with self.assertRaises(sifen_client.ErrorSidecar) as caso:
            sifen_client.generar_xml({}, {})
        self.assertIn('SIFEN_SIDECAR_URL', str(caso.exception))

    @override_settings(SIFEN=dict(SIFEN_PRENDIDO, sidecar_url='http://x.invalid'))
    def test_si_falta_el_xml_en_la_respuesta_no_sigue_adelante(self):
        # Un sidecar que contesta 200 con el cuerpo vacío no puede hacer que
        # firmemos una cadena vacía.
        with patch.object(sifen_client, '_postear', return_value={}):
            with self.assertRaises(sifen_client.ErrorSidecar):
                sifen_client.generar_xml({}, {})
