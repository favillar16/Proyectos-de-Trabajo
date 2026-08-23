"""
Numeración de comprobantes en el formato que exige la DNIT: EEE-PPP-NNNNNNN.

Hoy el sistema numera con Pago.numero_ticket = 'T-<timestamp>-<pedido_id>'
(apps/caja/models.py). Eso sirve para un ticket interno, pero **no es un
número de comprobante válido** para ninguna factura, ni en papel con
timbrado ni electrónica. Este módulo es el reemplazo.

Reglas que impone la DNIT y que el timestamp no cumplía:

  · Formato fijo establecimiento(3)-punto de expedición(3)-número(7).
  · Correlativo **sin saltos** dentro de cada punto de expedición. Un salto
    hay que justificarlo ante la DNIT, así que el número se asigna recién
    cuando el comprobante se emite de verdad, nunca "por las dudas".
  · Nunca se repite, ni siquiera si dos cajas cobran en el mismo segundo —
    de ahí el select_for_update() en SecuenciaComprobante.siguiente().
"""
import re

LARGO_ESTABLECIMIENTO = 3
LARGO_PUNTO_EXPEDICION = 3
LARGO_NUMERO = 7
NUMERO_MAXIMO = 10 ** LARGO_NUMERO - 1   # 9.999.999 por punto de expedición

_FORMATO = re.compile(r'^(\d{3})-(\d{3})-(\d{7})$')


class NumeracionInvalida(ValueError):
    """El número de comprobante no tiene el formato EEE-PPP-NNNNNNN."""


def formatear(establecimiento, punto_expedicion, numero) -> str:
    """Arma 'EEE-PPP-NNNNNNN' a partir de los tres componentes."""
    numero = int(numero)
    if not 1 <= numero <= NUMERO_MAXIMO:
        raise NumeracionInvalida(
            f'El número {numero} se sale del rango 1..{NUMERO_MAXIMO} del '
            f'punto de expedición. Hay que habilitar uno nuevo en la DNIT.')
    return (f'{int(establecimiento):0{LARGO_ESTABLECIMIENTO}d}-'
            f'{int(punto_expedicion):0{LARGO_PUNTO_EXPEDICION}d}-'
            f'{numero:0{LARGO_NUMERO}d}')


def descomponer(numero_completo: str) -> tuple[str, str, int]:
    """Parte 'EEE-PPP-NNNNNNN' en (establecimiento, punto, numero)."""
    m = _FORMATO.match((numero_completo or '').strip())
    if not m:
        raise NumeracionInvalida(
            f'Número de comprobante mal formado: {numero_completo!r}. '
            f'Se espera EEE-PPP-NNNNNNN, por ejemplo 001-001-0000001.')
    est, punto, num = m.groups()
    return est, punto, int(num)


def es_valido(numero_completo: str) -> bool:
    """True si respeta el formato. No lanza."""
    return bool(_FORMATO.match((numero_completo or '').strip()))
