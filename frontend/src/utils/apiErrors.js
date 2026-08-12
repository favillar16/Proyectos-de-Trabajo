/**
 * mensajeErrorApi
 * Traduce un error de axios/DRF a un mensaje legible en español para mostrar
 * en un toast, en vez de volcar el JSON crudo que devuelve el backend.
 * Usado en los formularios de creación de nota de pedido (NuevoPedidoForm,
 * ShowroomPage) donde el error puede venir de varios serializers distintos.
 */
const ETIQUETAS = {
  cliente_nombre:        'Nombre del cliente',
  cliente_ruc:            'RUC',
  cliente_telefono:      'Teléfono',
  cliente_observaciones: 'Observaciones',
  descuento:             'Descuento',
  total_ajustado:        'Monto ajustado',
  stock_insuficiente:    'Stock insuficiente',
  non_field_errors:      'Datos del pedido',
}

export function mensajeErrorApi(err, fallback = 'Ocurrió un error inesperado.') {
  const data = err?.response?.data
  if (!data) return fallback
  if (typeof data === 'string') return data
  if (Array.isArray(data)) return data.join(' · ') || fallback

  // 'detail' es la clave genérica de DRF para errores de sesión/permiso
  // (401 token vencido, 403 sin permiso) — no es un campo del formulario,
  // así que se muestra directo en vez de "detail: ...".
  if (typeof data.detail === 'string' && Object.keys(data).length === 1) {
    return data.detail
  }
  if (typeof data.detail === 'string' && data.code) {
    return data.detail
  }

  const partes = []

  Object.entries(data).forEach(([campo, valor]) => {
    // Errores por ítem: [{}, {"cantidad": ["..."]}, {}] — uno por cada línea del carrito
    if (campo === 'items' && Array.isArray(valor)) {
      valor.forEach((itemErr, i) => {
        if (itemErr && typeof itemErr === 'object' && Object.keys(itemErr).length) {
          const detalle = Object.values(itemErr)
            .map(m => (Array.isArray(m) ? m.join(' ') : String(m)))
            .join(' ')
          partes.push(`Ítem ${i + 1}: ${detalle}`)
        }
      })
      return
    }

    const texto = Array.isArray(valor) ? valor.join(' ') : String(valor)
    const etiqueta = ETIQUETAS[campo] ?? campo
    partes.push(`${etiqueta}: ${texto}`)
  })

  return partes.join(' · ') || fallback
}
