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

El sidecar vive en `sidecar/` y se levanta con `npm start` (ver su README).
Este módulo se escribió ANTES que él, a propósito, para que el lado Node se
escribiera contra un contrato ya probado en vez de al revés.
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
        if e.code == 422:
            # 422 es el código con el que el sidecar avisa que el problema es
            # del pedido o de la configuración —falta el certificado, el CDC
            # no tiene 44 dígitos, xmlgen rechazó el payload—, no de la red.
            # Reintentarlo diez veces daría diez veces lo mismo y gastaría la
            # cola tapando el error real. Se trata como terminal, igual que un
            # rechazo del SIFEN. Ver sidecar/servidor.js, "mapeo de errores".
            raise RechazoSifen(
                f'El sidecar rechazó el pedido: {detalle}',
                codigo='SIDECAR', respuesta=detalle) from e
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
        # Se manda el ambiente para que el sidecar no tenga que adivinarlo.
        #
        # ⚠️ Ojo con lo que este flag NO hace: en xmlgen `config.test` no marca
        # el documento como de prueba. Es andamiaje de la NT 013 (2023), cuando
        # una fórmula del IVA entró en test un mes antes que en producción; las
        # dos fechas pasaron y hoy los dos caminos calculan igual. Lo que
        # realmente distingue un documento de prueba es la leyenda obligatoria
        # de la Guía de Pruebas §2, y esa la pone `payload._marcar_como_prueba()`.
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


def enviar_lote(xmls_firmados: list) -> dict:
    """
    Transmite varios DE de una vez por el web service asincrónico.

    **No devuelve si los aprobó.** El SIFEN contesta un número de lote y lo
    procesa cuando puede; el resultado se pide después con `consultar_lote()`.
    Por eso acá no hay `RechazoSifen`: todavía no hay nada que rechazar. Lo
    único que puede fallar en este paso es la recepción del lote.

    Devuelve un dict con `lote` (el número) y el crudo de la respuesta.
    """
    respuesta = _postear('enviarLote', {'xmls': list(xmls_firmados)})

    numero = (respuesta.get('lote')
              or respuesta.get('numeroLote')
              or respuesta.get('dProtConsLote'))
    if not numero:
        # Sin número de lote no hay forma de preguntar después por el
        # resultado: los documentos quedarían transmitidos y huérfanos. Es
        # preferible tratarlo como fallo de transporte y reintentar.
        raise ErrorSidecar(
            f'El SIFEN recibió el lote pero no devolvió su número. '
            f'Respuesta: {str(respuesta)[:300]}')

    return {
        'lote': str(numero),
        'codigo': str(respuesta.get('codigo') or ''),
        'mensaje': respuesta.get('mensaje') or '',
        'respuesta': respuesta.get('respuesta')
                     or json.dumps(respuesta, ensure_ascii=False),
    }


def consultar(cdc: str) -> dict:
    """Consulta el estado de un DTE ya transmitido, por su CDC."""
    return _postear('consultar', {'cdc': cdc})


def consultar_lote(numero_lote) -> dict:
    """
    Pide el resultado de un lote ya enviado.

    El SIFEN puede contestar que todavía lo está procesando; eso no es un
    error, es el flujo normal del asincrónico. Quien llame tiene que estar
    preparado para volver a preguntar más tarde.
    """
    return _postear('consultarLote', {'lote': str(numero_lote)})


def geografia(filtro: dict = None) -> dict:
    """
    Las tablas geográficas de la DNIT (departamentos, distritos, ciudades).

    Vienen adentro de `xmlgen`, así que esto **no sale a internet ni usa el
    certificado**: es un archivo de la librería que el sidecar ya tiene.
    """
    return _postear('geografia', filtro or {})


def consultar_ruc(ruc: str) -> dict:
    """
    Consulta un RUC en el padrón de la DNIT.

    Dos usos: es uno de los web services que la Guía de Pruebas exige
    ejercitar, y sirve para validar el RUC del cliente **antes** de emitir,
    en vez de enterarse por un rechazo.
    """
    return _postear('consultarRuc', {'ruc': ruc})


def enviar_evento(tipo: str, data: dict, params: dict = None) -> dict:
    """
    Manda un evento (cancelación, inutilización, conformidad...).

    `tipo` es el nombre del evento tal como lo nombra la librería
    ('cancelacion', 'inutilizacion', ...) y `data` el cuerpo que corresponde
    a ese evento. La forma de cada uno está en el README de
    facturacionelectronicapy-xmlgen.

    `params` son los datos del emisor, los mismos que lleva un DE. Los pide
    `xmlgen.generateXMLEvento*`, que recibe `(id, params, data)`. Si no se
    pasan se arman de la configuración vigente — que es lo correcto para un
    evento, porque un evento se emite hoy, no se retransmite del pasado.
    """
    from . import payload as _payload
    return _postear(f'evento/{tipo}', {
        'params': params if params is not None else _payload.construir_params(),
        'data': data,
    })


def salud() -> dict:
    """
    ¿Está vivo el sidecar y tiene el certificado cargado?

    Sirve para el diagnóstico (`verificar_fiscal`) y para que el worker no
    intente transmitir cuando el sidecar todavía no arrancó.
    """
    return _postear('salud', {})
