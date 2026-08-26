"""
Bandera de "estoy aplicando cambios que vinieron del otro nodo".

Sin esto el sync entra en un rebote infinito: el servidor aplica un cambio que
mandó la notebook, el signal lo anota como cambio local, y en la vuelta
siguiente se lo devuelve a la notebook, que vuelve a anotarlo, y así.

Es thread-local porque daphne atiende varios pedidos a la vez y la bandera solo
puede valer para el hilo que está aplicando el lote.
"""
import threading
from contextlib import contextmanager

_local = threading.local()


def aplicando_remoto():
    return getattr(_local, 'aplicando', False)


@contextmanager
def aplicacion_remota():
    """Dentro de este bloque, los signals de sync no anotan nada."""
    anterior = getattr(_local, 'aplicando', False)
    _local.aplicando = True
    try:
        yield
    finally:
        _local.aplicando = anterior
