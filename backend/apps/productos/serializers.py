"""
Serializers de productos — API REST
Separados en Read / Write para evitar el anti-patrón de un solo
serializer que intenta cubrir lectura y escritura al mismo tiempo.
"""
from rest_framework import serializers
from django.db import transaction
from .models import (
    Categoria, Marca, Acabado, TipoInstalacion,
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


class TipoInstalacionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = TipoInstalacion
        fields = ['id', 'nombre']


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
            'peso_kg_caja',
            'precio_diferencial', 'precio_venta',
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
            'piezas_por_caja', 'm2_por_caja', 'peso_kg_caja',
            'precio_diferencial', 'activa',
            'stock_inicial', 'stock_minimo', 'ubicacion',
        ]

    def validate(self, attrs):
        largo = attrs.get('largo_cm')
        ancho = attrs.get('ancho_cm')
        if bool(largo) != bool(ancho):
            raise serializers.ValidationError(
                'Debe indicar largo y ancho juntos, o dejar ambos vacíos.'
            )
        return attrs

    def create(self, validated_data):
        stock_inicial = validated_data.pop('stock_inicial', 0) or 0
        stock_minimo  = validated_data.pop('stock_minimo', 0)  or 0
        ubicacion     = validated_data.pop('ubicacion', '')

        variante = super().create(validated_data)

        # La señal ya crea el Stock con cantidad=0; lo actualizamos si hay inicial
        if stock_inicial > 0 or stock_minimo > 0 or ubicacion:
            Stock.objects.filter(variante=variante).update(
                cantidad     = stock_inicial,
                stock_minimo = stock_minimo,
                ubicacion    = ubicacion,
            )
        return variante

    def update(self, instance, validated_data):
        # Actualizar stock si se envían los campos
        stock_inicial = validated_data.pop('stock_inicial', None)
        stock_minimo  = validated_data.pop('stock_minimo', None)
        ubicacion     = validated_data.pop('ubicacion', None)

        instance = super().update(instance, validated_data)

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

class ProductoListSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)
    categoria_tipo   = serializers.CharField(source='categoria.tipo',   read_only=True)
    marca_nombre     = serializers.CharField(source='marca.nombre',     read_only=True, allow_null=True)
    imagen_principal = ImagenProductoSerializer(read_only=True)
    stock_total      = serializers.DecimalField(max_digits=10, decimal_places=4, read_only=True)
    variantes_count  = serializers.SerializerMethodField()
    margen_bruto     = serializers.FloatField(read_only=True)

    class Meta:
        model  = Producto
        fields = [
            'id', 'codigo', 'nombre', 'slug',
            'categoria_nombre', 'categoria_tipo', 'marca_nombre',
            'precio_base', 'unidad_venta',
            'imagen_principal', 'stock_total', 'variantes_count',
            'destacado', 'activo', 'visible_showroom',
            'margen_bruto',
            'fecha_creacion',
        ]

    def get_variantes_count(self, obj):
        # Usa el prefetch si ya está cargado
        if hasattr(obj, '_prefetched_objects_cache') and 'variantes' in obj._prefetched_objects_cache:
            return len(obj._prefetched_objects_cache['variantes'])
        return obj.variantes.filter(activa=True).count()


# ─── Producto — Lectura detallada ─────────────────────────────────────────────

class ProductoDetailSerializer(serializers.ModelSerializer):
    categoria         = CategoriaSerializer(read_only=True)
    marca             = MarcaSerializer(read_only=True, allow_null=True)
    tipos_instalacion = TipoInstalacionSerializer(many=True, read_only=True)
    imagenes          = ImagenProductoSerializer(many=True, read_only=True)
    variantes         = VarianteReadSerializer(many=True, read_only=True)
    stock_total       = serializers.DecimalField(max_digits=10, decimal_places=4, read_only=True)
    margen_bruto      = serializers.FloatField(read_only=True)

    class Meta:
        model  = Producto
        fields = [
            'id', 'codigo', 'nombre', 'descripcion', 'slug',
            'categoria', 'marca', 'tipos_instalacion',
            'precio_base', 'precio_costo', 'unidad_venta',
            'destacado', 'activo', 'visible_showroom',
            'notas_internas', 'stock_total', 'margen_bruto',
            'imagenes', 'variantes',
            'fecha_creacion', 'fecha_actualizacion',
        ]


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
    tipos_instalacion_ids = serializers.PrimaryKeyRelatedField(
        queryset=TipoInstalacion.objects.all(),
        source='tipos_instalacion',
        many=True, required=False,
    )

    class Meta:
        model  = Producto
        fields = [
            'codigo', 'nombre', 'descripcion',
            'categoria_id', 'marca_id', 'tipos_instalacion_ids',
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

    @transaction.atomic
    def create(self, validated_data):
        tipos = validated_data.pop('tipos_instalacion', [])
        producto = super().create(validated_data)
        if tipos:
            producto.tipos_instalacion.set(tipos)
        return producto

    @transaction.atomic
    def update(self, instance, validated_data):
        tipos = validated_data.pop('tipos_instalacion', None)
        producto = super().update(instance, validated_data)
        if tipos is not None:
            producto.tipos_instalacion.set(tipos)
        return producto

    def to_representation(self, instance):
        # Al crear/editar devolver el detalle completo
        return ProductoDetailSerializer(instance, context=self.context).data
