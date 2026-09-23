/**
 * El servidor contesta el contrato que espera Django, y sobre todo contesta
 * el CÓDIGO HTTP correcto.
 *
 * Por qué importa más el código que el cuerpo: `transmision.py` decide con él
 * si un documento se reintenta o se da por perdido. Un 502 donde iba un 422
 * hace que la cola gaste diez intentos en un certificado que no está; un 422
 * donde iba un 502 marca como rechazado un documento que el SIFEN nunca vio
 * —una venta ya cobrada que se pierde—, y eso no se deshace.
 *
 * Se levanta el servidor de verdad en un puerto libre y se le pega con fetch,
 * en vez de llamar a `despachar` directo: el mapeo de errores vive en el
 * manejador HTTP, así que probar la función de adentro no probaría nada de lo
 * que importa acá.
 */
const { test, before, after } = require('node:test');
const assert = require('node:assert');

// Se fija la configuración ANTES de cargar el servidor, porque `config.js` la
// lee una sola vez al importarse y el entorno le gana al archivo.
//
// Sin esto los tests leerían el `backend/.env` de quien los corre, y pasarían
// o fallarían según lo que esa máquina tenga configurado — que es lo contrario
// de lo que hace un test. Pasó de verdad: el caso "sin certificado da 422"
// empezó a fallar el día que se configuró un .p12 de prueba en esta PC.
process.env.SIFEN_CERT_PATH = '';
process.env.SIFEN_CERT_PASSWORD = '';
process.env.SIFEN_AMBIENTE = 'test';
process.env.SIFEN_CSC_ID = '0001';
process.env.SIFEN_CSC = 'ABCD0000000000000000000000000000';

const { servidor } = require('../servidor');

let base;

before(async () => {
  await new Promise((resolve) => servidor.listen(0, '127.0.0.1', resolve));
  base = `http://127.0.0.1:${servidor.address().port}`;
});

after(() => new Promise((resolve) => servidor.close(resolve)));

const postear = (ruta, cuerpo) =>
  fetch(`${base}/${ruta}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cuerpo ?? {}),
  });

test('/salud contesta 200 por POST, que es como lo llama Django', async () => {
  const r = await postear('salud', {});
  assert.strictEqual(r.status, 200);
  const cuerpo = await r.json();
  assert.strictEqual(cuerpo.servicio, 'sidecar-sifen');
  assert.ok('certificado' in cuerpo);
  assert.ok(Array.isArray(cuerpo.eventos));
});

test('/salud también contesta por GET, para poder mirarlo con curl', async () => {
  const r = await fetch(`${base}/salud`);
  assert.strictEqual(r.status, 200);
});

test('sin certificado, /firmar da 422 (terminal) y no 502', async () => {
  // Es el caso del día de hoy: el .p12 todavía no llegó. Reintentar diez
  // veces no lo va a hacer aparecer.
  const r = await postear('firmar', { xml: '<a/>' });
  assert.strictEqual(r.status, 422);
  const cuerpo = await r.json();
  assert.strictEqual(cuerpo.terminal, true);
  assert.match(cuerpo.error, /SIFEN_CERT_PATH/);
});

test('un campo que falta da 422, con el nombre del campo', async () => {
  const r = await postear('firmar', {});
  assert.strictEqual(r.status, 422);
  assert.match((await r.json()).error, /"xml"/);
});

test('un evento que no existe da 422 y lista los que sí existen', async () => {
  // Un nombre mal escrito tiene que fallar con la lista a la vista, no con un
  // "undefined is not a function" en medio de una cancelación.
  const r = await postear('evento/cancelacionn', { params: {}, data: {} });
  assert.strictEqual(r.status, 422);
  const { error } = await r.json();
  assert.match(error, /cancelacion/);
  assert.match(error, /inutilizacion/);
});

test('un CDC que no tiene 44 dígitos da 422 antes de salir a la red', async () => {
  const r = await postear('consultar', { cdc: '123' });
  assert.strictEqual(r.status, 422);
  assert.match((await r.json()).error, /44/);
});

test('una ruta que no existe da 404', async () => {
  const r = await postear('inventada', {});
  assert.strictEqual(r.status, 404);
});

test('GET a una ruta que no es /salud da 405', async () => {
  const r = await fetch(`${base}/enviar`);
  assert.strictEqual(r.status, 405);
});

test('un cuerpo que no es JSON da 422, no tira el proceso', async () => {
  const r = await fetch(`${base}/xml`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{esto no es json',
  });
  assert.strictEqual(r.status, 422);
});

// Emisor y documento mínimos que acepta xmlgen. Se comparten entre los dos
// tests de abajo.
const params = {
    version: 150,
    ruc: '80173107-0',
    razonSocial: 'PRUEBA SIDECAR',
    nombreFantasia: 'PRUEBA SIDECAR',
    actividadesEconomicas: [{ codigo: '47523', descripcion: 'Comercio' }],
    timbradoNumero: '18936285',
    timbradoFecha: '2026-06-23',
    tipoContribuyente: 2,
    tipoRegimen: 8,
    establecimientos: [{
      codigo: '001', direccion: 'CALLE PRUEBA', numeroCasa: '0',
      departamento: 6, departamentoDescripcion: 'CAAGUAZU',
      distrito: 61, distritoDescripcion: 'CNEL. OVIEDO',
      ciudad: 2886, ciudadDescripcion: 'CNEL. OVIEDO',
      telefono: '0971451936', email: '',
    }],
  };
const data = {
    tipoDocumento: 1,
    establecimiento: '001',
    punto: '001',
    numero: '0000001',
    descripcion: '',
    observacion: '',
    fecha: '2026-09-16T10:00:00',
    tipoEmision: 1,
    tipoTransaccion: 1,
    tipoImpuesto: 1,
    moneda: 'PYG',
    condicionAnticipo: 1,
    condicionTipoCambio: 1,
    cliente: {
      contribuyente: false,
      razonSocial: 'CLIENTE PRUEBA',
      tipoOperacion: 2,
      documentoTipo: 1,
      documentoNumero: '4823661',
      pais: 'PRY',
      paisDescripcion: 'Paraguay',
    },
    condicion: {
      tipo: 1,
      entregas: [{ tipo: 1, monto: '100000', moneda: 'PYG', cambio: 0 }],
    },
    items: [{
      codigo: 'SKU-1',
      descripcion: 'Producto de prueba',
      unidadMedida: 109,
      cantidad: 1,
      precioUnitario: 100000,
      descuento: 0,
      ivaTipo: 1,
      iva: 10,
      ivaBase: 100,
      ivaProporcion: 100,
    }],
    factura: { presencia: 1 },
};

test('/xml arma un DE real con la librería de la DNIT', async () => {
  // Es la prueba de que el sidecar está bien montado: xmlgen no necesita
  // certificado, así que esto se puede correr desde hoy.
  const r = await postear('xml', {
    params,
    data: { ...data, codigoSeguridadAleatorio: '123456789' },
    test: true,
  });
  const cuerpo = await r.json();
  assert.strictEqual(r.status, 200, `respondió ${r.status}: ${JSON.stringify(cuerpo)}`);
  const { xml } = cuerpo;
  assert.match(xml, /<rDE/);
  assert.match(xml, /<dVerFor>150<\/dVerFor>/);
  // El CDC lo calcula xmlgen solo, a partir de los campos sueltos.
  assert.match(xml, /<DE Id="\d{44}"/);
});

test('un campo que falta NO pasa como "undefined" adentro del XML', async () => {
  // xmlgen no valida: si falta un dato lo interpola igual y escribe el string
  // "undefined" en el XML, devolviendo éxito. Se descubrió acá, omitiendo
  // `codigoSeguridadAleatorio`: salió un DE con
  //     <DE Id="...1undefined3"> y <dCodSeg>undefined</dCodSeg>
  // que se habría firmado y transmitido, para volver rechazado con un error
  // del SIFEN que no señala el campo que falta. Y como un rechazo es
  // terminal, la venta quedaba sin factura y sin pista de por qué.
  const sinCodigoSeguridad = { ...data };
  delete sinCodigoSeguridad.codigoSeguridadAleatorio;

  const r = await postear('xml', { params, data: sinCodigoSeguridad, test: true });
  assert.strictEqual(r.status, 422);
  const { error, terminal } = await r.json();
  assert.strictEqual(terminal, true);
  assert.match(error, /undefined|44 dígitos/);
});

test('/geografia devuelve las tablas de la DNIT que trae xmlgen', async () => {
  // Resuelven los códigos de departamento/distrito/ciudad sin tener que bajar
  // la planilla externa que el Manual referencia y no incluye.
  const r = await postear('geografia', { distrito: 61 });
  assert.strictEqual(r.status, 200);
  const { ciudades } = await r.json();
  assert.ok(ciudades.some((c) => c.codigo === 2886));
});
