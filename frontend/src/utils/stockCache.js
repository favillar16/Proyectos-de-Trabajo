/**
 * Refresca en esta pantalla todo lo que muestra stock.
 *
 * Crear, cancelar o cobrar un pedido, quitarle un ítem, registrar una
 * devolución o ajustar el inventario cambian el disponible, y cada ventana
 * lo tiene en su propia consulta de React Query (Showroom, Productos,
 * Inventario, consulta rápida, tablero). Invalidando solo `['pedidos']`, las
 * demás seguían mostrando el número viejo hasta vencer su `staleTime` —
 * el vendedor acababa de reservar y el showroom le ofrecía lo mismo otra vez.
 *
 * Las claves son prefijos: invalidan cualquier variante de la consulta.
 * Solo se vuelven a pedir las que están montadas, así que llamarla es barato.
 */
const CLAVES_CON_STOCK = [
  ['showroom'],
  ['stock-detalle'],
  ['producto-detalle'],
  ['productos'],
  ['stock'],
  ['stock-consulta'],
  ['reservas'],
  ['movimientos-stock'],
  ['producto-variantes'],
  ['buscar-variantes'],
  ['kpis'],
]

export function invalidarStock(queryClient) {
  CLAVES_CON_STOCK.forEach(queryKey => queryClient.invalidateQueries({ queryKey }))
}
