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
import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus, RefreshCw, FileText, Clock, Truck,
  CheckCircle, CreditCard, XCircle, ChevronRight,
  Package, User, AlertCircle, Loader2,
} from 'lucide-react'
import Layout from '../components/layout/Layout'
import NuevoPedidoForm from '../components/ventas/NuevoPedidoForm'
import { ventasApi } from '../services/api'
import { useAuthStore } from '../store/authStore'
import { usePedidoSocket } from '../hooks/usePedidoSocket'
import toast from 'react-hot-toast'

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

  const { data: pedido, isLoading } = useQuery({
    queryKey: ['pedido', pedidoResumen?.id],
    queryFn: () => ventasApi.detalle(pedidoResumen.id).then(r => r.data),
    enabled: Boolean(pedidoResumen),
    staleTime: 5000,
  })

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

  // WebSocket del pedido específico
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
      toast.success(`Estado actualizado: ${ESTADO_CFG[pedidoActualizado.estado]?.label}`)
    },
    onError: (err) => toast.error(err.response?.data?.error || 'Error al cambiar estado'),
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
              <EstadoBadge estado={pedidoResumen.estado} />
              <button onClick={onCerrar} style={{ background:'transparent', border:'none',
                cursor:'pointer', color:C.textMuted, padding:'6px',
                display:'flex', alignItems:'center', borderRadius:'8px' }}>
                <XCircle size={20} />
              </button>
            </div>
          </div>
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

              {/* Observaciones */}
              {pedido.cliente_observaciones && (
                <div style={{ padding:'12px 20px', borderBottom:`1px solid ${C.border}`,
                  background:C.bgSec }}>
                  <p style={{ fontSize:'11px', color:C.textMuted, marginBottom:'3px' }}>Observaciones</p>
                  <p style={{ fontSize:'13px', color:C.textSec }}>{pedido.cliente_observaciones}</p>
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
      <style>{`
        @keyframes slideIn { from{transform:translateX(100%)} to{transform:translateX(0)} }
        @keyframes spin { to{transform:rotate(360deg)} }
      `}</style>
    </>
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

  // Cajero: listo → pagado (simplificado — el módulo de caja completo va aparte)
  if (rol === 'cajero' && pedido.estado === 'listo') {
    return (
      <BtnAccion label="Confirmar pago y cerrar" icon={<CreditCard size={16}/>}
        color={C.success} onClick={() => onCambiarEstado('pagado')} isPending={isPending} />
    )
  }

  // Cancelar (admin, encargada de ventas o vendedor en estados previos al pago)
  if (pedido.estado !== 'pagado' && pedido.estado !== 'cancelado' &&
      (rol === 'admin' || ((rol === 'vendedor' || rol === 'encargada_ventas') && pedido.estado === 'pendiente'))) {
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
    queryKey: ['pedidos', rol, filtroEstado],
    queryFn: () => ventasApi.pedidos({ estado: filtroEstado || undefined }).then(r => r.data),
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
        <div style={{ display:'flex', gap:'8px', flexShrink:0 }}>
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
            {filtroEstado ? `Sin pedidos en estado "${ESTADO_CFG[filtroEstado]?.label}"` : 'Sin pedidos'}
          </p>
          {puedeVender && !filtroEstado && (
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
