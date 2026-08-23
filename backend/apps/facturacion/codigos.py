"""
Tablas de códigos del SIFEN y traducción desde los valores que ya usa el
sistema.

Todo lo que el SIFEN recibe es numérico y codificado. El resto del sistema
trabaja con strings legibles ('efectivo', 'contado', 'admin'), que son los
que ve la vendedora en pantalla. Este módulo es el único lugar donde se
traduce de uno al otro: si mañana la DNIT cambia un código, se cambia acá y
no hay que tocar caja, ventas ni el frontend.

⚠️ Los valores son los del Manual Técnico del SIFEN, pero hay que
contrastarlos contra la versión vigente antes del lanzamiento — la DNIT
publica revisiones y algún código puede haberse movido. Ver
docs/facturacion_electronica.md §"Pendientes de verificar".
"""

# ─── Tipo de documento electrónico (campo iTiDE) ─────────────────────────────
# El negocio hoy solo emite facturas. Los otros quedan listados porque la nota
# de crédito hace falta apenas se anule una venta ya facturada.
TIPO_DE_FACTURA            = 1
TIPO_DE_NOTA_CREDITO       = 5
TIPO_DE_NOTA_DEBITO        = 6
TIPO_DE_NOTA_REMISION      = 7

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

# ─── Naturaleza del receptor (campo iNatRec) ─────────────────────────────────
RECEPTOR_CONTRIBUYENTE    = 1   # tiene RUC
RECEPTOR_NO_CONTRIBUYENTE = 2   # consumidor final, se identifica con CI

# ─── Tipo de operación (campo iTiOpe) ────────────────────────────────────────
OPERACION_B2B = 1   # a otro contribuyente
OPERACION_B2C = 2   # a consumidor final
OPERACION_B2G = 3   # al Estado

# ─── Tipo de documento de identidad del receptor (campo iTipIDRec) ───────────
# Solo aplica cuando el receptor NO es contribuyente (no tiene RUC).
IDENTIDAD_CEDULA_PY  = 1
IDENTIDAD_PASAPORTE  = 3
IDENTIDAD_INNOMINADO = 5   # venta a consumidor final sin identificar

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


def naturaleza_receptor(ruc: str) -> int:
    """
    Contribuyente si trae RUC, no contribuyente si no.

    Se decide por la presencia del RUC y no por Cliente.tipo, porque una
    persona física puede tener RUC y una venta de mostrador puede no
    identificar a nadie.
    """
    return RECEPTOR_CONTRIBUYENTE if (ruc or '').strip() else RECEPTOR_NO_CONTRIBUYENTE


def tipo_operacion(ruc: str) -> int:
    """B2B si el receptor tiene RUC, B2C si es consumidor final."""
    return OPERACION_B2B if (ruc or '').strip() else OPERACION_B2C


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
