"""
App: ventas — Modelos
Ciclo completo de stock integrado en el modelo:

  CREAR pedido     → reserva stock de cada ítem (cantidad_reservada ++)
  CANCELAR pedido  → libera la reserva (cantidad_reservada --)
  PAGAR pedido     → la caja llama a descontar_stock() (cantidad --)
                     que también libera la reserva residual

Esto evita sobreventa: dos vendedores no pueden prometer el mismo stock.
"""
from decimal import Decimal
from django.db import models, transaction
from django.core.validators import MinValueValidator
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class Cliente(models.Model):
    """
    Padrón de clientes con RUC. Permite buscar y autocompletar los datos
    fiscales al armar una nota de pedido o facturar, sin reescribirlos.
    """
    TIPO_FISICA  = 'fisica'
    TIPO_JURIDICA = 'juridica'
    TIPOS = [
        (TIPO_FISICA,   'Persona física'),
        (TIPO_JURIDICA, 'Persona jurídica / Empresa'),
    ]
    CONDICION_CONTADO = 'contado'
    CONDICION_CREDITO = 'credito'
    CONDICIONES = [
        (CONDICION_CONTADO, 'Contado'),
        (CONDICION_CREDITO, 'Crédito'),
    ]

    razon_social   = models.CharField(max_length=180, help_text='Nombre o razón social')
    ruc            = models.CharField(max_length=30, blank=True, db_index=True,
                        help_text='RUC o CI. Ej: 80012345-6')
    tipo           = models.CharField(max_length=12, choices=TIPOS, default=TIPO_FISICA)
    telefono       = models.CharField(max_length=40, blank=True)
    email          = models.EmailField(blank=True)
    direccion      = models.CharField(max_length=250, blank=True)
    condicion_venta = models.CharField(max_length=12, choices=CONDICIONES,
                        default=CONDICION_CONTADO,
                        help_text='Condición de venta habitual de este cliente')
    permite_ajuste_precio = models.BooleanField(default=False,
                        help_text='Si es mayorista/constructora con precios negociables')
    activo         = models.BooleanField(default=True)
    notas          = models.TextField(blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table            = 'clientes'
        ordering            = ['razon_social']
        verbose_name        = 'Cliente'
        verbose_name_plural = 'Clientes'
        indexes = [
            models.Index(fields=['ruc'],          name='idx_cliente_ruc'),
            models.Index(fields=['razon_social'], name='idx_cliente_razon'),
        ]

    def __str__(self):
        return f'{self.razon_social}{" — " + self.ruc if self.ruc else ""}'


class NotaPedido(models.Model):
    ESTADO_PENDIENTE      = 'pendiente'
    ESTADO_EN_PREPARACION = 'en_preparacion'
    ESTADO_LISTO          = 'listo'
    ESTADO_PAGADO         = 'pagado'
    ESTADO_CANCELADO      = 'cancelado'

    ESTADOS = [
        (ESTADO_PENDIENTE,      'Pendiente'),
        (ESTADO_EN_PREPARACION, 'En preparación'),
        (ESTADO_LISTO,          'Listo para cobrar'),
        (ESTADO_PAGADO,         'Pagado — cerrado'),
        (ESTADO_CANCELADO,      'Cancelado'),
    ]

    numero  = models.CharField(max_length=20, unique=True)
    estado  = models.CharField(max_length=20, choices=ESTADOS, default=ESTADO_PENDIENTE, db_index=True)

    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT, related_name='pedidos_creados'
    )
    cliente = models.ForeignKey(
        'Cliente', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pedidos', help_text='Cliente del padrón (opcional)'
    )
    cliente_nombre        = models.CharField(max_length=150, blank=True)
    cliente_ruc           = models.CharField(max_length=30,  blank=True)
    cliente_telefono      = models.CharField(max_length=30,  blank=True)
    cliente_observaciones = models.TextField(blank=True)

    subtotal  = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    descuento = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total     = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # Monto final ajustado manualmente por el vendedor (precio negociado).
    # Si es null, vale el `total` calculado. Si tiene valor, ese es el monto a cobrar.
    total_ajustado = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text='Monto final negociado; reemplaza al total calculado si está definido'
    )

    observaciones_deposito = models.TextField(blank=True)
    preparado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pedidos_preparados'
    )
    fecha_preparacion = models.DateTimeField(null=True, blank=True)
    fecha_creacion    = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table            = 'notas_pedido'
        ordering            = ['-fecha_creacion']
        verbose_name        = 'Nota de pedido'
        verbose_name_plural = 'Notas de pedido'
        indexes = [
            models.Index(fields=['estado', '-fecha_creacion'], name='idx_pedido_estado_fecha'),
            models.Index(fields=['vendedor', 'estado'],        name='idx_pedido_vendedor'),
        ]

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            hoy    = timezone.now()
            ultimo = NotaPedido.objects.filter(
                fecha_creacion__year=hoy.year,
                fecha_creacion__month=hoy.month,
            ).count()
            self.numero = f'NP-{hoy.strftime("%Y%m")}-{str(ultimo + 1).zfill(4)}'
        super().save(*args, **kwargs)

    def recalcular_totales(self):
        """Recalcula subtotal y total desde los ítems. Llama save() si hubo cambio."""
        nuevo_subtotal = sum(i.subtotal for i in self.items.all())
        nuevo_total    = nuevo_subtotal - self.descuento
        if self.subtotal != nuevo_subtotal or self.total != nuevo_total:
            self.subtotal = nuevo_subtotal
            self.total    = nuevo_total
            self.save(update_fields=['subtotal', 'total'])

    def __str__(self):
        return f'{self.numero} — {self.get_estado_display()} — {self.cliente_nombre or "Sin nombre"}'

    @property
    def monto_a_cobrar(self):
        """
        Monto final que debe cobrar la caja: el ajustado si el vendedor lo
        definió, o el total calculado en caso contrario.
        """
        if self.total_ajustado is not None:
            return self.total_ajustado
        return self.total

    @property
    def puede_preparar(self):
        return self.estado == self.ESTADO_PENDIENTE

    @property
    def puede_cobrar(self):
        return self.estado == self.ESTADO_LISTO

    # ── Operaciones de stock ──────────────────────────────────

    @transaction.atomic
    def reservar_stock(self, usuario):
        """
        Al crear el pedido: reserva la cantidad de cada ítem en stock.
        Si algún ítem no tiene stock suficiente, lanza StockInsuficienteError
        y revierte toda la reserva (transacción atómica).
        """
        from apps.inventario.models import Stock, MovimientoStock

        errores = []
        reservados = []

        for item in self.items.select_related('variante').all():
            try:
                stock = Stock.objects.select_for_update().get(variante=item.variante)
                stock.registrar_movimiento(
                    tipo            = MovimientoStock.TIPO_RESERVA,
                    cantidad        = item.cantidad,
                    usuario         = usuario,
                    referencia_tipo = 'pedido',
                    referencia_id   = self.id,
                    observaciones   = f'Reserva — pedido {self.numero}',
                )
                reservados.append(item.variante.sku)
            except Exception as e:
                errores.append({'sku': item.variante.sku, 'error': str(e)})

        if errores:
            raise StockInsuficienteError(errores)

        return reservados

    @transaction.atomic
    def liberar_stock(self, usuario):
        """
        Al cancelar: libera todas las reservas del pedido.
        Seguro llamar aunque no haya reservas previas.
        """
        from apps.inventario.models import Stock, MovimientoStock

        for item in self.items.select_related('variante').all():
            try:
                stock = Stock.objects.select_for_update().get(variante=item.variante)
                if stock.cantidad_reservada > 0:
                    liberar = min(item.cantidad, stock.cantidad_reservada)
                    stock.registrar_movimiento(
                        tipo            = MovimientoStock.TIPO_LIBERACION,
                        cantidad        = liberar,
                        usuario         = usuario,
                        referencia_tipo = 'pedido',
                        referencia_id   = self.id,
                        observaciones   = f'Liberación — pedido {self.numero} cancelado',
                    )
            except Exception as e:
                logger.warning(f'Error liberando stock de {item.variante.sku}: {e}')

    @transaction.atomic
    def descontar_stock(self, usuario, numero_ticket=''):
        """
        Al confirmar el pago: descuenta el stock real y libera la reserva.
        Retorna lista de errores (vacía si todo salió bien).
        """
        from apps.inventario.models import Stock, MovimientoStock

        errores = []

        for item in self.items.select_related('variante').all():
            try:
                stock = Stock.objects.select_for_update().get(variante=item.variante)

                # Liberar la reserva de este ítem
                if stock.cantidad_reservada > 0:
                    liberar = min(item.cantidad, stock.cantidad_reservada)
                    stock.cantidad_reservada = max(stock.cantidad_reservada - liberar, 0)
                    stock.save(update_fields=['cantidad_reservada'])

                # Descontar del stock físico
                if item.cantidad > stock.cantidad:
                    # Stock insuficiente al momento de pagar (caso raro pero posible)
                    logger.error(
                        f'Stock insuficiente al pagar: {item.variante.sku} '
                        f'tiene {stock.cantidad}, se necesitan {item.cantidad}'
                    )
                    errores.append({
                        'sku':       item.variante.sku,
                        'error':     f'Stock insuficiente: disponible {stock.cantidad}, requerido {item.cantidad}',
                        'resuelto':  False,
                    })
                    # Descontar lo que haya (no bloquear la venta)
                    cantidad_real = stock.cantidad
                else:
                    cantidad_real = item.cantidad

                if cantidad_real > 0:
                    MovimientoStock.objects.create(
                        variante          = item.variante,
                        tipo              = MovimientoStock.TIPO_SALIDA,
                        cantidad          = cantidad_real,
                        cantidad_anterior = stock.cantidad,
                        cantidad_posterior= stock.cantidad - cantidad_real,
                        referencia_tipo   = 'venta',
                        referencia_id     = self.id,
                        usuario           = usuario,
                        observaciones     = f'Venta — {numero_ticket} — pedido {self.numero}',
                    )
                    stock.cantidad = stock.cantidad - cantidad_real
                    stock.save(update_fields=['cantidad'])

                    # Emitir alerta si quedó en stock crítico
                    stock.refresh_from_db()
                    if stock.en_stock_critico or stock.sin_stock:
                        _emitir_alerta_stock(stock)

            except Exception as e:
                logger.exception(f'Error descontando stock de {item.variante.sku}: {e}')
                errores.append({
                    'sku':      item.variante.sku,
                    'error':    str(e),
                    'resuelto': False,
                })

        return errores


class StockInsuficienteError(Exception):
    """Lanzada cuando no hay stock suficiente para reservar un pedido."""
    def __init__(self, errores: list):
        self.errores = errores
        super().__init__(f'Stock insuficiente para {len(errores)} producto(s)')


class ItemPedido(models.Model):
    pedido    = models.ForeignKey(NotaPedido, on_delete=models.CASCADE, related_name='items')
    variante  = models.ForeignKey(
        'productos.Variante', on_delete=models.PROTECT, related_name='items_pedido'
    )
    cantidad        = models.DecimalField(max_digits=10, decimal_places=4,
                          validators=[MinValueValidator(Decimal('0.0001'))])
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    descuento_item  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    observaciones   = models.CharField(max_length=200, blank=True)
    preparado         = models.BooleanField(default=False)
    cantidad_preparada = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    class Meta:
        db_table            = 'items_pedido'
        verbose_name        = 'Ítem de pedido'
        verbose_name_plural = 'Ítems de pedido'

    @property
    def subtotal(self):
        return (self.precio_unitario * self.cantidad) - self.descuento_item

    def __str__(self):
        return f'{self.variante} × {self.cantidad} = {self.subtotal}'


# ─── Helper WebSocket para alertas de stock ────────────────────────────────────

def _emitir_alerta_stock(stock):
    """Notifica al admin/depósito cuando el stock baja del mínimo."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if not layer:
            return

        data = {
            'tipo':    'alerta_stock',
            'sku':     stock.variante.sku,
            'nombre':  stock.variante.producto.nombre,
            'estado':  stock.estado,
            'disponible': float(stock.cantidad_disponible),
            'minimo':  float(stock.stock_minimo),
        }
        for room in ['rol_admin', 'rol_deposito']:
            async_to_sync(layer.group_send)(
                room, {'type': 'pedido_estado_cambio', 'data': data}
            )
    except Exception:
        pass
