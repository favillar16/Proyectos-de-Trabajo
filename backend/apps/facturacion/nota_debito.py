"""
Nota de débito electrónica.

Es el espejo de la nota de crédito: en vez de revertir parte de una factura,
**agrega** un importe a cobrar sobre una operación ya facturada. Los casos
reales del rubro son intereses por mora, un recupero de flete que no se
facturó en su momento, o un ajuste de precio hacia arriba.

Dos diferencias con la nota de crédito que explican por qué es un módulo
aparte y no un parámetro de aquel:

  · **Nunca toca stock.** Una nota de crédito por devolución repone
    mercadería; un débito no devuelve nada, cobra más por lo mismo. No hay
    ningún caso en que deba mover inventario.
  · **Lleva su propio monto**, que no sale de la factura. La de crédito por
    el total copia los importes del documento que anula; acá el importe es
    nuevo —el interés, el flete— y hay que calcular su IVA desde cero.

Lo que sí comparte: el XML lo arma la misma rama de `payload.py` (el Manual
trata C002=5 y C002=6 juntos, con el mismo grupo E4 y el mismo documento
asociado por CDC), y la numeración corre por una secuencia propia del tipo 6.
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from . import cdc as cdc_mod
from . import codigos
from .models import DocumentoElectronico, SecuenciaComprobante

logger = logging.getLogger(__name__)


class NotaDebitoInvalida(ValueError):
    """No se puede emitir la nota de débito pedida."""


# Motivos que tienen sentido en un débito. Los de devolución quedan afuera a
# propósito: devolver mercadería baja lo que el cliente debe, no lo sube, y
# ofrecerlos acá invitaría a emitir el documento al revés. Para eso está la
# nota de crédito.
MOTIVOS_DEBITO = {
    codigos.MOTIVO_DESCUENTO:          codigos.MOTIVOS_NOTA[codigos.MOTIVO_DESCUENTO],
    codigos.MOTIVO_RECUPERO_COSTO:     codigos.MOTIVOS_NOTA[codigos.MOTIVO_RECUPERO_COSTO],
    codigos.MOTIVO_RECUPERO_GASTO:     codigos.MOTIVOS_NOTA[codigos.MOTIVO_RECUPERO_GASTO],
    codigos.MOTIVO_AJUSTE_PRECIO:      codigos.MOTIVOS_NOTA[codigos.MOTIVO_AJUSTE_PRECIO],
}


def validar(factura, *, motivo, monto):
    """
    ¿Se puede emitir esta nota de débito?

    Se valida todo antes de tomar el número: un correlativo que avanza y
    después falla deja un hueco que hay que declarar por el evento de
    inutilización.
    """
    if factura is None:
        raise NotaDebitoInvalida('No se indicó sobre qué factura.')

    if factura.tipo_documento != codigos.TIPO_DE_FACTURA:
        raise NotaDebitoInvalida(
            f'El documento {factura.numero_completo} no es una factura: una '
            f'nota de débito solo se emite sobre una factura.')

    if motivo not in MOTIVOS_DEBITO:
        opciones = ', '.join(f'{k}={v}' for k, v in MOTIVOS_DEBITO.items())
        raise NotaDebitoInvalida(
            f'El motivo {motivo!r} no corresponde a una nota de débito. '
            f'Opciones: {opciones}. Para devolver mercadería va una nota de '
            f'crédito.')

    if factura.estado == DocumentoElectronico.ESTADO_RECHAZADO:
        raise NotaDebitoInvalida(
            f'La factura {factura.numero_completo} fue rechazada por el '
            f'SIFEN, así que no existe como documento tributario: no hay '
            f'nada sobre qué emitir un débito.')

    try:
        monto = Decimal(str(monto))
    except Exception:
        raise NotaDebitoInvalida(f'Monto inválido: {monto!r}')
    if monto <= 0:
        raise NotaDebitoInvalida(
            'El monto de la nota de débito tiene que ser mayor a cero: es lo '
            'que se le suma a lo que el cliente debe.')

    return monto


@transaction.atomic
def emitir(factura, *, motivo, monto, usuario, tasa_iva=None):
    """
    Emite la nota de débito que suma un importe sobre una factura.

    `monto` es el total **con IVA incluido**, igual que se maneja el precio en
    todo el sistema: en el mostrador nadie razona en base neta. El desglose lo
    calcula `codigos.desglosar_iva`.

    `tasa_iva` en None usa la tasa del 10%, que es la del rubro. Se puede
    forzar para un recupero exento.

    Devuelve el DocumentoElectronico en estado 'pendiente'; lo transmite
    después el worker, igual que cualquier otro.

    A diferencia de la nota de crédito, **no toca stock**: un débito no
    devuelve mercadería.
    """
    monto = validar(factura, motivo=motivo, monto=monto)

    tasa = codigos.TASA_10 if tasa_iva is None else tasa_iva
    if tasa not in codigos.TASAS_VALIDAS:
        raise NotaDebitoInvalida(
            f'La tasa de IVA {tasa!r} no es una de las que acepta el SIFEN.')

    base, iva = codigos.desglosar_iva(monto, tasa)

    numero, numero_completo = SecuenciaComprobante.siguiente(
        codigos.TIPO_DE_NOTA_DEBITO,
        factura.establecimiento,
        factura.punto_expedicion,
    )

    ahora = timezone.now()
    codigo_seguridad = cdc_mod.generar_codigo_seguridad(numero)
    cdc_nota = cdc_mod.generar(
        ruc_emisor=factura.emisor_ruc,
        establecimiento=factura.establecimiento,
        punto_expedicion=factura.punto_expedicion,
        numero=numero,
        # Del CDC de la factura: es el mismo emisor, y así la nota no depende
        # de que settings no haya cambiado desde entonces.
        tipo_contribuyente=int(factura.cdc[24]),
        fecha_emision=ahora.date(),
        tipo_documento=codigos.TIPO_DE_NOTA_DEBITO,
        codigo_seguridad=codigo_seguridad,
    )

    totales = {
        'total_gravado_10': base if tasa == codigos.TASA_10 else Decimal('0'),
        'iva_10':           iva if tasa == codigos.TASA_10 else Decimal('0'),
        'total_gravado_5':  base if tasa == codigos.TASA_5 else Decimal('0'),
        'iva_5':            iva if tasa == codigos.TASA_5 else Decimal('0'),
        'total_exento':     base if tasa == codigos.TASA_0 else Decimal('0'),
    }

    nota = DocumentoElectronico.objects.create(
        pago=factura.pago,
        cdc=cdc_nota,
        tipo_documento=codigos.TIPO_DE_NOTA_DEBITO,
        establecimiento=factura.establecimiento,
        punto_expedicion=factura.punto_expedicion,
        numero=numero,
        numero_completo=numero_completo,
        codigo_seguridad=codigo_seguridad,
        fecha_emision=ahora,

        documento_asociado_cdc=factura.cdc,
        motivo_nota=motivo,

        # El emisor se copia de la factura, no de settings: los dos
        # documentos de una misma operación declaran el mismo timbrado.
        emisor_ruc=factura.emisor_ruc,
        emisor_razon_social=factura.emisor_razon_social,
        emisor_direccion=factura.emisor_direccion,
        emisor_telefono=factura.emisor_telefono,
        emisor_timbrado=factura.emisor_timbrado,
        emisor_timbrado_vto=factura.emisor_timbrado_vto,

        receptor_ruc=factura.receptor_ruc,
        receptor_razon_social=factura.receptor_razon_social,
        receptor_direccion=factura.receptor_direccion,
        receptor_telefono=factura.receptor_telefono,
        receptor_email=factura.receptor_email,
        receptor_naturaleza=factura.receptor_naturaleza,

        condicion_venta=factura.condicion_venta,
        medio_pago=factura.medio_pago,
        total=monto,
        **totales,

        creado_por=usuario,
    )

    logger.info('Nota de débito %s emitida sobre la factura %s por %s '
                '(motivo %s)', nota.numero_completo, factura.numero_completo,
                monto, motivo)
    return nota
