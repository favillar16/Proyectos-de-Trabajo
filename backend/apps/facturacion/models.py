"""
Modelos de facturación electrónica.

Dos piezas:

  · SecuenciaComprobante — el correlativo sin saltos por punto de expedición.
  · DocumentoElectronico — la cola de DEs pendientes de transmitir al SIFEN.

Sobre la cola: este sistema es un appliance de red local pensado para
funcionar **sin internet** (ver CLAUDE.md). El SIFEN, en cambio, exige
transmitir por internet. Si el cobro esperara la respuesta del SIFEN, un
corte de conexión frenaría la caja del local con clientes en el mostrador.

Por eso la emisión es asíncrona: al confirmar el pago se calcula el CDC
localmente, se guarda el DE en estado 'pendiente' y se imprime el KuDE en el
acto. Un worker aparte lo transmite cuando hay conexión y va anotando el
resultado. La venta nunca depende de la red.
"""
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction

from . import numeracion


class SecuenciaComprobante(models.Model):
    """
    Correlativo de comprobantes por (tipo de documento, establecimiento,
    punto de expedición).

    Una fila por talonario habilitado. El número se toma con
    select_for_update() para que dos cajas cobrando al mismo tiempo no
    puedan sacar el mismo número — la DNIT no perdona duplicados ni saltos.
    """
    tipo_documento = models.PositiveSmallIntegerField(
        help_text='Código iTiDE del SIFEN. 1 = factura.')
    establecimiento = models.CharField(max_length=3)
    punto_expedicion = models.CharField(max_length=3)

    ultimo_numero = models.PositiveIntegerField(
        default=0,
        help_text='Último número emitido. El próximo comprobante lleva este + 1.')

    # Rango autorizado por el timbrado. Si la DNIT autorizó del 1 al 999, al
    # llegar al tope hay que pedir timbrado nuevo: mejor avisar antes de
    # quedarse sin poder facturar en medio de una venta.
    numero_desde = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1)])
    numero_hasta = models.PositiveIntegerField(
        default=numeracion.NUMERO_MAXIMO, validators=[MinValueValidator(1)])

    activa = models.BooleanField(default=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'fe_secuencias_comprobante'
        verbose_name = 'Secuencia de comprobante'
        verbose_name_plural = 'Secuencias de comprobante'
        constraints = [
            models.UniqueConstraint(
                fields=['tipo_documento', 'establecimiento', 'punto_expedicion'],
                name='uq_secuencia_por_punto_expedicion'),
        ]

    def __str__(self):
        return (f'{self.establecimiento}-{self.punto_expedicion} '
                f'(tipo {self.tipo_documento}) — último {self.ultimo_numero}')

    @property
    def numeros_restantes(self) -> int:
        return max(0, self.numero_hasta - self.ultimo_numero)

    @classmethod
    @transaction.atomic
    def siguiente(cls, tipo_documento, establecimiento, punto_expedicion):
        """
        Reserva y devuelve el próximo número: (numero, 'EEE-PPP-NNNNNNN').

        Tiene que llamarse dentro de la misma transacción que crea el
        comprobante. Si la transacción se revierte, el número vuelve atrás y
        no queda un salto en el correlativo.
        """
        secuencia, _ = cls.objects.select_for_update().get_or_create(
            tipo_documento=tipo_documento,
            establecimiento=f'{int(establecimiento):03d}',
            punto_expedicion=f'{int(punto_expedicion):03d}',
        )
        if not secuencia.activa:
            raise ValueError(
                f'El punto de expedición {secuencia.establecimiento}-'
                f'{secuencia.punto_expedicion} está desactivado.')

        proximo = max(secuencia.ultimo_numero + 1, secuencia.numero_desde)
        if proximo > secuencia.numero_hasta:
            raise ValueError(
                f'Se agotó el rango autorizado del punto de expedición '
                f'{secuencia.establecimiento}-{secuencia.punto_expedicion} '
                f'(hasta {secuencia.numero_hasta}). Hay que solicitar un '
                f'timbrado nuevo a la DNIT antes de seguir facturando.')

        secuencia.ultimo_numero = proximo
        secuencia.save(update_fields=['ultimo_numero', 'fecha_actualizacion'])

        return proximo, numeracion.formatear(
            secuencia.establecimiento, secuencia.punto_expedicion, proximo)


class DocumentoElectronico(models.Model):
    """
    Un DE emitido por el sistema, con su estado frente al SIFEN.

    Los datos fiscales se copian acá al emitir en vez de leerse de settings
    al imprimir. Es a propósito: si mañana cambia el timbrado, una
    reimpresión de una factura vieja tiene que salir con el timbrado que
    tenía cuando se emitió, no con el actual. Un comprobante es un registro
    histórico, no una vista de la configuración de hoy.
    """
    ESTADO_PENDIENTE = 'pendiente'    # generado, todavía sin transmitir
    ESTADO_FIRMADO = 'firmado'        # XML firmado, listo para enviar
    ESTADO_ENVIADO = 'enviado'        # transmitido, sin respuesta definitiva
    ESTADO_APROBADO = 'aprobado'      # el SIFEN lo aceptó
    ESTADO_RECHAZADO = 'rechazado'    # el SIFEN lo rechazó: hay que corregir
    ESTADO_CANCELADO = 'cancelado'    # anulado por evento de cancelación

    ESTADOS = [
        (ESTADO_PENDIENTE, 'Pendiente de envío'),
        (ESTADO_FIRMADO,   'Firmado'),
        (ESTADO_ENVIADO,   'Enviado, esperando respuesta'),
        (ESTADO_APROBADO,  'Aprobado por el SIFEN'),
        (ESTADO_RECHAZADO, 'Rechazado por el SIFEN'),
        (ESTADO_CANCELADO, 'Cancelado'),
    ]

    # Estados desde los que todavía tiene sentido reintentar el envío.
    ESTADOS_TRANSMITIBLES = (ESTADO_PENDIENTE, ESTADO_FIRMADO, ESTADO_ENVIADO)

    pago = models.OneToOneField(
        'caja.Pago', on_delete=models.PROTECT,
        related_name='documento_electronico',
        help_text='El cobro que originó este comprobante.')

    # ── Identificación del DE ────────────────────────────────────────────
    cdc = models.CharField(
        max_length=44, unique=True, db_index=True,
        help_text='Código de Control de 44 dígitos. Se calcula localmente.')
    tipo_documento = models.PositiveSmallIntegerField(default=1)
    establecimiento = models.CharField(max_length=3)
    punto_expedicion = models.CharField(max_length=3)
    numero = models.PositiveIntegerField()
    numero_completo = models.CharField(
        max_length=15, db_index=True, help_text='EEE-PPP-NNNNNNN')
    codigo_seguridad = models.CharField(max_length=9)
    fecha_emision = models.DateTimeField()

    # ── Snapshot fiscal del emisor al momento de emitir ──────────────────
    emisor_ruc = models.CharField(max_length=20)
    emisor_razon_social = models.CharField(max_length=180)
    emisor_direccion = models.CharField(max_length=250, blank=True)
    emisor_telefono = models.CharField(max_length=40, blank=True)
    emisor_timbrado = models.CharField(max_length=20, blank=True)
    emisor_timbrado_vto = models.CharField(max_length=20, blank=True)

    # ── Receptor ─────────────────────────────────────────────────────────
    receptor_ruc = models.CharField(max_length=20, blank=True)
    receptor_razon_social = models.CharField(max_length=180)
    receptor_direccion = models.CharField(max_length=250, blank=True)
    receptor_telefono = models.CharField(max_length=40, blank=True)
    receptor_email = models.EmailField(blank=True)
    receptor_naturaleza = models.PositiveSmallIntegerField(
        default=2, help_text='1 contribuyente, 2 no contribuyente.')

    # ── Totales, ya desglosados como los declara el SIFEN ────────────────
    condicion_venta = models.PositiveSmallIntegerField(default=1)
    medio_pago = models.PositiveSmallIntegerField(default=1)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    total_gravado_10 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_gravado_5 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_exento = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    iva_10 = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    iva_5 = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # ── Estado frente al SIFEN ───────────────────────────────────────────
    estado = models.CharField(
        max_length=12, choices=ESTADOS, default=ESTADO_PENDIENTE, db_index=True)
    xml_generado = models.TextField(
        blank=True, help_text='XML del DE. Se guarda para poder reenviarlo.')
    xml_firmado = models.TextField(blank=True)
    respuesta_sifen = models.TextField(
        blank=True, help_text='Última respuesta del SIFEN, tal cual vino.')
    codigo_respuesta = models.CharField(max_length=10, blank=True)
    intentos_envio = models.PositiveIntegerField(default=0)
    ultimo_intento = models.DateTimeField(null=True, blank=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='documentos_electronicos')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fe_documentos_electronicos'
        ordering = ['-fecha_emision']
        verbose_name = 'Documento electrónico'
        verbose_name_plural = 'Documentos electrónicos'
        indexes = [
            models.Index(fields=['estado', 'fecha_emision'],
                         name='idx_de_estado_fecha'),
        ]

    def __str__(self):
        return f'{self.numero_completo} — {self.get_estado_display()}'

    @property
    def pendiente_de_envio(self) -> bool:
        return self.estado in self.ESTADOS_TRANSMITIBLES

    @property
    def url_consulta_qr(self) -> str:
        """
        URL que codifica el QR del KuDE para que el cliente consulte el
        comprobante en el portal de la DNIT.

        ⚠️ El armado real del QR lleva además una firma (hash del DE con el
        código de seguridad) que exige el certificado. Esto es solo la base;
        se completa en el sidecar con facturacionelectronicapy-qrgen.
        """
        base = getattr(settings, 'SIFEN', {}).get('url_consulta_qr', '')
        return f'{base}?nVersion=150&Id={self.cdc}' if base else ''
