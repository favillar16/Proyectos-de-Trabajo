/**
 * useLectorCodigoBarras
 *
 * Detecta las lecturas del lector de código de barras (FTX LC123BH5).
 *
 * Cómo funciona el lector: para la computadora es un teclado. Cuando se
 * dispara, "tipea" los caracteres del código uno atrás del otro y termina con
 * un Enter. No hay driver ni puerto que escuchar: llegan eventos de teclado
 * como si alguien escribiera muy rápido.
 *
 * Cómo se lo distingue de una persona escribiendo: por la velocidad. Una
 * persona tarda como mínimo unos 100 ms entre tecla y tecla; el lector manda
 * todo el código en pocos milisegundos. Si entre teclas pasa más del tiempo
 * configurado, se descarta lo acumulado y se asume que era alguien tipeando.
 *
 * Por qué se escucha en toda la pantalla y no en un campo: para que el
 * operario del depósito apunte y dispare sin tener que hacer clic antes en el
 * campo correcto. Igual, si el foco está en un campo de texto donde la persona
 * está escribiendo a mano, la detección no interfiere: lo que se teclea a mano
 * es lento y nunca se toma como una lectura.
 *
 * Uso:
 *   useLectorCodigoBarras({
 *     onLectura: (codigo) => { ... },
 *     activo: true,
 *   })
 */
import { useEffect, useRef } from 'react'

// Tiempo máximo entre dos teclas para seguir considerándolas una misma
// lectura. 50 ms deja cómodo al lector (que manda todo casi junto) y descarta
// a cualquier persona escribiendo, incluso rápido.
const MS_ENTRE_TECLAS = 50

// Un código de barras real nunca es de 2 o 3 caracteres. Este mínimo evita
// que una pulsación suelta seguida de Enter se tome como lectura.
const LARGO_MINIMO = 4

export function useLectorCodigoBarras({ onLectura, activo = true, largoMinimo = LARGO_MINIMO } = {}) {
  const acumulado = useRef('')
  const ultimaTecla = useRef(0)
  // El callback se guarda en una ref para no tener que volver a suscribir el
  // listener en cada render cuando la pantalla pasa una función nueva.
  const callback = useRef(onLectura)

  useEffect(() => { callback.current = onLectura }, [onLectura])

  useEffect(() => {
    if (!activo) return

    const alPresionar = (e) => {
      // Combinaciones de teclado del usuario (Ctrl+C, Alt+Tab...) no son lecturas
      if (e.ctrlKey || e.altKey || e.metaKey) return

      const ahora = Date.now()
      const pausa = ahora - ultimaTecla.current
      ultimaTecla.current = ahora

      // Pasó demasiado tiempo desde la tecla anterior: no viene del lector
      if (pausa > MS_ENTRE_TECLAS) acumulado.current = ''

      if (e.key === 'Enter') {
        const codigo = acumulado.current.trim()
        acumulado.current = ''
        if (codigo.length >= largoMinimo) {
          // Se frena el Enter para que no dispare de paso el botón que
          // estuviera enfocado ni envíe el formulario.
          e.preventDefault()
          e.stopPropagation()
          callback.current?.(codigo)
        }
        return
      }

      // Solo caracteres imprimibles: 'a', '7', '-'. Se ignoran Shift, F5,
      // las flechas y demás teclas de control, que llegan con nombre largo.
      if (e.key.length === 1) acumulado.current += e.key
    }

    // En fase de captura, para leer el evento antes de que un campo de texto
    // o un formulario se lo quede.
    window.addEventListener('keydown', alPresionar, true)
    return () => window.removeEventListener('keydown', alPresionar, true)
  }, [activo, largoMinimo])
}

export default useLectorCodigoBarras
