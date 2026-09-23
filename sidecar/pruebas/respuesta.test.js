/**
 * La respuesta del SIFEN se interpreta bien.
 *
 * Los casos no son inventados: el primero es literalmente el ejemplo que
 * publica el Manual Técnico V150 §9.1, parseado como lo parsea setapi
 * (`xml2js` con `explicitArray: false`). Los demás cubren las formas que el
 * manual declara pero el ejemplo no muestra — sobre todo `gResProc` repetido,
 * que es ocurrencia 1-100.
 */
const { test } = require('node:test');
const assert = require('node:assert');
const { interpretar, sinNamespaces, juntar } = require('../respuesta');

// Manual Técnico V150 §9.1, "Response de ejemplo utilizando SOAP".
const RECHAZO_DEL_MANUAL = {
  'ns2:rRetEnviDe': {
    'ns2:rProtDe': {
      'ns2:dId': '00000000000000000000000000000000000000000000',
      'ns2:dFecProc': '2019-06-03T12:00:00',
      'ns2:dDigVal': '0000000000000000000000000000',
      'ns2:gResProc': {
        'ns2:dEstRes': 'Rechazado',
        'ns2:dProtAut': '0000000000',
        'ns2:dCodRes': '0160',
        'ns2:dMsgRes': 'XML malformado',
      },
    },
  },
  id: 1,
};

test('el rechazo del ejemplo del manual se lee como rechazado', () => {
  const r = interpretar(RECHAZO_DEL_MANUAL);
  assert.strictEqual(r.estado, 'rechazado');
  assert.strictEqual(r.codigo, '0160');
  assert.match(r.mensaje, /XML malformado/);
  assert.strictEqual(r.protocolo, '0000000000');
});

test('una aprobación se lee como aprobado', () => {
  const r = interpretar({
    'ns2:rRetEnviDe': {
      'ns2:rProtDe': {
        'ns2:gResProc': {
          'ns2:dEstRes': 'Aprobado',
          'ns2:dProtAut': '1234567890',
          'ns2:dCodRes': '0260',
          'ns2:dMsgRes': 'Autorizado el uso del DE',
        },
      },
    },
  });
  assert.strictEqual(r.estado, 'aprobado');
  assert.strictEqual(r.protocolo, '1234567890');
});

test('"Aprobado con observación" no se confunde con "Aprobado"', () => {
  // Importa: el tilde y el texto largo. Si el prefijo se comparara mal, un
  // documento observado se guardaría como aprobado liso y la observación se
  // perdería.
  const r = interpretar({
    'ns2:rRetEnviDe': {
      'ns2:rProtDe': {
        'ns2:gResProc': {
          'ns2:dEstRes': 'Aprobado con observación',
          'ns2:dCodRes': '0270',
          'ns2:dMsgRes': 'Autorizado con observaciones',
        },
      },
    },
  });
  assert.strictEqual(r.estado, 'aprobado_con_observaciones');
});

test('gResProc repetido: se conservan TODOS los motivos del rechazo', () => {
  // El manual da a gResProc ocurrencia 1-100. xml2js con explicitArray:false
  // entrega un arreglo cuando hay más de uno. Quedarse con el primero
  // perdería el resto, que es justo lo que hace falta para corregir.
  const r = interpretar({
    'ns2:rRetEnviDe': {
      'ns2:rProtDe': {
        'ns2:gResProc': [
          { 'ns2:dEstRes': 'Rechazado', 'ns2:dCodRes': '0160',
            'ns2:dMsgRes': 'XML malformado' },
          { 'ns2:dCodRes': '1216',
            'ns2:dMsgRes': 'Campo iTipTra no debe informarse' },
          { 'ns2:dCodRes': '0420', 'ns2:dMsgRes': 'CDC duplicado' },
        ],
      },
    },
  });
  assert.strictEqual(r.estado, 'rechazado');
  assert.match(r.mensaje, /0160/);
  assert.match(r.mensaje, /1216/);
  assert.match(r.mensaje, /CDC duplicado/);
});

test('si un resultado posterior rechaza, el documento no queda aprobado', () => {
  const r = interpretar({
    rRetEnviDe: {
      rProtDe: {
        gResProc: [
          { dEstRes: 'Aprobado', dCodRes: '0260', dMsgRes: 'ok' },
          { dEstRes: 'Rechazado', dCodRes: '0420', dMsgRes: 'CDC duplicado' },
        ],
      },
    },
  });
  assert.strictEqual(r.estado, 'rechazado');
});

test('el acuse de lote (0300) es "enviado", no aprobado ni rechazado', () => {
  // El WS asincrónico no resuelve el documento: solo acusa recibo del lote.
  // Tratarlo como aprobado daría por buena una factura que el SIFEN todavía
  // no miró.
  const r = interpretar({
    'ns2:rRetEnviLoteDE': {
      'ns2:dCodRes': '0300',
      'ns2:dMsgRes': 'Lote recibido con exito',
      'ns2:dProtConsLote': '123456789',
    },
  });
  assert.strictEqual(r.estado, 'enviado');
});

test('una respuesta que no se entiende queda "desconocido", no rechazado', () => {
  // Es la decisión de seguridad del módulo: lo que no se entiende se
  // reintenta. Darlo por rechazado perdería una venta ya cobrada.
  const r = interpretar({ algo: { inesperado: true } });
  assert.strictEqual(r.estado, 'desconocido');
});

test('la respuesta del evento (§9.5.3) anida distinto y se lee igual', () => {
  const r = interpretar({
    'ns2:rRetEnviEventoDe': {
      'ns2:dFecProc': '2026-09-16T10:00:00',
      'ns2:gResProcEVe': {
        'ns2:dEstRes': 'Aprobado',
        'ns2:dProtAut': '9876543210',
        'ns2:id': '1',
        'ns2:gResProc': { 'ns2:dCodRes': '0600',
                          'ns2:dMsgRes': 'Evento registrado' },
      },
    },
  });
  assert.strictEqual(r.estado, 'aprobado');
  assert.strictEqual(r.codigo, '0600');
  assert.strictEqual(r.protocolo, '9876543210');
});

test('sinNamespaces limpia las claves en todo el árbol', () => {
  assert.deepStrictEqual(
    sinNamespaces({ 'a:b': { 'c:d': [{ 'e:f': 1 }] } }),
    { b: { d: [{ f: 1 }] } });
});

test('juntar no se traga un valor 0 ni rompe con null', () => {
  assert.deepStrictEqual(juntar({ x: { y: 0 } }, 'y'), [0]);
  assert.deepStrictEqual(juntar({ x: null }, 'y'), []);
});
