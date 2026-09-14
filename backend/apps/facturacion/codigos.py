"""
Tablas de códigos del SIFEN y traducción desde los valores que ya usa el
sistema.

Todo lo que el SIFEN recibe es numérico y codificado. El resto del sistema
trabaja con strings legibles ('efectivo', 'contado', 'admin'), que son los
que ve la vendedora en pantalla. Este módulo es el único lugar donde se
traduce de uno al otro: si mañana la DNIT cambia un código, se cambia acá y
no hay que tocar caja, ventas ni el frontend.

Los códigos de este módulo se contrastaron campo por campo contra el Manual
Técnico del SIFEN **versión 150** el 14/09/2026 (tablas inline de la sección
10.4 y las Codificaciones de la sección 15). Cada bloque anota el campo del
manual del que sale, así que una revisión futura se hace tabla contra tabla.

Lo único que sigue sin cerrarse es el algoritmo del dígito verificador
(módulo 11): el manual §10.2 remite a un PDF aparte cuyo enlace está caído.
Ver docs/facturacion_electronica.md §5.2.
"""

# ─── Tipo de documento electrónico (campo C002 iTiDE) ────────────────────────
# La habilitación ante la DNIT se pide por los cinco tipos emitibles, así que
# los cinco tienen que poder generarse. Los códigos 2, 3 y 8 los declara el
# manual como "Futuro": el SIFEN todavía no los recibe.
TIPO_DE_FACTURA            = 1
TIPO_DE_AUTOFACTURA        = 4
TIPO_DE_NOTA_CREDITO       = 5
TIPO_DE_NOTA_DEBITO        = 6
TIPO_DE_NOTA_REMISION      = 7

# El campo C003 (dDesTiDE) acompaña obligatoriamente a C002 con la descripción
# textual exacta. No es decorativo: el SIFEN valida que coincida con el código.
DESCRIPCION_TIPO_DE = {
    TIPO_DE_FACTURA:       'Factura electrónica',
    TIPO_DE_AUTOFACTURA:   'Autofactura electrónica',
    TIPO_DE_NOTA_CREDITO:  'Nota de crédito electrónica',
    TIPO_DE_NOTA_DEBITO:   'Nota de débito electrónica',
    TIPO_DE_NOTA_REMISION: 'Nota de remisión electrónica',
}

# ─── Tipo de régimen (Tabla 1 de las Codificaciones) ─────────────────────────
# El negocio no está en ningún régimen especial (turismo, maquila, importador):
# le corresponde el régimen contable común.
REGIMEN_CONTABLE = 8

# ─── Motivo de emisión de nota de crédito / débito (campo E401 iMotEmi) ──────
MOTIVO_DEVOLUCION_Y_AJUSTE = 1
MOTIVO_DEVOLUCION          = 2
MOTIVO_DESCUENTO           = 3
MOTIVO_BONIFICACION        = 4
MOTIVO_CREDITO_INCOBRABLE  = 5
MOTIVO_RECUPERO_COSTO      = 6
MOTIVO_RECUPERO_GASTO      = 7
MOTIVO_AJUSTE_PRECIO       = 8

MOTIVOS_NOTA = {
    MOTIVO_DEVOLUCION_Y_AJUSTE: 'Devolución y Ajuste de precios',
    MOTIVO_DEVOLUCION:          'Devolución',
    MOTIVO_DESCUENTO:           'Descuento',
    MOTIVO_BONIFICACION:        'Bonificación',
    MOTIVO_CREDITO_INCOBRABLE:  'Crédito incobrable',
    MOTIVO_RECUPERO_COSTO:      'Recupero de costo',
    MOTIVO_RECUPERO_GASTO:      'Recupero de gasto',
    MOTIVO_AJUSTE_PRECIO:       'Ajuste de precio',
}

# ─── Nota de remisión electrónica ────────────────────────────────────────────
# Grupo E6 (motivo y responsable) más el grupo E10 (transporte). Son los
# datos que acompañan el traslado de la mercadería; el negocio entrega pisos
# y sanitarios a domicilio, así que el caso normal es "traslado por venta"
# con transporte propio y modalidad terrestre.

# Motivo de emisión (campo E501 iMotEmiNR).
TRASLADO_POR_VENTA           = 1
TRASLADO_POR_CONSIGNACION    = 2
TRASLADO_EXPORTACION         = 3
TRASLADO_POR_COMPRA          = 4
TRASLADO_IMPORTACION         = 5
TRASLADO_POR_DEVOLUCION      = 6
TRASLADO_ENTRE_LOCALES       = 7
TRASLADO_POR_TRANSFORMACION  = 8
TRASLADO_POR_REPARACION      = 9
TRASLADO_EMISOR_MOVIL        = 10
TRASLADO_EXHIBICION          = 11
TRASLADO_FERIAS              = 12
TRASLADO_ENCOMIENDA          = 13

MOTIVOS_TRASLADO = {
    TRASLADO_POR_VENTA:          'Traslado por venta',
    TRASLADO_POR_CONSIGNACION:   'Traslado por consignación',
    TRASLADO_EXPORTACION:        'Exportación',
    TRASLADO_POR_COMPRA:         'Traslado por compra',
    TRASLADO_IMPORTACION:        'Importación',
    TRASLADO_POR_DEVOLUCION:     'Traslado por devolución',
    TRASLADO_ENTRE_LOCALES:      'Traslado entre locales de la empresa',
    TRASLADO_POR_TRANSFORMACION: 'Traslado de bienes por transformación',
    TRASLADO_POR_REPARACION:     'Traslado de bienes por reparación',
    TRASLADO_EMISOR_MOVIL:       'Traslado por emisor móvil',
    TRASLADO_EXHIBICION:         'Exhibición o demostración',
    TRASLADO_FERIAS:             'Participación en ferias',
    TRASLADO_ENCOMIENDA:         'Traslado de encomienda',
}

# Responsable de la emisión de la nota (campo E503 iRespEmiNR).
RESPONSABLE_EMISOR_FACTURA   = 1
RESPONSABLE_POSEEDOR         = 2
RESPONSABLE_TRANSPORTISTA    = 3
RESPONSABLE_DESPACHANTE      = 4
RESPONSABLE_AGENTE_TRANSPORTE = 5

RESPONSABLES_REMISION = {
    RESPONSABLE_EMISOR_FACTURA:    'Emisor de la factura',
    RESPONSABLE_POSEEDOR:          'Poseedor de la factura y bienes',
    RESPONSABLE_TRANSPORTISTA:     'Empresa transportista',
    RESPONSABLE_DESPACHANTE:       'Despachante de Aduanas',
    RESPONSABLE_AGENTE_TRANSPORTE: 'Agente de transporte o intermediario',
}

# Tipo de transporte (campo E901 iTipTrans).
TRANSPORTE_PROPIO  = 1
TRANSPORTE_TERCERO = 2

# Modalidad del transporte (campo E903 iModTrans).
MODALIDAD_TERRESTRE  = 1
MODALIDAD_FLUVIAL    = 2
MODALIDAD_AEREA      = 3
MODALIDAD_MULTIMODAL = 4

MODALIDADES_TRANSPORTE = {
    MODALIDAD_TERRESTRE:  'Terrestre',
    MODALIDAD_FLUVIAL:    'Fluvial',
    MODALIDAD_AEREA:      'Aéreo',
    MODALIDAD_MULTIMODAL: 'Multimodal',
}

# Responsable del costo del flete (campo E905 iRespFlete).
FLETE_EMISOR              = 1
FLETE_RECEPTOR            = 2
FLETE_TERCERO             = 3
FLETE_AGENTE_INTERMEDIARIO = 4
FLETE_TRANSPORTE_PROPIO   = 5

# Tipo de identificación del vehículo (campo E967 dTipIdenVeh).
# Con matrícula (la chapa) es el caso normal de un camión local.
VEHICULO_POR_NUMERO    = 1
VEHICULO_POR_MATRICULA = 2

# ─── Tipo de documento asociado (campo H002 iTipDocAso) ──────────────────────
# Una nota de crédito sobre una factura electrónica referencia su CDC, que es
# el caso "Electrónico". El "Impreso" sería para anular una factura de
# talonario anterior a la facturación electrónica.
DOCUMENTO_ASOCIADO_ELECTRONICO = 1
DOCUMENTO_ASOCIADO_IMPRESO     = 2
DOCUMENTO_ASOCIADO_CONSTANCIA  = 3

# ─── Tipo de emisión (campo iTipEmi) ─────────────────────────────────────────
EMISION_NORMAL       = 1
EMISION_CONTINGENCIA = 2   # se emite sin poder consultar al SIFEN en el momento

# ─── Tipo de transacción (campo iTipTra) ─────────────────────────────────────
TRANSACCION_VENTA_MERCADERIA = 1

# ─── Tipo de impuesto (campo iTImp) ──────────────────────────────────────────
IMPUESTO_IVA = 1

# ─── Condición de la operación (campo iCondOpe) ──────────────────────────────
CONDICION_CONTADO = 1
CONDICION_CREDITO = 2

# Mapea Cliente.condicion_venta / el string que hoy manda la caja.
CONDICION_VENTA = {
    'contado': CONDICION_CONTADO,
    'credito': CONDICION_CREDITO,
    'crédito': CONDICION_CREDITO,
}

# ─── Medio de pago (campo iTiPago) ───────────────────────────────────────────
PAGO_EFECTIVO          = 1
PAGO_TARJETA_CREDITO   = 3
PAGO_TARJETA_DEBITO    = 4
PAGO_TRANSFERENCIA     = 5

# Mapea Pago.MEDIOS (apps/caja/models.py). Las claves son exactamente los
# valores que guarda la columna medio_pago.
MEDIO_PAGO = {
    'efectivo':      PAGO_EFECTIVO,
    'credito':       PAGO_TARJETA_CREDITO,
    'debito':        PAGO_TARJETA_DEBITO,
    'transferencia': PAGO_TRANSFERENCIA,
}

# ─── Pago con tarjeta (grupo E620 gPagTarCD) ─────────────────────────────────
# Este grupo NO es opcional: el manual dice "se activa si E606 = 3 o 4", o sea
# siempre que el cobro sea con tarjeta de crédito o débito. De sus campos, la
# denominación (E621), su descripción (E622) y la forma de procesamiento
# (E626) son obligatorios; el resto —procesadora, código de autorización,
# titular, últimos cuatro dígitos— son opcionales para el SIFEN, aunque en la
# práctica el comercio los quiere para poder conciliar contra el resumen de
# la procesadora.
TARJETA_VISA             = 1
TARJETA_MASTERCARD       = 2
TARJETA_AMERICAN_EXPRESS = 3
TARJETA_MAESTRO          = 4
TARJETA_PANAL            = 5
TARJETA_CABAL            = 6
TARJETA_OTRA             = 99

DENOMINACION_TARJETA = {
    TARJETA_VISA:             'Visa',
    TARJETA_MASTERCARD:       'Mastercard',
    TARJETA_AMERICAN_EXPRESS: 'American Express',
    TARJETA_MAESTRO:          'Maestro',
    TARJETA_PANAL:            'Panal',
    TARJETA_CABAL:            'Cabal',
}

# Forma de procesamiento del pago (campo E626 iForProPa).
PROCESAMIENTO_POS              = 1
PROCESAMIENTO_PAGO_ELECTRONICO = 2   # compras por internet
PROCESAMIENTO_OTRO             = 9

# Medios de pago que obligan a declarar el grupo de tarjeta.
MEDIOS_CON_TARJETA = (PAGO_TARJETA_CREDITO, PAGO_TARJETA_DEBITO)


def descripcion_tarjeta(denominacion: int, descripcion_libre: str = '') -> str:
    """
    Texto del campo E622, que el SIFEN valida contra el código E621.

    Para el código 99 ("Otro") el manual pide que se informe la denominación
    real en texto, así que ahí sí manda lo que cargó la cajera.
    """
    if denominacion == TARJETA_OTRA:
        return (descripcion_libre or 'Otro').strip()[:20]
    return DENOMINACION_TARJETA.get(denominacion, 'Otro')


# ─── Naturaleza del receptor (campo iNatRec) ─────────────────────────────────
RECEPTOR_CONTRIBUYENTE    = 1   # tiene RUC
RECEPTOR_NO_CONTRIBUYENTE = 2   # consumidor final, se identifica con CI

# ─── Tipo de operación (campo iTiOpe) ────────────────────────────────────────
OPERACION_B2B = 1   # a otro contribuyente
OPERACION_B2C = 2   # a consumidor final
OPERACION_B2G = 3   # al Estado

# ─── Tipo de contribuyente del receptor (campo D205 iTiContRec) ──────────────
# Obligatorio cuando el receptor ES contribuyente (D201 = 1); no se informa
# cuando no lo es. Ojo que no es lo mismo que el tipo de contribuyente del
# EMISOR, que va en el dígito 25 del CDC.
RECEPTOR_PERSONA_FISICA   = 1
RECEPTOR_PERSONA_JURIDICA = 2

# ─── Tipo de documento de identidad del receptor (campo D208 iTipIDRec) ──────
# Solo aplica cuando el receptor NO es contribuyente (no tiene RUC).
#
# El pasaporte estaba en 3, que es el código de la cédula extranjera. Estos
# valores no se usaban todavía en ningún lado, así que el error nunca llegó a
# un DE — pero habría salido a la luz recién como rechazo del SIFEN.
IDENTIDAD_CEDULA_PY            = 1
IDENTIDAD_PASAPORTE            = 2
IDENTIDAD_CEDULA_EXTRANJERA    = 3
IDENTIDAD_CARNET_RESIDENCIA    = 4
IDENTIDAD_INNOMINADO           = 5   # venta a consumidor final sin identificar
IDENTIDAD_TARJETA_DIPLOMATICA  = 6
IDENTIDAD_OTRO                 = 9

# ─── Afectación tributaria del IVA (campo iAfecIVA) ──────────────────────────
IVA_GRAVADO   = 1   # gravado al 10% o al 5%
IVA_EXONERADO = 2
IVA_EXENTO    = 3
IVA_GRAVADO_PARCIAL = 4

# Tasas vigentes en Paraguay. El rubro del negocio (pisos, cerámicos,
# sanitarios) va todo al 10%, pero la tasa se guarda por variante porque el
# SIFEN la exige ítem por ítem y no admite un único IVA global.
TASA_10 = 10
TASA_5  = 5
TASA_0  = 0

TASAS_VALIDAS = (TASA_10, TASA_5, TASA_0)


# ─── Traductores ─────────────────────────────────────────────────────────────

def codigo_medio_pago(medio: str) -> int:
    """Traduce Pago.medio_pago al código iTiPago. Default: efectivo."""
    return MEDIO_PAGO.get((medio or '').strip().lower(), PAGO_EFECTIVO)


def codigo_condicion_venta(condicion: str) -> int:
    """Traduce 'contado'/'credito' al código iCondOpe. Default: contado."""
    return CONDICION_VENTA.get((condicion or '').strip().lower(), CONDICION_CONTADO)


def es_ruc(identificacion: str) -> bool:
    """
    ¿El número que cargó la cajera es un RUC, o es una cédula?

    No alcanza con que venga algo: la pantalla de caja pide **"RUC/CI"** y
    acepta las dos cosas. Si una cédula se declarara como `dRucRec`, el SIFEN
    validaría su dígito verificador, no cerraría, y rechazaría la factura —
    todas las facturas a consumidor final identificado con cédula.

    El criterio es el DV: en Paraguay el RUC de una persona física es su
    cédula MÁS el dígito verificador, así que "4123456-7" es un RUC y
    "4123456" es una cédula. Validar el módulo 11 separa los dos casos.
    """
    from .ruc import es_valido
    return es_valido(identificacion or '')


def naturaleza_receptor(ruc: str) -> int:
    """
    Contribuyente si lo que vino es un RUC válido; si no, no contribuyente.

    Se decide por el número y no por Cliente.tipo, porque una persona física
    puede tener RUC y una venta de mostrador puede no identificar a nadie.
    """
    return RECEPTOR_CONTRIBUYENTE if es_ruc(ruc) else RECEPTOR_NO_CONTRIBUYENTE


def tipo_operacion(ruc: str) -> int:
    """B2B si el receptor es contribuyente, B2C si es consumidor final."""
    return OPERACION_B2B if es_ruc(ruc) else OPERACION_B2C


def desglosar_iva(total_con_iva, tasa: int):
    """
    Separa base gravada e IVA de un monto que YA incluye el impuesto.

    En Paraguay el precio de góndola es con IVA incluido, así que el sistema
    guarda precios finales y acá se hace la separación al revés:
    iva = total * tasa / (100 + tasa).

    Devuelve (base_gravada, iva) como Decimal redondeado a guaraníes enteros,
    que es como se declara: el guaraní no tiene centavos.
    """
    from decimal import Decimal, ROUND_HALF_UP

    total = Decimal(str(total_con_iva))
    if tasa not in TASAS_VALIDAS:
        raise ValueError(f'Tasa de IVA no válida para el SIFEN: {tasa}')
    if tasa == TASA_0:
        return total.quantize(Decimal('1'), rounding=ROUND_HALF_UP), Decimal('0')

    iva = (total * Decimal(tasa) / Decimal(100 + tasa)).quantize(
        Decimal('1'), rounding=ROUND_HALF_UP)
    base = (total - iva).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return base, iva
