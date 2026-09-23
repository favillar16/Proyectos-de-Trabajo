/**
 * Paleta y formateadores compartidos por las pantallas de facturación.
 *
 * Existe para no copiar el objeto `C` en cada componente nuevo. Cada página
 * del sistema define el suyo —es la convención que ya había— pero las tres
 * vistas de facturación son partes de una misma pantalla, y tener tres copias
 * del mismo marrón garantiza que un día queden distintas.
 */
export const C = {
  sidebar: '#453941', gold: '#B99C74', goldDark: '#8a7355',
  goldMuted: 'rgba(185,156,116,0.10)',
  border: '#e8e4df', bg: '#ffffff', bgSec: '#fafaf9', bgTer: '#f5f4f2',
  text: '#1a1714', textSec: '#6b6560', textMuted: '#9e9892',
  success: '#3d7a5a', successBg: '#edf7f1',
  warning: '#8a6a1a', warningBg: '#fef9ee',
  danger: '#9a3030', dangerBg: '#fef0f0',
  info: '#2a5c8a', infoBg: '#eef4fb',
}

export function formatGs(v) {
  return `Gs. ${Number(v || 0).toLocaleString('es-PY')}`
}

export function formatFecha(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('es-PY', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

/** Estilo base de los campos de texto, para que los formularios se vean igual. */
export const campo = {
  width: '100%', padding: '9px 11px', borderRadius: '8px',
  border: `1px solid ${C.border}`, fontSize: '13px', fontFamily: 'inherit',
  color: C.text, background: C.bg, boxSizing: 'border-box', outline: 'none',
}

/** Etiqueta de un campo. */
export const etiqueta = {
  display: 'block', fontSize: '12px', fontWeight: '500',
  color: C.textSec, marginBottom: '5px',
}
