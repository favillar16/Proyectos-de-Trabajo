/**
 * useDevice
 * Detecta el tipo de dispositivo y orientación para adaptar la UI.
 *
 * Redmi Pad SE specs:
 *   - Pantalla: 11 pulgadas, resolución 1920×1200 (densidad ~206 ppi)
 *   - Viewport landscape: ~1280px CSS (con DPR ~1.5)
 *   - Viewport portrait:  ~800px CSS
 *   - Touch: sí, sin hover real
 */
import { useState, useEffect, useCallback } from 'react'

// Breakpoints basados en el Redmi Pad SE
const BP = {
  MOBILE:       600,   // < 600px
  TABLET_PORT:  860,   // 600–860px  → tablet portrait
  TABLET_LAND:  1180,  // 860–1180px → tablet landscape
  DESKTOP:      1180,  // > 1180px   → escritorio
}

function detectar() {
  const w = window.innerWidth
  const h = window.innerHeight
  const isTouch = ('ontouchstart' in window) || navigator.maxTouchPoints > 0
  const isTablet = isTouch && w >= BP.MOBILE
  const orientation = w >= h ? 'landscape' : 'portrait'

  return {
    width:       w,
    height:      h,
    isTouch,
    isTablet,
    isMobile:    w < BP.MOBILE,
    isDesktop:   !isTouch || w >= BP.DESKTOP,
    orientation,
    isLandscape: orientation === 'landscape',
    isPortrait:  orientation === 'portrait',
    // Cuántas columnas caben cómodamente en el grid del showroom
    columnasSugeridas: w >= 1100 ? 5 : w >= 860 ? 4 : w >= 600 ? 3 : 2,
    // Tamaño mínimo recomendado de target táctil (px)
    minTouchTarget: isTouch ? 48 : 36,
  }
}

export function useDevice() {
  const [device, setDevice] = useState(detectar)

  useEffect(() => {
    const handler = () => setDevice(detectar())
    window.addEventListener('resize',           handler, { passive: true })
    window.addEventListener('orientationchange',handler, { passive: true })
    return () => {
      window.removeEventListener('resize',           handler)
      window.removeEventListener('orientationchange',handler)
    }
  }, [])

  return device
}

/**
 * useSwipe
 * Hook de swipe táctil con umbral de velocidad y distancia.
 * Más confiable que solo medir distancia, especialmente en Android Chrome.
 *
 * @param {{ onLeft, onRight, onUp, onDown, umbralPx, umbralVelocidad }} opciones
 */
export function useSwipe({
  onLeft, onRight, onUp, onDown,
  umbralPx         = 50,
  umbralVelocidad  = 0.3,  // px/ms
} = {}) {
  const touchData = { x: 0, y: 0, t: 0 }

  const onTouchStart = useCallback((e) => {
    touchData.x = e.touches[0].clientX
    touchData.y = e.touches[0].clientY
    touchData.t = Date.now()
  }, [])

  const onTouchEnd = useCallback((e) => {
    const dx       = e.changedTouches[0].clientX - touchData.x
    const dy       = e.changedTouches[0].clientY - touchData.y
    const dt       = Date.now() - touchData.t
    const velX     = Math.abs(dx) / dt
    const velY     = Math.abs(dy) / dt
    const esPrincipalmenteH = Math.abs(dx) > Math.abs(dy)

    if (esPrincipalmenteH && Math.abs(dx) > umbralPx && velX > umbralVelocidad) {
      dx < 0 ? onLeft?.() : onRight?.()
    } else if (!esPrincipalmenteH && Math.abs(dy) > umbralPx && velY > umbralVelocidad) {
      dy < 0 ? onUp?.() : onDown?.()
    }
  }, [onLeft, onRight, onUp, onDown, umbralPx, umbralVelocidad])

  return { onTouchStart, onTouchEnd }
}
