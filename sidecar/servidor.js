/**
 * Sidecar HTTP que habla con el SIFEN.
 *
 * Es el proceso que faltaba de la Fase A. El contrato que cumple no se
 * inventó acá: está escrito y probado del lado Django en
 * `backend/apps/facturacion/sifen_client.py`, que se escribió primero a
 * propósito. Este archivo lo implementa, no lo define.
 *
 *   POST /xml              {params, data, test}  → {xml}
 *   POST /firmar           {xml}                 → {xml}
 *   POST /qr               {xml}                 → {xml}
 *   POST /enviar           {xml}                 → {estado, codigo, mensaje, ...}
 *   POST /consultar        {cdc}                 → {estado, codigo, mensaje, ...}
 *   POST /evento/<tipo>    {params, data}        → {estado, codigo, mensaje, ...}
 *   POST /salud            {}                    → diagnóstico
 *
 * ── Lo más importante de este archivo es el mapeo de errores ────────────────
 *
 * Todo el diseño de la cola depende de una distinción: qué se reintenta y qué
 * no (ver `transmision.py`). El sidecar es quien tiene la información para
 * decidirlo, y la comunica con el código HTTP:
 *
 *   200  El SIFEN contestó. Incluso si contestó "Rechazado": eso es una
 *        respuesta, no una falla. Django la lee y marca el documento.
 *   422  El pedido está mal o falta configuración (no hay certificado, el
 *        evento no existe, el CDC no tiene 44 dígitos). Reintentarlo da
 *        exactamente lo mismo → terminal.
 *   502  No se pudo hablar con el SIFEN, o pasó algo que no entendemos.
 *        Puede ser el corte de internet de la tienda → reintentable.
 *
 * Ante la duda va 502. La asimetría es deliberada: reintentar de más gasta
 * intentos, pero dar por rechazado un documento válido pierde una venta ya
 * cobrada, y eso no se puede deshacer.
 *
 * No usa Express ni ningún framework: son unas pocas rutas que reciben JSON y el
 * `http` de Node alcanza. Cada dependencia es una cosa más que hay que
 * acordarse de instalar el día que se reinstala la PC de la tienda — la misma
 * razón por la que `sifen_client.py` usa `urllib` y no `requests`.
 */
const http = require('http');

const config = require('./config');
const sifen = require('./sifen');

// El XML de un DE con muchos ítems es grande, pero no ilimitado. Un tope
// evita que un pedido malformado haga crecer la memoria del proceso.
const MAX_CUERPO = 10 * 1024 * 1024;   // 10 MB

function registrar(...args) {
  console.log(new Date().toISOString(), ...args);
}

function leerCuerpo(peticion) {
  return new Promise((resolve, reject) => {
    const partes = [];
    let tamano = 0;
    peticion.on('data', (parte) => {
      tamano += parte.length;
      if (tamano > MAX_CUERPO) {
        reject(new sifen.ErrorTerminal(
          `El cuerpo supera ${MAX_CUERPO} bytes.`));
        peticion.destroy();
        return;
      }
      partes.push(parte);
    });
    peticion.on('end', () => {
      const crudo = Buffer.concat(partes).toString('utf8');
      if (!crudo.trim()) return resolve({});
      try {
        resolve(JSON.parse(crudo));
      } catch (e) {
        reject(new sifen.ErrorTerminal(`El cuerpo no es JSON válido: ${e.message}`));
      }
    });
    peticion.on('error', reject);
  });
}

function responder(respuesta, codigo, cuerpo) {
  const texto = JSON.stringify(cuerpo);
  respuesta.writeHead(codigo, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(texto),
  });
  respuesta.end(texto);
}

function exigir(cuerpo, campo) {
  const valor = cuerpo[campo];
  if (valor === undefined || valor === null || valor === '') {
    throw new sifen.ErrorTerminal(`Falta el campo "${campo}" en el pedido.`);
  }
  return valor;
}

// ─── Rutas ───────────────────────────────────────────────────────────────────

const rutas = {
  async xml(cuerpo) {
    // `test` lo manda Django desde SIFEN_AMBIENTE. Se respeta lo que mandó en
    // vez de recalcularlo acá: si los dos lados lo decidieran por su cuenta
    // podrían discrepar, y un DE firmado como de prueba que va a producción
    // es un rechazo seguro.
    const esPrueba = cuerpo.test !== undefined
      ? Boolean(cuerpo.test)
      : config.env === 'test';
    return { xml: await sifen.generarXml(cuerpo.params, cuerpo.data, esPrueba) };
  },

  async firmar(cuerpo) {
    return { xml: await sifen.firmar(exigir(cuerpo, 'xml')) };
  },

  async qr(cuerpo) {
    return { xml: await sifen.generarQr(exigir(cuerpo, 'xml')) };
  },

  async enviar(cuerpo) {
    return sifen.enviar(exigir(cuerpo, 'xml'));
  },

  async enviarLote(cuerpo) {
    return sifen.enviarLote(exigir(cuerpo, 'xmls'));
  },

  async consultar(cuerpo) {
    return sifen.consultar(exigir(cuerpo, 'cdc'));
  },

  async consultarLote(cuerpo) {
    return sifen.consultarLote(exigir(cuerpo, 'lote'));
  },

  async consultarRuc(cuerpo) {
    return sifen.consultarRuc(exigir(cuerpo, 'ruc'));
  },

  async salud(cuerpo, { ruta }) {
    const estado = {
      servicio: 'sidecar-sifen',
      ok: true,
      ambiente: config.ambiente,
      env: config.env,
      certificado: {
        configurado: Boolean(config.certificadoPath),
        archivo: config.certificadoPath || null,
        existe: config.certificadoDisponible(),
        vence: null,
      },
      csc: { id: config.cscId || null, cargado: Boolean(config.csc) },
      eventos: Object.keys(sifen.GENERADORES_EVENTO),
    };

    // El vencimiento obliga a abrir el .p12, así que solo se mira si está.
    // Que no se pueda abrir es información valiosa —una clave equivocada se
    // descubre acá y no en la primera venta— y no tiene que tirar /salud:
    // la gracia de este endpoint es contestar siempre.
    if (estado.certificado.existe && config.certificadoPassword) {
      try {
        const vigencia = await sifen.vencimientoCertificado();
        estado.certificado.vence = vigencia.vence;
        estado.certificado.desde = vigencia.desde;
      } catch (e) {
        estado.certificado.error = `No se pudo abrir el .p12: ${e.message}`;
        estado.ok = false;
      }
    }
    return estado;
  },
};

/** Las tablas geográficas de la DNIT, para resolver los códigos del domicilio. */
async function rutaGeografia(cuerpo) {
  const { departamento, distrito } = cuerpo;
  if (distrito !== undefined && distrito !== null) {
    return { ciudades: await sifen.consultarCiudades(Number(distrito)) };
  }
  if (departamento !== undefined && departamento !== null) {
    return { distritos: await sifen.consultarDistritos(Number(departamento)) };
  }
  return { departamentos: await sifen.consultarDepartamentos() };
}

async function despachar(ruta, cuerpo) {
  if (ruta.startsWith('evento/')) {
    const tipo = ruta.slice('evento/'.length);
    return sifen.enviarEvento(tipo, cuerpo.params, cuerpo.data);
  }
  if (ruta === 'geografia') return rutaGeografia(cuerpo);
  const manejador = rutas[ruta];
  if (!manejador) {
    const e = new Error(`No existe la ruta /${ruta}.`);
    e.noEncontrada = true;
    throw e;
  }
  return manejador(cuerpo, { ruta });
}

const servidor = http.createServer(async (peticion, respuesta) => {
  const ruta = new URL(peticion.url, 'http://localhost')
    .pathname.replace(/^\/+|\/+$/g, '');

  // /salud también por GET, para poder mirarlo desde el navegador o con curl
  // sin armar un POST. El resto es POST, como lo manda sifen_client.py.
  if (peticion.method === 'GET' && (ruta === 'salud' || ruta === '')) {
    try {
      return responder(respuesta, 200, await rutas.salud({}, { ruta: 'salud' }));
    } catch (e) {
      return responder(respuesta, 502, { error: e.message });
    }
  }
  if (peticion.method !== 'POST') {
    return responder(respuesta, 405, { error: 'Se esperaba POST.' });
  }

  const empezo = Date.now();
  try {
    const cuerpo = await leerCuerpo(peticion);
    const resultado = await despachar(ruta, cuerpo);
    registrar(`POST /${ruta} → 200 (${Date.now() - empezo}ms)`,
      resultado.estado ? `estado=${resultado.estado} codigo=${resultado.codigo}` : '');
    return responder(respuesta, 200, resultado);
  } catch (e) {
    if (e && e.noEncontrada) {
      registrar(`POST /${ruta} → 404`);
      return responder(respuesta, 404, { error: e.message });
    }
    if (e instanceof sifen.ErrorTerminal) {
      // Terminal: el pedido está mal o falta configuración. Django lo marca
      // rechazado y deja de intentar, en vez de gastar diez reintentos en un
      // certificado que no está.
      registrar(`POST /${ruta} → 422 ${e.message}`);
      return responder(respuesta, 422, { error: e.message, terminal: true });
    }
    // Cualquier otra cosa: se asume transporte y se deja reintentar.
    registrar(`POST /${ruta} → 502 ${e && e.message} (${Date.now() - empezo}ms)`);
    return responder(respuesta, 502, {
      error: (e && e.message) || String(e),
      detalle: (e && e.stack) ? String(e.stack).split('\n').slice(0, 4).join(' ') : '',
    });
  }
});

servidor.headersTimeout = config.timeoutMs + 5000;
servidor.requestTimeout = 0;   // el timeout real lo pone quien llama

if (require.main === module) {
  servidor.listen(config.puerto, config.host, () => {
    registrar(`sidecar SIFEN escuchando en http://${config.host}:${config.puerto}`);
    registrar(`  ambiente:    ${config.ambiente} (librerías: "${config.env}")`);
    registrar(`  certificado: ${config.certificadoPath || 'SIN CONFIGURAR'}` +
      (config.certificadoPath
        ? (config.certificadoDisponible() ? ' (existe)' : ' ⚠ NO EXISTE')
        : ''));
    registrar(`  CSC:         ${config.csc ? `cargado (ID ${config.cscId})` : 'SIN CONFIGURAR'}`);
    if (config.host !== '127.0.0.1' && config.host !== 'localhost') {
      registrar('  ⚠ ATENCIÓN: el sidecar NO está limitado a loopback. Firma ' +
        'cualquier XML que le manden, sin autenticar. Ver config.js.');
    }
  });
}

module.exports = { servidor, despachar };
