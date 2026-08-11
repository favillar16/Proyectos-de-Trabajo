"""
Serializers de productos — API REST
Separados en Read / Write para evitar el anti-patrón de un solo
serializer que intenta cubrir lectura y escritura al mismo tiempo.
"""
from rest_framework import serializers
from .models import (
    Categoria, Marca, Acabado,
    Producto, Variante, ImagenProducto, ImagenVariante,
)
from apps.inventario.models import Stock


# ─── Auxiliares (solo lectura) ────────────────────────────────────────────────

class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Categoria
        fields = ['id', 'nombre', 'tipo', 'descripcion', 'activa', 'orden']


class MarcaSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Marca
        fields = ['id', 'nombre', 'pais_origen', 'activa']


class AcabadoSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Acabado
        fields = ['id', 'nombre', 'descripcion']


# ─── Imágenes ─────────────────────────────────────────────────────────────────

class ImagenProductoSerializer(serializers.ModelSerializer):
    imagen_url = serializers.SerializerMethodField()

    class Meta:
        model  = ImagenProducto
        fields = ['id', 'imagen', 'imagen_url', 'es_principal', 'titulo', 'orden', 'fecha_subida']
        extra_kwargs = {'imagen': {'write_only': True, 'required': False}}

    def get_imagen_url(self, obj):
        request = self.context.get('request')
        if obj.imagen and request:
            return request.build_absolute_uri(obj.imagen.url)
        return obj.imagen.url if obj.imagen else None


class ImagenVarianteSerializer(serializers.ModelSerializer):
    imagen_url = serializers.SerializerMethodField()

    class Meta:
        model  = ImagenVariante
        fields = ['id', 'imagen', 'imagen_url', 'es_principal', 'orden', 'fecha_subida']
        extra_kwargs = {'imagen': {'write_only': True, 'required': False}}

    def get_imagen_url(self, obj):
        request = self.context.get('request')
        if obj.imagen and request:
            return request.build_absolute_uri(obj.imagen.url)
        return obj.imagen.url if obj.imagen else None


# ─── Stock inline ─────────────────────────────────────────────────────────────

class StockInlineSerializer(serializers.ModelSerializer):
    disponible = serializers.DecimalField(
        source='cantidad_disponible', max_digits=10, decimal_places=4, read_only=True
    )
    estado = serializers.CharField(read_only=True)

    class Meta:
        model  = Stock
        fields = [
            'cantidad', 'cantidad_reservada', 'disponible',
            'stock_minimo', 'ubicacion', 'estado',
        ]


# ─── Variante — Lectura ───────────────────────────────────────────────────────

class VarianteReadSerializer(serializers.ModelSerializer):
    acabado          = AcabadoSerializer(read_only=True)
    imagenes         = ImagenVarianteSerializer(many=True, read_only=True)
    stock            = StockInlineSerializer(read_only=True)
    precio_venta     = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    dimension_display = serializers.CharField(read_only=True)
    m2_calculado     = serializers.FloatField(source='m2_por_caja_calculado', read_only=True)
    tiene_stock      = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Variante
        fields = [
            'id', 'sku', 'color', 'calidad',
            'acabado',
            'largo_cm', 'ancho_cm', 'espesor_mm',
            'dimension_display',
            'piezas_por_caja', 'm2_por_caja', 'm2_calculado',
            'peso_kg_caja', 'cajas_por_pallet',
            'precio_diferencial', 'precio_venta',
            'tipo_grifo', 'posicion_grifo', 'montaje_grifo',
            'tipo_ducha', 'tipo_cisterna',
            'activa', 'tiene_stock',
            'imagenes', 'stock',
        ]


# ─── Variante — Escritura ─────────────────────────────────────────────────────

class VarianteWriteSerializer(serializers.ModelSerializer):
    acabado_id = serializers.PrimaryKeyRelatedField(
        queryset=Acabado.objects.all(), source='acabado',
        required=False, allow_null=True,
    )
    # Stock inicial al crear la variante
    stock_inicial  = serializers.DecimalField(
        max_digits=10, decimal_places=4,
        required=False, allow_null=True, write_only=True,
        min_value=0,
    )
    # A la mercadería nueva se la recibe en cajas o pallets, no en m² — mismo
    # criterio que el ajuste manual de stock (apps.inventario.AjusteStockView).
    stock_inicial_unidad = serializers.ChoiceField(
        choices=[
            ('venta', 'Unidad de venta (m²/unidad)'),
            ('caja', 'Cajas'),
            ('pallet', 'Pallets'),
        ],
        required=False, default='venta', write_only=True,
    )
    stock_minimo   = serializers.DecimalField(
        max_digits=10, decimal_places=4,
        required=False, allow_null=True, write_only=True,
        min_value=0,
    )
    ubicacion      = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model  = Variante
        fields = [
            'id', 'sku', 'color', 'calidad', 'acabado_id',
            'largo_cm', 'ancho_cm', 'espesor_mm',
            'piezas_por_caja', 'm2_por_caja', 'peso_kg_caja', 'cajas_por_pallet',
            'precio_diferencial', 'activa',
            'tipo_grifo', 'posicion_grifo', 'montaje_grifo',
            'tipo_ducha', 'tipo_cisterna',
            'stock_inicial', 'stock_inicial_unidad', 'stock_minimo', 'ubicacion',
        ]

    def validate(self, attrs):
        largo = attrs.get('largo_cm')
        ancho = attrs.get('ancho_cm')
        if bool(largo) != bool(ancho):
            raise serializers.ValidationError(
                'Debe indicar largo y ancho juntos, o dejar ambos vacíos.'
            )

        # Cruce m2_por_caja vs. dimensiones — mismo criterio que Variante.clean(),
        # que nunca corre acá porque el ModelViewSet no llama full_clean().
        piezas  = attrs.get('piezas_por_caja')
        m2_caja = attrs.get('m2_por_caja')
        if largo and ancho and piezas and m2_caja:
            calculado = (float(largo) / 100) * (float(ancho) / 100) * float(piezas)
            if abs(float(m2_caja) - calculado) > 0.05:
                raise serializers.ValidationError({
                    'm2_por_caja': (
                        f'El valor ingresado ({m2_caja} m²) no coincide con el calculado '
                        f'({calculado:.4f} m²). Verificar dimensiones o piezas por caja.'
                    )
                })
        return attrs

    def create(self, validated_data):
        stock_inicial        = validated_data.pop('stock_inicial', 0) or 0
        stock_inicial_unidad = validated_data.pop('stock_inicial_unidad', 'venta')
        stock_minimo         = validated_data.pop('stock_minimo', 0)  or 0
        ubicacion            = validated_data.pop('ubicacion', '')

        variante = super().create(validated_data)

        # Si el stock inicial se cargó en cajas o pallets, convertir a la
        # unidad de venta — misma cuenta que usa el ajuste manual de stock
        # (apps.inventario.AjusteStockView) y la recepción de pedidos a
        # proveedor, centralizada en Variante.convertir_a_unidad_venta.
        if stock_inicial > 0 and stock_inicial_unidad != 'venta':
            try:
                stock_inicial = variante.convertir_a_unidad_venta(stock_inicial, stock_inicial_unidad)
            except ValueError as e:
                raise serializers.ValidationError({'stock_inicial': str(e)})

        # La señal ya crea el Stock con cantidad=0.
        if stock_inicial > 0 or stock_minimo > 0 or ubicacion:
            stock = Stock.objects.get(variante=variante)
            if stock_minimo:
                stock.stock_minimo = stock_minimo
            if ubicacion:
                stock.ubicacion = ubicacion
            if stock_inicial > 0:
                # stock_referencia queda fijo en el valor inicial cargado (ya
                # convertido): es la base del 100% contra la que se calculan
                # las alertas de stock bajo/crítico.
                stock.stock_referencia = stock_inicial
            stock.save()

            if stock_inicial > 0:
                # Vía registrar_movimiento (no un update() directo) para que
                # la primera carga de stock también quede en el historial de
                # auditoría, igual que cualquier otro movimiento.
                stock.registrar_movimiento(
                    tipo            = 'entrada',
                    cantidad        = stock_inicial,
                    usuario         = self.context['request'].user,
                    referencia_tipo = 'alta_producto',
                    observaciones   = f'Stock inicial al crear la variante {variante.sku}',
                )
        return variante

    def update(self, instance, validated_data):
        # Actualizar stock si se envían los campos
        stock_inicial        = validated_data.pop('stock_inicial', None)
        stock_inicial_unidad = validated_data.pop('stock_inicial_unidad', 'venta')
        stock_minimo  = validated_data.pop('stock_minimo', None)
        ubicacion     = validated_data.pop('ubicacion', None)

        instance = super().update(instance, validated_data)

        if stock_inicial is not None and stock_inicial > 0 and stock_inicial_unidad != 'venta':
            try:
                stock_inicial = instance.convertir_a_unidad_venta(stock_inicial, stock_inicial_unidad)
            except ValueError as e:
                raise serializers.ValidationError({'stock_inicial': str(e)})

        if any(v is not None for v in [stock_inicial, stock_minimo, ubicacion]):
            stock_qs = Stock.objects.filter(variante=instance)
            update_fields = {}
            if stock_inicial is not None:
                update_fields['cantidad'] = stock_inicial
            if stock_minimo is not None:
                update_fields['stock_minimo'] = stock_minimo
            if ubicacion is not None:
                update_fields['ubicacion'] = ubicacion
            stock_qs.update(**update_fields)

        return instance


# ─── Producto — Lectura ligera (listado / showroom) ───────────────────────────

def _pedido_pendiente_de(obj):
    """
    Primer pedido a proveedor pendiente/en camino de este producto (ya viene
    ordenado por fecha de entrega estimada desde el prefetch en
    `_producto_qs_completo`), o None si no hay ninguno.
    """
    pedidos = getattr(obj, 'pedidos_pendientes_prefetch', None)
    if not pedidos:
        return None
    p = pedidos[0]
    return {
        'id': p.id,
        'estado': p.estado,
        'proveedor_nombre': p.proveedor.nombre,
        'fecha_entrega_estimada': p.fecha_entrega_estimada,
    }


def _puede_ver_costo(context):
    # Solo admin/depósito pueden ver el costo de adquisición y el margen que
    # se deriva de él — el resto del personal (vendedor, encargada de
    # ventas, cajero) no debe recibirlo ni en el listado ni en el detalle.
    request = context.get('request')
    usuario = getattr(request, 'user', None)
    return bool(usuario and getattr(usuario, 'rol', None) in ('admin', 'deposito'))


class ProductoListSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)
    categoria_tipo   = serializers.CharField(source='categoria.tipo',   read_only=True)
    marca_nombre     = serializers.CharField(source='marca.nombre',     read_only=True, allow_null=True)
    imagen_principal = ImagenProductoSerializer(read_only=True)
    stock_total      = serializers.DecimalField(max_digits=10, decimal_places=4, read_only=True)
    variantes_count  = serializers.SerializerMethodField()
    margen_bruto     = serializers.SerializerMethodField()
    precio_costo     = serializers.SerializerMethodField()
    pedido_pendiente = serializers.SerializerMethodField()

    class Meta:
        model  = Producto
        fields = [
            'id', 'codigo', 'nombre', 'slug',
            'categoria_nombre', 'categoria_tipo', 'marca_nombre',
            'precio_base', 'precio_costo', 'unidad_venta',
            'imagen_principal', 'stock_total', 'variantes_count',
            'destacado', 'activo', 'visible_showroom',
            'margen_bruto', 'pedido_pendiente',
            'fecha_creacion',
        ]

    def get_variantes_count(self, obj):
        # Usa el prefetch si ya está cargado
        if hasattr(obj, '_prefetched_objects_cache') and 'variantes' in obj._prefetched_objects_cache:
            return len(obj._prefetched_objects_cache['variantes'])
        return obj.variantes.filter(activa=True).count()

    def get_precio_costo(self, obj):
        return obj.precio_costo if _puede_ver_costo(self.context) else None

    def get_margen_bruto(self, obj):
        return obj.margen_bruto if _puede_ver_costo(self.context) else None

    def get_pedido_pendiente(self, obj):
        return _pedido_pendiente_de(obj)


# ─── Producto — Lectura detallada ─────────────────────────────────────────────

class ProductoDetailSerializer(serializers.ModelSerializer):
    categoria         = CategoriaSerializer(read_only=True)
    marca             = MarcaSerializer(read_only=True, allow_null=True)
    imagenes          = ImagenProductoSerializer(many=True, read_only=True)
    variantes         = VarianteReadSerializer(many=True, read_only=True)
    stock_total       = serializers.DecimalField(max_digits=10, decimal_places=4, read_only=True)
    precio_costo      = serializers.SerializerMethodField()
    margen_bruto      = serializers.SerializerMethodField()
    pedido_pendiente  = serializers.SerializerMethodField()

    class Meta:
        model  = Producto
        fields = [
            'id', 'codigo', 'nombre', 'descripcion', 'slug',
            'categoria', 'marca',
            'precio_base', 'precio_costo', 'unidad_venta',
            'destacado', 'activo', 'visible_showroom',
            'notas_internas', 'stock_total', 'margen_bruto', 'pedido_pendiente',
            'imagenes', 'variantes',
            'fecha_creacion', 'fecha_actualizacion',
        ]

    def get_precio_costo(self, obj):
        return obj.precio_costo if _puede_ver_costo(self.context) else None

    def get_margen_bruto(self, obj):
        return obj.margen_bruto if _puede_ver_costo(self.context) else None

    def get_pedido_pendiente(self, obj):
        return _pedido_pendiente_de(obj)


# ─── Producto — Escritura (crear / editar) ────────────────────────────────────

class ProductoWriteSerializer(serializers.ModelSerializer):
    categoria_id       = serializers.PrimaryKeyRelatedField(
        queryset=Categoria.objects.filter(activa=True),
        source='categoria',
    )
    marca_id           = serializers.PrimaryKeyRelatedField(
        queryset=Marca.objects.filter(activa=True),
        source='marca', required=False, allow_null=True,
    )

    class Meta:
        model  = Producto
        fields = [
            'codigo', 'nombre', 'descripcion',
            'categoria_id', 'marca_id',
            'precio_base', 'precio_costo', 'unidad_venta',
            'destacado', 'activo', 'visible_showroom',
            'notas_internas',
        ]
        # El código se genera automáticamente a partir de la categoría/nombre.
        # Es de solo lectura: el usuario no lo ingresa ni lo edita.
        read_only_fields = ['codigo']

    def validate_precio_base(self, value):
        if value <= 0:
            raise serializers.ValidationError('El precio base debe ser mayor a 0.')
        return value

    def create(self, validated_data):
        if not _puede_ver_costo(self.context):
            validated_data.pop('precio_costo', None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # precio_costo no viaja al frontend para roles sin permiso (ver
        # ProductoDetailSerializer) — si el formulario de un vendedor lo
        # reenvía en null porque nunca lo vio, no debe borrar el costo real
        # ya cargado por admin/depósito.
        if not _puede_ver_costo(self.context):
            validated_data.pop('precio_costo', None)
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        # Al crear/editar devolver el detalle completo
        return ProductoDetailSerializer(instance, context=self.context).data
