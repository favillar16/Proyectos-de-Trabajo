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
from decimal import Decimal

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

    # ForeignKey y no OneToOne: un mismo cobro puede terminar con más de un
    # documento. El caso concreto es la nota de crédito — se emite sobre una
    # factura ya emitida, sobre el mismo cobro, y tiene que convivir con
    # ella. La restricción que importa (no facturar dos veces la misma
    # venta) se conserva con el UniqueConstraint de más abajo, que es lo que
    # el OneToOne garantizaba de verdad.
    # Nullable por la **autofactura**, que es el único tipo que no nace de un
    # cobro: no es una venta, es una compra a alguien sin RUC, y el local se
    # factura a sí mismo. Forzarla a colgar de un Pago habría obligado a
    # inventar un cobro que no existe, que es peor que admitir el null.
    # El UniqueConstraint de más abajo sigue funcionando: Postgres trata
    # cada NULL como distinto, así que no limita cuántas autofacturas hay.
    pago = models.ForeignKey(
        'caja.Pago', on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='documentos_electronicos',
        help_text='El cobro que originó este comprobante. Vacío en la '
                  'autofactura, que no viene de una venta.')

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

    # ── Documento asociado (solo notas de crédito y débito) ──────────────
    # Una nota de crédito no existe sola: corrige un documento anterior y
    # tiene que referenciarlo. Cuando el documento corregido es electrónico
    # se lo referencia por su CDC (campo H004 dCdCDERef del manual).
    documento_asociado_cdc = models.CharField(
        max_length=44, blank=True, db_index=True,
        help_text='CDC del documento que esta nota corrige. Obligatorio en '
                  'notas de crédito y débito.')
    motivo_nota = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Código iMotEmi del motivo de la nota (1 devolución y '
                  'ajuste, 2 devolución, 3 descuento...). Ver codigos.'
                  'MOTIVOS_NOTA.')

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
    # Contenido del QR (campo dCarQR), tal como lo calculó `qrgen`: lleva el
    # hash de la firma y el CSC, así que no se puede reconstruir de este
    # lado. Se guarda al transmitir para que el KuDE lo imprima sin tener
    # que volver a parsear el XML firmado en cada reimpresión.
    enlace_qr = models.TextField(blank=True)
    respuesta_sifen = models.TextField(
        blank=True, help_text='Última respuesta del SIFEN, tal cual vino.')
    codigo_respuesta = models.CharField(max_length=10, blank=True)
    intentos_envio = models.PositiveIntegerField(default=0)
    ultimo_intento = models.DateTimeField(null=True, blank=True)
    # Momento en que el SIFEN aprobó el DTE. No es lo mismo que
    # `fecha_emision` (cuándo se cobró) ni que `ultimo_intento` (cuándo se
    # transmitió): el plazo para cancelar —48 h en la factura, 168 en el
    # resto— se cuenta desde la aprobación, así que hay que guardarla.
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)

    # El lote por el que se transmitió, si fue por el camino asincrónico.
    # Null es el caso normal: el sincrónico no arma lotes. Se referencia por
    # string porque LoteTransmision se define más abajo en este archivo.
    lote = models.ForeignKey(
        'facturacion.LoteTransmision', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='documentos',
        help_text='Lote asincrónico por el que se envió, si no fue sincrónico.')

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
        constraints = [
            # Un cobro no puede tener dos facturas, ni dos notas de crédito.
            # Puede tener una factura Y una nota de crédito: son tipos
            # distintos.
            models.UniqueConstraint(
                fields=['pago', 'tipo_documento'],
                name='uq_un_documento_por_tipo_y_cobro'),
        ]

    def __str__(self):
        return f'{self.numero_completo} — {self.get_estado_display()}'

    def clean(self):
        """
        Una nota de crédito o débito sin documento asociado no es emitible.

        Se valida acá y no solo al armar el payload porque es una regla del
        documento, no del XML: una nota que no dice qué corrige no significa
        nada, ni siquiera puertas adentro.
        """
        from django.core.exceptions import ValidationError
        from . import codigos

        es_nota = self.tipo_documento in (codigos.TIPO_DE_NOTA_CREDITO,
                                          codigos.TIPO_DE_NOTA_DEBITO)
        if es_nota:
            if not self.documento_asociado_cdc:
                raise ValidationError({
                    'documento_asociado_cdc':
                        'Una nota de crédito o débito tiene que referenciar '
                        'el CDC del documento que corrige.'})
            if self.motivo_nota not in codigos.MOTIVOS_NOTA:
                raise ValidationError({
                    'motivo_nota':
                        'Falta el motivo de la nota, o no es uno de los '
                        'códigos que acepta el SIFEN.'})
        elif self.documento_asociado_cdc or self.motivo_nota is not None:
            raise ValidationError(
                'Solo las notas de crédito y débito llevan documento '
                'asociado y motivo.')

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


class DatosTraslado(models.Model):
    """
    Datos del traslado de mercadería, para la nota de remisión electrónica.

    Por qué existe y por qué acá: la nota de remisión es el único de los cinco
    documentos que **no describe un cobro sino un movimiento físico**. No
    cuelga de un `Pago` como los demás: cuelga del pedido que se está
    entregando. El negocio vende pisos y sanitarios a domicilio, así que el
    caso normal es "traslado por venta" con el camión propio.

    Vive en `facturacion` y no en `ventas` porque hoy existe únicamente para
    poder emitir el DE — el sistema no tiene un módulo de entregas. Si algún
    día lo tiene, esto es lo que hay que mudar.

    Los campos son los de los grupos E6 (motivo y responsable) y E10
    (transporte, vehículo, transportista y direcciones) del Manual Técnico.
    """
    pedido = models.OneToOneField(
        'ventas.NotaPedido', on_delete=models.PROTECT,
        related_name='datos_traslado',
        help_text='El pedido cuya mercadería se traslada.')

    # ── Grupo E6: motivo y responsable ───────────────────────────────────
    motivo = models.PositiveSmallIntegerField(
        default=1,
        help_text='Código E501: 1 traslado por venta, 6 por devolución, '
                  '7 entre locales... Ver codigos.MOTIVOS_TRASLADO.')
    responsable = models.PositiveSmallIntegerField(
        default=1,
        help_text='Código E503: quién emite la nota. 1 = el emisor de la '
                  'factura, que es el caso del negocio.')

    fecha_inicio_traslado = models.DateField(
        help_text='Cuándo sale la mercadería del local.')
    fecha_fin_traslado = models.DateField(
        null=True, blank=True,
        help_text='Cuándo se estima que llega.')
    kilometros = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Kilómetros estimados de recorrido (E505). La NT 010 lo '
                  'volvió OBLIGATORIO para la nota de remisión, así que sin '
                  'esto el documento vuelve rechazado. Queda nullable en la '
                  'base para no romper filas viejas; clean() lo exige.')

    # ── Grupo E10: transporte ────────────────────────────────────────────
    tipo_transporte = models.PositiveSmallIntegerField(
        default=1, help_text='Código E901: 1 propio, 2 de terceros.')
    modalidad = models.PositiveSmallIntegerField(
        default=1,
        help_text='Código E903: 1 terrestre, 2 fluvial, 3 aéreo, 4 multimodal.')
    responsable_flete = models.PositiveSmallIntegerField(
        default=5,
        help_text='Código E905. 5 = transporte propio, que es el caso cuando '
                  'entrega el camión del negocio.')

    # ── Grupo E10.3: vehículo ────────────────────────────────────────────
    vehiculo_tipo = models.CharField(
        max_length=10, blank=True,
        help_text='Camión, camioneta... Tiene que ser coherente con la '
                  'modalidad (E961).')
    vehiculo_marca = models.CharField(max_length=10, blank=True)
    vehiculo_matricula = models.CharField(
        max_length=7, blank=True,
        help_text='La chapa. Es la identificación habitual de un camión '
                  'local (E965). La NT 005 amplió el campo de 6 a 7.')
    vehiculo_numero = models.CharField(
        max_length=20, blank=True,
        help_text='Número de identificación, si no se usa la matrícula (E963).')

    # ── Grupo E10.4: transportista ───────────────────────────────────────
    transportista_nombre = models.CharField(max_length=60, blank=True)
    transportista_ruc = models.CharField(max_length=20, blank=True)
    transportista_documento = models.CharField(
        max_length=20, blank=True,
        help_text='Cédula, cuando el transportista no es contribuyente.')
    transportista_direccion = models.CharField(
        max_length=255, blank=True,
        help_text='Obligatoria cuando se declara un transportista (E10.4).')
    conductor_nombre = models.CharField(max_length=60, blank=True)
    conductor_documento = models.CharField(max_length=20, blank=True)
    conductor_direccion = models.CharField(
        max_length=255, blank=True,
        help_text='Obligatoria cuando se declara un chofer.')

    # ── Direcciones de salida y llegada ──────────────────────────────────
    # El SIFEN las pide desglosadas, igual que el domicilio del emisor: no
    # acepta la dirección como un texto libre.
    #
    # El local de salida casi siempre es el propio negocio, así que estos
    # campos quedan vacíos y `payload.py` cae en los del emisor. Existen para
    # el caso en que la mercadería salga de otro lado (un depósito, la casa
    # del proveedor) y ahí sí hay que declararlo.
    direccion_salida = models.CharField(max_length=255, blank=True)
    salida_numero_casa = models.CharField(max_length=20, blank=True)
    salida_ciudad = models.PositiveIntegerField(null=True, blank=True)
    salida_ciudad_desc = models.CharField(max_length=40, blank=True)
    direccion_entrega = models.CharField(max_length=255)
    entrega_numero_casa = models.CharField(max_length=20, blank=True, default='0')
    entrega_departamento = models.PositiveSmallIntegerField(null=True, blank=True)
    entrega_departamento_desc = models.CharField(max_length=40, blank=True)
    entrega_distrito = models.PositiveSmallIntegerField(null=True, blank=True)
    entrega_distrito_desc = models.CharField(max_length=40, blank=True)
    entrega_ciudad = models.PositiveIntegerField(null=True, blank=True)
    entrega_ciudad_desc = models.CharField(max_length=40, blank=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='traslados_registrados')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fe_datos_traslado'
        verbose_name = 'Datos de traslado'
        verbose_name_plural = 'Datos de traslado'

    def __str__(self):
        return f'Traslado del pedido {self.pedido_id} — {self.direccion_entrega[:40]}'

    def clean(self):
        """
        El vehículo hay que poder identificarlo de alguna forma.

        El SIFEN exige o la matrícula o el número de identificación (campo
        E967 decide cuál), y un traslado sin vehículo identificable es una
        nota de remisión que va a volver rechazada.
        """
        from django.core.exceptions import ValidationError
        if not (self.vehiculo_matricula or self.vehiculo_numero):
            raise ValidationError({
                'vehiculo_matricula':
                    'Hay que identificar el vehículo: la chapa (matrícula) o '
                    'su número de identificación.'})
        if not self.direccion_entrega.strip():
            raise ValidationError({
                'direccion_entrega': 'Falta la dirección de entrega.'})
        if not self.kilometros:
            raise ValidationError({
                'kilometros':
                    'Los kilómetros estimados del recorrido son obligatorios '
                    'para la nota de remisión (campo E505; la NT 010 lo pasó '
                    'de opcional a obligatorio).'})

    @property
    def tipo_identificacion_vehiculo(self) -> int:
        """Campo E967: se deduce de cuál de los dos datos se cargó."""
        from . import codigos
        return (codigos.VEHICULO_POR_MATRICULA if self.vehiculo_matricula
                else codigos.VEHICULO_POR_NUMERO)


class EventoDocumento(models.Model):
    """
    Un evento del rol emisor frente al SIFEN: cancelación o inutilización.

    Los dos existen por el mismo motivo —un comprobante electrónico no se
    borra— pero resuelven situaciones distintas:

      · **Cancelación**: el DTE se emitió bien, el SIFEN lo aprobó y la venta
        después no se concretó. Se cancela el documento aprobado.
      · **Inutilización**: un número del talonario quedó sin usar (se reservó
        y la emisión no llegó a completarse). No hay documento que cancelar:
        lo que se declara es que ese número no va a existir nunca. Es lo que
        cierra el hueco real, porque la DNIT exige que el correlativo no
        tenga saltos sin justificar.

    Un evento se guarda **antes** de transmitirse, igual que un DE: si el
    sidecar está caído o se cortó internet, queda pendiente y lo reintenta el
    worker. Cancelar no puede depender de que la red esté levantada en ese
    segundo — y menos con un plazo de 48 horas corriendo.
    """

    TIPO_CANCELACION = 'cancelacion'
    TIPO_INUTILIZACION = 'inutilizacion'
    TIPOS = [
        (TIPO_CANCELACION,   'Cancelación de un documento'),
        (TIPO_INUTILIZACION, 'Inutilización de un rango de números'),
    ]

    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_ENVIADO = 'enviado'
    ESTADO_APROBADO = 'aprobado'
    ESTADO_RECHAZADO = 'rechazado'
    ESTADOS = [
        (ESTADO_PENDIENTE, 'Pendiente de envío'),
        (ESTADO_ENVIADO,   'Enviado, esperando respuesta'),
        (ESTADO_APROBADO,  'Aprobado por el SIFEN'),
        (ESTADO_RECHAZADO, 'Rechazado por el SIFEN'),
    ]
    ESTADOS_TRANSMITIBLES = (ESTADO_PENDIENTE, ESTADO_ENVIADO)

    # Plazo para pedir la cancelación, contado desde la aprobación en el
    # SIFEN. Manual Técnico V150 §11.6.1, validaciones GDE004a y GDE004b:
    # 48 horas para la factura electrónica, 168 para el resto de los tipos.
    # Vencido el plazo, el camino es una nota de crédito, no un evento.
    HORAS_CANCELACION_FACTURA = 48
    HORAS_CANCELACION_OTROS = 168

    # Manual §11.5.1, GEI006: el rango de una inutilización no puede pasar de
    # 1000 números.
    MAXIMO_NUMEROS_INUTILIZABLES = 1000

    # Tabla J, fila 2: la inutilización debe comunicarse «dentro de los 15
    # primeros días del mes siguiente al acaecimiento del hecho». A
    # diferencia del plazo de cancelación, este NO bloquea: ver
    # `eventos.advertencia_de_plazo_inutilizacion()` para el motivo.
    DIA_LIMITE_INUTILIZACION = 15

    # GEC003 / GEI008: el motivo es campo abierto de 5 a 500 caracteres. El
    # mínimo no es capricho del sistema: el SIFEN rechaza "ok".
    MOTIVO_MIN = 5
    MOTIVO_MAX = 500

    tipo = models.CharField(max_length=15, choices=TIPOS, db_index=True)

    # ── Cancelación ──────────────────────────────────────────────────────
    documento = models.ForeignKey(
        'DocumentoElectronico', on_delete=models.PROTECT,
        null=True, blank=True, related_name='eventos',
        help_text='El DTE que se cancela. Solo en eventos de cancelación.')

    # ── Inutilización ────────────────────────────────────────────────────
    # Se guardan sueltos y no como FK a la secuencia porque describen un
    # hecho histórico: qué números se declararon inutilizados, con qué
    # timbrado. Si mañana cambia el timbrado, este registro no se mueve.
    timbrado = models.CharField(max_length=8, blank=True)
    establecimiento = models.CharField(max_length=3, blank=True)
    punto_expedicion = models.CharField(max_length=3, blank=True)
    numero_desde = models.PositiveIntegerField(null=True, blank=True)
    numero_hasta = models.PositiveIntegerField(null=True, blank=True)
    tipo_documento = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Código iTiDE del talonario inutilizado. 1 = factura.')

    motivo = models.CharField(
        max_length=MOTIVO_MAX,
        help_text='Texto libre de 5 a 500 caracteres. Lo lee la DNIT.')

    # ── Estado frente al SIFEN ───────────────────────────────────────────
    estado = models.CharField(
        max_length=12, choices=ESTADOS, default=ESTADO_PENDIENTE, db_index=True)
    xml_enviado = models.TextField(blank=True)
    respuesta_sifen = models.TextField(blank=True)
    codigo_respuesta = models.CharField(max_length=10, blank=True)
    intentos_envio = models.PositiveIntegerField(default=0)
    ultimo_intento = models.DateTimeField(null=True, blank=True)
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='eventos_fiscales')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fe_eventos'
        ordering = ['-fecha_creacion']
        verbose_name = 'Evento fiscal'
        verbose_name_plural = 'Eventos fiscales'
        indexes = [
            models.Index(fields=['estado', 'fecha_creacion'],
                         name='idx_evento_estado_fecha'),
        ]
        constraints = [
            # Un mismo documento no se cancela dos veces. El SIFEN lo rechaza
            # por duplicidad (validación GEC002b, código 4003) y acá se evita
            # antes de gastar el intento. Los rechazados quedan afuera del
            # índice: si el primero volvió rechazado, se tiene que poder
            # reintentar con el motivo corregido.
            models.UniqueConstraint(
                fields=['documento'],
                condition=models.Q(tipo='cancelacion') & ~models.Q(estado='rechazado'),
                name='uq_una_cancelacion_viva_por_documento'),
        ]

    def __str__(self):
        if self.tipo == self.TIPO_CANCELACION:
            objetivo = self.documento.numero_completo if self.documento else '—'
        else:
            objetivo = (f'{self.establecimiento}-{self.punto_expedicion} '
                        f'{self.numero_desde}..{self.numero_hasta}')
        return f'{self.get_tipo_display()} — {objetivo} — {self.get_estado_display()}'

    def clean(self):
        from django.core.exceptions import ValidationError

        largo = len((self.motivo or '').strip())
        if not self.MOTIVO_MIN <= largo <= self.MOTIVO_MAX:
            raise ValidationError({'motivo': (
                f'El motivo tiene que tener entre {self.MOTIVO_MIN} y '
                f'{self.MOTIVO_MAX} caracteres: lo lee la DNIT y es lo único '
                f'que justifica el evento.')})

        if self.tipo == self.TIPO_CANCELACION:
            if not self.documento_id:
                raise ValidationError({'documento': (
                    'Una cancelación tiene que decir qué documento cancela.')})
            if self.numero_desde or self.numero_hasta:
                raise ValidationError(
                    'Una cancelación no lleva rango de números: eso es una '
                    'inutilización.')
            return

        # ── Inutilización ────────────────────────────────────────────────
        if self.documento_id:
            raise ValidationError({'documento': (
                'Una inutilización no cancela un documento: declara números '
                'que nunca se usaron.')})
        faltantes = [campo for campo, valor in (
            ('timbrado', self.timbrado),
            ('establecimiento', self.establecimiento),
            ('punto_expedicion', self.punto_expedicion),
            ('numero_desde', self.numero_desde),
            ('numero_hasta', self.numero_hasta),
            ('tipo_documento', self.tipo_documento),
        ) if not valor]
        if faltantes:
            raise ValidationError({campo: 'Es obligatorio para inutilizar.'
                                   for campo in faltantes})

        if len(self.timbrado) != 8:
            raise ValidationError({'timbrado': (
                'El timbrado tiene ocho dígitos (campo GEI002).')})
        if self.numero_hasta < self.numero_desde:
            raise ValidationError({'numero_hasta': (
                'El número final no puede ser menor que el inicial '
                '(validación GEI006a).')})
        cantidad = self.numero_hasta - self.numero_desde + 1
        if cantidad > self.MAXIMO_NUMEROS_INUTILIZABLES:
            raise ValidationError({'numero_hasta': (
                f'Un evento inutiliza hasta '
                f'{self.MAXIMO_NUMEROS_INUTILIZABLES} números y este pide '
                f'{cantidad} (validación GEI006). Hay que partirlo en varios.')})

    @property
    def pendiente_de_envio(self) -> bool:
        return self.estado in self.ESTADOS_TRANSMITIBLES

    @property
    def rango_legible(self) -> str:
        if self.tipo != self.TIPO_INUTILIZACION:
            return ''
        from . import numeracion
        return (f'{numeracion.formatear(self.establecimiento, self.punto_expedicion, self.numero_desde)}'
                f' a '
                f'{numeracion.formatear(self.establecimiento, self.punto_expedicion, self.numero_hasta)}')


class LoteTransmision(models.Model):
    """
    Un envío asincrónico de varios DE de una sola vez.

    Es el otro camino de transmisión, distinto del sincrónico en algo más
    que la velocidad: **el SIFEN no contesta si los aprobó**. Contesta un
    número de lote (`dProtConsLote`) y los procesa cuando puede; el resultado
    se pide después, por separado. Son dos viajes, y este modelo es lo que
    vive entre uno y otro.

    Sin guardar ese número no hay forma de volver a preguntar: los documentos
    quedarían transmitidos y huérfanos, sin manera de saber si son DTE o si
    fueron rechazados. Por eso el número se guarda antes que nada.

    Lo exige la Guía de Pruebas (5 aprobados y 5 rechazados en lote, por cada
    tipo de documento), pero además sirve en producción: mandar el cierre del
    día en un lote en vez de veinte llamadas sueltas.
    """
    ESTADO_ENVIADO = 'enviado'        # el SIFEN lo recibió; falta el resultado
    ESTADO_PROCESADO = 'procesado'    # ya llegó el resultado de cada documento
    ESTADO_RECHAZADO = 'rechazado'    # el lote entero no fue aceptado

    ESTADOS = [
        (ESTADO_ENVIADO,   'Enviado, esperando resultado'),
        (ESTADO_PROCESADO, 'Procesado'),
        (ESTADO_RECHAZADO, 'Rechazado'),
    ]

    numero = models.CharField(
        max_length=30, unique=True, db_index=True,
        help_text='Número de lote que devolvió el SIFEN (dProtConsLote).')
    estado = models.CharField(
        max_length=15, choices=ESTADOS, default=ESTADO_ENVIADO, db_index=True)
    cantidad = models.PositiveSmallIntegerField(
        default=0, help_text='Cuántos documentos se mandaron en este lote.')

    fecha_envio = models.DateTimeField(auto_now_add=True)
    fecha_resultado = models.DateTimeField(null=True, blank=True)
    # Cuántas veces se preguntó por el resultado. El SIFEN puede tardar, así
    # que "todavía procesando" no es un error y no gasta intentos de envío:
    # se cuenta aparte para poder avisar si un lote quedó sin resultado.
    consultas = models.PositiveSmallIntegerField(default=0)

    codigo_respuesta = models.CharField(max_length=10, blank=True)
    respuesta_sifen = models.TextField(blank=True)

    creado_por = models.ForeignKey(
        'usuarios.Usuario', on_delete=models.PROTECT,
        null=True, blank=True, related_name='lotes_sifen')

    class Meta:
        db_table = 'sifen_lotes'
        verbose_name = 'lote de transmisión'
        verbose_name_plural = 'lotes de transmisión'
        ordering = ['-fecha_envio']

    def __str__(self):
        return f'Lote {self.numero} — {self.get_estado_display()} ({self.cantidad})'


class EventoReceptor(models.Model):
    """
    Un evento del rol **receptor**: lo que Óga Porã declara sobre un DTE que
    le emitió otro.

    Es el otro lado del mostrador y por eso no reusa `EventoDocumento`: aquel
    cuelga de un `DocumentoElectronico` nuestro, y acá el documento **no es
    nuestro** — lo emitió un proveedor. Lo único que tenemos de él es su CDC,
    que es justamente lo que el SIFEN pide para identificarlo.

    Los cuatro tipos, y qué significan (Manual §11.2):

      · **Conformidad** — se acepta el documento. Total (1) o parcial (2); la
        parcial además declara cuándo se estima recibir la mercadería.
      · **Disconformidad** — se rechaza, con motivo. Es conclusivo: puede
        obligar al emisor a emitir una nota de crédito.
      · **Desconocimiento** — "este documento no es mío, yo no hice esta
        operación". Necesita identificar a quien lo desconoce.
      · **Notificación de recepción** — "lo recibí, todavía no me expido".
        Es informativo y opcional.

    Los dos primeros son **conclusivos** y los dos últimos **informativos**:
    un evento informativo no genera ninguna acción del emisor.

    La Guía de Pruebas exige 3 pruebas de cada uno para habilitarse, pero el
    uso real es el de arriba: manifestarse sobre las facturas de proveedores.
    """

    TIPO_CONFORMIDAD = 'conformidad'
    TIPO_DISCONFORMIDAD = 'disconformidad'
    TIPO_DESCONOCIMIENTO = 'desconocimiento'
    TIPO_NOTIFICACION = 'notificacion'
    TIPOS = [
        (TIPO_CONFORMIDAD,     'Conformidad con el DTE'),
        (TIPO_DISCONFORMIDAD,  'Disconformidad con el DTE'),
        (TIPO_DESCONOCIMIENTO, 'Desconocimiento del DE o DTE'),
        (TIPO_NOTIFICACION,    'Notificación de recepción'),
    ]

    # Los que pueden hacer que el emisor tenga que corregir algo. Los otros
    # dos solo dejan una marca.
    TIPOS_CONCLUSIVOS = (TIPO_CONFORMIDAD, TIPO_DISCONFORMIDAD)

    CONFORMIDAD_TOTAL = 1
    CONFORMIDAD_PARCIAL = 2

    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_ENVIADO = 'enviado'
    ESTADO_APROBADO = 'aprobado'
    ESTADO_RECHAZADO = 'rechazado'
    ESTADOS = [
        (ESTADO_PENDIENTE, 'Pendiente de envío'),
        (ESTADO_ENVIADO,   'Enviado, esperando respuesta'),
        (ESTADO_APROBADO,  'Aprobado por el SIFEN'),
        (ESTADO_RECHAZADO, 'Rechazado por el SIFEN'),
    ]
    ESTADOS_TRANSMITIBLES = (ESTADO_PENDIENTE, ESTADO_ENVIADO)

    # Mismo rango que el motivo de los eventos del emisor: el SIFEN rechaza
    # un motivo de dos letras.
    MOTIVO_MIN = 5
    MOTIVO_MAX = 500

    # Tabla J, filas 10 a 13: los cuatro eventos del receptor se registran
    # «hasta 45 días contados desde la fecha de emisión». Ojo con el punto
    # de partida: es la emisión del documento del proveedor, no la fecha en
    # que nos llegó ni la de la aprobación. Sale del CDC, que la lleva
    # adentro (`cdc.fecha_de_emision`).
    DIAS_PARA_REGISTRAR = 45

    # Tabla K: un evento del receptor elegido por equivocación se corrige
    # «hasta 15 días del registro del primer evento», y una sola vez. El
    # evento de corrección todavía no está implementado —la librería de la
    # DNIT no trae generador— pero la regla vive acá para que el día que se
    # implemente no haya que volver al manual.
    DIAS_PARA_CORREGIR = 15

    tipo = models.CharField(max_length=20, choices=TIPOS, db_index=True)

    # El CDC del documento ajeno. Es lo único que lo identifica: no hay un
    # DocumentoElectronico local al que apuntar.
    cdc = models.CharField(
        max_length=44, db_index=True,
        help_text='CDC del DTE emitido por el proveedor, 44 dígitos.')

    # Solo conformidad
    tipo_conformidad = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='1 = total, 2 = parcial. Solo en conformidad.')
    fecha_recepcion = models.DateTimeField(
        null=True, blank=True,
        help_text='Fecha estimada de recepción. Obligatoria si la '
                  'conformidad es parcial, y en desconocimiento y '
                  'notificación.')

    # Disconformidad y desconocimiento
    motivo = models.TextField(blank=True)

    # Desconocimiento y notificación: identifican a quien se manifiesta y al
    # documento del que se habla.
    fecha_emision_documento = models.DateTimeField(null=True, blank=True)
    total_documento = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text='Total en guaraníes del documento. Lo pide la notificación.')

    estado = models.CharField(
        max_length=15, choices=ESTADOS, default=ESTADO_PENDIENTE,
        db_index=True)
    intentos_envio = models.PositiveSmallIntegerField(default=0)
    ultimo_intento = models.DateTimeField(null=True, blank=True)
    codigo_respuesta = models.CharField(max_length=10, blank=True)
    respuesta_sifen = models.TextField(blank=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='eventos_receptor')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fe_eventos_receptor'
        ordering = ['-fecha_creacion']
        verbose_name = 'evento del receptor'
        verbose_name_plural = 'eventos del receptor'
        constraints = [
            # No tiene sentido manifestarse dos veces igual sobre el mismo
            # documento, y el SIFEN lo rechazaría. Se permite reintentar uno
            # rechazado, por eso la condición mira el estado.
            models.UniqueConstraint(
                fields=['cdc', 'tipo'],
                condition=~models.Q(estado='rechazado'),
                name='uq_un_evento_receptor_vivo_por_cdc_y_tipo'),
        ]

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.cdc[:12]}… ({self.estado})'

    @property
    def es_conclusivo(self) -> bool:
        return self.tipo in self.TIPOS_CONCLUSIVOS



class DatosAutofactura(models.Model):
    """
    El vendedor no contribuyente y el lugar de la operación.

    La autofactura es el único documento de los cinco que **no documenta una
    venta**: documenta una **compra** a alguien que no puede emitir factura —
    un particular, alguien sin RUC. El local se factura a sí mismo para poder
    respaldar ese gasto.

    De ahí salen sus dos particularidades:

      · No cuelga de un cobro (por eso `DocumentoElectronico.pago` admite
        null): no hay venta ni pedido detrás.
      · Necesita datos que el sistema no tenía en ninguna parte, porque
        describen a la contraparte de una compra: quién vendió, con qué
        documento, dónde vive, y **dónde ocurrió la transacción** — que el
        SIFEN pide aparte del domicilio del vendedor, y puede no coincidir.

    Los nombres de los campos siguen al grupo `gCamAE` del Manual, verificado
    contra `jsonDteMain.service.js` de la librería de la DNIT.
    """

    # Naturaleza del vendedor (campo E601 iNatVen).
    VENDEDOR_NO_CONTRIBUYENTE = 1
    VENDEDOR_EXTRANJERO = 2
    NATURALEZAS = [
        (VENDEDOR_NO_CONTRIBUYENTE, 'No contribuyente'),
        (VENDEDOR_EXTRANJERO,       'Extranjero'),
    ]

    documento = models.OneToOneField(
        'DocumentoElectronico', on_delete=models.CASCADE,
        related_name='datos_autofactura')

    naturaleza_vendedor = models.PositiveSmallIntegerField(
        choices=NATURALEZAS, default=VENDEDOR_NO_CONTRIBUYENTE)
    # Código de la tabla de tipos de documento de identidad del SIFEN
    # (1 cédula paraguaya, 2 pasaporte, 3 cédula extranjera...).
    tipo_documento_vendedor = models.PositiveSmallIntegerField(default=1)
    numero_documento_vendedor = models.CharField(max_length=20)
    nombre_vendedor = models.CharField(max_length=60)

    direccion_vendedor = models.CharField(max_length=255)
    numero_casa_vendedor = models.CharField(max_length=10, blank=True, default='0')
    departamento_vendedor = models.PositiveSmallIntegerField()
    departamento_vendedor_desc = models.CharField(max_length=40)
    distrito_vendedor = models.PositiveIntegerField()
    distrito_vendedor_desc = models.CharField(max_length=40)
    ciudad_vendedor = models.PositiveIntegerField()
    ciudad_vendedor_desc = models.CharField(max_length=40)

    # Dónde ocurrió la transacción. El SIFEN lo pide aparte del domicilio del
    # vendedor porque no tienen por qué coincidir: se le puede comprar en el
    # local a alguien que vive en otra ciudad.
    lugar_transaccion = models.CharField(max_length=255)
    departamento_transaccion = models.PositiveSmallIntegerField()
    departamento_transaccion_desc = models.CharField(max_length=40)
    distrito_transaccion = models.PositiveIntegerField()
    distrito_transaccion_desc = models.CharField(max_length=40)
    ciudad_transaccion = models.PositiveIntegerField()
    ciudad_transaccion_desc = models.CharField(max_length=40)

    class Meta:
        db_table = 'fe_datos_autofactura'
        verbose_name = 'datos de autofactura'
        verbose_name_plural = 'datos de autofactura'

    def __str__(self):
        return f'Autofactura a {self.nombre_vendedor}'


class ItemAutofactura(models.Model):
    """
    Un renglón de la autofactura.

    Existe porque los ítems de los otros documentos salen del pedido, y una
    autofactura no tiene pedido: lo que se compró no está en el catálogo del
    local ni pasó por el stock. Se escribe a mano.

    No mueve inventario a propósito. Comprarle mercadería a un particular
    puede o no entrar al stock vendible, y eso es una decisión de depósito,
    no una consecuencia automática del comprobante.
    """
    documento = models.ForeignKey(
        'DocumentoElectronico', on_delete=models.CASCADE,
        related_name='items_autofactura')

    descripcion = models.CharField(max_length=120)
    cantidad = models.DecimalField(
        max_digits=12, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))])
    precio_unitario = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))])
    # La autofactura es a un no contribuyente: la operación no genera crédito
    # fiscal y va exenta. Se deja configurable porque el campo existe en el
    # XML, pero el default es el caso real.
    tasa_iva = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'fe_items_autofactura'
        ordering = ['id']

    def __str__(self):
        return f'{self.cantidad} × {self.descripcion}'

    @property
    def subtotal(self):
        return (self.cantidad * self.precio_unitario).quantize(Decimal('1'))

