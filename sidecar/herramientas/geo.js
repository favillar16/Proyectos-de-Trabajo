/**
 * Busca códigos de departamento, distrito y ciudad en las tablas de la DNIT.
 *
 * Para qué: el Manual Técnico no trae esos códigos — la Tabla 2.1 (§15) remite
 * a una planilla externa, `CODIGO DE REFERENCIA GEOGRAFICA.xlsx`. Pero
 * `xmlgen` las trae adentro, así que la planilla no hace falta.
 *
 * Importa acertarle: un código geográfico equivocado es rechazo directo del
 * documento, y no hay forma de darse cuenta antes de transmitir.
 *
 *     npm run geo                 # los 18 departamentos
 *     npm run geo -- oviedo       # busca el texto en los tres niveles
 *     npm run geo -- 61           # el distrito 61 y todas sus ciudades
 *
 * ⚠️ Hay nombres repetidos. Coronel Oviedo aparece dos veces como ciudad del
 * distrito 61 (2886 y 2937). La regla que se observó es que la **primera**
 * ciudad listada de un distrito es la cabecera, fuera del orden alfabético —
 * pasa en 205 de los 272 distritos—, pero es una inferencia sobre la forma de
 * los datos, no un dato oficial. Cuando hay repetidos, confirmar con la
 * contadora antes de cargarlo en el .env.
 */
const xmlgen = require('facturacionelectronicapy-xmlgen').default;

const normalizar = (t) =>
  (t ?? '').toString().normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase();

async function main() {
  const argumento = process.argv.slice(2).join(' ').trim();
  const departamentos = await xmlgen.consultarDepartamentos();

  if (!argumento) {
    console.log('DEPARTAMENTOS:');
    for (const d of departamentos) console.log(`  ${String(d.codigo).padStart(3)}  ${d.descripcion}`);
    console.log('\nUsar: npm run geo -- <texto o código de distrito>');
    return;
  }

  // Un número se toma como código de distrito y se listan sus ciudades.
  if (/^\d+$/.test(argumento)) {
    const ciudades = await xmlgen.consultarCiudades(Number(argumento));
    console.log(`CIUDADES del distrito ${argumento} (${ciudades.length}):`);
    for (const c of ciudades) console.log(`  ${String(c.codigo).padStart(5)}  ${c.descripcion}`);
    return;
  }

  const buscado = normalizar(argumento);
  const deps = departamentos.filter((d) => normalizar(d.descripcion).includes(buscado));
  if (deps.length) {
    console.log('DEPARTAMENTOS:');
    for (const d of deps) console.log(`  ${d.codigo}  ${d.descripcion}`);
  }

  for (const dep of departamentos) {
    const distritos = await xmlgen.consultarDistritos(dep.codigo);
    for (const dis of distritos) {
      if (normalizar(dis.descripcion).includes(buscado)) {
        console.log(`\nDISTRITO ${dis.codigo}  ${dis.descripcion}  (depto ${dep.codigo} ${dep.descripcion})`);
        const ciudades = await xmlgen.consultarCiudades(dis.codigo);
        const coincide = ciudades.filter((c) => normalizar(c.descripcion).includes(buscado));
        for (const c of coincide) {
          const primera = ciudades[0].codigo === c.codigo;
          console.log(`  CIUDAD ${String(c.codigo).padStart(5)}  ${c.descripcion}` +
            (primera ? '   <- primera del distrito (probable cabecera)' : ''));
        }
        if (coincide.length > 1) {
          console.log('  ⚠ hay más de una con ese nombre: confirmar cuál corresponde.');
        }
      }
    }
  }
}

main().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
