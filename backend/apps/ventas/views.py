"""
Views de ventas — Nota de Pedido
Cada cambio de estado emite un evento WebSocket a los grupos correspondientes.
"""
from rest_framework import views, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import NotaPedido, ItemPedido, Cliente
from .serializers import (
    NotaPedidoReadSerializer,
    NotaPedidoListSerializer,
    NotaPedidoCreateSerializer,
    ClienteSerializer,
)
from apps.usuarios.permissions import (
    EsAdminOVendedor, EsAdminOCajero, EsAdminODeposito,
    EsAdminVendedorODeposito, TodosLosRoles,
)
from . import nota_pedido_doc as nota_doc


# ─── Helpers WebSocket ────────────────────────────────────────────────────────

def _serializar_pedido(pedido, request=None):
    return NotaPedidoReadSerializer(pedido, context={'request': request}).data


def _emitir_evento(pedido, tipo_evento, request=None):
    """
    Envía el pedido actualizado a:
    - Room del pedido específico (pedido_<id>)
    - Rooms de roles involucrados (deposito, cajero, admin)
    """
    layer = get_channel_layer()
    if not layer:
        return

    data = {
        'tipo':   tipo_evento,
        'pedido': _serializar_pedido(pedido, request),
    }

    # Room del pedido
    async_to_sync(layer.group_send)(
        f'pedido_{pedido.id}',
        {'type': 'pedido_actualizado', 'data': data},
    )

    # Rooms por rol según el tipo de evento
    roles_destino = {
        # Depósito ya no participa del flujo de venta: el pedido nace
        # directo en "listo" (ver NotaPedidoCreateSerializer.create) y solo
        # caja tiene algo que hacer con él.
        'pedido_creado':      ['cajero', 'admin'],
        'pedido_preparando':  ['vendedor', 'cajero', 'admin'],
        'pedido_listo':       ['cajero', 'vendedor', 'admin'],
        'pedido_pagado':      ['vendedor', 'admin'],
        'pedido_cancelado':   ['deposito', 'cajero', 'admin'],
        'item_preparado':     ['cajero', 'vendedor', 'admin'],
    }

    for rol in roles_destino.get(tipo_evento, ['admin']):
        async_to_sync(layer.group_send)(
            f'rol_{rol}',
            {'type': 'pedido_estado_cambio', 'data': data},
        )


# ─── Vistas ───────────────────────────────────────────────────────────────────

class NotaPedidoListCreateView(views.APIView):
    """
    GET:  admin, vendedor, depósito, cajero (filtrado por rol)
    POST: solo vendedor y admin pueden crear pedidos
    """

    def get_permissions(self):
        if self.request.method == 'POST':
            return [EsAdminOVendedor()]
        return [TodosLosRoles()]

    def get(self, request):
        """
        Listado filtrado por rol:
        - vendedor:  sus propios pedidos
        - deposito:  pendientes y en preparación
        - cajero:    listos para cobrar
        - admin:     todos
        """
        qs = NotaPedido.objects.select_related(
            'vendedor', 'preparado_por'
        ).prefetch_related('items__variante__producto').order_by('-fecha_creacion')

        rol = request.user.rol

        if rol == 'vendedor':
            qs = qs.filter(vendedor=request.user)
        elif rol == 'deposito':
            qs = qs.filter(estado__in=[
                NotaPedido.ESTADO_PENDIENTE,
                NotaPedido.ESTADO_EN_PREPARACION,
            ])
        elif rol == 'cajero':
            qs = qs.filter(estado=NotaPedido.ESTADO_LISTO)

        # Filtros opcionales
        estado = request.query_params.get('estado')
        if estado:
            qs = qs.filter(estado=estado)

        serializer = NotaPedidoListSerializer(qs, many=True, context={'request': request})
        return Response({'results': serializer.data, 'count': qs.count()})

    def post(self, request):
        """Crear nueva nota de pedido (vendedor)."""
        serializer = NotaPedidoCreateSerializer(
            data=request.data,
            context={'request': request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        pedido = serializer.save()
        _emitir_evento(pedido, 'pedido_creado', request)
        # El pedido ya nace "listo" (sin paso de depósito) — avisar también
        # con este evento para que caja lo vea aparecer al instante.
        _emitir_evento(pedido, 'pedido_listo', request)

        return Response(
            NotaPedidoReadSerializer(pedido, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class NotaPedidoDetailView(views.APIView):
    """
    GET:   todos los roles
    PATCH: vendedor puede editar campos de cliente mientras está pendiente
    """

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH'):
            return [EsAdminOVendedor()]
        return [TodosLosRoles()]

    def _get_pedido(self, pk):
        return get_object_or_404(
            NotaPedido.objects.select_related('vendedor', 'preparado_por')
                              .prefetch_related(
                                  'items__variante__producto',
                                  'items__variante__acabado',
                                  'items__variante__imagenes',
                                  'items__variante__producto__imagenes',
                                  'items__variante__stock',
                              ),
            pk=pk
        )

    def get(self, request, pk):
        pedido = self._get_pedido(pk)
        return Response(NotaPedidoReadSerializer(pedido, context={'request': request}).data)

    def patch(self, request, pk):
        """
        Actualizar campos editables mientras el pedido está PENDIENTE.
        - Datos del cliente: admin, encargada de ventas o vendedor.
        - Monto (descuento / total_ajustado): SOLO admin o encargada de ventas.
        Una vez que el pedido pasa a 'en preparación' o más, nada es editable.
        """
        pedido = self._get_pedido(pk)

        if pedido.estado != NotaPedido.ESTADO_PENDIENTE:
            return Response(
                {'error': 'Solo se puede editar un pedido en estado Pendiente. '
                          'Un pedido en preparación o posterior no admite cambios.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        usuario = request.user
        puede_precio = (
            hasattr(usuario, 'puede_editar_precio_pedido')
            and usuario.puede_editar_precio_pedido()
        )

        # Campos de cliente: cualquier rol que pueda crear pedidos
        for campo in ['cliente_nombre', 'cliente_telefono', 'cliente_observaciones']:
            if campo in request.data:
                setattr(pedido, campo, request.data[campo])

        # Campos que afectan el monto: SOLO admin / encargada de ventas
        intento_monto = ('descuento' in request.data) or ('total_ajustado' in request.data)
        if intento_monto and not puede_precio:
            return Response(
                {'error': 'Solo la Encargada de Ventas o un administrador pueden '
                          'modificar el monto del pedido.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if puede_precio:
            if 'descuento' in request.data:
                pedido.descuento = request.data['descuento'] or 0

        # Recalcular el total base siempre
        pedido.subtotal = sum(i.subtotal for i in pedido.items.all())
        pedido.total    = pedido.subtotal - pedido.descuento

        # Monto final ajustado (precio negociado) — solo con permiso
        if puede_precio and 'total_ajustado' in request.data:
            ajustado = request.data['total_ajustado']
            if ajustado in (None, '', 'null'):
                pedido.total_ajustado = None      # quitar el ajuste, vuelve al total calculado
            else:
                from decimal import Decimal, InvalidOperation
                try:
                    valor = Decimal(str(ajustado))
                except (InvalidOperation, ValueError):
                    return Response({'error': 'Monto ajustado inválido.'},
                                    status=status.HTTP_400_BAD_REQUEST)
                if valor < 0:
                    return Response({'error': 'El monto no puede ser negativo.'},
                                    status=status.HTTP_400_BAD_REQUEST)
                pedido.total_ajustado = valor if valor != pedido.total else None

        pedido.save()

        _emitir_evento(pedido, 'pedido_actualizado', request)
        return Response(NotaPedidoReadSerializer(pedido, context={'request': request}).data)


class CambioEstadoView(views.APIView):
    """
    POST /ventas/pedidos/<id>/estado/
    Transiciones permitidas según rol:
      pendiente → en_preparacion  : depósito
      en_preparacion → listo      : depósito
      listo → pagado              : cajero (desde módulo de caja)
      cualquiera → cancelado      : admin o vendedor (solo si no está pagado)
    """
    permission_classes = [EsAdminVendedorODeposito]

    TRANSICIONES = {
        NotaPedido.ESTADO_PENDIENTE:       [NotaPedido.ESTADO_EN_PREPARACION, NotaPedido.ESTADO_CANCELADO],
        NotaPedido.ESTADO_EN_PREPARACION:  [NotaPedido.ESTADO_LISTO,          NotaPedido.ESTADO_CANCELADO],
        NotaPedido.ESTADO_LISTO:           [NotaPedido.ESTADO_CANCELADO],
    }

    EVENTO_POR_ESTADO = {
        NotaPedido.ESTADO_EN_PREPARACION: 'pedido_preparando',
        NotaPedido.ESTADO_LISTO:          'pedido_listo',
        NotaPedido.ESTADO_PAGADO:         'pedido_pagado',
        NotaPedido.ESTADO_CANCELADO:      'pedido_cancelado',
    }

    @transaction.atomic
    def post(self, request, pk):
        # select_for_update() bloquea la fila del pedido durante toda la
        # transición: dos requests casi simultáneos sobre el mismo pedido
        # (doble tap, reintento tras timeout) se serializan en vez de que
        # ambos lean el mismo estado "pre-cambio" y, por ejemplo, ambos
        # liberen la reserva de stock del pedido.
        pedido      = get_object_or_404(NotaPedido.objects.select_for_update(), pk=pk)
        nuevo_estado = request.data.get('estado')

        # El pago SIEMPRE se registra desde el módulo de Caja (RegistrarPagoView),
        # que crea el Pago, descuenta stock e imprime el comprobante. Permitir
        # "pagado" acá dejaría un pedido cerrado sin cobro, sin descuento de
        # stock y sin rastro en los reportes de caja.
        if nuevo_estado == NotaPedido.ESTADO_PAGADO:
            return Response(
                {'error': 'El pago se registra desde el módulo de Caja, no se puede '
                          'marcar un pedido como pagado directamente.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        permitidos = self.TRANSICIONES.get(pedido.estado, [])
        if nuevo_estado not in permitidos:
            return Response(
                {'error': f'Transición no permitida: {pedido.estado} → {nuevo_estado}. '
                          f'Permitidas: {permitidos}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validaciones extra
        if nuevo_estado == NotaPedido.ESTADO_LISTO:
            no_prep = pedido.items.filter(preparado=False).count()
            if no_prep > 0:
                return Response(
                    {'error': f'{no_prep} ítem(s) aún no están marcados como preparados.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        pedido.estado = nuevo_estado

        if nuevo_estado == NotaPedido.ESTADO_EN_PREPARACION:
            pedido.preparado_por = request.user

        if nuevo_estado == NotaPedido.ESTADO_LISTO:
            pedido.fecha_preparacion = timezone.now()
            if request.data.get('observaciones_deposito'):
                pedido.observaciones_deposito = request.data['observaciones_deposito']

        if nuevo_estado == NotaPedido.ESTADO_CANCELADO:
            # Liberar reservas de stock antes de guardar el estado
            pedido.liberar_stock(usuario=request.user)

        pedido.save()

        evento = self.EVENTO_POR_ESTADO.get(nuevo_estado, 'pedido_actualizado')
        _emitir_evento(pedido, evento, request)

        return Response(NotaPedidoReadSerializer(pedido, context={'request': request}).data)


class PrepararItemView(views.APIView):
    """
    POST /ventas/pedidos/<id>/items/<item_id>/preparar/
    Solo el personal de depósito y el admin pueden marcar ítems como preparados.
    """
    permission_classes = [EsAdminODeposito]

    def post(self, request, pk, item_id):
        pedido = get_object_or_404(NotaPedido, pk=pk)
        item   = get_object_or_404(ItemPedido, pk=item_id, pedido=pedido)

        if pedido.estado not in [NotaPedido.ESTADO_PENDIENTE, NotaPedido.ESTADO_EN_PREPARACION]:
            return Response(
                {'error': 'Solo se pueden preparar ítems de pedidos pendientes o en preparación.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        item.preparado         = request.data.get('preparado', True)
        item.cantidad_preparada = request.data.get('cantidad_preparada', item.cantidad)
        item.save(update_fields=['preparado', 'cantidad_preparada'])

        # Si todos están preparados, emitir aviso
        todos = not pedido.items.filter(preparado=False).exists()
        _emitir_evento(pedido, 'item_preparado', request)

        return Response({
            'item_id':    item.id,
            'preparado':  item.preparado,
            'todos_listos': todos,
        })


class CancelarItemView(views.APIView):
    """
    DELETE /ventas/pedidos/<id>/items/<item_id>/
    Solo vendedor y admin pueden eliminar ítems (solo en estado pendiente).
    """
    permission_classes = [EsAdminOVendedor]

    def delete(self, request, pk, item_id):
        pedido = get_object_or_404(NotaPedido, pk=pk)

        if pedido.estado != NotaPedido.ESTADO_PENDIENTE:
            return Response(
                {'error': 'Solo se pueden eliminar ítems de pedidos pendientes.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        item = get_object_or_404(ItemPedido, pk=item_id, pedido=pedido)
        item.delete()

        # Recalcular totales
        pedido.subtotal = sum(i.subtotal for i in pedido.items.all())
        pedido.total    = pedido.subtotal - pedido.descuento
        pedido.save(update_fields=['subtotal', 'total'])

        _emitir_evento(pedido, 'pedido_actualizado', request)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ════════════════════════════════════════════════════════
# PADRÓN DE CLIENTES (buscador por RUC + CRUD)
# ════════════════════════════════════════════════════════

class ClienteListCreateView(views.APIView):
    """
    GET  /ventas/clientes/?buscar=texto   → busca por razón social o RUC
    POST /ventas/clientes/                → crea un cliente
    """
    def get_permissions(self):
        return [EsAdminOVendedor()] if self.request.method == 'POST' else [TodosLosRoles()]

    def get(self, request):
        qs = Cliente.objects.filter(activo=True)
        buscar = request.query_params.get('buscar', '').strip()
        if buscar:
            from django.db.models import Q
            qs = qs.filter(Q(razon_social__icontains=buscar) | Q(ruc__icontains=buscar))
        # Materializar como lista (máximo 50) y contar sobre la lista, NO sobre
        # el queryset ya cortado (un slice no admite .count()).
        clientes = list(qs[:50])
        data = ClienteSerializer(clientes, many=True).data
        return Response({'results': data, 'count': len(data)})

    def post(self, request):
        s = ClienteSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(ClienteSerializer(s.save()).data, status=status.HTTP_201_CREATED)


class ClienteDetailView(views.APIView):
    permission_classes = [EsAdminOVendedor]

    def get(self, request, pk):
        return Response(ClienteSerializer(get_object_or_404(Cliente, pk=pk)).data)

    def patch(self, request, pk):
        cliente = get_object_or_404(Cliente, pk=pk)
        s = ClienteSerializer(cliente, data=request.data, partial=True)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(ClienteSerializer(s.save()).data)

    def delete(self, request, pk):
        cliente = get_object_or_404(Cliente, pk=pk)
        cliente.activo = False
        cliente.save(update_fields=['activo'])
        return Response({'detail': 'Cliente desactivado.'}, status=status.HTTP_200_OK)


# ════════════════════════════════════════════════════════
# Nota para el cliente, como documento descargable (PDF / Excel)
# ════════════════════════════════════════════════════════
class NotaPedidoDocumentoView(views.APIView):
    """
    GET /api/ventas/pedidos/<pk>/nota/?formato=pdf|xlsx&tipo=presupuesto|pedido

    Devuelve el pedido diagramado como la nota que el negocio ya usaba.
    Depósito queda afuera: el documento lleva precios y totales, y ese rol
    no ve montos en ningún lado del sistema.
    """
    permission_classes = [EsAdminOVendedor | EsAdminOCajero]

    def get(self, request, pk):
        pedido = get_object_or_404(
            NotaPedido.objects.select_related('vendedor', 'cliente')
                              .prefetch_related('items__variante__producto',
                                                'items__variante__acabado'),
            pk=pk,
        )
        formato = request.query_params.get('formato', 'pdf').lower()
        formato = 'xlsx' if formato in ('xlsx', 'excel') else 'pdf'
        tipo = request.query_params.get('tipo', nota_doc.TIPO_DEFECTO).lower()
        datos = nota_doc.datos_desde_pedido(pedido, tipo=tipo)
        return nota_doc.responder(datos, formato)
