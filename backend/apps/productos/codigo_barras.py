"""
apps/productos/codigo_barras.py

Códigos de barras de las variantes, para el lector FTX-LC123BH5.

El lector es un HID: se comporta como un teclado y "tipea" el código seguido
de un Enter. No necesita driver ni configuración en el backend — todo lo que
hace falta acá es (1) guardar el código contra la variante y (2) poder
resolverlo a una variante en una sola consulta exacta.

Dos orígenes de código conviven:

1. **De fábrica.** La caja del porcelanato ya trae un EAN-13 impreso. Es el
   caso ideal: se escanea al recibir la mercadería y se guarda tal cual.
2. **Interno.** La mayoría de los sanitarios y accesorios del rubro vienen sin
   código. Para esos el sistema genera un EAN-13 propio con prefijo 200-299,
   que es el rango que GS1 reserva para uso interno de un comercio: nunca
   colisiona con un código real de fábrica porque ningún fabricante puede
   registrarse en ese rango. Se imprime en etiqueta con la Epson L1250
   (ver apps/caja/etiquetas.py).

Se aceptan además códigos que no son EAN-13 (Code128, CODE39, QR), porque
el FTX-LC123BH5 los lee y algún proveedor los usa. La validación solo exige
que el dígito verificador cierre cuando el código *parece* un EAN-13 o un
UPC-A: un EAN-13 mal tipeado a mano es el error que de verdad ocurre, y
dejarlo pasar significa que el escaneo nunca encuentra el producto.
"""
import re

from django.core.exceptions import ValidationError

# Rango GS1 de uso interno del comercio. No se asigna a ningún fabricante.
PREFIJO_INTERNO = '200'

# Lo que el lector puede entregar: dígitos, letras, guiones y puntos.
# Se rechazan espacios y caracteres de control porque son casi siempre basura
# de un escaneo cortado a la mitad.
_PATRON_VALIDO = re.compile(r'^[A-Za-z0-9\-\.\/\+]{4,32}$')


def normalizar(codigo) -> str:
    """
    Deja el código como se guarda: sin espacios alrededor y en mayúsculas.

    El lector puede mandar un CR/LF al final según cómo esté configurado el
    sufijo; se limpia acá para que no llegue nunca a la base.
    """
    return (codigo or '').strip().strip('\r\n').upper()


def digito_verificador_ean(cuerpo: str) -> str:
    """
    Dígito verificador de un EAN/UPC a partir del cuerpo sin él.

    Es el algoritmo estándar de GS1: se suman los dígitos alternando pesos
    1 y 3 *desde la derecha*, y el verificador es lo que falta para la
    decena siguiente.

    Ojo con el orden de los pesos: el peso 3 arranca en el dígito de más a la
    derecha del cuerpo, no en el primero. Calcularlo al revés da un código que
    parece válido pero que ningún lector acepta.
    """
    if not cuerpo.isdigit():
        raise ValueError('El cuerpo de un EAN solo puede tener dígitos.')
    suma = 0
    for i, ch in enumerate(reversed(cuerpo)):
        peso = 3 if i % 2 == 0 else 1
        suma += int(ch) * peso
    return str((10 - suma % 10) % 10)


def es_ean_valido(codigo: str) -> bool:
    """True si el código es un EAN-13, EAN-8 o UPC-A con el DV correcto."""
    codigo = normalizar(codigo)
    if not codigo.isdigit() or len(codigo) not in (8, 12, 13):
        return False
    return digito_verificador_ean(codigo[:-1]) == codigo[-1]


def parece_ean(codigo: str) -> bool:
    """
    True si el código tiene la pinta de un EAN/UPC (solo dígitos y largo
    de EAN-8, UPC-A o EAN-13), independientemente de si el DV cierra.
    """
    codigo = normalizar(codigo)
    return codigo.isdigit() and len(codigo) in (8, 12, 13)


def generar_ean_interno(numero: int) -> str:
    """
    EAN-13 interno para una variante que no trae código de fábrica.

    `numero` es normalmente el id de la variante. Entra en los 9 dígitos que
    quedan entre el prefijo 200 y el verificador, así que el tope real es
    999.999.999 variantes: no se va a alcanzar nunca en este negocio.
    """
    if numero < 0 or numero > 999_999_999:
        raise ValueError(f'Número fuera del rango del EAN-13 interno: {numero}')
    cuerpo = f'{PREFIJO_INTERNO}{numero:09d}'
    return cuerpo + digito_verificador_ean(cuerpo)


def es_interno(codigo: str) -> bool:
    """True si el código lo generó este sistema (prefijo GS1 de uso interno)."""
    codigo = normalizar(codigo)
    return len(codigo) == 13 and codigo.startswith(PREFIJO_INTERNO)


def validar_codigo_barras(codigo):
    """
    Validador del campo `Variante.codigo_barras`.

    Vacío es válido: la mayoría del catálogo arranca sin código y se van
    cargando a medida que entra mercadería.
    """
    codigo = normalizar(codigo)
    if not codigo:
        return

    if not _PATRON_VALIDO.match(codigo):
        raise ValidationError(
            'El código de barras solo puede tener letras, números, guiones y '
            'puntos, y entre 4 y 32 caracteres. Si lo escaneaste y salió esto, '
            'volvé a escanearlo: probablemente se cortó a la mitad.'
        )

    if parece_ean(codigo) and not es_ean_valido(codigo):
        esperado = digito_verificador_ean(codigo[:-1])
        raise ValidationError(
            f'El código {codigo} tiene largo de EAN pero el dígito verificador '
            f'no cierra (termina en {codigo[-1]} y debería terminar en '
            f'{esperado}). Revisá si se tipeó mal algún dígito.'
        )
