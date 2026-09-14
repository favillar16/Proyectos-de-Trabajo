"""
Cliente del sidecar Node que habla con el SIFEN.

Por qué hay un sidecar: firmar el XML y abrir un TLS mutuo con certificado
son cosas que en Python-sobre-Windows exigen `xmlsec`, que es binario nativo
y difícil de instalar. La DNIT publica librerías de referencia en Node
(`facturacionelectronicapy-*`) que ya resuelven todo eso, y la PC servidor ya
tiene Node instalado para Vite. Ver docs/facturacion_electronica.md §3.

Este módulo es la frontera: acá adentro se conoce el contrato HTTP con el
sidecar, y afuera solo se ven diccionarios y excepciones de Python.

Se usa `urllib` de la biblioteca estándar y no `requests`, por la misma razón
que `apps/sync/cliente.py`: agregar una dependencia significa acordarse de
instalarla a mano en cada equipo el día que se reinstala, y lo que hace falta
acá es un POST con JSON.

⚠️ El sidecar todavía no existe. Este módulo define el contrato que tendrá
que cumplir; está escrito primero a propósito, para que el lado Node se
escriba contra algo ya probado en vez de al revés.
"""
import json
import logging
from urllib import error, request

from django.conf import settings

logger = logging.getLogger(__name__)


class ErrorSidecar(Exception):
    """
    No se pudo hablar con el sidecar, o el sidecar falló.

    Es **reintentable**: el sidecar caído, un timeout o un corte de red no
    dicen nada sobre el documento. El worker lo vuelve a intentar.
    """


class RechazoSifen(Exception):
    """
    El SIFEN procesó el documento y lo rechazó.

    **No es reintentable**: reenviar lo mismo da el mismo rechazo. Hay que
    corregir el documento y emitir uno nuevo.
    """

    def __init__(self, mensaje, *, codigo='', respuesta=''):
        super().__init__(mensaje)
        self.codigo = codigo
        self.respuesta = respuesta


def _config() -> dict:
    return getattr(settings, 'SIFEN', {})


def _url(ruta: str) -> str:
    base = _config().get('sidecar_url', '').rstrip('/')
    if not base:
        raise ErrorSidecar(
            'SIFEN_SIDECAR_URL está vacío: no se sabe dónde está el sidecar.')
    return f'{base}/{ruta.lstrip("/")}'


def _postear(ruta: str, cuerpo: dict) -> dict:
    """
    POST con JSON al sidecar. Devuelve el JSON de respuesta.

    Todo lo que salga mal en el transporte se traduce a ErrorSidecar, que es
    la señal de "reintentá después".
    """
    datos = json.dumps(cuerpo, ensure_ascii=False, default=str).encode('utf-8')
    peticion = request.Request(_url(ruta), data=datos, method='POST', headers={
        'Content-Type': 'application/json; charset=utf-8',
    })
    timeout = _config().get('timeout_seg', 30)

    try:
        with request.urlopen(peticion, timeout=timeout) as respuesta:
            crudo = respuesta.read().decode('utf-8')
        return json.loads(crudo) if crudo else {}
    except error.HTTPError as e:
        detalle = e.read().decode('utf-8', errors='replace')[:800]
        raise ErrorSidecar(f'El sidecar respondió HTTP {e.code}: {detalle}') from e
    except error.URLError as e:
        raise ErrorSidecar(
            f'No se pudo conectar al sidecar en {_url(ruta)}: {e.reason}. '
            f'¿Está levantado?') from e
    except json.JSONDecodeError as e:
        raise ErrorSidecar(f'El sidecar devolvió algo que no es JSON: {e}') from e
    except TimeoutError as e:
        raise ErrorSidecar(f'El sidecar no respondió en {timeout}s.') from e


def _exigir(respuesta: dict, clave: str, ruta: str) -> str:
    valor = respuesta.get(clave)
    if not valor:
        raise ErrorSidecar(
            f'El sidecar contestó {ruta} sin el campo {clave!r}: '
            f'{str(respuesta)[:300]}')
    return valor


# ─── Operaciones ─────────────────────────────────────────────────────────────

def generar_xml(params: dict, data: dict) -> str:
    """
    Arma el XML del DE. No necesita certificado.

    Es la única operación que se puede probar de punta a punta sin tener la
    firma, así que conviene usarla como primer chequeo de que el sidecar está
    bien montado.
    """
    respuesta = _postear('xml', {
        'params': params,
        'data': data,
        # xmlgen marca el XML como de prueba según este flag. No es cosmético:
        # el ambiente de test de la DNIT lo exige.
        'test': _config().get('ambiente', 'test') != 'produccion',
    })
    return _exigir(respuesta, 'xml', 'xml')


def firmar_xml(xml: str) -> str:
    """
    Firma el XML con el certificado del emisor.

    El certificado y su clave los lee el sidecar de su propia configuración;
    no viajan en la petición. Es a propósito: cuanto menos circule la clave
    del .p12, mejor.
    """
    respuesta = _postear('firmar', {'xml': xml})
    return _exigir(respuesta, 'xml', 'firmar')


def generar_qr(xml_firmado: str) -> str:
    """
    Devuelve el XML con el QR incorporado (campo dCarQR).

    El QR se calcula con el CSC, que el sidecar también tiene configurado.
    """
    respuesta = _postear('qr', {'xml': xml_firmado})
    return _exigir(respuesta, 'xml', 'qr')


def enviar(xml_firmado: str) -> dict:
    """
    Transmite el DE al SIFEN por el web service sincrónico.

    Devuelve un dict con al menos: estado, codigo, mensaje, y el crudo de la
    respuesta. Si el SIFEN rechaza, lanza RechazoSifen — que el worker NO
    reintenta.
    """
    respuesta = _postear('enviar', {'xml': xml_firmado})

    estado = (respuesta.get('estado') or '').lower()
    codigo = str(respuesta.get('codigo') or '')
    mensaje = respuesta.get('mensaje') or ''
    crudo = respuesta.get('respuesta') or json.dumps(respuesta, ensure_ascii=False)

    if estado == 'rechazado':
        raise RechazoSifen(
            f'El SIFEN rechazó el documento ({codigo}): {mensaje}',
            codigo=codigo, respuesta=crudo)
    if estado not in ('aprobado', 'aprobado_con_observaciones', 'enviado'):
        # Algo que no entendemos: se trata como problema de transporte y se
        # reintenta, en vez de dar el documento por perdido.
        raise ErrorSidecar(
            f'Respuesta de envío inesperada del sidecar: {str(respuesta)[:300]}')

    return {
        'estado': estado,
        'codigo': codigo,
        'mensaje': mensaje,
        'respuesta': crudo,
    }


def consultar(cdc: str) -> dict:
    """Consulta el estado de un DTE ya transmitido, por su CDC."""
    return _postear('consultar', {'cdc': cdc})


def enviar_evento(tipo: str, data: dict) -> dict:
    """
    Manda un evento (cancelación, inutilización, conformidad...).

    `tipo` es el nombre del evento tal como lo nombra la librería
    ('cancelacion', 'inutilizacion', ...) y `data` el cuerpo que corresponde
    a ese evento. La forma de cada uno está en el README de
    facturacionelectronicapy-xmlgen.
    """
    return _postear(f'evento/{tipo}', {'data': data})


def salud() -> dict:
    """
    ¿Está vivo el sidecar y tiene el certificado cargado?

    Sirve para el diagnóstico (`verificar_fiscal`) y para que el worker no
    intente transmitir cuando el sidecar todavía no arrancó.
    """
    return _postear('salud', {})
