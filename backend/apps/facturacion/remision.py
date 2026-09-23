"""
Nota de remisión electrónica.

Es el documento que **sustenta el traslado de mercadería**, no la venta. Esa
distinción es la que gobierna todo este módulo, y viene de la norma, no de una
decisión de diseño:

  · **Decreto 6.539/2005, art. 30** — las notas de remisión "son los documentos
    que sustentan el traslado de mercaderías dentro del territorio nacional,
    por cualquier motivo", y "deberán ser expedidas en forma previa al traslado
    y acompañar a la mercadería en tránsito en todo el trayecto".
  · **Decreto 6.539/2005, art. 31** — está obligada a expedirla toda persona
    física o jurídica "propietaria o responsable de los bienes".
  · **RG 41/2014, art. 5** — "La emisión de la nota de remisión no será
    necesaria cuando la factura u otro comprobante de venta contenga todos los
    datos requeridos en los artículos precedentes."

Consecuencia práctica para el mostrador, y la razón por la que esto es un
**botón** y no un paso automático del cobro: **no toda venta lleva remisión.**
Si el cliente se lleva los pisos en su propia camioneta con la factura en la
mano, la mercadería viaja respaldada por el comprobante de venta y no hace
falta nada más. La remisión aparece cuando el local despacha: flete propio o
contratado, entrega a domicilio, traslado entre locales. Por eso el disparador
vive en la pantalla de Pedidos, donde se sabe si hay entrega, y no en caja.

El tipo de documento es el 7 del Manual Técnico V150 y su motivo sale de la
tabla E502, que tiene catorce entradas — "traslado por ventas" es solo una.

Diferencias con `emisor.emitir_para_pago()`, a propósito:

  · **Esto sí lanza.** Emitir la factura no puede tumbar un cobro porque hay
    alguien esperando en el mostrador; acá la acción es deliberada y quien la
    pidió necesita saber por qué falló.
  · **No toca stock.** La mercadería ya se descontó al confirmar el pago. Una
    remisión describe un movimiento, no cambia existencias.
"""
import logging

from django.db import transaction
from django.utils import timezone

from . import cdc as cdc_mod
from . import codigos
from .models import DocumentoElectronico, SecuenciaComprobante

logger = logging.getLogger(__name__)


class RemisionInvalida(ValueError):
    """No se puede emitir la nota de remisión pedida."""


def validar(pago):
    """
    ¿Se puede emitir la remisión de este cobro?

    Se valida todo antes de tomar el número: si el correlativo avanza y
    después falla algo, queda un hueco que hay que declararle a la DNIT por
    el evento de inutilización. Barato de evitar acá.
    """
    if pago is None:
        raise RemisionInvalida('No se indicó sobre qué cobro.')

    pedido = pago.pedido
    traslado = getattr(pedido, 'datos_traslado', None)
    if traslado is None:
        raise RemisionInvalida(
            f'El pedido {pedido.numero} no tiene cargados los datos del '
            f'traslado (motivo, vehículo, dirección de entrega). Sin eso no '
            f'hay remisión: son los datos que el documento declara.')

    # NT 010: los kilómetros (E505) pasaron a ser obligatorios. El payload
    # también lo verifica, pero ahí ya sería tarde — el número estaría tomado.
    if not traslado.kilometros:
        raise RemisionInvalida(
            f'El traslado del pedido {pedido.numero} no tiene los kilómetros '
            f'estimados de recorrido, que la NT 010 volvió obligatorios '
            f'(campo E505).')

    # NT 023: la remisión nunca puede ir a un receptor innominado. Tiene
    # sentido — traslada algo hacia alguien concreto, con una dirección.
    factura = pago.documento_electronico
    ruc = (factura.receptor_ruc if factura is not None
           else pedido.cliente_ruc or '').strip()
    if not ruc:
        raise RemisionInvalida(
            f'El pedido {pedido.numero} no identifica al cliente. Una nota de '
            f'remisión no admite receptor innominado (NT 023): hay que cargar '
            f'el RUC o la cédula antes de emitirla.')

    existente = DocumentoElectronico.objects.filter(
        pago=pago, tipo_documento=codigos.TIPO_DE_NOTA_REMISION,
    ).exclude(estado=DocumentoElectronico.ESTADO_RECHAZADO).first()
    if existente is not None:
        raise RemisionInvalida(
            f'El pedido {pedido.numero} ya tiene la nota de remisión '
            f'{existente.numero_completo}. Para anularla hay que cancelar el '
            f'documento ante el SIFEN, no emitir una segunda.')

    return traslado


@transaction.atomic
def emitir(pago, *, usuario):
    """
    Emite la nota de remisión que respalda el traslado de un pedido cobrado.

    Devuelve el DocumentoElectronico en estado 'pendiente': lo transmite
    después el worker de la cola, igual que cualquier otro documento. El KuDE
    —que es el papel que viaja con la mercadería— se baja de
    `GET /facturacion/documentos/<pk>/kude/`.

    Todo corre en una transacción junto con la toma del número, por lo mismo
    de siempre: si algo falla el correlativo vuelve atrás.
    """
    validar(pago)

    from django.conf import settings
    fiscal = getattr(settings, 'DATOS_FISCALES', {})
    pedido = pago.pedido
    factura = pago.documento_electronico

    # El emisor se copia de la factura cuando existe, y solo si no, de
    # settings. Mismo criterio que la nota de crédito: los dos documentos de
    # una misma operación tienen que declarar el mismo timbrado, aunque el
    # negocio haya cambiado de timbrado desde entonces.
    if factura is not None:
        establecimiento = factura.establecimiento
        punto_expedicion = factura.punto_expedicion
        tipo_contribuyente = int(factura.cdc[24])
    else:
        establecimiento = f"{int(fiscal['establecimiento']):03d}"
        punto_expedicion = f"{int(fiscal['punto_expedicion']):03d}"
        tipo_contribuyente = fiscal.get('tipo_contribuyente', 2)

    numero, numero_completo = SecuenciaComprobante.siguiente(
        codigos.TIPO_DE_NOTA_REMISION, establecimiento, punto_expedicion)

    ahora = timezone.now()
    codigo_seguridad = cdc_mod.generar_codigo_seguridad(numero)
    cdc = cdc_mod.generar(
        ruc_emisor=(factura.emisor_ruc if factura is not None
                    else fiscal.get('ruc', '')),
        establecimiento=establecimiento,
        punto_expedicion=punto_expedicion,
        numero=numero,
        tipo_contribuyente=tipo_contribuyente,
        fecha_emision=ahora.date(),
        tipo_documento=codigos.TIPO_DE_NOTA_REMISION,
        codigo_seguridad=codigo_seguridad,
    )

    if factura is not None:
        emisor = {
            'emisor_ruc': factura.emisor_ruc,
            'emisor_razon_social': factura.emisor_razon_social,
            'emisor_direccion': factura.emisor_direccion,
            'emisor_telefono': factura.emisor_telefono,
            'emisor_timbrado': factura.emisor_timbrado,
            'emisor_timbrado_vto': factura.emisor_timbrado_vto,
        }
        receptor = {
            'receptor_ruc': factura.receptor_ruc,
            'receptor_razon_social': factura.receptor_razon_social,
            'receptor_direccion': factura.receptor_direccion,
            'receptor_telefono': factura.receptor_telefono,
            'receptor_email': factura.receptor_email,
            'receptor_naturaleza': factura.receptor_naturaleza,
        }
    else:
        ruc = (pedido.cliente_ruc or '').strip()
        emisor = {
            'emisor_ruc': fiscal.get('ruc', ''),
            'emisor_razon_social': fiscal.get('razon_social', ''),
            'emisor_direccion': fiscal.get('direccion', ''),
            'emisor_telefono': fiscal.get('telefono', ''),
            'emisor_timbrado': fiscal.get('timbrado', ''),
            'emisor_timbrado_vto': fiscal.get('timbrado_vto', ''),
        }
        receptor = {
            'receptor_ruc': ruc,
            'receptor_razon_social': pedido.cliente_nombre or '',
            'receptor_direccion': '',
            'receptor_telefono': pedido.cliente_telefono or '',
            'receptor_email': '',
            'receptor_naturaleza': codigos.naturaleza_receptor(ruc),
        }

    # Los montos no forman parte de una remisión: el Manual V150 exceptúa al
    # tipo 7 del valor total por ítem (E720) y del grupo de IVA (E730). Se
    # guarda igual el total del cobro porque la columna no admite nulo y
    # porque sirve de referencia interna al mirar el documento; el XML no lo
    # lleva. Los desgloses quedan en cero a propósito: declarar un IVA en un
    # documento que no lo tiene sería peor que no declarar nada.
    remision = DocumentoElectronico.objects.create(
        pago=pago,
        cdc=cdc,
        tipo_documento=codigos.TIPO_DE_NOTA_REMISION,
        establecimiento=establecimiento,
        punto_expedicion=punto_expedicion,
        numero=numero,
        numero_completo=numero_completo,
        codigo_seguridad=codigo_seguridad,
        fecha_emision=ahora,

        # La remisión se vincula a su factura por CDC cuando la hay. El SIFEN
        # además registra esa vinculación solo (Manual §11.3, ejemplo 2:
        # "vinculación automática de la nota de remisión electrónica a una
        # factura electrónica" al aprobarse), pero declararla acá deja el
        # dato en la base sin depender de consultar al SIFEN.
        documento_asociado_cdc=(factura.cdc if factura is not None else ''),

        **emisor,
        **receptor,

        condicion_venta=(factura.condicion_venta if factura is not None
                         else codigos.codigo_condicion_venta('contado')),
        medio_pago=(factura.medio_pago if factura is not None
                    else codigos.codigo_medio_pago(pago.medio_pago)),
        total=pago.monto,

        creado_por=usuario,
    )

    logger.info('Nota de remisión %s emitida para el pedido %s (CDC %s)',
                remision.numero_completo, pedido.numero, remision.cdc)
    return remision
