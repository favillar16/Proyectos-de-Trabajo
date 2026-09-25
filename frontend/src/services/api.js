import axios from 'axios'
import { baseUrlApi, olvidarServidor } from './servidor'

// La URL base ya no se calcula acá: la resuelve services/servidor.js buscando
// al servidor por nombre de red (y, si hace falta, barriendo la subred), para
// no depender de una IP que puede cambiar. Se aplica en el interceptor de
// request porque la búsqueda es asíncrona.
const api = axios.create({
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,
})

// Inyectar servidor y token en cada request
api.interceptors.request.use(
  async (config) => {
    config.baseURL = await baseUrlApi()
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
          const res = await axios.post(`${await baseUrlApi()}/auth/refresh/`, { refresh: refreshToken })
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
    // Sin respuesta = no llegamos al servidor: puede haberse movido de IP.
    // Olvidamos el conocido para que el proximo request lo vuelva a buscar.
    if (!error.response) olvidarServidor()

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

  // Gestión de catálogos auxiliares (categorías, marcas, acabados)
  crearCategoria:      (data)     => api.post('/productos/categorias/', data),
  editarCategoria:     (id, data) => api.patch(`/productos/categorias/${id}/`, data),
  eliminarCategoria:   (id)       => api.delete(`/productos/categorias/${id}/`),
  crearMarca:          (data)     => api.post('/productos/marcas/', data),
  editarMarca:         (id, data) => api.patch(`/productos/marcas/${id}/`, data),
  eliminarMarca:       (id)       => api.delete(`/productos/marcas/${id}/`),
  crearAcabado:        (data)     => api.post('/productos/acabados/', data),
  editarAcabado:       (id, data) => api.patch(`/productos/acabados/${id}/`, data),
  eliminarAcabado:     (id)       => api.delete(`/productos/acabados/${id}/`),
}

// ─── Inventario ───────────────────────────────────────────────
export const inventarioApi = {
  consultaRapida: (q)      => api.get('/inventario/consulta/', { params: { q } }),
  stockGeneral:   (params) => api.get('/inventario/stock/', { params }),
  movimientos:    (params) => api.get('/inventario/movimientos/', { params }),
  ajustar:        (data)   => api.post('/inventario/ajustes/', data),
  // params: { desde, hasta, buscar } — los ajustes hechos a mano, de todos los productos
  registroAjustes:(params) => api.get('/inventario/ajustes/', { params }),
  // params: { producto_id } o { variante_id } — para quién está apartado el stock
  reservas:       (params) => api.get('/inventario/reservas/', { params }),
  // El mismo registro como reporte: formato 'pdf' o 'xlsx', con los mismos filtros
  reporteAjustes: (formato, params) => api.get('/inventario/ajustes/', {
    params: { ...params, formato }, responseType: 'blob',
  }),
}

// ─── Ventas ───────────────────────────────────────────────────
export const ventasApi = {
  // params: { estado, buscar } — `buscar` cruza nombre, CI/RUC y número de pedido
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

  // Nota diagramada para el cliente — descarga un archivo (PDF o Excel).
  // `tipo` elige el encabezado: 'presupuesto' o 'pedido'.
  descargarNota: (id, formato, tipo = 'presupuesto') =>
    api.get(`/ventas/pedidos/${id}/nota/`, {
      params: { formato, tipo },
      responseType: 'blob',
    }),

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
  // Mismo comprobante que reimprimir pero SIN mandar nada a la impresora —
  // es el que reabre el cuadro "Datos para cargar en e-Kuatia'í".
  comprobante:     (id)        => api.get(`/caja/pagos/${id}/comprobante/`),
  estadoImpresora: ()          => api.get('/caja/impresora/estado/'),

  // Devoluciones y cambios
  resumenDevolucion:     (pagoId)  => api.get(`/caja/pagos/${pagoId}/devolucion/`),
  registrarDevolucion:   (data)    => api.post('/caja/devoluciones/', data),
  listaDevoluciones:     (params)  => api.get('/caja/devoluciones/', { params }),
  reimprimirDevolucion:  (id)      => api.post(`/caja/devoluciones/${id}/reimprimir/`),

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
// ─── Facturación electrónica ──────────────────────────────────
// Los datos de traslado cuelgan del PEDIDO y no del cobro: una nota de
// remisión describe un movimiento de mercadería, no una venta. Por eso la
// ruta va por pedido.
//
// `guardarTraslado` es un PUT y no un POST/PATCH separados porque hay uno
// solo por pedido: el formulario manda el estado completo y el backend decide
// si crea o actualiza. Para quien lo carga, "Guardar" es una sola acción.
export const facturacionApi = {
  // Cola de documentos electrónicos y eventos del emisor (panel de admin)
  documentos:      (params)       => api.get('/facturacion/documentos/', { params }),
  // El KuDE es el PDF que se le entrega al cliente: la representación
  // gráfica del DE, no la factura en sí (esa es el XML aprobado).
  kude:            (id)           => api.get(`/facturacion/documentos/${id}/kude/`, {
                                       responseType: 'blob' }),
  cancelar:        (id, motivo)   => api.post(`/facturacion/documentos/${id}/cancelar/`, { motivo }),
  numerosSinUsar:  (params = {})  => api.get('/facturacion/numeros-sin-usar/', { params }),
  inutilizaciones: (params = {})  => api.get('/facturacion/inutilizaciones/', { params }),
  inutilizar:      (data)         => api.post('/facturacion/inutilizaciones/', data),
  motivosNota:     ()             => api.get('/facturacion/motivos-nota/'),
  // Cobros marcados como factura que no llegaron a generar documento
  // electrónico — el punto ciego de la cola de arriba, que solo lista los
  // documentos que existen.
  ventasSinDocumento: (params = {}) =>
    api.get('/facturacion/ventas-sin-documento/', { params }),

  // Nota de débito: el espejo de la de crédito. El monto va CON IVA incluido,
  // igual que todos los precios del sistema.
  motivosDebito:   ()             => api.get('/facturacion/motivos-debito/'),
  notaDebito:      (id, data)     => api.post(`/facturacion/documentos/${id}/nota-debito/`, data),

  // Camino asincrónico. Mandar un lote y pedir su resultado son dos viajes
  // distintos: el SIFEN contesta un número y procesa después.
  lotes:           ()             => api.get('/facturacion/lotes/'),
  enviarLote:      (limite)       => api.post('/facturacion/lotes/', { limite }),
  consultarLotes:  ()             => api.post('/facturacion/lotes/', { consultar: true }),

  // Padrón de la DNIT. Es una ayuda, no una barrera: necesita certificado y
  // conexión, así que no se puede exigir para cobrar.
  consultarRuc:    (ruc)          => api.get('/facturacion/consulta-ruc/', { params: { ruc } }),

  // Autofactura: el único documento que respalda una COMPRA a alguien sin
  // RUC, no una venta. Por eso no va por documento ni por pedido.
  autofacturas:    ()             => api.get('/facturacion/autofacturas/'),
  // Tablas geográficas de la DNIT (departamento → distrito → ciudad). Salen
  // del sidecar y NO necesitan certificado ni internet: son un archivo de la
  // librería. No se copian al frontend para que no queden desfasadas.
  geografia:       (params = {}) => api.get('/facturacion/geografia/', { params }),
  emitirAutofactura: (data)       => api.post('/facturacion/autofacturas/', data),

  // Eventos del rol receptor: lo que el local declara sobre un DTE ajeno,
  // identificado solo por su CDC.
  eventosReceptor: ()             => api.get('/facturacion/eventos-receptor/'),
  registrarEventoReceptor: (data) => api.post('/facturacion/eventos-receptor/', data),
  notaCredito:     (id, data)     => api.post(`/facturacion/documentos/${id}/nota-credito/`, data),

  opcionesTraslado: ()            => api.get('/facturacion/opciones-traslado/'),
  traslado:         (pedidoId)    => api.get(`/facturacion/pedidos/${pedidoId}/traslado/`),
  guardarTraslado:  (pedidoId, data) => api.put(`/facturacion/pedidos/${pedidoId}/traslado/`, data),
  borrarTraslado:   (pedidoId)    => api.delete(`/facturacion/pedidos/${pedidoId}/traslado/`),

  // Emitir la remisión es una acción aparte del cobro y no un efecto suyo:
  // el documento respalda el TRASLADO de la mercadería, no la venta (Decreto
  // 6.539/2005 art. 30), y la RG 41/2014 art. 5 exime de emitirla cuando la
  // mercadería viaja acompañada del comprobante de venta. El cliente que se
  // lleva los pisos con su factura no necesita ninguna; el pedido que sale
  // en el flete del local, sí. Lo sabe quien despacha, no el sistema.
  remision:         (pedidoId)    => api.get(`/facturacion/pedidos/${pedidoId}/remision/`),
  emitirRemision:   (pedidoId)    => api.post(`/facturacion/pedidos/${pedidoId}/remision/`, {}),
}
