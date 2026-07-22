/**
 * useShowroom
 * Centraliza el estado, filtros, paginación y consulta de stock
 * del showroom digital. Separado del componente visual.
 */
import { useState, useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { productosApi } from '../services/api'

export const VISTA = { GRID: 'grid', LISTA: 'lista' }
export const ORDEN = {
  DESTACADO:  '-destacado,nombre',
  NOMBRE_AZ:  'nombre',
  PRECIO_ASC: 'precio_base',
  PRECIO_DESC:'-precio_base',
  NUEVO:      '-fecha_creacion',
}

export function useShowroom() {
  // ── Filtros ──────────────────────────────────────────────
  const [busqueda,    setBusqueda]    = useState('')
  const [categoria,   setCategoria]   = useState('')
  const [marca,       setMarca]       = useState('')
  const [soloStock,   setSoloStock]   = useState(false)
  const [orden,       setOrden]       = useState(ORDEN.DESTACADO)
  const [vista,       setVista]       = useState(VISTA.GRID)
  const [pagina,      setPagina]      = useState(1)
  const PAGE_SIZE = 24

  // ── Producto seleccionado (modal de detalle) ─────────────
  const [productoSeleccionado, setProductoSeleccionado] = useState(null)

  // ── Query principal ──────────────────────────────────────
  const params = useMemo(() => ({
    search:    busqueda   || undefined,
    categoria: categoria  || undefined,
    marca:     marca      || undefined,
    con_stock: soloStock  || undefined,
    ordering:  orden,
    page:      pagina,
    page_size: PAGE_SIZE,
  }), [busqueda, categoria, marca, soloStock, orden, pagina])

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['showroom', params],
    queryFn:  () => productosApi.showroom(params).then(r => r.data),
    staleTime: 20_000,
    keepPreviousData: true,
  })

  // ── Catálogos de filtros ─────────────────────────────────
  const { data: categorias } = useQuery({
    queryKey: ['categorias'],
    queryFn:  () => productosApi.categorias({ activas_only: 1 }).then(r => r.data?.results || r.data || []),
    staleTime: 300_000,
  })

  const { data: marcas } = useQuery({
    queryKey: ['marcas'],
    queryFn:  () => productosApi.marcas({ activas_only: 1 }).then(r => r.data?.results || r.data || []),
    staleTime: 300_000,
  })

  // ── Stock del producto seleccionado ──────────────────────
  const { data: stockDetalle, isLoading: stockLoading } = useQuery({
    queryKey: ['stock-detalle', productoSeleccionado?.id],
    queryFn:  () => productosApi.stock(productoSeleccionado.id).then(r => r.data),
    enabled:  Boolean(productoSeleccionado),
    staleTime: 10_000,
  })

  // ── Detalle completo del producto seleccionado ───────────
  const { data: productoDetalle, isLoading: detalleLoading } = useQuery({
    queryKey: ['producto-detalle', productoSeleccionado?.id],
    queryFn:  () => productosApi.detalle(productoSeleccionado.id).then(r => r.data),
    enabled:  Boolean(productoSeleccionado),
    staleTime: 30_000,
  })

  // ── Resetear página al cambiar filtros ───────────────────
  const aplicarFiltro = useCallback((setter) => (...args) => {
    setter(...args)
    setPagina(1)
  }, [])

  const limpiarFiltros = useCallback(() => {
    setBusqueda('')
    setCategoria('')
    setMarca('')
    setSoloStock(false)
    setOrden(ORDEN.DESTACADO)
    setPagina(1)
  }, [])

  const hayFiltrosActivos = busqueda || categoria || marca || soloStock

  return {
    // Estado
    busqueda, categoria, marca, soloStock, orden, vista, pagina,
    // Datos
    productos:        data?.results || [],
    totalProductos:   data?.count   || 0,
    totalPaginas:     Math.ceil((data?.count || 0) / PAGE_SIZE),
    isLoading, isFetching,
    categorias:       categorias || [],
    marcas:           marcas     || [],
    // Detalle
    productoSeleccionado,
    productoDetalle,
    stockDetalle:     stockDetalle || [],
    detalleLoading:   detalleLoading || stockLoading,
    // Acciones
    setBusqueda:   aplicarFiltro(setBusqueda),
    setCategoria:  aplicarFiltro(setCategoria),
    setMarca:      aplicarFiltro(setMarca),
    setSoloStock:  aplicarFiltro(setSoloStock),
    setOrden:      aplicarFiltro(setOrden),
    setVista,
    setPagina,
    setProductoSeleccionado,
    limpiarFiltros,
    hayFiltrosActivos,
  }
}
