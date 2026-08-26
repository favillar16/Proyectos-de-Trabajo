/**
 * Descubrimiento del servidor — sin depender de una IP fija.
 *
 * En el local no hay acceso al panel del router, así que no se puede reservar
 * la IP de la PC servidor por DHCP: se fija desde la propia PC y puede cambiar
 * si el router se reemplaza o se resetea (ahí la subred entera pasa a ser otra).
 * Por eso la app no guarda una dirección: la busca.
 *
 * Orden de búsqueda (el primero que conteste gana):
 *   1. VITE_API_URL, si alguien la fijó a mano — corta acá, sin sondear.
 *   2. El último servidor que funcionó, guardado en localStorage.
 *   3. El host con el que se abrió la página (lo normal: la app se sirve
 *      desde el mismo equipo que corre la API).
 *   4. Los nombres de red del servidor: mDNS ("ogapora.local") y NetBIOS
 *      ("ogapora"). Funciona en Windows y en Chrome de escritorio.
 *   5. Barrido de la subred, si conocemos alguna IP de referencia. Es el
 *      único camino que le queda a las tablets Android, que no resuelven
 *      nombres .local.
 *
 * Cada candidato se confirma pidiendo /api/v1/salud/ y verificando que
 * responda `sistema: "oga-pora"`. Así un equipo cualquiera que tenga el
 * puerto 8000 abierto no se confunde con el servidor del negocio.
 */

const PUERTO = import.meta.env.VITE_API_PORT || '8000'
const URL_FIJA = import.meta.env.VITE_API_URL || ''

// Nombres de red del servidor. Se pueden ampliar sin recompilar nada más.
const NOMBRES = (import.meta.env.VITE_SERVIDOR_NOMBRES || 'ogapora.local,ogapora')
  .split(',')
  .map((n) => n.trim())
  .filter(Boolean)

// Último octeto donde vive la PC servidor por convención (fijar_ip.ps1).
// Se prueba primero en el barrido para no recorrer 254 direcciones al pedo.
const OCTETOS_PROBABLES = [250, 100, 10, 2]

const CLAVE_CACHE = 'ogapora-servidor'
const TIMEOUT_SONDA = 2500   // ms — en LAN una respuesta buena tarda <100ms
const TIMEOUT_BARRIDO = 1200 // ms — más corto: son cientos de intentos
const CONCURRENCIA = 24

// ─── Sonda ────────────────────────────────────────────────────────────────────

/** Pide /salud/ a un host y devuelve su identidad, o null si no es el nuestro. */
async function sondear(host, timeout = TIMEOUT_SONDA) {
  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), timeout)
  try {
    const res = await fetch(`http://${host}:${PUERTO}/api/v1/salud/`, {
      signal: ctrl.signal,
      // La sonda no necesita cookies ni token, y así no arrastra preflight.
      credentials: 'omit',
      cache: 'no-store',
    })
    if (!res.ok) return null
    const datos = await res.json()
    return datos?.sistema === 'oga-pora' ? datos : null
  } catch {
    return null   // host caído, nombre que no resuelve, timeout, CORS…
  } finally {
    clearTimeout(t)
  }
}

// ─── Candidatos ───────────────────────────────────────────────────────────────

function leerCache() {
  try {
    const guardado = JSON.parse(localStorage.getItem(CLAVE_CACHE) || 'null')
    return guardado?.host || null
  } catch {
    return null
  }
}

function guardarCache(host, identidad) {
  try {
    localStorage.setItem(CLAVE_CACHE, JSON.stringify({
      host,
      nombre: identidad?.nombre || '',
      visto: new Date().toISOString(),
    }))
  } catch {/* modo incógnito o storage lleno: seguimos sin recordar */}
}

const esIPv4 = (h) => /^\d{1,3}(\.\d{1,3}){3}$/.test(h)

/** Direcciones de la misma subred que `ip`, las más probables primero. */
function barrerSubred(ip) {
  const prefijo = ip.split('.').slice(0, 3).join('.')
  const propio = Number(ip.split('.')[3])
  const resto = []
  for (let i = 1; i < 255; i++) {
    if (i !== propio && !OCTETOS_PROBABLES.includes(i)) resto.push(i)
  }
  return [...OCTETOS_PROBABLES, ...resto].map((o) => `${prefijo}.${o}`)
}

/** Sondea una lista en tandas; devuelve el primer host que conteste. */
async function primeroQueConteste(hosts, timeout) {
  for (let i = 0; i < hosts.length; i += CONCURRENCIA) {
    const tanda = hosts.slice(i, i + CONCURRENCIA)
    const resultados = await Promise.all(
      tanda.map(async (h) => ({ host: h, identidad: await sondear(h, timeout) }))
    )
    const ganador = resultados.find((r) => r.identidad)
    if (ganador) return ganador
  }
  return null
}

// ─── Resolución ───────────────────────────────────────────────────────────────

async function descubrir() {
  const propio = window.location.hostname

  // 1 — URL fijada a mano: se respeta tal cual, es una decisión explícita.
  if (URL_FIJA) return { baseUrl: URL_FIJA, host: null, identidad: null }

  // 2, 3, 4 — cache, host de origen y nombres de red, uno por uno.
  const directos = [leerCache(), propio, ...NOMBRES].filter(Boolean)
  for (const host of [...new Set(directos)]) {
    const identidad = await sondear(host)
    if (identidad) {
      guardarCache(host, identidad)
      return { baseUrl: `http://${host}:${PUERTO}/api/v1`, host, identidad }
    }
  }

  // 5 — barrido de la subred. Solo sirve si tenemos una IP de referencia:
  // la del origen, o la del último servidor conocido.
  const referencia = [propio, leerCache()].find(esIPv4)
  if (referencia) {
    const encontrado = await primeroQueConteste(barrerSubred(referencia), TIMEOUT_BARRIDO)
    if (encontrado) {
      guardarCache(encontrado.host, encontrado.identidad)
      return {
        baseUrl: `http://${encontrado.host}:${PUERTO}/api/v1`,
        host: encontrado.host,
        identidad: encontrado.identidad,
      }
    }
  }

  // Sin servidor. Devolvemos el host de origen igual: así la app falla con un
  // error de red normal (que la UI ya sabe mostrar) en vez de quedarse colgada.
  return { baseUrl: `http://${propio}:${PUERTO}/api/v1`, host: propio, identidad: null }
}

let enCurso = null

/**
 * URL base de la API, descubriendo el servidor la primera vez.
 * Las llamadas simultáneas comparten la misma búsqueda.
 */
export function resolverServidor() {
  if (!enCurso) enCurso = descubrir()
  return enCurso
}

export async function baseUrlApi() {
  return (await resolverServidor()).baseUrl
}

/** URL base del WebSocket, sobre el mismo servidor que la API. */
export async function baseUrlWs() {
  const { baseUrl } = await resolverServidor()
  const protocolo = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return baseUrl.replace(/^https?/, protocolo).replace(/\/api\/v1$/, '')
}

/**
 * Olvida el servidor conocido y fuerza una búsqueda nueva. Se llama cuando
 * la red falla, que es justo el síntoma de que el servidor cambió de IP.
 */
export function olvidarServidor() {
  enCurso = null
  try { localStorage.removeItem(CLAVE_CACHE) } catch {/* nada que borrar */}
}

/** Datos del servidor en uso, para mostrarlos en pantalla. Null si aún no se resolvió. */
export function servidorActual() {
  try {
    return JSON.parse(localStorage.getItem(CLAVE_CACHE) || 'null')
  } catch {
    return null
  }
}
