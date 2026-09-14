"""
Nota de crédito electrónica.

Es el documento con el que se anula o corrige una factura ya emitida. Una vez
que una factura salió al SIFEN no se borra ni se edita: se emite una nota de
crédito que la referencia por su CDC. Esa es la regla de fondo, y explica por
qué esto no es "cancelar una venta" sino emitir otro documento.

Cuándo se usa cada cosa:

  · **Nota de crédito** — la factura ya fue aprobada por el SIFEN y hay que
    revertirla (el cliente devolvió la mercadería, se anuló la venta, se
    acordó un descuento posterior). Es lo que implementa este módulo.
  · **Evento de cancelación** — la factura se transmitió hace poco y todavía
    está dentro de la ventana que da la DNIT para cancelarla sin nota. Es un
    camino distinto, del grupo de eventos (Fase C del plan de migración).

Alcance de hoy: nota de crédito **por el total de la factura**. Cubre la
anulación y la devolución completa, que es lo que pasa en el mostrador. Una
nota parcial —devolver dos cajas de cinco— necesita además elegir ítems y
cantidades, y eso pide un modelo propio de ítems de la nota; está anotado en
docs/migracion_ekuatia.md y no se hace a medias acá.
"""
import logging

from django.db import transaction
from django.utils import timezone

from . import cdc as cdc_mod
from . import codigos
from .models import DocumentoElectronico, SecuenciaComprobante

logger = logging.getLogger(__name__)


class NotaCreditoInvalida(ValueError):
    """No se puede emitir la nota de crédito pedida."""


# Motivos que implican que la mercadería volvió al local. Solo estos reponen
# stock: un descuento posterior o un ajuste de precio no devuelven nada al
# depósito, y reponerlo inventaría existencias que no están.
MOTIVOS_QUE_DEVUELVEN_MERCADERIA = (
    codigos.MOTIVO_DEVOLUCION,
    codigos.MOTIVO_DEVOLUCION_Y_AJUSTE,
)


def validar(factura, *, motivo):
    """
    ¿Se puede emitir una nota de crédito sobre esta factura?

    Se valida antes de tocar nada, para que el error sea claro y no quede
    medio documento creado.
    """
    if factura is None:
        raise NotaCreditoInvalida('No se indicó sobre qué factura.')

    if factura.tipo_documento != codigos.TIPO_DE_FACTURA:
        raise NotaCreditoInvalida(
            f'El documento {factura.numero_completo} no es una factura: una '
            f'nota de crédito solo se emite sobre una factura.')

    if motivo not in codigos.MOTIVOS_NOTA:
        raise NotaCreditoInvalida(
            f'El motivo {motivo!r} no es uno de los que acepta el SIFEN. '
            f'Opciones: {", ".join(f"{k}={v}" for k, v in codigos.MOTIVOS_NOTA.items())}')

    if factura.estado == DocumentoElectronico.ESTADO_RECHAZADO:
        raise NotaCreditoInvalida(
            f'La factura {factura.numero_completo} fue rechazada por el '
            f'SIFEN, así que no existe como documento tributario: no hay nada '
            f'que anular con una nota de crédito. Hay que corregir el motivo '
            f'del rechazo y emitir una factura nueva.')

    existente = DocumentoElectronico.objects.filter(
        documento_asociado_cdc=factura.cdc,
        tipo_documento=codigos.TIPO_DE_NOTA_CREDITO,
    ).first()
    if existente is not None:
        raise NotaCreditoInvalida(
            f'La factura {factura.numero_completo} ya tiene la nota de '
            f'crédito {existente.numero_completo}. Emitir una segunda '
            f'duplicaría la devolución.')


@transaction.atomic
def emitir(factura, *, motivo, usuario, reponer_stock=None, observacion=''):
    """
    Emite la nota de crédito que revierte una factura.

    Devuelve el DocumentoElectronico creado, en estado 'pendiente': el worker
    lo transmite después, igual que cualquier otro documento.

    `reponer_stock` en None decide según el motivo — devolución repone,
    descuento no. Se puede forzar con True/False cuando el caso real no
    coincide con la regla (por ejemplo, mercadería devuelta rota, que vuelve
    al sistema pero no al stock vendible).

    Todo corre en una transacción: si algo falla, el número de la nota vuelve
    atrás y no queda un salto en el correlativo que después haya que
    justificar ante la DNIT.
    """
    validar(factura, motivo=motivo)

    if reponer_stock is None:
        reponer_stock = motivo in MOTIVOS_QUE_DEVUELVEN_MERCADERIA

    numero, numero_completo = SecuenciaComprobante.siguiente(
        codigos.TIPO_DE_NOTA_CREDITO,
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
        # El tipo de contribuyente sale del CDC de la factura: es el mismo
        # emisor, y así la nota no depende de que settings no haya cambiado.
        tipo_contribuyente=int(factura.cdc[24]),
        fecha_emision=ahora.date(),
        tipo_documento=codigos.TIPO_DE_NOTA_CREDITO,
        codigo_seguridad=codigo_seguridad,
    )

    nota = DocumentoElectronico.objects.create(
        pago=factura.pago,
        cdc=cdc_nota,
        tipo_documento=codigos.TIPO_DE_NOTA_CREDITO,
        establecimiento=factura.establecimiento,
        punto_expedicion=factura.punto_expedicion,
        numero=numero,
        numero_completo=numero_completo,
        codigo_seguridad=codigo_seguridad,
        fecha_emision=ahora,

        documento_asociado_cdc=factura.cdc,
        motivo_nota=motivo,

        # El emisor se copia de la factura y no de settings: la nota tiene
        # que declarar el mismo timbrado con el que se emitió el documento
        # que corrige, aunque hoy el negocio esté usando otro.
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
        total=factura.total,
        total_gravado_10=factura.total_gravado_10,
        total_gravado_5=factura.total_gravado_5,
        total_exento=factura.total_exento,
        iva_10=factura.iva_10,
        iva_5=factura.iva_5,

        creado_por=usuario,
    )

    if reponer_stock:
        _reponer_stock(factura, nota, usuario, observacion)

    logger.info('Nota de crédito %s emitida sobre la factura %s (motivo %s)',
                nota.numero_completo, factura.numero_completo, motivo)
    return nota


def _reponer_stock(factura, nota, usuario, observacion=''):
    """
    Devuelve al stock lo que se había descontado por la venta.

    Se hace por `Stock.registrar_movimiento()` y nunca tocando la cantidad a
    mano: eso escribe el MovimientoStock de auditoría en la misma
    transacción, que es la regla del proyecto (ver CLAUDE.md).

    Un problema al reponer **sí** interrumpe la emisión, al revés de lo que
    pasa al facturar. Acá no hay nadie esperando en el mostrador, y una nota
    de crédito por devolución que no repone el stock deja el inventario
    mintiendo — es peor dejarla emitida a medias que no emitirla.
    """
    from apps.inventario.models import MovimientoStock, Stock

    pedido = factura.pago.pedido
    for item in pedido.items.select_related('variante').all():
        stock = Stock.objects.select_for_update().get(variante=item.variante)
        stock.registrar_movimiento(
            MovimientoStock.TIPO_DEVOLUCION,
            item.cantidad,
            usuario,
            referencia_tipo='nota_credito',
            referencia_id=nota.pk,
            observaciones=(observacion or
                           f'Devolución por nota de crédito {nota.numero_completo} '
                           f'(factura {factura.numero_completo})'),
        )
