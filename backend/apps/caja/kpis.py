"""
apps/caja/kpis.py
Endpoint de KPIs y reportes para el dashboard administrativo.

Agrupa en una sola llamada todos los datos que necesita la pantalla:
  - Ventas de hoy, semana y mes
  - Comparación con período anterior (para el % de cambio)
  - Desglose por medio de pago
  - Top 5 productos más vendidos
  - Últimas ventas (feed de actividad)
  - Resumen de stock crítico
  - Pedidos activos por estado
"""
from rest_framework import views
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.usuarios.permissions import EsAdmin
from django.db.models import Sum, Count, Avg, F, Q
from django.db.models.functions import TruncDate, TruncWeek
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


def _rango(dias_atras):
    ahora  = timezone.now()
    inicio = ahora.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=dias_atras - 1)
    return inicio, ahora


def _ventas_periodo(inicio, fin):
    """Total de ventas confirmadas en un rango de fechas."""
    from .models import Pago
    qs = Pago.objects.filter(
        estado=Pago.ESTADO_CONFIRMADO,
        fecha__gte=inicio,
        fecha__lte=fin,
    )
    agg = qs.aggregate(total=Sum('monto'), cantidad=Count('id'))
    return float(agg['total'] or 0), int(agg['cantidad'] or 0)


def _pct_cambio(actual, anterior):
    if anterior == 0:
        return None  # No hay base de comparación
    return round(((actual - anterior) / anterior) * 100, 1)


class KPIsDashboardView(views.APIView):
    """
    GET /caja/kpis/
    Params opcionales:
      dias=7|30|90   — ventana de tiempo (default 30)

    Respuesta única con todos los KPIs del dashboard.
    Diseñado para una sola llamada desde el frontend.
    """
    permission_classes = [EsAdmin]

    def get(self, request):
        from .models import Pago
        from apps.ventas.models import NotaPedido, ItemPedido
        from apps.inventario.models import Stock
        from apps.costos.models import GastoOperativo, Empleado

        dias = int(request.query_params.get('dias', 30))

        # ── Rangos temporales ─────────────────────────────────
        ahora     = timezone.now()
        hoy_ini   = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
        semana_ini = hoy_ini - timedelta(days=6)
        mes_ini   = hoy_ini - timedelta(days=29)

        # Período anterior para comparación
        ayer_ini  = hoy_ini - timedelta(days=1)
        ayer_fin  = hoy_ini - timedelta(seconds=1)
        sem_ant_ini = semana_ini - timedelta(days=7)
        sem_ant_fin = semana_ini - timedelta(seconds=1)
        mes_ant_ini = mes_ini - timedelta(days=30)
        mes_ant_fin = mes_ini - timedelta(seconds=1)

        # ── Ventas ────────────────────────────────────────────
        venta_hoy,     cant_hoy     = _ventas_periodo(hoy_ini,      ahora)
        venta_ayer,    cant_ayer    = _ventas_periodo(ayer_ini,      ayer_fin)
        venta_semana,  cant_semana  = _ventas_periodo(semana_ini,    ahora)
        venta_sem_ant, _            = _ventas_periodo(sem_ant_ini,   sem_ant_fin)
        venta_mes,     cant_mes     = _ventas_periodo(mes_ini,       ahora)
        venta_mes_ant, _            = _ventas_periodo(mes_ant_ini,   mes_ant_fin)

        # ── Ticket promedio ───────────────────────────────────
        ticket_prom_mes = round(venta_mes / cant_mes, 0) if cant_mes > 0 else 0

        # ── Desglose por medio de pago (últimos 30 días) ──────
        medios_qs = Pago.objects.filter(
            estado=Pago.ESTADO_CONFIRMADO,
            fecha__gte=mes_ini,
        ).values('medio_pago').annotate(
            total=Sum('monto'),
            cantidad=Count('id'),
        ).order_by('-total')

        medios = [
            {
                'medio':    item['medio_pago'],
                'label':    dict(Pago.MEDIOS).get(item['medio_pago'], item['medio_pago']),
                'total':    float(item['total'] or 0),
                'cantidad': int(item['cantidad'] or 0),
            }
            for item in medios_qs
        ]

        # ── Ventas por día (últimos N días para el gráfico) ───
        n_dias = min(dias, 30)
        grafico_ini = hoy_ini - timedelta(days=n_dias - 1)

        ventas_diarias_qs = Pago.objects.filter(
            estado=Pago.ESTADO_CONFIRMADO,
            fecha__gte=grafico_ini,
        ).annotate(
            dia=TruncDate('fecha')
        ).values('dia').annotate(
            total=Sum('monto'),
            cantidad=Count('id'),
        ).order_by('dia')

        # Rellenar días sin ventas con 0
        dias_con_datos = {item['dia']: item for item in ventas_diarias_qs}
        grafico_ventas = []
        for i in range(n_dias):
            fecha = (grafico_ini + timedelta(days=i)).date()
            dato  = dias_con_datos.get(fecha)
            grafico_ventas.append({
                'fecha':    fecha.strftime('%d/%m'),
                'total':    float(dato['total'] or 0) if dato else 0,
                'cantidad': int(dato['cantidad'] or 0) if dato else 0,
            })

        # ── Top 5 productos más vendidos (último mes) ─────────
        top_qs = ItemPedido.objects.filter(
            pedido__estado=NotaPedido.ESTADO_PAGADO,
            pedido__fecha_creacion__gte=mes_ini,
        ).values(
            nombre=F('variante__producto__nombre'),
            codigo=F('variante__producto__codigo'),
        ).annotate(
            unidades=Sum('cantidad'),
            ingresos=Sum(F('cantidad') * F('precio_unitario')),
        ).order_by('-ingresos')[:5]

        top_productos = [
            {
                'nombre':   item['nombre'],
                'codigo':   item['codigo'],
                'unidades': float(item['unidades'] or 0),
                'ingresos': float(item['ingresos'] or 0),
            }
            for item in top_qs
        ]

        # ── Últimas ventas (feed de actividad) ────────────────
        ultimas_qs = Pago.objects.filter(
            estado=Pago.ESTADO_CONFIRMADO,
        ).select_related(
            'pedido', 'cajero',
        ).order_by('-fecha')[:8]

        ultimas = [
            {
                'ticket':  p.numero_ticket,
                'cliente': p.pedido.cliente_nombre or 'Consumidor Final',
                'monto':   float(p.monto),
                'medio':   dict(Pago.MEDIOS).get(p.medio_pago, p.medio_pago),
                'cajero':  p.cajero.nombre_completo,
                'fecha':   p.fecha.strftime('%d/%m %H:%M'),
                'hace':    _hace_cuanto(p.fecha, ahora),
            }
            for p in ultimas_qs
        ]

        # ── Stock ─────────────────────────────────────────────
        stock_total    = Stock.objects.count()
        stock_critico  = Stock.objects.filter(
            cantidad__gt=0, cantidad__lte=F('stock_minimo')
        ).count()
        stock_sin      = Stock.objects.filter(cantidad__lte=0).count()
        stock_ok       = stock_total - stock_critico - stock_sin

        # ── Pedidos activos ───────────────────────────────────
        pedidos_qs = NotaPedido.objects.values('estado').annotate(
            cantidad=Count('id')
        ).filter(
            estado__in=[
                NotaPedido.ESTADO_PENDIENTE,
                NotaPedido.ESTADO_EN_PREPARACION,
                NotaPedido.ESTADO_LISTO,
            ]
        )
        pedidos_activos = {item['estado']: item['cantidad'] for item in pedidos_qs}

        # ── Respuesta ─────────────────────────────────────────
        return Response({
            'generado_en': ahora.strftime('%d/%m/%Y %H:%M'),

            'ventas': {
                'hoy':        {'total': venta_hoy,    'cantidad': cant_hoy,    'vs_ayer':  _pct_cambio(venta_hoy, venta_ayer)},
                'semana':     {'total': venta_semana, 'cantidad': cant_semana, 'vs_ant':   _pct_cambio(venta_semana, venta_sem_ant)},
                'mes':        {'total': venta_mes,    'cantidad': cant_mes,    'vs_ant':   _pct_cambio(venta_mes, venta_mes_ant)},
                'ticket_prom':ticket_prom_mes,
                'por_medio':  medios,
                'grafico':    grafico_ventas,
            },

            'top_productos': top_productos,
            'ultimas_ventas': ultimas,

            'stock': {
                'total':   stock_total,
                'ok':      stock_ok,
                'critico': stock_critico,
                'sin_stock': stock_sin,
            },

            # ── Costos del período ───────────────────────────────────
            'costos': _resumen_costos(mes_ini, ahora),

            'pedidos_activos': {
                'pendiente':      pedidos_activos.get(NotaPedido.ESTADO_PENDIENTE, 0),
                'en_preparacion': pedidos_activos.get(NotaPedido.ESTADO_EN_PREPARACION, 0),
                'listo':          pedidos_activos.get(NotaPedido.ESTADO_LISTO, 0),
            },
        })


def _hace_cuanto(fecha, ahora):
    diff = int((ahora - fecha).total_seconds())
    if diff < 60:    return 'ahora'
    if diff < 3600:  return f'hace {diff // 60} min'
    if diff < 86400: return f'hace {diff // 3600}h'
    return fecha.strftime('%d/%m')


def _resumen_costos(inicio, fin):
    """
    Calcula el resumen de costos para el período del dashboard.
    Filtra por anio+mes en lugar de fecha, según el modelo real.
    """
    try:
        from apps.costos.models import GastoOperativo, Empleado
        from django.db.models import Sum

        # Filtrar por el mes del período de inicio
        gastos_qs = GastoOperativo.objects.filter(
            anio=inicio.year,
            mes=inicio.month,
        ).exclude(estado=GastoOperativo.ESTADO_CANCELADO)

        total_gastos = float(
            gastos_qs.aggregate(t=Sum('monto'))['t'] or 0
        )

        # Desglose por tipo de categoría
        por_tipo = {}
        for g in gastos_qs.select_related('categoria'):
            tipo  = g.categoria.tipo
            label = g.categoria.get_tipo_display()
            if tipo not in por_tipo:
                por_tipo[tipo] = {'label': label, 'total': 0}
            por_tipo[tipo]['total'] += float(g.monto)

        # Masa salarial: suma de salario_base de empleados activos
        nomina_activa = float(
            Empleado.objects.filter(activo=True).aggregate(t=Sum('salario_base'))['t'] or 0
        )

        return {
            'total':         total_gastos,
            'nomina_activa': nomina_activa,
            'por_tipo':      por_tipo,
        }
    except Exception as e:
        logger.warning(f'_resumen_costos error: {e}')
        return {'total': 0, 'nomina_activa': 0, 'por_tipo': {}}
