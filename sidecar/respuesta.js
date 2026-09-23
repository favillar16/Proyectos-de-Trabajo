/**
 * Traducción de la respuesta del SIFEN al contrato que espera Django.
 *
 * `apps/facturacion/sifen_client.py` espera `{estado, codigo, mensaje,
 * respuesta}` y decide con eso lo más importante del diseño: si el documento
 * se reintenta o se da por rechazado para siempre. Traducir mal acá tiene una
 * consecuencia asimétrica — marcar como "rechazado" un documento que el SIFEN
 * nunca vio es perder una venta ya cobrada; reintentar de más solo gasta
 * intentos. Ante la duda, esto devuelve algo que el cliente trata como
 * reintentable.
 *
 * La forma de la respuesta está tomada del Manual Técnico V150, no deducida:
 *
 *   §9.1  rRetEnviDe → rProtDe → gResProc → {dEstRes, dProtAut, dCodRes, dMsgRes}
 *   §9.5.3 rRetEnviEventoDe → gResProcEVe → {dEstRes, dProtAut, id, gResProc}
 *
 * Dos detalles del manual que hay que respetar y son fáciles de pasar por alto:
 *
 *  1. `gResProc` tiene ocurrencia **1-100**: un rechazo trae varios motivos.
 *     `setapi` parsea con `explicitArray: false`, así que un solo mensaje llega
 *     como objeto y varios como arreglo. Quedarse con el primero perdería los
 *     demás, que es justo lo que hace falta para entender por qué rechazaron.
 *  2. Los valores de `dEstRes` son texto en castellano y con tilde
 *     ("Aprobado con observación"). Se comparan sin tildes y sin distinguir
 *     mayúsculas, porque de eso no conviene depender.
 */

/** "Aprobado con observación" → "aprobado con observacion" */
function normalizarTexto(valor) {
  return (valor ?? '')
    .toString()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .trim()
    .toLowerCase();
}

/**
 * Saca el prefijo de namespace de todas las claves, recursivamente.
 * `ns2:rRetEnviDe` → `rRetEnviDe`. El prefijo lo elige el servidor y puede
 * cambiar sin aviso; el nombre del campo no.
 */
function sinNamespaces(nodo) {
  if (Array.isArray(nodo)) return nodo.map(sinNamespaces);
  if (nodo === null || typeof nodo !== 'object') return nodo;
  const salida = {};
  for (const [clave, valor] of Object.entries(nodo)) {
    salida[clave.includes(':') ? clave.split(':').pop() : clave] =
      sinNamespaces(valor);
  }
  return salida;
}

/**
 * Junta todos los valores de un campo, esté donde esté en el árbol.
 *
 * Se busca en profundidad en vez de recorrer una ruta fija porque las tres
 * respuestas que consume el sistema (recepción de DE, recepción de evento y
 * consulta) anidan los mismos campos a distinta profundidad. El nombre del
 * campo es lo estable.
 */
function juntar(nodo, campo, acumulado = []) {
  if (Array.isArray(nodo)) {
    for (const item of nodo) juntar(item, campo, acumulado);
    return acumulado;
  }
  if (nodo === null || typeof nodo !== 'object') return acumulado;
  for (const [clave, valor] of Object.entries(nodo)) {
    if (clave === campo) {
      if (Array.isArray(valor)) {
        for (const v of valor) {
          if (v !== null && typeof v === 'object') juntar(v, campo, acumulado);
          else if (v !== undefined && v !== '') acumulado.push(v);
        }
      } else if (valor !== null && typeof valor === 'object') {
        juntar(valor, campo, acumulado);
      } else if (valor !== undefined && valor !== '') {
        acumulado.push(valor);
      }
    } else {
      juntar(valor, campo, acumulado);
    }
  }
  return acumulado;
}

const primero = (lista) => (lista.length ? String(lista[0]) : '');

/**
 * Códigos de resultado que significan "el SIFEN lo recibió pero todavía no lo
 * resolvió" (capítulo 12 del manual). El lote asincrónico contesta 0300 y no
 * trae `dEstRes`: no es aprobación ni rechazo, es acuse de recibo.
 */
const CODIGOS_RECIBIDO = new Set(['0300', '0301', '0302']);

/**
 * @param {object} crudo respuesta ya parseada que devuelve setapi
 * @returns {{estado: string, codigo: string, mensaje: string,
 *            protocolo: string, respuesta: string}}
 */
function interpretar(crudo) {
  const limpio = sinNamespaces(crudo);
  const serializado = JSON.stringify(limpio);

  const estados = juntar(limpio, 'dEstRes');
  const codigos = juntar(limpio, 'dCodRes').concat(juntar(limpio, 'dCodResLot'));
  const mensajes = juntar(limpio, 'dMsgRes').concat(juntar(limpio, 'dMsgResLot'));
  const protocolos = juntar(limpio, 'dProtAut');

  // Todos los códigos y mensajes, no solo el primero: un rechazo trae hasta
  // 100 motivos y cada uno es una pista distinta de qué corregir.
  const mensaje = mensajes
    .map((m, i) => (codigos[i] ? `[${codigos[i]}] ${m}` : String(m)))
    .join(' | ');

  let estado;
  const declarado = normalizarTexto(primero(estados));

  if (declarado.startsWith('aprobado con observacion')) {
    estado = 'aprobado_con_observaciones';
  } else if (declarado.startsWith('aprobado')) {
    // Si alguno de los resultados vino rechazado, el documento NO está
    // aprobado por más que el primero lo diga.
    estado = estados.some((e) => normalizarTexto(e).startsWith('rechazado'))
      ? 'rechazado'
      : 'aprobado';
  } else if (declarado.startsWith('rechazado')) {
    estado = 'rechazado';
  } else if (codigos.some((c) => CODIGOS_RECIBIDO.has(String(c).padStart(4, '0')))) {
    estado = 'enviado';
  } else {
    // No se entendió la respuesta. Se devuelve tal cual y el cliente de Django
    // lo trata como problema de transporte, o sea reintentable. Es la opción
    // segura: dar por rechazado lo que no se entendió sería peor.
    estado = 'desconocido';
  }

  return {
    estado,
    codigo: primero(codigos),
    mensaje: mensaje || primero(estados),
    protocolo: primero(protocolos),
    // Número de lote. Solo viene en la respuesta del envío asincrónico
    // (`rResEnviLoteDe`), y es el único dato con el que después se puede
    // preguntar por el resultado: sin esto los documentos quedarían
    // transmitidos y huérfanos. El nombre del campo está verificado contra la
    // librería de la DNIT, que lo manda así al consultar
    // (`<dProtConsLote>` en SET.js).
    lote: primero(juntar(limpio, 'dProtConsLote')),
    respuesta: serializado,
  };
}

/**
 * Interpreta la consulta de resultado de un lote.
 *
 * Se diferencia de `interpretar()` en que acá **no alcanza con aplanar**: la
 * respuesta trae un resultado por documento y hay que poder decir cuál
 * corresponde a cuál. Aplanar mezclaría los estados de todos y el sistema no
 * sabría a qué DE marcar aprobado.
 *
 * ⚠️ La forma exacta de `rResEnviConsLoteDe` está en el XSD
 * (`SiResultLoteDE_v150.xsd`), que no está versionado en el repo. Por eso
 * esto **no recorre una ruta fija**: busca en el árbol cualquier nodo que
 * tenga a la vez un identificador de 44 dígitos —el CDC— y un `dEstRes`. Si
 * el SIFEN anida distinto de lo esperado, sigue funcionando; si no encuentra
 * nada, devuelve la lista vacía y el llamador reintenta, que es la salida
 * segura. Cuando se baje el XSD, vale contrastar esto contra él.
 */
function interpretarLote(crudo) {
  const limpio = sinNamespaces(crudo);
  const general = interpretar(crudo);
  const documentos = [];

  const esCdc = (valor) => /^\d{44}$/.test(String(valor || '').trim());

  function recorrer(nodo) {
    if (Array.isArray(nodo)) {
      for (const item of nodo) recorrer(item);
      return;
    }
    if (nodo === null || typeof nodo !== 'object') return;

    // ¿Este nodo es el resultado de UN documento?
    const cdc = [nodo.id, nodo.dCDC, nodo.CDC, nodo.dId]
      .map((v) => (v === null || v === undefined ? '' : String(v).trim()))
      .find(esCdc);

    if (cdc && juntar(nodo, 'dEstRes').length) {
      const estados = juntar(nodo, 'dEstRes');
      const codigos = juntar(nodo, 'dCodRes');
      const mensajes = juntar(nodo, 'dMsgRes');
      const declarado = normalizarTexto(primero(estados));

      let estado = 'desconocido';
      if (declarado.startsWith('aprobado con observacion')) {
        estado = 'aprobado_con_observaciones';
      } else if (declarado.startsWith('aprobado')) {
        estado = estados.some((e) => normalizarTexto(e).startsWith('rechazado'))
          ? 'rechazado'
          : 'aprobado';
      } else if (declarado.startsWith('rechazado')) {
        estado = 'rechazado';
      }

      documentos.push({
        cdc,
        estado,
        codigo: primero(codigos),
        mensaje: mensajes
          .map((m, i) => (codigos[i] ? `[${codigos[i]}] ${m}` : String(m)))
          .join(' | ') || primero(estados),
        protocolo: primero(juntar(nodo, 'dProtAut')),
      });
      return; // no seguir bajando: ya se consumió este subárbol
    }

    for (const valor of Object.values(nodo)) recorrer(valor);
  }

  recorrer(limpio);
  return { ...general, documentos };
}

module.exports = {
  interpretar,
  interpretarLote,
  sinNamespaces,
  juntar,
  normalizarTexto,
};
