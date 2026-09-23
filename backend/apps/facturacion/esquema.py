"""
Validación del XML contra el XSD del SIFEN, antes de transmitir.

El SIFEN valida el schema antes que nada: si el XML está mal armado, el
documento vuelve rechazado y hay que leer un código de error para entender
qué campo era. Validar del lado de acá convierte ese viaje de ida y vuelta en
un error inmediato, con el nombre del campo. Durante la batería de la Guía de
Pruebas —del orden de 130 documentos— eso cambia bastante el trabajo.

**Es opcional a propósito**, y se apaga solo si le falta cualquiera de las dos
patas:

  1. **El XSD.** La DNIT lo publica como `Estructura_DE xsd`, en un `.rar`,
     en <https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica>. No está
     versionado en el repo. Se descomprime donde sea y se apunta
     `SIFEN_XSD_PATH` del `.env` al `.xsd` principal, que se llama
     **`siRecepDE_v150.xsd`** (el nombre lo declara el propio XML que arma
     `xmlgen`, en su `xsi:schemaLocation`).

     ⚠️ **Ojo con cuál se baja.** El 23/09/2026 se probó el archivo que la
     página publica bajo el nombre «Estructura_DE xsd» y **es de 2018**:
     no tiene `targetNamespace`, y sus grupos se llaman `gCiODE`, `gDTim` y
     `gCamOC`, nombres que no aparecen ni una vez en el Manual V150 (que usa
     `gOpeDE`, `gTimb`, `gDatGralOpe`). Apuntarle `SIFEN_XSD_PATH` haría que
     **todo** documento vuelva «no cumple el esquema», porque falla ya en el
     elemento raíz. Por eso `_schema()` revisa el namespace antes de
     aceptarlo — ver `NAMESPACE_SIFEN` más abajo.
  2. **La librería `xmlschema`.** Es Python puro (no necesita compilador ni
     DLLs, a diferencia de lxml) pero es una dependencia más, y este sistema
     corre en la PC de una tienda que alguien va a tener que reinstalar algún
     día. Está en `requirements-dev.txt`, no en `requirements.txt`: hace falta
     para la campaña de pruebas, no para vender.

Con cualquiera de las dos ausentes, `validar()` no hace nada y lo dice una
vez en el log. Nunca frena una emisión por no poder validar: no poder
chequear no es lo mismo que estar mal.
"""
import logging
import os
import threading

from django.conf import settings

logger = logging.getLogger(__name__)

# El namespace de los DE del SIFEN. Es lo que separa el XSD de la V150 del
# borrador de 2018 que la DNIT todavía publica con el mismo nombre: aquel no
# declara `targetNamespace`, así que sus elementos no están en ninguno.
NAMESPACE_SIFEN = 'http://ekuatia.set.gov.py/sifen/xsd'

# Se arma una sola vez: compilar un XSD grande es caro y el worker transmite
# de a muchos. El lock evita que dos hilos lo compilen a la vez.
_cache = {'schema': None, 'intentado': False}
_candado = threading.Lock()


class XmlInvalido(ValueError):
    """El XML no cumple el esquema del SIFEN."""


def ruta_xsd() -> str:
    return str(getattr(settings, 'SIFEN', {}).get('xsd_path') or '').strip()


def disponible() -> bool:
    """¿Se puede validar? Sin ruido: se usa para decidir, no para avisar."""
    return _schema() is not None


def _schema():
    if _cache['intentado']:
        return _cache['schema']

    with _candado:
        if _cache['intentado']:
            return _cache['schema']
        _cache['intentado'] = True

        ruta = ruta_xsd()
        if not ruta:
            logger.info(
                'Validación contra XSD desactivada: SIFEN_XSD_PATH está vacío. '
                'Ver apps/facturacion/esquema.py para activarla.')
            return None
        if not os.path.exists(ruta):
            logger.warning(
                'SIFEN_XSD_PATH apunta a "%s", que no existe. No se valida '
                'contra el esquema.', ruta)
            return None

        try:
            import xmlschema
        except ImportError:
            logger.warning(
                'Hay un XSD configurado pero falta la librería "xmlschema". '
                'Instalar con: pip install -r requirements-dev.txt')
            return None

        try:
            schema = xmlschema.XMLSchema(ruta)
        except Exception as e:
            # Un XSD que no compila es un problema de instalación, no del
            # documento. Se avisa y se sigue sin validar.
            logger.warning('No se pudo cargar el XSD %s: %s', ruta, e)
            return None

        # Un XSD de otra versión compila perfecto y después rechaza todo. Es
        # el peor final posible —parece que valida y en realidad tumba la
        # emisión entera—, así que se descarta acá y no en el primer
        # documento.
        if schema.target_namespace != NAMESPACE_SIFEN:
            logger.warning(
                'El XSD de %s no es el del SIFEN: declara el namespace %r en '
                'vez de %r. Probablemente sea el «Estructura_DE xsd» viejo, '
                'anterior a la V150. No se valida contra él: haría rechazar '
                'todos los documentos. Hace falta siRecepDE_v150.xsd.',
                ruta, schema.target_namespace or '(ninguno)', NAMESPACE_SIFEN)
            return None

        _cache['schema'] = schema
        logger.info('XSD del SIFEN cargado desde %s', ruta)
        return _cache['schema']


def validar(xml: str):
    """
    Lanza `XmlInvalido` si el XML no cumple el esquema.

    No hace nada si la validación no está disponible. Eso es deliberado: que
    falte el XSD no puede impedir facturar.
    """
    schema = _schema()
    if schema is None or not xml:
        return

    try:
        errores = list(schema.iter_errors(xml))
    except Exception as e:
        # Error del validador, no del documento. No se convierte en rechazo.
        logger.warning('El validador de XSD falló: %s', e)
        return

    if not errores:
        return

    # Los primeros, no todos: un XML mal armado puede tirar cientos y el
    # mensaje tiene que entrar en el campo de respuesta del documento.
    detalle = ' | '.join(
        f'{getattr(e, "path", "") or "?"}: {getattr(e, "reason", None) or e}'
        for e in errores[:5])
    if len(errores) > 5:
        detalle += f' | (y {len(errores) - 5} error(es) más)'

    raise XmlInvalido(
        f'El XML no cumple el esquema del SIFEN ({len(errores)} '
        f'problema(s)): {detalle}')


def reiniciar_cache():
    """Para los tests: obliga a releer la configuración."""
    with _candado:
        _cache['schema'] = None
        _cache['intentado'] = False
