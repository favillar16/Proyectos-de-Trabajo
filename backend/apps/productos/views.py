"""
Views de productos — API REST
Endpoints completos para crear, editar, subir imágenes y gestionar variantes.
"""
from rest_framework import viewsets, filters, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Prefetch
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404

from apps.usuarios.permissions import (
    LecturaLibreEscrituraAdmin,
    LecturaLibreEscrituraAdminOVendedor,
    PermisosPorAccion, EsAdmin, TodosLosRoles,
)

from .models import (
    Categoria, Marca, Acabado,
    Producto, Variante, ImagenProducto, ImagenVariante,
)
from .serializers import (
    CategoriaSerializer, MarcaSerializer, AcabadoSerializer,
    ProductoListSerializer, ProductoDetailSerializer, ProductoWriteSerializer,
    VarianteReadSerializer, VarianteWriteSerializer,
    ImagenProductoSerializer, ImagenVarianteSerializer,
)
from .filters import ProductoFilter


def _producto_qs_completo():
    """QuerySet base con todos los prefetch necesarios."""
    from apps.costos.models import PedidoProveedor

    return Producto.objects.select_related(
        'categoria', 'marca',
    ).prefetch_related(
        Prefetch(
            'imagenes',
            queryset=ImagenProducto.objects.order_by('-es_principal', 'orden'),
        ),
        Prefetch(
            'variantes',
            queryset=Variante.objects.filter(activa=True)
                .select_related('acabado')
                .prefetch_related(
                    Prefetch('imagenes', queryset=ImagenVariante.objects.order_by('-es_principal', 'orden')),
                    'stock',
                ),
        ),
        Prefetch(
            'pedidos_proveedor',
            queryset=PedidoProveedor.objects.filter(
                estado__in=[PedidoProveedor.ESTADO_PENDIENTE, PedidoProveedor.ESTADO_EN_CAMINO]
            ).select_related('proveedor').order_by('fecha_entrega_estimada'),
            to_attr='pedidos_pendientes_prefetch',
        ),
    )


# ─── Auxiliares ───────────────────────────────────────────────────────────────

class ProtegeAlBorrarMixin:
    """
    El ModelViewSet por defecto hace un delete() físico. Varios modelos acá
    tienen FKs con on_delete=PROTECT apuntándoles (MovimientoStock, ItemPedido,
    Producto.categoria/marca) — sin este mixin, borrar algo que ya tuvo
    movimiento/uso propaga un ProtectedError sin capturar y DRF lo devuelve
    como 500 crudo en vez de un error legible.
    """
    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {'error': 'No se puede eliminar: está en uso (tiene productos, '
                          'variantes o movimientos asociados). Desactivalo en su lugar.'},
                status=status.HTTP_400_BAD_REQUEST,
            )


class CategoriaViewSet(ProtegeAlBorrarMixin, viewsets.ModelViewSet):
    queryset         = Categoria.objects.order_by('orden', 'nombre')
    serializer_class = CategoriaSerializer
    filter_backends  = [filters.SearchFilter]
    search_fields    = ['nombre']
    permission_classes = [LecturaLibreEscrituraAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('activas_only') == '1':
            qs = qs.filter(activa=True)
        return qs


class MarcaViewSet(ProtegeAlBorrarMixin, viewsets.ModelViewSet):
    queryset         = Marca.objects.order_by('nombre')
    serializer_class = MarcaSerializer
    filter_backends  = [filters.SearchFilter]
    search_fields    = ['nombre']
    permission_classes = [LecturaLibreEscrituraAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('activas_only') == '1':
            qs = qs.filter(activa=True)
        return qs


class AcabadoViewSet(viewsets.ModelViewSet):
    queryset         = Acabado.objects.order_by('nombre')
    serializer_class = AcabadoSerializer
    permission_classes = [LecturaLibreEscrituraAdmin]


# ─── Productos ────────────────────────────────────────────────────────────────

class ProductoViewSet(ProtegeAlBorrarMixin, viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductoFilter
    search_fields   = ['nombre', 'codigo', 'descripcion', 'marca__nombre',
                       'variantes__sku', 'variantes__codigo_barras']
    ordering_fields = ['nombre', 'precio_base', 'fecha_creacion', 'destacado']
    ordering        = ['-destacado', 'nombre']
    parser_classes  = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [PermisosPorAccion]

    # Todos ven el catálogo; solo admin/vendedor modifican
    permisos_por_accion = {
        'list':              [TodosLosRoles],
        'retrieve':          [TodosLosRoles],
        'showroom':          [TodosLosRoles],
        'stock':             [TodosLosRoles],
        'create':            [LecturaLibreEscrituraAdminOVendedor],
        'update':            [LecturaLibreEscrituraAdminOVendedor],
        'partial_update':    [LecturaLibreEscrituraAdminOVendedor],
        'destroy':           [EsAdmin],
        'subir_imagen':      [LecturaLibreEscrituraAdminOVendedor],
        'eliminar_imagen':   [LecturaLibreEscrituraAdminOVendedor],
        'marcar_imagen_principal': [LecturaLibreEscrituraAdminOVendedor],
        'reordenar_imagenes':[LecturaLibreEscrituraAdminOVendedor],
        'agregar_variante':  [LecturaLibreEscrituraAdminOVendedor],
        'default':           [TodosLosRoles],
    }

    def get_queryset(self):
        # distinct() evita productos repetidos cuando la búsqueda coincide con
        # varias de sus variantes (por SKU o por código de barras).
        return _producto_qs_completo().filter(activo=True).distinct()

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return ProductoWriteSerializer
        if self.action == 'list':
            return ProductoListSerializer
        return ProductoDetailSerializer

    # ── Endpoint showroom (tablets) ───────────────────────────
    @action(detail=False, methods=['get'])
    def showroom(self, request):
        """Listado optimizado para el showroom en tablets."""
        qs = self.get_queryset().filter(visible_showroom=True)
        qs = self.filter_queryset(qs)
        page = self.paginate_queryset(qs)
        serializer = ProductoListSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    # ── Subir imagen al producto ──────────────────────────────
    @action(detail=True, methods=['post'], url_path='imagenes',
            parser_classes=[MultiPartParser, FormParser])
    def subir_imagen(self, request, pk=None):
        """
        POST /api/v1/productos/<id>/imagenes/
        Body: multipart con 'imagen', 'es_principal' (opt), 'titulo' (opt), 'orden' (opt)
        """
        producto = self.get_object()
        serializer = ImagenProductoSerializer(
            data=request.data,
            context={'request': request},
        )
        if serializer.is_valid():
            serializer.save(producto=producto)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # ── Eliminar imagen ───────────────────────────────────────
    @action(detail=True, methods=['delete'], url_path=r'imagenes/(?P<imagen_id>\d+)')
    def eliminar_imagen(self, request, pk=None, imagen_id=None):
        """DELETE /api/v1/productos/<id>/imagenes/<imagen_id>/"""
        producto = self.get_object()
        imagen   = get_object_or_404(ImagenProducto, pk=imagen_id, producto=producto)
        imagen.imagen.delete(save=False)  # Borra el archivo físico
        imagen.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── Marcar imagen como principal ──────────────────────────
    @action(detail=True, methods=['patch'], url_path=r'imagenes/(?P<imagen_id>\d+)/principal')
    def marcar_imagen_principal(self, request, pk=None, imagen_id=None):
        """PATCH /api/v1/productos/<id>/imagenes/<imagen_id>/principal/"""
        producto = self.get_object()
        imagen   = get_object_or_404(ImagenProducto, pk=imagen_id, producto=producto)
        ImagenProducto.objects.filter(producto=producto, es_principal=True).update(es_principal=False)
        imagen.es_principal = True
        imagen.save(update_fields=['es_principal'])
        return Response({'detail': 'Imagen principal actualizada.'})

    # ── Reordenar imágenes ────────────────────────────────────
    @action(detail=True, methods=['patch'], url_path='imagenes/orden')
    def reordenar_imagenes(self, request, pk=None):
        """
        PATCH /api/v1/productos/<id>/imagenes/orden/
        Body: {"orden": [{"id": 1, "orden": 0}, {"id": 2, "orden": 1}]}
        """
        producto = self.get_object()
        items    = request.data.get('orden', [])
        for item in items:
            ImagenProducto.objects.filter(
                pk=item['id'], producto=producto
            ).update(orden=item['orden'])
        return Response({'detail': 'Orden actualizado.'})

    # ── Stock de todas las variantes ──────────────────────────
    @action(detail=True, methods=['get'])
    def stock(self, request, pk=None):
        """GET /api/v1/productos/<id>/stock/"""
        producto = self.get_object()
        data = []
        for v in producto.variantes.filter(activa=True).select_related('stock', 'acabado'):
            s = getattr(v, 'stock', None)
            data.append({
                'variante_id':  v.id,
                'sku':          v.sku,
                'descripcion':  str(v),
                'dimension':    v.dimension_display,
                'color':        v.color,
                'acabado':      v.acabado.nombre if v.acabado else '',
                'cantidad':     float(s.cantidad)           if s else 0,
                'reservado':    float(s.cantidad_reservada) if s else 0,
                'disponible':   float(s.cantidad_disponible)if s else 0,
                'stock_minimo': float(s.stock_minimo)       if s else 0,
                'estado':       s.estado                    if s else 'sin_stock',
                'ubicacion':    s.ubicacion                 if s else '',
            })
        return Response(data)

    # ── Agregar variante a un producto existente ──────────────
    @action(detail=True, methods=['post'], url_path='variantes')
    def agregar_variante(self, request, pk=None):
        """POST /api/v1/productos/<id>/variantes/"""
        producto   = self.get_object()
        serializer = VarianteWriteSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            variante = serializer.save(producto=producto)
            return Response(
                VarianteReadSerializer(variante, context={'request': request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── Variantes ────────────────────────────────────────────────────────────────

class VarianteViewSet(ProtegeAlBorrarMixin, viewsets.ModelViewSet):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [PermisosPorAccion]
    permisos_por_accion = {
        'list':     [TodosLosRoles],
        'retrieve': [TodosLosRoles],
        'create':   [LecturaLibreEscrituraAdminOVendedor],
        'update':   [LecturaLibreEscrituraAdminOVendedor],
        'partial_update': [LecturaLibreEscrituraAdminOVendedor],
        'destroy':  [EsAdmin],
        # Todos los roles leen el código de barras: depósito al recibir
        # mercadería, vendedor al armar el pedido, caja al cobrar.
        'por_codigo_barras': [TodosLosRoles],
        'default':  [TodosLosRoles],
    }

    def get_queryset(self):
        return Variante.objects.select_related(
            'producto', 'acabado',
        ).prefetch_related(
            Prefetch('imagenes', queryset=ImagenVariante.objects.order_by('-es_principal', 'orden')),
            'stock',
        ).filter(activa=True)

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return VarianteWriteSerializer
        return VarianteReadSerializer

    # ── Lectura del código de barras ──────────────────────────
    @action(detail=False, methods=['get'], url_path='por-codigo-barras')
    def por_codigo_barras(self, request):
        """
        GET /api/v1/productos/variantes/por-codigo-barras/?codigo=7891234567895

        Devuelve la variante que tiene ese código de barras, con su stock.
        Es lo que consulta el sistema cada vez que alguien dispara el lector.

        Responde 200 siempre, con `encontrado` en true o false, incluso cuando
        el código no está cargado. Un código desconocido no es un error: al dar
        de alta mercadería nueva es justamente lo que se espera, y la pantalla
        tiene que poder ofrecer cargarlo en vez de mostrar un cartel de error.

        Busca también por SKU: algunas etiquetas del proveedor traen impreso el
        código interno y no un código de barras de fábrica, y así el lector
        sirve igual.
        """
        codigo = (request.query_params.get('codigo') or '').strip()

        if not codigo:
            return Response(
                {'detail': 'Falta el parámetro "codigo".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Se busca en las inactivas también: si una variante dada de baja
        # conserva ese código, hay que avisarlo y no dejar cargarlo de nuevo.
        base = Variante.objects.select_related('producto', 'acabado').prefetch_related('stock')

        variante = (
            base.filter(codigo_barras__iexact=codigo).first()
            or base.filter(sku__iexact=codigo).first()
        )

        if variante is None:
            return Response({'encontrado': False, 'codigo': codigo})

        return Response({
            'encontrado': True,
            'codigo':     codigo,
            'variante':   VarianteReadSerializer(variante, context={'request': request}).data,
            'producto': {
                'id':           variante.producto_id,
                'codigo':       variante.producto.codigo,
                'nombre':       variante.producto.nombre,
                'unidad_venta': variante.producto.unidad_venta,
                'activo':       variante.producto.activo,
            },
        })

    # ── Subir imagen de variante ──────────────────────────────
    @action(detail=True, methods=['post'], url_path='imagenes',
            parser_classes=[MultiPartParser, FormParser])
    def subir_imagen(self, request, pk=None):
        """POST /api/v1/variantes/<id>/imagenes/"""
        variante   = self.get_object()
        serializer = ImagenVarianteSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save(variante=variante)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # ── Eliminar imagen de variante ───────────────────────────
    @action(detail=True, methods=['delete'], url_path=r'imagenes/(?P<imagen_id>\d+)')
    def eliminar_imagen(self, request, pk=None, imagen_id=None):
        variante = self.get_object()
        imagen   = get_object_or_404(ImagenVariante, pk=imagen_id, variante=variante)
        imagen.imagen.delete(save=False)
        imagen.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── Marcar imagen principal de variante ───────────────────
    @action(detail=True, methods=['patch'], url_path=r'imagenes/(?P<imagen_id>\d+)/principal')
    def marcar_imagen_principal(self, request, pk=None, imagen_id=None):
        variante = self.get_object()
        imagen   = get_object_or_404(ImagenVariante, pk=imagen_id, variante=variante)
        ImagenVariante.objects.filter(variante=variante, es_principal=True).update(es_principal=False)
        imagen.es_principal = True
        imagen.save(update_fields=['es_principal'])
        return Response({'detail': 'Imagen principal de variante actualizada.'})
