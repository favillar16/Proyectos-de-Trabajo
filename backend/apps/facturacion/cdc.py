"""
CDC — Código de Control del Documento Electrónico (44 dígitos).

Es la identidad del DE en el SIFEN: va impreso en el KuDE, es lo que
codifica el QR y es la clave con la que se consulta el documento. Se calcula
**localmente**, sin consultar al SIFEN — eso es lo que permite imprimir el
comprobante en el acto aunque el local esté sin internet, y transmitir el DE
después (ver la cola en models.py).

Composición:

    posición  largo  campo
    1– 2        2    tipo de documento electrónico (01 = factura)
    3–10        8    RUC del emisor, sin el dígito verificador
    11          1    dígito verificador del RUC del emisor
    12–14       3    establecimiento
    15–17       3    punto de expedición
    18–24       7    número del documento
    25          1    tipo de contribuyente (1 física, 2 jurídica)
    26–33       8    fecha de emisión, AAAAMMDD
    34          1    tipo de emisión (1 normal, 2 contingencia)
    35–43       9    código de seguridad aleatorio
    44          1    dígito verificador del CDC
                ──
                44

⚠️ La composición y el módulo 11 del DV son los del Manual Técnico del
SIFEN, pero hay que contrastarlos contra la versión vigente antes de emitir
en producción. El chequeo concreto está en
docs/facturacion_electronica.md §"Pendientes de verificar".
"""
import secrets
from datetime import date

from . import codigos
from .ruc import validar as validar_ruc

LARGO_CDC = 44
LARGO_CODIGO_SEGURIDAD = 9


class CdcInvalido(ValueError):
    """El CDC no tiene el largo o el dígito verificador correcto."""


# Reglas del campo dCodSeg, Manual Técnico del SIFEN v150, §10.3:
#   · número positivo de 9 dígitos, aleatorio y NO SECUENCIAL
#   · rango entre 000000001 y 999999999  (ojo: el cero NO es válido)
#   · distinto para cada DE
#   · no debe ser igual al número de documento (campo dNumDoc)
#   · si tiene menos de 9 dígitos, completar con ceros a la izquierda
CODIGO_SEGURIDAD_MIN = 1
CODIGO_SEGURIDAD_MAX = 10 ** LARGO_CODIGO_SEGURIDAD - 1   # 999.999.999


def generar_codigo_seguridad(numero_documento=None) -> str:
    """
    Código de seguridad aleatorio de 9 dígitos, según §10.3 del Manual
    Técnico.

    Se usa secrets y no random: es lo que impide que alguien pueda adivinar
    el CDC de una factura ajena y consultarla en el portal del SIFEN.

    `numero_documento` es el dNumDoc del comprobante. Si se pasa, se evita
    generar un código igual a él, que el manual prohíbe expresamente.
    """
    prohibido = None
    if numero_documento is not None:
        try:
            prohibido = int(numero_documento)
        except (TypeError, ValueError):
            prohibido = None

    while True:
        # randbelow(N) da 0..N-1; se desplaza para que el mínimo sea 1 y
        # nunca salga 000000000, que está fuera del rango permitido.
        valor = CODIGO_SEGURIDAD_MIN + secrets.randbelow(
            CODIGO_SEGURIDAD_MAX - CODIGO_SEGURIDAD_MIN + 1)
        if valor != prohibido:
            return f'{valor:0{LARGO_CODIGO_SEGURIDAD}d}'


# Rango de pesos del módulo 11. Los pesos se aplican de derecha a izquierda
# y vuelven a PESO_MIN al pasar PESO_MAX.
#
# ⚠️ Ojo con subir PESO_MAX a 11: un peso de 11 hace que ese dígito NO aporte
# nada al checksum (11·d ≡ 0 mod 11), o sea que se puede alterar sin que el
# DV lo note. Con un cuerpo de 43 dígitos el ciclo pasa cuatro veces por el
# 11 y deja 8 dígitos sin protección — está medido, hay un test que lo
# verifica (tests/test_cdc.py, ProteccionDelDigitoVerificadorTests).
#
# Por eso acá el ciclo llega hasta 9 y no hasta 11. En ruc.py sí llega a 11,
# pero ahí es inofensivo: el RUC tiene 8 dígitos y los pesos nunca pasan de 9.
PESO_MIN = 2
PESO_MAX = 9


def calcular_dv(cuerpo: str) -> int:
    """Dígito verificador módulo 11 de los primeros 43 dígitos del CDC."""
    if len(cuerpo) != LARGO_CDC - 1 or not cuerpo.isdigit():
        raise CdcInvalido(
            f'El cuerpo del CDC debe ser {LARGO_CDC - 1} dígitos, vino {cuerpo!r}')

    total = 0
    peso = PESO_MIN
    for digito in reversed(cuerpo):
        total += int(digito) * peso
        peso += 1
        if peso > PESO_MAX:
            peso = PESO_MIN

    resto = total % 11
    return 0 if resto < 2 else 11 - resto


def generar(*, ruc_emisor: str, establecimiento: str, punto_expedicion: str,
            numero: str, tipo_contribuyente: int, fecha_emision: date,
            tipo_documento: int = codigos.TIPO_DE_FACTURA,
            tipo_emision: int = codigos.EMISION_NORMAL,
            codigo_seguridad: str | None = None) -> str:
    """
    Arma el CDC completo. Devuelve los 44 dígitos como string.

    codigo_seguridad se pasa solo para recalcular un CDC ya emitido (por
    ejemplo al reimprimir); en una emisión nueva se deja en None para que se
    genere uno aleatorio.
    """
    base, dv_ruc = validar_ruc(ruc_emisor)
    if len(base) > 8:
        raise CdcInvalido(f'El RUC del emisor no entra en 8 dígitos: {ruc_emisor}')

    codigo_seguridad = codigo_seguridad or generar_codigo_seguridad(numero)
    if len(codigo_seguridad) != LARGO_CODIGO_SEGURIDAD or not codigo_seguridad.isdigit():
        raise CdcInvalido(
            f'El código de seguridad debe ser {LARGO_CODIGO_SEGURIDAD} dígitos')
    if not CODIGO_SEGURIDAD_MIN <= int(codigo_seguridad) <= CODIGO_SEGURIDAD_MAX:
        raise CdcInvalido(
            f'El código de seguridad {codigo_seguridad} está fuera del rango '
            f'permitido (000000001..999999999), Manual Técnico §10.3.')

    cuerpo = (
        f'{int(tipo_documento):02d}'
        f'{base:0>8}'
        f'{dv_ruc:d}'
        f'{int(establecimiento):03d}'
        f'{int(punto_expedicion):03d}'
        f'{int(numero):07d}'
        f'{int(tipo_contribuyente):d}'
        f'{fecha_emision:%Y%m%d}'
        f'{int(tipo_emision):d}'
        f'{codigo_seguridad}'
    )
    if len(cuerpo) != LARGO_CDC - 1:
        raise CdcInvalido(
            f'El cuerpo del CDC quedó en {len(cuerpo)} dígitos y debe ser '
            f'{LARGO_CDC - 1}. Revisar los datos fiscales del .env.')

    return cuerpo + str(calcular_dv(cuerpo))


def es_valido(cdc: str) -> bool:
    """True si el CDC tiene 44 dígitos y el DV cierra. No lanza."""
    cdc = (cdc or '').strip()
    if len(cdc) != LARGO_CDC or not cdc.isdigit():
        return False
    try:
        return calcular_dv(cdc[:-1]) == int(cdc[-1])
    except CdcInvalido:
        return False


def descomponer(cdc: str) -> dict:
    """
    Parte un CDC en sus campos. Sirve para el KuDE y para depurar un rechazo
    del SIFEN sin tener que contar dígitos a mano.
    """
    if not es_valido(cdc):
        raise CdcInvalido(f'CDC inválido: {cdc!r}')
    return {
        'tipo_documento':     int(cdc[0:2]),
        'ruc_emisor':         cdc[2:10].lstrip('0'),
        'dv_ruc_emisor':      int(cdc[10]),
        'establecimiento':    cdc[11:14],
        'punto_expedicion':   cdc[14:17],
        'numero':             cdc[17:24],
        'tipo_contribuyente': int(cdc[24]),
        'fecha_emision':      f'{cdc[25:29]}-{cdc[29:31]}-{cdc[31:33]}',
        'tipo_emision':       int(cdc[33]),
        'codigo_seguridad':   cdc[34:43],
        'dv':                 int(cdc[43]),
    }


def formatear_legible(cdc: str) -> str:
    """Agrupa el CDC de a 4 para imprimirlo en el KuDE sin que sea ilegible."""
    cdc = (cdc or '').strip()
    return ' '.join(cdc[i:i + 4] for i in range(0, len(cdc), 4))
