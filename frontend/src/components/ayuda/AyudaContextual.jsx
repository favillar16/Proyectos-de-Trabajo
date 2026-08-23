/**
 * Ayuda contextual del sistema.
 *
 * Se abre con F1 o con el botón «?» flotante, y muestra la ayuda de la
 * pantalla en la que está parada la persona. El botón existe además de la
 * tecla porque las tablets del local no tienen teclas de función: ahí el
 * «?» es la única forma de llegar.
 *
 * El contenido vive en src/ayuda/contenido.js — este archivo solo lo
 * presenta. Para agregar ayuda de una pantalla nueva se toca ese archivo,
 * no este.
 */
import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { HelpCircle, X, Keyboard } from 'lucide-react'
import { useDevice } from '../../hooks/useDevice'
import { useAuthStore } from '../../store/authStore'
import { ayudaDeRuta, AYUDA_GENERAL, ATAJOS_GLOBALES } from '../../ayuda/contenido'

const C = {
  gold:          '#B99C74',
  goldLight:     '#d4bc98',
  goldMuted:     'rgba(185,156,116,0.12)',
  sidebar:       '#453941',
  sidebarBorder: 'rgba(185,156,116,0.15)',
  bg:            '#ffffff',
  bgSecondary:   '#fafaf9',
  border:        '#e8e4df',
  textPrimary:   '#1a1714',
  textSecondary: '#6b6560',
  textOnSidebar: '#e8e0d5',
}

const ANCHO_PANEL = 420

function Bloque({ bloque }) {
  return (
    <section style={{ marginBottom: '22px' }}>
      <h3 style={{
        margin: '0 0 8px', fontSize: '13px', fontWeight: 600,
        color: C.textPrimary, letterSpacing: '0.01em',
      }}>
        {bloque.titulo}
      </h3>
      <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
        {bloque.items.map((item, i) => (
          <li key={i} style={{
            position: 'relative',
            padding: '0 0 0 16px',
            marginBottom: '7px',
            fontSize: '13px',
            lineHeight: 1.55,
            color: C.textSecondary,
          }}>
            <span style={{
              position: 'absolute', left: 0, top: '7px',
              width: '5px', height: '5px', borderRadius: '50%',
              background: C.gold,
            }} />
            {item}
          </li>
        ))}
      </ul>
    </section>
  )
}

export default function AyudaContextual() {
  const [abierto, setAbierto] = useState(false)
  const [hover, setHover] = useState(false)
  const { pathname } = useLocation()
  const { usuario } = useAuthStore()
  const device = useDevice()

  // La barra inferior de tablet ocupa 62px; sin este corrimiento el botón
  // «?» le queda encima y no se puede tocar.
  const sobreTabletNav = device.isTouch && device.width < 1180

  // F1 abre y cierra; Esc cierra. Chrome usa F1 para su propia ayuda, así
  // que hay que cancelar el evento antes de que se lo lleve.
  useEffect(() => {
    const alPulsar = (e) => {
      if (e.key === 'F1') {
        e.preventDefault()
        setAbierto(a => !a)
      } else if (e.key === 'Escape') {
        setAbierto(false)
      }
    }
    window.addEventListener('keydown', alPulsar)
    return () => window.removeEventListener('keydown', alPulsar)
  }, [])

  // Al cambiar de pantalla se cierra: la ayuda que quedaba abierta era la de
  // la pantalla anterior y confunde más de lo que ayuda.
  useEffect(() => { setAbierto(false) }, [pathname])

  const ayuda = ayudaDeRuta(pathname, usuario?.rol)

  return (
    <>
      {/* ── Botón flotante «?» ── */}
      <button
        onClick={() => setAbierto(a => !a)}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        title="Ayuda de esta pantalla (F1)"
        aria-label="Abrir la ayuda de esta pantalla"
        style={{
          position: 'fixed',
          right: '18px',
          bottom: sobreTabletNav ? '76px' : '18px',
          zIndex: 1300,
          width: '46px', height: '46px',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          borderRadius: '50%',
          border: `1px solid ${C.sidebarBorder}`,
          background: hover || abierto ? C.gold : C.sidebar,
          color: hover || abierto ? C.sidebar : C.goldLight,
          cursor: 'pointer',
          boxShadow: '0 4px 14px rgba(0,0,0,0.18)',
          transition: 'background 140ms, color 140ms',
        }}
      >
        {abierto ? <X size={20} /> : <HelpCircle size={22} />}
      </button>

      {/* ── Fondo oscurecido ── */}
      {abierto && (
        <div
          onClick={() => setAbierto(false)}
          style={{
            position: 'fixed', inset: 0, zIndex: 1290,
            background: 'rgba(26,23,20,0.35)',
          }}
        />
      )}

      {/* ── Panel ── */}
      <aside
        role="dialog"
        aria-label="Ayuda"
        aria-hidden={!abierto}
        style={{
          position: 'fixed',
          top: 0, right: 0, bottom: 0,
          zIndex: 1295,
          width: `min(${ANCHO_PANEL}px, 100vw)`,
          background: C.bg,
          borderLeft: `1px solid ${C.border}`,
          boxShadow: abierto ? '-8px 0 28px rgba(0,0,0,0.12)' : 'none',
          transform: abierto ? 'translateX(0)' : `translateX(100%)`,
          transition: 'transform 200ms ease',
          display: 'flex', flexDirection: 'column',
          // Sin esto el panel cerrado sigue capturando clics sobre la página.
          visibility: abierto ? 'visible' : 'hidden',
        }}
      >
        {/* Encabezado */}
        <header style={{
          display: 'flex', alignItems: 'center', gap: '10px',
          padding: '16px 18px',
          background: C.sidebar,
          borderBottom: `1px solid ${C.sidebarBorder}`,
          flexShrink: 0,
        }}>
          <HelpCircle size={18} style={{ color: C.gold, flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: '14px', fontWeight: 600, color: C.textOnSidebar,
            }}>
              {ayuda ? ayuda.titulo : 'Ayuda'}
            </div>
            {ayuda?.resumen && (
              <div style={{
                fontSize: '11.5px', color: 'rgba(232,224,213,0.6)',
                marginTop: '2px',
              }}>
                {ayuda.resumen}
              </div>
            )}
          </div>
          <button
            onClick={() => setAbierto(false)}
            aria-label="Cerrar la ayuda"
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: '30px', height: '30px', flexShrink: 0,
              background: 'transparent', cursor: 'pointer',
              border: `1px solid ${C.sidebarBorder}`, borderRadius: '7px',
              color: C.textOnSidebar,
            }}
          >
            <X size={15} />
          </button>
        </header>

        {/* Cuerpo */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }}>
          {ayuda
            ? ayuda.bloques.map((b, i) => <Bloque key={i} bloque={b} />)
            : (
              <p style={{
                margin: '0 0 22px', fontSize: '13px', lineHeight: 1.55,
                color: C.textSecondary,
              }}>
                Esta pantalla todavía no tiene ayuda propia. Abajo están las
                dudas más comunes del sistema.
              </p>
            )}

          <div style={{
            height: '1px', background: C.border, margin: '4px 0 22px',
          }} />

          <h2 style={{
            margin: '0 0 14px', fontSize: '12px', fontWeight: 600,
            textTransform: 'uppercase', letterSpacing: '0.06em',
            color: C.gold,
          }}>
            {AYUDA_GENERAL.titulo}
          </h2>
          {AYUDA_GENERAL.bloques.map((b, i) => <Bloque key={i} bloque={b} />)}

          {/* Atajos — solo tienen sentido donde hay teclado */}
          {!device.isTouch && (
            <div style={{
              marginTop: '6px', padding: '12px 14px',
              background: C.bgSecondary,
              border: `1px solid ${C.border}`, borderRadius: '9px',
            }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: '7px',
                marginBottom: '9px',
                fontSize: '12px', fontWeight: 600, color: C.textPrimary,
              }}>
                <Keyboard size={14} style={{ color: C.gold }} />
                Atajos
              </div>
              {ATAJOS_GLOBALES.map((a, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: '9px',
                  marginBottom: '5px', fontSize: '12.5px', color: C.textSecondary,
                }}>
                  <kbd style={{
                    minWidth: '30px', textAlign: 'center',
                    padding: '2px 6px',
                    background: C.bg, border: `1px solid ${C.border}`,
                    borderRadius: '5px', fontSize: '11px',
                    fontFamily: 'inherit', color: C.textPrimary,
                  }}>
                    {a.teclas}
                  </kbd>
                  {a.descripcion}
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
