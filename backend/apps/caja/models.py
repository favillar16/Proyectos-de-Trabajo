"""
App: caja
Sesiones de caja, pagos y cierre
"""
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator


class SesionCaja(models.Model):
    """Apertura y cierre de caja por turno"""
    ESTADO_ABIERTA = 'abierta'
    ESTADO_CERRADA = 'cerrada'

    cajero = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='sesiones_caja'
    )
    estado = models.CharField(
        max_length=10,
        choices=[(ESTADO_ABIERTA, 'Abierta'), (ESTADO_CERRADA, 'Cerrada')],
        default=ESTADO_ABIERTA
    )
    monto_apertura = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    monto_cierre = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    observaciones_cierre = models.TextField(blank=True)

    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sesiones_caja'
        ordering = ['-fecha_apertura']
        verbose_name = 'Sesión de caja'
        verbose_name_plural = 'Sesiones de caja'
        constraints = [
            models.UniqueConstraint(
                fields=['cajero'],
                condition=models.Q(estado='abierta'),
                name='unique_sesion_abierta_por_cajero',
            ),
        ]

    def __str__(self):
        return f'Caja {self.cajero} — {self.fecha_apertura.strftime("%d/%m/%Y %H:%M")} ({self.estado})'

    @property
    def total_ventas(self):
        return self.pagos.filter(
            estado=Pago.ESTADO_CONFIRMADO
        ).aggregate(
            total=models.Sum('monto')
        )['total'] or 0


class Pago(models.Model):
    """Pago asociado a una nota de pedido"""
    MEDIO_EFECTIVO = 'efectivo'
    MEDIO_TARJETA_DEBITO = 'debito'
    MEDIO_TARJETA_CREDITO = 'credito'
    MEDIO_TRANSFERENCIA = 'transferencia'

    MEDIOS = [
        (MEDIO_EFECTIVO, 'Efectivo'),
        (MEDIO_TARJETA_DEBITO, 'Tarjeta de débito'),
        (MEDIO_TARJETA_CREDITO, 'Tarjeta de crédito'),
        (MEDIO_TRANSFERENCIA, 'Transferencia bancaria'),
    ]

    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_CONFIRMADO = 'confirmado'
    ESTADO_ANULADO = 'anulado'

    ESTADOS = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_CONFIRMADO, 'Confirmado'),
        (ESTADO_ANULADO, 'Anulado'),
    ]

    pedido = models.ForeignKey(
        'ventas.NotaPedido',
        on_delete=models.PROTECT,
        related_name='pagos'
    )
    sesion_caja = models.ForeignKey(
        SesionCaja,
        on_delete=models.PROTECT,
        related_name='pagos'
    )
    cajero = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='pagos_procesados'
    )

    medio_pago = models.CharField(max_length=20, choices=MEDIOS)
    monto = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    monto_recibido = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    vuelto = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    descuento_porcentaje = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text='Descuento porcentual aplicado en caja (0-100).'
    )
    monto_sin_descuento = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text='Monto del pedido antes de aplicar el descuento de caja.'
    )

    estado = models.CharField(max_length=15, choices=ESTADOS, default=ESTADO_PENDIENTE)
    numero_ticket = models.CharField(max_length=20, blank=True)
    referencia_externa = models.CharField(
        max_length=100, blank=True,
        help_text='Nro de autorización de tarjeta, nro de transferencia, etc.'
    )

    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'pagos'
        ordering = ['-fecha']
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'

    def save(self, *args, **kwargs):
        if not self.numero_ticket:
            from django.utils import timezone
            ts = timezone.now().strftime('%Y%m%d%H%M%S')
            self.numero_ticket = f'T-{ts}-{self.pedido_id}'
        if self.monto_recibido and self.medio_pago == self.MEDIO_EFECTIVO:
            self.vuelto = max(0, self.monto_recibido - self.monto)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Pago {self.numero_ticket} — {self.get_medio_pago_display()} — {self.monto}'
