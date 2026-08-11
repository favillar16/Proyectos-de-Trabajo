"""
App: costos — Gastos operativos, proveedores, salarios y pedidos a proveedores.
"""
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal
from datetime import date


class CategoriaGasto(models.Model):
    TIPO_PROVEEDOR = 'proveedor'
    TIPO_SALARIO   = 'salario'
    TIPO_SERVICIO  = 'servicio'
    TIPO_OTRO      = 'otro'
    TIPOS = [
        (TIPO_PROVEEDOR, 'Pago a proveedor'),
        (TIPO_SALARIO,   'Salario de empleado'),
        (TIPO_SERVICIO,  'Servicio / Utility'),
        (TIPO_OTRO,      'Otro gasto'),
    ]
    nombre      = models.CharField(max_length=100)
    tipo        = models.CharField(max_length=20, choices=TIPOS, default=TIPO_OTRO)
    descripcion = models.CharField(max_length=250, blank=True)
    activa      = models.BooleanField(default=True)
    orden       = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table='categorias_gasto'; ordering=['orden','nombre']
        verbose_name='Categoría de gasto'; verbose_name_plural='Categorías de gasto'

    def __str__(self): return f'{self.nombre} ({self.get_tipo_display()})'


class Proveedor(models.Model):
    """Proveedores del negocio para registro de pagos y pedidos."""
    nombre        = models.CharField(max_length=150)
    ruc           = models.CharField(max_length=30, blank=True)
    contacto      = models.CharField(max_length=120, blank=True, help_text='Persona de contacto')
    telefono      = models.CharField(max_length=40, blank=True)
    email         = models.EmailField(blank=True)
    direccion     = models.CharField(max_length=250, blank=True)
    rubro         = models.CharField(max_length=120, blank=True, help_text='Qué provee (ej: porcelanatos)')
    activo        = models.BooleanField(default=True)
    notas         = models.TextField(blank=True)
    fecha_creacion= models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table='proveedores'; ordering=['nombre']
        verbose_name='Proveedor'; verbose_name_plural='Proveedores'

    def __str__(self): return self.nombre


class Empleado(models.Model):
    nombre_completo = models.CharField(max_length=150)
    cargo           = models.CharField(max_length=100, blank=True)
    salario_base    = models.DecimalField(max_digits=12, decimal_places=2,
                          validators=[MinValueValidator(Decimal('0'))],
                          help_text='Salario mensual base en Gs.')
    activo          = models.BooleanField(default=True)
    fecha_ingreso   = models.DateField(null=True, blank=True)
    usuario         = models.OneToOneField(settings.AUTH_USER_MODEL,
                          on_delete=models.SET_NULL, null=True, blank=True,
                          related_name='empleado')
    notas           = models.TextField(blank=True)
    fecha_creacion  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table='empleados'; ordering=['nombre_completo']
        verbose_name='Empleado'; verbose_name_plural='Empleados'

    def __str__(self): return f'{self.nombre_completo} — {self.cargo or "Sin cargo"}'


class GastoOperativo(models.Model):
    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_PAGADO    = 'pagado'
    ESTADO_CANCELADO = 'cancelado'
    ESTADOS = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_PAGADO,    'Pagado'),
        (ESTADO_CANCELADO, 'Cancelado'),
    ]

    # Métodos de pago
    PAGO_EFECTIVO      = 'efectivo'
    PAGO_TRANSFERENCIA = 'transferencia'
    PAGO_CREDITO       = 'credito'
    PAGO_CHEQUE        = 'cheque'
    METODOS_PAGO = [
        (PAGO_EFECTIVO,      'Efectivo'),
        (PAGO_TRANSFERENCIA, 'Transferencia'),
        (PAGO_CREDITO,       'Crédito'),
        (PAGO_CHEQUE,        'Cheque'),
    ]

    MESES = [(i, n) for i, n in enumerate([
        'Enero','Febrero','Marzo','Abril','Mayo','Junio',
        'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre',
    ], 1)]

    categoria       = models.ForeignKey(CategoriaGasto, on_delete=models.PROTECT, related_name='gastos')
    proveedor       = models.ForeignKey(Proveedor, on_delete=models.SET_NULL,
                          null=True, blank=True, related_name='pagos')
    empleado        = models.ForeignKey(Empleado, on_delete=models.SET_NULL,
                          null=True, blank=True, related_name='pagos_salario')
    descripcion     = models.CharField(max_length=250)
    monto           = models.DecimalField(max_digits=14, decimal_places=2,
                          validators=[MinValueValidator(Decimal('0.01'))])
    anio            = models.PositiveSmallIntegerField()
    mes             = models.PositiveSmallIntegerField(choices=MESES)
    fecha_pago      = models.DateField(null=True, blank=True)
    estado          = models.CharField(max_length=15, choices=ESTADOS, default=ESTADO_PENDIENTE)

    # Método de pago (relevante sobre todo para pagos a proveedor)
    metodo_pago     = models.CharField(max_length=20, choices=METODOS_PAGO,
                          blank=True, default='')

    # Datos del cheque (solo si metodo_pago == cheque)
    cheque_numero       = models.CharField(max_length=50, blank=True)
    cheque_banco        = models.CharField(max_length=80, blank=True)
    cheque_fecha_cobro  = models.DateField(null=True, blank=True,
                            help_text='Fecha en que el cheque puede cobrarse (plazo)')

    registrado_por  = models.ForeignKey(settings.AUTH_USER_MODEL,
                          on_delete=models.PROTECT, related_name='gastos_registrados')
    comprobante     = models.CharField(max_length=100, blank=True)
    notas           = models.TextField(blank=True)
    fecha_creacion  = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table='gastos_operativos'; ordering=['-anio','-mes','-fecha_creacion']
        verbose_name='Gasto operativo'; verbose_name_plural='Gastos operativos'
        indexes=[
            models.Index(fields=['anio','mes'], name='idx_gasto_periodo'),
            models.Index(fields=['estado','anio','mes'], name='idx_gasto_estado'),
            models.Index(fields=['cheque_fecha_cobro'], name='idx_gasto_cheque'),
        ]

    def __str__(self):
        mes_label = dict(self.MESES).get(self.mes, self.mes)
        return f'{self.descripcion} — {mes_label}/{self.anio} — Gs. {self.monto:,.0f}'

    @property
    def periodo_label(self):
        return f'{dict(self.MESES).get(self.mes, self.mes)} {self.anio}'

    @property
    def dias_para_cobro_cheque(self):
        """Días que faltan para la fecha de cobro del cheque. None si no aplica."""
        if self.metodo_pago == self.PAGO_CHEQUE and self.cheque_fecha_cobro:
            return (self.cheque_fecha_cobro - date.today()).days
        return None


class PedidoProveedor(models.Model):
    """
    Pedido de mercadería a un proveedor, con plazo de entrega comprometido.
    Permite seguir qué pedidos están por llegar y cuáles se atrasaron.
    """
    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_EN_CAMINO = 'en_camino'
    ESTADO_RECIBIDO  = 'recibido'
    ESTADO_CANCELADO = 'cancelado'
    ESTADOS = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_EN_CAMINO, 'En camino'),
        (ESTADO_RECIBIDO,  'Recibido'),
        (ESTADO_CANCELADO, 'Cancelado'),
    ]

    UNIDAD_VENTA  = 'venta'
    UNIDAD_CAJA   = 'caja'
    UNIDAD_PALLET = 'pallet'
    UNIDADES_PEDIDO = [
        (UNIDAD_VENTA,  'Unidad de venta (m²/unidad)'),
        (UNIDAD_CAJA,   'Cajas'),
        (UNIDAD_PALLET, 'Pallets'),
    ]

    proveedor        = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name='pedidos')
    descripcion      = models.CharField(max_length=250, help_text='Qué se pidió')
    producto         = models.ForeignKey(
                          'productos.Producto', on_delete=models.SET_NULL,
                          null=True, blank=True, related_name='pedidos_proveedor',
                          help_text='Producto del catálogo que se está reponiendo (opcional)')
    cantidad_pedida  = models.DecimalField(max_digits=10, decimal_places=4,
                          null=True, blank=True,
                          validators=[MinValueValidator(Decimal('0.0001'))],
                          help_text='Cantidad pedida, en la unidad indicada por unidad_pedido')
    unidad_pedido    = models.CharField(max_length=10, choices=UNIDADES_PEDIDO, default=UNIDAD_VENTA,
                          help_text=(
                              'Unidad en la que se cargó cantidad_pedida — a los proveedores se les '
                              'compra en pallets o cajas, no en m², así que se guarda tal como se '
                              'pidió en vez de convertir a m² de entrada y perder ese dato.'
                          ))
    monto_estimado   = models.DecimalField(max_digits=14, decimal_places=2,
                          null=True, blank=True,
                          validators=[MinValueValidator(Decimal('0'))])
    fecha_pedido     = models.DateField(default=date.today)
    fecha_entrega_estimada = models.DateField(
                          help_text='Plazo comprometido por el proveedor')
    fecha_entrega_real = models.DateField(null=True, blank=True)
    estado           = models.CharField(max_length=15, choices=ESTADOS, default=ESTADO_PENDIENTE)
    registrado_por   = models.ForeignKey(settings.AUTH_USER_MODEL,
                          on_delete=models.PROTECT, related_name='pedidos_proveedor')
    notas            = models.TextField(blank=True)
    fecha_creacion   = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table='pedidos_proveedor'; ordering=['-fecha_pedido','fecha_entrega_estimada']
        verbose_name='Pedido a proveedor'; verbose_name_plural='Pedidos a proveedores'
        indexes=[
            models.Index(fields=['estado','fecha_entrega_estimada'], name='idx_pedprov_estado'),
        ]

    def __str__(self):
        return f'{self.proveedor.nombre} — {self.descripcion[:40]} ({self.get_estado_display()})'

    @property
    def dias_para_entrega(self):
        """Días que faltan para la entrega estimada. Negativo si está atrasado."""
        if self.estado in (self.ESTADO_RECIBIDO, self.ESTADO_CANCELADO):
            return None
        return (self.fecha_entrega_estimada - date.today()).days
