"""
Tests de los eventos del emisor: cancelación e inutilización (Fase C).

El sidecar se simula, como en `test_transmision.py`: lo que se prueba es que
**nosotros** hagamos lo correcto, no que la librería de la DNIT funcione.

Lo que importa que esté bien, y por qué:

  · el **plazo**. 48 h desde la aprobación en la factura, 168 en el resto
    (Manual V150 §11.6.1, GDE004a/GDE004b). Dejar pedir una cancelación
    vencida gasta un intento y devuelve un rechazo que nadie entiende; peor,
    hace creer que la venta se anuló cuando para la DNIT sigue viva.
  · el documento pasa a `cancelado` **solo si el SIFEN aprobó** el evento.
  · una inutilización nunca puede tapar un número que sí se emitió (GEI005).
  · un corte de red deja el evento pendiente, no rechazado: con un plazo
    corriendo, perder una cancelación por un timeout es lo más caro posible.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.facturacion import codigos, eventos, sifen_client
from apps.facturacion.emisor import crear_documento
from apps.facturacion.models import (DocumentoElectronico, EventoDocumento,
                                     SecuenciaComprobante)

from .factories import (DATOS_FISCALES_COMPLETOS, RUC_RECEPTOR, SIFEN_APAGADO,
                        SIFEN_PRENDIDO, crear_pago, crear_pedido, crear_sesion,
                        crear_usuario, crear_variante)

RESPUESTA_APROBADA = {
    'estado': 'aprobado',
    'codigo': '0600',
    'mensaje': 'Evento registrado',
    'respuesta': '<xml>respuesta del SIFEN</xml>',
}


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class BaseEventos(TestCase):
    databases = {'default', 'sync'}
    _secuencia = 0

    def setUp(self):
        self.admin = crear_usuario(username=f'admin_ev{self._nuevo()}', rol='admin')

    @classmethod
    def _nuevo(cls):
        cls._secuencia += 1
        return cls._secuencia

    def _documento(self, aprobado=True, tipo=codigos.TIPO_DE_FACTURA,
                   horas_desde_aprobacion=0):
        n = self._nuevo()
        usuario = crear_usuario(username=f'cajero_ev{n}')
        variante = crear_variante(nombre=f'Producto ev{n}')
        pedido = crear_pedido(usuario, [(variante, 1, 100000)])
        sesion = crear_sesion(usuario)
        pago = crear_pago(pedido, sesion, usuario, 100000)
        documento = crear_documento(
            pago, receptor={'ruc': RUC_RECEPTOR, 'razon_social': 'Cliente SRL'})
        if tipo != documento.tipo_documento:
            documento.tipo_documento = tipo
        if aprobado:
            documento.estado = DocumentoElectronico.ESTADO_APROBADO
            documento.fecha_aprobacion = (
                timezone.now() - timedelta(hours=horas_desde_aprobacion))
        documento.save()
        return documento


class PlazoDeCancelacionTests(BaseEventos):

    def test_la_factura_tiene_48_horas(self):
        self.assertEqual(eventos.horas_de_plazo(codigos.TIPO_DE_FACTURA), 48)

    def test_los_demas_tipos_tienen_168(self):
        for tipo in (codigos.TIPO_DE_NOTA_CREDITO, codigos.TIPO_DE_NOTA_DEBITO,
                     codigos.TIPO_DE_NOTA_REMISION, codigos.TIPO_DE_AUTOFACTURA):
            self.assertEqual(eventos.horas_de_plazo(tipo), 168)

    def test_el_reloj_arranca_en_la_aprobacion_no_en_la_emision(self):
        documento = self._documento(horas_desde_aprobacion=10)
        self.assertAlmostEqual(eventos.horas_restantes(documento), 38, delta=0.1)

    def test_sin_aprobacion_no_hay_plazo_que_calcular(self):
        documento = self._documento(aprobado=False)
        self.assertIsNone(eventos.horas_restantes(documento))

    def test_pasadas_las_48_horas_ya_no_se_puede(self):
        documento = self._documento(horas_desde_aprobacion=49)
        self.assertIn('Venció el plazo',
                      eventos.motivo_por_el_que_no_se_puede_cancelar(documento))

    def test_una_nota_de_credito_a_las_49_horas_todavia_se_puede(self):
        documento = self._documento(tipo=codigos.TIPO_DE_NOTA_CREDITO,
                                    horas_desde_aprobacion=49)
        self.assertEqual(
            eventos.motivo_por_el_que_no_se_puede_cancelar(documento), '')


class RegistrarCancelacionTests(BaseEventos):

    def test_registra_el_evento_pendiente_sin_transmitir(self):
        documento = self._documento()
        evento = eventos.registrar_cancelacion(
            documento, 'El cliente desistió de la compra', self.admin)

        self.assertEqual(evento.estado, EventoDocumento.ESTADO_PENDIENTE)
        self.assertEqual(evento.tipo, EventoDocumento.TIPO_CANCELACION)
        documento.refresh_from_db()
        # Todavía no lo canceló nadie: el SIFEN no contestó.
        self.assertEqual(documento.estado, DocumentoElectronico.ESTADO_APROBADO)

    def test_un_documento_no_aprobado_no_se_cancela(self):
        documento = self._documento(aprobado=False)
        with self.assertRaises(eventos.EventoNoPermitido):
            eventos.registrar_cancelacion(documento, 'Motivo válido', self.admin)

    def test_no_se_puede_pedir_dos_veces(self):
        documento = self._documento()
        eventos.registrar_cancelacion(documento, 'Primera solicitud', self.admin)
        with self.assertRaises(eventos.EventoNoPermitido):
            eventos.registrar_cancelacion(documento, 'Segunda solicitud', self.admin)

    def test_si_la_primera_fue_rechazada_se_puede_reintentar(self):
        """Un rechazo del SIFEN es corregible: no puede dejar trabado el DTE."""
        documento = self._documento()
        primero = eventos.registrar_cancelacion(documento, 'Motivo flojo', self.admin)
        primero.estado = EventoDocumento.ESTADO_RECHAZADO
        primero.save()

        segundo = eventos.registrar_cancelacion(
            documento, 'Motivo corregido y completo', self.admin)
        self.assertEqual(segundo.estado, EventoDocumento.ESTADO_PENDIENTE)

    def test_el_motivo_corto_no_pasa(self):
        """GEC003 pide de 5 a 500 caracteres; el SIFEN rechaza un 'ok'."""
        documento = self._documento()
        with self.assertRaises(ValidationError):
            eventos.registrar_cancelacion(documento, 'ok', self.admin)

    def test_el_motivo_larguisimo_tampoco(self):
        documento = self._documento()
        with self.assertRaises(ValidationError):
            eventos.registrar_cancelacion(documento, 'x' * 501, self.admin)


class TransmitirCancelacionTests(BaseEventos):

    def _evento(self):
        return eventos.registrar_cancelacion(
            self._documento(), 'El cliente desistió de la compra', self.admin)

    def test_aprobado_deja_el_documento_cancelado(self):
        evento = self._evento()
        with patch.object(sifen_client, 'enviar_evento',
                          return_value=RESPUESTA_APROBADA):
            eventos.transmitir(evento)

        self.assertEqual(evento.estado, EventoDocumento.ESTADO_APROBADO)
        evento.documento.refresh_from_db()
        self.assertEqual(evento.documento.estado,
                         DocumentoElectronico.ESTADO_CANCELADO)

    def test_manda_el_cdc_y_el_motivo(self):
        evento = self._evento()
        with patch.object(sifen_client, 'enviar_evento',
                          return_value=RESPUESTA_APROBADA) as enviar:
            eventos.transmitir(evento)

        tipo, datos = enviar.call_args[0]
        self.assertEqual(tipo, 'cancelacion')
        self.assertEqual(datos['cdc'], evento.documento.cdc)
        self.assertEqual(len(datos['cdc']), 44)
        self.assertEqual(datos['motivo'], 'El cliente desistió de la compra')

    def test_un_corte_de_red_deja_el_evento_pendiente(self):
        evento = self._evento()
        with patch.object(sifen_client, 'enviar_evento',
                          side_effect=sifen_client.ErrorSidecar('sin conexión')):
            eventos.transmitir(evento)

        self.assertEqual(evento.estado, EventoDocumento.ESTADO_PENDIENTE)
        self.assertEqual(evento.intentos_envio, 1)
        evento.documento.refresh_from_db()
        self.assertEqual(evento.documento.estado,
                         DocumentoElectronico.ESTADO_APROBADO)

    def test_un_rechazo_no_cancela_el_documento(self):
        evento = self._evento()
        with patch.object(
                sifen_client, 'enviar_evento',
                side_effect=sifen_client.RechazoSifen(
                    'fuera de plazo', codigo='4009', respuesta='<xml/>')):
            eventos.transmitir(evento)

        self.assertEqual(evento.estado, EventoDocumento.ESTADO_RECHAZADO)
        self.assertEqual(evento.codigo_respuesta, '4009')
        evento.documento.refresh_from_db()
        self.assertEqual(evento.documento.estado,
                         DocumentoElectronico.ESTADO_APROBADO)

    def test_un_error_inesperado_no_da_el_evento_por_perdido(self):
        evento = self._evento()
        with patch.object(sifen_client, 'enviar_evento',
                          side_effect=RuntimeError('boom')):
            eventos.transmitir(evento)
        self.assertEqual(evento.estado, EventoDocumento.ESTADO_PENDIENTE)

    def test_la_cola_solo_toma_los_transmitibles(self):
        pendiente = self._evento()
        aprobado = self._evento()
        aprobado.estado = EventoDocumento.ESTADO_APROBADO
        aprobado.save()

        ids = [e.pk for e in eventos.pendientes()]
        self.assertIn(pendiente.pk, ids)
        self.assertNotIn(aprobado.pk, ids)


class InutilizacionTests(BaseEventos):

    def _registrar(self, desde=10, hasta=12, **extra):
        datos = dict(
            tipo_documento=codigos.TIPO_DE_FACTURA,
            establecimiento='001', punto_expedicion='001',
            desde=desde, hasta=hasta,
            motivo='Números salteados por corte de energía',
            usuario=self.admin,
        )
        datos.update(extra)
        return eventos.registrar_inutilizacion(**datos)

    def test_registra_el_rango_con_el_timbrado_vigente(self):
        evento = self._registrar()
        self.assertEqual(evento.tipo, EventoDocumento.TIPO_INUTILIZACION)
        self.assertEqual(evento.timbrado, '12345678')
        self.assertEqual(evento.numero_desde, 10)
        self.assertIn('001-001-0000010', evento.rango_legible)

    def test_no_se_puede_inutilizar_un_numero_ya_emitido(self):
        """GEI005: declarar inexistente algo que sí se emitió es lo peor."""
        documento = self._documento()
        with self.assertRaises(eventos.EventoNoPermitido) as caso:
            self._registrar(desde=documento.numero, hasta=documento.numero)
        self.assertIn('emitido', str(caso.exception))

    def test_no_se_puede_inutilizar_dos_veces_el_mismo_rango(self):
        self._registrar(desde=20, hasta=25)
        with self.assertRaises(eventos.EventoNoPermitido):
            self._registrar(desde=23, hasta=30)

    def test_un_rechazo_previo_no_bloquea_el_rango(self):
        evento = self._registrar(desde=40, hasta=42)
        evento.estado = EventoDocumento.ESTADO_RECHAZADO
        evento.save()
        self.assertIsNotNone(self._registrar(desde=40, hasta=42))

    def test_el_rango_no_puede_pasar_de_mil_numeros(self):
        with self.assertRaises(ValidationError):
            self._registrar(desde=1000, hasta=2001)

    def test_el_final_no_puede_ser_menor_que_el_inicio(self):
        with self.assertRaises(ValidationError):
            self._registrar(desde=50, hasta=49)

    def test_manda_los_campos_que_pide_xmlgen(self):
        evento = self._registrar(desde=60, hasta=61)
        with patch.object(sifen_client, 'enviar_evento',
                          return_value=RESPUESTA_APROBADA) as enviar:
            eventos.transmitir(evento)

        tipo, datos = enviar.call_args[0]
        self.assertEqual(tipo, 'inutilizacion')
        self.assertEqual(
            set(datos),
            {'timbrado', 'establecimiento', 'punto', 'desde', 'hasta',
             'tipoDocumento', 'motivo'})
        self.assertEqual(len(datos['timbrado']), 8)
        self.assertEqual(len(datos['establecimiento']), 3)

    def test_los_huecos_son_los_numeros_consumidos_sin_documento(self):
        documento = self._documento()
        secuencia = SecuenciaComprobante.objects.get(
            tipo_documento=codigos.TIPO_DE_FACTURA,
            establecimiento='001', punto_expedicion='001')
        # Se consumieron dos números más que no llegaron a comprobante.
        secuencia.ultimo_numero = documento.numero + 2
        secuencia.save()

        huecos = eventos.huecos_de_numeracion(
            codigos.TIPO_DE_FACTURA, '001', '001')
        self.assertIn(documento.numero + 1, huecos)
        self.assertIn(documento.numero + 2, huecos)
        self.assertNotIn(documento.numero, huecos)

    def test_un_hueco_ya_inutilizado_deja_de_figurar(self):
        documento = self._documento()
        secuencia = SecuenciaComprobante.objects.get(
            tipo_documento=codigos.TIPO_DE_FACTURA,
            establecimiento='001', punto_expedicion='001')
        secuencia.ultimo_numero = documento.numero + 1
        secuencia.save()
        self._registrar(desde=documento.numero + 1, hasta=documento.numero + 1)

        self.assertNotIn(
            documento.numero + 1,
            eventos.huecos_de_numeracion(codigos.TIPO_DE_FACTURA, '001', '001'))


class ApiEventosTests(BaseEventos):

    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def test_cancelar_registra_y_transmite(self):
        documento = self._documento()
        with patch.object(sifen_client, 'enviar_evento',
                          return_value=RESPUESTA_APROBADA):
            respuesta = self.api.post(
                reverse('fe-cancelar', args=[documento.pk]),
                {'motivo': 'El cliente desistió de la compra'}, format='json')

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data['evento']['estado'], 'aprobado')
        self.assertEqual(respuesta.data['documento']['estado'], 'cancelado')

    def test_cancelar_con_motivo_vacio_da_400(self):
        documento = self._documento()
        respuesta = self.api.post(reverse('fe-cancelar', args=[documento.pk]),
                                  {'motivo': ''}, format='json')
        self.assertEqual(respuesta.status_code, 400)

    def test_cancelar_fuera_de_plazo_da_400_con_el_motivo(self):
        documento = self._documento(horas_desde_aprobacion=72)
        respuesta = self.api.post(
            reverse('fe-cancelar', args=[documento.pk]),
            {'motivo': 'Se anuló la venta la semana pasada'}, format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('plazo', respuesta.data['error'])

    def test_un_cajero_no_puede_cancelar(self):
        documento = self._documento()
        self.api.force_authenticate(crear_usuario(username='cajero_no', rol='cajero'))
        respuesta = self.api.post(
            reverse('fe-cancelar', args=[documento.pk]),
            {'motivo': 'Devolución del cliente'}, format='json')
        self.assertEqual(respuesta.status_code, 403)

    @override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_APAGADO)
    def test_con_el_sifen_apagado_queda_registrado_sin_transmitir(self):
        documento = self._documento()
        with patch.object(sifen_client, 'enviar_evento') as enviar:
            respuesta = self.api.post(
                reverse('fe-cancelar', args=[documento.pk]),
                {'motivo': 'Prueba con el interruptor apagado'}, format='json')

        self.assertEqual(respuesta.status_code, 201)
        enviar.assert_not_called()
        self.assertEqual(respuesta.data['evento']['estado'], 'pendiente')

    def test_inutilizar_por_api(self):
        with patch.object(sifen_client, 'enviar_evento',
                          return_value=RESPUESTA_APROBADA):
            respuesta = self.api.post(reverse('fe-inutilizaciones'), {
                'tipo_documento': codigos.TIPO_DE_FACTURA,
                'establecimiento': '001', 'punto_expedicion': '001',
                'desde': 90, 'hasta': 92,
                'motivo': 'Se cortó la luz en medio de la emisión',
            }, format='json')

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data['evento']['estado'], 'aprobado')

    def test_inutilizar_sin_rango_da_400(self):
        respuesta = self.api.post(reverse('fe-inutilizaciones'),
                                  {'motivo': 'Falta el rango entero'},
                                  format='json')
        self.assertEqual(respuesta.status_code, 400)

    def test_los_numeros_sin_usar_vienen_agrupados_en_rangos(self):
        documento = self._documento()
        secuencia = SecuenciaComprobante.objects.get(
            tipo_documento=codigos.TIPO_DE_FACTURA,
            establecimiento='001', punto_expedicion='001')
        secuencia.ultimo_numero = documento.numero + 3
        secuencia.save()

        respuesta = self.api.get(reverse('fe-numeros-sin-usar'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['rangos'][-1],
                         {'desde': documento.numero + 1,
                          'hasta': documento.numero + 3})

    def test_la_cola_dice_cuantas_horas_quedan_para_cancelar(self):
        self._documento(horas_desde_aprobacion=6)
        respuesta = self.api.get(reverse('fe-documentos'))
        horas = [d['horas_para_cancelar'] for d in respuesta.data['documentos']
                 if d['horas_para_cancelar'] is not None]
        self.assertTrue(any(41 < h < 43 for h in horas), horas)
