"""
Cobro con cheque: validación de los datos del papel que recibe la caja.

Es el equivalente de `pos.py` para el otro medio de pago que el SIFEN no
deja declarar "a secas". La diferencia con la tarjeta es que acá no hay
ningún dispositivo del otro lado: el cheque es un papel y los datos los lee
la cajera de ese papel. Por eso esto no es un driver sino una validación.

─── Qué exige el SIFEN ─────────────────────────────────────────────────────

El grupo E630 (`gPagCheq`) del Manual Técnico se activa si E606 = 2, o sea
en todo cobro con cheque, y sus dos campos son obligatorios:

    E631 dNumCheq  A(8)     número, con ceros a la izquierda hasta ocho
    E632 dBcoEmi   A(4-20)  banco emisor

El mínimo de cuatro caracteres del banco importa en la práctica: "BNF" tiene
tres y el documento volvería rechazado, así que se guarda el nombre del
banco y no la sigla.

─── Por qué se exige siempre, y no solo al facturar ────────────────────────

Con la tarjeta la regla es distinta a propósito: los datos se piden solo si
la venta se factura y el SIFEN está prendido, para no agregarle trabajo a la
cajera por una obligación fiscal que todavía no rige (ver apps/caja/pos.py).

Con el cheque no aplica ese razonamiento. La tarjeta ya fue autorizada por
la terminal y el voucher queda impreso: el cobro está hecho aunque el
sistema no anote nada. Un cheque, en cambio, es una promesa de pago, y si
la caja no registra banco y número el local se queda con un papel que
después no puede cruzar contra el extracto ni reclamar. Eso es del negocio,
no del DNIT, y rige con el SIFEN apagado igual.
"""
from dataclasses import dataclass, field
from datetime import date

from django.utils.dateparse import parse_date

from apps.facturacion import codigos


class ErrorCheque(Exception):
    """Los datos del cheque no alcanzan para registrarlo."""


@dataclass
class DatosChequeValidados:
    """Lo que la caja necesita guardar de un cheque, ya normalizado."""
    numero: str = ''
    banco: str = ''
    titular: str = ''
    fecha_cobro: date = None
    crudo: dict = field(default_factory=dict)

    @property
    def es_diferido(self) -> bool:
        from django.utils import timezone
        return bool(self.fecha_cobro and self.fecha_cobro > timezone.localdate())


def validar(datos: dict) -> DatosChequeValidados:
    """
    Revisa los datos que cargó la cajera y los deja como los quiere el SIFEN.

    Valida en serio y no por prolijidad: para cuando alguien note que falta
    el número, el cliente ya se fue y el cheque es un papel más en el cajón.
    """
    datos = datos or {}

    numero_crudo = str(datos.get('numero') or '').strip()
    solo_digitos = ''.join(c for c in numero_crudo if c.isdigit())
    if not solo_digitos:
        raise ErrorCheque(
            'Falta el número del cheque. Es lo único que identifica al papel '
            'que queda en caja, y el SIFEN lo exige en toda venta con cheque.')
    if len(solo_digitos) > codigos.LARGO_NUMERO_CHEQUE:
        raise ErrorCheque(
            f'El número de cheque no puede tener más de '
            f'{codigos.LARGO_NUMERO_CHEQUE} dígitos.')

    banco = ' '.join(str(datos.get('banco') or '').split())
    if len(banco) < codigos.LARGO_MIN_BANCO:
        raise ErrorCheque(
            'Falta el banco emisor del cheque, con un nombre de al menos '
            f'{codigos.LARGO_MIN_BANCO} letras. El SIFEN no acepta siglas '
            'cortas: va "Banco Nacional de Fomento", no "BNF".')

    fecha_cobro = _fecha(datos.get('fecha_cobro'))

    return DatosChequeValidados(
        numero=codigos.numero_cheque_sifen(solo_digitos),
        banco=banco[:codigos.LARGO_MAX_BANCO],
        titular=' '.join(str(datos.get('titular') or '').split())[:60],
        fecha_cobro=fecha_cobro,
        crudo=dict(datos),
    )


def _fecha(valor):
    """La fecha de cobro del cheque diferido, si vino. Vacía = a la vista."""
    if valor in (None, ''):
        return None
    if isinstance(valor, date):
        return valor
    fecha = parse_date(str(valor))
    if fecha is None:
        raise ErrorCheque(
            f'La fecha de cobro del cheque ({valor!r}) no se entiende. '
            f'Va en formato AAAA-MM-DD, o vacía si el cheque es a la vista.')
    return fecha


def requiere_datos_de_cheque(medio_pago: str) -> bool:
    """
    ¿Este medio de pago obliga a declarar el grupo de cheque del SIFEN?

    Se decide traduciendo primero al código del SIFEN, para no repetir acá la
    lista de medios que ya vive en `codigos.MEDIO_PAGO` — igual que
    `pos.requiere_datos_de_tarjeta()`.
    """
    return codigos.codigo_medio_pago(medio_pago) in codigos.MEDIOS_CON_CHEQUE
