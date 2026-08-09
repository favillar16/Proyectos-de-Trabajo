/**
 * camposPorTipo
 * Define qué bloques de atributos mostrar en el formulario de variante
 * según el `tipo` de la categoría elegida (ver docs/Listado de Productos.docx).
 * Todo lo que no está listado usa los valores por defecto (sin dimensiones,
 * sin combo extra) — son categorías donde alcanza con color/acabado/cantidad,
 * que ya son campos genéricos y siempre visibles.
 */

// Categorías donde tiene sentido pedir Largo/Ancho
const TIPOS_CON_DIMENSIONES = new Set([
  'piso', 'porcelanato', 'ceramica',
  'bacha', 'pileta_cocina', 'pileta_ropa',
  'griferia', 'ducha', 'nicho_bano', 'espejo',
])

// Combo extra específico por tipo (grifo | ducha | cisterna | null)
const COMBO_POR_TIPO = {
  griferia: 'grifo',
  ducha:    'ducha',
  inodoro:  'cisterna',
}

export function tieneDimensiones(categoriaTipo) {
  return TIPOS_CON_DIMENSIONES.has(categoriaTipo)
}

export function comboExtra(categoriaTipo) {
  return COMBO_POR_TIPO[categoriaTipo] || null
}
