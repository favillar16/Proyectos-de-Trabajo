/**
 * GaleriaImagenes v2
 * Galería con lightbox fullscreen optimizada para tablets Android.
 *
 * Mejoras respecto a v1:
 * - Swipe basado en velocidad (más confiable en Android Chrome)
 * - Preload de imagen siguiente/anterior para transición sin flash
 * - Prevención de scroll de página durante swipe horizontal
 * - Indicadores de puntos en lugar de counter en galería compacta
 * - Animación de slide CSS pura (sin JS layout thrashing)
 * - touch-action: pan-y en contenedores que permiten scroll vertical
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { ChevronLeft, ChevronRight, X, ZoomIn, Image } from 'lucide-react'
import { useSwipe } from '../../hooks/useDevice'

const C = {
  sidebar:   '#453941',
  gold:      '#B99C74',
  border:    '#e8e4df',
  bg:        '#ffffff',
  bgSec:     '#fafaf9',
  bgTer:     '#f5f4f2',
  textMuted: '#9e9892',
}

// ─── Preload silencioso de imágenes adyacentes ────────────────────────────────
function precargarImagen(url) {
  if (!url) return
  const img = new window.Image()
  img.src = url
}

// ─── Lightbox fullscreen ──────────────────────────────────────────────────────
function Lightbox({ imagenes, indiceInicial, onCerrar }) {
  const [indice, setIndice] = useState(indiceInicial)
  const [animDir, setAnimDir] = useState(null) // 'izq' | 'der' | null

  const irA = useCallback((nuevoIdx) => {
    const dir = nuevoIdx > indice ? 'izq' : 'der'
    setAnimDir(dir)
    setTimeout(() => { setIndice(nuevoIdx); setAnimDir(null) }, 180)
  }, [indice])

  const anterior = useCallback(() => {
    const idx = (indice - 1 + imagenes.length) % imagenes.length
    irA(idx)
  }, [indice, imagenes.length, irA])

  const siguiente = useCallback(() => {
    const idx = (indice + 1) % imagenes.length
    irA(idx)
  }, [indice, imagenes.length, irA])

  // Precargar adyacentes
  useEffect(() => {
    const sig = imagenes[(indice + 1) % imagenes.length]
    const ant = imagenes[(indice - 1 + imagenes.length) % imagenes.length]
    precargarImagen(sig?.imagen_url || sig?.imagen)
    precargarImagen(ant?.imagen_url || ant?.imagen)
  }, [indice, imagenes])

  // Teclado
  useEffect(() => {
    const h = (e) => {
      if (e.key === 'ArrowLeft')  anterior()
      if (e.key === 'ArrowRight') siguiente()
      if (e.key === 'Escape')     onCerrar()
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [anterior, siguiente, onCerrar])

  const swipe = useSwipe({
    onLeft:  siguiente,
    onRight: anterior,
    umbralPx: 45,
    umbralVelocidad: 0.25,
  })

  const img = imagenes[indice]
  const url = img?.imagen_url || img?.imagen

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.95)',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        touchAction: 'none',
      }}
      onClick={onCerrar}
      {...swipe}
    >
      {/* Cerrar */}
      <button
        onClick={e => { e.stopPropagation(); onCerrar() }}
        style={{
          position: 'absolute', top: '16px', right: '16px', zIndex: 10,
          background: 'rgba(255,255,255,0.12)', border: 'none',
          borderRadius: '50%', width: '48px', height: '48px',
          cursor: 'pointer', color: '#fff',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        <X size={22} />
      </button>

      {/* Imagen */}
      <div
        onClick={e => e.stopPropagation()}
        style={{
          maxWidth: '92vw', maxHeight: '80vh',
          opacity: animDir ? 0 : 1,
          transform: animDir === 'izq' ? 'translateX(-20px)'
                   : animDir === 'der' ? 'translateX(20px)' : 'none',
          transition: animDir ? 'none' : 'opacity 180ms, transform 180ms',
        }}
      >
        <img
          src={url} alt={img?.titulo || ''}
          style={{
            maxWidth: '92vw', maxHeight: '80vh',
            objectFit: 'contain', borderRadius: '8px',
            userSelect: 'none', WebkitUserSelect: 'none',
            display: 'block',
          }}
          draggable={false}
        />
        {img?.titulo && (
          <p style={{
            textAlign: 'center', color: 'rgba(255,255,255,0.5)',
            fontSize: '12px', marginTop: '10px',
          }}>
            {img.titulo}
          </p>
        )}
      </div>

      {/* Flechas — mínimo 48px para touch */}
      {imagenes.length > 1 && (
        <>
          <button
            onClick={e => { e.stopPropagation(); anterior() }}
            style={{
              position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)',
              background: 'rgba(255,255,255,0.12)', border: 'none',
              borderRadius: '50%', width: '48px', height: '48px',
              cursor: 'pointer', color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            <ChevronLeft size={24} />
          </button>
          <button
            onClick={e => { e.stopPropagation(); siguiente() }}
            style={{
              position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)',
              background: 'rgba(255,255,255,0.12)', border: 'none',
              borderRadius: '50%', width: '48px', height: '48px',
              cursor: 'pointer', color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            <ChevronRight size={24} />
          </button>
        </>
      )}

      {/* Miniaturas */}
      {imagenes.length > 1 && (
        <div
          onClick={e => e.stopPropagation()}
          style={{
            position: 'absolute', bottom: '20px',
            display: 'flex', gap: '8px', alignItems: 'center',
            maxWidth: '88vw', overflowX: 'auto', padding: '4px',
          }}
        >
          {imagenes.map((img, i) => (
            <div
              key={i}
              onClick={() => irA(i)}
              style={{
                width: '56px', height: '56px', flexShrink: 0,
                borderRadius: '7px', overflow: 'hidden', cursor: 'pointer',
                border: `2px solid ${i === indice ? C.gold : 'rgba(255,255,255,0.2)'}`,
                opacity: i === indice ? 1 : 0.5,
                transition: 'all 150ms',
              }}
            >
              <img
                src={img.imagen_url || img.imagen} alt=""
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                draggable={false}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Galería principal ────────────────────────────────────────────────────────
export default function GaleriaImagenes({
  imagenes = [],
  altura   = 340,
  compact  = false,   // sin tira de miniaturas (para panel de variantes)
}) {
  const [indiceActivo,    setIndiceActivo]    = useState(0)
  const [lightboxAbierto, setLightboxAbierto] = useState(false)
  const [lightboxIndice,  setLightboxIndice]  = useState(0)

  // Resetear al cambiar producto
  useEffect(() => { setIndiceActivo(0) }, [imagenes])

  // Precargar siguiente imagen al cambiar
  useEffect(() => {
    const sig = imagenes[(indiceActivo + 1) % imagenes.length]
    precargarImagen(sig?.imagen_url || sig?.imagen)
  }, [indiceActivo, imagenes])

  const swipe = useSwipe({
    onLeft:  () => setIndiceActivo(i => Math.min(i + 1, imagenes.length - 1)),
    onRight: () => setIndiceActivo(i => Math.max(i - 1, 0)),
    umbralPx: 45,
    umbralVelocidad: 0.25,
  })

  const abrirLightbox = useCallback((idx) => {
    setLightboxIndice(idx)
    setLightboxAbierto(true)
  }, [])

  if (!imagenes || imagenes.length === 0) {
    return (
      <div style={{
        height: altura, background: C.bgTer, borderRadius: '12px',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', gap: '10px',
        color: C.textMuted,
      }}>
        <Image size={32} style={{ opacity: 0.3 }} />
        <p style={{ fontSize: '13px' }}>Sin imágenes</p>
      </div>
    )
  }

  const imgActiva = imagenes[indiceActivo]
  const urlActiva = imgActiva?.imagen_url || imgActiva?.imagen

  return (
    <>
      {/* Imagen principal */}
      <div
        style={{
          height: altura, borderRadius: '12px', overflow: 'hidden',
          position: 'relative', background: C.bgTer, cursor: 'zoom-in',
          userSelect: 'none', WebkitUserSelect: 'none',
          // Permitir scroll vertical de la página, bloquear solo horizontal para swipe
          touchAction: 'pan-y',
        }}
        onClick={() => abrirLightbox(indiceActivo)}
        {...swipe}
      >
        <img
          src={urlActiva}
          alt={imgActiva?.titulo || ''}
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          draggable={false}
          loading="eager"
        />

        {/* Botón zoom — 44px mínimo */}
        <div style={{
          position: 'absolute', bottom: '10px', right: '10px',
          background: 'rgba(0,0,0,0.42)', borderRadius: '8px',
          width: '36px', height: '36px',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', pointerEvents: 'none',
        }}>
          <ZoomIn size={16} />
        </div>

        {/* Indicadores de puntos (más táctiles que flechas en galería embebida) */}
        {imagenes.length > 1 && (
          <div style={{
            position: 'absolute', bottom: '10px', left: '50%',
            transform: 'translateX(-50%)',
            display: 'flex', gap: '5px', alignItems: 'center',
          }}>
            {imagenes.map((_, i) => (
              <div
                key={i}
                onClick={e => { e.stopPropagation(); setIndiceActivo(i) }}
                style={{
                  width: i === indiceActivo ? '18px' : '6px',
                  height: '6px', borderRadius: '3px',
                  background: i === indiceActivo
                    ? C.gold
                    : 'rgba(255,255,255,0.5)',
                  transition: 'all 200ms',
                  cursor: 'pointer',
                  // Target táctil expandido con padding invisible
                  padding: '6px 4px',
                  margin: '-6px -4px',
                }}
              />
            ))}
          </div>
        )}

        {/* Flechas laterales — solo si hay más de 1 imagen */}
        {imagenes.length > 1 && (
          <>
            <button
              onClick={e => { e.stopPropagation(); setIndiceActivo(i => Math.max(i - 1, 0)) }}
              style={{
                position: 'absolute', left: '8px', top: '50%', transform: 'translateY(-50%)',
                background: 'rgba(0,0,0,0.38)', border: 'none',
                borderRadius: '50%', width: '40px', height: '40px',
                cursor: 'pointer', color: '#fff',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                opacity: indiceActivo === 0 ? 0.25 : 0.85,
                transition: 'opacity 120ms',
              }}
            >
              <ChevronLeft size={20} />
            </button>
            <button
              onClick={e => { e.stopPropagation(); setIndiceActivo(i => Math.min(i + 1, imagenes.length - 1)) }}
              style={{
                position: 'absolute', right: '8px', top: '50%', transform: 'translateY(-50%)',
                background: 'rgba(0,0,0,0.38)', border: 'none',
                borderRadius: '50%', width: '40px', height: '40px',
                cursor: 'pointer', color: '#fff',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                opacity: indiceActivo === imagenes.length - 1 ? 0.25 : 0.85,
                transition: 'opacity 120ms',
              }}
            >
              <ChevronRight size={20} />
            </button>
          </>
        )}
      </div>

      {/* Tira de miniaturas — solo en modo no-compact */}
      {!compact && imagenes.length > 1 && (
        <div style={{
          display: 'flex', gap: '8px', marginTop: '10px',
          overflowX: 'auto', paddingBottom: '2px',
          // Scroll táctil horizontal sin afectar el resto
          touchAction: 'pan-x',
          WebkitOverflowScrolling: 'touch',
        }}>
          {imagenes.map((img, i) => {
            const url = img.imagen_url || img.imagen
            const activa = i === indiceActivo
            return (
              <div
                key={i}
                onClick={() => setIndiceActivo(i)}
                style={{
                  // Mínimo 48px de ancho para target táctil
                  width: '60px', height: '60px', flexShrink: 0,
                  borderRadius: '8px', overflow: 'hidden', cursor: 'pointer',
                  border: `2px solid ${activa ? C.gold : C.border}`,
                  opacity: activa ? 1 : 0.55,
                  transition: 'all 150ms',
                }}
              >
                <img
                  src={url} alt=""
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  draggable={false}
                  loading="lazy"
                />
              </div>
            )
          })}
        </div>
      )}

      {/* Lightbox */}
      {lightboxAbierto && (
        <Lightbox
          imagenes={imagenes}
          indiceInicial={lightboxIndice}
          onCerrar={() => setLightboxAbierto(false)}
        />
      )}
    </>
  )
}
