"""
Validación de RUC paraguayo — dígito verificador módulo 11.

El SIFEN rechaza el documento entero si el RUC del emisor o del receptor
viene con el dígito verificador mal. Conviene validarlo al cargarlo en la
pantalla de caja y no descubrirlo recién cuando el DE vuelve rechazado.

⚠️ El algoritmo de abajo es el módulo 11 estándar que usa la DNIT, pero hay
que contrastarlo contra el Manual Técnico antes del lanzamiento: probar con
el RUC real del negocio y verificar que dé el DV que figura en la cédula
tributaria. Ver docs/facturacion_electronica.md §"Pendientes de verificar".
"""
import re

# El RUC se escribe de mil formas en el mostrador: "80012345-6", "80012345 6",
# "800123456". Se normaliza todo a (base, dv) antes de validar.
_NO_DIGITOS = re.compile(r'[^0-9]')


class RucInvalido(ValueError):
    """El RUC no tiene el formato o el dígito verificador correcto."""


def calcular_dv(base: str) -> int:
    """
    Dígito verificador módulo 11 de la base del RUC (el RUC sin el DV).

    Se recorre de derecha a izquierda multiplicando por pesos crecientes 2..11,
    reiniciando a 2 al pasarse. Resto 0 o 1 ⇒ DV 0.
    """
    base = _NO_DIGITOS.sub('', base)
    if not base:
        raise RucInvalido('El RUC no tiene dígitos')

    total = 0
    peso = 2
    for digito in reversed(base):
        total += int(digito) * peso
        peso += 1
        if peso > 11:
            peso = 2

    resto = total % 11
    return 0 if resto < 2 else 11 - resto


def separar(ruc: str) -> tuple[str, int]:
    """
    Devuelve (base, dv) a partir de un RUC escrito de cualquier forma.

    Si el texto trae guión, se respeta lo que el usuario escribió después del
    guión como DV. Si no trae guión, se asume que el último dígito es el DV
    (que es como lo imprime la cédula tributaria).
    """
    texto = (ruc or '').strip()
    if not texto:
        raise RucInvalido('RUC vacío')

    if '-' in texto:
        base, _, dv = texto.rpartition('-')
        base = _NO_DIGITOS.sub('', base)
        dv = _NO_DIGITOS.sub('', dv)
        if not base or not dv:
            raise RucInvalido(f'RUC mal formado: {ruc!r}')
        return base, int(dv[0])

    digitos = _NO_DIGITOS.sub('', texto)
    if len(digitos) < 2:
        raise RucInvalido(f'RUC demasiado corto: {ruc!r}')
    return digitos[:-1], int(digitos[-1])


def es_valido(ruc: str) -> bool:
    """True si el dígito verificador coincide. No lanza."""
    try:
        base, dv = separar(ruc)
        return calcular_dv(base) == dv
    except (RucInvalido, ValueError):
        return False


def validar(ruc: str) -> tuple[str, int]:
    """
    Igual que separar(), pero lanza RucInvalido si el DV no coincide.
    Devuelve (base, dv) ya normalizados para armar el CDC.
    """
    base, dv = separar(ruc)
    esperado = calcular_dv(base)
    if esperado != dv:
        raise RucInvalido(
            f'El RUC {ruc} tiene el dígito verificador mal: '
            f'termina en {dv} y debería terminar en {esperado}'
        )
    return base, dv


def formatear(ruc: str) -> str:
    """Normaliza a la forma 'base-dv' que espera el KuDE. No valida el DV."""
    base, dv = separar(ruc)
    return f'{base}-{dv}'
