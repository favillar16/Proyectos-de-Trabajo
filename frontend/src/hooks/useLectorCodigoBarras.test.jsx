/**
 * Tests del lector de código de barras (FTX LC123BH5).
 *
 * Alcance: acá se verifica NUESTRO lado. Que el lector físico mande las teclas
 * con el intervalo que asumimos, y que tenga configurado el Enter como sufijo,
 * es comportamiento del aparato y solo se comprueba escaneando algo de verdad
 * — está anotado en docs/perifericos.md.
 *
 * Lo que sí se prueba, que es lo que rompe en la práctica:
 *   · que una ráfaga rápida terminada en Enter se lea como una lectura;
 *   · que alguien tipeando a mano NO dispare una lectura, que es el falso
 *     positivo que arruinaría el buscador;
 *   · que el Enter del lector no se propague al formulario de atrás.
 */
import { render, cleanup, fireEvent } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useLectorCodigoBarras } from './useLectorCodigoBarras'

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

function Sonda({ onLectura, activo = true, largoMinimo }) {
  useLectorCodigoBarras({ onLectura, activo, largoMinimo })
  return <div data-testid="sonda">sonda</div>
}

/**
 * Simula una lectura: teclas separadas por `intervalo` ms de tiempo simulado.
 * Devuelve el resultado del fireEvent del Enter (false si algún handler llamó
 * a preventDefault).
 */
function escanear(codigo, { intervalo = 10, conEnter = true, destino } = {}) {
  const target = destino || document.body
  for (const ch of codigo) {
    vi.advanceTimersByTime(intervalo)
    fireEvent.keyDown(target, { key: ch })
  }
  if (!conEnter) return undefined
  vi.advanceTimersByTime(intervalo)
  return fireEvent.keyDown(target, { key: 'Enter' })
}

describe('lecturas del lector', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    // El hook mide el intervalo entre teclas con Date.now(), no con
    // setTimeout: el reloj falso tiene que avanzar junto con los timers.
    vi.setSystemTime(new Date('2026-08-25T10:00:00Z'))
  })

  it('lee un EAN-13 escaneado rápido', () => {
    const onLectura = vi.fn()
    render(<Sonda onLectura={onLectura} />)

    escanear('7501031311309')

    expect(onLectura).toHaveBeenCalledTimes(1)
    expect(onLectura).toHaveBeenCalledWith('7501031311309')
  })

  it('lee un código alfanumérico (Code128, o un SKU impreso)', () => {
    const onLectura = vi.fn()
    render(<Sonda onLectura={onLectura} />)

    escanear('POR-001-60X60')

    expect(onLectura).toHaveBeenCalledWith('POR-001-60X60')
  })

  it('frena el Enter para que no envíe el formulario de atrás', () => {
    render(<Sonda onLectura={vi.fn()} />)
    const noSePropago = escanear('7501031311309') === false
    expect(noSePropago).toBe(true)
  })

  it('ignora el tipeo humano: demasiado lento entre teclas', () => {
    const onLectura = vi.fn()
    render(<Sonda onLectura={onLectura} />)

    // 150 ms entre teclas es velocidad de persona.
    escanear('7501031311309', { intervalo: 150 })

    expect(onLectura).not.toHaveBeenCalled()
  })

  it('no dispara sin el Enter final', () => {
    const onLectura = vi.fn()
    render(<Sonda onLectura={onLectura} />)

    escanear('7501031311309', { conEnter: false })

    expect(onLectura).not.toHaveBeenCalled()
  })

  it('ignora ráfagas demasiado cortas para ser un código', () => {
    const onLectura = vi.fn()
    render(<Sonda onLectura={onLectura} />)

    escanear('75')

    expect(onLectura).not.toHaveBeenCalled()
  })

  it('respeta un largo mínimo distinto si se lo pasan', () => {
    const onLectura = vi.fn()
    render(<Sonda onLectura={onLectura} largoMinimo={2} />)

    escanear('75')

    expect(onLectura).toHaveBeenCalledWith('75')
  })

  it('descarta una ráfaga a medias y no la pega con la lectura siguiente', () => {
    const onLectura = vi.fn()
    render(<Sonda onLectura={onLectura} />)

    escanear('BASURA', { conEnter: false })
    vi.advanceTimersByTime(1000)          // pausa larga: corta la ráfaga
    escanear('7501031311309')

    expect(onLectura).toHaveBeenCalledTimes(1)
    expect(onLectura).toHaveBeenCalledWith('7501031311309')
  })

  it('dos lecturas seguidas disparan dos veces', () => {
    const onLectura = vi.fn()
    render(<Sonda onLectura={onLectura} />)

    escanear('7501031311309')
    escanear('5449000000996')

    expect(onLectura.mock.calls.map(c => c[0]))
      .toEqual(['7501031311309', '5449000000996'])
  })

  it('ignora teclas que no son caracteres (flechas, F1, Escape)', () => {
    const onLectura = vi.fn()
    render(<Sonda onLectura={onLectura} />)

    for (const key of ['ArrowDown', 'F1', 'Escape', 'Shift']) {
      vi.advanceTimersByTime(10)
      fireEvent.keyDown(document.body, { key })
    }
    escanear('7501031311309')

    expect(onLectura).toHaveBeenCalledWith('7501031311309')
  })

  it('un atajo con Ctrl no se confunde con una lectura', () => {
    const onLectura = vi.fn()
    render(<Sonda onLectura={onLectura} />)

    escanear('7501031', { conEnter: false })
    vi.advanceTimersByTime(10)
    fireEvent.keyDown(document.body, { key: 'p', ctrlKey: true })
    vi.advanceTimersByTime(10)
    fireEvent.keyDown(document.body, { key: 'Enter' })

    expect(onLectura).not.toHaveBeenCalled()
  })

  it('se puede apagar con activo=false', () => {
    const onLectura = vi.fn()
    render(<Sonda onLectura={onLectura} activo={false} />)

    escanear('7501031311309')

    expect(onLectura).not.toHaveBeenCalled()
  })

  it('deja de escuchar al desmontarse', () => {
    const onLectura = vi.fn()
    const { unmount } = render(<Sonda onLectura={onLectura} />)
    unmount()

    escanear('7501031311309')

    expect(onLectura).not.toHaveBeenCalled()
  })

  it('usa siempre el callback más reciente, sin resuscribir el listener', () => {
    const viejo = vi.fn()
    const nuevo = vi.fn()
    const { rerender } = render(<Sonda onLectura={viejo} />)
    rerender(<Sonda onLectura={nuevo} />)

    escanear('7501031311309')

    expect(viejo).not.toHaveBeenCalled()
    expect(nuevo).toHaveBeenCalledWith('7501031311309')
  })
})

describe('lectura con el foco dentro de un campo', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-25T10:00:00Z'))
  })

  it('sigue leyendo aunque el foco esté en un input', () => {
    // Es a propósito y es lo que permite disparar sin hacer clic antes en el
    // buscador. El precio es que el código además se escribe en el campo
    // enfocado; las pantallas que usan el lector lo contemplan poniendo el
    // código leído en ese mismo buscador.
    const onLectura = vi.fn()
    render(
      <>
        <Sonda onLectura={onLectura} />
        <input data-testid="campo" />
      </>,
    )
    const campo = document.querySelector('[data-testid="campo"]')
    campo.focus()

    escanear('7501031311309', { destino: campo })

    expect(onLectura).toHaveBeenCalledWith('7501031311309')
  })

  it('escribir a mano en un campo no dispara ninguna lectura', () => {
    const onLectura = vi.fn()
    render(
      <>
        <Sonda onLectura={onLectura} />
        <input data-testid="campo" />
      </>,
    )
    const campo = document.querySelector('[data-testid="campo"]')
    campo.focus()

    escanear('porcelanato', { intervalo: 150, destino: campo })

    expect(onLectura).not.toHaveBeenCalled()
  })
})
