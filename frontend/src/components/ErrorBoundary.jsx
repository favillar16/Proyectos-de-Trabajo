import { Component } from 'react'

const C = {
  bg: '#ffffff', text: '#1a1714', textSec: '#6b6560',
  gold: '#B99C74', sidebar: '#453941', border: '#e8e4df',
}

/**
 * Red de seguridad: sin esto, cualquier error de JS sin capturar en
 * cualquier pantalla tumba toda la app a una página en blanco sin mensaje.
 * Envuelve las rutas en App.jsx.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('Error no controlado:', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          minHeight: '100vh', display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: '14px',
          padding: '24px', textAlign: 'center', background: C.bg, color: C.text,
          fontFamily: 'system-ui, sans-serif',
        }}>
          <p style={{ fontSize: '17px', fontWeight: 600 }}>Ocurrió un error</p>
          <p style={{ fontSize: '14px', color: C.textSec, maxWidth: '360px' }}>
            Algo falló al mostrar esta pantalla. Podés intentar recargar —
            si el problema sigue, avisá qué estabas haciendo justo antes.
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '9px 20px', background: C.sidebar,
              border: `1px solid ${C.gold}`, borderRadius: '9px',
              color: C.gold, fontSize: '14px', cursor: 'pointer',
            }}
          >
            Recargar
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
