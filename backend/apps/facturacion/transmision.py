"""
Transmisión de los documentos encolados al SIFEN.

Es la contraparte de `emisor.py`. Aquel crea el DE durante el cobro y no
transmite nada; este lo levanta después y lo manda, cuando ya no hay nadie
esperando en el mostrador.

La separación es la que sostiene todo el diseño: el cobro nunca depende de
la red (ver models.py y CLAUDE.md). El costo es que hay que llevar la cuenta
de los intentos y distinguir qué vale la pena reintentar.

Dos clases de fallo, y se tratan distinto:

  · **Reintentable** — el sidecar está caído, se cortó internet, hubo
    timeout. No dicen nada sobre el documento: se vuelve a intentar hasta
    SIFEN_MAX_INTENTOS.
  · **Terminal** — el SIFEN rechazó el documento, o el payload no se puede
    armar. Reenviar lo mismo da lo mismo: se marca 'rechazado' y se deja de
    intentar, para que alguien lo mire.

La DNIT da una ventana para transmitir un DE ya emitido, así que un corte de
unas horas no invalida la venta.
"""
import logging

from django.db import transaction
from django.utils import timezone

from . import payload as payload_mod
from . import sifen_client
from .models import DocumentoElectronico

logger = logging.getLogger(__name__)


class ResultadoTransmision:
    """Qué pasó con un documento. Sirve para el resumen del comando."""

    def __init__(self, documento, estado, detalle='', reintentable=False):
        self.documento = documento
        self.estado = estado
        self.detalle = detalle
        self.reintentable = reintentable

    @property
    def ok(self) -> bool:
        return self.estado in (DocumentoElectronico.ESTADO_APROBADO,
                               DocumentoElectronico.ESTADO_ENVIADO)

    def __str__(self):
        marca = 'OK ' if self.ok else '── '
        return f'{marca}{self.documento.numero_completo}: {self.estado}' + (
            f' — {self.detalle}' if self.detalle else '')


def pendientes(limite=None):
    """
    Documentos que todavía tiene sentido transmitir.

    Se ordenan por fecha de emisión: el SIFEN no exige orden, pero si algo
    sale mal conviene que los más viejos —los que están más cerca de agotar
    la ventana de transmisión— salgan primero.
    """
    consulta = (DocumentoElectronico.objects
                .filter(estado__in=DocumentoElectronico.ESTADOS_TRANSMITIBLES)
                .select_related('pago__pedido', 'creado_por')
                .order_by('fecha_emision'))

    from django.conf import settings
    max_intentos = getattr(settings, 'SIFEN', {}).get('max_intentos', 10)
    consulta = consulta.filter(intentos_envio__lt=max_intentos)

    return consulta[:limite] if limite else consulta


def transmitir(documento) -> ResultadoTransmision:
    """
    Manda un documento: arma el payload, genera el XML, lo firma, le pone el
    QR y lo transmite.

    Nunca lanza. Devuelve siempre un ResultadoTransmision y deja el estado
    del documento guardado, incluida la respuesta del SIFEN tal como vino —
    que es lo que después permite entender un rechazo.
    """
    documento.intentos_envio += 1
    documento.ultimo_intento = timezone.now()

    try:
        cuerpo = payload_mod.construir(documento)
    except payload_mod.DatosIncompletos as e:
        # No se puede armar: es terminal, reintentarlo no cambia nada.
        return _terminar(documento, str(e), codigo='PAYLOAD')

    try:
        xml = sifen_client.generar_xml(cuerpo['params'], cuerpo['data'])
        documento.xml_generado = xml

        firmado = sifen_client.firmar_xml(xml)
        con_qr = sifen_client.generar_qr(firmado)
        documento.xml_firmado = con_qr
        documento.estado = DocumentoElectronico.ESTADO_FIRMADO
        # Se guarda el firmado ANTES de transmitir: si el envío se corta a
        # mitad de camino, el próximo intento no tiene que volver a firmar.
        documento.save(update_fields=[
            'xml_generado', 'xml_firmado', 'estado',
            'intentos_envio', 'ultimo_intento'])

        respuesta = sifen_client.enviar(con_qr)

    except sifen_client.RechazoSifen as e:
        return _terminar(documento, str(e), codigo=e.codigo, respuesta=e.respuesta)

    except sifen_client.ErrorSidecar as e:
        # Reintentable: se guarda el intento y se deja el estado como estaba.
        documento.respuesta_sifen = str(e)[:2000]
        documento.save(update_fields=[
            'respuesta_sifen', 'intentos_envio', 'ultimo_intento'])
        logger.warning('DE %s: intento %s fallido — %s',
                       documento.numero_completo, documento.intentos_envio, e)
        return ResultadoTransmision(
            documento, documento.estado, str(e), reintentable=True)

    except Exception as e:
        # Un error que no previmos. Se trata como reintentable —es más seguro
        # reintentar que dar por rechazado un documento válido— pero se
        # registra completo para poder arreglarlo.
        logger.exception('DE %s: error inesperado al transmitir',
                         documento.numero_completo)
        documento.respuesta_sifen = f'Error inesperado: {e}'[:2000]
        documento.save(update_fields=[
            'respuesta_sifen', 'intentos_envio', 'ultimo_intento'])
        return ResultadoTransmision(
            documento, documento.estado, f'error inesperado: {e}',
            reintentable=True)

    # Aprobado (o aprobado con observaciones).
    documento.estado = (DocumentoElectronico.ESTADO_APROBADO
                        if respuesta['estado'].startswith('aprobado')
                        else DocumentoElectronico.ESTADO_ENVIADO)
    documento.codigo_respuesta = respuesta['codigo'][:10]
    documento.respuesta_sifen = respuesta['respuesta'][:5000]
    documento.save(update_fields=[
        'estado', 'codigo_respuesta', 'respuesta_sifen',
        'intentos_envio', 'ultimo_intento'])

    logger.info('DE %s %s por el SIFEN (%s)', documento.numero_completo,
                documento.estado, respuesta['codigo'])
    return ResultadoTransmision(documento, documento.estado, respuesta['mensaje'])


def _terminar(documento, detalle, *, codigo='', respuesta=''):
    """Marca el documento como rechazado y deja de reintentarlo."""
    documento.estado = DocumentoElectronico.ESTADO_RECHAZADO
    documento.codigo_respuesta = str(codigo)[:10]
    documento.respuesta_sifen = (respuesta or detalle)[:5000]
    documento.save(update_fields=[
        'estado', 'codigo_respuesta', 'respuesta_sifen',
        'intentos_envio', 'ultimo_intento'])
    logger.error('DE %s rechazado: %s', documento.numero_completo, detalle)
    return ResultadoTransmision(
        documento, DocumentoElectronico.ESTADO_RECHAZADO, detalle)


def transmitir_pendientes(limite=None):
    """
    Recorre la cola. Devuelve la lista de resultados.

    Cada documento va en su propia transacción: si uno falla, los que ya se
    transmitieron quedan guardados. Sería un error meter la cola entera en
    una sola transacción — un rechazo al final desharía envíos que el SIFEN
    ya aceptó, y el sistema quedaría creyendo que no los mandó.
    """
    resultados = []
    for documento in list(pendientes(limite)):
        with transaction.atomic():
            resultados.append(transmitir(documento))
    return resultados
