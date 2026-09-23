"""
Eventos del rol **receptor**: lo que el local declara sobre un DTE ajeno.

`eventos.py` cubre el otro lado — cancelar o inutilizar comprobantes propios.
Acá el documento lo emitió un proveedor y de él solo tenemos el CDC, que es
justamente lo que el SIFEN pide para identificarlo. Por eso es un módulo
aparte y no un tipo más de aquel: no hay `DocumentoElectronico` local al que
apuntar.

Los cuatro tipos, y la diferencia que importa (Manual §11.2.5):

  · **Conclusivos** — conformidad y disconformidad. Pueden obligar al emisor
    a hacer algo: emitir una nota de crédito, cancelar el DTE.
  · **Informativos** — desconocimiento y notificación de recepción. Dejan una
    marca y no generan ninguna acción del otro lado.

La forma de `data` de cada uno está **verificada contra la librería de la
DNIT** (`jsonEventoMain.service.js`), no deducida del manual. Los nombres de
las claves son los de la librería.

Igual que los eventos del emisor: se guardan **antes** de transmitirse, para
que un corte de red no pierda la declaración.
"""
import logging

from django.db import transaction
from django.utils import timezone

from . import sifen_client
from .cdc import fecha_de_emision as _fecha_de_emision_del_cdc
from .models import EventoReceptor

logger = logging.getLogger(__name__)


class EventoReceptorInvalido(ValueError):
    """Los datos del evento no alcanzan para emitirlo."""


def _validar_cdc(cdc):
    cdc = str(cdc or '').strip()
    if len(cdc) != 44 or not cdc.isdigit():
        raise EventoReceptorInvalido(
            f'El CDC tiene que tener 44 dígitos; vino "{cdc}" ({len(cdc)}).')
    return cdc


def _a_datetime(valor):
    """
    Deja un valor de fecha como datetime con zona, o None.

    Acepta texto porque es como viene del formulario: el campo es un
    `datetime-local`, que manda `AAAA-MM-DDTHH:MM` sin zona. Se interpreta
    como hora de Asunción, que es la del local.
    """
    if not valor:
        return None
    if isinstance(valor, str):
        from django.utils.dateparse import parse_datetime
        valor = parse_datetime(valor)
        if valor is None:
            raise EventoReceptorInvalido(
                'No se entiende la fecha. Se espera AAAA-MM-DDTHH:MM:SS.')
    if timezone.is_naive(valor):
        valor = timezone.make_aware(valor)
    return valor


def _validar_motivo(motivo):
    motivo = str(motivo or '').strip()
    if not (EventoReceptor.MOTIVO_MIN <= len(motivo) <= EventoReceptor.MOTIVO_MAX):
        raise EventoReceptorInvalido(
            f'El motivo tiene que tener entre {EventoReceptor.MOTIVO_MIN} y '
            f'{EventoReceptor.MOTIVO_MAX} caracteres. El SIFEN rechaza un '
            f'motivo de dos letras.')
    return motivo


# ─── Plazos ──────────────────────────────────────────────────────────────────
#
# El lado emisor (`eventos.py`) cuenta las 48/168 horas desde que el SIFEN
# aprobó el documento. Acá el reloj es otro: el documento es de un proveedor,
# nunca vimos su aprobación, y el Manual (Tabla J, filas 10 a 13) cuenta
# **45 días desde la fecha de emisión**. Esa fecha está adentro del CDC, así
# que no hace falta pedírsela a nadie.


def dias_restantes_para_registrar(cdc) -> int | None:
    """
    Días que quedan para manifestarse sobre ese documento. Negativo si el
    plazo ya venció, None si el CDC no dice su fecha de emisión.
    """
    emision = _fecha_de_emision_del_cdc(cdc)
    if emision is None:
        return None
    limite = emision + timezone.timedelta(
        days=EventoReceptor.DIAS_PARA_REGISTRAR)
    # La fecha del CDC es un día, no un instante: el plazo se agota al final
    # del día 45, no a la hora en que se emitió el documento.
    return (limite - timezone.localdate()).days


def motivo_por_el_que_no_se_puede_registrar(cdc) -> str:
    """
    Cadena vacía si todavía se puede registrar un evento sobre ese CDC; si
    no, el motivo en castellano llano.
    """
    restantes = dias_restantes_para_registrar(cdc)
    if restantes is None:
        return ('El CDC no lleva una fecha de emisión válida en las '
                'posiciones 26 a 33, así que no se puede saber si el plazo '
                'sigue abierto. Conviene revisar que esté bien copiado.')
    if restantes < 0:
        return (f'Venció el plazo de {EventoReceptor.DIAS_PARA_REGISTRAR} '
                f'días desde la emisión para manifestarse sobre este '
                f'documento (se pasó por {abs(restantes)} día(s)). El SIFEN '
                f'lo va a rechazar.')
    return ''


def dias_restantes_para_corregir(evento) -> int:
    """
    Días que quedan para corregir un evento ya registrado (Tabla K): 15
    desde el registro del primero, y una sola corrección por evento.

    El evento de corrección **todavía no se emite** —`xmlgen` no trae
    generador para él—, así que por ahora esto sirve para decirle a quien
    mira la pantalla si se equivocó a tiempo o si ya no hay vuelta atrás.
    """
    registro = timezone.localtime(evento.fecha_creacion).date()
    limite = registro + timezone.timedelta(
        days=EventoReceptor.DIAS_PARA_CORREGIR)
    return (limite - timezone.localdate()).days


def se_puede_corregir(evento) -> bool:
    """
    ¿Sigue abierta la ventana para corregir este evento?

    Solo sobre un evento que el SIFEN aceptó: corregir algo que volvió
    rechazado no es una corrección, es volver a registrarlo.
    """
    return (evento.estado == EventoReceptor.ESTADO_APROBADO
            and dias_restantes_para_corregir(evento) >= 0)


# ─── Registrar ───────────────────────────────────────────────────────────────

@transaction.atomic
def registrar(*, tipo, cdc, usuario, motivo='', tipo_conformidad=None,
              fecha_recepcion=None, fecha_emision_documento=None,
              total_documento=None) -> EventoReceptor:
    """
    Guarda el evento en estado 'pendiente'. No transmite.

    Valida acá y no al transmitir para que el error salga con la persona
    delante, y no horas después en el log del worker.
    """
    cdc = _validar_cdc(cdc)

    if tipo not in dict(EventoReceptor.TIPOS):
        raise EventoReceptorInvalido(
            f'"{tipo}" no es un evento del receptor. Opciones: '
            + ', '.join(dict(EventoReceptor.TIPOS)))

    # Antes que los campos propios de cada tipo: si el plazo venció, no tiene
    # sentido hacer que alguien complete el formulario entero para enterarse
    # después.
    fuera_de_plazo = motivo_por_el_que_no_se_puede_registrar(cdc)
    if fuera_de_plazo:
        raise EventoReceptorInvalido(fuera_de_plazo)

    if tipo == EventoReceptor.TIPO_CONFORMIDAD:
        if tipo_conformidad not in (EventoReceptor.CONFORMIDAD_TOTAL,
                                    EventoReceptor.CONFORMIDAD_PARCIAL):
            raise EventoReceptorInvalido(
                'La conformidad tiene que decir si es total (1) o parcial (2).')
        # La librería exige la fecha estimada de recepción solo en la parcial.
        if (tipo_conformidad == EventoReceptor.CONFORMIDAD_PARCIAL
                and not fecha_recepcion):
            raise EventoReceptorInvalido(
                'Una conformidad parcial tiene que declarar la fecha estimada '
                'de recepción de la mercadería.')

    elif tipo == EventoReceptor.TIPO_DISCONFORMIDAD:
        motivo = _validar_motivo(motivo)

    elif tipo == EventoReceptor.TIPO_DESCONOCIMIENTO:
        motivo = _validar_motivo(motivo)
        if not (fecha_emision_documento and fecha_recepcion):
            raise EventoReceptorInvalido(
                'El desconocimiento tiene que declarar la fecha de emisión del '
                'documento y la de recepción.')

    elif tipo == EventoReceptor.TIPO_NOTIFICACION:
        if not (fecha_emision_documento and fecha_recepcion):
            raise EventoReceptorInvalido(
                'La notificación de recepción tiene que declarar la fecha de '
                'emisión del documento y la de recepción.')
        if total_documento is None:
            raise EventoReceptorInvalido(
                'La notificación de recepción tiene que declarar el total del '
                'documento en guaraníes.')

    # Las fechas llegan como texto del formulario (`datetime-local`, sin
    # zona). Se normalizan ANTES de guardar para que lo almacenado sea
    # consistente con el resto del sistema, que trabaja en UTC con
    # `USE_TZ=True`. Sin esto Django avisa con un RuntimeWarning y guarda la
    # hora interpretándola como UTC, o sea corrida cuatro horas.
    fecha_recepcion = _a_datetime(fecha_recepcion)
    fecha_emision_documento = _a_datetime(fecha_emision_documento)

    vivo = EventoReceptor.objects.filter(cdc=cdc, tipo=tipo).exclude(
        estado=EventoReceptor.ESTADO_RECHAZADO).first()
    if vivo is not None:
        raise EventoReceptorInvalido(
            f'Ya hay un evento de {vivo.get_tipo_display().lower()} para ese '
            f'documento ({vivo.get_estado_display()}). Manifestarse dos veces '
            f'sobre lo mismo lo rechaza el SIFEN.')

    evento = EventoReceptor.objects.create(
        tipo=tipo, cdc=cdc, motivo=motivo,
        tipo_conformidad=tipo_conformidad,
        fecha_recepcion=fecha_recepcion,
        fecha_emision_documento=fecha_emision_documento,
        total_documento=total_documento,
        creado_por=usuario,
    )
    logger.info('Evento de receptor %s registrado sobre el CDC %s',
                tipo, cdc)
    return evento


def _fecha_sifen(momento) -> str:
    """
    Fecha en el formato que exige la librería: 19 caracteres exactos,
    `AAAA-MM-DDTHH:MM:SS`.

    La librería lo valida por **largo** (`length != 19`), así que un
    `isoformat()` con microsegundos o con zona horaria lo rechaza.

    Acepta también un string porque es como llega desde la API: el campo del
    formulario es un `datetime-local` y el evento se transmite en el mismo
    request, antes de que el modelo haya convertido nada. Sin esto, el evento
    quedaba registrado pero la transmisión moría con
    `'str' object has no attribute 'utcoffset'` — un error que no dice nada
    sobre la fecha.

    Y una fecha sin zona (la que manda `datetime-local`) se interpreta como
    hora de Asunción, que es la del local: dejarla naive haría que el SIFEN
    recibiera una hora corrida.
    """
    if not momento:
        return ''

    if isinstance(momento, str):
        from django.utils.dateparse import parse_datetime
        parseada = parse_datetime(momento)
        if parseada is None:
            raise EventoReceptorInvalido(
                f'No se entiende la fecha "{momento}". Se espera '
                f'AAAA-MM-DDTHH:MM:SS.')
        momento = parseada

    if timezone.is_naive(momento):
        momento = timezone.make_aware(momento)

    return timezone.localtime(momento).strftime('%Y-%m-%dT%H:%M:%S')


def _datos_para_sifen(evento) -> dict:
    """
    El cuerpo que espera `xmlgen` para cada evento del receptor.

    Verificado contra `jsonEventoMain.service.js`. `xmlgen` **no valida,
    interpola**: un campo que falte termina como el string "undefined" dentro
    del XML, así que lo que sale de acá tiene que estar completo.
    """
    if evento.tipo == EventoReceptor.TIPO_CONFORMIDAD:
        datos = {'cdc': evento.cdc, 'tipoConformidad': evento.tipo_conformidad}
        if evento.tipo_conformidad == EventoReceptor.CONFORMIDAD_PARCIAL:
            datos['fechaRecepcion'] = _fecha_sifen(evento.fecha_recepcion)
        return datos

    if evento.tipo == EventoReceptor.TIPO_DISCONFORMIDAD:
        return {'cdc': evento.cdc, 'motivo': evento.motivo}

    # Desconocimiento y notificación comparten casi todo: identifican al DTE
    # y a quien se manifiesta. El emisor de esos datos somos nosotros, así
    # que salen de la configuración fiscal y no del evento.
    from .payload import _fiscal
    fiscal = _fiscal()
    ruc = str(fiscal.get('ruc') or '')
    base = {
        'cdc': evento.cdc,
        'fechaEmision': _fecha_sifen(evento.fecha_emision_documento),
        'fechaRecepcion': _fecha_sifen(evento.fecha_recepcion),
        'nombre': fiscal.get('razon_social', ''),
        'ruc': ruc,
    }

    if evento.tipo == EventoReceptor.TIPO_DESCONOCIMIENTO:
        base['motivo'] = evento.motivo
        return base

    base['totalPYG'] = float(evento.total_documento or 0)
    return base


def transmitir(evento) -> EventoReceptor:
    """
    Manda el evento al SIFEN. Nunca lanza: deja el resultado en el evento.

    Misma distinción de siempre: `ErrorSidecar` es reintentable (la red no
    dice nada sobre el evento) y `RechazoSifen` es terminal.
    """
    evento.intentos_envio += 1
    evento.ultimo_intento = timezone.now()

    try:
        respuesta = sifen_client.enviar_evento(
            evento.tipo, _datos_para_sifen(evento))
    except sifen_client.RechazoSifen as e:
        evento.estado = EventoReceptor.ESTADO_RECHAZADO
        evento.codigo_respuesta = str(e.codigo)[:10]
        evento.respuesta_sifen = (e.respuesta or str(e))[:5000]
        evento.save(update_fields=['estado', 'codigo_respuesta',
                                   'respuesta_sifen', 'intentos_envio',
                                   'ultimo_intento'])
        logger.error('Evento de receptor %s rechazado: %s', evento.pk, e)
        return evento
    except Exception as e:  # noqa: BLE001 — se registra y se reintenta
        logger.warning('Evento de receptor %s: intento %s fallido — %s',
                       evento.pk, evento.intentos_envio, e)
        evento.respuesta_sifen = str(e)[:2000]
        evento.save(update_fields=['respuesta_sifen', 'intentos_envio',
                                   'ultimo_intento'])
        return evento

    estado = (respuesta.get('estado') or '').lower()
    evento.codigo_respuesta = str(respuesta.get('codigo') or '')[:10]
    evento.respuesta_sifen = str(respuesta.get('respuesta')
                                 or respuesta.get('mensaje') or '')[:5000]
    if estado.startswith('aprobado'):
        evento.estado = EventoReceptor.ESTADO_APROBADO
    elif estado == 'rechazado':
        evento.estado = EventoReceptor.ESTADO_RECHAZADO
    else:
        evento.estado = EventoReceptor.ESTADO_ENVIADO
    evento.save(update_fields=['estado', 'codigo_respuesta', 'respuesta_sifen',
                               'intentos_envio', 'ultimo_intento'])
    logger.info('Evento de receptor %s %s', evento.pk, evento.estado)
    return evento


def pendientes(limite=None):
    """Eventos del receptor que todavía tiene sentido transmitir."""
    consulta = EventoReceptor.objects.filter(
        estado__in=EventoReceptor.ESTADOS_TRANSMITIBLES
    ).order_by('fecha_creacion')
    return list(consulta[:limite] if limite else consulta)


def transmitir_pendientes(limite=None):
    """Recorre la cola de eventos del receptor."""
    return [transmitir(e) for e in pendientes(limite)]
