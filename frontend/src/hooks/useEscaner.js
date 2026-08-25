/**
 * useEscaner — lector de código de barras FTX-LC123BH5.
 *
 * Cómo funciona el lector
 * ───────────────────────
 * El FTX-LC123BH5 es un HID: Windows lo ve como un teclado más. Al leer un
 * código "tipea" sus caracteres uno por uno y termina con un Enter. No hay
 * driver, no hay puerto serie, no hay nada que instalar — desde el navegador
 * un escaneo es indistinguible de alguien escribiendo muy rápido.
 *
 * "Muy rápido" es justamente lo que se usa para distinguirlo: una persona
 * tarda 80-200 ms entre teclas, el lector manda todo el código en menos de
 * 30 ms por carácter. Este hook junta las teclas que llegan seguidas y, si al
 * cerrar con Enter la ráfaga fue lo bastante veloz y larga, la trata como un
 * escaneo.
 *
 * Por qué solo escucha fuera de los campos de texto
 * ─────────────────────────────────────────────────
 * Si el foco está en un input, el lector escribe ahí y el componente ya lo ve
 * como texto normal: ese caso se resuelve con un `onKeyDown` en el propio
 * campo (ver `alEnterDeEscaneo`), no acá. Capturar globalmente cuando hay un
 * campo enfocado haría que un escaneo dispare la búsqueda Y además deje el
 * código pegado en el buscador, o peor, que se lo coma cuando la vendedora
 * estaba escribiendo el nombre de un cliente.
 *
 * Fuera de los campos, en cambio, las teclas no van a ninguna parte, así que
 * se las puede capturar sin quitarle nada a nadie.
 */
import { useCallback, useEffect, useRef } from 'react'

// Milisegundos máximos entre dos teclas para seguir considerándolas parte del
// mismo escaneo. 60 ms deja margen para una tablet lenta sin llegar a la
// velocidad de tipeo de una persona.
const INTERVALO_MAXIMO_MS = 60

// Un código de barras corto igual tiene 4+ caracteres. Menos que eso es
// alguien apoyando el codo en el teclado.
const LARGO_MINIMO = 4

// Si la ráfaga queda a medias (el lector falló, o se apretaron dos teclas
// sueltas), el buffer se descarta solo. Sin esto, el próximo escaneo llegaría
// pegado a la basura anterior.
const MS_HASTA_DESCARTAR = 400

/** True si el elemento acepta texto y por lo tanto se le debe dejar el teclado. */
export function esCampoDeTexto(el) {
  if (!el) return false
  if (el.isContentEditable) return true
  const tag = (el.tagName || '').toUpperCase()
  if (tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (tag !== 'INPUT') return false
  // Los checkbox y radio no reciben texto: un escaneo sobre ellos se puede
  // capturar igual.
  const tipo = (el.type || 'text').toLowerCase()
  return !['checkbox', 'radio', 'button', 'submit', 'reset', 'file'].includes(tipo)
}

/**
 * @param {(codigo: string) => void} onEscaneo  Se llama con el código leído.
 * @param {object} opciones
 *   activo              — permite apagar el hook sin desmontarlo (default true)
 *   intervaloMaximoMs   — ver arriba
 *   largoMinimo         — ver arriba
 */
export function useEscaner(onEscaneo, opciones = {}) {
  const {
    activo = true,
    intervaloMaximoMs = INTERVALO_MAXIMO_MS,
    largoMinimo = LARGO_MINIMO,
  } = opciones

  // El callback va por ref para que cambiarlo en cada render no obligue a
  // desuscribir y volver a suscribir el listener en cada pasada.
  const callbackRef = useRef(onEscaneo)
  useEffect(() => { callbackRef.current = onEscaneo }, [onEscaneo])

  const buffer = useRef('')
  const ultimaTecla = useRef(0)
  const temporizador = useRef(null)

  const limpiar = useCallback(() => {
    buffer.current = ''
    if (temporizador.current) {
      clearTimeout(temporizador.current)
      temporizador.current = null
    }
  }, [])

  useEffect(() => {
    if (!activo) {
      limpiar()
      return undefined
    }

    const alPresionar = (e) => {
      // Con el foco en un campo de texto el escaneo es texto normal: no es
      // asunto de este hook.
      if (esCampoDeTexto(e.target) || esCampoDeTexto(document.activeElement)) {
        limpiar()
        return
      }
      // Los modificadores descartan la ráfaga: Ctrl+P no es un código.
      if (e.ctrlKey || e.altKey || e.metaKey) {
        limpiar()
        return
      }

      const ahora = Date.now()
      const transcurrido = ahora - ultimaTecla.current
      ultimaTecla.current = ahora

      if (e.key === 'Enter') {
        const codigo = buffer.current
        limpiar()
        if (codigo.length >= largoMinimo) {
          // El Enter del lector no tiene que enviar el formulario que haya
          // detrás ni activar el botón que quedó con foco.
          e.preventDefault()
          callbackRef.current?.(codigo)
        }
        return
      }

      // Solo caracteres imprimibles: las flechas, F1, Escape y compañía llegan
      // como nombres de varias letras y no forman parte de ningún código.
      if (e.key.length !== 1) return

      // Demasiado lento para ser el lector: se arranca una ráfaga nueva.
      if (transcurrido > intervaloMaximoMs) {
        buffer.current = ''
      }

      buffer.current += e.key
      // Con el foco fuera de un campo estas teclas no iban a escribir en
      // ningún lado, pero sí pueden disparar atajos del navegador (la barra
      // espaciadora hace scroll, por ejemplo).
      e.preventDefault()

      if (temporizador.current) clearTimeout(temporizador.current)
      temporizador.current = setTimeout(limpiar, MS_HASTA_DESCARTAR)
    }

    document.addEventListener('keydown', alPresionar)
    return () => {
      document.removeEventListener('keydown', alPresionar)
      limpiar()
    }
  }, [activo, intervaloMaximoMs, largoMinimo, limpiar])
}

/**
 * Handler para un input donde el lector escribe directamente (el buscador de
 * stock, el campo "código de barras" de la ficha de producto).
 *
 * El lector cierra con Enter, así que alcanza con actuar sobre esa tecla. Se
 * llama a preventDefault() para que el Enter no envíe el formulario: en la
 * ficha de producto eso guardaría el alta a medio completar.
 *
 * Uso:
 *   <input onKeyDown={alEnterDeEscaneo(codigo => buscar(codigo))} />
 */
export function alEnterDeEscaneo(onEscaneo, { limpiarCampo = false } = {}) {
  return (e) => {
    if (e.key !== 'Enter') return
    const codigo = (e.target.value || '').trim()
    e.preventDefault()
    if (!codigo) return
    if (limpiarCampo) e.target.value = ''
    onEscaneo(codigo)
  }
}

export default useEscaner
