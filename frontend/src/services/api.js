import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,
})

// Inyectar token en cada request
api.interceptors.request.use(
  (config) => {
    const state = JSON.parse(localStorage.getItem('ceramica-auth') || '{}')
    const token = state?.state?.token
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  },
  (error) => Promise.reject(error)
)

// Interceptor de respuesta — refresh automático si token expiró
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      try {
        const state = JSON.parse(localStorage.getItem('ceramica-auth') || '{}')
        const refreshToken = state?.state?.refreshToken
        if (refreshToken) {
          const res = await axios.post(`${BASE_URL}/auth/refresh/`, { refresh: refreshToken })
          const newToken = res.data.access
          const stored = JSON.parse(localStorage.getItem('ceramica-auth') || '{}')
          if (stored?.state) {
            stored.state.token = newToken
            localStorage.setItem('ceramica-auth', JSON.stringify(stored))
          }
          original.headers.Authorization = `Bearer ${newToken}`
          return api(original)
        }
      } catch {
        localStorage.removeItem('ceramica-auth')
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api

// ─── Productos ────────────────────────────────────────────────
export const productosApi = {
  listar:    (params)   => api.get('/productos/', { params }),
  detalle:   (id)       => api.get(`/productos/${id}/`),
  crear:     (data)     => api.post('/productos/', data),
  actualizar:(id, data) => api.patch(`/productos/${id}/`, data),
  eliminar:  (id)       => api.delete(`/productos/${id}/`),

  showroom:  (params)   => api.get('/productos/showroom/', { params }),
  stock:     (id)       => api.get(`/productos/${id}/stock/`),

  subirImagen: (id, formData) => api.post(`/productos/${id}/imagenes/`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  eliminarImagen:        (prodId, imgId) => api.delete(`/productos/${prodId}/imagenes/${imgId}/`),
  marcarImagenPrincipal: (prodId, imgId) => api.patch(`/productos/${prodId}/imagenes/${imgId}/principal/`),
  reordenarImagenes:     (prodId, orden) => api.patch(`/productos/${prodId}/imagenes/orden/`, { orden }),

  agregarVariante:    (prodId, data) => api.post(`/productos/${prodId}/variantes/`, data),
  actualizarVariante: (varId, data)  => api.patch(`/productos/variantes/${varId}/`, data),
  eliminarVariante:   (varId)        => api.delete(`/productos/variantes/${varId}/`),

  subirImagenVariante:           (varId, formData) => api.post(`/productos/variantes/${varId}/imagenes/`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  eliminarImagenVariante:        (varId, imgId) => api.delete(`/productos/variantes/${varId}/imagenes/${imgId}/`),
  marcarImagenPrincipalVariante: (varId, imgId) => api.patch(`/productos/variantes/${varId}/imagenes/${imgId}/principal/`),

  categorias:       (params) => api.get('/productos/categorias/', { params }),
  marcas:           (params) => api.get('/productos/marcas/', { params }),
  acabados:         ()       => api.get('/productos/acabados/'),
  tiposInstalacion: ()       => api.get('/productos/tipos-instalacion/'),

  // Gestión de catálogos auxiliares (categorías, marcas, acabados, tipos)
  crearCategoria:      (data)     => api.post('/productos/categorias/', data),
  editarCategoria:     (id, data) => api.patch(`/productos/categorias/${id}/`, data),
  eliminarCategoria:   (id)       => api.delete(`/productos/categorias/${id}/`),
  crearMarca:          (data)     => api.post('/productos/marcas/', data),
  editarMarca:         (id, data) => api.patch(`/productos/marcas/${id}/`, data),
  eliminarMarca:       (id)       => api.delete(`/productos/marcas/${id}/`),
  crearAcabado:        (data)     => api.post('/productos/acabados/', data),
  editarAcabado:       (id, data) => api.patch(`/productos/acabados/${id}/`, data),
  eliminarAcabado:     (id)       => api.delete(`/productos/acabados/${id}/`),
  crearTipoInstalacion:   (data)     => api.post('/productos/tipos-instalacion/', data),
  editarTipoInstalacion:  (id, data) => api.patch(`/productos/tipos-instalacion/${id}/`, data),
  eliminarTipoInstalacion:(id)       => api.delete(`/productos/tipos-instalacion/${id}/`),
}

// ─── Inventario ───────────────────────────────────────────────
export const inventarioApi = {
  consultaRapida: (q)      => api.get('/inventario/consulta/', { params: { q } }),
  stockGeneral:   (params) => api.get('/inventario/stock/', { params }),
  movimientos:    (params) => api.get('/inventario/movimientos/', { params }),
  ajustar:        (data)   => api.post('/inventario/ajustes/', data),
}

// ─── Ventas ───────────────────────────────────────────────────
export const ventasApi = {
  pedidos:      (params)    => api.get('/ventas/pedidos/', { params }),
  detalle:      (id)        => api.get(`/ventas/pedidos/${id}/`),
  crear:        (data)      => api.post('/ventas/pedidos/', data),
  actualizar:   (id, data)  => api.patch(`/ventas/pedidos/${id}/`, data),
  cambiarEstado:(id, estado, extra = {}) =>
    api.post(`/ventas/pedidos/${id}/estado/`, { estado, ...extra }),
  prepararItem: (pedidoId, itemId, data) =>
    api.post(`/ventas/pedidos/${pedidoId}/items/${itemId}/preparar/`, data),
  eliminarItem: (pedidoId, itemId) =>
    api.delete(`/ventas/pedidos/${pedidoId}/items/${itemId}/`),

  // Padrón de clientes con RUC
  clientes:        (buscar = '') => api.get('/ventas/clientes/', { params: buscar ? { buscar } : {} }),
  crearCliente:    (data)        => api.post('/ventas/clientes/', data),
  actualizarCliente:(id, data)   => api.patch(`/ventas/clientes/${id}/`, data),
  desactivarCliente:(id)         => api.delete(`/ventas/clientes/${id}/`),
}

// ─── Caja ─────────────────────────────────────────────────────
export const cajaApi = {
  sesionActual:    ()          => api.get('/caja/sesion-actual/'),
  abrirCaja:       (data)      => api.post('/caja/sesiones/', data),
  cerrarCaja:      (id, data)  => api.post(`/caja/sesiones/${id}/cerrar/`, data),
  registrarPago:   (data)      => api.post('/caja/pagos/', data),
  listaPagos:      (params)    => api.get('/caja/pagos/lista/', { params }),
  reimprimir:      (id)        => api.post(`/caja/pagos/${id}/reimprimir/`),
  estadoImpresora: ()          => api.get('/caja/impresora/estado/'),

  // Reportes — descargan un archivo (PDF o Excel)
  descargarReporte: (tipo, formato, params = {}) =>
    api.get(`/caja/reportes/${tipo}/`, {
      params: { formato, ...params },
      responseType: 'blob',
    }),
}

// ─── Dashboard ────────────────────────────────────────────────
export const dashboardApi = {
  kpis: (dias = 30) => api.get('/caja/kpis/', { params: { dias } }),
}

// ─── Usuarios ─────────────────────────────────────────────────
export const usuariosApi = {
  me:              ()          => api.get('/usuarios/me/'),
  listar:          (params)    => api.get('/usuarios/', { params }),
  crear:           (data)      => api.post('/usuarios/', data),
  detalle:         (id)        => api.get(`/usuarios/${id}/`),
  actualizar:      (id, data)  => api.patch(`/usuarios/${id}/`, data),
  desactivar:      (id)        => api.delete(`/usuarios/${id}/`),
  cambiarPassword: (id, data)  => api.post(`/usuarios/${id}/password/`, data),
}

// ─── Costos operativos ────────────────────────────────────────
export const costosApi = {
  categorias:        (params)    => api.get('/costos/categorias/', { params }),
  crearCategoria:    (data)      => api.post('/costos/categorias/', data),

  empleados:         (params)    => api.get('/costos/empleados/', { params }),
  crearEmpleado:     (data)      => api.post('/costos/empleados/', data),
  actualizarEmpleado:(id, data)  => api.patch(`/costos/empleados/${id}/`, data),
  desactivarEmpleado:(id)        => api.delete(`/costos/empleados/${id}/`),

  proveedores:       (params)    => api.get('/costos/proveedores/', { params }),
  crearProveedor:    (data)      => api.post('/costos/proveedores/', data),
  actualizarProveedor:(id, data) => api.patch(`/costos/proveedores/${id}/`, data),
  desactivarProveedor:(id)       => api.delete(`/costos/proveedores/${id}/`),

  gastos:            (params)    => api.get('/costos/gastos/', { params }),
  crearGasto:        (data)      => api.post('/costos/gastos/', data),
  actualizarGasto:   (id, data)  => api.patch(`/costos/gastos/${id}/`, data),
  eliminarGasto:     (id)        => api.delete(`/costos/gastos/${id}/`),

  pedidosProveedor:        (params)   => api.get('/costos/pedidos-proveedor/', { params }),
  crearPedidoProveedor:    (data)     => api.post('/costos/pedidos-proveedor/', data),
  actualizarPedidoProveedor:(id, data)=> api.patch(`/costos/pedidos-proveedor/${id}/`, data),
  eliminarPedidoProveedor: (id)       => api.delete(`/costos/pedidos-proveedor/${id}/`),

  alertas:           (dias = 7)  => api.get('/costos/alertas/', { params: { dias } }),
  resumen:           (anio, mes) => api.get('/costos/resumen/', { params: { anio, mes } }),
}