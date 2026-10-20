"""
Resumen de clientes: cuánto invirtió cada uno en el local.

Existe para que la propietaria pueda decidir a fin de año un descuento o un
regalo a los que más compraron. Por eso cuenta **solo plata**: lo que el
cliente efectivamente pagó, no lo que se le presupuestó.

─── Qué es "lo invertido" ──────────────────────────────────────────────────

La suma de los cobros confirmados de sus pedidos (`Pago.monto`, ya con el
descuento de caja y el precio negociado) menos lo que la caja le reintegró
por devoluciones. El cobro de un cambio ya viene neto del crédito de lo
devuelto, así que con eso alcanza para no contarlo dos veces — es la misma
cuenta que el Balance de Ventas (`reportes.reporte_ventas`).

Un pedido cancelado o sin cobrar no suma: no es plata que entró. Una nota
eliminada sí, si estaba pagada — eliminar solo la saca de la ventana de
pedidos, la venta sigue existiendo.

─── Quién es "el mismo cliente" ───────────────────────────────────────────

El padrón (`ventas.Cliente`) es opcional: muchos pedidos traen solo un nombre
y a veces un CI/RUC tipeado a mano. Se agrupa por, en este orden:

1. el cliente del padrón, si el pedido lo tiene;
2. el CI/RUC, sin el dígito verificador ni puntos — "80012345-6",
   "80.012.345" y "80012345" son la misma persona —, y si ese documento
   está en el padrón, se junta con su ficha;
3. el nombre, sin mayúsculas ni espacios de más.

Lo que no tiene ni documento ni nombre no se puede atribuir a nadie y va
aparte, en `sin_identificar`.
"""
import re
from datetime import date
from decimal import Decimal

from django.utils import timezone

from .models import Devolucion, Pago


def documento_normalizado(ruc: str) -> str:
    """'80.012.345-6' → '80012345'. Vacío si no trae nada útil."""
    base = (ruc or '').split('-')[0]
    return re.sub(r'[^0-9A-Za-z]', '', base).upper()


def _nombre_normalizado(nombre: str) -> str:
    return ' '.join((nombre or '').split()).casefold()


class _Agrupador:
    """Decide a qué cliente pertenece cada pedido, con el padrón a mano."""

    def __init__(self):
        from apps.ventas.models import Cliente
        self.padron = {c.id: c for c in Cliente.objects.all()}
        self.por_documento = {}
        for c in self.padron.values():
            doc = documento_normalizado(c.ruc)
            if doc:
                self.por_documento.setdefault(doc, c)

    def clave(self, pedido, pago):
        if pedido.cliente_id and pedido.cliente_id in self.padron:
            return ('padron', pedido.cliente_id)
        doc = documento_normalizado(pedido.cliente_ruc or pago.cliente_ruc)
        if doc:
            cliente = self.por_documento.get(doc)
            return ('padron', cliente.id) if cliente else ('documento', doc)
        nombre = _nombre_normalizado(pedido.cliente_nombre or pago.cliente_razon_social)
        if nombre:
            return ('nombre', nombre)
        return None


def resumen_clientes(desde: date, hasta: date, buscar: str = '') -> dict:
    """
    Un renglón por cliente con lo invertido en el período, de mayor a menor.

    `buscar` filtra por nombre o documento después de agrupar, para que el
    total de un cliente no cambie según qué se tipeó.
    """
    agrupador = _Agrupador()
    clientes = {}
    sin_identificar = Decimal('0')

    def renglon(clave, pedido, pago):
        r = clientes.get(clave)
        if r is None:
            ficha = agrupador.padron.get(clave[1]) if clave[0] == 'padron' else None
            r = clientes[clave] = {
                'clave':      f'{clave[0]}:{clave[1]}',
                'cliente_id': ficha.id if ficha else None,
                'nombre':     ficha.razon_social if ficha else '',
                'documento':  ficha.ruc if ficha else '',
                'telefono':   ficha.telefono if ficha else '',
                'en_padron':  ficha is not None,
                'total':      Decimal('0'),
                'reintegrado': Decimal('0'),
                'compras':    0,
                'primera_compra': None,
                'ultima_compra':  None,
                'detalle':    [],
            }
        # Lo que falte de la ficha se completa con lo que traiga el pedido;
        # los pagos llegan en orden, así que queda el dato más reciente.
        if not r['en_padron']:
            r['nombre'] = pedido.cliente_nombre or pago.cliente_razon_social or r['nombre']
            r['documento'] = pedido.cliente_ruc or pago.cliente_ruc or r['documento']
            r['telefono'] = pedido.cliente_telefono or pago.cliente_telefono or r['telefono']
        return r

    pagos = (Pago.objects
             .filter(estado=Pago.ESTADO_CONFIRMADO,
                     fecha__date__gte=desde, fecha__date__lte=hasta)
             .select_related('pedido', 'devolucion_aplicada')
             .order_by('fecha'))
    for pago in pagos:
        pedido = pago.pedido
        clave = agrupador.clave(pedido, pago)
        if clave is None:
            sin_identificar += pago.monto
            continue
        r = renglon(clave, pedido, pago)
        r['total'] += pago.monto
        aplicada = getattr(pago, 'devolucion_aplicada', None)
        es_cambio = aplicada is not None
        if not es_cambio:
            r['compras'] += 1
        fecha = timezone.localtime(pago.fecha).date()
        r['primera_compra'] = r['primera_compra'] or fecha
        r['ultima_compra'] = fecha
        r['detalle'].append({
            'fecha':  fecha.isoformat(),
            'pedido': pedido.numero,
            'ticket': pago.numero_ticket,
            'monto':  float(pago.monto),
            'cambio': es_cambio,
        })

    reintegros = (Devolucion.objects
                  .filter(monto_reintegro__gt=0,
                          fecha__date__gte=desde, fecha__date__lte=hasta)
                  .select_related('pago_original__pedido')
                  .order_by('fecha'))
    for d in reintegros:
        pago = d.pago_original
        clave = agrupador.clave(pago.pedido, pago)
        if clave is None:
            sin_identificar -= d.monto_reintegro
            continue
        r = renglon(clave, pago.pedido, pago)
        r['total'] -= d.monto_reintegro
        r['reintegrado'] += d.monto_reintegro
        r['detalle'].append({
            'fecha':  timezone.localtime(d.fecha).date().isoformat(),
            'pedido': pago.pedido.numero,
            'ticket': d.numero,
            'monto':  -float(d.monto_reintegro),
            'cambio': False,
        })

    filas = list(clientes.values())
    buscar = _nombre_normalizado(buscar)
    if buscar:
        doc = documento_normalizado(buscar)
        filas = [r for r in filas
                 if buscar in _nombre_normalizado(r['nombre'])
                 or (doc and doc in documento_normalizado(r['documento']))]

    filas.sort(key=lambda r: (-r['total'], _nombre_normalizado(r['nombre'])))
    for posicion, r in enumerate(filas, start=1):
        r['posicion'] = posicion
        r['ticket_promedio'] = float(r['total'] / r['compras']) if r['compras'] else 0.0
        r['total'] = float(r['total'])
        r['reintegrado'] = float(r['reintegrado'])
        r['primera_compra'] = r['primera_compra'].isoformat() if r['primera_compra'] else None
        r['ultima_compra'] = r['ultima_compra'].isoformat() if r['ultima_compra'] else None
        r['detalle'].sort(key=lambda x: x['fecha'], reverse=True)

    return {
        'desde':    desde.isoformat(),
        'hasta':    hasta.isoformat(),
        'clientes': filas,
        'totales': {
            'clientes':        len(filas),
            'invertido':       float(sum(Decimal(str(r['total'])) for r in filas)),
            'sin_identificar': float(sin_identificar),
        },
    }


def reporte_clientes(desde: date, hasta: date, buscar: str = '') -> dict:
    """El mismo resumen en el formato de `reportes.render_pdf`/`render_xlsx`."""
    from .reportes import _gs

    datos = resumen_clientes(desde, hasta, buscar)

    def fecha(iso):
        return date.fromisoformat(iso).strftime('%d/%m/%Y') if iso else ''

    filas = [[
        r['posicion'], r['nombre'] or '—', r['documento'] or '—',
        r['compras'], fecha(r['ultima_compra']),
        _gs(r['ticket_promedio']), _gs(r['total']),
    ] for r in datos['clientes']]

    totales = {
        'Clientes': datos['totales']['clientes'],
        'Total invertido': _gs(datos['totales']['invertido']),
    }
    if datos['totales']['sin_identificar']:
        totales['Ventas sin cliente identificado'] = _gs(datos['totales']['sin_identificar'])

    return {
        'titulo':    'Clientes — monto invertido',
        'subtitulo': f'Del {fecha(datos["desde"])} al {fecha(datos["hasta"])}',
        'hoja':      'Clientes',
        'columnas':  ['#', 'Cliente', 'CI / RUC', 'Compras', 'Última compra',
                      'Ticket promedio', 'Invertido'],
        'cols_derecha': [0, 3, 5, 6],
        'filas':     filas,
        'totales':   totales,
    }
