/**
 * Cantidades en m² (o en la unidad de venta) tal como las guarda el backend.
 *
 * `ItemPedido.cantidad` y `Stock.cantidad` tienen cuatro decimales. Mostrar
 * dos —como se hacía con `toFixed(2)`— cambiaba lo vendido: tres piezas de
 * 0,245 m² son 0,735 m², y la pantalla decía 0,74 aunque se cobraba 0,735.
 */
export const DECIMALES_CANTIDAD = 4

// "0,735" · "12,60" · "17,00": al menos dos decimales, a lo sumo cuatro.
export function formatCantidad(v) {
  return Number(v || 0).toLocaleString('es-PY', {
    minimumFractionDigits: 2, maximumFractionDigits: DECIMALES_CANTIDAD,
  })
}
