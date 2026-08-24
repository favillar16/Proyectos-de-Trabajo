"""
App: inventario — Views
Endpoints para consulta y gestión de stock.

Consulta rápida (/inventario/consulta/):
  Permite buscar stock por código de producto, SKU de variante o nombre,
  sin necesidad de conocer el ID. Diseñado para uso desde el showroom.

Stock general (/inventario/stock/):
  Listado paginado de todo el stock con filtros.

Ajuste de stock (/inventario/ajustes/):
  Registro de entradas, salidas y ajustes de inventario.
"""
from rest_framework import viewsets, views, filters, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from apps.usuarios.permissions import EsAdminODeposito, TodosLosRoles
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Stock, MovimientoStock
from apps.productos.models import Producto, Variante

MAX_MOVIMIENTOS = 200


# ─── Serializers inline (sin archivo separado para mantener todo junto) ───────

from rest_framework import serializers


class StockConsultaSerializer(serializers.Serializer):
    """Resultado de una consulta rápida de stock."""
    producto_id      = serializers.IntegerField()
    producto_codigo  = serializers.CharField()
    producto_nombre  = serializers.CharField()
    variante_id      = serializers.IntegerField()
    sku              = serializers.CharField()
    descripcion      = serializers.CharField()
    color            = serializers.CharField()
    dimension        = serializers.CharField()
    acabado          = serializers.CharField()
    precio_venta     = serializers.DecimalField(max_digits=14, decimal_places=2)
    unidad_venta     = serializers.CharField()
    cantidad         = serializers.DecimalField(max_digits=10, decimal_places=4)
    cantidad_reservada = serializers.DecimalField(max_digits=10, decimal_places=4)
    disponible       = serializers.DecimalField(max_digits=10, decimal_places=4)
    stock_minimo     = serializers.DecimalField(max_digits=10, decimal_places=4)
    estado           = serializers.CharField()
    ubicacion        = serializers.CharField()
    fecha_actualizacion = serializers.DateTimeField()
    imagen_url       = serializers.CharField(allow_null=True)


class AjusteStockSerializer(serializers.Serializer):
    """Payload para registrar un ajuste manual de stock."""
    variante_id   = serializers.IntegerField()
    tipo          = serializers.ChoiceField(choices=[
        ('entrada',    'Entrada de mercadería'),
        ('salida',     'Salida por venta'),
        ('ajuste',     'Ajuste de inventario'),
        ('devolucion', 'Devolución'),
    ])
    cantidad      = serializers.DecimalField(max_digits=10, decimal_places=4, min_value=0.0001)
    # Si el producto se vende por m², el depósito puede cargar en cajas o en
    # pallets y el sistema convierte a m² automáticamente usando
    # m2_por_caja / cajas_por_pallet de la variante.
    unidad_ingreso = serializers.ChoiceField(
        choices=[
            ('venta', 'Unidad de venta (m²/unidad)'),
            ('caja', 'Cajas'),
            ('pallet', 'Pallets'),
        ],
        required=False, default='venta')
    observaciones = serializers.CharField(required=False, allow_blank=True, default='')


class MovimientoStockSerializer(serializers.ModelSerializer):
    """Fila del historial de auditoría de una variante."""
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)
    usuario_nombre = serializers.CharField(source='usuario.nombre_completo', read_only=True)

    class Meta:
        model  = MovimientoStock
        fields = [
            'id', 'tipo', 'tipo_display', 'cantidad',
            'cantidad_anterior', 'cantidad_posterior',
            'referencia_tipo', 'referencia_id',
            'usuario_nombre', 'observaciones', 'fecha',
        ]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _stock_a_dict(stock, request=None):
    """Convierte un objeto Stock al dict que espera el frontend."""
    v = stock.variante
    p = v.producto

    # Imagen principal de la variante, o del producto si no tiene
    imagen_url = None
    img_v = v.imagenes.filter(es_principal=True).first() or v.imagenes.first()
    img_p = p.imagenes.filter(es_principal=True).first() or p.imagenes.first()
    img   = img_v or img_p
    if img and img.imagen:
        imagen_url = (
            request.build_absolute_uri(img.imagen.url)
            if request else img.imagen.url
        )

    partes_desc = [p.nombre]
    if v.dimension_display:
        partes_desc.append(v.dimension_display)
    if v.color:
        partes_desc.append(v.color)
    if v.acabado:
        partes_desc.append(v.acabado.nombre)

    return {
        'producto_id':       p.id,
        'producto_codigo':   p.codigo,
        'producto_nombre':   p.nombre,
        'variante_id':       v.id,
        'sku':               v.sku,
        'descripcion':       ' — '.join(partes_desc),
        'color':             v.color,
        'calidad':           v.calidad,
        'dimension':         v.dimension_display,
        'acabado':           v.acabado.nombre if v.acabado else '',
        'precio_venta':      str(v.precio_venta),
        'unidad_venta':      p.unidad_venta,
        'cantidad':          str(stock.cantidad),
        'cantidad_reservada':str(stock.cantidad_reservada),
        'disponible':        str(stock.cantidad_disponible),
        'stock_minimo':      str(stock.stock_minimo),
        'estado':            stock.estado,
        'ubicacion':         stock.ubicacion,
        'fecha_actualizacion': stock.fecha_actualizacion.isoformat(),
        'imagen_url':        imagen_url,
        # Conversión cajas ↔ m² (None si el producto no se vende por m²)
        'vende_por_m2':      stock.vende_por_m2,
        'm2_por_caja':       stock.m2_por_caja,
        'cajas_completas':   stock.cajas_completas,
        'm2_sueltos':        stock.m2_sueltos,
        'detalle_cajas':     stock.detalle_cajas,
        'cajas_por_pallet':  v.cajas_por_pallet,
    }


# ─── Consulta rápida ──────────────────────────────────────────────────────────

class ConsultaRapidaStockView(views.APIView):
    permission_classes = [TodosLosRoles]
    """
    GET /inventario/consulta/?q=<texto>

    Busca stock por:
    - Código de producto (exacto o parcial)
    - SKU de variante (exacto o parcial)
    - Nombre de producto (parcial)

    Retorna máximo 20 resultados ordenados por relevancia:
    1. Coincidencia exacta de código/SKU
    2. Coincidencia de inicio de código/SKU
    3. Resto por nombre
    """
    permission_classes = [TodosLosRoles]

    def get(self, request):
        q = request.query_params.get('q', '').strip()

        if len(q) < 2:
            return Response({
                'resultados': [],
                'total': 0,
                'mensaje': 'Ingresá al menos 2 caracteres para buscar.',
            })

        # Buscar variantes cuyos productos o el SKU coincidan
        stocks = Stock.objects.select_related(
            'variante__producto__categoria',
            'variante__acabado',
        ).prefetch_related(
            'variante__imagenes',
            'variante__producto__imagenes',
        ).filter(
            Q(variante__sku__icontains=q)
            # El código de barras importa acá porque es donde apunta el lector:
            # el operario dispara y el resultado sale solo, sin tocar la pantalla.
            | Q(variante__codigo_barras__iexact=q)
            | Q(variante__producto__codigo__icontains=q)
            | Q(variante__producto__nombre__icontains=q)
            | Q(variante__color__icontains=q),
            variante__activa=True,
            variante__producto__activo=True,
        ).order_by(
            'variante__producto__nombre',
            'variante__color',
        )[:20]

        # Ordenar: exactos primero, luego parciales
        q_lower = q.lower()
        def relevancia(s):
            sku    = s.variante.sku.lower()
            codigo = s.variante.producto.codigo.lower()
            barras = (s.variante.codigo_barras or '').lower()
            # Una lectura del lector es siempre coincidencia exacta: va primero
            if barras and barras == q_lower:
                return 0
            if sku == q_lower or codigo == q_lower:
                return 0
            if sku.startswith(q_lower) or codigo.startswith(q_lower):
                return 1
            return 2

        resultados_ordenados = sorted(stocks, key=relevancia)

        data = [_stock_a_dict(s, request) for s in resultados_ordenados]

        return Response({
            'resultados': data,
            'total':      len(data),
            'query':      q,
        })


# ─── Stock general (listado paginado) ─────────────────────────────────────────

class StockListView(views.APIView):
    """
    GET /inventario/stock/
    Params: categoria, estado (disponible|critico|sin_stock), search, page, page_size
    """
    permission_classes = [TodosLosRoles]

    def get(self, request):
        qs = Stock.objects.select_related(
            'variante__producto__categoria',
            'variante__producto__marca',
            'variante__acabado',
        ).filter(
            variante__activa=True,
            variante__producto__activo=True,
        ).order_by('variante__producto__nombre', 'variante__color')

        # Filtros
        categoria = request.query_params.get('categoria')
        if categoria:
            qs = qs.filter(variante__producto__categoria_id=categoria)

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(variante__producto__nombre__icontains=search)
                | Q(variante__producto__codigo__icontains=search)
                | Q(variante__sku__icontains=search)
            )

        estado = request.query_params.get('estado')
        # Filtrado por estado en Python (no en SQL para aprovechar properties)
        stocks_list = list(qs)
        if estado in ('sin_stock', 'critico', 'bajo', 'disponible'):
            stocks_list = [s for s in stocks_list if s.estado == estado]

        # Paginación simple
        page      = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 40))
        total     = len(stocks_list)
        inicio    = (page - 1) * page_size
        fin       = inicio + page_size
        pagina    = stocks_list[inicio:fin]

        return Response({
            'count':    total,
            'page':     page,
            'pages':    (total + page_size - 1) // page_size,
            'results':  [_stock_a_dict(s, request) for s in pagina],
        })


# ─── Ajuste de stock ──────────────────────────────────────────────────────────

class AjusteStockView(views.APIView):
    """
    POST /inventario/ajustes/
    Registra un movimiento de stock (entrada, salida, ajuste, devolución).
    """
    permission_classes = [EsAdminODeposito]

    @transaction.atomic
    def post(self, request):
        serializer = AjusteStockSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        try:
            # select_for_update(): dos ajustes concurrentes sobre el mismo
            # SKU (o un ajuste corriendo a la par de una venta) se
            # serializan en vez de pisarse (lost update).
            stock = Stock.objects.select_for_update().select_related('variante').get(
                variante_id=data['variante_id']
            )
        except Stock.DoesNotExist:
            return Response(
                {'error': f"No existe stock para la variante {data['variante_id']}."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Si el ingreso es en cajas o pallets, convertir a la unidad de venta (m²)
        # — misma cuenta que usa la recepción de pedidos a proveedor (apps.costos),
        # centralizada en Variante.convertir_a_unidad_venta para no repetirla.
        unidad_ingreso = data.get('unidad_ingreso', 'venta')
        obs = data.get('observaciones', '')
        try:
            cantidad_final = stock.variante.convertir_a_unidad_venta(data['cantidad'], unidad_ingreso)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if unidad_ingreso == 'caja':
            detalle = f"{data['cantidad']:.0f} caja(s) × {stock.variante.m2_por_caja_calculado} m² = {cantidad_final} m²"
            obs = f'{obs} [{detalle}]'.strip()
        elif unidad_ingreso == 'pallet':
            detalle = (f"{data['cantidad']:.0f} pallet(s) × {stock.variante.cajas_por_pallet} cajas "
                       f"× {stock.variante.m2_por_caja_calculado} m² = {cantidad_final} m²")
            obs = f'{obs} [{detalle}]'.strip()

        try:
            stock.registrar_movimiento(
                tipo          = data['tipo'],
                cantidad      = cantidad_final,
                usuario       = request.user,
                referencia_tipo = 'ajuste_manual',
                observaciones = obs,
            )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'ok':        True,
            'variante':  stock.variante.sku,
            'cantidad':  str(stock.cantidad),
            'disponible':str(stock.cantidad_disponible),
            'estado':    stock.estado,
        })


# ─── Historial de movimientos ──────────────────────────────────────────────────

class MovimientoStockListView(views.APIView):
    """
    GET /inventario/movimientos/?variante_id=<id>
    Historial de auditoría (entradas, salidas, ajustes, reservas) de una
    variante, más reciente primero. Es de solo lectura: MovimientoStock
    nunca se edita ni se borra.
    """
    permission_classes = [TodosLosRoles]

    def get(self, request):
        variante_id = request.query_params.get('variante_id')
        if not variante_id:
            return Response({'error': 'variante_id es requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        qs = (
            MovimientoStock.objects
            .filter(variante_id=variante_id)
            .select_related('usuario')
            .order_by('-fecha')[:MAX_MOVIMIENTOS]
        )
        data = MovimientoStockSerializer(qs, many=True).data
        return Response({'results': data, 'count': len(data)})
