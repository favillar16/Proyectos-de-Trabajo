"""
Devoluciones y cambios de mercadería ya cobrada.

Todo lo que una devolución mueve pasa por `registrar()`, en una sola
transacción: el stock que vuelve, el pedido de cambio que sale, el cobro de
la diferencia o el reintegro. Si algo falla, no queda nada a medias — un
reintegro sin la mercadería de vuelta, o al revés, deja la caja o el
inventario mintiendo.

La cuenta de fondo:

    crédito  = lo que el cliente pagó por lo que trae
    nuevo    = lo que vale lo que se lleva (0 si no se lleva nada)
    diferencia = nuevo − crédito

    diferencia > 0  → se cobra la diferencia (Pago del pedido de cambio)
    diferencia < 0  → se reintegra (egreso de la caja)
    diferencia = 0  → no se mueve plata

El crédito sale de lo **cobrado**, no del precio de lista. Si la venta tuvo
descuento en caja o precio negociado, el valor de cada ítem se prorratea
contra lo que realmente entró, con la misma idea que `payload._items()`: el
último ítem absorbe el residuo del redondeo, así devolver una venta entera
reintegra exactamente lo cobrado, ni un guaraní más.
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum

from .models import Devolucion, ItemDevolucion, Pago

UN_GUARANI = Decimal('1')


class DevolucionInvalida(ValueError):
    """La devolución pedida no se puede registrar; el mensaje es para la cajera."""


# Medios con los que se puede cobrar la diferencia o reintegrar. El cheque
# queda afuera: para una diferencia de mostrador no tiene sentido recibir un
# papel a cobrar después, y la caja no emite cheques para reintegrar.
MEDIOS_PERMITIDOS = [m for m, _ in Pago.MEDIOS if m != Pago.MEDIO_CHEQUE]


def _gs(valor):
    return f'Gs. {int(valor):,}'.replace(',', '.')


def _cant(valor):
    """10.0000 → '10', 2.5200 → '2,52': como se lee en el mostrador."""
    return f'{Decimal(valor).normalize():f}'.replace('.', ',')


# ── Cuánto vale cada ítem de la venta ─────────────────────────────────────────

def _cobrado_por_la_venta(pago):
    """
    Lo que entró por esa venta, contando el crédito si fue un cambio.

    El pago de un pedido de cambio viene neto del crédito (puede ser 0), pero
    sus ítems valen lo que valen: si después el cliente devuelve eso también,
    se le reconoce el valor completo, no solo la diferencia que puso.
    """
    cobrado = pago.monto
    aplicada = Devolucion.objects.filter(pago_cambio=pago).first()
    if aplicada is not None:
        cobrado += aplicada.credito_aplicado
    return cobrado


def valor_por_item(pago):
    """{item_pedido.id: valor cobrado por ese ítem entero}."""
    items = list(pago.pedido.items.order_by('id'))
    if not items:
        return {}

    cobrado = _cobrado_por_la_venta(pago)
    suma = sum((i.subtotal for i in items), Decimal('0'))
    factor = (cobrado / suma) if suma > 0 else Decimal('0')

    valores = {}
    acumulado = Decimal('0')
    for item in items[:-1]:
        valor = (item.subtotal * factor).quantize(UN_GUARANI, rounding=ROUND_HALF_UP)
        valores[item.id] = valor
        acumulado += valor
    valores[items[-1].id] = cobrado - acumulado
    return valores


def ya_devuelto(item):
    """(cantidad, monto) que ya volvió de este ítem en devoluciones anteriores."""
    agg = ItemDevolucion.objects.filter(item_pedido=item).aggregate(
        cantidad=Sum('cantidad'), monto=Sum('monto'))
    return agg['cantidad'] or Decimal('0'), agg['monto'] or Decimal('0')


def credito_por(item, cantidad, valor_item):
    """
    Crédito por devolver `cantidad` de este ítem.

    Si se devuelve todo lo que queda, se reconoce todo lo que queda de su
    valor — no una cuenta proporcional redondeada, que al sumar las partes
    podría dar un guaraní distinto de lo cobrado.
    """
    cant_previa, monto_previo = ya_devuelto(item)
    if cant_previa + cantidad >= item.cantidad:
        return valor_item - monto_previo
    return (valor_item * cantidad / item.cantidad).quantize(
        UN_GUARANI, rounding=ROUND_HALF_UP)


# ── Qué bloquea una devolución ────────────────────────────────────────────────

def motivo_bloqueo_fiscal(pago):
    """
    Texto del motivo por el que esta venta no se puede devolver acá, o ''.

    Una factura electrónica viva solo se corrige con una nota de crédito por
    los ítems devueltos. La nota parcial todavía no existe: devolver por acá
    dejaría al SIFEN con la venta entera mientras la caja y el stock dicen
    otra cosa. Una factura rechazada o cancelada no existe como documento
    tributario, así que no bloquea.
    """
    from apps.facturacion.models import DocumentoElectronico

    factura = pago.documento_electronico
    if factura is None:
        return ''
    if factura.estado in (DocumentoElectronico.ESTADO_RECHAZADO,
                          DocumentoElectronico.ESTADO_CANCELADO):
        return ''
    return (f'Esta venta tiene la factura electrónica {factura.numero_completo}. '
            f'Para devolver mercadería facturada electrónicamente hace falta una '
            f'nota de crédito parcial, que todavía no está disponible en el sistema.')


# ── Lo que ve la cajera antes de confirmar ────────────────────────────────────

def resumen(pago):
    """Qué se puede devolver de esta venta, ítem por ítem, y a cuánto."""
    valores = valor_por_item(pago)
    items = []
    for item in pago.pedido.items.select_related('variante__producto').order_by('id'):
        cant_previa, monto_previo = ya_devuelto(item)
        disponible = item.cantidad - cant_previa
        valor = valores.get(item.id, Decimal('0'))
        items.append({
            'item_id':           item.id,
            'variante_id':       item.variante_id,
            'producto':          item.variante.producto.nombre,
            'variante':          str(item.variante),
            'sku':               item.variante.sku,
            'unidad':            item.variante.producto.unidad_venta,
            'cantidad_vendida':  item.cantidad,
            'cantidad_devuelta': cant_previa,
            'cantidad_disponible': max(disponible, Decimal('0')),
            # Lo que vale una unidad a precio cobrado. Solo orienta en la
            # pantalla: el crédito real lo calcula `credito_por()` al
            # confirmar, que es quien sabe del residuo.
            'precio_cobrado_unit': (valor / item.cantidad) if item.cantidad else Decimal('0'),
            'valor_restante':    valor - monto_previo,
        })

    return {
        'pago_id':        pago.id,
        'numero_ticket':  pago.numero_ticket,
        'pedido_numero':  pago.pedido.numero,
        'cliente':        pago.cliente_razon_social or pago.pedido.cliente_nombre or 'Consumidor Final',
        'fecha':          pago.fecha,
        'monto_cobrado':  _cobrado_por_la_venta(pago),
        'bloqueo':        motivo_bloqueo_fiscal(pago),
        'items':          items,
        'devoluciones_previas': [
            {'numero': d.numero, 'fecha': d.fecha, 'total_credito': d.total_credito,
             'motivo': d.motivo_texto}
            for d in pago.devoluciones.order_by('fecha')
        ],
    }


# ── Registrar ─────────────────────────────────────────────────────────────────

@dataclass
class Resultado:
    devolucion: Devolucion
    errores_stock: list


def _decimal(valor, campo):
    try:
        numero = Decimal(str(valor))
    except Exception:
        raise DevolucionInvalida(f'{campo} es inválido.')
    if not numero.is_finite():
        raise DevolucionInvalida(f'{campo} es inválido.')
    return numero


@transaction.atomic
def registrar(*, pago_original, sesion, usuario, motivo, items,
              motivo_detalle='', observaciones='', pedido_cambio=None,
              medio_pago='', monto_recibido=None, referencia_externa=''):
    """
    Registra la devolución completa y devuelve un `Resultado`.

    `items` es una lista de dicts `{item_id, cantidad, reingresa_stock}`.
    `medio_pago` es el de la diferencia: con qué paga el cliente si le toca
    poner, o con qué se le reintegra si le toca recibir.

    Lanza `DevolucionInvalida` antes de tocar nada si algo no cierra.
    """
    from apps.inventario.models import MovimientoStock, Stock
    from apps.ventas.models import ItemPedido, NotaPedido

    # ── La venta original ───────────────────────────────────
    # Se bloquea el pago para que dos cajas no devuelvan la misma mercadería
    # a la vez: las dos verían la cantidad disponible entera.
    pago_original = Pago.objects.select_for_update().select_related('pedido').get(
        pk=pago_original.pk)
    if pago_original.estado != Pago.ESTADO_CONFIRMADO:
        raise DevolucionInvalida('Solo se puede devolver mercadería de un cobro confirmado.')

    bloqueo = motivo_bloqueo_fiscal(pago_original)
    if bloqueo:
        raise DevolucionInvalida(bloqueo)

    # ── Motivo ──────────────────────────────────────────────
    motivos_validos = [m for m, _ in Devolucion.MOTIVOS]
    if motivo not in motivos_validos:
        raise DevolucionInvalida(f'Motivo inválido. Opciones: {motivos_validos}')
    motivo_detalle = (motivo_detalle or '').strip()
    if motivo == Devolucion.MOTIVO_OTRO and not motivo_detalle:
        raise DevolucionInvalida('Con "Otro motivo" hay que escribir cuál es.')
    if motivo == Devolucion.MOTIVO_CAMBIO and pedido_cambio is None:
        raise DevolucionInvalida(
            'Un cambio de producto necesita el pedido con lo que se lleva el '
            'cliente. Si no se lleva nada, es una devolución.')

    # ── Ítems ───────────────────────────────────────────────
    if not items:
        raise DevolucionInvalida('Indicá al menos un producto devuelto.')

    valores = valor_por_item(pago_original)
    lineas = []
    vistos = set()
    for pedido_item in items:
        item_id = pedido_item.get('item_id')
        if item_id in vistos:
            raise DevolucionInvalida('Un mismo producto aparece dos veces en la devolución.')
        vistos.add(item_id)

        try:
            item = ItemPedido.objects.select_related('variante').get(
                pk=item_id, pedido=pago_original.pedido)
        except (ItemPedido.DoesNotExist, ValueError, TypeError):
            raise DevolucionInvalida(
                f'El ítem {item_id} no es parte de la venta {pago_original.pedido.numero}.')

        # A 4 decimales, que es lo que guarda la columna: si no, la base
        # redondea al escribir y el control de "ya devuelto" deja de cuadrar.
        cantidad = _decimal(pedido_item.get('cantidad'), 'La cantidad').quantize(
            Decimal('0.0001'), rounding=ROUND_HALF_UP)
        if cantidad <= 0:
            raise DevolucionInvalida(f'La cantidad de {item.variante.sku} tiene que ser mayor a 0.')

        cant_previa, _ = ya_devuelto(item)
        disponible = item.cantidad - cant_previa
        if cantidad > disponible:
            raise DevolucionInvalida(
                f'De {item.variante.sku} se vendieron {_cant(item.cantidad)} y ya '
                f'volvieron {_cant(cant_previa)}: se pueden devolver hasta '
                f'{_cant(disponible)}.')

        lineas.append((item, cantidad,
                       credito_por(item, cantidad, valores[item.id]),
                       bool(pedido_item.get('reingresa_stock', True))))

    total_credito = sum((monto for _, _, monto, _ in lineas), Decimal('0'))

    # ── Pedido de cambio ────────────────────────────────────
    nuevo = Decimal('0')
    if pedido_cambio is not None:
        pedido_cambio = NotaPedido.objects.select_for_update().get(pk=pedido_cambio.pk)
        if pedido_cambio.pk == pago_original.pedido_id:
            raise DevolucionInvalida('El pedido de cambio no puede ser la misma venta.')
        if pedido_cambio.estado != NotaPedido.ESTADO_LISTO:
            raise DevolucionInvalida(
                f'El pedido {pedido_cambio.numero} está "{pedido_cambio.get_estado_display()}". '
                f'Para usarlo en un cambio tiene que estar "Listo para cobrar".')
        nuevo = pedido_cambio.monto_a_cobrar

    diferencia = nuevo - total_credito
    a_cobrar = max(diferencia, Decimal('0'))
    a_reintegrar = max(-diferencia, Decimal('0'))

    # ── Medio de la diferencia ──────────────────────────────
    if a_cobrar > 0 or a_reintegrar > 0:
        if medio_pago not in MEDIOS_PERMITIDOS:
            accion = 'cobrar la diferencia' if a_cobrar > 0 else 'reintegrar'
            raise DevolucionInvalida(
                f'Indicá con qué medio se va a {accion}. '
                f'Opciones: {", ".join(MEDIOS_PERMITIDOS)}.')
    if a_cobrar > 0 and medio_pago == Pago.MEDIO_EFECTIVO:
        if monto_recibido in (None, ''):
            raise DevolucionInvalida('Para cobrar en efectivo indicá el monto recibido.')
        monto_recibido = _decimal(monto_recibido, 'El monto recibido')
        if monto_recibido < a_cobrar:
            raise DevolucionInvalida(
                f'El monto recibido ({_gs(monto_recibido)}) es menor a la diferencia '
                f'a cobrar ({_gs(a_cobrar)}).')
    else:
        monto_recibido = None

    # ── A partir de acá se escribe ──────────────────────────
    devolucion = Devolucion.objects.create(
        pago_original=pago_original,
        sesion_caja=sesion,
        usuario=usuario,
        motivo=motivo,
        motivo_detalle=motivo_detalle,
        observaciones=observaciones or '',
        total_credito=total_credito,
        pedido_cambio=pedido_cambio,
        monto_reintegro=a_reintegrar,
        medio_reintegro=medio_pago if a_reintegrar > 0 else '',
    )

    for item, cantidad, monto, reingresa in lineas:
        ItemDevolucion.objects.create(
            devolucion=devolucion, item_pedido=item, variante=item.variante,
            cantidad=cantidad, monto=monto, reingresa_stock=reingresa)
        # La mercadería dañada vuelve al local pero no al stock vendible: no
        # se mueve el stock, y el ItemDevolucion queda como registro de que
        # entró.
        if reingresa:
            stock = Stock.objects.select_for_update().get(variante=item.variante)
            stock.registrar_movimiento(
                MovimientoStock.TIPO_DEVOLUCION, cantidad, usuario,
                referencia_tipo='devolucion', referencia_id=devolucion.pk,
                observaciones=(f'{devolucion.numero} — {devolucion.get_motivo_display()} '
                               f'(venta {pago_original.pedido.numero})'),
            )

    errores_stock = []
    if pedido_cambio is not None:
        # El pedido de cambio se cobra como cualquier otro, solo que por la
        # diferencia: su Pago lleva lo que el cliente puso de su bolsillo.
        # Con eso los reportes que suman cobros ya dan el neto sin saber de
        # devoluciones. Va como ticket: la factura de un cambio necesita la
        # nota de crédito parcial (ver motivo_bloqueo_fiscal).
        medio_cambio = medio_pago if medio_pago in MEDIOS_PERMITIDOS else Pago.MEDIO_EFECTIVO
        pago_cambio = Pago(
            pedido=pedido_cambio,
            sesion_caja=sesion,
            cajero=usuario,
            medio_pago=medio_cambio,
            monto=a_cobrar,
            monto_sin_descuento=nuevo,
            monto_recibido=monto_recibido,
            referencia_externa=referencia_externa or '',
            estado=Pago.ESTADO_CONFIRMADO,
            tipo_comprobante=Pago.COMPROBANTE_TICKET,
        )
        pago_cambio.save()
        devolucion.pago_cambio = pago_cambio
        devolucion.save(update_fields=['pago_cambio'])

        pedido_cambio.estado = NotaPedido.ESTADO_PAGADO
        pedido_cambio.save(update_fields=['estado', 'fecha_actualizacion'])
        errores_stock = pedido_cambio.descontar_stock(
            usuario=usuario, numero_ticket=pago_cambio.numero_ticket)

    return Resultado(devolucion=devolucion, errores_stock=errores_stock)


# ── El papel ──────────────────────────────────────────────────────────────────

def datos_comprobante(devolucion):
    """Todo lo que necesitan el ticket impreso y la pantalla."""
    from django.conf import settings
    from django.utils import timezone

    original = devolucion.pago_original
    pedido = original.pedido
    contacto = getattr(settings, 'CONTACTO_COMERCIAL', {})

    devueltos = [{
        'descripcion': i.variante.producto.nombre,
        'detalle':     str(i.variante),
        'cantidad':    float(i.cantidad),
        'subtotal':    float(i.monto),
        'reingresa_stock': i.reingresa_stock,
    } for i in devolucion.items.select_related('variante__producto').all()]

    llevados = []
    pago_cambio = devolucion.pago_cambio
    if devolucion.pedido_cambio_id:
        for item in devolucion.pedido_cambio.items.select_related('variante__producto').all():
            llevados.append({
                'descripcion': item.variante.producto.nombre,
                'detalle':     str(item.variante),
                'cantidad':    float(item.cantidad),
                'precio_unit': float(item.precio_unitario),
                'subtotal':    float(item.subtotal),
            })

    nuevo = float(devolucion.pedido_cambio.monto_a_cobrar) if devolucion.pedido_cambio_id else 0.0
    return {
        'numero':          devolucion.numero,
        'fecha':           timezone.localtime(devolucion.fecha).strftime('%d/%m/%Y %H:%M'),
        'cajero':          devolucion.usuario.nombre_completo,
        'cliente':         original.cliente_razon_social or pedido.cliente_nombre or 'Consumidor Final',
        'venta_ticket':    original.numero_ticket,
        'venta_pedido':    pedido.numero,
        'motivo':          devolucion.motivo_texto,
        'observaciones':   devolucion.observaciones,
        'devueltos':       devueltos,
        'total_credito':   float(devolucion.total_credito),
        'pedido_cambio':   devolucion.pedido_cambio.numero if devolucion.pedido_cambio_id else '',
        'llevados':        llevados,
        'total_nuevo':     nuevo,
        'a_cobrar':        float(pago_cambio.monto) if pago_cambio else 0.0,
        'medio_cobro':     pago_cambio.get_medio_pago_display() if pago_cambio and pago_cambio.monto > 0 else '',
        'ticket_cambio':   pago_cambio.numero_ticket if pago_cambio else '',
        'monto_recibido':  float(pago_cambio.monto_recibido) if pago_cambio and pago_cambio.monto_recibido else None,
        'vuelto':          float(pago_cambio.vuelto) if pago_cambio else 0.0,
        'a_reintegrar':    float(devolucion.monto_reintegro),
        'medio_reintegro': devolucion.get_medio_reintegro_display() if devolucion.monto_reintegro > 0 else '',
        'negocio':         'Oga Porã',
        'direccion':       contacto.get('direccion', ''),
        'telefono':        contacto.get('telefono', ''),
    }
