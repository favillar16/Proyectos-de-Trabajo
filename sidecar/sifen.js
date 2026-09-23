/**
 * Envoltorio de las librerías que publica la DNIT como referencia.
 *
 * Acá adentro se conoce la firma de cada librería; hacia afuera solo salen
 * strings y objetos planos. Si TIPS-SA cambia una firma, se cambia en este
 * archivo y en ningún otro.
 *
 * Tres cosas que se verificaron leyendo el código de las librerías y que no
 * son obvias desde el README:
 *
 *  1. **`signByNodeJS` tiene que ir en `true`.** Es el último parámetro de
 *     `signXML` y por defecto es falso. Con falso, `xmlsign` usa
 *     `XMLDsigJava`, que busca un JRE con `find-java-home` y hace `exec` de
 *     un `java -classpath ... SignXML`. Eso significaría instalar y mantener
 *     Java en la PC de la tienda, y que la firma dependa de un proceso
 *     externo. Con `true` firma en Node con `xml-crypto` y `node-forge`.
 *     (node_modules/facturacionelectronicapy-xmlsign/dist/index.js)
 *
 *  2. **El certificado se pasa como RUTA, no como contenido.** `PKCS12.js`
 *     hace `fs.readFileSync(file)`. La clave del .p12 nunca sale de este
 *     proceso: Django manda el XML y recibe el XML firmado, y nunca ve el
 *     certificado. Por eso `sifen_client.firmar_xml()` no lo manda.
 *     (node_modules/facturacionelectronicapy-setapi/dist/PKCS12.js)
 *
 *  3. **`setapi` abre un TLS mutuo con ese mismo certificado**: arma un
 *     `https.Agent({cert, key})` con la clave privada del .p12. Es la razón
 *     técnica por la que el certificado necesita `Extended Key Usage:
 *     clientAuth` y no alcanza uno de firma de documentos. Si el prestador
 *     entrega uno sin esa extensión, el handshake falla y no hay forma de
 *     arreglarlo del lado del software.
 *     (node_modules/facturacionelectronicapy-setapi/dist/SET.js, `recibe`)
 */
const xmlgen = require('facturacionelectronicapy-xmlgen').default;
const xmlsign = require('facturacionelectronicapy-xmlsign').default;
const qrgen = require('facturacionelectronicapy-qrgen').default;
const setapi = require('facturacionelectronicapy-setapi').default;

const config = require('./config');
const { interpretar, interpretarLote } = require('./respuesta');

/** Error de configuración o de datos: reintentarlo no cambia nada. */
class ErrorTerminal extends Error {}

/** Contador para el `id` que setapi echa de vuelta en la respuesta. */
let siguienteId = 1;
const nuevoId = () => siguienteId++;

function exigirCertificado() {
  if (!config.certificadoPath) {
    throw new ErrorTerminal(
      'SIFEN_CERT_PATH está vacío en backend/.env: no hay certificado con ' +
      'qué firmar. Ver docs/migracion_ekuatia.md §3.1.');
  }
  if (!config.certificadoDisponible()) {
    throw new ErrorTerminal(
      `No existe el archivo del certificado: ${config.certificadoPath}`);
  }
  if (!config.certificadoPassword) {
    throw new ErrorTerminal(
      'SIFEN_CERT_PASSWORD está vacío: el .p12 no se puede abrir sin la clave.');
  }
}

/** Arma el XML del DE. Es lo único que NO necesita certificado. */
async function generarXml(params, data, esPrueba) {
  if (!params || !data) {
    throw new ErrorTerminal('Faltan "params" o "data" en el pedido.');
  }
  let xml;
  try {
    xml = await xmlgen.generateXMLDE(params, data, { test: Boolean(esPrueba) });
  } catch (e) {
    // Armar el XML es cálculo local puro: no toca la red, no abre archivos,
    // no depende de nada que pueda estar caído un rato. Entonces TODO lo que
    // falle acá es un problema de los datos, y reintentarlo diez veces da
    // diez veces lo mismo. Va como terminal.
    //
    // Sin esta traducción el error salía como 502 y la cola lo reintentaba:
    // una nota de remisión a la que le falta la dirección del chofer se
    // llevaría los diez intentos y recién ahí quedaría visible, con el
    // mensaje enterrado entre reintentos en vez de arriba.
    //
    // `xmlgen` junta todas sus validaciones en un mensaje separado por "; ",
    // así que el error ya viene con la lista completa de lo que falta — no
    // hay que ir corrigiendo de a uno.
    throw new ErrorTerminal(
      `xmlgen rechazó el documento: ${(e && e.message) || e}`);
  }
  verificarXmlSano(xml);
  return xml;
}

/**
 * Revisa que el XML que devolvió xmlgen no tenga agujeros.
 *
 * Hace falta porque **xmlgen no falla cuando le falta un campo**: lo
 * interpola igual y escribe el string "undefined" en el XML. Se descubrió
 * probando el sidecar sin `codigoSeguridadAleatorio`, y el resultado fue un
 * DE aparentemente válido con
 *
 *     <DE Id="0180173107000100100000012202609161undefined3">
 *     <dCodSeg>undefined</dCodSeg>
 *
 * y respuesta de éxito. Ese documento se firmaría, se transmitiría y volvería
 * rechazado con un error del SIFEN que no señala al campo que falta — y como
 * un rechazo es terminal, la venta quedaría sin factura y con un mensaje que
 * no lleva a ninguna parte.
 *
 * Es barato revisarlo acá y el error queda dicho en los términos del problema.
 * `payload.py` hoy manda todos los campos, así que esto es una red, no un
 * parche: protege del día que se agregue un tipo de documento nuevo y se
 * olvide uno.
 */
function verificarXmlSano(xml) {
  if (typeof xml !== 'string' || !xml.includes('<rDE')) {
    throw new ErrorTerminal(
      'xmlgen no devolvió un XML de DE reconocible.');
  }

  if (/>undefined<|="[^"]*undefined[^"]*"|>null</.test(xml)) {
    const campos = [...xml.matchAll(/<(\w+)>(?:undefined|null)<\/\1>/g)]
      .map((m) => m[1]);
    throw new ErrorTerminal(
      'El XML salió con campos en "undefined": xmlgen interpola los datos ' +
      'que faltan en vez de fallar. ' +
      (campos.length ? `Campos afectados: ${campos.join(', ')}. ` : '') +
      'Revisar el payload que arma apps/facturacion/payload.py.');
  }

  // El CDC tiene 44 dígitos exactos (Manual Técnico §10.1). Si xmlgen lo
  // armó corto, algún campo que lo compone vino mal y el documento no se
  // puede consultar ni verificar por QR.
  const id = /<DE Id="([^"]*)"/.exec(xml);
  if (id && !/^\d{44}$/.test(id[1])) {
    throw new ErrorTerminal(
      `El CDC del XML no tiene 44 dígitos: "${id[1]}" (${id[1].length}). ` +
      'Revisar establecimiento, punto de expedición, número, fecha y ' +
      'código de seguridad en el payload.');
  }
}

/** Firma el XML con el .p12 del emisor. */
async function firmar(xml) {
  exigirCertificado();
  return xmlsign.signXML(
    xml, config.certificadoPath, config.certificadoPassword, true);
}

/** Le incorpora al XML firmado el campo dCarQR. */
async function generarQr(xmlFirmado) {
  if (!config.cscId || !config.csc) {
    throw new ErrorTerminal(
      'Falta SIFEN_CSC_ID o SIFEN_CSC en backend/.env: sin el Código de ' +
      'Seguridad del Contribuyente no se puede firmar el QR del KuDE.');
  }
  return qrgen.generateQR(xmlFirmado, config.cscId, config.csc, config.env);
}

/** Transmite el DE por el web service sincrónico. */
async function enviar(xmlFirmado) {
  exigirCertificado();
  const crudo = await setapi.recibe(
    nuevoId(), xmlFirmado, config.env,
    config.certificadoPath, config.certificadoPassword,
    { timeout: config.timeoutMs, debug: config.debug });
  return interpretar(crudo);
}

/** Consulta el estado de un DTE ya transmitido, por su CDC. */
async function consultar(cdc) {
  // El largo del CDC se valida ANTES de mirar el certificado. Los dos errores
  // son terminales, pero el que se reporta tiene que ser el verdadero: si
  // faltara el .p12 y además el CDC estuviera mal, avisar solo del
  // certificado mandaría a buscar el problema al lado equivocado. La
  // validación barata va primero.
  if (!cdc || String(cdc).length !== 44) {
    throw new ErrorTerminal(`El CDC tiene que tener 44 dígitos, vino: ${cdc}`);
  }
  exigirCertificado();
  const crudo = await setapi.consulta(
    nuevoId(), String(cdc), config.env,
    config.certificadoPath, config.certificadoPassword,
    { timeout: config.timeoutMs, debug: config.debug });
  return interpretar(crudo);
}

/**
 * Transmite varios DE de una vez por el web service asincrónico.
 *
 * El SIFEN no contesta si los aprobó: contesta un **número de lote** y lo
 * procesa cuando puede. El resultado se pide después con `consultarLote()`.
 * Por eso esto no es "lo mismo pero más rápido": es un flujo distinto, con
 * dos viajes, y el sistema tiene que guardar el número de lote en el medio.
 *
 * El tope de 50 lo fija el Manual Técnico §7.2 para el lote. Se valida acá
 * —antes de tocar el certificado— porque es un error de programación nuestro,
 * no del SIFEN, y conviene que falle rápido y con un mensaje que lo diga.
 */
async function enviarLote(xmlsFirmados) {
  if (!Array.isArray(xmlsFirmados) || xmlsFirmados.length === 0) {
    throw new ErrorTerminal('El lote no puede ir vacío.');
  }
  if (xmlsFirmados.length > 50) {
    throw new ErrorTerminal(
      `Un lote admite hasta 50 documentos, vinieron ${xmlsFirmados.length}.`);
  }
  exigirCertificado();
  const crudo = await setapi.recibeLote(
    nuevoId(), xmlsFirmados, config.env,
    config.certificadoPath, config.certificadoPassword,
    { timeout: config.timeoutMs, debug: config.debug });
  return interpretar(crudo);
}

/** Pide el resultado de un lote ya enviado, por su número. */
async function consultarLote(numeroLote) {
  const numero = Number(numeroLote);
  if (!Number.isFinite(numero) || numero <= 0) {
    throw new ErrorTerminal(
      `El número de lote tiene que ser un entero positivo, vino: ${numeroLote}`);
  }
  exigirCertificado();
  const crudo = await setapi.consultaLote(
    nuevoId(), numero, config.env,
    config.certificadoPath, config.certificadoPassword,
    { timeout: config.timeoutMs, debug: config.debug });
  // Interpretador propio: la consulta de lote trae un resultado POR
  // documento y hay que poder decir cuál es de cuál.
  return interpretarLote(crudo);
}

/**
 * Consulta un RUC en el padrón de la DNIT.
 *
 * Sirve para dos cosas distintas: es uno de los web services que la Guía de
 * Pruebas exige ejercitar, y —fuera de la habilitación— permite validar el
 * RUC del cliente **al cobrar**, antes de emitir, en vez de descubrir que
 * estaba mal cuando el documento vuelve rechazado.
 *
 * El RUC va sin dígito verificador: es lo que espera el servicio.
 */
async function consultarRuc(ruc) {
  const limpio = String(ruc || '').trim().split('-')[0];
  if (!limpio) {
    throw new ErrorTerminal('Falta el RUC a consultar.');
  }
  exigirCertificado();
  const crudo = await setapi.consultaRUC(
    nuevoId(), limpio, config.env,
    config.certificadoPath, config.certificadoPassword,
    { timeout: config.timeoutMs, debug: config.debug });
  return interpretar(crudo);
}

/**
 * Los eventos que `xmlgen` sabe generar, por el nombre que usa el sistema.
 *
 * Se declaran explícitamente y no se arma el nombre del método por
 * concatenación: un nombre mal escrito tiene que fallar acá, con la lista de
 * los que sí existen, y no producir un `undefined is not a function` en medio
 * de una cancelación.
 */
const GENERADORES_EVENTO = {
  cancelacion: 'generateXMLEventoCancelacion',
  inutilizacion: 'generateXMLEventoInutilizacion',
  conformidad: 'generateXMLEventoConformidad',
  disconformidad: 'generateXMLEventoDisconformidad',
  desconocimiento: 'generateXMLEventoDesconocimiento',
  notificacion: 'generateXMLEventoNotificacion',
  nominacion: 'generateXMLEventoNominacion',
  transporte: 'generateXMLEventoActualizacionDatosTransporte',
};

/** Genera, firma y transmite un evento. */
async function enviarEvento(tipo, params, data) {
  const metodo = GENERADORES_EVENTO[tipo];
  if (!metodo) {
    throw new ErrorTerminal(
      `Evento desconocido: "${tipo}". Los que existen son: ` +
      Object.keys(GENERADORES_EVENTO).join(', '));
  }
  if (!params || !data) {
    throw new ErrorTerminal(
      'Un evento necesita "params" (datos del emisor) y "data".');
  }
  exigirCertificado();

  const id = nuevoId();
  const xml = await xmlgen[metodo](id, params, data,
    { test: config.env === 'test' });
  // Ojo: el evento se firma con signXMLEvento, que firma el nodo `rEve`. Con
  // signXML se firmaría el nodo `DE`, que en un evento no existe.
  const firmado = await xmlsign.signXMLEvento(
    xml, config.certificadoPath, config.certificadoPassword, true);
  const crudo = await setapi.evento(
    id, firmado, config.env,
    config.certificadoPath, config.certificadoPassword,
    { timeout: config.timeoutMs, debug: config.debug });

  const resultado = interpretar(crudo);
  resultado.xml = firmado;
  return resultado;
}

/**
 * Fecha de vencimiento del certificado.
 *
 * Un .p12 vencido frena la facturación entera y no avisa solo: el primer
 * síntoma sería un rechazo del SIFEN a mitad de una jornada de ventas.
 */
async function vencimientoCertificado() {
  exigirCertificado();
  const crudo = await xmlsign.getExpiration(
    config.certificadoPath, config.certificadoPassword, true);

  // `getExpiration` no devuelve una fecha: devuelve
  // `{notBefore, notAfter}`. Se normaliza acá, que es la frontera con la
  // librería, para que del lado de Django llegue siempre lo mismo — la misma
  // razón por la que `respuesta.js` traduce la respuesta del SIFEN.
  //
  // No es un detalle: sin normalizar, el aviso de "certificado por vencer" de
  // `verificar_fiscal` no entiende el dato y no avisa nunca. Se descubrió
  // recién al probar con un .p12 de verdad; con el certificado sin configurar
  // el camino no se ejecuta.
  if (crudo && typeof crudo === 'object') {
    return {
      vence: crudo.notAfter ?? crudo.notafter ?? null,
      desde: crudo.notBefore ?? crudo.notbefore ?? null,
    };
  }
  return { vence: crudo ?? null, desde: null };
}

module.exports = {
  ErrorTerminal,
  generarXml,
  firmar,
  generarQr,
  enviar,
  enviarLote,
  consultar,
  consultarLote,
  consultarRuc,
  enviarEvento,
  vencimientoCertificado,
  GENERADORES_EVENTO,
  // Las tablas geográficas de la DNIT vienen adentro de xmlgen.
  consultarDepartamentos: () => xmlgen.consultarDepartamentos(),
  consultarDistritos: (dep) => xmlgen.consultarDistritos(dep),
  consultarCiudades: (dis) => xmlgen.consultarCiudades(dis),
};
