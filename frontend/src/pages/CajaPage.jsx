/**
 * CajaPage — Módulo de caja completo
 *
 * Estados de la pantalla:
 *   sin_sesion   → el cajero no ha abierto la caja
 *   con_sesion   → sesión activa, lista para cobrar pedidos
 *   cobro_activo → confirmando el pago de un pedido específico
 *   ticket       → mostrando el ticket tras cobrar
 *   cierre       → confirmando el cierre de la sesión
 *
 * El WebSocket de rol 'cajero' notifica en tiempo real cuando
 * llega un pedido listo para cobrar.
 */
import { useState, useCallback, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  CreditCard, DollarSign, Banknote, ArrowRightLeft,
  CheckCircle, XCircle, Printer, Lock, Unlock,
  ChevronRight, Package, Clock, AlertCircle,
  RefreshCw, Receipt, X, Loader2, TrendingUp,
  Wifi, WifiOff, Search, User, Copy, ClipboardCheck, ExternalLink,
} from 'lucide-react'
import Layout from '../components/layout/Layout'
import { cajaApi, ventasApi } from '../services/api'
import { usePedidoSocket } from '../hooks/usePedidoSocket'
import { useDevice } from '../hooks/useDevice'
import toast from 'react-hot-toast'

const C = {
  sidebar:'#453941', sidebarHov:'#362F31',
  gold:'#B99C74', goldDark:'#8a7355', goldLight:'#d4bc98', goldMuted:'rgba(185,156,116,0.10)',
  border:'#e8e4df', bg:'#ffffff', bgSec:'#fafaf9', bgTer:'#f5f4f2',
  text:'#1a1714', textSec:'#6b6560', textMuted:'#9e9892',
  success:'#3d7a5a', successBg:'#edf7f1', successBorder:'#b8deca',
  warning:'#8a6a1a', warningBg:'#fef9ee', warningBorder:'#f0d98a',
  danger:'#9a3030', dangerBg:'#fef0f0', dangerBorder:'#f0b8b8',
  info:'#2a5c8a', infoBg:'#eef4fb',
}

// Tope de descuento que puede aplicar un cajero al cobrar (debe coincidir
// con DESCUENTO_CAJA_MAXIMO en backend/apps/caja/views.py)
const DESCUENTO_CAJA_MAXIMO = 70

const MEDIOS = [
  { key:'efectivo',     label:'Efectivo',          icon:<Banknote size={18}/> },
  { key:'debito',       label:'Tarjeta débito',    icon:<CreditCard size={18}/> },
  { key:'credito',      label:'Tarjeta crédito',   icon:<CreditCard size={18}/> },
  { key:'transferencia',label:'Transferencia',     icon:<ArrowRightLeft size={18}/> },
]

function formatGs(v) { return `Gs. ${Number(v||0).toLocaleString('es-PY')}` }

function etiquetaTasaIva(tasa) {
  if (tasa === 5) return '5%'
  if (tasa === 0) return 'Exento'
  return '10%'
}

function formatFecha(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('es-PY', {
    day:'2-digit', month:'2-digit', year:'numeric',
    hour:'2-digit', minute:'2-digit',
  })
}

// ─── Pantalla: sin sesión abierta ─────────────────────────────────────────────
function PantallaSinSesion({ onAbrir, isLoading }) {
  const [monto, setMonto] = useState('')

  return (
    <div style={{ display:'flex', flexDirection:'column', alignItems:'center',
      justifyContent:'center', minHeight:'70vh', padding:'20px' }}>
      <div style={{ width:'64px', height:'64px', borderRadius:'16px',
        background:C.sidebar, border:`1px solid ${C.gold}`,
        display:'flex', alignItems:'center', justifyContent:'center',
        marginBottom:'20px' }}>
        <Lock size={28} style={{ color:C.gold }} />
      </div>
      <h2 style={{ fontSize:'22px', fontWeight:'500', fontFamily:'var(--font-display)',
        color:C.text, marginBottom:'6px' }}>Caja cerrada</h2>
      <p style={{ fontSize:'14px', color:C.textMuted, marginBottom:'32px' }}>
        Abrí la caja para comenzar a cobrar
      </p>

      <div style={{ width:'100%', maxWidth:'320px' }}>
        <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
          color:C.textSec, marginBottom:'6px' }}>
          Monto de apertura (Gs.)
        </label>
        <input
          type="number" min="0" step="1000"
          value={monto}
          onChange={e => setMonto(e.target.value)}
          placeholder="Ej: 500.000"
          style={{ width:'100%', height:'44px', padding:'0 14px',
            border:`1px solid ${C.border}`, borderRadius:'10px',
            fontSize:'16px', color:C.text, background:C.bg,
            outline:'none', marginBottom:'14px', textAlign:'right' }}
          onFocus={e=>e.target.style.borderColor=C.gold}
          onBlur={e=>e.target.style.borderColor=C.border}
        />
        <button
          onClick={() => onAbrir(Number(monto) || 0)}
          disabled={isLoading}
          style={{ width:'100%', height:'50px', borderRadius:'12px',
            background:C.sidebar, border:`1.5px solid ${C.gold}`,
            color:C.gold, fontSize:'15px', fontWeight:'500',
            cursor:'pointer', display:'flex', alignItems:'center',
            justifyContent:'center', gap:'8px', transition:'background 120ms' }}
          onMouseEnter={e=>e.currentTarget.style.background=C.sidebarHov}
          onMouseLeave={e=>e.currentTarget.style.background=C.sidebar}
        >
          {isLoading
            ? <Loader2 size={18} style={{ animation:'spin 1s linear infinite' }} />
            : <Unlock size={18} />}
          {isLoading ? 'Abriendo...' : 'Abrir caja'}
        </button>
      </div>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  )
}

// ─── Card de pedido en la cola ────────────────────────────────────────────────
function PedidoCard({ pedido, activo, onClick }) {
  const [hov, setHov] = useState(false)
  const esUrgente = pedido.estado === 'listo'

  return (
    <div
      onClick={() => onClick(pedido)}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        background: activo ? C.sidebar : (hov ? C.bgSec : C.bg),
        border: `1.5px solid ${activo ? C.gold : (hov ? C.goldDark : C.border)}`,
        borderRadius:'12px', padding:'14px 16px', cursor:'pointer',
        transition:'all 140ms', marginBottom:'8px',
        boxShadow: activo ? '0 0 0 3px rgba(185,156,116,0.15)' : 'none',
      }}
    >
      <div style={{ display:'flex', alignItems:'flex-start',
        justifyContent:'space-between', gap:'10px' }}>
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ display:'flex', alignItems:'center', gap:'7px', marginBottom:'3px' }}>
            <p style={{ fontSize:'14px', fontWeight:'600',
              color: activo ? C.gold : C.text, fontFamily:'monospace' }}>
              {pedido.numero}
            </p>
            {esUrgente && !activo && (
              <span style={{ fontSize:'10px', fontWeight:'500', padding:'1px 7px',
                borderRadius:'20px', background:C.successBg, color:C.success,
                border:`1px solid ${C.successBorder}` }}>
                Listo ✓
              </span>
            )}
          </div>
          <p style={{ fontSize:'13px', color: activo ? C.goldLight : C.textSec,
            overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
            {pedido.cliente_nombre || 'Consumidor Final'}
          </p>
          <p style={{ fontSize:'11px', color: activo ? C.textMuted : C.textMuted,
            marginTop:'2px' }}>
            {pedido.items_count} ítem{pedido.items_count!==1?'s':''}
            {pedido.vendedor_nombre && ` · ${pedido.vendedor_nombre}`}
          </p>
        </div>
        <div style={{ textAlign:'right', flexShrink:0 }}>
          <p style={{ fontSize:'16px', fontWeight:'700',
            color: activo ? C.gold : C.goldDark }}>
            {formatGs(pedido.total)}
          </p>
          <ChevronRight size={15} style={{ color: activo ? C.gold : C.textMuted }} />
        </div>
      </div>
    </div>
  )
}

// ─── Panel de cobro ───────────────────────────────────────────────────────────
// ─── Buscador de cliente del padrón para la caja (factura) ────────────────────
function BuscadorClienteCaja({ onSeleccionar }) {
  const [q, setQ] = useState('')
  const [abierto, setAbierto] = useState(false)

  const { data, isFetching } = useQuery({
    queryKey: ['clientes-caja', q],
    queryFn: () => ventasApi.clientes(q).then(r => r.data),
    enabled: abierto && q.trim().length >= 2,
    staleTime: 10000,
  })
  const resultados = data?.results || []

  return (
    <div style={{ marginBottom:'12px', position:'relative' }}>
      <div style={{ position:'relative' }}>
        <Search size={15} style={{ position:'absolute', left:'11px', top:'50%',
          transform:'translateY(-50%)', color:C.gold, pointerEvents:'none' }} />
        <input
          value={q}
          onChange={e => { setQ(e.target.value); setAbierto(true) }}
          onFocus={() => setAbierto(true)}
          placeholder="Buscar cliente por nombre o RUC..."
          style={{ width:'100%', height:'42px', padding:'0 12px 0 36px',
            border:`1.5px solid ${C.gold}`, borderRadius:'8px',
            fontSize:'13.5px', color:C.text, background:C.bg, outline:'none' }}
        />
        {isFetching && <Loader2 size={15} style={{ position:'absolute', right:'11px',
          top:'50%', transform:'translateY(-50%)', color:C.textMuted,
          animation:'spin 1s linear infinite' }} />}
      </div>

      {abierto && q.trim().length >= 2 && (
        <div style={{ position:'absolute', top:'46px', left:0, right:0, zIndex:20,
          background:C.bg, border:`1px solid ${C.border}`, borderRadius:'9px',
          boxShadow:'0 8px 24px rgba(0,0,0,0.12)', maxHeight:'220px', overflowY:'auto' }}>
          {resultados.length === 0 ? (
            <p style={{ fontSize:'12.5px', color:C.textMuted, padding:'12px', textAlign:'center' }}>
              {isFetching ? 'Buscando...' : 'Sin clientes registrados con ese dato'}
            </p>
          ) : (
            resultados.map(c => (
              <button key={c.id}
                onClick={() => { onSeleccionar(c); setAbierto(false); setQ('') }}
                style={{ width:'100%', display:'flex', alignItems:'center', gap:'9px',
                  padding:'10px 12px', background:'transparent', border:'none',
                  borderBottom:`1px solid ${C.bgTer}`, cursor:'pointer', textAlign:'left' }}>
                <User size={15} style={{ color:C.goldDark, flexShrink:0 }} />
                <div style={{ minWidth:0 }}>
                  <p style={{ fontSize:'13px', fontWeight:'500', color:C.text }}>{c.razon_social}</p>
                  {c.ruc && <p style={{ fontSize:'11px', color:C.textMuted }}>RUC: {c.ruc}</p>}
                </div>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}

function PanelCobro({ pedido: pedidoResumen, sesion, onPagado, onCancelar }) {
  const [medio, setMedio]       = useState('efectivo')
  const [recibido, setRecibido] = useState('')
  const [referencia, setReferencia] = useState('')
  const [tipoComprobante, setTipoComprobante] = useState('ticket')
  const [condicionVenta, setCondicionVenta] = useState('Contado')
  const [descuentoPct, setDescuentoPct] = useState('')   // % de descuento en caja
  // Datos del cliente para factura (se autocompletan desde el padrón)
  const [cli, setCli] = useState({ id:null, razon_social:'', ruc:'', telefono:'', direccion:'' })
  const queryClient = useQueryClient()
  const device = useDevice()

  const { data: pedido, isLoading } = useQuery({
    queryKey: ['pedido-caja', pedidoResumen?.id],
    queryFn: () => ventasApi.detalle(pedidoResumen.id).then(r => r.data),
    enabled: Boolean(pedidoResumen),
    staleTime: 5000,
  })

  // Si el pedido ya trae un cliente del padrón, precargarlo para la factura
  useEffect(() => {
    if (pedido?.cliente_ruc && !cli.ruc) {
      setCli(c => ({ ...c, razon_social: pedido.cliente_nombre || '', ruc: pedido.cliente_ruc }))
    }
  }, [pedido])

  // Monto base = el que viene del pedido (ya considera precio negociado)
  const montoBase = Number(pedido?.monto_a_cobrar ?? pedido?.total ?? pedidoResumen?.monto_a_cobrar ?? pedidoResumen?.total ?? 0)
  // Aplicar descuento porcentual de caja (tope alineado al backend: DESCUENTO_CAJA_MAXIMO)
  const pct = Math.min(DESCUENTO_CAJA_MAXIMO, Math.max(0, Number(descuentoPct) || 0))
  const total = Math.round(montoBase * (100 - pct) / 100)
  const vuelto    = medio === 'efectivo' && Number(recibido) > total
    ? Number(recibido) - total
    : 0

  const mutation = useMutation({
    mutationFn: () => cajaApi.registrarPago({
      pedido_id:          pedidoResumen.id,
      medio_pago:         medio,
      monto_recibido:     medio === 'efectivo' ? Number(recibido) || total : undefined,
      referencia_externa: referencia,
      tipo_comprobante:   tipoComprobante,
      cliente_ruc:        tipoComprobante === 'factura' ? cli.ruc : '',
      cliente_razon_social: tipoComprobante === 'factura' ? cli.razon_social : '',
      cliente_telefono:   tipoComprobante === 'factura' ? cli.telefono : '',
      cliente_direccion:  tipoComprobante === 'factura' ? cli.direccion : '',
      guardar_cliente:    tipoComprobante === 'factura' && Boolean(cli.ruc && cli.razon_social),
      condicion_venta:    tipoComprobante === 'factura' ? condicionVenta : 'Contado',
      descuento_porcentaje: pct,
    }).then(r => r.data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['pedidos'] })
      queryClient.invalidateQueries({ queryKey: ['sesion-caja'] })
      onPagado(data)
    },
    onError: (err) => {
      toast.error(err.response?.data?.error || 'Error al registrar el pago')
    },
  })

  const facturaSinDatos = tipoComprobante === 'factura' &&
    !(cli.ruc.trim() && cli.razon_social.trim())

  const puedeConfirmar = pedido?.estado === 'listo' &&
    !facturaSinDatos &&
    (medio !== 'efectivo' || Number(recibido) >= total || !recibido)

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>
      {/* Header */}
      <div style={{ padding:'16px 20px', borderBottom:`1px solid ${C.border}`,
        display:'flex', alignItems:'center', justifyContent:'space-between',
        flexShrink:0 }}>
        <div>
          <p style={{ fontSize:'11px', color:C.textMuted, fontFamily:'monospace' }}>
            {pedidoResumen?.numero}
          </p>
          <h2 style={{ fontSize:'17px', fontWeight:'500',
            fontFamily:'var(--font-display)', color:C.text, marginTop:'2px' }}>
            {pedidoResumen?.cliente_nombre || 'Consumidor Final'}
          </h2>
        </div>
        <div style={{ textAlign:'right' }}>
          <p style={{ fontSize:'22px', fontWeight:'700', color:C.goldDark }}>
            {formatGs(total)}
          </p>
          <p style={{ fontSize:'11px', color:C.textMuted }}>total a cobrar</p>
        </div>
      </div>

      {/* Body scrollable */}
      <div style={{ flex:1, overflowY:'auto', padding:'18px 20px',
        WebkitOverflowScrolling:'touch' }}>

        {/* Detalle de ítems */}
        {isLoading ? (
          <div style={{ height:'80px', background:C.bgTer, borderRadius:'10px',
            animation:'pulse 1.6s infinite', marginBottom:'16px' }} />
        ) : pedido?.items?.map(item => (
          <div key={item.id} style={{ display:'flex', justifyContent:'space-between',
            alignItems:'flex-start', padding:'8px 0',
            borderBottom:`1px solid ${C.border}` }}>
            <div style={{ flex:1, minWidth:0, paddingRight:'10px' }}>
              <p style={{ fontSize:'13px', fontWeight:'500', color:C.text }}>
                {item.descripcion}
              </p>
              <p style={{ fontSize:'11px', color:C.textMuted }}>
                {Number(item.cantidad).toFixed(2)} × {formatGs(item.precio_unitario)}
              </p>
            </div>
            <p style={{ fontSize:'14px', fontWeight:'600', color:C.goldDark,
              flexShrink:0 }}>
              {formatGs(item.subtotal)}
            </p>
          </div>
        ))}

        {/* Totales */}
        {pedido && (
          <div style={{ marginTop:'12px', paddingTop:'12px' }}>
            {Number(pedido.descuento) > 0 && (
              <div style={{ display:'flex', justifyContent:'space-between',
                marginBottom:'4px' }}>
                <span style={{ fontSize:'13px', color:C.textSec }}>Descuento</span>
                <span style={{ fontSize:'13px', color:C.danger }}>
                  − {formatGs(pedido.descuento)}
                </span>
              </div>
            )}
            {pedido.total_ajustado != null && Number(pedido.total_ajustado) !== Number(pedido.total) && (
              <div style={{ display:'flex', justifyContent:'space-between', marginBottom:'4px' }}>
                <span style={{ fontSize:'12.5px', color:C.textMuted }}>
                  Precio negociado (era {formatGs(pedido.total)})
                </span>
              </div>
            )}
            {pct > 0 && (
              <div style={{ display:'flex', justifyContent:'space-between', marginBottom:'4px' }}>
                <span style={{ fontSize:'13px', color:C.textSec }}>Descuento caja ({pct}%)</span>
                <span style={{ fontSize:'13px', color:C.danger }}>
                  − {formatGs(Math.round(montoBase * pct / 100))}
                </span>
              </div>
            )}
            <div style={{ display:'flex', justifyContent:'space-between',
              padding:'8px 0', borderTop:`2px solid ${C.border}` }}>
              <span style={{ fontSize:'15px', fontWeight:'600', color:C.text }}>TOTAL</span>
              <span style={{ fontSize:'18px', fontWeight:'700', color:C.goldDark }}>
                {formatGs(total)}
              </span>
            </div>
          </div>
        )}

        <div style={{ height:'1px', background:C.border, margin:'16px 0' }} />

        {/* Descuento por porcentaje en caja */}
        <p style={{ fontSize:'11px', fontWeight:'500', color:C.textMuted,
          textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'10px' }}>
          Descuento
        </p>
        <div style={{ display:'flex', alignItems:'center', gap:'10px', marginBottom:'8px' }}>
          <div style={{ position:'relative', width:'120px' }}>
            <input
              type="number" min="0" max={DESCUENTO_CAJA_MAXIMO} step="1"
              value={descuentoPct}
              onChange={e => setDescuentoPct(e.target.value)}
              placeholder="0"
              style={{ width:'100%', height:'44px', padding:'0 32px 0 12px', textAlign:'right',
                border:`1.5px solid ${pct > 0 ? C.gold : C.border}`, borderRadius:'9px',
                fontSize:'17px', fontWeight:'600', color:C.text, background:C.bg, outline:'none' }}
            />
            <span style={{ position:'absolute', right:'12px', top:'50%', transform:'translateY(-50%)',
              fontSize:'15px', color:C.textMuted, pointerEvents:'none' }}>%</span>
          </div>
          {pct > 0 && (
            <div style={{ flex:1, fontSize:'12.5px', color:C.textSec }}>
              <p>Sobre {formatGs(montoBase)}</p>
              <p style={{ color:C.success, fontWeight:'500' }}>
                − {formatGs(Math.round(montoBase * pct / 100))} de descuento
              </p>
            </div>
          )}
        </div>
        {pct > 0 && (
          <p style={{ fontSize:'11.5px', color:C.textMuted, marginBottom:'4px' }}>
            Total con descuento: <strong style={{ color:C.goldDark }}>{formatGs(total)}</strong>
          </p>
        )}

        <div style={{ height:'1px', background:C.border, margin:'16px 0' }} />

        {/* Tipo de comprobante */}
        <p style={{ fontSize:'11px', fontWeight:'500', color:C.textMuted,
          textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'10px' }}>
          Tipo de comprobante
        </p>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'8px',
          marginBottom:'16px' }}>
          {[
            { key:'ticket',  label:'Ticket',  desc:'Comprobante simple' },
            { key:'factura', label:'Factura', desc:'Con RUC y desglose de IVA' },
          ].map(t => (
            <button key={t.key} onClick={() => setTipoComprobante(t.key)}
              style={{
                padding:'11px 12px', borderRadius:'10px', cursor:'pointer',
                background: tipoComprobante===t.key ? C.sidebar : 'transparent',
                border:`1.5px solid ${tipoComprobante===t.key ? C.gold : C.border}`,
                color: tipoComprobante===t.key ? C.gold : C.textSec,
                display:'flex', flexDirection:'column', alignItems:'center', gap:'3px',
                transition:'all 140ms', WebkitTapHighlightColor:'transparent',
              }}>
              <span style={{ fontSize:'14px', fontWeight: tipoComprobante===t.key?'600':'500' }}>{t.label}</span>
              <span style={{ fontSize:'10.5px', opacity:0.8 }}>{t.desc}</span>
            </button>
          ))}
        </div>

        {/* Datos fiscales del cliente — solo para factura */}
        {tipoComprobante === 'factura' && (
          <div style={{ marginBottom:'16px', padding:'14px',
            background:C.bgSec, borderRadius:'10px', border:`1px solid ${C.border}` }}>
            <p style={{ fontSize:'11px', fontWeight:'600', color:C.textMuted,
              textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'10px' }}>
              Datos del cliente
            </p>

            {/* Buscador del padrón: por RUC o nombre, autocompleta los campos */}
            <BuscadorClienteCaja
              onSeleccionar={(c) => setCli({
                id: c.id, razon_social: c.razon_social, ruc: c.ruc,
                telefono: c.telefono || '', direccion: c.direccion || '',
              })}
            />

            <div style={{ marginBottom:'10px' }}>
              <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
                color:C.textSec, marginBottom:'5px' }}>Razón social / Nombre</label>
              <input
                value={cli.razon_social}
                onChange={e => setCli(c => ({ ...c, razon_social: e.target.value }))}
                placeholder="Nombre del cliente"
                style={{ width:'100%', height:'42px', padding:'0 12px',
                  border:`1px solid ${C.border}`, borderRadius:'8px',
                  fontSize:'14px', color:C.text, background:C.bg, outline:'none' }}
                onFocus={e => e.target.style.borderColor = C.gold}
                onBlur={e => e.target.style.borderColor = C.border}
              />
            </div>

            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'10px', marginBottom:'10px' }}>
              <div>
                <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
                  color:C.textSec, marginBottom:'5px' }}>RUC / CI</label>
                <input
                  value={cli.ruc}
                  onChange={e => setCli(c => ({ ...c, ruc: e.target.value }))}
                  placeholder="80012345-6"
                  style={{ width:'100%', height:'42px', padding:'0 12px',
                    border:`1px solid ${C.border}`, borderRadius:'8px',
                    fontSize:'14px', color:C.text, background:C.bg, outline:'none' }}
                  onFocus={e => e.target.style.borderColor = C.gold}
                  onBlur={e => e.target.style.borderColor = C.border}
                />
              </div>
              <div>
                <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
                  color:C.textSec, marginBottom:'5px' }}>Teléfono</label>
                <input
                  value={cli.telefono}
                  onChange={e => setCli(c => ({ ...c, telefono: e.target.value }))}
                  placeholder="09xx xxx xxx"
                  style={{ width:'100%', height:'42px', padding:'0 12px',
                    border:`1px solid ${C.border}`, borderRadius:'8px',
                    fontSize:'14px', color:C.text, background:C.bg, outline:'none' }}
                  onFocus={e => e.target.style.borderColor = C.gold}
                  onBlur={e => e.target.style.borderColor = C.border}
                />
              </div>
            </div>

            <div style={{ marginBottom:'10px' }}>
              <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
                color:C.textSec, marginBottom:'5px' }}>Dirección (opcional)</label>
              <input
                value={cli.direccion}
                onChange={e => setCli(c => ({ ...c, direccion: e.target.value }))}
                placeholder="Dirección del cliente"
                style={{ width:'100%', height:'42px', padding:'0 12px',
                  border:`1px solid ${C.border}`, borderRadius:'8px',
                  fontSize:'14px', color:C.text, background:C.bg, outline:'none' }}
                onFocus={e => e.target.style.borderColor = C.gold}
                onBlur={e => e.target.style.borderColor = C.border}
              />
            </div>

            {cli.ruc && cli.razon_social && !cli.id && (
              <p style={{ fontSize:'11.5px', color:C.goldDark, marginBottom:'8px' }}>
                Este cliente se guardará en el padrón para futuras compras.
              </p>
            )}

            {facturaSinDatos && (
              <p style={{ fontSize:'11.5px', color:C.danger, marginBottom:'8px' }}>
                Para emitir factura, completá al menos la razón social y el RUC/CI.
              </p>
            )}

            <div>
              <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
                color:C.textSec, marginBottom:'5px' }}>Condición de venta</label>
              <div style={{ display:'flex', gap:'8px' }}>
                {['Contado','Crédito'].map(cv => (
                  <button key={cv} onClick={() => setCondicionVenta(cv)}
                    style={{ flex:1, height:'40px', borderRadius:'8px', cursor:'pointer',
                      background: condicionVenta===cv ? C.sidebar : C.bg,
                      border:`1px solid ${condicionVenta===cv ? C.gold : C.border}`,
                      color: condicionVenta===cv ? C.gold : C.textSec,
                      fontSize:'13px', fontWeight: condicionVenta===cv?'500':'400',
                      WebkitTapHighlightColor:'transparent' }}>
                    {cv}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Selector de medio de pago */}
        <p style={{ fontSize:'11px', fontWeight:'500', color:C.textMuted,
          textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'10px' }}>
          Medio de pago
        </p>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'8px',
          marginBottom:'16px' }}>
          {MEDIOS.map(m => (
            <button key={m.key} onClick={() => setMedio(m.key)}
              style={{
                padding:'12px 10px', borderRadius:'10px', cursor:'pointer',
                background: medio===m.key ? C.sidebar : 'transparent',
                border:`1.5px solid ${medio===m.key ? C.gold : C.border}`,
                color: medio===m.key ? C.gold : C.textSec,
                fontSize:'13px', fontWeight: medio===m.key?'500':'400',
                display:'flex', flexDirection:'column', alignItems:'center', gap:'5px',
                transition:'all 140ms',
                WebkitTapHighlightColor:'transparent',
              }}>
              {m.icon}
              {m.label}
            </button>
          ))}
        </div>

        {/* Campo monto recibido (solo efectivo) */}
        {medio === 'efectivo' && (
          <div style={{ marginBottom:'12px' }}>
            <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
              color:C.textSec, marginBottom:'6px' }}>
              Monto recibido (Gs.)
            </label>
            <input
              type="number" min={total} step="1000"
              value={recibido}
              onChange={e => setRecibido(e.target.value)}
              placeholder={String(total)}
              style={{ width:'100%', height:'48px', padding:'0 14px',
                border:`1px solid ${C.border}`, borderRadius:'10px',
                fontSize:'18px', color:C.text, background:C.bg,
                outline:'none', textAlign:'right', fontWeight:'600' }}
              onFocus={e => e.target.style.borderColor = C.gold}
              onBlur={e => e.target.style.borderColor = C.border}
            />
            {/* Atajos rápidos de billetes */}
            <div style={{ display:'flex', gap:'6px', marginTop:'8px',
              flexWrap:'wrap' }}>
              {[total, Math.ceil(total/50000)*50000, Math.ceil(total/100000)*100000, 500000, 1000000]
                .filter((v,i,a) => v > 0 && a.indexOf(v) === i && v >= total)
                .slice(0,5)
                .map(v => (
                  <button key={v} onClick={() => setRecibido(String(v))}
                    style={{ padding:'5px 10px', borderRadius:'6px', cursor:'pointer',
                      background: String(v)===String(recibido) ? C.sidebar : C.bgTer,
                      border:`1px solid ${String(v)===String(recibido) ? C.gold : C.border}`,
                      color: String(v)===String(recibido) ? C.gold : C.textSec,
                      fontSize:'12px', transition:'all 120ms',
                      WebkitTapHighlightColor:'transparent' }}>
                    {formatGs(v)}
                  </button>
                ))}
            </div>

            {/* Vuelto */}
            {vuelto > 0 && (
              <div style={{ marginTop:'10px', padding:'12px 16px',
                background:C.successBg, border:`1px solid ${C.successBorder}`,
                borderRadius:'10px', display:'flex', alignItems:'center',
                justifyContent:'space-between' }}>
                <span style={{ fontSize:'14px', fontWeight:'500', color:C.success }}>
                  Vuelto
                </span>
                <span style={{ fontSize:'20px', fontWeight:'700', color:C.success }}>
                  {formatGs(vuelto)}
                </span>
              </div>
            )}
            {recibido && Number(recibido) < total && (
              <div style={{ marginTop:'10px', padding:'10px 14px',
                background:C.dangerBg, border:`1px solid ${C.dangerBorder}`,
                borderRadius:'10px', display:'flex', alignItems:'center', gap:'7px',
                fontSize:'13px', color:C.danger }}>
                <AlertCircle size={15} />
                Falta {formatGs(total - Number(recibido))} para completar el pago
              </div>
            )}
          </div>
        )}

        {/* Referencia para tarjeta/transferencia */}
        {(medio === 'debito' || medio === 'credito' || medio === 'transferencia') && (
          <div style={{ marginBottom:'12px' }}>
            <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
              color:C.textSec, marginBottom:'6px' }}>
              {medio === 'transferencia' ? 'Nro. de comprobante' : 'Nro. de autorización'}
              <span style={{ color:C.textMuted, fontWeight:'400' }}> (opcional)</span>
            </label>
            <input
              value={referencia}
              onChange={e => setReferencia(e.target.value)}
              placeholder="Ej: 123456"
              style={{ width:'100%', height:'44px', padding:'0 12px',
                border:`1px solid ${C.border}`, borderRadius:'10px',
                fontSize:'14px', color:C.text, background:C.bg, outline:'none' }}
              onFocus={e=>e.target.style.borderColor=C.gold}
              onBlur={e=>e.target.style.borderColor=C.border}
            />
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={{ padding:'14px 20px', borderTop:`1px solid ${C.border}`,
        background:C.bgSec, flexShrink:0, display:'flex', gap:'10px' }}>
        <button onClick={onCancelar}
          style={{ flex:1, height:device.isTouch?'50px':'44px',
            borderRadius:'10px', background:'transparent',
            border:`1px solid ${C.border}`, color:C.textSec,
            fontSize:'14px', cursor:'pointer' }}>
          Cancelar
        </button>
        <button
          onClick={() => mutation.mutate()}
          disabled={!puedeConfirmar || mutation.isPending}
          style={{ flex:2, height:device.isTouch?'50px':'44px',
            borderRadius:'10px',
            background: (!puedeConfirmar||mutation.isPending) ? C.bgTer : C.sidebar,
            border:`1.5px solid ${(!puedeConfirmar||mutation.isPending) ? C.border : C.gold}`,
            color: (!puedeConfirmar||mutation.isPending) ? C.textMuted : C.gold,
            fontSize:'14px', fontWeight:'500',
            cursor: (!puedeConfirmar||mutation.isPending) ? 'not-allowed':'pointer',
            display:'flex', alignItems:'center', justifyContent:'center', gap:'7px',
            transition:'all 120ms', WebkitTapHighlightColor:'transparent' }}>
          {mutation.isPending
            ? <><Loader2 size={16} style={{ animation:'spin 1s linear infinite' }}/> Procesando...</>
            : <><CheckCircle size={16}/> Confirmar pago</>}
        </button>
      </div>
      <style>{`
        @keyframes spin{to{transform:rotate(360deg)}}
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:.45}}
      `}</style>
    </div>
  )
}

// Bajo Solución Gratuita / e-Kuatia'í la factura legal se carga a mano en
// el portal e-Kuatia'í (ver docs/facturacion_electronica_manual_operativo.md)
// — no hay API, así que lo máximo que puede hacer el sistema es llevar a la
// cajera directo ahí en una pestaña nueva.
const URL_EKUATIAI = 'https://ekuatia.set.gov.py/ekuatiai/'

// Copia UN valor individual al portapapeles. Reemplaza el viejo "Copiar
// todo" en una sola plantilla: e-Kuatia'i pide cada dato en un campo
// separado del formulario (cliente, RUC, código/cantidad/precio de cada
// ítem, desglose de IVA...), así que copiar de a un campo evita que la
// cajera tenga que recortar a mano un bloque de texto para pegarlo en el
// lugar correcto — clic, pegar, siguiente campo.
//
// `mostrarValor` hace que el valor se vea escrito adentro del botón (para
// valores cortos como un código o un monto, donde sirve como referencia
// visual); sin eso queda como un ícono solo, para no romper el texto de al
// lado cuando el valor es largo (una razón social, por ejemplo).
function BotonCopiar({ valor, titulo, mostrarValor }) {
  const [copiado, setCopiado] = useState(false)

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(String(valor))
      setCopiado(true)
      setTimeout(() => setCopiado(false), 1500)
    } catch {
      toast.error('No se pudo copiar. Revisá los permisos del navegador.')
    }
  }

  const estilo = {
    display:'inline-flex', alignItems:'center', justifyContent:'center',
    gap: mostrarValor ? '4px' : 0,
    height:'20px', padding: mostrarValor ? '0 6px' : 0,
    width: mostrarValor ? 'auto' : '20px',
    marginLeft:'6px', borderRadius:'5px', cursor:'pointer',
    border:`1px solid ${copiado ? C.success : C.border}`,
    background: copiado ? C.successBg : C.bg,
    color: copiado ? C.success : C.textSec,
    fontSize:'10.5px', fontFamily: mostrarValor ? 'monospace' : 'inherit',
  }

  return (
    <button onClick={copiar} title={titulo || 'Copiar'} style={estilo}>
      {copiado ? <ClipboardCheck size={11}/> : <Copy size={11}/>}
      {mostrarValor && valor}
    </button>
  )
}

// ─── Ayudante de carga: datos listos para copiar al portal DNIT ───────────────
// Solo tiene sentido cuando la factura NO tiene timbrado real (o sea, hoy
// siempre): bajo Solución Gratuita / e-Kuatia'i la factura legal la emite
// el portal, cargada a mano — esto le ahorra a la cajera transcribir del
// papel. No se imprime junto al comprobante: es una herramienta interna.
function AyudanteCargaPortal({ ticket }) {
  return (
    <div style={{ marginTop:'16px', padding:'14px', background:C.bgSec,
      border:`1px solid ${C.border}`, borderRadius:'10px' }}>
      <p style={{ fontSize:'12.5px', fontWeight:'600', color:C.text, marginBottom:'10px' }}>
        Datos para cargar en e-Kuatia'í (portal DNIT)
      </p>

      <div style={{ fontSize:'11.5px', color:C.textSec, lineHeight:1.8 }}>
        <p>
          <b>Cliente:</b> {ticket.cliente_razon_social || ticket.cliente}
          <BotonCopiar valor={ticket.cliente_razon_social || ticket.cliente} titulo="Copiar cliente" />
        </p>
        <p>
          <b>RUC/CI:</b> {ticket.cliente_ruc || 'Sin especificar'}
          {ticket.cliente_ruc && <BotonCopiar valor={ticket.cliente_ruc} titulo="Copiar RUC/CI" />}
        </p>
        <p>
          <b>Condición de venta:</b> {ticket.condicion_venta}
          <BotonCopiar valor={ticket.condicion_venta} titulo="Copiar condición de venta" />
        </p>

        <p style={{ marginTop:'8px' }}><b>Ítems:</b></p>
        {ticket.items.map((it, i) => (
          <div key={i} style={{ paddingLeft:'8px', marginBottom:'8px' }}>
            <p>
              {it.cantidad} × {it.descripcion} — {formatGs(it.subtotal)} (IVA {etiquetaTasaIva(it.tasa_iva)})
            </p>
            <p style={{ display:'flex', alignItems:'center', flexWrap:'wrap',
              gap:'4px', marginTop:'3px' }}>
              <span style={{ color:C.textMuted }}>SKU:</span>
              {it.codigo
                ? <BotonCopiar valor={it.codigo} titulo="Copiar código interno (SKU)" mostrarValor />
                : <span style={{ color:C.textMuted, fontStyle:'italic' }}>sin código</span>}
              <span style={{ color:C.textMuted, marginLeft:'6px' }}>Cant:</span>
              <BotonCopiar valor={it.cantidad} titulo="Copiar cantidad" mostrarValor />
              <span style={{ color:C.textMuted, marginLeft:'6px' }}>P.Unit:</span>
              <BotonCopiar valor={it.precio_unit} titulo="Copiar precio unitario" mostrarValor />
            </p>
          </div>
        ))}

        <p style={{ marginTop:'8px' }}>
          <b>Base 10%:</b> {formatGs(ticket.base_gravada_10)}
          <BotonCopiar valor={ticket.base_gravada_10} titulo="Copiar base gravada 10%" />
          <span style={{ marginLeft:'10px' }}><b>IVA 10%:</b> {formatGs(ticket.iva_10)}</span>
          <BotonCopiar valor={ticket.iva_10} titulo="Copiar IVA 10%" />
        </p>
        <p>
          <b>Base 5%:</b> {formatGs(ticket.base_gravada_5)}
          <BotonCopiar valor={ticket.base_gravada_5} titulo="Copiar base gravada 5%" />
          <span style={{ marginLeft:'10px' }}><b>IVA 5%:</b> {formatGs(ticket.iva_5)}</span>
          <BotonCopiar valor={ticket.iva_5} titulo="Copiar IVA 5%" />
        </p>
        <p>
          <b>Exento:</b> {formatGs(ticket.exento)}
          <BotonCopiar valor={ticket.exento} titulo="Copiar exento" />
        </p>
        <p>
          <b>Total:</b> {formatGs(ticket.total)}
          <BotonCopiar valor={ticket.total} titulo="Copiar total" />
          <span style={{ marginLeft:'10px' }}><b>Medio de pago:</b> {ticket.medio_pago}</span>
        </p>
      </div>

      <a href={URL_EKUATIAI} target="_blank" rel="noopener noreferrer"
        style={{ marginTop:'12px', height:'38px', borderRadius:'8px',
          background:C.gold, border:`1px solid ${C.gold}`,
          color:'#fff', fontSize:'12.5px', fontWeight:'500',
          textDecoration:'none', cursor:'pointer',
          display:'flex', alignItems:'center', justifyContent:'center', gap:'7px' }}>
        <ExternalLink size={14}/> Generar factura electrónica
      </a>
    </div>
  )
}

// ─── Ticket térmico (imprimible) ──────────────────────────────────────────────
function Ticket({ datos, onNuevo, onImprimir }) {
  const ticketRef = useRef()

  const imprimir = () => {
    onImprimir?.()
    window.print()
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%',
      alignItems:'center', justifyContent:'center', padding:'20px',
      background:C.bgSec }}>
      <div style={{ width:'100%', maxWidth:'360px' }}>
        {/* Éxito */}
        <div style={{ textAlign:'center', marginBottom:'20px' }}>
          <div style={{ width:'56px', height:'56px', borderRadius:'50%',
            background:C.successBg, border:`2px solid ${C.success}`,
            display:'flex', alignItems:'center', justifyContent:'center',
            margin:'0 auto 12px' }}>
            <CheckCircle size={28} style={{ color:C.success }} />
          </div>
          <h2 style={{ fontSize:'20px', fontWeight:'500',
            fontFamily:'var(--font-display)', color:C.text }}>
            Pago confirmado
          </h2>
          <p style={{ fontSize:'13px', color:C.textMuted, marginTop:'4px' }}>
            {datos.tipo_comprobante === 'factura' ? 'Factura' : 'Ticket'} #{datos.ticket.numero_ticket}
          </p>
        </div>

        {/* Comprobante simulado (se imprime con window.print). Sin color: la
            impresora térmica de la tienda es blanco y negro, así que ningún
            sombreado/color acá se refleja en el papel — solo agrega ruido
            en pantalla. */}
        <div ref={ticketRef} className="ticket-imprimible" style={{
          background:C.bg,
          border: `1px solid ${C.border}`,
          borderRadius:'12px', padding:'20px',
          fontFamily:'monospace', fontSize:'12px',
          marginBottom:'16px',
        }}>
          {/* Cabecera — distinta para factura y ticket */}
          {datos.tipo_comprobante === 'factura' ? (
            <div style={{ textAlign:'center', borderBottom:`2px solid ${C.text}`,
              paddingBottom:'10px', marginBottom:'10px' }}>
              <p style={{ fontSize:'16px', fontWeight:'700', color:C.text }}>
                {datos.ticket.negocio}
              </p>
              {datos.ticket.ruc_negocio && (
                <p style={{ color:C.textMuted, fontSize:'11px' }}>RUC: {datos.ticket.ruc_negocio}</p>
              )}
              {datos.ticket.direccion && (
                <p style={{ color:C.textMuted, fontSize:'11px' }}>{datos.ticket.direccion}</p>
              )}
              <p style={{ fontSize:'15px', fontWeight:'700', color:C.text,
                letterSpacing:'0.08em', marginTop:'8px' }}>
                {datos.ticket.timbrado ? 'FACTURA' : 'COMPROBANTE DE VENTA'}
              </p>
              {datos.ticket.timbrado && (
                <p style={{ fontSize:'9px', color:C.textMuted }}>COMPROBANTE LEGAL</p>
              )}
              {datos.ticket.timbrado && (
                <p style={{ color:C.textMuted, fontSize:'10px', marginTop:'4px' }}>
                  Timbrado {datos.ticket.timbrado} · Vto {datos.ticket.timbrado_vto}
                </p>
              )}
              <p style={{ color:C.textMuted, fontSize:'11px', marginTop:'2px' }}>{datos.ticket.fecha}</p>
              <p style={{ color:C.textMuted, fontSize:'11px' }}>
                {datos.ticket.timbrado ? 'Factura Nro:' : 'Comprobante Nro:'} {datos.ticket.numero_ticket}
              </p>
            </div>
          ) : (
            <div style={{ textAlign:'center', borderBottom:`1px dashed ${C.border}`,
              paddingBottom:'10px', marginBottom:'10px' }}>
              <p style={{ fontSize:'15px', fontWeight:'700', color:C.text }}>
                {datos.ticket.negocio}
              </p>
              <p style={{ fontSize:'11px', fontWeight:'600', color:C.textSec,
                letterSpacing:'0.05em', marginTop:'3px' }}>
                · TICKET DE VENTA ·
              </p>
              <p style={{ fontSize:'9px', color:C.textMuted }}>Comprobante no fiscal</p>
              <p style={{ color:C.textMuted, fontSize:'11px', marginTop:'3px' }}>{datos.ticket.fecha}</p>
              <p style={{ color:C.textMuted, fontSize:'11px' }}>
                Ticket: {datos.ticket.numero_ticket}
              </p>
            </div>
          )}

          {/* Cliente */}
          <div style={{ marginBottom:'10px' }}>
            {datos.tipo_comprobante === 'factura' && (
              <p style={{ fontWeight:'700', fontSize:'10px', color:C.textSec,
                marginBottom:'3px', letterSpacing:'0.04em' }}>DATOS DEL CLIENTE</p>
            )}
            <p><span style={{ color:C.textMuted }}>Cliente: </span>
              <span style={{ color:C.text }}>
                {datos.ticket.cliente_razon_social || datos.ticket.cliente}
              </span></p>
            {datos.tipo_comprobante === 'factura' && (
              <p><span style={{ color:C.textMuted }}>RUC/CI:  </span>
                <span style={{ color:C.text }}>{datos.ticket.cliente_ruc}</span></p>
            )}
            <p><span style={{ color:C.textMuted }}>Pedido:  </span>
              <span style={{ color:C.text }}>{datos.ticket.pedido_numero}</span></p>
            <p><span style={{ color:C.textMuted }}>Cajero:  </span>
              <span style={{ color:C.text }}>{datos.ticket.cajero}</span></p>
          </div>

          {/* Línea separadora */}
          <p style={{ color:C.border, letterSpacing:'-1px' }}>
            {'─'.repeat(36)}
          </p>

          {/* Ítems */}
          <div style={{ margin:'8px 0' }}>
            {datos.ticket.items.map((item, i) => (
              <div key={i} style={{ marginBottom:'6px' }}>
                <p style={{ color:C.text, fontWeight:'500' }}>{item.descripcion}</p>
                <div style={{ display:'flex', justifyContent:'space-between',
                  color:C.textSec }}>
                  <span>{item.cantidad.toFixed(2)} × {formatGs(item.precio_unit)}</span>
                  <span style={{ fontWeight:'600', color:C.text }}>
                    {formatGs(item.subtotal)}
                  </span>
                </div>
              </div>
            ))}
          </div>

          <p style={{ color:C.border, letterSpacing:'-1px' }}>
            {'─'.repeat(36)}
          </p>

          {/* Totales */}
          <div style={{ margin:'8px 0' }}>
            {datos.ticket.descuento > 0 && (
              <div style={{ display:'flex', justifyContent:'space-between',
                color:C.textSec }}>
                <span>Descuento</span>
                <span>− {formatGs(datos.ticket.descuento)}</span>
              </div>
            )}
            <div style={{ display:'flex', justifyContent:'space-between',
              fontWeight:'700', fontSize:'14px', color:C.text, marginTop:'4px' }}>
              <span>TOTAL</span>
              <span>{formatGs(datos.ticket.total)}</span>
            </div>
            <div style={{ display:'flex', justifyContent:'space-between',
              color:C.textSec, marginTop:'4px' }}>
              <span>{datos.ticket.medio_pago}</span>
              {datos.ticket.monto_recibido &&
                <span>{formatGs(datos.ticket.monto_recibido)}</span>}
            </div>
            {datos.ticket.vuelto > 0 && (
              <div style={{ display:'flex', justifyContent:'space-between',
                color:C.success, fontWeight:'600' }}>
                <span>Vuelto</span>
                <span>{formatGs(datos.ticket.vuelto)}</span>
              </div>
            )}
          </div>

          {/* Pie */}
          <p style={{ color:C.border, letterSpacing:'-1px' }}>
            {'─'.repeat(36)}
          </p>
          <p style={{ textAlign:'center', color:C.textMuted, marginTop:'8px' }}>
            {datos.ticket.pie}
          </p>
        </div>

        {/* Ayudante de carga al portal — solo cuando la factura no tiene
            timbrado real, es decir, siempre bajo Solución Gratuita */}
        {datos.tipo_comprobante === 'factura' && !datos.ticket.timbrado && (
          <AyudanteCargaPortal ticket={datos.ticket} />
        )}

        {/* Acciones */}
        <div style={{ display:'flex', gap:'10px' }}>
          <button onClick={imprimir}
            style={{ flex:1, height:'46px', borderRadius:'10px',
              background:C.bgSec, border:`1px solid ${C.border}`,
              color: datos.impresion?.ok === false ? C.danger : C.textSec,
              fontSize:'14px', cursor:'pointer',
              display:'flex', alignItems:'center', justifyContent:'center', gap:'7px' }}>
            <Printer size={16} />
            {datos.impresion?.ok === false ? 'Reintentar' : 'Reimprimir'}
          </button>
          <button onClick={onNuevo}
            style={{ flex:2, height:'46px', borderRadius:'10px',
              background:C.sidebar, border:`1.5px solid ${C.gold}`,
              color:C.gold, fontSize:'14px', fontWeight:'500', cursor:'pointer',
              display:'flex', alignItems:'center', justifyContent:'center', gap:'7px' }}>
            <CheckCircle size={16} /> Cobrar siguiente
          </button>
        </div>


        {/* Alerta si la impresión falló */}
        {datos.impresion?.ok === false && (
          <div style={{ marginTop:'10px', padding:'10px 14px',
            background:C.warningBg, border:`1px solid ${C.warningBorder}`,
            borderRadius:'8px', fontSize:'12.5px', color:C.warning,
            display:'flex', alignItems:'flex-start', gap:'7px' }}>
            <AlertCircle size={15} style={{ flexShrink:0, marginTop:'1px' }} />
            <div>
              <p style={{ fontWeight:'500', marginBottom:'2px' }}>
                La impresora no pudo imprimir automáticamente
              </p>
              <p style={{ color:C.text }}>{datos.impresion?.error}</p>
              <p style={{ marginTop:'4px' }}>
                Verificar que la impresora esté conectada y encendida,
                luego usar "Reimprimir" arriba.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Panel de cierre de caja ──────────────────────────────────────────────────
function PanelCierre({ sesion, pagos, onConfirmar, onCancelar, isLoading }) {
  const [montoFinal, setMontoFinal] = useState('')
  const [observaciones, setObservaciones] = useState('')

  const totalVentas = pagos.reduce((s, p) => s + Number(p.monto), 0)
  const resumenMedios = pagos.reduce((acc, p) => {
    acc[p.medio_display] = (acc[p.medio_display] || 0) + Number(p.monto)
    return acc
  }, {})

  return (
    <div style={{ maxWidth:'480px', margin:'0 auto', padding:'20px' }}>
      <div style={{ textAlign:'center', marginBottom:'24px' }}>
        <div style={{ width:'52px', height:'52px', borderRadius:'14px',
          background:C.sidebar, border:`1px solid ${C.gold}`,
          display:'flex', alignItems:'center', justifyContent:'center',
          margin:'0 auto 12px' }}>
          <Lock size={24} style={{ color:C.gold }} />
        </div>
        <h2 style={{ fontSize:'20px', fontWeight:'500',
          fontFamily:'var(--font-display)', color:C.text }}>
          Cierre de caja
        </h2>
        <p style={{ fontSize:'13px', color:C.textMuted, marginTop:'4px' }}>
          {new Date().toLocaleDateString('es-PY', {
            weekday:'long', day:'numeric', month:'long',
          })}
        </p>
      </div>

      {/* Resumen del día */}
      <div style={{ background:C.bg, border:`1px solid ${C.border}`,
        borderRadius:'14px', overflow:'hidden', marginBottom:'16px' }}>
        <div style={{ padding:'14px 18px', borderBottom:`1px solid ${C.border}`,
          background:C.bgSec }}>
          <p style={{ fontSize:'11px', fontWeight:'500', color:C.textMuted,
            textTransform:'uppercase', letterSpacing:'0.06em' }}>
            Resumen del turno
          </p>
        </div>
        <div style={{ padding:'14px 18px' }}>
          <div style={{ display:'flex', justifyContent:'space-between', marginBottom:'10px' }}>
            <span style={{ fontSize:'13px', color:C.textSec }}>Apertura con</span>
            <span style={{ fontSize:'14px', fontWeight:'500', color:C.text }}>
              {formatGs(sesion?.monto_apertura || 0)}
            </span>
          </div>
          <div style={{ display:'flex', justifyContent:'space-between', marginBottom:'10px' }}>
            <span style={{ fontSize:'13px', color:C.textSec }}>Cobros realizados</span>
            <span style={{ fontSize:'14px', color:C.textSec }}>
              {pagos.length} pago{pagos.length!==1?'s':''}
            </span>
          </div>
          {Object.entries(resumenMedios).map(([medio, monto]) => (
            <div key={medio} style={{ display:'flex', justifyContent:'space-between',
              marginBottom:'6px', paddingLeft:'12px' }}>
              <span style={{ fontSize:'12px', color:C.textMuted }}>· {medio}</span>
              <span style={{ fontSize:'13px', color:C.textSec }}>{formatGs(monto)}</span>
            </div>
          ))}
          <div style={{ display:'flex', justifyContent:'space-between',
            paddingTop:'10px', borderTop:`2px solid ${C.border}`, marginTop:'6px' }}>
            <span style={{ fontSize:'14px', fontWeight:'600', color:C.text }}>
              Total cobrado
            </span>
            <span style={{ fontSize:'18px', fontWeight:'700', color:C.goldDark }}>
              {formatGs(totalVentas)}
            </span>
          </div>
        </div>
      </div>

      {/* Monto en caja al cierre */}
      <div style={{ marginBottom:'14px' }}>
        <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
          color:C.textSec, marginBottom:'6px' }}>
          Monto en caja al cierre (Gs.)
        </label>
        <input
          type="number" min="0" step="1000"
          value={montoFinal}
          onChange={e => setMontoFinal(e.target.value)}
          placeholder={String(Number(sesion?.monto_apertura||0) + totalVentas)}
          style={{ width:'100%', height:'46px', padding:'0 14px', textAlign:'right',
            border:`1px solid ${C.border}`, borderRadius:'10px',
            fontSize:'16px', color:C.text, background:C.bg, outline:'none',
            fontWeight:'600' }}
          onFocus={e=>e.target.style.borderColor=C.gold}
          onBlur={e=>e.target.style.borderColor=C.border}
        />
      </div>

      <div style={{ marginBottom:'20px' }}>
        <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
          color:C.textSec, marginBottom:'6px' }}>
          Observaciones (opcional)
        </label>
        <textarea
          value={observaciones}
          onChange={e => setObservaciones(e.target.value)}
          placeholder="Novedades del turno, diferencias, etc."
          rows={3}
          style={{ width:'100%', padding:'10px 12px',
            border:`1px solid ${C.border}`, borderRadius:'10px',
            fontSize:'13.5px', color:C.text, background:C.bg,
            outline:'none', resize:'vertical', fontFamily:'inherit' }}
          onFocus={e=>e.target.style.borderColor=C.gold}
          onBlur={e=>e.target.style.borderColor=C.border}
        />
      </div>

      <div style={{ display:'flex', gap:'10px' }}>
        <button onClick={onCancelar}
          style={{ flex:1, height:'46px', borderRadius:'10px',
            background:'transparent', border:`1px solid ${C.border}`,
            color:C.textSec, fontSize:'14px', cursor:'pointer' }}>
          Volver
        </button>
        <button
          onClick={() => onConfirmar({ monto_cierre: montoFinal || undefined, observaciones_cierre: observaciones })}
          disabled={isLoading}
          style={{ flex:2, height:'46px', borderRadius:'10px',
            background:C.sidebar, border:`1.5px solid ${C.gold}`,
            color:C.gold, fontSize:'14px', fontWeight:'500',
            cursor:'pointer', display:'flex', alignItems:'center',
            justifyContent:'center', gap:'7px' }}>
          {isLoading
            ? <><Loader2 size={16} style={{ animation:'spin 1s linear infinite' }}/> Cerrando...</>
            : <><Lock size={16}/> Cerrar caja</>}
        </button>
      </div>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  )
}

// ─── Página principal ─────────────────────────────────────────────────────────
export default function CajaPage() {
  const queryClient = useQueryClient()
  const device = useDevice()

  const [pedidoActivo,  setPedidoActivo]  = useState(null)
  const [ticketDatos,   setTicketDatos]   = useState(null)
  const [mostraCierre,  setMostraCierre]  = useState(false)

  // Estado de la impresora
  const { data: impresora } = useQuery({
    queryKey: ['estado-impresora'],
    queryFn:  () => cajaApi.estadoImpresora().then(r => r.data),
    staleTime: 60_000,
    retry: false,
  })

  // Sesión de caja
  const { data: sesionData, isLoading: sesionLoading } = useQuery({
    queryKey: ['sesion-caja'],
    queryFn: () => cajaApi.sesionActual().then(r => r.data),
    staleTime: 30_000,
  })

  const sesion     = sesionData?.sesion
  const tieneSesion = sesionData?.tiene_sesion

  // Pedidos listos para cobrar
  const { data: pedidosData, refetch: refetchPedidos } = useQuery({
    queryKey: ['pedidos-caja'],
    queryFn:  () => ventasApi.pedidos({ estado:'listo' }).then(r => r.data),
    enabled:  Boolean(tieneSesion),
    staleTime: 10_000,
    refetchInterval: 30_000,
  })
  const pedidosListos = pedidosData?.results || []

  // Pagos de la sesión actual
  const { data: pagosData } = useQuery({
    queryKey: ['pagos-sesion', sesion?.id],
    queryFn:  () => cajaApi.listaPagos({ sesion: sesion.id }).then(r => r.data),
    enabled:  Boolean(sesion?.id),
    staleTime: 10_000,
  })
  const pagos = pagosData?.results || []

  // WebSocket — nuevos pedidos listos
  usePedidoSocket({
    rol: 'cajero',
    onMensaje: (msg) => {
      if (msg.tipo === 'pedido_listo') {
        refetchPedidos()
        toast(`Pedido ${msg.pedido?.numero} listo para cobrar`, { icon:'💳', duration:5000 })
      }
    },
  })

  // Mutaciones
  const abrirCajaMut = useMutation({
    mutationFn: (monto) => cajaApi.abrirCaja({ monto_apertura: monto }).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sesion-caja'] })
      toast.success('Caja abierta')
    },
    onError: (err) => toast.error(err.response?.data?.error || 'Error al abrir caja'),
  })

  const cerrarCajaMut = useMutation({
    mutationFn: (data) => cajaApi.cerrarCaja(sesion.id, data).then(r => r.data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['sesion-caja'] })
      toast.success(`Caja cerrada. Total: ${formatGs(data.total_ventas)}`)
      setMostraCierre(false)
    },
    onError: (err) => toast.error(err.response?.data?.error || 'Error al cerrar caja'),
  })

  // ── Sin sesión ──────────────────────────────────────────────────────────────
  if (sesionLoading) {
    return (
      <Layout pageTitle="Caja" breadcrumbs={['Caja']}>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'center',
          minHeight:'50vh', color:C.textMuted }}>
          <Loader2 size={28} style={{ animation:'spin 1s linear infinite' }} />
          <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
        </div>
      </Layout>
    )
  }

  if (!tieneSesion) {
    return (
      <Layout pageTitle="Caja" breadcrumbs={['Caja']}>
        <PantallaSinSesion
          onAbrir={(monto) => abrirCajaMut.mutate(monto)}
          isLoading={abrirCajaMut.isPending}
        />
      </Layout>
    )
  }

  // ── Con sesión activa ───────────────────────────────────────────────────────
  return (
    <Layout pageTitle="Caja" breadcrumbs={['Caja']} fullWidth noPadding>
      <div style={{ display:'flex', height:'100%',
        overflow:'hidden', flexDirection: device.width < 768 ? 'column' : 'row' }}>

        {/* ── Columna izquierda: lista de pedidos + resumen ── */}
        <div style={{
          width: device.width < 768 ? '100%' : '320px',
          flexShrink:0,
          borderRight:`1px solid ${C.border}`,
          display:'flex', flexDirection:'column',
          background:C.bgSec,
          height: device.width < 768 ? 'auto' : '100%',
          overflowY: device.width < 768 ? 'visible' : 'auto',
        }}>
          {/* Header sesión */}
          <div style={{ padding:'16px', borderBottom:`1px solid ${C.border}`,
            background:C.bg, flexShrink:0 }}>
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
              marginBottom:'4px' }}>
              <div style={{ display:'flex', alignItems:'center', gap:'7px' }}>
                <div style={{ width:'8px', height:'8px', borderRadius:'50%',
                  background:C.success, boxShadow:`0 0 0 2px ${C.successBg}` }} />
                <p style={{ fontSize:'13px', fontWeight:'500', color:C.text }}>
                  Sesión activa
                </p>
              </div>
              <div style={{ display:'flex', alignItems:'center', gap:'8px' }}>
                {/* Indicador de impresora */}
                <div title={impresora?.disponible ? 'Impresora lista' : (impresora?.error || 'Sin impresora')}
                  style={{ display:'flex', alignItems:'center', gap:'3px',
                    fontSize:'11px', color: impresora?.disponible ? C.success : C.textMuted }}>
                  {impresora?.disponible
                    ? <Printer size={13} />
                    : <Printer size={13} style={{ opacity:0.4 }} />}
                </div>
                <button onClick={() => setMostraCierre(true)}
                  style={{ display:'flex', alignItems:'center', gap:'5px',
                    padding:'5px 10px', background:'transparent',
                    border:`1px solid ${C.border}`, borderRadius:'7px',
                    color:C.textSec, fontSize:'12px', cursor:'pointer' }}>
                  <Lock size={12} /> Cerrar caja
                </button>
              </div>
            </div>
            <p style={{ fontSize:'11px', color:C.textMuted }}>
              Desde {formatFecha(sesion?.fecha_apertura)}
            </p>
            <p style={{ fontSize:'12px', color:C.success, marginTop:'3px', fontWeight:'500' }}>
              {pagos.length} cobro{pagos.length!==1?'s':''} · {formatGs(pagos.reduce((s,p)=>s+Number(p.monto),0))}
            </p>
          </div>

          {/* Lista pedidos */}
          <div style={{ flex:1, overflowY:'auto', padding:'12px',
            WebkitOverflowScrolling:'touch' }}>
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
              marginBottom:'10px' }}>
              <p style={{ fontSize:'11px', fontWeight:'500', color:C.textMuted,
                textTransform:'uppercase', letterSpacing:'0.06em' }}>
                Para cobrar ({pedidosListos.length})
              </p>
              <button onClick={() => refetchPedidos()}
                style={{ background:'transparent', border:'none', cursor:'pointer',
                  color:C.textMuted, padding:'3px', display:'flex',
                  alignItems:'center' }}>
                <RefreshCw size={13} />
              </button>
            </div>

            {pedidosListos.length === 0 ? (
              <div style={{ textAlign:'center', padding:'40px 16px', color:C.textMuted }}>
                <Clock size={32} style={{ margin:'0 auto 10px', opacity:0.2 }} />
                <p style={{ fontSize:'13.5px', fontWeight:'500', color:C.textSec }}>
                  Sin pedidos pendientes
                </p>
                <p style={{ fontSize:'12px', marginTop:'3px' }}>
                  Los pedidos marcados como "Listo" aparecerán acá
                </p>
              </div>
            ) : (
              pedidosListos.map(p => (
                <PedidoCard
                  key={p.id}
                  pedido={p}
                  activo={pedidoActivo?.id === p.id}
                  onClick={(ped) => {
                    setPedidoActivo(ped)
                    setTicketDatos(null)
                  }}
                />
              ))
            )}

            {/* Historial de pagos del día */}
            {pagos.length > 0 && (
              <div style={{ marginTop:'16px' }}>
                <p style={{ fontSize:'11px', fontWeight:'500', color:C.textMuted,
                  textTransform:'uppercase', letterSpacing:'0.06em',
                  marginBottom:'8px' }}>
                  Cobros del turno
                </p>
                {pagos.map(p => (
                  <div key={p.id} style={{ display:'flex', justifyContent:'space-between',
                    alignItems:'center', padding:'8px 10px', marginBottom:'4px',
                    background:C.bg, borderRadius:'8px', border:`1px solid ${C.border}` }}>
                    <div>
                      <p style={{ fontSize:'12px', fontWeight:'500', color:C.text,
                        fontFamily:'monospace' }}>
                        {p.numero_ticket}
                      </p>
                      <p style={{ fontSize:'11px', color:C.textMuted }}>
                        {p.medio_display} · {p.pedido_cliente || '—'}
                      </p>
                    </div>
                    <p style={{ fontSize:'13px', fontWeight:'600', color:C.goldDark }}>
                      {formatGs(p.monto)}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── Columna derecha: cobro activo / ticket ── */}
        <div style={{ flex:1, display:'flex', flexDirection:'column',
          overflow:'hidden', background:C.bg }}>

          {/* Ticket post-pago */}
          {ticketDatos && (
            <Ticket
              datos={ticketDatos}
              onNuevo={() => { setTicketDatos(null); setPedidoActivo(null) }}
              onImprimir={() => {}}
            />
          )}

          {/* Cobro de pedido */}
          {pedidoActivo && !ticketDatos && (
            <PanelCobro
              pedido={pedidoActivo}
              sesion={sesion}
              onPagado={(data) => {
                setTicketDatos(data)
                refetchPedidos()
                queryClient.invalidateQueries({ queryKey: ['pagos-sesion', sesion?.id] })
              }}
              onCancelar={() => setPedidoActivo(null)}
            />
          )}

          {/* Estado vacío */}
          {!pedidoActivo && !ticketDatos && (
            <div style={{ display:'flex', flexDirection:'column', alignItems:'center',
              justifyContent:'center', height:'100%', color:C.textMuted, padding:'20px' }}>
              <Receipt size={48} style={{ margin:'0 auto 14px', opacity:0.15 }} />
              <p style={{ fontSize:'17px', fontWeight:'500', color:C.textSec,
                fontFamily:'var(--font-display)' }}>
                Seleccioná un pedido
              </p>
              <p style={{ fontSize:'13.5px', marginTop:'5px', textAlign:'center' }}>
                Los pedidos en estado "Listo para cobrar" <br/>aparecen en el panel izquierdo
              </p>
            </div>
          )}
        </div>
      </div>

      {/* ── Modal de cierre de caja ── */}
      {mostraCierre && (
        <>
          <div onClick={() => setMostraCierre(false)}
            style={{ position:'fixed', inset:0, zIndex:200,
              background:'rgba(26,23,20,0.45)', backdropFilter:'blur(3px)' }} />
          <div style={{ position:'fixed', top:0, right:0, bottom:0, zIndex:201,
            width:'min(480px,95vw)', background:C.bg,
            borderLeft:`1px solid ${C.border}`,
            boxShadow:'-8px 0 32px rgba(0,0,0,0.14)',
            overflowY:'auto',
            animation:'slideIn 200ms ease' }}>
            <PanelCierre
              sesion={sesion}
              pagos={pagos}
              onConfirmar={(data) => cerrarCajaMut.mutate(data)}
              onCancelar={() => setMostraCierre(false)}
              isLoading={cerrarCajaMut.isPending}
            />
          </div>
        </>
      )}

      <style>{`
        @keyframes slideIn { from{transform:translateX(100%)} to{transform:translateX(0)} }
        @keyframes spin { to{transform:rotate(360deg)} }
        @media print {
          body > *:not(.ticket-imprimible) { display: none !important; }
          .ticket-imprimible {
            font-family: 'Courier New', monospace !important;
            font-size: 12pt !important;
            width: 80mm !important;
            margin: 0 !important;
            padding: 4mm !important;
          }
        }
      `}</style>
    </Layout>
  )
}
