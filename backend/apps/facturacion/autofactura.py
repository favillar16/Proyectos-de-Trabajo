"""
Autofactura electrónica.

Es el documento más distinto de los cinco, y conviene tener claro por qué
antes de tocarlo: **no documenta una venta, documenta una compra**. Se emite
cuando el local le compra algo a alguien que no puede facturar —un
particular, alguien sin RUC— y necesita respaldar ese gasto. El local es a la
vez emisor y receptor: se factura a sí mismo.

De eso salen las tres cosas que no se parecen a nada del resto del sistema:

  · **No cuelga de un cobro.** No hay pedido, no hay caja, no hay cliente.
    Por eso `DocumentoElectronico.pago` admite null.
  · **Los ítems se escriben a mano** (`ItemAutofactura`): lo que se compró no
    está en el catálogo ni pasó por el stock.
  · **No mueve inventario.** Que lo comprado entre o no al stock vendible es
    una decisión de depósito, no una consecuencia del comprobante. Si algún
    día se quiere que lo haga, va por `Stock.registrar_movimiento()` como
    todo lo demás, no tocando cantidades a mano.

El receptor del XML somos nosotros mismos, así que los datos del receptor
salen de la configuración fiscal, no de un cliente.
"""
import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import cdc as cdc_mod
from . import codigos
from .models import (DatosAutofactura, DocumentoElectronico, ItemAutofactura,
                     SecuenciaComprobante)

logger = logging.getLogger(__name__)


class AutofacturaInvalida(ValueError):
    """No se puede emitir la autofactura pedida."""


CAMPOS_VENDEDOR = (
    'numero_documento_vendedor', 'nombre_vendedor', 'direccion_vendedor',
    'departamento_vendedor', 'departamento_vendedor_desc',
    'distrito_vendedor', 'distrito_vendedor_desc',
    'ciudad_vendedor', 'ciudad_vendedor_desc',
)

CAMPOS_TRANSACCION = (
    'lugar_transaccion',
    'departamento_transaccion', 'departamento_transaccion_desc',
    'distrito_transaccion', 'distrito_transaccion_desc',
    'ciudad_transaccion', 'ciudad_transaccion_desc',
)


def validar(vendedor: dict, items: list):
    """
    Revisa que estén los datos antes de tomar el número.

    Se valida todo junto y se listan **todos** los campos que faltan, no el
    primero: quien carga esto lo hace de un formulario y corregir de a uno
    sería una ida y vuelta por campo.
    """
    faltantes = [c for c in CAMPOS_VENDEDOR + CAMPOS_TRANSACCION
                 if not str(vendedor.get(c) or '').strip()]
    if faltantes:
        raise AutofacturaInvalida(
            'Faltan datos de la autofactura: ' + ', '.join(faltantes))

    if not items:
        raise AutofacturaInvalida(
            'La autofactura no tiene ítems: hay que cargar qué se compró.')

    for posicion, item in enumerate(items, start=1):
        if not str(item.get('descripcion') or '').strip():
            raise AutofacturaInvalida(
                f'El ítem {posicion} no tiene descripción.')
        try:
            cantidad = Decimal(str(item.get('cantidad')))
            precio = Decimal(str(item.get('precio_unitario')))
        except Exception:
            raise AutofacturaInvalida(
                f'El ítem {posicion} tiene cantidad o precio inválidos.')
        if cantidad <= 0:
            raise AutofacturaInvalida(
                f'El ítem {posicion} tiene cantidad cero o negativa.')
        if precio < 0:
            raise AutofacturaInvalida(
                f'El ítem {posicion} tiene precio negativo.')


@transaction.atomic
def emitir(*, vendedor: dict, items: list, usuario) -> DocumentoElectronico:
    """
    Emite la autofactura por una compra a un no contribuyente.

    `vendedor` lleva los campos de `DatosAutofactura`; `items` es una lista de
    dicts con descripcion, cantidad, precio_unitario y opcionalmente tasa_iva
    (por defecto exento, que es el caso: comprarle a un no contribuyente no
    genera crédito fiscal).

    Devuelve el DocumentoElectronico en 'pendiente'. Todo en una transacción:
    si algo falla, el correlativo del tipo 4 vuelve atrás.
    """
    validar(vendedor, items)

    fiscal = getattr(settings, 'DATOS_FISCALES', {})
    establecimiento = f"{int(fiscal['establecimiento']):03d}"
    punto_expedicion = f"{int(fiscal['punto_expedicion']):03d}"

    numero, numero_completo = SecuenciaComprobante.siguiente(
        codigos.TIPO_DE_AUTOFACTURA, establecimiento, punto_expedicion)

    ahora = timezone.now()
    codigo_seguridad = cdc_mod.generar_codigo_seguridad(numero)
    cdc = cdc_mod.generar(
        ruc_emisor=fiscal.get('ruc', ''),
        establecimiento=establecimiento,
        punto_expedicion=punto_expedicion,
        numero=numero,
        tipo_contribuyente=fiscal.get('tipo_contribuyente', 2),
        fecha_emision=ahora.date(),
        tipo_documento=codigos.TIPO_DE_AUTOFACTURA,
        codigo_seguridad=codigo_seguridad,
    )

    total = sum(
        (Decimal(str(i['cantidad'])) * Decimal(str(i['precio_unitario']))
         for i in items), Decimal('0')).quantize(Decimal('1'))

    ruc_propio = fiscal.get('ruc', '')
    documento = DocumentoElectronico.objects.create(
        pago=None,
        cdc=cdc,
        tipo_documento=codigos.TIPO_DE_AUTOFACTURA,
        establecimiento=establecimiento,
        punto_expedicion=punto_expedicion,
        numero=numero,
        numero_completo=numero_completo,
        codigo_seguridad=codigo_seguridad,
        fecha_emision=ahora,

        emisor_ruc=ruc_propio,
        emisor_razon_social=fiscal.get('razon_social', ''),
        emisor_direccion=fiscal.get('direccion', ''),
        emisor_telefono=fiscal.get('telefono', ''),
        emisor_timbrado=fiscal.get('timbrado', ''),
        emisor_timbrado_vto=fiscal.get('timbrado_vto', ''),

        # El receptor es el propio local: se está autofacturando.
        receptor_ruc=ruc_propio,
        receptor_razon_social=fiscal.get('razon_social', ''),
        receptor_direccion=fiscal.get('direccion', ''),
        receptor_telefono=fiscal.get('telefono', ''),
        receptor_naturaleza=codigos.naturaleza_receptor(ruc_propio),

        condicion_venta=codigos.codigo_condicion_venta('contado'),
        medio_pago=codigos.codigo_medio_pago('efectivo'),
        total=total,
        # Exento: comprarle a un no contribuyente no genera crédito fiscal.
        total_exento=total,

        creado_por=usuario,
    )

    DatosAutofactura.objects.create(
        documento=documento,
        naturaleza_vendedor=vendedor.get(
            'naturaleza_vendedor', DatosAutofactura.VENDEDOR_NO_CONTRIBUYENTE),
        tipo_documento_vendedor=vendedor.get('tipo_documento_vendedor', 1),
        **{c: vendedor[c] for c in CAMPOS_VENDEDOR + CAMPOS_TRANSACCION},
    )

    for item in items:
        ItemAutofactura.objects.create(
            documento=documento,
            descripcion=item['descripcion'],
            cantidad=Decimal(str(item['cantidad'])),
            precio_unitario=Decimal(str(item['precio_unitario'])),
            tasa_iva=int(item.get('tasa_iva') or 0),
        )

    logger.info('Autofactura %s emitida a %s por %s',
                numero_completo, vendedor.get('nombre_vendedor'), total)
    return documento
