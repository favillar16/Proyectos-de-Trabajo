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

from . import esquema, kude
from . import payload as payload_mod
from . import sifen_client
from .models import DocumentoElectronico, LoteTransmision

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
        # Armar, firmar y ponerle el QR: el mismo tramo que usa el camino de
        # lote. Vive en `_firmar()` para que los dos no puedan separarse — si
        # un día cambia el orden de firma y QR, cambia para los dos.
        con_qr = _firmar(documento)
        documento.save(update_fields=['intentos_envio', 'ultimo_intento'])

        respuesta = sifen_client.enviar(con_qr)

    except payload_mod.DatosIncompletos as e:
        # No se puede armar: es terminal, reintentarlo no cambia nada.
        return _terminar(documento, str(e), codigo='PAYLOAD')

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
    if documento.estado == DocumentoElectronico.ESTADO_APROBADO:
        # Desde acá se cuenta el plazo para cancelar: 48 h en la factura,
        # 168 en el resto (Manual §11.6.1). Sin esta marca no hay forma de
        # saber si el plazo sigue abierto — `ultimo_intento` se pisa en cada
        # reintento y `fecha_emision` es cuándo se cobró, no cuándo aprobó
        # el SIFEN.
        documento.fecha_aprobacion = timezone.now()
    documento.save(update_fields=[
        'estado', 'codigo_respuesta', 'respuesta_sifen', 'fecha_aprobacion',
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


# ─── Camino asincrónico: lotes ───────────────────────────────────────────────
# El SIFEN tiene dos formas de recibir un DE, y no se diferencian solo en la
# velocidad. El sincrónico contesta en el momento si lo aprobó. El asincrónico
# contesta un **número de lote** y lo procesa cuando puede: el resultado se
# pide después, en un segundo viaje.
#
# Eso cambia el diseño. En el sincrónico, `transmitir()` sale con el documento
# ya resuelto. Acá el documento queda en `enviado` —ni aprobado ni rechazado—
# y hay que volver a preguntar. Si el número de lote se pierde entre un viaje
# y el otro, los documentos quedan transmitidos y huérfanos, sin forma de
# saber qué pasó con ellos. Por eso lo primero que se hace con la respuesta es
# guardarlo.
#
# La Guía de Pruebas lo exige (5 aprobados y 5 rechazados en lote, por cada
# tipo de documento), pero además sirve en producción para mandar el cierre
# del día de una vez en lugar de veinte llamadas sueltas.

# Tope del Manual Técnico. El sidecar lo valida también; acá se corta antes
# para no armar un envío que ya se sabe que va a ser rechazado.
MAXIMO_POR_LOTE = 50


def _firmar(documento):
    """
    Deja el documento firmado y con QR, listo para transmitir.

    Es el tramo que comparten el camino sincrónico y el de lote. Guarda antes
    de salir: si el envío se corta después, el próximo intento no tiene que
    volver a firmar, y firmar cuesta abrir el .p12.

    Devuelve el XML firmado. Lanza lo mismo que las funciones del cliente.
    """
    cuerpo = payload_mod.construir(documento)
    xml = sifen_client.generar_xml(cuerpo['params'], cuerpo['data'])
    documento.xml_generado = xml

    # Contra el XSD del SIFEN, si está configurado. Se valida acá —antes de
    # firmar— porque firmar cuesta abrir el .p12 y no tiene sentido firmar
    # algo que ya se sabe que va a volver rechazado. `XmlInvalido` hereda de
    # ValueError y lo atrapa el `except Exception` de quien llama, que lo
    # trata como reintentable; se convierte en terminal acá, que es lo que
    # es: el XML no va a mejorar solo.
    try:
        esquema.validar(xml)
    except esquema.XmlInvalido as e:
        raise payload_mod.DatosIncompletos(str(e)) from e

    firmado = sifen_client.firmar_xml(xml)
    con_qr = sifen_client.generar_qr(firmado)
    documento.xml_firmado = con_qr
    documento.enlace_qr = kude.enlace_qr_del_xml(con_qr)
    documento.estado = DocumentoElectronico.ESTADO_FIRMADO
    documento.save(update_fields=[
        'xml_generado', 'xml_firmado', 'enlace_qr', 'estado'])
    return con_qr


def transmitir_lote(documentos, usuario=None):
    """
    Firma y manda varios documentos en un solo lote asincrónico.

    Devuelve el `LoteTransmision` creado. Los documentos quedan en `enviado`
    y apuntando al lote; el resultado se resuelve después con
    `consultar_lote()`.

    Un documento que no se pueda armar o firmar **no frena al lote**: se marca
    rechazado, o se deja para el próximo, y el resto sigue. Lo contrario haría
    que un dato mal cargado en una sola venta dejara sin transmitir a las
    otras cuarenta y nueve.
    """
    documentos = list(documentos)
    if not documentos:
        raise ValueError('No hay documentos para armar el lote.')
    if len(documentos) > MAXIMO_POR_LOTE:
        raise ValueError(
            f'Un lote admite hasta {MAXIMO_POR_LOTE} documentos, '
            f'vinieron {len(documentos)}.')

    xmls, incluidos = [], []
    for documento in documentos:
        documento.intentos_envio += 1
        documento.ultimo_intento = timezone.now()
        try:
            xmls.append(_firmar(documento))
            incluidos.append(documento)
        except payload_mod.DatosIncompletos as e:
            _terminar(documento, str(e), codigo='PAYLOAD')
        except sifen_client.RechazoSifen as e:
            _terminar(documento, str(e), codigo=e.codigo, respuesta=e.respuesta)
        except Exception as e:
            # No se pudo firmar: reintentable, queda para el próximo lote.
            logger.warning('DE %s quedó fuera del lote: %s',
                           documento.numero_completo, e)
            documento.respuesta_sifen = f'No entró al lote: {e}'[:2000]
            documento.save(update_fields=[
                'respuesta_sifen', 'intentos_envio', 'ultimo_intento'])

    if not xmls:
        raise ValueError(
            'Ningún documento del grupo se pudo firmar: no hay lote que enviar.')

    respuesta = sifen_client.enviar_lote(xmls)

    with transaction.atomic():
        lote = LoteTransmision.objects.create(
            numero=respuesta['lote'],
            cantidad=len(incluidos),
            codigo_respuesta=respuesta['codigo'][:10],
            respuesta_sifen=respuesta['respuesta'][:5000],
            creado_por=usuario,
        )
        for documento in incluidos:
            documento.lote = lote
            documento.estado = DocumentoElectronico.ESTADO_ENVIADO
            documento.save(update_fields=[
                'lote', 'estado', 'intentos_envio', 'ultimo_intento'])

    logger.info('Lote %s enviado con %s documento(s)', lote.numero, lote.cantidad)
    return lote


def consultar_lote(lote) -> dict:
    """
    Pide el resultado de un lote y lo reparte entre sus documentos.

    Devuelve un resumen: estado del lote, cuántos se resolvieron y cuántos
    siguen pendientes.

    Que el SIFEN conteste "todavía lo estoy procesando" **no es un error**: es
    el flujo normal del asincrónico. En ese caso el lote queda como está y se
    vuelve a preguntar más tarde. Se cuenta en `consultas`, aparte de los
    intentos de envío, para poder avisar si un lote quedó sin resolverse sin
    ensuciar el contador que decide si un documento se sigue reintentando.
    """
    lote.consultas += 1
    respuesta = sifen_client.consultar_lote(lote.numero)
    resultados = respuesta.get('documentos') or []

    if not resultados:
        lote.respuesta_sifen = str(respuesta)[:5000]
        lote.save(update_fields=['consultas', 'respuesta_sifen'])
        logger.info('Lote %s: el SIFEN todavía no devolvió resultados',
                    lote.numero)
        return {'estado': lote.estado, 'resueltos': 0,
                'pendientes': lote.documentos.count(),
                'detalle': 'El SIFEN todavía está procesando el lote.'}

    # El resultado viene por CDC, que es lo único que identifica al documento
    # de los dos lados. Se indexa por ahí y no por el orden del envío: el
    # SIFEN no garantiza devolverlos en el mismo orden en que se mandaron.
    por_cdc = {d.cdc: d for d in lote.documentos.all()}
    resueltos = 0

    with transaction.atomic():
        for resultado in resultados:
            documento = por_cdc.get(str(resultado.get('cdc') or ''))
            if documento is None:
                logger.warning('Lote %s: vino un resultado para el CDC %s, '
                               'que no es de este lote', lote.numero,
                               resultado.get('cdc'))
                continue

            estado = str(resultado.get('estado') or '')
            if estado.startswith('aprobado'):
                documento.estado = DocumentoElectronico.ESTADO_APROBADO
                documento.fecha_aprobacion = timezone.now()
            elif estado == 'rechazado':
                documento.estado = DocumentoElectronico.ESTADO_RECHAZADO
            else:
                # Estado que no se entendió: se deja como está y se vuelve a
                # preguntar. Dar por rechazado lo que no se entendió sería
                # perder una venta ya cobrada.
                continue

            documento.codigo_respuesta = str(resultado.get('codigo') or '')[:10]
            documento.respuesta_sifen = str(resultado.get('mensaje') or '')[:5000]
            documento.save(update_fields=[
                'estado', 'codigo_respuesta', 'respuesta_sifen',
                'fecha_aprobacion'])
            resueltos += 1

        pendientes_ahora = lote.documentos.filter(
            estado=DocumentoElectronico.ESTADO_ENVIADO).count()
        if pendientes_ahora == 0:
            lote.estado = LoteTransmision.ESTADO_PROCESADO
            lote.fecha_resultado = timezone.now()
        lote.codigo_respuesta = str(respuesta.get('codigo') or '')[:10]
        lote.respuesta_sifen = str(respuesta.get('respuesta') or '')[:5000]
        lote.save(update_fields=[
            'estado', 'fecha_resultado', 'consultas',
            'codigo_respuesta', 'respuesta_sifen'])

    logger.info('Lote %s: %s documento(s) resueltos, %s pendientes',
                lote.numero, resueltos, pendientes_ahora)
    return {'estado': lote.estado, 'resueltos': resueltos,
            'pendientes': pendientes_ahora,
            'detalle': respuesta.get('mensaje') or ''}


def lotes_sin_resultado(limite=None):
    """Lotes enviados a los que todavía no les llegó el resultado."""
    consulta = LoteTransmision.objects.filter(
        estado=LoteTransmision.ESTADO_ENVIADO).order_by('fecha_envio')
    return list(consulta[:limite] if limite else consulta)

