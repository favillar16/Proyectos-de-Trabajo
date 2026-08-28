"""
Serializers de ventas — Nota de Pedido
"""
from rest_framework import serializers
from django.db import transaction
from .models import NotaPedido, ItemPedido, Cliente
from apps.productos.models import Variante


def _oculta_montos(context):
    # Depósito prepara pedidos pero no maneja caja ni negocia precio — no
    # debe ver montos (documentado explícitamente en funcionalidades_sistema.md).
    request = context.get('request')
    usuario = getattr(request, 'user', None)
    return bool(usuario and getattr(usuario, 'rol', None) == 'deposito')


class ItemPedidoReadSerializer(serializers.ModelSerializer):
    sku             = serializers.CharField(source='variante.sku',             read_only=True)
    producto_nombre = serializers.CharField(source='variante.producto.nombre', read_only=True)
    descripcion     = serializers.SerializerMethodField()
    imagen_url      = serializers.SerializerMethodField()
    stock_disponible = serializers.SerializerMethodField()
    precio_unitario = serializers.SerializerMethodField()
    descuento_item  = serializers.SerializerMethodField()
    subtotal        = serializers.SerializerMethodField()

    class Meta:
        model  = ItemPedido
        fields = [
            'id', 'variante_id', 'sku', 'producto_nombre', 'descripcion',
            'cantidad', 'precio_unitario', 'descuento_item', 'subtotal',
            'observaciones', 'preparado', 'cantidad_preparada', 'imagen_url',
            'stock_disponible',
        ]

    def get_precio_unitario(self, obj):
        return None if _oculta_montos(self.context) else obj.precio_unitario

    def get_descuento_item(self, obj):
        return None if _oculta_montos(self.context) else obj.descuento_item

    def get_subtotal(self, obj):
        return None if _oculta_montos(self.context) else obj.subtotal

    def get_descripcion(self, obj):
        v = obj.variante
        partes = [v.producto.nombre]
        if v.dimension_display: partes.append(v.dimension_display)
        if v.color:             partes.append(v.color)
        if v.acabado:           partes.append(v.acabado.nombre)
        return ' — '.join(partes)

    def get_imagen_url(self, obj):
        request = self.context.get('request')
        img = (obj.variante.imagenes.filter(es_principal=True).first()
               or obj.variante.imagenes.first()
               or obj.variante.producto.imagenes.filter(es_principal=True).first()
               or obj.variante.producto.imagenes.first())
        if img and img.imagen:
            return request.build_absolute_uri(img.imagen.url) if request else img.imagen.url
        return None

    def get_stock_disponible(self, obj):
        try:
            return float(obj.variante.stock.cantidad_disponible)
        except Exception:
            return 0.0


class ItemPedidoWriteSerializer(serializers.Serializer):
    variante_id     = serializers.PrimaryKeyRelatedField(queryset=Variante.objects.filter(activa=True))
    cantidad        = serializers.DecimalField(max_digits=10, decimal_places=4, min_value=0.0001)
    precio_unitario = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    descuento_item  = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)
    observaciones   = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        # Si no se especifica precio, usar el de la variante
        if 'precio_unitario' not in attrs or attrs.get('precio_unitario') is None:
            attrs['precio_unitario'] = attrs['variante_id'].precio_venta
        return attrs


class NotaPedidoReadSerializer(serializers.ModelSerializer):
    items            = ItemPedidoReadSerializer(many=True, read_only=True)
    vendedor_nombre  = serializers.CharField(source='vendedor.nombre_completo', read_only=True)
    preparado_por_nombre = serializers.SerializerMethodField()
    estado_display   = serializers.CharField(source='get_estado_display', read_only=True)
    items_count      = serializers.SerializerMethodField()
    todos_preparados = serializers.SerializerMethodField()
    subtotal         = serializers.SerializerMethodField()
    descuento        = serializers.SerializerMethodField()
    total            = serializers.SerializerMethodField()
    total_ajustado   = serializers.SerializerMethodField()
    monto_a_cobrar   = serializers.SerializerMethodField()

    class Meta:
        model  = NotaPedido
        fields = [
            'id', 'numero', 'estado', 'estado_display',
            'vendedor_id', 'vendedor_nombre',
            'cliente_id', 'cliente_nombre', 'cliente_ruc',
            'cliente_telefono', 'cliente_observaciones',
            'subtotal', 'descuento', 'total', 'total_ajustado', 'monto_a_cobrar',
            'observaciones_deposito',
            'preparado_por_nombre', 'fecha_preparacion',
            'fecha_creacion', 'fecha_actualizacion',
            'items', 'items_count', 'todos_preparados',
            'puede_preparar', 'puede_cobrar',
        ]

    def get_preparado_por_nombre(self, obj):
        return obj.preparado_por.nombre_completo if obj.preparado_por else None

    def get_items_count(self, obj):
        return obj.items.count()

    def get_todos_preparados(self, obj):
        items = obj.items.all()
        return bool(items) and all(i.preparado for i in items)

    def get_subtotal(self, obj):
        return None if _oculta_montos(self.context) else obj.subtotal

    def get_descuento(self, obj):
        return None if _oculta_montos(self.context) else obj.descuento

    def get_total(self, obj):
        return None if _oculta_montos(self.context) else obj.total

    def get_total_ajustado(self, obj):
        return None if _oculta_montos(self.context) else obj.total_ajustado

    def get_monto_a_cobrar(self, obj):
        return None if _oculta_montos(self.context) else obj.monto_a_cobrar


class NotaPedidoListSerializer(serializers.ModelSerializer):
    """Versión ligera para listados."""
    vendedor_nombre = serializers.CharField(source='vendedor.nombre_completo', read_only=True)
    estado_display  = serializers.CharField(source='get_estado_display', read_only=True)
    items_count     = serializers.IntegerField(source='items.count', read_only=True)
    todos_preparados = serializers.SerializerMethodField()
    total           = serializers.SerializerMethodField()
    total_ajustado  = serializers.SerializerMethodField()
    monto_a_cobrar  = serializers.SerializerMethodField()

    class Meta:
        model  = NotaPedido
        fields = [
            'id', 'numero', 'estado', 'estado_display',
            'vendedor_nombre', 'cliente_nombre',
            'total', 'total_ajustado', 'monto_a_cobrar',
            'items_count', 'todos_preparados',
            'fecha_creacion', 'puede_preparar', 'puede_cobrar',
        ]

    def get_todos_preparados(self, obj):
        items = obj.items.all()
        return bool(items) and all(i.preparado for i in items)

    def get_total(self, obj):
        return None if _oculta_montos(self.context) else obj.total

    def get_total_ajustado(self, obj):
        return None if _oculta_montos(self.context) else obj.total_ajustado

    def get_monto_a_cobrar(self, obj):
        return None if _oculta_montos(self.context) else obj.monto_a_cobrar


class NotaPedidoCreateSerializer(serializers.Serializer):
    cliente_id            = serializers.IntegerField(required=False, allow_null=True)
    cliente_nombre        = serializers.CharField(required=False, allow_blank=True, default='')
    cliente_ruc           = serializers.CharField(required=False, allow_blank=True, default='')
    cliente_telefono      = serializers.CharField(required=False, allow_blank=True, default='')
    cliente_observaciones = serializers.CharField(required=False, allow_blank=True, default='')
    descuento             = serializers.DecimalField(max_digits=14, decimal_places=2, default=0, min_value=0)
    total_ajustado        = serializers.DecimalField(max_digits=14, decimal_places=2,
                              required=False, allow_null=True, min_value=0)
    items                 = ItemPedidoWriteSerializer(many=True, min_length=1)

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError('La nota debe tener al menos un producto.')
        return items

    @transaction.atomic
    def create(self, validated_data):
        from .models import StockInsuficienteError, Cliente

        items_data = validated_data.pop('items')
        vendedor   = self.context['request'].user

        # ¿Este usuario tiene la facultad de fijar precios? (admin / encargada de ventas)
        puede_precio = (
            hasattr(vendedor, 'puede_editar_precio_pedido')
            and vendedor.puede_editar_precio_pedido()
        )

        # Resolver cliente del padrón si se envió cliente_id
        cliente_obj = None
        cliente_id = validated_data.get('cliente_id')
        if cliente_id:
            cliente_obj = Cliente.objects.filter(id=cliente_id, activo=True).first()

        pedido = NotaPedido(
            vendedor              = vendedor,
            cliente               = cliente_obj,
            cliente_nombre        = validated_data.get('cliente_nombre', '') or (cliente_obj.razon_social if cliente_obj else ''),
            cliente_ruc           = validated_data.get('cliente_ruc', '') or (cliente_obj.ruc if cliente_obj else ''),
            cliente_telefono      = validated_data.get('cliente_telefono', '') or (cliente_obj.telefono if cliente_obj else ''),
            cliente_observaciones = validated_data.get('cliente_observaciones', ''),
            descuento             = validated_data.get('descuento', 0) if puede_precio else 0,
        )
        pedido.save()

        for item_data in items_data:
            variante = item_data['variante_id']
            # Si el usuario NO puede editar precios, se ignora cualquier precio
            # enviado y se usa SIEMPRE el precio de catálogo de la variante.
            if puede_precio:
                precio = item_data.get('precio_unitario') or variante.precio_venta
                desc_item = item_data.get('descuento_item', 0)
            else:
                precio = variante.precio_venta
                desc_item = 0
            ItemPedido.objects.create(
                pedido          = pedido,
                variante        = variante,
                cantidad        = item_data['cantidad'],
                precio_unitario = precio,
                descuento_item  = desc_item,
                observaciones   = item_data.get('observaciones', ''),
            )

        # Recalcular totales
        pedido.subtotal = sum(i.subtotal for i in pedido.items.all())
        pedido.total    = pedido.subtotal - pedido.descuento

        # Monto ajustado (precio negociado) — SOLO si el usuario puede fijar precios
        if puede_precio:
            ajustado = validated_data.get('total_ajustado')
            if ajustado is not None and ajustado != pedido.total:
                pedido.total_ajustado = ajustado

        pedido.save(update_fields=['subtotal', 'total', 'total_ajustado'])

        # Reservar stock — si falla, la transacción completa se revierte
        try:
            pedido.reservar_stock(usuario=vendedor)
        except StockInsuficienteError as e:
            raise serializers.ValidationError({
                'stock_insuficiente': [
                    f'{err["sku"]}: {err["error"]}' for err in e.errores
                ]
            }) from e

        return pedido


class ClienteSerializer(serializers.ModelSerializer):
    tipo_label      = serializers.CharField(source='get_tipo_display', read_only=True)
    condicion_label = serializers.CharField(source='get_condicion_venta_display', read_only=True)

    class Meta:
        model  = Cliente
        fields = [
            'id', 'razon_social', 'ruc', 'tipo', 'tipo_label',
            'telefono', 'email', 'direccion',
            'condicion_venta', 'condicion_label', 'permite_ajuste_precio',
            'activo', 'notas', 'fecha_creacion',
        ]
        read_only_fields = ['fecha_creacion']
