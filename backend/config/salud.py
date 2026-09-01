"""
Identificación del nodo — cómo los clientes encuentran al servidor.

El local no tiene acceso al panel del router, así que no se puede reservar
una IP por DHCP: la dirección de la PC servidor se fija desde la propia PC
(`fijar_ip.ps1`) y puede cambiar si se reemplaza o resetea el router. Para
que nada quede atado a un número, todos los clientes (tablets, notebook,
scripts de sync) buscan al servidor probando candidatos —nombre mDNS,
nombre NetBIOS, última IP conocida, barrido de la subred— y confirman que
dieron con el equipo correcto pidiendo este endpoint.

Es deliberadamente público y sin autenticación: solo dice "acá vive Oga
Porã", nada más. No expone datos del negocio.
"""
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.utils import timezone


@never_cache
def salud(request):
    """Responde la identidad del nodo. Usado como sonda de descubrimiento."""
    return JsonResponse({
        'sistema':     'oga-pora',
        'rol':         settings.NODO['rol'],
        'nombre':      settings.NODO['nombre'],
        'red_wifi':    settings.NODO['red_wifi'],
        'api':         'v1',
        'hora':        timezone.localtime().isoformat(),
    })
