"""
Apps: costos — Views completas (gastos, proveedores, salarios, pedidos a proveedor)
"""
from decimal import Decimal
from rest_framework import views, status
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Sum, Count, Q, F as models_F
from datetime import date, timedelta

from rest_framework import serializers
from .models import (
    CategoriaGasto, Empleado, GastoOperativo,
    Proveedor, PedidoProveedor,
)
from apps.productos.models import Producto
from apps.inventario.models import Stock
from apps.usuarios.permissions import EsAdmin


# ════════════════════════════════════════════════════════
# SERIALIZERS
# ════════════════════════════════════════════════════════

class CategoriaGastoSerializer(serializers.ModelSerializer):
    tipo_label = serializers.CharField(source="get_tipo_display", read_only=True)
    class Meta:
        model  = CategoriaGasto
        fields = ["id","nombre","tipo","tipo_label","descripcion","activa","orden"]


class ProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Proveedor
        fields = ["id","nombre","ruc","contacto","telefono","email",
                  "direccion","rubro","activo","notas","fecha_creacion"]
        read_only_fields = ["fecha_creacion"]


class EmpleadoSerializer(serializers.ModelSerializer):
    usuario_id = serializers.PrimaryKeyRelatedField(
        source="usuario", queryset=get_user_model().objects.all(),
        required=False, allow_null=True,
    )

    class Meta:
        model  = Empleado
        fields = ["id","nombre_completo","cargo","salario_base","activo",
                  "fecha_ingreso","usuario_id","notas","fecha_creacion"]
        read_only_fields = ["fecha_creacion"]


class GastoReadSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source="categoria.nombre",  read_only=True)
    categoria_tipo   = serializers.CharField(source="categoria.tipo",    read_only=True)
    empleado_nombre  = serializers.SerializerMethodField()
    proveedor_nombre = serializers.SerializerMethodField()
    estado_label     = serializers.CharField(source="get_estado_display", read_only=True)
    metodo_pago_label= serializers.CharField(source="get_metodo_pago_display", read_only=True)
    mes_label        = serializers.CharField(source="periodo_label",      read_only=True)
    dias_cheque      = serializers.IntegerField(source="dias_para_cobro_cheque", read_only=True)
    registrado_por_nombre = serializers.CharField(
        source="registrado_por.nombre_completo", read_only=True)

    class Meta:
        model  = GastoOperativo
        fields = ["id","descripcion","monto","anio","mes","mes_label",
            "categoria_id","categoria_nombre","categoria_tipo",
            "empleado_id","empleado_nombre",
            "proveedor_id","proveedor_nombre",
            "estado","estado_label","fecha_pago",
            "metodo_pago","metodo_pago_label",
            "cheque_numero","cheque_banco","cheque_fecha_cobro","dias_cheque",
            "comprobante","notas",
            "registrado_por_nombre","fecha_creacion"]

    def get_empleado_nombre(self, obj):
        return obj.empleado.nombre_completo if obj.empleado else None
    def get_proveedor_nombre(self, obj):
        return obj.proveedor.nombre if obj.proveedor else None


class GastoWriteSerializer(serializers.Serializer):
    descripcion  = serializers.CharField(max_length=250)
    monto        = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0.01)
    categoria_id = serializers.PrimaryKeyRelatedField(
        queryset=CategoriaGasto.objects.filter(activa=True), source="categoria")
    empleado_id  = serializers.PrimaryKeyRelatedField(
        queryset=Empleado.objects.filter(activo=True),
        source="empleado", required=False, allow_null=True)
    proveedor_id = serializers.PrimaryKeyRelatedField(
        queryset=Proveedor.objects.filter(activo=True),
        source="proveedor", required=False, allow_null=True)
    anio         = serializers.IntegerField(min_value=2020, max_value=2100)
    mes          = serializers.IntegerField(min_value=1, max_value=12)
    estado       = serializers.ChoiceField(choices=GastoOperativo.ESTADOS,
                       default=GastoOperativo.ESTADO_PENDIENTE)
    fecha_pago   = serializers.DateField(required=False, allow_null=True)
    metodo_pago  = serializers.ChoiceField(choices=GastoOperativo.METODOS_PAGO,
                       required=False, allow_blank=True, default="")
    cheque_numero      = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    cheque_banco       = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    cheque_fecha_cobro = serializers.DateField(required=False, allow_null=True)
    comprobante  = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    notas        = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        # Si es cheque, la fecha de cobro es obligatoria
        if attrs.get('metodo_pago') == GastoOperativo.PAGO_CHEQUE:
            if not attrs.get('cheque_fecha_cobro'):
                raise serializers.ValidationError({
                    'cheque_fecha_cobro': 'La fecha de cobro es obligatoria para pagos con cheque.'
                })
        return attrs


class PedidoProveedorReadSerializer(serializers.ModelSerializer):
    proveedor_nombre = serializers.CharField(source="proveedor.nombre", read_only=True)
    estado_label     = serializers.CharField(source="get_estado_display", read_only=True)
    dias_entrega     = serializers.IntegerField(source="dias_para_entrega", read_only=True)
    producto_nombre  = serializers.CharField(source="producto.nombre", read_only=True, allow_null=True)
    producto_unidad_venta = serializers.CharField(source="producto.unidad_venta", read_only=True, allow_null=True)
    registrado_por_nombre = serializers.CharField(
        source="registrado_por.nombre_completo", read_only=True)

    class Meta:
        model  = PedidoProveedor
        fields = ["id","proveedor_id","proveedor_nombre","descripcion",
                  "producto_id","producto_nombre","producto_unidad_venta","cantidad_pedida",
                  "monto_estimado","fecha_pedido","fecha_entrega_estimada",
                  "fecha_entrega_real","estado","estado_label","dias_entrega",
                  "notas","registrado_por_nombre","fecha_creacion"]


class PedidoProveedorWriteSerializer(serializers.Serializer):
    proveedor_id   = serializers.PrimaryKeyRelatedField(
        queryset=Proveedor.objects.filter(activo=True), source="proveedor")
    descripcion    = serializers.CharField(max_length=250)
    producto_id    = serializers.PrimaryKeyRelatedField(
        queryset=Producto.objects.filter(activo=True), source="producto",
        required=False, allow_null=True)
    cantidad_pedida = serializers.DecimalField(max_digits=10, decimal_places=4,
                        required=False, allow_null=True, min_value=0.0001)
    monto_estimado = serializers.DecimalField(max_digits=14, decimal_places=2,
                        required=False, allow_null=True, min_value=0)
    fecha_pedido   = serializers.DateField(required=False)
    fecha_entrega_estimada = serializers.DateField()
    fecha_entrega_real = serializers.DateField(required=False, allow_null=True)
    estado         = serializers.ChoiceField(choices=PedidoProveedor.ESTADOS,
                        default=PedidoProveedor.ESTADO_PENDIENTE)
    notas          = serializers.CharField(required=False, allow_blank=True, default="")


# ════════════════════════════════════════════════════════
# CATEGORÍAS
# ════════════════════════════════════════════════════════

class CategoriaGastoListView(views.APIView):
    permission_classes = [EsAdmin]
    def get(self, request):
        qs = CategoriaGasto.objects.all()
        if request.query_params.get("activas") == "1": qs = qs.filter(activa=True)
        return Response({"results": CategoriaGastoSerializer(qs, many=True).data})
    def post(self, request):
        s = CategoriaGastoSerializer(data=request.data)
        if not s.is_valid(): return Response(s.errors, status=400)
        return Response(CategoriaGastoSerializer(s.save()).data, status=201)


# ════════════════════════════════════════════════════════
# PROVEEDORES
# ════════════════════════════════════════════════════════

class ProveedorListCreateView(views.APIView):
    permission_classes = [EsAdmin]
    def get(self, request):
        qs = Proveedor.objects.all()
        if request.query_params.get("activos") == "1": qs = qs.filter(activo=True)
        return Response({"results": ProveedorSerializer(qs, many=True).data, "count": qs.count()})
    def post(self, request):
        s = ProveedorSerializer(data=request.data)
        if not s.is_valid(): return Response(s.errors, status=400)
        return Response(ProveedorSerializer(s.save()).data, status=201)


class ProveedorDetailView(views.APIView):
    permission_classes = [EsAdmin]
    def get(self, request, pk):
        return Response(ProveedorSerializer(get_object_or_404(Proveedor, pk=pk)).data)
    def patch(self, request, pk):
        prov = get_object_or_404(Proveedor, pk=pk)
        s = ProveedorSerializer(prov, data=request.data, partial=True)
        if not s.is_valid(): return Response(s.errors, status=400)
        return Response(ProveedorSerializer(s.save()).data)
    def delete(self, request, pk):
        prov = get_object_or_404(Proveedor, pk=pk)
        prov.activo = False; prov.save(update_fields=["activo"])
        return Response({"detail": "Proveedor desactivado."})


# ════════════════════════════════════════════════════════
# EMPLEADOS
# ════════════════════════════════════════════════════════

class EmpleadoListCreateView(views.APIView):
    permission_classes = [EsAdmin]
    def get(self, request):
        qs = Empleado.objects.all()
        if request.query_params.get("activos") == "1": qs = qs.filter(activo=True)
        return Response({"results": EmpleadoSerializer(qs, many=True).data, "count": qs.count()})
    def post(self, request):
        s = EmpleadoSerializer(data=request.data)
        if not s.is_valid(): return Response(s.errors, status=400)
        return Response(EmpleadoSerializer(s.save()).data, status=201)


class EmpleadoDetailView(views.APIView):
    permission_classes = [EsAdmin]
    def get(self, request, pk):
        return Response(EmpleadoSerializer(get_object_or_404(Empleado, pk=pk)).data)
    def patch(self, request, pk):
        emp = get_object_or_404(Empleado, pk=pk)
        s = EmpleadoSerializer(emp, data=request.data, partial=True)
        if not s.is_valid(): return Response(s.errors, status=400)
        return Response(EmpleadoSerializer(s.save()).data)
    def delete(self, request, pk):
        emp = get_object_or_404(Empleado, pk=pk)
        emp.activo = False; emp.save(update_fields=["activo"])
        return Response({"detail": "Empleado desactivado."})


# ════════════════════════════════════════════════════════
# GASTOS
# ════════════════════════════════════════════════════════

class GastoListCreateView(views.APIView):
    permission_classes = [EsAdmin]
    def get(self, request):
        qs = GastoOperativo.objects.select_related("categoria","empleado","proveedor","registrado_por")
        for param, field in [("anio","anio"),("mes","mes"),("estado","estado"),
                             ("categoria","categoria_id"),("proveedor","proveedor_id"),
                             ("metodo_pago","metodo_pago")]:
            v = request.query_params.get(param)
            if v: qs = qs.filter(**{field: v})
        total = float(qs.aggregate(t=Sum("monto"))["t"] or 0)
        return Response({"results": GastoReadSerializer(qs, many=True).data,
                         "count": qs.count(), "total": total})
    def post(self, request):
        s = GastoWriteSerializer(data=request.data)
        if not s.is_valid(): return Response(s.errors, status=400)
        gasto = GastoOperativo.objects.create(registrado_por=request.user, **s.validated_data)
        return Response(GastoReadSerializer(gasto).data, status=201)


class GastoDetailView(views.APIView):
    permission_classes = [EsAdmin]
    def get(self, request, pk):
        g = get_object_or_404(GastoOperativo.objects.select_related("categoria","empleado","proveedor","registrado_por"), pk=pk)
        return Response(GastoReadSerializer(g).data)
    def patch(self, request, pk):
        g = get_object_or_404(GastoOperativo, pk=pk)
        s = GastoWriteSerializer(data=request.data, partial=True)
        if not s.is_valid(): return Response(s.errors, status=400)
        for campo, valor in s.validated_data.items(): setattr(g, campo, valor)
        g.save()
        return Response(GastoReadSerializer(GastoOperativo.objects.select_related("categoria","empleado","proveedor","registrado_por").get(pk=pk)).data)
    def delete(self, request, pk):
        get_object_or_404(GastoOperativo, pk=pk).delete()
        return Response(status=204)


# ════════════════════════════════════════════════════════
# PEDIDOS A PROVEEDOR
# ════════════════════════════════════════════════════════

class PedidoProveedorListCreateView(views.APIView):
    permission_classes = [EsAdmin]
    def get(self, request):
        qs = PedidoProveedor.objects.select_related("proveedor","registrado_por")
        for param, field in [("estado","estado"),("proveedor","proveedor_id")]:
            v = request.query_params.get(param)
            if v: qs = qs.filter(**{field: v})
        return Response({"results": PedidoProveedorReadSerializer(qs, many=True).data,
                         "count": qs.count()})
    def post(self, request):
        s = PedidoProveedorWriteSerializer(data=request.data)
        if not s.is_valid(): return Response(s.errors, status=400)
        pedido = PedidoProveedor.objects.create(registrado_por=request.user, **s.validated_data)
        return Response(PedidoProveedorReadSerializer(pedido).data, status=201)


class PedidoProveedorDetailView(views.APIView):
    permission_classes = [EsAdmin]
    def get(self, request, pk):
        p = get_object_or_404(PedidoProveedor.objects.select_related("proveedor","registrado_por"), pk=pk)
        return Response(PedidoProveedorReadSerializer(p).data)
    def patch(self, request, pk):
        p = get_object_or_404(PedidoProveedor, pk=pk)
        s = PedidoProveedorWriteSerializer(data=request.data, partial=True)
        if not s.is_valid(): return Response(s.errors, status=400)

        estado_anterior = p.estado
        estado_nuevo    = s.validated_data.get('estado', p.estado)
        pasa_a_recibido = (
            estado_nuevo == PedidoProveedor.ESTADO_RECIBIDO
            and estado_anterior != PedidoProveedor.ESTADO_RECIBIDO
        )

        variante = None
        cantidad_recibida = None
        if pasa_a_recibido:
            producto = s.validated_data.get('producto', p.producto)
            if producto:
                variantes_activas = list(producto.variantes.filter(activa=True))
                if not variantes_activas:
                    return Response(
                        {'error': f'"{producto.nombre}" no tiene variantes activas; no se puede cargar el stock.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if len(variantes_activas) == 1:
                    variante = variantes_activas[0]
                else:
                    variante_id = request.data.get('variante_id')
                    if not variante_id:
                        return Response({
                            'error': 'Este producto tiene varias variantes; indicá a cuál entra el stock.',
                            'variantes': [
                                {'id': v.id, 'sku': v.sku, 'descripcion': str(v)}
                                for v in variantes_activas
                            ],
                        }, status=status.HTTP_400_BAD_REQUEST)
                    variante = next((v for v in variantes_activas if v.id == int(variante_id)), None)
                    if not variante:
                        return Response(
                            {'error': 'La variante indicada no pertenece a este producto.'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                cantidad_recibida_raw = request.data.get('cantidad_recibida') or s.validated_data.get('cantidad_pedida') or p.cantidad_pedida
                if not cantidad_recibida_raw or Decimal(str(cantidad_recibida_raw)) <= 0:
                    return Response(
                        {'error': 'Indicá la cantidad recibida para sumar al stock.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                # Misma conversión cajas/pallets → unidad de venta que usa el
                # ajuste manual de stock (apps.inventario), centralizada en
                # Variante.convertir_a_unidad_venta.
                unidad_recibido = request.data.get('unidad_recibido', 'venta')
                try:
                    cantidad_recibida = variante.convertir_a_unidad_venta(cantidad_recibida_raw, unidad_recibido)
                except ValueError as e:
                    return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        for campo, valor in s.validated_data.items(): setattr(p, campo, valor)
        # Si pasa a recibido y no tiene fecha real, ponerla hoy
        if p.estado == PedidoProveedor.ESTADO_RECIBIDO and not p.fecha_entrega_real:
            p.fecha_entrega_real = date.today()

        with transaction.atomic():
            p.save()
            if pasa_a_recibido and variante:
                stock = Stock.objects.select_for_update().get(variante=variante)
                stock.registrar_movimiento(
                    'entrada', cantidad_recibida, request.user,
                    referencia_tipo='pedido_proveedor', referencia_id=p.id,
                    observaciones=f'Pedido #{p.id} a {p.proveedor.nombre} — {p.descripcion[:60]}',
                )

        return Response(PedidoProveedorReadSerializer(PedidoProveedor.objects.select_related("proveedor","registrado_por").get(pk=pk)).data)
    def delete(self, request, pk):
        get_object_or_404(PedidoProveedor, pk=pk).delete()
        return Response(status=204)


# ════════════════════════════════════════════════════════
# ALERTAS (cheques por cobrar + pedidos por llegar)
# ════════════════════════════════════════════════════════

class AlertasCostosView(views.APIView):
    """
    GET /costos/alertas/?dias=7
    Devuelve cheques cuyo plazo de cobro se acerca y pedidos a proveedor
    cuya entrega está próxima o atrasada.
    """
    permission_classes = [EsAdmin]

    def get(self, request):
        dias = int(request.query_params.get("dias", 7))
        hoy = date.today()
        limite = hoy + timedelta(days=dias)

        # Cheques: pendientes con fecha de cobro <= límite (incluye vencidos)
        cheques_qs = GastoOperativo.objects.filter(
            metodo_pago=GastoOperativo.PAGO_CHEQUE,
            cheque_fecha_cobro__isnull=False,
            cheque_fecha_cobro__lte=limite,
        ).exclude(estado=GastoOperativo.ESTADO_CANCELADO).select_related("proveedor")

        cheques = []
        for g in cheques_qs:
            d = (g.cheque_fecha_cobro - hoy).days
            cheques.append({
                "id": g.id,
                "proveedor": g.proveedor.nombre if g.proveedor else (g.descripcion or "Proveedor"),
                "monto": float(g.monto),
                "fecha_cobro": g.cheque_fecha_cobro.isoformat(),
                "dias": d,
                "cheque_numero": g.cheque_numero,
                "cheque_banco": g.cheque_banco,
                "vencido": d < 0,
            })

        # Pedidos a proveedor: pendientes/en camino con entrega <= límite
        pedidos_qs = PedidoProveedor.objects.filter(
            estado__in=[PedidoProveedor.ESTADO_PENDIENTE, PedidoProveedor.ESTADO_EN_CAMINO],
            fecha_entrega_estimada__lte=limite,
        ).select_related("proveedor")

        pedidos = []
        for p in pedidos_qs:
            d = (p.fecha_entrega_estimada - hoy).days
            pedidos.append({
                "id": p.id,
                "proveedor": p.proveedor.nombre,
                "descripcion": p.descripcion,
                "fecha_entrega": p.fecha_entrega_estimada.isoformat(),
                "dias": d,
                "atrasado": d < 0,
            })

        cheques.sort(key=lambda x: x["dias"])
        pedidos.sort(key=lambda x: x["dias"])

        return Response({
            "cheques":  cheques,
            "pedidos":  pedidos,
            "total_alertas": len(cheques) + len(pedidos),
        })


# ════════════════════════════════════════════════════════
# RESUMEN (para dashboard)
# ════════════════════════════════════════════════════════

class ResumenCostosView(views.APIView):
    permission_classes = [EsAdmin]
    def get(self, request):
        hoy  = date.today()
        anio = int(request.query_params.get("anio", hoy.year))
        mes  = int(request.query_params.get("mes",  hoy.month))
        qs = GastoOperativo.objects.filter(anio=anio, mes=mes).exclude(estado=GastoOperativo.ESTADO_CANCELADO)
        total      = float(qs.aggregate(t=Sum("monto"))["t"] or 0)
        pagados    = float(qs.filter(estado=GastoOperativo.ESTADO_PAGADO).aggregate(t=Sum("monto"))["t"] or 0)
        pendientes = float(qs.filter(estado=GastoOperativo.ESTADO_PENDIENTE).aggregate(t=Sum("monto"))["t"] or 0)
        por_tipo = {}
        for g in qs.select_related("categoria"):
            por_tipo[g.categoria.tipo] = por_tipo.get(g.categoria.tipo, 0) + float(g.monto)
        por_categoria = list(qs.values(nombre=models_F("categoria__nombre"))
            .annotate(total=Sum("monto"), cantidad=Count("id")).order_by("-total"))
        masa_salarial = float(Empleado.objects.filter(activo=True).aggregate(t=Sum("salario_base"))["t"] or 0)
        return Response({
            "periodo":       {"anio": anio, "mes": mes},
            "total_gastos":  total,
            "pagados":       pagados,
            "pendientes":    pendientes,
            "por_tipo":      por_tipo,
            "por_categoria": [{"nombre": p["nombre"], "total": float(p["total"]), "cantidad": p["cantidad"]} for p in por_categoria],
            "masa_salarial": masa_salarial,
        })
