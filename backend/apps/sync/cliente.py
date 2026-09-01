"""
Cliente HTTP mínimo para hablar con el otro nodo.

Usa `urllib` de la biblioteca estándar y no `requests` a propósito: este
sistema corre en equipos sin internet, donde agregar una dependencia significa
acordarse de instalarla a mano en cada máquina el día que se reinstala. Lo que
hace falta acá —un POST con JSON y un POST multipart— entra en unas pocas
líneas.
"""
import json
import mimetypes
import uuid
from urllib import error, request

TIMEOUT = 30


class ErrorDeNodo(Exception):
    """El otro nodo contestó algo que no esperábamos, o no contestó."""


def _abrir(peticion):
    try:
        with request.urlopen(peticion, timeout=TIMEOUT) as respuesta:
            cuerpo = respuesta.read().decode('utf-8')
            return json.loads(cuerpo) if cuerpo else {}
    except error.HTTPError as e:
        detalle = e.read().decode('utf-8', errors='replace')[:400]
        raise ErrorDeNodo(f'HTTP {e.code}: {detalle}') from e
    except error.URLError as e:
        raise ErrorDeNodo(f'No se pudo conectar: {e.reason}') from e
    except json.JSONDecodeError as e:
        raise ErrorDeNodo(f'Respuesta que no es JSON: {e}') from e


def enviar_json(url, token, cuerpo):
    datos = json.dumps(cuerpo, ensure_ascii=False).encode('utf-8')
    peticion = request.Request(url, data=datos, method='POST', headers={
        'Content-Type': 'application/json; charset=utf-8',
        'X-Sync-Token': token,
    })
    return _abrir(peticion)


def pedir_json(url, token):
    peticion = request.Request(url, method='GET', headers={'X-Sync-Token': token})
    return _abrir(peticion)


def enviar_archivo(url, token, ruta_relativa, contenido, nombre_archivo):
    """POST multipart con un campo de texto ("ruta") y el archivo."""
    borde = f'----OgaPora{uuid.uuid4().hex}'
    tipo = mimetypes.guess_type(nombre_archivo)[0] or 'application/octet-stream'
    salto = b'\r\n'

    partes = [
        f'--{borde}'.encode(),
        b'Content-Disposition: form-data; name="ruta"',
        b'',
        ruta_relativa.encode('utf-8'),
        f'--{borde}'.encode(),
        f'Content-Disposition: form-data; name="archivo"; filename="{nombre_archivo}"'.encode('utf-8'),
        f'Content-Type: {tipo}'.encode(),
        b'',
        contenido,
        f'--{borde}--'.encode(),
        b'',
    ]
    cuerpo = salto.join(partes)

    peticion = request.Request(url, data=cuerpo, method='POST', headers={
        'Content-Type': f'multipart/form-data; boundary={borde}',
        'X-Sync-Token': token,
    })
    return _abrir(peticion)
