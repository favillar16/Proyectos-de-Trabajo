"""
Ganancia real: lo que se cobró por la mercadería contra lo que costó.

Antes de esto el sistema no tenía cómo decir cuánto se gana. El dashboard
mostraba "Balance neto = ventas − gastos del mes" con un "Margen %", pero
eso es un **flujo de caja**, no una ganancia: no resta lo que costó la
mercadería vendida, y los pagos a proveedor entran el mes en que se pagan,
no el mes en que esa mercadería se vende. Un mes con una compra grande
parecía a pérdida; uno sin compras, con un margen de 90%.

Acá se calcula como se hace en un comercio:

  ganancia bruta = lo cobrado por cada ítem − su costo de adquisición
  ganancia neta  = ganancia bruta − gastos operativos del período

Tres decisiones que conviene no deshacer:

  · **Lo cobrado, no el precio de lista.** El ingreso de cada ítem es su
    parte del cobro real (`devoluciones.valor_por_item`): ya trae el
    descuento del pedido, el precio negociado, el descuento de caja y, en un
    cambio, el crédito de lo devuelto. Con el precio de lista la ganancia
    salía más alta de lo que de verdad entró.
  · **El costo congelado al vender** (`ItemPedido.costo_unitario`). El costo
    del producto cambia con cada factura nueva del proveedor; si se leyera
    el de hoy, la ganancia de una venta vieja cambiaría sola.
  · **Los pagos a proveedor no son gasto acá.** Esa plata compra stock, y
    ese stock ya entra como costo cuando se vende. Restarlos también sería
    contar la mercadería dos veces.

Precio y costo van los dos con IVA incluido (así se cargan: ver
`cargar_lote_facturas`), así que se comparan directo.

Las devoluciones restan en la fecha en que ocurren: el ingreso vuelve
(el crédito) y el costo también, **salvo** que la mercadería haya vuelto
dañada (`reingresa_stock=False`): ahí el costo no se recupera y queda como
pérdida, que es exactamente lo que pasó.
"""
import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal


@dataclass
class Linea:
    fecha: object          # datetime de la venta o de la devolución
    variante: object
    cantidad: Decimal      # negativa en una devolución
    ingreso: Decimal       # negativo en una devolución
    costo: Decimal = None  # None = sin costo cargado
    referencia: str = ''   # número de pedido o de devolución
    cliente: str = ''
    devolucion: bool = False
    danada: bool = False

    @property
    def ganancia(self):
        return None if self.costo is None else self.ingreso - self.costo


def lineas(desde: date, hasta: date):
    """Cada ítem vendido y cada ítem devuelto del período, con su ingreso y su costo."""
    from apps.caja.models import ItemDevolucion, Pago
    from apps.caja.devoluciones import valor_por_item

    pagos = (Pago.objects
             .filter(estado=Pago.ESTADO_CONFIRMADO,
                     fecha__date__gte=desde, fecha__date__lte=hasta)
             .select_related('pedido')
             .prefetch_related('pedido__items__variante__producto',
                               'pedido__items__variante__acabado')
             .order_by('fecha'))
    for pago in pagos:
        if not pago.pedido:
            continue
        valores = valor_por_item(pago)
        for item in pago.pedido.items.all():
            costo = (item.cantidad * item.costo_unitario
                     if item.costo_unitario is not None else None)
            yield Linea(
                fecha=pago.fecha, variante=item.variante,
                cantidad=item.cantidad, ingreso=valores.get(item.id, Decimal('0')),
                costo=costo, referencia=pago.pedido.numero,
                cliente=pago.pedido.cliente_nombre or 'Consumidor Final',
            )

    devueltos = (ItemDevolucion.objects
                 .filter(devolucion__fecha__date__gte=desde,
                         devolucion__fecha__date__lte=hasta)
                 .select_related('devolucion__pago_original__pedido',
                                 'variante__producto', 'variante__acabado',
                                 'item_pedido')
                 .order_by('devolucion__fecha'))
    for dev in devueltos:
        unitario = dev.item_pedido.costo_unitario
        if unitario is None:
            costo = None
        elif dev.reingresa_stock:
            costo = -(dev.cantidad * unitario)   # la mercadería volvió al stock
        else:
            costo = Decimal('0')                 # dañada: el costo se perdió
        pedido = dev.devolucion.pago_original.pedido
        yield Linea(
            fecha=dev.devolucion.fecha, variante=dev.variante,
            cantidad=-dev.cantidad, ingreso=-dev.monto, costo=costo,
            referencia=dev.devolucion.numero,
            cliente=pedido.cliente_nombre or 'Consumidor Final',
            devolucion=True, danada=not dev.reingresa_stock,
        )


def gastos_operativos(desde: date, hasta: date) -> Decimal:
    """
    Gastos del período, sin los pagos a proveedor (ver arriba por qué).

    Los gastos se cargan por mes (`anio`/`mes`), no por día. Para un rango
    que corta un mes por la mitad se toma la parte proporcional a los días:
    el alquiler de octubre no se gasta entero el 1° de octubre.
    """
    from apps.costos.models import CategoriaGasto, GastoOperativo

    total = Decimal('0')
    dia = date(desde.year, desde.month, 1)
    while dia <= hasta:
        dias_mes = calendar.monthrange(dia.year, dia.month)[1]
        ini = max(desde, dia)
        fin = min(hasta, date(dia.year, dia.month, dias_mes))
        del_mes = (GastoOperativo.objects
                   .filter(anio=dia.year, mes=dia.month)
                   .exclude(estado=GastoOperativo.ESTADO_CANCELADO)
                   .exclude(categoria__tipo=CategoriaGasto.TIPO_PROVEEDOR))
        suma = sum((g.monto for g in del_mes), Decimal('0'))
        total += suma * Decimal((fin - ini).days + 1) / Decimal(dias_mes)
        dia = date(dia.year, dia.month, dias_mes) + timedelta(days=1)
    return total.quantize(Decimal('1'))


def resumen(desde: date, hasta: date, con_lineas=False) -> dict:
    """Los totales del período. `margen` es sobre lo cobrado, en %."""
    todas = list(lineas(desde, hasta))
    con_costo = [l for l in todas if l.costo is not None]

    ingresos = sum((l.ingreso for l in todas), Decimal('0'))
    ingresos_con_costo = sum((l.ingreso for l in con_costo), Decimal('0'))
    costo = sum((l.costo for l in con_costo), Decimal('0'))
    bruta = ingresos_con_costo - costo
    gastos = gastos_operativos(desde, hasta)

    datos = {
        'ingresos':           ingresos,
        'ingresos_con_costo': ingresos_con_costo,
        'ingresos_sin_costo': ingresos - ingresos_con_costo,
        'costo':              costo,
        'ganancia_bruta':     bruta,
        'margen':             (bruta / ingresos_con_costo * 100) if ingresos_con_costo else None,
        'gastos':             gastos,
        'ganancia_neta':      bruta - gastos,
    }
    if con_lineas:
        datos['lineas'] = todas
    return datos
