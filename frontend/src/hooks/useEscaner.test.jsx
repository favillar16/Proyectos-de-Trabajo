/**
 * Tests del lector de código de barras (FTX-LC123BH5).
 *
 * Alcance: acá se verifica NUESTRO lado. Que el lector físico mande las
 * teclas con el intervalo que asumimos, y que tenga configurado el Enter
 * como sufijo, es comportamiento del aparato y solo se comprueba
 * escaneando algo de verdad — está anotado en docs/traspaso_pendientes.md.
 *
 * Lo que sí se prueba y es lo que rompe en la práctica:
 *   · que una ráfaga rápida terminada en Enter se lea como un escaneo;
 *   · que alguien tipeando a mano NO dispare un escaneo;
 *   · que con el foco en un campo de texto el hook se aparte, para no
 *     comerse lo que la vendedora está escribiendo.
 */
import { render, cleanup, fireEvent } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useEscaner, alEnterDeEscaneo, esCampoDeTexto } from './useEscaner'

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

function Sonda({ onEscaneo, activo = true }) {
  useEscaner(onEscaneo, { activo })
  return <div data-testid="sonda">sin campos</div>
}

/**
 * Simula un escaneo: teclas separadas por `intervalo` ms de tiempo simulado.
 * Devuelve el resultado del fireEvent del Enter (false si alguien llamó a
 * preventDefault).
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

describe('useEscaner — ráfagas del lector', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    // Date.now() tiene que avanzar con los timers falsos: el hook mide el
    // intervalo entre teclas con Date.now(), no con setTimeout.
    vi.setSystemTime(new Date('2026-08-25T10:00:00Z'))
  })

  it('lee un EAN-13 escaneado rápido', () => {
    const onEscaneo = vi.fn()
    render(<Sonda onEscaneo={onEscaneo} />)

    escanear('7501031311309')

    expect(onEscaneo).toHaveBeenCalledTimes(1)
    expect(onEscaneo).toHaveBeenCalledWith('7501031311309')
  })

  it('lee un código alfanumérico (Code128)', () => {
    const onEscaneo = vi.fn()
    render(<Sonda onEscaneo={onEscaneo} />)

    escanear('POR-001-60X60')

    expect(onEscaneo).toHaveBeenCalledWith('POR-001-60X60')
  })

  it('frena el Enter del lector para que no envíe el formulario de atrás', () => {
    render(<Sonda onEscaneo={vi.fn()} />)
    const noSePropago = escanear('7501031311309') === false
    expect(noSePropago).toBe(true)
  })

  it('ignora el tipeo humano: demasiado lento entre teclas', () => {
    const onEscaneo = vi.fn()
    render(<Sonda onEscaneo={onEscaneo} />)

    // 150 ms entre teclas es velocidad de persona.
    escanear('7501031311309', { intervalo: 150 })

    expect(onEscaneo).not.toHaveBeenCalled()
  })

  it('no dispara sin el Enter final', () => {
    const onEscaneo = vi.fn()
    render(<Sonda onEscaneo={onEscaneo} />)

    escanear('7501031311309', { conEnter: false })

    expect(onEscaneo).not.toHaveBeenCalled()
  })

  it('ignora ráfagas demasiado cortas para ser un código', () => {
    const onEscaneo = vi.fn()
    render(<Sonda onEscaneo={onEscaneo} />)

    escanear('75')

    expect(onEscaneo).not.toHaveBeenCalled()
  })

  it('descarta una ráfaga a medias y no la pega con el escaneo siguiente', () => {
    const onEscaneo = vi.fn()
    render(<Sonda onEscaneo={onEscaneo} />)

    escanear('BASURA', { conEnter: false })
    vi.advanceTimersByTime(1000)          // pasa el plazo de descarte
    escanear('7501031311309')

    expect(onEscaneo).toHaveBeenCalledTimes(1)
    expect(onEscaneo).toHaveBeenCalledWith('7501031311309')
  })

  it('dos escaneos seguidos disparan dos veces', () => {
    const onEscaneo = vi.fn()
    render(<Sonda onEscaneo={onEscaneo} />)

    escanear('7501031311309')
    escanear('5449000000996')

    expect(onEscaneo.mock.calls.map(c => c[0]))
      .toEqual(['7501031311309', '5449000000996'])
  })

  it('ignora teclas que no son caracteres (flechas, F1, Escape)', () => {
    const onEscaneo = vi.fn()
    render(<Sonda onEscaneo={onEscaneo} />)

    for (const key of ['ArrowDown', 'F1', 'Escape', 'Shift']) {
      vi.advanceTimersByTime(10)
      fireEvent.keyDown(document.body, { key })
    }
    escanear('7501031311309')

    expect(onEscaneo).toHaveBeenCalledWith('7501031311309')
  })

  it('un atajo con Ctrl no se confunde con un escaneo', () => {
    const onEscaneo = vi.fn()
    render(<Sonda onEscaneo={onEscaneo} />)

    escanear('7501031', { conEnter: false })
    vi.advanceTimersByTime(10)
    fireEvent.keyDown(document.body, { key: 'p', ctrlKey: true })
    vi.advanceTimersByTime(10)
    fireEvent.keyDown(document.body, { key: 'Enter' })

    expect(onEscaneo).not.toHaveBeenCalled()
  })

  it('se puede apagar con activo=false', () => {
    const onEscaneo = vi.fn()
    render(<Sonda onEscaneo={onEscaneo} activo={false} />)

    escanear('7501031311309')

    expect(onEscaneo).not.toHaveBeenCalled()
  })

  it('deja de escuchar al desmontarse', () => {
    const onEscaneo = vi.fn()
    const { unmount } = render(<Sonda onEscaneo={onEscaneo} />)
    unmount()

    escanear('7501031311309')

    expect(onEscaneo).not.toHaveBeenCalled()
  })
})

describe('useEscaner — respeta los campos de texto', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-25T10:00:00Z'))
  })

  it('no captura cuando el foco está en un input', () => {
    const onEscaneo = vi.fn()
    render(
      <>
        <Sonda onEscaneo={onEscaneo} />
        <input data-testid="campo" />
      </>,
    )
    const campo = document.querySelector('[data-testid="campo"]')
    campo.focus()

    escanear('7501031311309', { destino: campo })

    // El input recibe el texto como cualquier tipeo; el hook global se aparta
    // para no duplicar la lectura ni comerse lo que se está escribiendo.
    expect(onEscaneo).not.toHaveBeenCalled()
  })

  it('no captura en un textarea', () => {
    const onEscaneo = vi.fn()
    render(
      <>
        <Sonda onEscaneo={onEscaneo} />
        <textarea data-testid="notas" />
      </>,
    )
    const notas = document.querySelector('[data-testid="notas"]')
    notas.focus()

    escanear('7501031311309', { destino: notas })

    expect(onEscaneo).not.toHaveBeenCalled()
  })

  it('sí captura sobre un checkbox, que no recibe texto', () => {
    const onEscaneo = vi.fn()
    render(
      <>
        <Sonda onEscaneo={onEscaneo} />
        <input type="checkbox" data-testid="check" />
      </>,
    )
    const check = document.querySelector('[data-testid="check"]')

    escanear('7501031311309', { destino: check })

    expect(onEscaneo).toHaveBeenCalledWith('7501031311309')
  })
})

describe('esCampoDeTexto', () => {
  it('reconoce inputs de texto, textarea y select', () => {
    const input = document.createElement('input')
    const area = document.createElement('textarea')
    const select = document.createElement('select')
    expect(esCampoDeTexto(input)).toBe(true)
    expect(esCampoDeTexto(area)).toBe(true)
    expect(esCampoDeTexto(select)).toBe(true)
  })

  it('no considera campo de texto a un botón ni a un div común', () => {
    const boton = document.createElement('button')
    const div = document.createElement('div')
    expect(esCampoDeTexto(boton)).toBe(false)
    expect(esCampoDeTexto(div)).toBe(false)
    expect(esCampoDeTexto(null)).toBe(false)
  })
})

describe('alEnterDeEscaneo — el lector escribiendo dentro de un campo', () => {
  it('dispara con el contenido del campo al apretar Enter', () => {
    const onEscaneo = vi.fn()
    const handler = alEnterDeEscaneo(onEscaneo)
    handler({ key: 'Enter', target: { value: ' 7501031311309 ' }, preventDefault: vi.fn() })
    expect(onEscaneo).toHaveBeenCalledWith('7501031311309')
  })

  it('no hace nada con otras teclas', () => {
    const onEscaneo = vi.fn()
    const handler = alEnterDeEscaneo(onEscaneo)
    handler({ key: 'a', target: { value: '75' }, preventDefault: vi.fn() })
    expect(onEscaneo).not.toHaveBeenCalled()
  })

  it('frena el submit del formulario', () => {
    const preventDefault = vi.fn()
    const handler = alEnterDeEscaneo(vi.fn())
    handler({ key: 'Enter', target: { value: '7501031311309' }, preventDefault })
    expect(preventDefault).toHaveBeenCalled()
  })

  it('ignora un campo vacío', () => {
    const onEscaneo = vi.fn()
    const handler = alEnterDeEscaneo(onEscaneo)
    handler({ key: 'Enter', target: { value: '   ' }, preventDefault: vi.fn() })
    expect(onEscaneo).not.toHaveBeenCalled()
  })

  it('puede limpiar el campo para el escaneo siguiente', () => {
    const target = { value: '7501031311309' }
    const handler = alEnterDeEscaneo(vi.fn(), { limpiarCampo: true })
    handler({ key: 'Enter', target, preventDefault: vi.fn() })
    expect(target.value).toBe('')
  })
})
