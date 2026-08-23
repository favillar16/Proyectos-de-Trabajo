/**
 * Tests de la ayuda contextual.
 *
 * Alcance, para que quede claro qué cubren y qué no: acá se verifica
 * NUESTRO lado del contrato con el navegador — que ante F1 se llame a
 * preventDefault() y se abra el panel. Que Chrome efectivamente respete ese
 * preventDefault() y no abra su propia ayuda es comportamiento del
 * navegador y solo se puede comprobar abriéndolo. Está registrado como
 * pendiente en docs/traspaso_pendientes.md §2.
 */
import { render, screen, cleanup } from '@testing-library/react'
import { fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import AyudaContextual from './AyudaContextual'
import { AYUDA_POR_RUTA, ayudaDeRuta } from '../../ayuda/contenido'
import { useAuthStore } from '../../store/authStore'

afterEach(cleanup)

function montar({ ruta = '/productos', rol = 'admin' } = {}) {
  useAuthStore.setState({ usuario: { rol, nombre_completo: 'Test' } })
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <AyudaContextual />
    </MemoryRouter>,
  )
}

const panel = () => document.querySelector('[role="dialog"]')
const estaAbierto = () => panel().getAttribute('aria-hidden') === 'false'

function pulsar(key) {
  // fireEvent devuelve false si algún handler llamó a preventDefault().
  return fireEvent.keyDown(window, { key })
}

describe('apertura y cierre', () => {
  it('arranca cerrado', () => {
    montar()
    expect(estaAbierto()).toBe(false)
  })

  it('F1 lo abre', () => {
    montar()
    pulsar('F1')
    expect(estaAbierto()).toBe(true)
  })

  it('F1 de nuevo lo cierra', () => {
    montar()
    pulsar('F1')
    pulsar('F1')
    expect(estaAbierto()).toBe(false)
  })

  it('F1 cancela el evento para que Chrome no abra su propia ayuda', () => {
    // Es lo único que podemos garantizar desde el código; que el navegador
    // lo respete se verifica a mano.
    montar()
    const noCancelado = pulsar('F1')
    expect(noCancelado).toBe(false)
  })

  it('Escape lo cierra', () => {
    montar()
    pulsar('F1')
    pulsar('Escape')
    expect(estaAbierto()).toBe(false)
  })

  it('Escape no cancela el evento (otros paneles también lo usan)', () => {
    montar()
    expect(pulsar('Escape')).toBe(true)
  })

  it('otras teclas no lo abren', () => {
    montar()
    for (const key of ['F2', 'F3', 'a', 'Enter']) {
      pulsar(key)
      expect(estaAbierto()).toBe(false)
    }
  })

  it('el botón «?» lo abre — es la única vía en tablet, que no tiene F1', () => {
    montar()
    fireEvent.click(screen.getByLabelText(/abrir la ayuda/i))
    expect(estaAbierto()).toBe(true)
  })

  it('el botón de cerrar lo cierra', () => {
    montar()
    pulsar('F1')
    fireEvent.click(screen.getByLabelText(/cerrar la ayuda/i))
    expect(estaAbierto()).toBe(false)
  })

  it('deja de escuchar al desmontarse', () => {
    const { unmount } = montar()
    unmount()
    // Si el listener quedara vivo, esto tiraría por acceder a un componente
    // desmontado o dejaría un handler huérfano por cada navegación.
    expect(() => pulsar('F1')).not.toThrow()
  })
})

describe('contenido según la pantalla', () => {
  it('muestra la ayuda de la ruta actual', () => {
    montar({ ruta: '/caja', rol: 'cajero' })
    pulsar('F1')
    expect(screen.getByText('Caja')).toBeTruthy()
    expect(screen.getByText(/Antes de poder cobrar/)).toBeTruthy()
  })

  it('una ruta sin ayuda propia no rompe: cae en la ayuda general', () => {
    montar({ ruta: '/una-ruta-inventada' })
    pulsar('F1')
    expect(screen.getByText(/todavía no tiene ayuda propia/i)).toBeTruthy()
    expect(screen.getByText(/Si algo no funciona/i)).toBeTruthy()
  })

  it('la ayuda general aparece siempre', () => {
    montar({ ruta: '/caja', rol: 'cajero' })
    pulsar('F1')
    expect(screen.getByText(/Si algo no funciona/i)).toBeTruthy()
  })
})

describe('filtrado por rol', () => {
  it('al cajero le muestra la ayuda de caja', () => {
    expect(ayudaDeRuta('/caja', 'cajero')).not.toBeNull()
  })

  it('al vendedor NO le muestra la ayuda de caja', () => {
    // No puede ejecutar nada de eso; mostrárselo solo confunde.
    expect(ayudaDeRuta('/caja', 'vendedor')).toBeNull()
  })

  it('solo el admin ve la ayuda de costos y usuarios', () => {
    for (const ruta of ['/costos', '/usuarios']) {
      expect(ayudaDeRuta(ruta, 'admin')).not.toBeNull()
      expect(ayudaDeRuta(ruta, 'cajero')).toBeNull()
    }
  })

  it('el showroom es para todos', () => {
    for (const rol of ['admin', 'vendedor', 'cajero', 'deposito']) {
      expect(ayudaDeRuta('/showroom', rol)).not.toBeNull()
    }
  })

  it('sin rol conocido no se filtra nada', () => {
    expect(ayudaDeRuta('/caja', undefined)).not.toBeNull()
  })
})

describe('integridad del contenido', () => {
  it('cada pantalla tiene título, resumen y al menos un bloque', () => {
    for (const [ruta, ayuda] of Object.entries(AYUDA_POR_RUTA)) {
      expect(ayuda.titulo, `${ruta} sin título`).toBeTruthy()
      expect(ayuda.resumen, `${ruta} sin resumen`).toBeTruthy()
      expect(ayuda.bloques.length, `${ruta} sin bloques`).toBeGreaterThan(0)
    }
  })

  it('ningún bloque queda vacío', () => {
    for (const [ruta, ayuda] of Object.entries(AYUDA_POR_RUTA)) {
      for (const bloque of ayuda.bloques) {
        expect(bloque.titulo, `${ruta}: bloque sin título`).toBeTruthy()
        expect(bloque.items.length, `${ruta}/${bloque.titulo} sin items`)
          .toBeGreaterThan(0)
        for (const item of bloque.items) {
          expect(typeof item).toBe('string')
          expect(item.trim().length).toBeGreaterThan(0)
        }
      }
    }
  })

  it('cubre todas las pantallas del sistema', () => {
    // Si se agrega una página nueva y se olvida su ayuda, esto lo marca.
    const esperadas = ['/showroom', '/productos', '/pedidos', '/caja',
                       '/inventario', '/dashboard', '/usuarios', '/costos']
    for (const ruta of esperadas) {
      expect(AYUDA_POR_RUTA[ruta], `Falta la ayuda de ${ruta}`).toBeTruthy()
    }
  })

  it('los roles declarados existen en el sistema', () => {
    const roles = ['admin', 'encargada_ventas', 'vendedor', 'cajero', 'deposito']
    for (const [ruta, ayuda] of Object.entries(AYUDA_POR_RUTA)) {
      for (const rol of ayuda.roles || []) {
        expect(roles, `${ruta} declara el rol desconocido ${rol}`).toContain(rol)
      }
    }
  })
})
