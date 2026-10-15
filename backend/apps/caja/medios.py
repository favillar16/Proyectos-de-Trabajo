"""
Las líneas de un cobro: con qué medios se pagó y cuánto con cada uno.

Existe por el pago mixto. La propietaria cobra ventas grandes con dos o tres
cheques, o con un cheque y el resto en efectivo, y la caja solo admitía un
medio por cobro. Un cobro sigue siendo **un** `Pago` —un ticket, una
factura—; lo que cambia es que trae una lista de líneas (`PagoMedio`).

Este módulo valida esa lista antes de tocar la base, con la misma lógica que
`cheque.py`: si algo falta, se frena con el cliente todavía en el mostrador.
Las reglas:

  · Las líneas suman exactamente lo que hay que cobrar. Ni de más ni de
    menos: un cobro que no cierra es plata que nadie sabe explicar al
    arqueo.
  · Efectivo, una sola línea. Es la única que puede traer más de lo que
    imputa (`monto_recibido`) y dar vuelto; dos líneas de efectivo no dicen
    nada que una no diga, y harían ambiguo el vuelto.
  · Cada cheque es una línea con sus datos (banco y número, siempre — ver
    cheque.py). Dos cheques son dos líneas.
  · Las tarjetas pasan por la terminal POS solo al facturar con el SIFEN
    prendido, igual que antes (ver pos.py); eso lo hace la vista, que es la
    que conoce el tipo de comprobante.

`desde_request()` acepta también el formato viejo —un solo `medio_pago` con
`monto_recibido`, `datos_cheque`, `datos_tarjeta`—, que es el que siguen
mandando el cobro de un solo medio y cualquier cliente que no se actualizó.
"""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from . import cheque as cheque_mod
from .models import Pago


class ErrorMedios(Exception):
    """Las líneas del cobro no alcanzan para registrarlo."""


@dataclass
class LineaValidada:
    medio: str
    monto: Decimal
    monto_recibido: Decimal = None
    referencia_externa: str = ''
    cheque: 'cheque_mod.DatosChequeValidados' = None
    datos_tarjeta: dict = field(default_factory=dict)

    @property
    def vuelto(self) -> Decimal:
        if self.medio == Pago.MEDIO_EFECTIVO and self.monto_recibido is not None:
            return max(Decimal('0'), self.monto_recibido - self.monto)
        return Decimal('0')


def _decimal(valor, que):
    if valor in (None, ''):
        return None
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError):
        raise ErrorMedios(f'{que} no es un número válido.')


def _gs(valor) -> str:
    return f'Gs. {int(valor):,}'.replace(',', '.')


def desde_request(data, monto_final: Decimal) -> list:
    """
    Las líneas del cobro, validadas, a partir del body de la request.

    `monto_final` es lo que hay que cobrar (ya con el descuento de caja).
    """
    medios_validos = [m[0] for m in Pago.MEDIOS]
    crudas = data.get('medios')

    if not crudas:
        # Formato de un solo medio: la línea es el cobro entero.
        crudas = [{
            'medio':              data.get('medio_pago', ''),
            'monto':              monto_final,
            'monto_recibido':     data.get('monto_recibido'),
            'referencia_externa': data.get('referencia_externa', ''),
            'datos_cheque':       data.get('datos_cheque'),
            'datos_tarjeta':      data.get('datos_tarjeta'),
        }]
    if not isinstance(crudas, list):
        raise ErrorMedios('Los medios de pago vienen en un formato que no se entiende.')

    lineas = []
    for n, cruda in enumerate(crudas, start=1):
        cruda = cruda or {}
        medio = cruda.get('medio', '')
        que = f'Medio {n}' if len(crudas) > 1 else 'El cobro'
        if medio not in medios_validos:
            raise ErrorMedios(f'Medio de pago inválido. Opciones: {medios_validos}')

        monto = _decimal(cruda.get('monto'), f'El monto de {que.lower()}')
        if monto is None or monto < 0 or (len(crudas) > 1 and monto <= 0):
            raise ErrorMedios(f'{que}: falta el monto.')
        if monto != monto.quantize(Decimal('1')):
            raise ErrorMedios(f'{que}: el monto va en guaraníes, sin decimales.')

        linea = LineaValidada(
            medio=medio, monto=monto,
            referencia_externa=str(cruda.get('referencia_externa') or '')[:100],
            datos_tarjeta=cruda.get('datos_tarjeta') or {},
        )

        if medio == Pago.MEDIO_EFECTIVO:
            recibido = _decimal(cruda.get('monto_recibido'), 'El monto recibido')
            if recibido is None:
                raise ErrorMedios('Para pagos en efectivo debés indicar el monto recibido.')
            if recibido < monto:
                raise ErrorMedios(
                    f'El monto recibido en efectivo ({_gs(recibido)}) es menor a lo '
                    f'que se cobra en efectivo ({_gs(monto)}).')
            linea.monto_recibido = recibido

        if cheque_mod.requiere_datos_de_cheque(medio):
            try:
                linea.cheque = cheque_mod.validar(cruda.get('datos_cheque') or {})
            except cheque_mod.ErrorCheque as e:
                prefijo = f'Cheque de {_gs(monto)}: ' if len(crudas) > 1 else ''
                raise ErrorMedios(f'{prefijo}{e}')

        lineas.append(linea)

    if not lineas:
        raise ErrorMedios('Indicá con qué se paga.')

    if sum(1 for l in lineas if l.medio == Pago.MEDIO_EFECTIVO) > 1:
        raise ErrorMedios('El efectivo va en una sola línea: sumá los montos.')

    numeros = [l.cheque.numero for l in lineas if l.cheque is not None]
    if len(numeros) != len(set(numeros)):
        raise ErrorMedios('Hay dos cheques con el mismo número.')

    total = sum(l.monto for l in lineas)
    if total != monto_final:
        falta = monto_final - total
        raise ErrorMedios(
            f'Los medios de pago suman {_gs(total)} y hay que cobrar '
            f'{_gs(monto_final)}: '
            + (f'faltan {_gs(falta)}.' if falta > 0 else f'sobran {_gs(-falta)}.'))

    return lineas


def medio_del_cobro(lineas) -> str:
    """El `Pago.medio_pago`: el medio si es uno solo (aunque sean varios cheques), si no 'mixto'."""
    medios = {l.medio for l in lineas}
    return medios.pop() if len(medios) == 1 else Pago.MEDIO_MIXTO
