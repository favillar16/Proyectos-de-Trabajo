"""
Eventos del rol emisor: cancelación e inutilización (Fase C).

Qué resuelve cada uno, que no es lo mismo aunque se parezcan:

  · **Cancelación** — el DTE existe, el SIFEN lo aprobó, y la venta no se
    concretó. Manual Técnico V150 §11.1.2: el emisor tiene **48 horas desde
    la aprobación** para cancelar una factura electrónica y **168** para los
    demás tipos (§11.6.1, validaciones GDE004a y GDE004b). Vencido el plazo
    el camino ya no es un evento sino una nota de crédito.

  · **Inutilización** — un número del talonario se reservó y nunca llegó a
    ser un documento. No hay nada que cancelar: se declara que ese número no
    va a existir. Es el que cierra el hueco operativo real, porque la DNIT
    exige un correlativo sin saltos y un salto callado es una observación en
    una fiscalización.

Dos decisiones de diseño, las dos por el mismo motivo —que la operación del
local no dependa de la red:

1. El evento **se guarda antes de transmitirse**, como un DE. Si el sidecar
   está caído, queda `pendiente` y lo levanta el worker. Con 48 horas
   corriendo, hacer que cancelar dependa de que internet ande en ese segundo
   sería el peor momento posible para acoplarlos.
2. El documento pasa a `cancelado` **solo cuando el SIFEN aprueba el
   evento**. Marcarlo antes dejaría la base diciendo que un DTE está
   cancelado cuando para la DNIT sigue vivo, que es la desincronización más
   cara de las dos posibles.

La NT 025 (23/04/2025) sacó la validación que exigía que el receptor no
hubiera confirmado el DTE antes de cancelar. No hay nada que implementar por
esa nota: lo que hace es quitar un motivo de rechazo.
"""
import logging
from datetime import date

from django.db import transaction
from django.utils import timezone

from . import codigos, numeracion, sifen_client
from .models import DocumentoElectronico, EventoDocumento, SecuenciaComprobante

logger = logging.getLogger(__name__)


class EventoNoPermitido(Exception):
    """El evento no se puede registrar. Lleva el motivo en el mensaje."""


# ─── Plazos ──────────────────────────────────────────────────────────────────

def horas_de_plazo(tipo_documento: int) -> int:
    """48 h para la factura electrónica, 168 para el resto (GDE004a/b)."""
    return (EventoDocumento.HORAS_CANCELACION_FACTURA
            if tipo_documento == codigos.TIPO_DE_FACTURA
            else EventoDocumento.HORAS_CANCELACION_OTROS)


def momento_de_aprobacion(documento):
    """
    Cuándo aprobó el SIFEN este documento.

    Normalmente es `fecha_aprobacion`. Para los documentos aprobados antes de
    que ese campo existiera se cae a `ultimo_intento`, que en un documento
    aprobado es exactamente el mismo instante: `transmision.transmitir()`
    guarda los dos juntos. Sin este respaldo, un DTE viejo quedaría sin poder
    cancelarse nunca, no por una regla de la DNIT sino por una columna que se
    agregó después.
    """
    if documento.fecha_aprobacion:
        return documento.fecha_aprobacion
    if documento.estado == DocumentoElectronico.ESTADO_APROBADO:
        return documento.ultimo_intento
    return None


def horas_restantes(documento) -> float | None:
    """
    Cuántas horas quedan para pedir la cancelación. None si el documento
    todavía no fue aprobado (el reloj arranca con la aprobación, no con la
    emisión).
    """
    aprobacion = momento_de_aprobacion(documento)
    if not aprobacion:
        return None
    limite = aprobacion + timezone.timedelta(
        hours=horas_de_plazo(documento.tipo_documento))
    return (limite - timezone.now()).total_seconds() / 3600


def documentos_asociados_vivos(documento):
    """
    Los DTE que cuelgan de este y todavía están en pie: notas de crédito, de
    débito y remisiones que lo referencian por CDC (campo H004 `dCdCDERef`).

    Se excluyen los rechazados y los ya cancelados porque no existen para la
    DNIT: uno nunca llegó a ser DTE y el otro ya se dio de baja.
    """
    if not documento.cdc:
        return DocumentoElectronico.objects.none()
    return DocumentoElectronico.objects.filter(
        documento_asociado_cdc=documento.cdc,
    ).exclude(
        estado__in=(DocumentoElectronico.ESTADO_CANCELADO,
                    DocumentoElectronico.ESTADO_RECHAZADO),
    ).order_by('-numero')


def motivo_por_el_que_no_se_puede_cancelar(documento) -> str:
    """
    Cadena vacía si se puede cancelar; si no, el motivo en castellano llano,
    listo para mostrarle a quien está en la caja.
    """
    if documento.estado == DocumentoElectronico.ESTADO_CANCELADO:
        return 'Este documento ya está cancelado.'
    if documento.estado != DocumentoElectronico.ESTADO_APROBADO:
        return ('Solo se puede cancelar un documento aprobado por el SIFEN. '
                f'Este está «{documento.get_estado_display()}»: si todavía no '
                f'se transmitió, lo que corresponde es corregirlo antes de '
                f'que salga.')
    if documento.eventos.filter(
            tipo=EventoDocumento.TIPO_CANCELACION).exclude(
            estado=EventoDocumento.ESTADO_RECHAZADO).exists():
        return 'Ya hay un pedido de cancelación en curso para este documento.'

    restantes = horas_restantes(documento)
    if restantes is None:
        return ('No está registrada la fecha en que el SIFEN aprobó este '
                'documento, así que no se puede saber si el plazo sigue '
                'abierto.')
    if restantes <= 0:
        plazo = horas_de_plazo(documento.tipo_documento)
        return (f'Venció el plazo de {plazo} horas desde la aprobación para '
                f'cancelar este documento. La corrección va por nota de '
                f'crédito.')

    # Tabla J, fila 1: «Para un DTE que tenga otros DTEs asociados, se debe
    # realizar la cancelación del último DTE hasta llegar al inicial». O sea
    # que una factura con una nota de crédito colgada no se cancela primero:
    # hay que empezar por la nota. Sin este control el SIFEN devolvería el
    # rechazo, ya con el evento registrado y el plazo corriendo.
    asociados = list(documentos_asociados_vivos(documento)[:5])
    if asociados:
        detalle = ', '.join(
            f'{d.numero_completo} ({d.get_estado_display().lower()})'
            for d in asociados)
        return (f'Este documento tiene {len(asociados)} documento(s) '
                f'asociado(s) todavía vigente(s): {detalle}. Hay que cancelar '
                f'primero el último de la cadena e ir hacia atrás hasta llegar '
                f'a este.')
    return ''


# ─── Registrar ───────────────────────────────────────────────────────────────

@transaction.atomic
def registrar_cancelacion(documento, motivo, usuario) -> EventoDocumento:
    """
    Deja la cancelación registrada y pendiente de envío. No transmite.
    Lanza EventoNoPermitido si el documento no admite la cancelación.
    """
    impedimento = motivo_por_el_que_no_se_puede_cancelar(documento)
    if impedimento:
        raise EventoNoPermitido(impedimento)

    evento = EventoDocumento(
        tipo=EventoDocumento.TIPO_CANCELACION,
        documento=documento,
        motivo=(motivo or '').strip(),
        creado_por=usuario,
    )
    evento.full_clean(exclude=['xml_enviado'])
    evento.save()
    logger.info('Cancelación registrada para %s por %s',
                documento.numero_completo, usuario)
    return evento


def numeros_ocupados(tipo_documento, establecimiento, punto_expedicion,
                     desde, hasta):
    """
    Números del rango que ya son un documento emitido.

    Es la validación GEI005 ("Existe DTE en el rango informado") hecha del
    lado de acá: mandar un rango con un documento adentro vuelve rechazado, y
    además querría decir que se estuvo por declarar inexistente algo que sí
    se emitió.
    """
    return sorted(DocumentoElectronico.objects.filter(
        tipo_documento=tipo_documento,
        establecimiento=f'{int(establecimiento):03d}',
        punto_expedicion=f'{int(punto_expedicion):03d}',
        numero__gte=desde, numero__lte=hasta,
    ).values_list('numero', flat=True))


def numeros_ya_inutilizados(tipo_documento, establecimiento, punto_expedicion,
                            desde, hasta):
    """
    Números del rango que ya están declarados inutilizados (GEI005a).

    Solo cuentan los eventos que el SIFEN no rechazó: uno rechazado no
    inutilizó nada.
    """
    ocupados = set()
    eventos = EventoDocumento.objects.filter(
        tipo=EventoDocumento.TIPO_INUTILIZACION,
        tipo_documento=tipo_documento,
        establecimiento=f'{int(establecimiento):03d}',
        punto_expedicion=f'{int(punto_expedicion):03d}',
        numero_desde__lte=hasta, numero_hasta__gte=desde,
    ).exclude(estado=EventoDocumento.ESTADO_RECHAZADO)
    for evento in eventos:
        ocupados.update(range(max(evento.numero_desde, desde),
                              min(evento.numero_hasta, hasta) + 1))
    return sorted(ocupados)


def huecos_de_numeracion(tipo_documento, establecimiento, punto_expedicion):
    """
    Números ya consumidos por la secuencia que no terminaron en un documento
    ni están inutilizados: los candidatos a inutilizar.

    Existen porque `SecuenciaComprobante.siguiente()` reserva el número
    dentro de la transacción del cobro. Si esa transacción se revierte el
    número vuelve atrás y no hay hueco; pero si el comprobante se creó y
    después se borró a mano, o si el número se tomó en una operación que
    quedó a medias fuera de la transacción, el hueco queda. Esta función es
    la que lo encuentra, porque nadie va a notarlo mirando el correlativo.
    """
    est = f'{int(establecimiento):03d}'
    punto = f'{int(punto_expedicion):03d}'
    try:
        secuencia = SecuenciaComprobante.objects.get(
            tipo_documento=tipo_documento,
            establecimiento=est, punto_expedicion=punto)
    except SecuenciaComprobante.DoesNotExist:
        return []

    if secuencia.ultimo_numero < secuencia.numero_desde:
        return []

    emitidos = set(numeros_ocupados(
        tipo_documento, est, punto, secuencia.numero_desde, secuencia.ultimo_numero))
    inutilizados = set(numeros_ya_inutilizados(
        tipo_documento, est, punto, secuencia.numero_desde, secuencia.ultimo_numero))
    return [n for n in range(secuencia.numero_desde, secuencia.ultimo_numero + 1)
            if n not in emitidos and n not in inutilizados]


# ─── Plazos de la inutilización ──────────────────────────────────────────────
#
# Tabla J, fila 2, pone dos límites y son de naturaleza distinta:
#
#   · «Dentro de los 15 primeros días del mes siguiente al acaecimiento del
#     hecho» — es una obligación de comunicar. **No bloquea**: ver
#     `advertencia_de_plazo_inutilizacion()`.
#   · «Y hasta fecha límite de validez del timbrado (plazo del sistema)» — ese
#     sí lo hace cumplir el SIFEN, así que bloquea.


def fecha_del_hecho(tipo_documento, establecimiento, punto_expedicion, hasta):
    """
    Cuándo se produjo el salto de numeración, o None si todavía no se produjo.

    El Manual cuenta el plazo desde «el acaecimiento del hecho» y no dice
    cuál es la fecha de un número que nunca existió. La lectura que se toma
    acá: el hecho queda consumado cuando el correlativo siguió de largo, o
    sea en la fecha del primer documento emitido **después** del rango. Si no
    hay ninguno, los números están reservados pero la secuencia todavía no
    saltó: no hay hecho que comunicar y por eso devuelve None.
    """
    siguiente = DocumentoElectronico.objects.filter(
        tipo_documento=tipo_documento,
        establecimiento=f'{int(establecimiento):03d}',
        punto_expedicion=f'{int(punto_expedicion):03d}',
        numero__gt=int(hasta),
    ).order_by('numero').first()
    if siguiente is None or not siguiente.fecha_emision:
        return None
    return timezone.localtime(siguiente.fecha_emision).date()


def fecha_limite_inutilizacion(fecha_hecho: date) -> date:
    """El 15 del mes siguiente al hecho."""
    mes, anio = fecha_hecho.month + 1, fecha_hecho.year
    if mes > 12:
        mes, anio = 1, anio + 1
    return date(anio, mes, EventoDocumento.DIA_LIMITE_INUTILIZACION)


def advertencia_de_plazo_inutilizacion(tipo_documento, establecimiento,
                                       punto_expedicion, hasta) -> str:
    """
    Aviso si el plazo para comunicar la inutilización ya pasó. Cadena vacía
    si está en plazo o si no se puede fechar el hecho.

    **Avisa pero no impide**, a diferencia del plazo de cancelación, y la
    razón es que no hay camino alternativo: vencida la cancelación queda la
    nota de crédito, pero un número saltado que no se declara no tiene otra
    forma de cerrarse y el correlativo queda roto para siempre. Declararlo
    tarde es peor que a tiempo y mejor que nunca; quien decide asumir esa
    diferencia es el contribuyente, no este módulo.
    """
    hecho = fecha_del_hecho(tipo_documento, establecimiento,
                            punto_expedicion, hasta)
    if hecho is None:
        return ''
    limite = fecha_limite_inutilizacion(hecho)
    hoy = timezone.localdate()
    if hoy <= limite:
        return ''
    return (f'El salto de numeración es del {hecho:%d/%m/%Y} y debía '
            f'comunicarse antes del {limite:%d/%m/%Y} (Manual, Tabla J). '
            f'Se puede declarar igual —dejar el hueco sin declarar es peor—, '
            f'pero es una comunicación fuera de plazo.')


def timbrado_vencido() -> str:
    """
    Motivo si el timbrado ya no está vigente, cadena vacía si lo está o si no
    hay fecha de vencimiento cargada.

    Este límite sí lo aplica el SIFEN («plazo del sistema»), así que impide
    registrar: un rango de un timbrado vencido vuelve rechazado.
    """
    from .payload import _fiscal

    crudo = str(_fiscal().get('timbrado_vto') or '').strip()
    if not crudo:
        return ''
    try:
        vence = date.fromisoformat(crudo[:10])
    except ValueError:
        # Una fecha mal cargada en el .env no puede frenar una declaración.
        logger.warning('FISCAL_TIMBRADO_VTO no es una fecha ISO: %r', crudo)
        return ''
    if timezone.localdate() <= vence:
        return ''
    return (f'El timbrado venció el {vence:%d/%m/%Y}. Ya no se puede '
            f'inutilizar numeración suya: el SIFEN la rechaza.')


@transaction.atomic
def registrar_inutilizacion(*, tipo_documento, establecimiento,
                            punto_expedicion, desde, hasta, motivo, usuario,
                            timbrado=None) -> EventoDocumento:
    """
    Deja la inutilización registrada y pendiente de envío. No transmite.

    El timbrado, si no se pasa, sale de la configuración fiscal vigente: es
    el que tiene autorizado el talonario que se está inutilizando.
    """
    from .payload import _fiscal

    desde, hasta = int(desde), int(hasta)
    timbrado = (timbrado or _fiscal().get('timbrado', '')).strip()

    vencido = timbrado_vencido()
    if vencido:
        raise EventoNoPermitido(vencido)

    ocupados = numeros_ocupados(tipo_documento, establecimiento,
                                punto_expedicion, desde, hasta)
    if ocupados:
        muestra = ', '.join(
            numeracion.formatear(establecimiento, punto_expedicion, n)
            for n in ocupados[:5])
        raise EventoNoPermitido(
            f'En el rango hay {len(ocupados)} comprobante(s) ya emitido(s) '
            f'({muestra}{"…" if len(ocupados) > 5 else ""}). Un número '
            f'emitido no se inutiliza: se cancela.')

    repetidos = numeros_ya_inutilizados(tipo_documento, establecimiento,
                                        punto_expedicion, desde, hasta)
    if repetidos:
        raise EventoNoPermitido(
            f'{len(repetidos)} número(s) del rango ya estaban declarados '
            f'inutilizados (desde el {repetidos[0]}).')

    tarde = advertencia_de_plazo_inutilizacion(
        tipo_documento, establecimiento, punto_expedicion, hasta)
    if tarde:
        logger.warning('Inutilización fuera de plazo (%s-%s, %s a %s): %s',
                       establecimiento, punto_expedicion, desde, hasta, tarde)

    evento = EventoDocumento(
        tipo=EventoDocumento.TIPO_INUTILIZACION,
        timbrado=timbrado,
        establecimiento=f'{int(establecimiento):03d}',
        punto_expedicion=f'{int(punto_expedicion):03d}',
        numero_desde=desde,
        numero_hasta=hasta,
        tipo_documento=tipo_documento,
        motivo=(motivo or '').strip(),
        creado_por=usuario,
    )
    evento.full_clean(exclude=['xml_enviado'])
    evento.save()
    logger.info('Inutilización registrada: %s por %s', evento.rango_legible, usuario)
    return evento


# ─── Transmitir ──────────────────────────────────────────────────────────────

def _datos_para_sifen(evento) -> dict:
    """
    El cuerpo que espera `xmlgen` para cada evento.

    Los nombres de las claves son los de la librería, no los del manual: es
    la frontera, y respetarlos acá evita tener que recordarlos en el resto
    del código. `xmlgen` **no valida, interpola**: un campo faltante termina
    como el string "undefined" adentro del XML, así que lo que se manda tiene
    que estar completo antes de llegar.
    """
    if evento.tipo == EventoDocumento.TIPO_CANCELACION:
        return {'cdc': evento.documento.cdc, 'motivo': evento.motivo}
    return {
        'timbrado': evento.timbrado,
        'establecimiento': evento.establecimiento,
        'punto': evento.punto_expedicion,
        'desde': evento.numero_desde,
        'hasta': evento.numero_hasta,
        'tipoDocumento': evento.tipo_documento,
        'motivo': evento.motivo,
    }


def transmitir(evento) -> EventoDocumento:
    """
    Manda el evento al SIFEN a través del sidecar. Nunca lanza: deja el
    resultado en el propio evento y lo devuelve.

    Misma distinción que en la cola de documentos: un `ErrorSidecar` es
    reintentable (la red no dice nada sobre el evento) y un `RechazoSifen` es
    terminal.
    """
    evento.intentos_envio += 1
    evento.ultimo_intento = timezone.now()

    try:
        respuesta = sifen_client.enviar_evento(evento.tipo, _datos_para_sifen(evento))
    except sifen_client.RechazoSifen as e:
        evento.estado = EventoDocumento.ESTADO_RECHAZADO
        evento.codigo_respuesta = str(e.codigo)[:10]
        evento.respuesta_sifen = (e.respuesta or str(e))[:5000]
        evento.save(update_fields=['estado', 'codigo_respuesta', 'respuesta_sifen',
                                   'intentos_envio', 'ultimo_intento'])
        logger.error('Evento %s rechazado: %s', evento.pk, e)
        return evento
    except sifen_client.ErrorSidecar as e:
        evento.respuesta_sifen = str(e)[:2000]
        evento.save(update_fields=['respuesta_sifen', 'intentos_envio',
                                   'ultimo_intento'])
        logger.warning('Evento %s: intento %s fallido — %s',
                       evento.pk, evento.intentos_envio, e)
        return evento
    except Exception as e:  # noqa: BLE001 — se registra y se reintenta
        logger.exception('Evento %s: error inesperado', evento.pk)
        evento.respuesta_sifen = f'Error inesperado: {e}'[:2000]
        evento.save(update_fields=['respuesta_sifen', 'intentos_envio',
                                   'ultimo_intento'])
        return evento

    estado = (respuesta.get('estado') or '').lower()
    evento.codigo_respuesta = str(respuesta.get('codigo') or '')[:10]
    evento.respuesta_sifen = str(
        respuesta.get('respuesta') or respuesta.get('mensaje') or respuesta)[:5000]
    evento.xml_enviado = respuesta.get('xml', '') or evento.xml_enviado

    if estado.startswith('aprobado'):
        evento.estado = EventoDocumento.ESTADO_APROBADO
        evento.fecha_aprobacion = timezone.now()
    elif estado == 'rechazado':
        evento.estado = EventoDocumento.ESTADO_RECHAZADO
    else:
        # Respuesta que no sabemos leer: se deja enviado para reintentar y
        # consultar, en vez de dar por hecho cualquiera de las dos cosas.
        evento.estado = EventoDocumento.ESTADO_ENVIADO

    evento.save(update_fields=['estado', 'codigo_respuesta', 'respuesta_sifen',
                               'xml_enviado', 'fecha_aprobacion',
                               'intentos_envio', 'ultimo_intento'])

    if (evento.estado == EventoDocumento.ESTADO_APROBADO
            and evento.tipo == EventoDocumento.TIPO_CANCELACION):
        _marcar_documento_cancelado(evento)

    logger.info('Evento %s: %s (%s)', evento.pk, evento.estado,
                evento.codigo_respuesta)
    return evento


def _marcar_documento_cancelado(evento):
    """
    El DTE pasa a cancelado recién cuando el SIFEN aprobó el evento.

    No toca el cobro ni el stock: cancelar el comprobante fiscal y devolver
    la mercadería son dos cosas distintas, y mezclarlas haría que una
    corrección de papeles mueva el inventario.
    """
    documento = evento.documento
    documento.estado = DocumentoElectronico.ESTADO_CANCELADO
    documento.save(update_fields=['estado'])
    logger.info('DTE %s cancelado por evento %s',
                documento.numero_completo, evento.pk)


def pendientes(limite=None):
    """Eventos que todavía tiene sentido transmitir."""
    from django.conf import settings

    max_intentos = getattr(settings, 'SIFEN', {}).get('max_intentos', 10)
    consulta = (EventoDocumento.objects
                .filter(estado__in=EventoDocumento.ESTADOS_TRANSMITIBLES,
                        intentos_envio__lt=max_intentos)
                .select_related('documento', 'creado_por')
                .order_by('fecha_creacion'))
    return consulta[:limite] if limite else consulta


def transmitir_pendientes(limite=None):
    """
    Recorre la cola de eventos. Uno por transacción, igual que los
    documentos: un rechazo al final no puede deshacer lo que ya se mandó.
    """
    resultados = []
    for evento in list(pendientes(limite)):
        with transaction.atomic():
            resultados.append(transmitir(evento))
    return resultados
