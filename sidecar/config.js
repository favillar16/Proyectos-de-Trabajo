/**
 * Configuración del sidecar.
 *
 * Se lee del MISMO `backend/.env` que usa Django, a propósito: el certificado,
 * su clave, el CSC y el ambiente son datos que los dos lados tienen que ver
 * iguales. Con dos archivos de configuración separados, el día que alguien
 * cambia el ambiente de `test` a `produccion` en uno solo, el sistema firma
 * para producción y transmite a test (o al revés) y el error aparece como un
 * rechazo incomprensible del SIFEN.
 *
 * No se usa `dotenv`: leer un archivo de `clave=valor` son veinte líneas, y
 * cada dependencia es una cosa más que hay que acordarse de instalar el día
 * que se reinstala la PC de la tienda. Es la misma razón por la que
 * `sifen_client.py` usa `urllib` y no `requests`.
 */
const fs = require('fs');
const path = require('path');

const RUTA_ENV = path.join(__dirname, '..', 'backend', '.env');

function leerEnv(ruta) {
  if (!fs.existsSync(ruta)) return {};
  const salida = {};
  for (const linea of fs.readFileSync(ruta, 'utf8').split(/\r?\n/)) {
    const limpia = linea.trim();
    if (!limpia || limpia.startsWith('#')) continue;
    const corte = limpia.indexOf('=');
    if (corte === -1) continue;
    const clave = limpia.slice(0, corte).trim();
    let valor = limpia.slice(corte + 1).trim();
    // python-decouple acepta el valor entre comillas y no las considera parte
    // del dato. Si no se sacaran acá, la clave del .p12 llegaría con comillas
    // y el certificado no abriría.
    if (valor.length >= 2 &&
        ((valor.startsWith('"') && valor.endsWith('"')) ||
         (valor.startsWith("'") && valor.endsWith("'")))) {
      valor = valor.slice(1, -1);
    }
    salida[clave] = valor;
  }
  return salida;
}

// El entorno del proceso gana sobre el archivo: así se puede arrancar una
// instancia apuntando al ambiente de pruebas sin tocar el .env del servidor.
const archivo = leerEnv(RUTA_ENV);
const dato = (clave, porDefecto = '') =>
  (process.env[clave] ?? archivo[clave] ?? porDefecto).toString().trim();

function resolverRutaCertificado(valor) {
  if (!valor) return '';
  return path.isAbsolute(valor)
    ? valor
    : path.resolve(__dirname, '..', 'backend', valor);
}

const config = {
  puerto: parseInt(dato('SIFEN_SIDECAR_PUERTO', '8100'), 10),

  // Solo loopback. El sidecar tiene la clave del certificado en memoria y
  // firma cualquier XML que le manden sin autenticar a quien pregunta: en la
  // LAN de la tienda, con las tablets y CORS abiertos, escucharlo en 0.0.0.0
  // sería entregar la firma electrónica del contribuyente. Django corre en la
  // misma máquina, así que 127.0.0.1 alcanza. Ver docs/facturacion_electronica.md
  host: dato('SIFEN_SIDECAR_HOST', '127.0.0.1'),

  // 'test' | 'produccion'. Las librerías esperan "test" | "prod".
  ambiente: dato('SIFEN_AMBIENTE', 'test'),

  certificadoPath: resolverRutaCertificado(dato('SIFEN_CERT_PATH')),
  certificadoPassword: dato('SIFEN_CERT_PASSWORD'),

  cscId: dato('SIFEN_CSC_ID'),
  csc: dato('SIFEN_CSC'),

  timeoutMs: parseInt(dato('SIFEN_TIMEOUT', '30'), 10) * 1000,
  debug: dato('SIFEN_SIDECAR_DEBUG', 'False').toLowerCase() === 'true',
};

/** Las librerías de la DNIT reciben "test" | "prod", no el nombre largo. */
config.env = config.ambiente === 'produccion' ? 'prod' : 'test';

/** ¿Hay certificado configurado y existe el archivo? */
config.certificadoDisponible = () =>
  Boolean(config.certificadoPath) && fs.existsSync(config.certificadoPath);

module.exports = config;
