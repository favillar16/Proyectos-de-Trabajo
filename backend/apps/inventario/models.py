"""
App: inventario
Control de stock por variante y registro de movimientos.

Mejoras v2:
- Señal post_save: crea Stock automáticamente al crear una Variante
- Método Stock.registrar_movimiento() para centralizar toda modificación de stock
- Índices en MovimientoStock para consultas de historial rápido
- Stock.en_alerta distingue entre crítico y sin_stock
- Validación: cantidad_reservada no puede superar cantidad real
"""
from django.db import models, transaction
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


class Stock(models.Model):
    """
    Stock actual por variante. Relación OneToOne con Variante.
    Se crea automáticamente al crear una Variante (ver señal al final).
    """
    variante = models.OneToOneField(
        'productos.Variante',
        on_delete=models.CASCADE,
        related_name='stock'
    )

    # ── Cantidades ────────────────────────────────────────────
    cantidad = models.DecimalField(
        max_digits=10, decimal_places=4,
        default=0,
        validators=[MinValueValidator(0)],
        help_text='Cantidad física real en el depósito'
    )
    cantidad_reservada = models.DecimalField(
        max_digits=10, decimal_places=4,
        default=0,
        validators=[MinValueValidator(0)],
        help_text='Reservada por notas de pedido pendientes de cobro'
    )
    stock_minimo = models.DecimalField(
        max_digits=10, decimal_places=4,
        default=0,
        validators=[MinValueValidator(0)],
        help_text='Umbral de alerta de stock bajo. 0 = sin alerta.'
    )

    # ── Ubicación física en depósito ──────────────────────────
    ubicacion = models.CharField(
        max_length=100, blank=True,
        help_text='Ej: Pasillo A — Estante 3, Depósito fondo, Exhibición piso'
    )

    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table            = 'stock'
        verbose_name        = 'Stock'
        verbose_name_plural = 'Stock'

    def __str__(self):
        return f'{self.variante.sku} — {self.cantidad_disponible} disponible'

    def clean(self):
        if self.cantidad_reservada > self.cantidad:
            raise ValidationError({
                'cantidad_reservada': (
                    f'La cantidad reservada ({self.cantidad_reservada}) no puede '
                    f'superar la cantidad real ({self.cantidad}).'
                )
            })

    # ── Properties ───────────────────────────────────────────

    @property
    def cantidad_disponible(self):
        """Stock real menos lo reservado por pedidos pendientes."""
        return max(self.cantidad - self.cantidad_reservada, 0)

    @property
    def sin_stock(self):
        return self.cantidad_disponible <= 0

    @property
    def en_stock_critico(self):
        """True cuando está bajo el mínimo pero aún tiene algo."""
        return not self.sin_stock and self.cantidad_disponible <= self.stock_minimo

    @property
    def estado(self):
        """Texto de estado para mostrar en UI."""
        if self.sin_stock:
            return 'sin_stock'
        if self.en_stock_critico:
            return 'critico'
        return 'disponible'

    # ── Conversión cajas ↔ unidad de venta (m²) ──────────────
    @property
    def m2_por_caja(self):
        """M² que cubre una caja de esta variante, si aplica."""
        try:
            return self.variante.m2_por_caja_calculado
        except Exception:
            return None

    @property
    def vende_por_m2(self):
        """True si el producto se vende en m² y tiene rendimiento por caja."""
        try:
            return (self.variante.producto.unidad_venta == 'm2'
                    and bool(self.m2_por_caja))
        except Exception:
            return False

    @property
    def cajas_completas(self):
        """Cuántas cajas completas quedan disponibles. None si no aplica."""
        m2c = self.m2_por_caja
        if not m2c or m2c <= 0:
            return None
        # Redondear el cociente a 4 decimales antes de truncar para evitar
        # errores de punto flotante (ej: 25.20 / 2.52 = 9.9999… → debe dar 10)
        cociente = round(float(self.cantidad_disponible) / float(m2c), 4)
        return int(cociente)

    @property
    def m2_sueltos(self):
        """M² que sobran fuera de cajas completas. None si no aplica."""
        m2c = self.m2_por_caja
        if not m2c or m2c <= 0:
            return None
        sueltos = round(float(self.cantidad_disponible) - self.cajas_completas * float(m2c), 2)
        # Evitar -0.0 o residuos mínimos por flotante
        return max(sueltos, 0.0)

    @property
    def detalle_cajas(self):
        """
        Texto legible del stock en cajas + m². Ej: '4 cajas + 1.25 m²'.
        Si no aplica conversión, devuelve solo la cantidad.
        """
        if not self.vende_por_m2:
            return None
        cajas = self.cajas_completas
        sueltos = self.m2_sueltos
        partes = []
        if cajas:
            partes.append(f'{cajas} caja{"s" if cajas != 1 else ""}')
        if sueltos and sueltos > 0:
            partes.append(f'{sueltos:.2f} m²')
        return ' + '.join(partes) if partes else '0 cajas'

    # ── Método central de modificación ───────────────────────

    @transaction.atomic
    def registrar_movimiento(self, tipo, cantidad, usuario, referencia_tipo='', referencia_id=None, observaciones=''):
        """
        Modifica el stock y genera el movimiento en una sola transacción.
        Usar siempre este método en lugar de modificar 'cantidad' directamente.

        Tipos válidos: entrada, salida, ajuste, reserva, liberacion, devolucion
        """
        if cantidad <= 0:
            raise ValidationError('La cantidad del movimiento debe ser mayor a 0.')

        cantidad_anterior = self.cantidad

        if tipo == MovimientoStock.TIPO_ENTRADA:
            self.cantidad += cantidad

        elif tipo == MovimientoStock.TIPO_SALIDA:
            if cantidad > self.cantidad_disponible:
                raise ValidationError(
                    f'Stock insuficiente. Disponible: {self.cantidad_disponible}, '
                    f'solicitado: {cantidad}.'
                )
            self.cantidad -= cantidad

        elif tipo == MovimientoStock.TIPO_RESERVA:
            if cantidad > self.cantidad_disponible:
                raise ValidationError(
                    f'No se puede reservar {cantidad}. Disponible: {self.cantidad_disponible}.'
                )
            self.cantidad_reservada += cantidad

        elif tipo == MovimientoStock.TIPO_LIBERACION:
            self.cantidad_reservada = max(self.cantidad_reservada - cantidad, 0)

        elif tipo == MovimientoStock.TIPO_AJUSTE:
            # Ajuste fija el stock en el valor exacto indicado
            self.cantidad = cantidad

        elif tipo == MovimientoStock.TIPO_DEVOLUCION:
            self.cantidad += cantidad
            self.cantidad_reservada = max(self.cantidad_reservada - cantidad, 0)

        else:
            raise ValidationError(f'Tipo de movimiento desconocido: {tipo}')

        self.save()

        MovimientoStock.objects.create(
            variante          = self.variante,
            tipo              = tipo,
            cantidad          = cantidad,
            cantidad_anterior = cantidad_anterior,
            cantidad_posterior= self.cantidad,
            referencia_tipo   = referencia_tipo,
            referencia_id     = referencia_id,
            usuario           = usuario,
            observaciones     = observaciones,
        )

        return self


class MovimientoStock(models.Model):
    """
    Registro inmutable de cada cambio de stock.
    Nunca se edita ni borra — es el historial de auditoría.
    """
    TIPO_ENTRADA    = 'entrada'
    TIPO_SALIDA     = 'salida'
    TIPO_AJUSTE     = 'ajuste'
    TIPO_RESERVA    = 'reserva'
    TIPO_LIBERACION = 'liberacion'
    TIPO_DEVOLUCION = 'devolucion'

    TIPOS = [
        (TIPO_ENTRADA,    'Entrada de mercadería'),
        (TIPO_SALIDA,     'Salida por venta'),
        (TIPO_AJUSTE,     'Ajuste de inventario'),
        (TIPO_RESERVA,    'Reserva por pedido'),
        (TIPO_LIBERACION, 'Liberación de reserva'),
        (TIPO_DEVOLUCION, 'Devolución'),
    ]

    variante = models.ForeignKey(
        'productos.Variante',
        on_delete=models.PROTECT,
        related_name='movimientos',
        db_index=True
    )
    tipo              = models.CharField(max_length=20, choices=TIPOS, db_index=True)
    cantidad          = models.DecimalField(max_digits=10, decimal_places=4)
    cantidad_anterior = models.DecimalField(max_digits=10, decimal_places=4)
    cantidad_posterior= models.DecimalField(max_digits=10, decimal_places=4)

    # ── Referencia al documento origen ───────────────────────
    referencia_tipo = models.CharField(
        max_length=30, blank=True, db_index=True,
        help_text='venta | pedido | ajuste | devolucion'
    )
    referencia_id = models.PositiveBigIntegerField(
        null=True, blank=True,
        help_text='ID del documento origen (NotaPedido.id, Pago.id, etc.)'
    )

    usuario       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='movimientos_stock'
    )
    observaciones = models.TextField(blank=True)
    fecha         = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table            = 'movimientos_stock'
        ordering            = ['-fecha']
        verbose_name        = 'Movimiento de stock'
        verbose_name_plural = 'Movimientos de stock'
        indexes = [
            models.Index(fields=['variante', '-fecha'],          name='idx_mov_variante_fecha'),
            models.Index(fields=['tipo', '-fecha'],              name='idx_mov_tipo_fecha'),
            models.Index(fields=['referencia_tipo', 'referencia_id'], name='idx_mov_referencia'),
            models.Index(fields=['usuario', '-fecha'],           name='idx_mov_usuario_fecha'),
        ]

    def __str__(self):
        fecha_fmt = self.fecha.strftime('%d/%m/%Y %H:%M') if self.fecha else '—'
        return (
            f'{self.get_tipo_display()} — '
            f'{self.variante.sku} — '
            f'{self.cantidad:+.4f} → {self.cantidad_posterior:.4f} '
            f'({fecha_fmt})'
        )


# ─── Señal: crear Stock automáticamente al crear una Variante ────────────────

@receiver(post_save, sender='productos.Variante')
def crear_stock_para_variante(sender, instance, created, **kwargs):
    """
    Cuando se crea una nueva Variante, se genera automáticamente
    su registro de Stock con cantidad 0. Evita tener que crearlo a mano.
    """
    if created:
        Stock.objects.get_or_create(variante=instance)
