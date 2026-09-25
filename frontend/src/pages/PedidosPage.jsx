/**
 * PedidosPage — Vista adaptada por rol
 *
 * vendedor:  crea pedidos y ve el estado de los suyos
 * deposito:  ve pedidos pendientes, marca ítems como preparados
 * cajero:    ve pedidos listos para cobrar
 * admin:     ve todo
 *
 * WebSocket actualiza la lista en tiempo real sin recargar.
 */
import { useState, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus, RefreshCw, FileText, Clock, Truck,
  CheckCircle, CreditCard, XCircle, ChevronRight,
  Package, User, AlertCircle, Loader2, FileSpreadsheet,
  Search, X, Trash2, Undo2,
} from 'lucide-react'
import Layout from '../components/layout/Layout'
import NuevoPedidoForm from '../components/ventas/NuevoPedidoForm'
import DatosTrasladoForm from '../components/ventas/DatosTrasladoForm'
import { ventasApi, facturacionApi } from '../services/api'
import { useAuthStore } from '../store/authStore'
import { usePedidoSocket } from '../hooks/usePedidoSocket'
import toast from 'react-hot-toast'
import { invalidarStock } from '../utils/stockCache'

const C = {
  sidebar:'#453941', sidebarHov:'#362F31',
  gold:'#B99C74', goldDark:'#8a7355', goldMuted:'rgba(185,156,116,0.10)',
  border:'#e8e4df', bg:'#ffffff', bgSec:'#fafaf9', bgTer:'#f5f4f2',
  text:'#1a1714', textSec:'#6b6560', textMuted:'#9e9892',
  success:'#3d7a5a', successBg:'#edf7f1', successBorder:'#b8deca',
  warning:'#8a6a1a', warningBg:'#fef9ee', warningBorder:'#f0d98a',
  danger:'#9a3030',  dangerBg:'#fef0f0',  dangerBorder:'#f0b8b8',
  info:'#2a5c8a',    infoBg:'#eef4fb',
}

function formatGs(v) { return `Gs. ${Number(v||0).toLocaleString('es-PY')}` }

function formatFecha(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const hoy = new Date()
  const diff = Math.floor((hoy - d) / 60000)
  if (diff < 1)  return 'ahora'
  if (diff < 60) return `hace ${diff} min`
  if (diff < 1440) return `hace ${Math.floor(diff/60)}h`
  return d.toLocaleDateString('es-PY', { day:'2-digit', month:'2-digit' })
}

// ─── Descarga de la nota diagramada para el cliente ──────────────────────────
// El backend devuelve el archivo armado (mismo diseño que la nota que el
// negocio ya usaba); acá solo se fuerza la descarga. El tipo ya no se elige a
// mano: se deriva del estado del pedido, para que no quede la posibilidad de
// imprimir un "Presupuesto" de algo que depósito ya está preparando (o un
// "Pedido" de algo que todavía no se confirmó como venta). Mientras el pedido
// sigue "Pendiente" —no entró al segmento de pedidos— es Presupuesto; en
// cuanto pasa a cualquier estado siguiente, es Pedido.
function DescargasNota({ pedidoId, numero, estado }) {
  const tipo  = estado === 'pendiente' ? 'presupuesto' : 'pedido'
  const label = estado === 'pendiente' ? 'Presupuesto'  : 'Pedido'
  const [cargando, setCargando] = useState(null)

  const descargar = async (formato) => {
    setCargando(formato)
    try {
      const res = await ventasApi.descargarNota(pedidoId, formato, tipo)
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `nota_${tipo}_${numero}.${formato === 'pdf' ? 'pdf' : 'xlsx'}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch {
      toast.error(`No se pudo generar la nota en ${formato === 'pdf' ? 'PDF' : 'Excel'}`)
    } finally {
      setCargando(null)
    }
  }

  const btn = (formato, Icono, label) => {
    const activo = cargando === formato
    const Ico = activo ? Loader2 : Icono
    return (
      <button onClick={() => descargar(formato)} disabled={Boolean(cargando)} style={{
        display:'flex', alignItems:'center', gap:'6px',
        padding:'7px 12px', borderRadius:'8px', cursor: cargando ? 'wait' : 'pointer',
        background:C.bgTer, border:`1px solid ${C.border}`, color:C.textSec,
        fontSize:'12.5px', fontWeight:'500',
      }}>
        <Ico size={14} style={activo ? { animation:'spin 1s linear infinite' } : undefined} />
        {label}
      </button>
    )
  }

  return (
    <div style={{ display:'flex', alignItems:'center', gap:'8px', marginTop:'12px', flexWrap:'wrap' }}>
      <span style={{
        padding:'7px 11px', borderRadius:'8px', fontSize:'12px', fontWeight:'600',
        background:C.goldMuted, color:C.goldDark, border:`1px solid ${C.border}`,
      }}>
        {label}
      </span>
      {btn('pdf',  FileText,        'PDF')}
      {btn('xlsx', FileSpreadsheet, 'Excel')}
    </div>
  )
}

// ─── Configuración visual de estados ─────────────────────────────────────────
const ESTADO_CFG = {
  pendiente:       { label:'Pendiente',         icon:<Clock size={13}/>,        bg:C.infoBg,      color:C.info,    border:'#aecae8' },
  en_preparacion:  { label:'En preparación',    icon:<Truck size={13}/>,        bg:C.warningBg,   color:C.warning, border:C.warningBorder },
  listo:           { label:'Listo para cobrar', icon:<CheckCircle size={13}/>,  bg:C.successBg,   color:C.success, border:C.successBorder },
  pagado:          { label:'Pagado',            icon:<CreditCard size={13}/>,   bg:C.bgTer,       color:C.textSec, border:C.border },
  cancelado:       { label:'Cancelado',         icon:<XCircle size={13}/>,      bg:C.dangerBg,    color:C.danger,  border:C.dangerBorder },
}

function EstadoBadge({ estado }) {
  const cfg = ESTADO_CFG[estado] || ESTADO_CFG.pendiente
  return (
    <span style={{ display:'inline-flex', alignItems:'center', gap:'4px',
      padding:'3px 9px', borderRadius:'20px',
      background:cfg.bg, color:cfg.color,
      border:`1px solid ${cfg.border}`,
      fontSize:'11px', fontWeight:'500', whiteSpace:'nowrap' }}>
      {cfg.icon} {cfg.label}
    </span>
  )
}

// ─── Card de pedido en la lista ───────────────────────────────────────────────
function PedidoCard({ pedido, onAbrir, esActivo, rol }) {
  return (
    <div
      onClick={() => onAbrir(pedido)}
      style={{
        background: esActivo ? C.bgSec : C.bg,
        border:`1px solid ${esActivo ? C.gold : C.border}`,
        borderRadius:'12px', padding:'14px 16px', cursor:'pointer',
        transition:'all 150ms', marginBottom:'8px',
        boxShadow: esActivo ? '0 0 0 2px rgba(185,156,116,0.15)' : 'none',
      }}
      onMouseEnter={e => { if(!esActivo) e.currentTarget.style.borderColor=C.goldDark }}
      onMouseLeave={e => { if(!esActivo) e.currentTarget.style.borderColor=C.border }}
    >
      <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between', gap:'10px', marginBottom:'8px' }}>
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ display:'flex', alignItems:'center', gap:'7px', marginBottom:'3px' }}>
            <p style={{ fontSize:'14px', fontWeight:'600', color:C.text, fontFamily:'monospace' }}>
              {pedido.numero}
            </p>
            <EstadoBadge estado={pedido.estado} />
          </div>
          <p style={{ fontSize:'12.5px', color:C.textSec }}>
            {pedido.cliente_nombre || 'Sin nombre'}
            {/* El documento va en la tarjeta porque es por lo que se busca:
                de poco sirve encontrar el pedido por RUC si después la lista
                no lo muestra para confirmar que es el cliente correcto. */}
            {pedido.cliente_ruc && <span style={{ color:C.textMuted }}> · {pedido.cliente_ruc}</span>}
            {pedido.vendedor_nombre && <span style={{ color:C.textMuted }}> · {pedido.vendedor_nombre}</span>}
          </p>
        </div>
        <div style={{ textAlign:'right', flexShrink:0 }}>
          {rol !== 'deposito' && (
            <p style={{ fontSize:'15px', fontWeight:'600', color:C.goldDark }}>{formatGs(pedido.total)}</p>
          )}
          <p style={{ fontSize:'11px', color:C.textMuted, marginTop:'2px' }}>
            {pedido.items_count} ítem{pedido.items_count!==1?'s':''}
          </p>
        </div>
      </div>

      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <p style={{ fontSize:'11px', color:C.textMuted }}>{formatFecha(pedido.fecha_creacion)}</p>
        {pedido.todos_preparados && pedido.estado === 'en_preparacion' && (
          <span style={{ fontSize:'11px', color:C.success, fontWeight:'500',
            display:'flex', alignItems:'center', gap:'3px' }}>
            <CheckCircle size={11} /> Todo preparado
          </span>
        )}
        <ChevronRight size={15} style={{ color:C.textMuted }} />
      </div>
    </div>
  )
}

// ─── Panel de detalle del pedido ──────────────────────────────────────────────
function PanelDetalle({ pedido: pedidoResumen, rol, puedeEditarPrecio, onCerrar }) {
  const queryClient = useQueryClient()
  const [editandoMonto, setEditandoMonto] = useState(false)
  const [montoNuevo, setMontoNuevo] = useState('')
  const [editandoTraslado, setEditandoTraslado] = useState(false)
  // Confirmación en dos toques para quitar un ítem. No se usa window.confirm:
  // en la tablet abre un diálogo del navegador encima de la PWA y, si queda
  // abierto, bloquea toda la pantalla.
  const [itemAQuitar, setItemAQuitar] = useState(null)

  const { data: pedido, isLoading } = useQuery({
    queryKey: ['pedido', pedidoResumen?.id],
    queryFn: () => ventasApi.detalle(pedidoResumen.id).then(r => r.data),
    enabled: Boolean(pedidoResumen),
    staleTime: 5000,
  })

  // El WebSocket del pedido (más abajo) ya mantiene fresca la query
  // ['pedido', id] en cuanto depósito/caja avanzan el estado. `pedidoResumen`
  // en cambio es la foto que tenía la lista cuando se abrió el panel — usarla
  // acá dejaría el encabezado y la nota mostrando un estado viejo mientras el
  // panel sigue abierto (se vio como "Presupuesto" en un pedido ya Pagado).
  const estadoActual = pedido?.estado ?? pedidoResumen?.estado

  const ajusteMut = useMutation({
    mutationFn: (valor) => ventasApi.actualizar(pedidoResumen.id, { total_ajustado: valor }).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pedido', pedidoResumen?.id] })
      queryClient.invalidateQueries({ queryKey: ['pedidos'] })
      toast.success('Monto del pedido actualizado')
      setEditandoMonto(false)
    },
    onError: (err) => toast.error(err.response?.data?.error || 'No se pudo actualizar el monto'),
  })

  // WebSocket del pedido específico. El backend emite el evento de cambio de
  // estado (que dispara el toast de abajo) ANTES de devolver la respuesta
  // HTTP de la mutación — a veces el eco llega antes que el propio
  // onSuccess. Por eso el toast de "cambié el estado" vive acá, en un solo
  // lugar, en vez de repetirlo también en el onSuccess de la mutación:
  // cualquier orden de llegada muestra un único aviso, para el que hizo el
  // cambio y para cualquier otro rol que tenga este mismo pedido abierto.
  usePedidoSocket({
    pedidoId: pedidoResumen?.id,
    onMensaje: (msg) => {
      if (msg.tipo !== 'pedido_actualizado' && msg.tipo !== 'item_preparado') {
        toast(`Pedido ${msg.pedido?.numero}: ${ESTADO_CFG[msg.pedido?.estado]?.label || 'actualizado'}`,
          { icon: msg.pedido?.estado === 'listo' ? '✅' : 'ℹ️' })
      }
    },
  })

  const cambiarEstado = useMutation({
    mutationFn: ({ estado, extra }) => ventasApi.cambiarEstado(pedidoResumen.id, estado, extra).then(r => r.data),
    onSuccess: (pedidoActualizado) => {
      queryClient.setQueryData(['pedido', pedidoActualizado.id], pedidoActualizado)
      queryClient.invalidateQueries({ queryKey: ['pedidos'] })
      invalidarStock(queryClient)
    },
    onError: (err) => toast.error(err.response?.data?.error || 'Error al cambiar estado'),
  })

  // Quitar un ítem devuelve su reserva al stock (lo hace el backend). Sin
  // esta pantalla, la única forma de recuperar mercadería reservada de más
  // era cancelar el pedido entero o tocar el inventario a mano.
  const quitarItem = useMutation({
    mutationFn: (itemId) => ventasApi.eliminarItem(pedidoResumen.id, itemId).then(r => r.data),
    onSuccess: (data) => {
      setItemAQuitar(null)
      queryClient.invalidateQueries({ queryKey: ['pedido', pedidoResumen.id] })
      queryClient.invalidateQueries({ queryKey: ['pedidos'] })
      invalidarStock(queryClient)
      const liberado = Number(data?.liberado || 0)
      toast.success(liberado > 0
        ? `Producto quitado — se liberaron ${liberado.toLocaleString('es-PY', { maximumFractionDigits: 2 })} al stock`
        : 'Producto quitado del pedido')
    },
    onError: (err) => toast.error(err.response?.data?.error || 'No se pudo quitar el producto'),
  })

  const prepararItem = useMutation({
    mutationFn: ({ itemId, preparado }) =>
      ventasApi.prepararItem(pedidoResumen.id, itemId, { preparado, cantidad_preparada: pedido?.items?.find(i=>i.id===itemId)?.cantidad }).then(r => r.data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['pedido', pedidoResumen.id] })
      if (data.todos_listos) {
        toast.success('Todos los ítems preparados — podés marcar el pedido como Listo')
      }
    },
  })

  // Quitar productos es parte de editar el pedido: mismo permiso y misma
  // ventana (solo 'pendiente'), igual que el ajuste de monto.
  const puedeQuitarItems = (
    ['vendedor', 'encargada_ventas', 'admin'].includes(rol)
    && estadoActual === 'pendiente'
  )

  if (!pedidoResumen) return null

  return (
    <>
      <div onClick={onCerrar} style={{ position:'fixed', inset:0, zIndex:150,
        background:'rgba(26,23,20,0.4)', backdropFilter:'blur(2px)' }} />
      <div style={{ position:'fixed', top:0, right:0, bottom:0, zIndex:151,
        width:'min(560px,95vw)', background:C.bg,
        borderLeft:`1px solid ${C.border}`,
        boxShadow:'-8px 0 32px rgba(0,0,0,0.12)',
        display:'flex', flexDirection:'column',
        animation:'slideIn 200ms ease' }}>

        {/* Header */}
        <div style={{ padding:'16px 20px', borderBottom:`1px solid ${C.border}`, flexShrink:0 }}>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
            <div>
              <p style={{ fontSize:'11px', color:C.textMuted, fontFamily:'monospace' }}>
                {pedidoResumen.numero}
              </p>
              <h2 style={{ fontSize:'17px', fontWeight:'500', color:C.text,
                fontFamily:'var(--font-display)', marginTop:'2px' }}>
                {pedidoResumen.cliente_nombre || 'Sin nombre'}
              </h2>
            </div>
            <div style={{ display:'flex', alignItems:'center', gap:'10px' }}>
              <EstadoBadge estado={estadoActual} />
              <button onClick={onCerrar} style={{ background:'transparent', border:'none',
                cursor:'pointer', color:C.textMuted, padding:'6px',
                display:'flex', alignItems:'center', borderRadius:'8px' }}>
                <XCircle size={20} />
              </button>
            </div>
          </div>

          {/* Nota para el cliente — depósito no la ve porque lleva precios */}
          {rol !== 'deposito' && (
            <DescargasNota pedidoId={pedidoResumen.id} numero={pedidoResumen.numero} estado={estadoActual} />
          )}
        </div>

        {/* Body */}
        <div style={{ flex:1, overflowY:'auto', WebkitOverflowScrolling:'touch' }}>
          {isLoading ? (
            <div style={{ padding:'40px', textAlign:'center', color:C.textMuted }}>
              <Loader2 size={24} style={{ animation:'spin 1s linear infinite', margin:'0 auto 10px', display:'block' }} />
              Cargando pedido...
            </div>
          ) : pedido ? (
            <>
              {/* Info cliente */}
              {(pedido.cliente_nombre || pedido.cliente_telefono) && (
                <div style={{ padding:'14px 20px', borderBottom:`1px solid ${C.border}`,
                  display:'flex', gap:'16px', flexWrap:'wrap' }}>
                  {[
                    { label:'Cliente', valor:pedido.cliente_nombre },
                    { label:'Teléfono', valor:pedido.cliente_telefono },
                    { label:'Vendedor', valor:pedido.vendedor_nombre },
                  ].filter(f=>f.valor).map(f=>(
                    <div key={f.label}>
                      <p style={{ fontSize:'10.5px', color:C.textMuted, marginBottom:'1px' }}>{f.label}</p>
                      <p style={{ fontSize:'13.5px', color:C.text }}>{f.valor}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Datos del traslado — para la nota de remisión electrónica.
                  Cajero no los ve: los carga quien prepara la entrega. */}
              {rol !== 'cajero' && (
                <>
                  <ResumenTraslado
                    pedidoId={pedido.id}
                    onAbrir={() => setEditandoTraslado(true)}
                  />
                  {/* Emitir la remisión y bajar su KuDE. Aparece recién con
                      el pedido cobrado: el documento cuelga del cobro. */}
                  <AccionesRemision pedido={pedido} />
                </>
              )}

              {/* Observaciones */}
              {pedido.cliente_observaciones && (
                <div style={{ padding:'12px 20px', borderBottom:`1px solid ${C.border}`,
                  background:C.bgSec }}>
                  <p style={{ fontSize:'11px', color:C.textMuted, marginBottom:'3px' }}>Observaciones</p>
                  <p style={{ fontSize:'13px', color:C.textSec }}>{pedido.cliente_observaciones}</p>
                </div>
              )}

              {/* La mercadería del pedido está apartada para este cliente
                  desde que se creó, hasta que se cobre o se cancele. */}
              {['pendiente', 'en_preparacion', 'listo'].includes(pedido.estado) && (
                <div style={{ padding:'9px 20px', borderBottom:`1px solid ${C.border}`,
                  background:C.infoBg, display:'flex', alignItems:'center', gap:'7px' }}>
                  <Package size={14} style={{ color:C.info, flexShrink:0 }} />
                  <p style={{ fontSize:'12px', color:C.info }}>
                    Stock reservado{pedido.cliente_nombre ? ` para ${pedido.cliente_nombre}` : ''}:
                    nadie más puede venderlo hasta que el pedido se cobre o se cancele.
                  </p>
                </div>
              )}

              {/* Ítems */}
              <div>
                {pedido.items?.map(item => (
                  <div key={item.id} style={{
                    display:'flex', alignItems:'center', gap:'12px',
                    padding:'12px 20px', borderBottom:`1px solid ${C.border}`,
                    background: item.preparado ? C.successBg : C.bg,
                    transition:'background 200ms',
                  }}>
                    {/* Imagen */}
                    <div style={{ width:'44px', height:'44px', flexShrink:0, borderRadius:'8px',
                      overflow:'hidden', background:C.bgTer,
                      display:'flex', alignItems:'center', justifyContent:'center' }}>
                      {item.imagen_url
                        ? <img src={item.imagen_url} alt="" style={{ width:'100%', height:'100%', objectFit:'cover' }} />
                        : <Package size={16} style={{ color:C.border, opacity:0.5 }} />}
                    </div>

                    {/* Info */}
                    <div style={{ flex:1, minWidth:0 }}>
                      <p style={{ fontSize:'13px', fontWeight:'500', color:C.text,
                        overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                        {item.descripcion}
                      </p>
                      <p style={{ fontSize:'11px', color:C.textMuted, marginTop:'1px' }}>
                        {rol === 'deposito'
                          ? `${Number(item.cantidad).toFixed(2)} unidad${Number(item.cantidad)!==1?'es':''}`
                          : `${Number(item.cantidad).toFixed(2)} × ${formatGs(item.precio_unitario)} = ${formatGs(item.subtotal)}`}
                      </p>
                      {item.observaciones && (
                        <p style={{ fontSize:'11px', color:C.info, marginTop:'2px' }}>
                          📝 {item.observaciones}
                        </p>
                      )}
                    </div>

                    {/* Acción depósito: marcar preparado */}
                    {rol === 'deposito' && pedido.estado !== 'pagado' && pedido.estado !== 'cancelado' && (
                      <button
                        onClick={() => prepararItem.mutate({ itemId: item.id, preparado: !item.preparado })}
                        style={{
                          width:'36px', height:'36px', flexShrink:0,
                          borderRadius:'8px', cursor:'pointer',
                          background: item.preparado ? C.successBg : C.bgSec,
                          border:`1.5px solid ${item.preparado ? C.success : C.border}`,
                          color: item.preparado ? C.success : C.textMuted,
                          display:'flex', alignItems:'center', justifyContent:'center',
                          transition:'all 150ms',
                        }}
                        title={item.preparado ? 'Desmarcar' : 'Marcar como preparado'}
                      >
                        <CheckCircle size={18} />
                      </button>
                    )}

                    {/* Estado del ítem (solo lectura para no-depósito) */}
                    {rol !== 'deposito' && item.preparado && (
                      <CheckCircle size={18} style={{ color:C.success, flexShrink:0 }} />
                    )}

                    {/* Quitar el producto del pedido — solo mientras está
                        pendiente, que es cuando el pedido es editable. */}
                    {puedeQuitarItems && (
                      itemAQuitar === item.id ? (
                        <div style={{ display:'flex', gap:'5px', flexShrink:0 }}>
                          <button
                            disabled={quitarItem.isPending}
                            onClick={() => quitarItem.mutate(item.id)}
                            style={{ height:'36px', padding:'0 10px', borderRadius:'8px',
                              cursor:'pointer', background:C.dangerBg,
                              border:`1.5px solid ${C.danger}`, color:C.danger,
                              fontSize:'12px', fontWeight:'500' }}>
                            {quitarItem.isPending ? 'Quitando...' : 'Quitar'}
                          </button>
                          <button onClick={() => setItemAQuitar(null)}
                            title="No quitar"
                            style={{ width:'36px', height:'36px', borderRadius:'8px',
                              cursor:'pointer', background:C.bg,
                              border:`1px solid ${C.border}`, color:C.textSec,
                              display:'flex', alignItems:'center', justifyContent:'center' }}>
                            <Undo2 size={15} />
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setItemAQuitar(item.id)}
                          disabled={pedido.items.length <= 1}
                          title={pedido.items.length <= 1
                            ? 'Es el único producto del pedido: cancelá el pedido entero'
                            : 'Quitar del pedido y liberar el stock reservado'}
                          style={{ width:'36px', height:'36px', flexShrink:0,
                            borderRadius:'8px', background:'transparent',
                            border:`1px solid ${C.border}`, color:C.textMuted,
                            cursor: pedido.items.length <= 1 ? 'not-allowed' : 'pointer',
                            opacity: pedido.items.length <= 1 ? 0.35 : 1,
                            display:'flex', alignItems:'center', justifyContent:'center' }}>
                          <Trash2 size={15} />
                        </button>
                      )
                    )}
                  </div>
                ))}
              </div>

              {/* Totales — depósito no maneja montos */}
              {rol !== 'deposito' && (
              <div style={{ padding:'14px 20px', borderTop:`1px solid ${C.border}` }}>
                {[
                  { l:'Subtotal', v:pedido.subtotal, muted:true },
                  ...(Number(pedido.descuento)>0 ? [{ l:'Descuento', v:-Number(pedido.descuento), muted:true, neg:true }] : []),
                  { l:'Total', v:pedido.total, muted:false },
                ].map(row => (
                  <div key={row.l} style={{ display:'flex', justifyContent:'space-between',
                    marginBottom:'5px' }}>
                    <span style={{ fontSize:row.muted?'12px':'14px',
                      fontWeight:row.muted?'400':'600',
                      color:row.muted?C.textSec:C.text }}>{row.l}</span>
                    <span style={{ fontSize:row.muted?'13px':'16px',
                      fontWeight:row.muted?'500':'700',
                      color:row.neg?C.danger:(row.muted?C.textSec:C.goldDark) }}>
                      {row.neg?'− ':''}{formatGs(Math.abs(row.v))}
                    </span>
                  </div>
                ))}

                {/* Monto negociado vigente, si lo hay */}
                {pedido.total_ajustado != null && Number(pedido.total_ajustado) !== Number(pedido.total) && (
                  <div style={{ display:'flex', justifyContent:'space-between',
                    marginTop:'6px', paddingTop:'8px', borderTop:`1px dashed ${C.border}` }}>
                    <span style={{ fontSize:'13px', fontWeight:'600', color:C.goldDark }}>
                      Monto a cobrar (negociado)
                    </span>
                    <span style={{ fontSize:'17px', fontWeight:'700', color:C.goldDark }}>
                      {formatGs(pedido.monto_a_cobrar)}
                    </span>
                  </div>
                )}

                {/* Ajuste de monto — solo Encargada/admin y solo si está pendiente */}
                {puedeEditarPrecio && pedido.estado === 'pendiente' && (
                  <div style={{ marginTop:'10px', paddingTop:'10px',
                    borderTop:`1px solid ${C.border}` }}>
                    {!editandoMonto ? (
                      <button
                        onClick={() => {
                          setMontoNuevo(String(Number(pedido.monto_a_cobrar)))
                          setEditandoMonto(true)
                        }}
                        style={{ width:'100%', height:'40px', borderRadius:'8px', cursor:'pointer',
                          background:C.goldMuted, border:`1px solid ${C.gold}`,
                          color:C.goldDark, fontSize:'13px', fontWeight:'500' }}>
                        Ajustar monto del pedido
                      </button>
                    ) : (
                      <div>
                        <label style={{ display:'block', fontSize:'12px', color:C.textSec,
                          marginBottom:'6px' }}>
                          Nuevo monto final (calculado: {formatGs(pedido.total)})
                        </label>
                        <input
                          type="number" min="0" step="1000" value={montoNuevo}
                          onChange={e => setMontoNuevo(e.target.value)}
                          autoFocus
                          style={{ width:'100%', height:'44px', padding:'0 12px', textAlign:'right',
                            border:`1.5px solid ${C.gold}`, borderRadius:'9px',
                            fontSize:'17px', fontWeight:'600', color:C.goldDark,
                            background:C.bg, outline:'none' }}
                        />
                        <div style={{ display:'flex', gap:'8px', marginTop:'8px' }}>
                          <button onClick={() => setEditandoMonto(false)}
                            style={{ flex:1, height:'40px', borderRadius:'8px', cursor:'pointer',
                              background:'transparent', border:`1px solid ${C.border}`,
                              color:C.textSec, fontSize:'13px' }}>
                            Cancelar
                          </button>
                          <button
                            disabled={ajusteMut.isPending}
                            onClick={() => ajusteMut.mutate(montoNuevo === '' ? null : Number(montoNuevo))}
                            style={{ flex:1, height:'40px', borderRadius:'8px', cursor:'pointer',
                              background:C.sidebar, border:`1px solid ${C.gold}`,
                              color:C.gold, fontSize:'13px', fontWeight:'500' }}>
                            {ajusteMut.isPending ? 'Guardando...' : 'Guardar monto'}
                          </button>
                        </div>
                        <p style={{ fontSize:'11px', color:C.textMuted, marginTop:'6px' }}>
                          Solo se puede ajustar antes de pasar a depósito.
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>
              )}
            </>
          ) : null}
        </div>

        {/* Footer con acciones según rol y estado */}
        {pedido && (
          <div style={{ padding:'14px 20px', borderTop:`1px solid ${C.border}`,
            background:C.bgSec, flexShrink:0 }}>
            <AccionesFooter
              pedido={pedido}
              rol={rol}
              onCambiarEstado={(estado, extra) => cambiarEstado.mutate({ estado, extra })}
              isPending={cambiarEstado.isPending}
            />
          </div>
        )}
      </div>
      {editandoTraslado && (
        <DatosTrasladoForm
          pedido={pedido ?? pedidoResumen}
          onCerrar={() => setEditandoTraslado(false)}
        />
      )}

      <style>{`
        @keyframes slideIn { from{transform:translateX(100%)} to{transform:translateX(0)} }
        @keyframes spin { to{transform:rotate(360deg)} }
      `}</style>
    </>
  )
}

/**
 * Fila que dice si el pedido tiene cargados los datos del traslado.
 *
 * Se muestra siempre —no solo cuando ya hay algo— porque el problema que
 * resuelve es justamente que nadie sabía que había que cargarlos: la nota de
 * remisión salía bien del lado del XML y se trababa acá. Con la fila visible,
 * quien prepara la entrega ve el pendiente sin tener que acordarse.
 */
function ResumenTraslado({ pedidoId, onAbrir }) {
  const { data, isLoading } = useQuery({
    queryKey: ['traslado', pedidoId],
    queryFn: () => facturacionApi.traslado(pedidoId).then(r => r.data),
    enabled: Boolean(pedidoId),
  })

  const cargado = data?.existe
  return (
    <button onClick={onAbrir}
      style={{ width:'100%', display:'flex', alignItems:'center', gap:'11px',
        padding:'12px 20px', borderBottom:`1px solid ${C.border}`,
        background: cargado ? C.successBg : C.bg, border:'none',
        borderLeft:`3px solid ${cargado ? C.success : C.border}`,
        cursor:'pointer', textAlign:'left', fontFamily:'inherit' }}>
      <Truck size={16} color={cargado ? C.success : C.textMuted}
        style={{ flexShrink:0 }} />
      <div style={{ flex:1, minWidth:0 }}>
        <p style={{ fontSize:'13px', color:C.text, margin:0 }}>
          Datos del traslado
        </p>
        <p style={{ fontSize:'11.5px', color:C.textMuted, margin:'2px 0 0',
          overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
          {isLoading ? 'Cargando...'
            : cargado
              ? `${data.motivo_descripcion} · ${data.vehiculo_matricula || data.vehiculo_numero} · ${data.kilometros} km`
              : 'Sin cargar — hacen falta para la nota de remisión'}
        </p>
      </div>
      <ChevronRight size={16} color={C.textMuted} style={{ flexShrink:0 }} />
    </button>
  )
}

/**
 * Emitir la nota de remisión, o bajar su KuDE si ya se emitió.
 *
 * Es un botón y no un paso automático del cobro a propósito. La remisión
 * respalda el **traslado** de la mercadería, no la venta: el Decreto
 * 6.539/2005 art. 30 dice que sustenta "el traslado de mercaderías dentro del
 * territorio nacional, por cualquier motivo", y la RG 41/2014 art. 5 exime de
 * emitirla cuando la mercadería va acompañada del comprobante de venta. O
 * sea: el cliente que se lleva los pisos en su camioneta con la factura no
 * necesita remisión; el pedido que sale en el flete del local, sí. Quien
 * despacha es el único que sabe cuál de los dos casos es.
 *
 * Solo aparece con el pedido ya cobrado y con los datos del traslado
 * cargados, que son las dos condiciones que el backend también exige.
 */
function AccionesRemision({ pedido }) {
  const pedidoId = pedido.id
  const estado = pedido.estado
  const queryClient = useQueryClient()
  const [bajando, setBajando] = useState(false)
  const [editandoCliente, setEditandoCliente] = useState(false)

  const { data } = useQuery({
    queryKey: ['remision', pedidoId],
    queryFn: () => facturacionApi.remision(pedidoId).then(r => r.data),
    enabled: Boolean(pedidoId) && estado === 'pagado',
  })

  // Misma clave que usa ResumenTraslado, así que esto lee de la caché en vez
  // de repetir el pedido a la API.
  const { data: traslado } = useQuery({
    queryKey: ['traslado', pedidoId],
    queryFn: () => facturacionApi.traslado(pedidoId).then(r => r.data),
    enabled: Boolean(pedidoId),
  })
  const hayTraslado = Boolean(traslado?.existe)
  const hayCliente = Boolean((pedido.cliente_ruc || '').trim())

  const emitirMut = useMutation({
    mutationFn: () => facturacionApi.emitirRemision(pedidoId),
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey:['remision', pedidoId] })
      toast.success(`Nota de remisión ${r.data.remision.numero} emitida`)
    },
    onError: (err) => toast.error(
      err.response?.data?.error || 'No se pudo emitir la nota de remisión'),
  })

  const descargarKude = async () => {
    setBajando(true)
    try {
      const res = await facturacionApi.kude(data.id)
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `remision_${data.numero}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch {
      toast.error('No se pudo bajar el KuDE de la remisión')
    } finally {
      setBajando(false)
    }
  }

  // Antes de cobrar no hay remisión posible: el documento cuelga del cobro.
  if (estado !== 'pagado') return null

  const emitida = data?.existe
  // Las dos condiciones que el backend también exige, en el mismo orden en
  // que conviene resolverlas: primero quién recibe, después cómo viaja.
  const listoParaEmitir = hayCliente && hayTraslado

  const faltante = !hayCliente
    ? 'Falta identificar al cliente — el SIFEN no acepta remisión sin RUC o CI'
    : !hayTraslado
      ? 'Cargá antes los datos del traslado'
      : 'Solo si la mercadería sale en el flete del local'

  return (
    <div style={{ borderBottom:`1px solid ${C.border}` }}>
    <div style={{ padding:'12px 20px',
      display:'flex', alignItems:'center', gap:'10px', flexWrap:'wrap' }}>
      <FileText size={16} color={emitida ? C.success : C.textMuted}
        style={{ flexShrink:0 }} />
      <div style={{ flex:1, minWidth:'150px' }}>
        <p style={{ fontSize:'13px', color:C.text, margin:0 }}>
          Nota de remisión
        </p>
        <p style={{ fontSize:'11.5px', color:C.textMuted, margin:'2px 0 0' }}>
          {emitida ? `${data.numero} · ${data.estado_display || data.estado}` : faltante}
        </p>
      </div>
      {/* El botón de cargar el cliente va antes que el de emitir, porque es
          el paso que desbloquea al otro. Se ofrece siempre —no solo cuando
          falta— para poder corregir un RUC mal tipeado antes de emitir; una
          vez emitida, el dato ya viajó al documento y no se toca. */}
      {!emitida && (
        <button onClick={() => setEditandoCliente(v => !v)} style={{
          display:'flex', alignItems:'center', gap:'6px',
          padding:'7px 12px', borderRadius:'8px', cursor:'pointer',
          background: hayCliente ? C.bgTer : C.warningBg,
          border:`1px solid ${hayCliente ? C.border : C.warningBorder}`,
          color: hayCliente ? C.textSec : C.warning,
          fontSize:'12.5px', fontWeight:'500',
        }}>
          <User size={14}/> {hayCliente ? 'Cliente' : 'Cargar cliente'}
        </button>
      )}
      {emitida ? (
        <button onClick={descargarKude} disabled={bajando} style={{
          display:'flex', alignItems:'center', gap:'6px',
          padding:'7px 12px', borderRadius:'8px', cursor: bajando ? 'wait' : 'pointer',
          background:C.bgTer, border:`1px solid ${C.border}`, color:C.textSec,
          fontSize:'12.5px', fontWeight:'500',
        }}>
          {bajando ? <Loader2 size={14} style={{ animation:'spin 1s linear infinite' }}/>
                   : <FileText size={14}/>}
          KuDE
        </button>
      ) : (
        <button onClick={() => emitirMut.mutate()}
          disabled={!listoParaEmitir || emitirMut.isPending}
          title={listoParaEmitir ? 'Emitir la nota de remisión del traslado'
                                 : faltante}
          style={{
            display:'flex', alignItems:'center', gap:'6px',
            padding:'7px 12px', borderRadius:'8px',
            cursor: listoParaEmitir ? 'pointer' : 'not-allowed',
            opacity: listoParaEmitir ? 1 : 0.5,
            background:C.goldMuted, border:`1px solid ${C.border}`, color:C.goldDark,
            fontSize:'12.5px', fontWeight:'500',
          }}>
          {emitirMut.isPending
            ? <Loader2 size={14} style={{ animation:'spin 1s linear infinite' }}/>
            : <Truck size={14}/>}
          Emitir
        </button>
      )}
    </div>

    {editandoCliente && !emitida && (
      <DatosClienteRemision
        pedido={pedido}
        onListo={() => setEditandoCliente(false)}
      />
    )}
    </div>
  )
}

/**
 * Carga o corrige los datos del cliente de un pedido YA COBRADO.
 *
 * Existe por una razón puntual: la nota de remisión se emite después de
 * cobrar y el SIFEN no la acepta sin receptor identificado (NT 023). Si la
 * venta se cobró como ticket —donde nadie pide el RUC— el pedido quedaba sin
 * forma de despacharse y sin ninguna pantalla donde arreglarlo. El backend
 * abre exactamente esta rendija: en un pedido pagado solo se pueden tocar
 * estos tres campos, nada de ítems ni de montos.
 *
 * Busca en el padrón mientras se escribe para no retipear a un cliente que ya
 * está cargado, que es de donde salen la mitad de los RUC mal escritos.
 *
 * Ojo con lo que esto NO hace: no reescribe una factura ya emitida. El
 * documento electrónico guarda su propio snapshot del receptor al emitirse,
 * porque es un registro histórico. Corregir acá sirve para el documento que
 * todavía no salió.
 */
function DatosClienteRemision({ pedido, onListo }) {
  const queryClient = useQueryClient()
  const [datos, setDatos] = useState({
    cliente_nombre:   pedido.cliente_nombre   || '',
    cliente_ruc:      pedido.cliente_ruc      || '',
    cliente_telefono: pedido.cliente_telefono || '',
  })
  const [busqueda, setBusqueda] = useState('')

  const { data: encontrados = [] } = useQuery({
    queryKey: ['clientes-padron', busqueda],
    queryFn: () => ventasApi.clientes(busqueda).then(r => r.data),
    enabled: busqueda.trim().length >= 2,
  })

  const guardarMut = useMutation({
    mutationFn: () => ventasApi.actualizar(pedido.id, datos),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey:['pedido', pedido.id] })
      queryClient.invalidateQueries({ queryKey:['pedidos'] })
      toast.success('Datos del cliente guardados')
      onListo()
    },
    onError: (err) => toast.error(
      err.response?.data?.error || 'No se pudieron guardar los datos'),
  })

  const set = (k) => (e) => setDatos(d => ({ ...d, [k]: e.target.value }))
  const estiloInput = {
    width:'100%', padding:'8px 10px', borderRadius:'7px',
    border:`1px solid ${C.border}`, fontSize:'13px', fontFamily:'inherit',
    color:C.text, background:C.bg, boxSizing:'border-box',
  }

  const listado = Array.isArray(encontrados)
    ? encontrados
    : (encontrados.results || [])

  return (
    <div style={{ padding:'0 20px 14px', background:C.bgSec }}>
      <p style={{ fontSize:'11.5px', color:C.textMuted, margin:'0 0 10px' }}>
        El SIFEN exige identificar a quien recibe la mercadería. Buscá en el
        padrón o escribilo a mano.
      </p>

      <div style={{ position:'relative', marginBottom:'10px' }}>
        <input value={busqueda} onChange={e => setBusqueda(e.target.value)}
          placeholder="Buscar en el padrón por nombre o RUC..."
          style={estiloInput} />
        {listado.length > 0 && busqueda.trim().length >= 2 && (
          <div style={{ position:'absolute', top:'100%', left:0, right:0, zIndex:5,
            background:C.bg, border:`1px solid ${C.border}`, borderRadius:'8px',
            marginTop:'4px', maxHeight:'170px', overflowY:'auto',
            boxShadow:'0 6px 18px rgba(0,0,0,0.08)' }}>
            {listado.slice(0, 8).map(c => (
              <button key={c.id} onClick={() => {
                setDatos({
                  cliente_nombre:   c.razon_social || '',
                  cliente_ruc:      c.ruc || '',
                  cliente_telefono: c.telefono || '',
                })
                setBusqueda('')
              }} style={{
                display:'block', width:'100%', textAlign:'left', padding:'8px 10px',
                background:'none', border:'none', borderBottom:`1px solid ${C.border}`,
                cursor:'pointer', fontFamily:'inherit',
              }}>
                <span style={{ fontSize:'13px', color:C.text }}>{c.razon_social}</span>
                {c.ruc && (
                  <span style={{ fontSize:'11px', color:C.textMuted, marginLeft:'8px' }}>
                    RUC: {c.ruc}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      <div style={{ display:'grid', gap:'8px',
        gridTemplateColumns:'repeat(auto-fit, minmax(150px, 1fr))' }}>
        <input value={datos.cliente_nombre} onChange={set('cliente_nombre')}
          placeholder="Nombre o razón social" style={estiloInput} />
        <input value={datos.cliente_ruc} onChange={set('cliente_ruc')}
          placeholder="RUC / CI *" style={estiloInput} />
        <input value={datos.cliente_telefono} onChange={set('cliente_telefono')}
          placeholder="Teléfono" style={estiloInput} />
      </div>

      <div style={{ display:'flex', gap:'8px', marginTop:'10px' }}>
        <button onClick={() => guardarMut.mutate()}
          disabled={!datos.cliente_ruc.trim() || guardarMut.isPending}
          style={{
            display:'flex', alignItems:'center', gap:'6px',
            padding:'8px 14px', borderRadius:'8px',
            cursor: datos.cliente_ruc.trim() ? 'pointer' : 'not-allowed',
            opacity: datos.cliente_ruc.trim() ? 1 : 0.5,
            background:C.sidebar, border:`1px solid ${C.gold}`, color:C.gold,
            fontSize:'12.5px', fontWeight:'500',
          }}>
          {guardarMut.isPending
            ? <Loader2 size={14} style={{ animation:'spin 1s linear infinite' }}/>
            : <CheckCircle size={14}/>}
          Guardar
        </button>
        <button onClick={onListo} style={{
          padding:'8px 14px', borderRadius:'8px', cursor:'pointer',
          background:C.bg, border:`1px solid ${C.border}`, color:C.textSec,
          fontSize:'12.5px', fontFamily:'inherit',
        }}>
          Cancelar
        </button>
      </div>
    </div>
  )
}

function AccionesFooter({ pedido, rol, onCambiarEstado, isPending }) {
  const todosPrepados = pedido.todos_preparados

  // Depósito: pendiente → en preparación
  if (rol === 'deposito' && pedido.estado === 'pendiente') {
    return (
      <BtnAccion label="Iniciar preparación" icon={<Truck size={16}/>}
        color={C.warning} onClick={() => onCambiarEstado('en_preparacion')} isPending={isPending} />
    )
  }

  // Depósito: en preparación → listo
  if (rol === 'deposito' && pedido.estado === 'en_preparacion') {
    return (
      <div style={{ display:'flex', flexDirection:'column', gap:'8px' }}>
        {!todosPrepados && (
          <div style={{ display:'flex', alignItems:'center', gap:'6px', padding:'8px 12px',
            background:C.warningBg, border:`1px solid ${C.warningBorder}`,
            borderRadius:'8px', fontSize:'12.5px', color:C.warning }}>
            <AlertCircle size={14} /> Marcá todos los ítems como preparados primero
          </div>
        )}
        <BtnAccion
          label="Marcar como listo para cobrar"
          icon={<CheckCircle size={16}/>}
          color={C.success}
          disabled={!todosPrepados}
          onClick={() => onCambiarEstado('listo')}
          isPending={isPending}
        />
      </div>
    )
  }

  // Vendedor/Encargada/admin: pendiente → listo, directo a caja sin pasar
  // por depósito (el vendedor ya vio el stock disponible en el Showroom).
  // Este es el punto de la ventana de Pedidos donde se revisa, edita o
  // imprime la nota/presupuesto antes de mandarla a cobrar.
  if ((rol === 'vendedor' || rol === 'encargada_ventas' || rol === 'admin') && pedido.estado === 'pendiente') {
    return (
      <div style={{ display:'flex', flexDirection:'column', gap:'8px' }}>
        <BtnAccion label="Enviar a caja" icon={<CreditCard size={16}/>}
          color={C.success} onClick={() => onCambiarEstado('listo')} isPending={isPending} />
        <BtnAccion label="Cancelar pedido" icon={<XCircle size={16}/>}
          color={C.danger} variant="ghost"
          onClick={() => onCambiarEstado('cancelado')} isPending={isPending} />
      </div>
    )
  }

  // Cajero: listo → pagado (simplificado — el módulo de caja completo va aparte)
  if (rol === 'cajero' && pedido.estado === 'listo') {
    return (
      <BtnAccion label="Confirmar pago y cerrar" icon={<CreditCard size={16}/>}
        color={C.success} onClick={() => onCambiarEstado('pagado')} isPending={isPending} />
    )
  }

  // Cancelar (admin, en cualquier estado previo al pago)
  if (pedido.estado !== 'pagado' && pedido.estado !== 'cancelado' && rol === 'admin') {
    return (
      <BtnAccion label="Cancelar pedido" icon={<XCircle size={16}/>}
        color={C.danger} variant="ghost"
        onClick={() => onCambiarEstado('cancelado')} isPending={isPending} />
    )
  }

  return null
}

function BtnAccion({ label, icon, color, variant='filled', disabled, onClick, isPending }) {
  const filled = variant === 'filled'
  return (
    <button
      disabled={disabled || isPending}
      onClick={onClick}
      style={{
        width:'100%', height:'46px', borderRadius:'10px',
        background: filled ? C.sidebar : 'transparent',
        border:`1.5px solid ${disabled ? C.border : color}`,
        color: disabled ? C.textMuted : (filled ? C.gold : color),
        fontSize:'14px', fontWeight:'500',
        cursor: disabled||isPending ? 'not-allowed':'pointer',
        display:'flex', alignItems:'center', justifyContent:'center', gap:'7px',
        opacity: disabled ? 0.5 : 1,
        transition:'all 120ms',
      }}
    >
      {isPending
        ? <Loader2 size={16} style={{ animation:'spin 1s linear infinite' }} />
        : icon}
      {isPending ? 'Procesando...' : label}
    </button>
  )
}

// ─── Página principal ─────────────────────────────────────────────────────────
export default function PedidosPage() {
  const { usuario } = useAuthStore()
  const rol = usuario?.rol || 'vendedor'
  // Encargada de Ventas opera igual que el vendedor en esta pantalla
  const puedeVender = rol === 'admin' || rol === 'encargada_ventas' || rol === 'vendedor'
  const queryClient = useQueryClient()

  const [pedidoActivo, setPedidoActivo] = useState(null)
  const [mostrarNuevo, setMostrarNuevo] = useState(false)
  const [filtroEstado, setFiltroEstado] = useState('')
  // Búsqueda por nombre o CI/RUC del cliente (también entra el número de
  // pedido). Se manda al backend y no se filtra en el cliente: la lista que
  // llega es la del rol y puede no contener el pedido buscado.
  const [busqueda, setBusqueda] = useState('')
  const [busquedaAplicada, setBusquedaAplicada] = useState('')

  // Debounce: en la tablet cada tecla dispararía un request.
  useEffect(() => {
    const t = setTimeout(() => setBusquedaAplicada(busqueda.trim()), 350)
    return () => clearTimeout(t)
  }, [busqueda])

  // Canal WebSocket por rol para recibir notificaciones
  usePedidoSocket({
    rol,
    onMensaje: (msg) => {
      queryClient.invalidateQueries({ queryKey: ['pedidos'] })
      if (msg.tipo === 'pedido_creado' && rol !== 'vendedor') {
        toast(`Nuevo pedido: ${msg.pedido?.numero} — ${msg.pedido?.cliente_nombre || 'Sin nombre'}`,
          { icon:'📋', duration: 5000 })
      }
      if (msg.tipo === 'pedido_listo' && rol === 'cajero') {
        toast(`Pedido ${msg.pedido?.numero} listo para cobrar`, { icon:'✅', duration: 6000 })
      }
    },
  })

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['pedidos', rol, filtroEstado, busquedaAplicada],
    queryFn: () => ventasApi.pedidos({
      estado: filtroEstado || undefined,
      buscar: busquedaAplicada || undefined,
    }).then(r => r.data),
    staleTime: 10_000,
    refetchInterval: 30_000, // fallback polling cada 30s si WebSocket falla
  })

  const pedidos = data?.results || []

  // Filtros de estado visibles según el rol
  const filtrosRol = {
    vendedor:  ['', 'pendiente', 'en_preparacion', 'listo', 'pagado', 'cancelado'],
    deposito:  ['', 'pendiente', 'en_preparacion'],
    cajero:    ['', 'listo', 'pagado'],
    admin:     ['', 'pendiente', 'en_preparacion', 'listo', 'pagado', 'cancelado'],
  }

  const filtrosDisponibles = filtrosRol[rol] || ['']

  const TITULO_ROL = {
    vendedor: 'Mis pedidos',
    deposito: 'Pedidos para preparar',
    cajero:   'Pedidos para cobrar',
    admin:    'Todos los pedidos',
  }

  return (
    <Layout
      pageTitle={TITULO_ROL[rol] || 'Pedidos'}
      breadcrumbs={['Pedidos']}
    >
      {/* Barra de acciones */}
      <div style={{ display:'flex', gap:'10px', flexWrap:'wrap', alignItems:'center',
        marginBottom:'16px' }}>

        {/* Filtros de estado */}
        <div style={{ display:'flex', gap:'6px', flexWrap:'wrap', flex:1 }}>
          {filtrosDisponibles.map(est => {
            const cfg = est ? ESTADO_CFG[est] : null
            const activo = filtroEstado === est
            return (
              <button key={est}
                onClick={() => setFiltroEstado(est)}
                style={{
                  padding:'7px 13px', borderRadius:'8px', cursor:'pointer',
                  fontSize:'12.5px', fontWeight: activo?'500':'400',
                  background: activo ? (cfg?.bg || C.sidebar) : 'transparent',
                  border:`1px solid ${activo ? (cfg?.border || C.gold) : C.border}`,
                  color: activo ? (cfg?.color || C.gold) : C.textSec,
                  transition:'all 120ms',
                  display:'flex', alignItems:'center', gap:'5px',
                }}>
                {cfg?.icon} {cfg?.label || 'Todos'}
                {est && (
                  <span style={{ fontSize:'11px', opacity:0.7 }}>
                    ({pedidos.filter(p => p.estado === est).length})
                  </span>
                )}
              </button>
            )
          })}
        </div>

        {/* Acciones */}
        <div style={{ display:'flex', gap:'8px', flexShrink:0, alignItems:'center' }}>
          <div style={{ position:'relative' }}>
            <Search size={15} style={{ position:'absolute', left:'10px', top:'50%',
              transform:'translateY(-50%)', color:C.textMuted, pointerEvents:'none' }} />
            <input
              value={busqueda}
              onChange={e => setBusqueda(e.target.value)}
              placeholder="Buscar cliente, CI/RUC o N.º"
              style={{ height:'38px', width:'232px', padding:'0 30px 0 32px',
                border:`1px solid ${busqueda ? C.gold : C.border}`, borderRadius:'9px',
                fontSize:'13px', color:C.text, background:C.bg, outline:'none' }}
            />
            {busqueda && (
              <button onClick={() => setBusqueda('')} title="Limpiar búsqueda"
                style={{ position:'absolute', right:'6px', top:'50%',
                  transform:'translateY(-50%)', background:'transparent', border:'none',
                  cursor:'pointer', color:C.textMuted, display:'flex', padding:'4px' }}>
                <X size={14} />
              </button>
            )}
          </div>

          <button onClick={() => refetch()}
            style={{ width:'38px', height:'38px', borderRadius:'9px',
              background:'transparent', border:`1px solid ${C.border}`,
              cursor:'pointer', color:C.textSec,
              display:'flex', alignItems:'center', justifyContent:'center' }}>
            <RefreshCw size={16} />
          </button>

          {puedeVender && (
            <button onClick={() => setMostrarNuevo(true)}
              style={{ display:'flex', alignItems:'center', gap:'6px',
                padding:'8px 16px', background:C.sidebar,
                border:`1px solid ${C.gold}`, borderRadius:'9px',
                color:C.gold, fontSize:'13.5px', fontWeight:'500',
                cursor:'pointer', whiteSpace:'nowrap' }}>
              <Plus size={15} /> Nuevo pedido
            </button>
          )}
        </div>
      </div>

      {/* Contenido */}
      {isLoading ? (
        <div style={{ display:'flex', flexDirection:'column', gap:'8px' }}>
          {Array.from({length:5}).map((_,i)=>(
            <div key={i} style={{ height:'80px', background:C.bgSec,
              border:`1px solid ${C.border}`, borderRadius:'12px',
              animation:'pulse 1.6s ease-in-out infinite' }} />
          ))}
        </div>
      ) : pedidos.length === 0 ? (
        <div style={{ textAlign:'center', padding:'60px 20px', color:C.textMuted }}>
          <FileText size={48} style={{ margin:'0 auto 14px', opacity:0.2 }} />
          <p style={{ fontSize:'17px', fontWeight:'500', color:C.textSec,
            fontFamily:'var(--font-display)' }}>
            {busquedaAplicada
              ? `Ningún pedido coincide con "${busquedaAplicada}"`
              : filtroEstado ? `Sin pedidos en estado "${ESTADO_CFG[filtroEstado]?.label}"` : 'Sin pedidos'}
          </p>
          {busquedaAplicada && (
            <p style={{ fontSize:'12.5px', color:C.textMuted, marginTop:'6px' }}>
              Se busca por nombre del cliente, CI/RUC o número de pedido.
            </p>
          )}
          {puedeVender && !filtroEstado && !busquedaAplicada && (
            <button onClick={() => setMostrarNuevo(true)}
              style={{ marginTop:'16px', display:'inline-flex', alignItems:'center', gap:'7px',
                padding:'10px 20px', background:C.sidebar,
                border:`1px solid ${C.gold}`, borderRadius:'10px',
                color:C.gold, fontSize:'13.5px', cursor:'pointer' }}>
              <Plus size={15} /> Crear primer pedido
            </button>
          )}
        </div>
      ) : (
        <div>
          {pedidos
            .filter(p => !filtroEstado || p.estado === filtroEstado)
            .map(p => (
              <PedidoCard
                key={p.id}
                pedido={p}
                onAbrir={setPedidoActivo}
                esActivo={pedidoActivo?.id === p.id}
                rol={rol}
              />
            ))
          }
        </div>
      )}

      {/* Panel detalle */}
      {pedidoActivo && (
        <PanelDetalle
          pedido={pedidoActivo}
          rol={rol}
          puedeEditarPrecio={Boolean(usuario?.puede_editar_precio)}
          onCerrar={() => setPedidoActivo(null)}
        />
      )}

      {/* Panel nuevo pedido */}
      {mostrarNuevo && (
        <>
          <div onClick={() => setMostrarNuevo(false)} style={{ position:'fixed', inset:0,
            zIndex:150, background:'rgba(26,23,20,0.4)', backdropFilter:'blur(2px)' }} />
          <div style={{ position:'fixed', top:0, right:0, bottom:0, zIndex:151,
            width:'min(580px,95vw)', background:C.bg,
            borderLeft:`1px solid ${C.border}`,
            boxShadow:'-8px 0 32px rgba(0,0,0,0.12)',
            animation:'slideIn 200ms ease' }}>
            <NuevoPedidoForm
              onPedidoCreado={(p) => { setMostrarNuevo(false); setPedidoActivo(p) }}
              onCancelar={() => setMostrarNuevo(false)}
            />
          </div>
        </>
      )}

      <style>{`
        @keyframes slideIn { from{transform:translateX(100%)} to{transform:translateX(0)} }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.45} }
        @keyframes spin { to{transform:rotate(360deg)} }
      `}</style>
    </Layout>
  )
}
