"""
apps/productos/codigo_barras.py

Códigos EAN-13 internos, para la mercadería que no trae código de fábrica.

Este módulo NO decide cómo se guarda ni cómo se busca un código: de eso se
encarga `Variante.codigo_barras` y el endpoint
`productos/variantes/por-codigo-barras/`. Acá está solo la aritmética de GS1,
que hace falta para dos cosas:

1. **Generar** un código propio cuando el producto no trae ninguno. Buena parte
   del rubro (sanitarios, griferías, accesorios) llega sin EAN impreso, y sin
   código no hay nada que escanear. Se usa el **prefijo 200**, el rango que
   GS1 reserva para uso interno de un comercio: nunca colisiona con un código
   real, porque ningún fabricante puede registrarse ahí.
   → `python manage.py asignar_codigos_barras`

2. **Reconocer** si un código es un EAN-13 válido, para saber con qué
   simbología imprimir la etiqueta: EAN-13 si el dígito verificador cierra,
   Code128 en cualquier otro caso. El lector FTX-LC123BH5 lee las dos.
   → `apps/caja/impresora_a4.py`
"""

# Rango GS1 de uso interno del comercio. No se asigna a ningún fabricante.
PREFIJO_INTERNO = '200'


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


def es_ean_valido(codigo) -> bool:
    """True si el código es un EAN-13, EAN-8 o UPC-A con el DV correcto."""
    codigo = (codigo or '').strip()
    if not codigo.isdigit() or len(codigo) not in (8, 12, 13):
        return False
    return digito_verificador_ean(codigo[:-1]) == codigo[-1]


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


def es_interno(codigo) -> bool:
    """True si el código lo generó este sistema (prefijo GS1 de uso interno)."""
    codigo = (codigo or '').strip()
    return len(codigo) == 13 and codigo.startswith(PREFIJO_INTERNO)
