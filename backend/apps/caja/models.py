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

    def total_reintegros(self, medio=None):
        """
        Plata que salió de la caja en este turno por devoluciones.

        Con `medio` se acota a uno: el arqueo solo resta el efectivo, porque
        un reintegro por transferencia nunca salió del cajón.
        """
        qs = self.devoluciones.filter(monto_reintegro__gt=0)
        if medio:
            qs = qs.filter(medio_reintegro=medio)
        return qs.aggregate(total=models.Sum('monto_reintegro'))['total'] or 0


class Pago(models.Model):
    """Pago asociado a una nota de pedido"""
    MEDIO_EFECTIVO = 'efectivo'
    MEDIO_TARJETA_DEBITO = 'debito'
    MEDIO_TARJETA_CREDITO = 'credito'
    MEDIO_TRANSFERENCIA = 'transferencia'
    MEDIO_CHEQUE = 'cheque'

    MEDIOS = [
        (MEDIO_EFECTIVO, 'Efectivo'),
        (MEDIO_TARJETA_DEBITO, 'Tarjeta de débito'),
        (MEDIO_TARJETA_CREDITO, 'Tarjeta de crédito'),
        (MEDIO_TRANSFERENCIA, 'Transferencia bancaria'),
        (MEDIO_CHEQUE, 'Cheque'),
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

    # ── Datos del comprobante ──────────────────────────────────
    # Antes de esto, "ticket" vs "factura" y los datos del cliente (RUC,
    # razón social...) solo vivían de paso en la request de ConfirmarPago:
    # se usaban para armar el papel impreso en el momento y se perdían. Sin
    # DocumentoElectronico real (SIFEN_HABILITADO=False, el caso de hoy),
    # reimprimir un pago viejo no tenía de dónde sacar esos datos — salía
    # siempre como ticket, aunque se hubiera cobrado como factura. Quedan
    # acá para que ReimprimirTicketView pueda reconstruir el comprobante
    # correcto y para poder buscar cobros por RUC.
    COMPROBANTE_TICKET = 'ticket'
    COMPROBANTE_FACTURA = 'factura'
    TIPOS_COMPROBANTE = [
        (COMPROBANTE_TICKET, 'Ticket'),
        (COMPROBANTE_FACTURA, 'Factura'),
    ]
    tipo_comprobante = models.CharField(
        max_length=10, choices=TIPOS_COMPROBANTE, default=COMPROBANTE_TICKET,
    )
    cliente_ruc = models.CharField(max_length=30, blank=True, db_index=True)
    cliente_razon_social = models.CharField(max_length=200, blank=True)
    cliente_telefono = models.CharField(max_length=30, blank=True)
    cliente_direccion = models.CharField(max_length=255, blank=True)
    # Correo del receptor. No es un dato de contacto más: es el campo D216
    # (`dEmailRec`) del documento electrónico, por el que el comprobante le
    # llega al cliente una vez que la facturación electrónica esté en marcha.
    # 80 caracteres es el máximo que fija el Manual V150 para ese campo — no
    # el largo de un EmailField cualquiera. Ver codigos.validar_email_receptor.
    cliente_email = models.EmailField(max_length=80, blank=True)
    condicion_venta = models.CharField(max_length=20, blank=True, default='Contado')

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

    @property
    def documento_electronico(self):
        """
        La factura electrónica de este cobro, si se emitió.

        Existe para que el resto del sistema siga hablando de "el documento
        electrónico del pago" en singular, que es como se lo piensa: un cobro
        se factura una sola vez. La relación por debajo es de varios porque
        además puede colgar una nota de crédito, que es otro documento sobre
        el mismo cobro — pero cuando alguien pide "el documento" de una venta
        se refiere a su factura.
        """
        from apps.facturacion.codigos import TIPO_DE_FACTURA
        return self.documentos_electronicos.filter(
            tipo_documento=TIPO_DE_FACTURA).first()

    @property
    def nota_credito(self):
        """La nota de crédito que anula o corrige esta venta, si existe."""
        from apps.facturacion.codigos import TIPO_DE_NOTA_CREDITO
        return self.documentos_electronicos.filter(
            tipo_documento=TIPO_DE_NOTA_CREDITO).first()

    def __str__(self):
        return f'Pago {self.numero_ticket} — {self.get_medio_pago_display()} — {self.monto}'


class DatosTarjeta(models.Model):
    """
    Datos del cobro con tarjeta, tal como los pide el SIFEN.

    Existe por una razón concreta: el grupo E620 (`gPagTarCD`) del Manual
    Técnico **se activa obligatoriamente** cuando el medio de pago es tarjeta
    de crédito o débito. Sin al menos la denominación de la tarjeta, el
    documento electrónico de esa venta vuelve rechazado.

    Va en una tabla aparte y no en columnas de `Pago` porque solo aplica a
    una parte de los cobros, y porque así se puede preguntar directamente
    cuáles son los cobros con tarjeta a los que les falta el dato.

    Los datos salen de la terminal POS: o los copia la cajera del voucher, o
    los manda la terminal si algún día se integra (ver apps/caja/pos.py). El
    modelo es el mismo en los dos casos.
    """
    pago = models.OneToOneField(
        Pago, on_delete=models.CASCADE, related_name='datos_tarjeta')

    # ── Obligatorios para el SIFEN ───────────────────────────────────────
    denominacion = models.PositiveSmallIntegerField(
        help_text='Código E621: 1 Visa, 2 Mastercard, 3 Amex, 4 Maestro, '
                  '5 Panal, 6 Cabal, 99 Otra.')
    denominacion_descripcion = models.CharField(
        max_length=20, blank=True,
        help_text='Solo para denominación 99: el nombre real de la tarjeta.')
    forma_procesamiento = models.PositiveSmallIntegerField(
        default=1, help_text='Código E626: 1 POS, 2 pago electrónico, 9 otro.')

    # ── Opcionales para el SIFEN, útiles para conciliar ──────────────────
    codigo_autorizacion = models.CharField(
        max_length=10, blank=True,
        help_text='El que imprime el voucher de la terminal.')
    titular = models.CharField(max_length=30, blank=True)
    ultimos_digitos = models.CharField(
        max_length=4, blank=True,
        help_text='Los últimos cuatro de la tarjeta. Nunca el número entero: '
                  'guardarlo completo sería un problema de seguridad y el '
                  'SIFEN tampoco lo pide.')
    procesadora_ruc = models.CharField(max_length=20, blank=True)
    procesadora_razon_social = models.CharField(max_length=60, blank=True)
    numero_boleta = models.CharField(
        max_length=30, blank=True,
        help_text='Número del voucher, para cruzar con el resumen de la '
                  'procesadora al cierre.')

    origen = models.CharField(
        max_length=20, default='manual',
        help_text='Qué terminal produjo estos datos (manual, simulada, o el '
                  'driver de la procesadora).')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'caja_datos_tarjeta'
        verbose_name = 'Datos de tarjeta'
        verbose_name_plural = 'Datos de tarjeta'

    def __str__(self):
        cola = f' ****{self.ultimos_digitos}' if self.ultimos_digitos else ''
        return f'{self.descripcion_sifen}{cola} — {self.pago.numero_ticket}'

    @property
    def descripcion_sifen(self) -> str:
        """Descripción del campo E622, coherente con el código E621."""
        from apps.facturacion import codigos
        return codigos.descripcion_tarjeta(
            self.denominacion, self.denominacion_descripcion)


class DatosCheque(models.Model):
    """
    Datos del cobro con cheque: qué papel recibió la caja.

    Existe por dos motivos que apuntan al mismo lado. El primero es fiscal:
    el grupo E630 (`gPagCheq`) del Manual Técnico **se activa
    obligatoriamente** cuando el medio de pago es cheque, y sus dos campos
    —número y banco emisor— son de ocurrencia 1-1. Sin ellos el documento
    electrónico de esa venta vuelve rechazado.

    El segundo es del negocio, y rige aunque el SIFEN esté apagado: a
    diferencia de la tarjeta —donde la terminal ya autorizó el cobro y el
    voucher queda impreso—, un cheque es una promesa de pago. Si la caja no
    anota de qué banco es y qué número tiene, el local se queda con un papel
    que después no puede cruzar contra nada. Por eso los dos campos se
    exigen siempre, no solo al facturar.

    Va en una tabla aparte, igual que `DatosTarjeta` y por la misma razón:
    solo aplica a una parte de los cobros.
    """
    pago = models.OneToOneField(
        Pago, on_delete=models.CASCADE, related_name='datos_cheque')

    # ── Obligatorios para el SIFEN ───────────────────────────────────────
    numero = models.CharField(
        max_length=8,
        help_text='Campo E631: ocho dígitos, completados con ceros a la '
                  'izquierda. Se normaliza al guardar.')
    banco = models.CharField(
        max_length=20,
        help_text='Campo E632: banco emisor, de 4 a 20 caracteres. El '
                  'mínimo es del SIFEN, así que va el nombre y no la sigla.')

    # ── Del negocio, no del SIFEN ────────────────────────────────────────
    titular = models.CharField(
        max_length=60, blank=True,
        help_text='A nombre de quién está librado el cheque.')
    fecha_cobro = models.DateField(
        null=True, blank=True,
        help_text='Fecha a partir de la cual el cheque se puede cobrar. '
                  'Vacío = a la vista. Cargada = cheque diferido, que no es '
                  'plata en el cajón todavía.')

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'caja_datos_cheque'
        verbose_name = 'Datos de cheque'
        verbose_name_plural = 'Datos de cheque'

    def __str__(self):
        return f'Cheque {self.numero} — {self.banco} — {self.pago.numero_ticket}'

    def save(self, *args, **kwargs):
        from apps.facturacion import codigos
        self.numero = codigos.numero_cheque_sifen(self.numero)
        super().save(*args, **kwargs)

    @property
    def es_diferido(self) -> bool:
        """¿El cheque todavía no se puede depositar?"""
        from django.utils import timezone
        return bool(self.fecha_cobro and self.fecha_cobro > timezone.localdate())

    @property
    def descripcion_corta(self) -> str:
        """Una línea para el ticket y las pantallas: 'Nro — Banco'."""
        texto = f'{self.numero} — {self.banco}'
        if self.fecha_cobro:
            texto += f' (al {self.fecha_cobro.strftime("%d/%m/%Y")})'
        return texto


class Devolucion(models.Model):
    """
    El cliente trae de vuelta mercadería de una venta ya cobrada.

    Cubre tres casos que en el mostrador son uno solo:

      · **Devolución sin cambio** — se le reintegra lo que pagó por lo que
        trae. Sale plata de la caja (`monto_reintegro`).
      · **Cambio por algo que vale más** — lo que trae queda como crédito a
        favor del pedido nuevo (`pedido_cambio`) y se cobra solo la
        diferencia, en un `Pago` normal (`pago_cambio`) cuyo monto ya viene
        neto del crédito.
      · **Cambio por algo que vale menos** — el pedido nuevo se da por pagado
        con el crédito (su `Pago` es de 0) y el sobrante se reintegra.

    Así, en cualquiera de los tres, la suma de los cobros menos los
    reintegros es lo que realmente entró al negocio, y ningún reporte tiene
    que conocer el crédito para cuadrar.

    El crédito sale de lo que **se cobró** por cada ítem, no de su precio de
    lista: si la venta tuvo descuento en caja o precio negociado, devolver al
    precio de lista le daría al cliente más de lo que pagó. Ver
    apps/caja/devoluciones.py.

    Mientras no exista la nota de crédito parcial, una venta con factura
    electrónica viva no se puede devolver por acá: el SIFEN seguiría teniendo
    la venta entera. Ver `devoluciones.validar_fiscal`.
    """
    MOTIVO_CAMBIO            = 'cambio'
    MOTIVO_ESTADO_INADECUADO = 'estado_inadecuado'
    MOTIVO_OTRO              = 'otro'
    MOTIVOS = [
        (MOTIVO_CAMBIO,            'Cambio de producto'),
        (MOTIVO_ESTADO_INADECUADO, 'Devolución por estado inadecuado'),
        (MOTIVO_OTRO,              'Otro motivo'),
    ]

    numero = models.CharField(max_length=20, unique=True)
    pago_original = models.ForeignKey(
        Pago, on_delete=models.PROTECT, related_name='devoluciones',
        help_text='El cobro de la venta de la que vuelve la mercadería.')
    sesion_caja = models.ForeignKey(
        SesionCaja, on_delete=models.PROTECT, related_name='devoluciones',
        help_text='El turno por el que se movió la plata, no el de la venta.')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='devoluciones_registradas')

    motivo = models.CharField(max_length=20, choices=MOTIVOS)
    motivo_detalle = models.CharField(
        max_length=200, blank=True,
        help_text='Obligatorio con "Otro motivo"; opcional en el resto.')
    observaciones = models.TextField(blank=True)

    total_credito = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text='Lo que vale, a precio cobrado, la mercadería que volvió.')

    pedido_cambio = models.OneToOneField(
        'ventas.NotaPedido', on_delete=models.PROTECT,
        null=True, blank=True, related_name='devolucion_de_cambio',
        help_text='Lo que el cliente se lleva a cambio, si se lleva algo.')
    pago_cambio = models.OneToOneField(
        Pago, on_delete=models.PROTECT,
        null=True, blank=True, related_name='devolucion_aplicada',
        help_text='El cobro del pedido de cambio, ya neto del crédito.')

    monto_reintegro = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text='Lo que salió de la caja hacia el cliente.')
    medio_reintegro = models.CharField(
        max_length=20, choices=Pago.MEDIOS, blank=True)

    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'caja_devoluciones'
        ordering = ['-fecha']
        verbose_name = 'Devolución'
        verbose_name_plural = 'Devoluciones'

    def __str__(self):
        return f'{self.numero} — {self.get_motivo_display()} — {self.total_credito}'

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            hoy = timezone.now()
            correlativo = Devolucion.objects.filter(
                fecha__year=hoy.year, fecha__month=hoy.month).count() + 1
            prefijo = f'DEV-{hoy.strftime("%Y%m")}-'
            while Devolucion.objects.filter(
                    numero=f'{prefijo}{correlativo:04d}').exists():
                correlativo += 1
            self.numero = f'{prefijo}{correlativo:04d}'
        super().save(*args, **kwargs)

    @property
    def credito_aplicado(self):
        """La parte del crédito que se usó para pagar el pedido de cambio."""
        return self.total_credito - self.monto_reintegro

    @property
    def motivo_texto(self):
        if self.motivo_detalle:
            return f'{self.get_motivo_display()}: {self.motivo_detalle}'
        return self.get_motivo_display()


class ItemDevolucion(models.Model):
    """Una línea de la venta original que volvió, total o parcialmente."""
    devolucion = models.ForeignKey(
        Devolucion, on_delete=models.CASCADE, related_name='items')
    item_pedido = models.ForeignKey(
        'ventas.ItemPedido', on_delete=models.PROTECT,
        related_name='devoluciones')
    variante = models.ForeignKey(
        'productos.Variante', on_delete=models.PROTECT,
        related_name='items_devueltos')
    cantidad = models.DecimalField(max_digits=10, decimal_places=4)
    monto = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text='Crédito por esta línea, a precio cobrado.')
    reingresa_stock = models.BooleanField(
        default=True,
        help_text='False para mercadería dañada: vuelve al local pero no al '
                  'stock vendible, o el showroom ofrecería piezas rotas.')

    class Meta:
        db_table = 'caja_items_devolucion'
        verbose_name = 'Ítem devuelto'
        verbose_name_plural = 'Ítems devueltos'

    def __str__(self):
        return f'{self.variante} × {self.cantidad} = {self.monto}'
