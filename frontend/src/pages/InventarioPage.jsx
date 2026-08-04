/**
 * InventarioPage
 * Vista completa de stock con:
 * - Resumen de alertas (crítico / sin stock)
 * - Tabla filtrable por estado, categoría, búsqueda
 * - Panel de ajuste manual de stock
 * - Historial de movimientos por variante
 * - WebSocket para actualizar en tiempo real cuando hay ventas
 */
import { useState, useCallback, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle, XCircle, CheckCircle, Package,
  Search, SlidersHorizontal, RefreshCw, Plus,
  Minus, RotateCcw, History, X, ChevronDown,
  Warehouse, TrendingDown, TrendingUp, ArrowUpDown,
} from 'lucide-react'
import Layout from '../components/layout/Layout'
import { inventarioApi, productosApi } from '../services/api'
import { usePedidoSocket } from '../hooks/usePedidoSocket'
import toast from 'react-hot-toast'

const C = {
  sidebar:'#453941', sidebarHov:'#362F31',
  gold:'#B99C74', goldDark:'#8a7355', goldMuted:'rgba(185,156,116,0.10)',
  border:'#e8e4df', bg:'#ffffff', bgSec:'#fafaf9', bgTer:'#f5f4f2',
  text:'#1a1714', textSec:'#6b6560', textMuted:'#9e9892',
  success:'#3d7a5a', successBg:'#edf7f1', successBorder:'#b8deca',
  warning:'#8a6a1a', warningBg:'#fef9ee', warningBorder:'#f0d98a',
  danger:'#9a3030', dangerBg:'#fef0f0', dangerBorder:'#f0b8b8',
  info:'#2a5c8a', infoBg:'#eef4fb',
}

function formatGs(v) { return `Gs. ${Number(v||0).toLocaleString('es-PY')}` }
function formatFecha(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('es-PY', {
    day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit',
  })
}

function useDebounce(v, d=380) {
  const [dv, setDv] = useState(v)
  useEffect(() => {
    const t = setTimeout(() => setDv(v), d)
    return () => clearTimeout(t)
  }, [v, d])
  return dv
}

// ─── Badge de estado ──────────────────────────────────────────────────────────
function EstadoBadge({ estado, disponible }) {
  const cfg = {
    disponible: { bg:C.successBg, color:C.success, border:C.successBorder, icon:<CheckCircle size={11}/>, label:'OK' },
    critico:    { bg:C.warningBg, color:C.warning, border:C.warningBorder, icon:<AlertCircle size={11}/>, label:'Bajo' },
    sin_stock:  { bg:C.dangerBg,  color:C.danger,  border:C.dangerBorder,  icon:<XCircle    size={11}/>, label:'Sin stock' },
  }
  const s = cfg[estado] || cfg.sin_stock
  return (
    <span style={{ display:'inline-flex', alignItems:'center', gap:'3px',
      padding:'2px 8px', borderRadius:'20px',
      background:s.bg, color:s.color, border:`1px solid ${s.border}`,
      fontSize:'11px', fontWeight:'500', whiteSpace:'nowrap' }}>
      {s.icon} {s.label}
    </span>
  )
}

// ─── Tipo de movimiento ───────────────────────────────────────────────────────
const TIPO_CFG = {
  entrada:    { color:C.success, label:'Entrada',    icono:<TrendingUp size={13}/> },
  salida:     { color:C.danger,  label:'Salida',     icono:<TrendingDown size={13}/> },
  ajuste:     { color:C.info,    label:'Ajuste',     icono:<ArrowUpDown size={13}/> },
  reserva:    { color:C.warning, label:'Reserva',    icono:<Package size={13}/> },
  liberacion: { color:C.textSec, label:'Liberación', icono:<RotateCcw size={13}/> },
  devolucion: { color:C.success, label:'Devolución', icono:<RotateCcw size={13}/> },
}

// ─── Panel de ajuste de stock ─────────────────────────────────────────────────
function PanelAjuste({ item, onCerrar }) {
  const queryClient = useQueryClient()
  const [tipo,   setTipo]   = useState('entrada')
  const [cantidad, setCantidad] = useState('')
  const [obs,    setObs]    = useState('')
  const [unidadIngreso, setUnidadIngreso] = useState('venta')

  // ¿Este producto admite carga en cajas?
  const admiteCajas = item.vende_por_m2 && item.m2_por_caja > 0
  // Vista previa de la conversión cuando se carga en cajas
  const previewM2 = (admiteCajas && unidadIngreso === 'caja' && cantidad)
    ? (Number(cantidad) * Number(item.m2_por_caja)).toFixed(2)
    : null

  const mutation = useMutation({
    mutationFn: () => inventarioApi.ajustar({
      variante_id:    item.variante_id,
      tipo,
      cantidad:       Number(cantidad),
      unidad_ingreso: unidadIngreso,
      observaciones:  obs,
    }).then(r => r.data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['stock'] })
      toast.success(`Stock actualizado: ${data.disponible} disponible`)
      onCerrar()
    },
    onError: (err) => toast.error(err.response?.data?.error || 'Error al ajustar stock'),
  })

  const TIPOS_AJU = [
    { key:'entrada',    label:'Entrada de mercadería' },
    { key:'salida',     label:'Salida manual'          },
    { key:'ajuste',     label:'Ajuste a cantidad exacta' },
    { key:'devolucion', label:'Devolución de cliente'  },
  ]

  return (
    <>
      <div onClick={onCerrar} style={{ position:'fixed', inset:0, zIndex:200,
        background:'rgba(26,23,20,0.4)', backdropFilter:'blur(2px)' }} />
      <div style={{ position:'fixed', top:'50%', left:'50%', zIndex:201,
        transform:'translate(-50%,-50%)',
        width:'min(420px,92vw)', background:C.bg,
        border:`1px solid ${C.border}`, borderRadius:'16px',
        boxShadow:'0 20px 50px rgba(0,0,0,0.15)',
        padding:'24px' }}>

        <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between',
          marginBottom:'18px' }}>
          <div>
            <h3 style={{ fontSize:'16px', fontWeight:'500', color:C.text }}>
              Ajustar stock
            </h3>
            <p style={{ fontSize:'12px', color:C.textMuted, marginTop:'2px',
              fontFamily:'monospace' }}>
              {item.sku}
            </p>
          </div>
          <button onClick={onCerrar} style={{ background:'transparent', border:'none',
            cursor:'pointer', color:C.textMuted, padding:'4px',
            display:'flex', alignItems:'center' }}>
            <X size={18} />
          </button>
        </div>

        {/* Estado actual */}
        <div style={{ padding:'12px 16px', background:C.bgSec,
          border:`1px solid ${C.border}`, borderRadius:'10px', marginBottom:'16px' }}>
          <p style={{ fontSize:'13px', fontWeight:'500', color:C.text, marginBottom:'6px' }}>
            {item.descripcion}
          </p>
          <div style={{ display:'flex', gap:'16px' }}>
            {[
              { l:'En depósito', v:item.cantidad,   c:C.text    },
              { l:'Reservado',   v:item.reservado,  c:C.warning },
              { l:'Disponible',  v:item.disponible, c:C.success },
            ].map(f=>(
              <div key={f.l}>
                <p style={{ fontSize:'10.5px', color:C.textMuted }}>{f.l}</p>
                <p style={{ fontSize:'17px', fontWeight:'600', color:f.c }}>
                  {Number(f.v).toFixed(2)}
                </p>
              </div>
            ))}
          </div>
          {item.detalle_cajas && (
            <p style={{ fontSize:'12px', color:C.textSec, marginTop:'8px',
              paddingTop:'8px', borderTop:`1px solid ${C.border}` }}>
              Equivale a <strong>{item.detalle_cajas}</strong>
              {item.m2_por_caja ? ` · 1 caja = ${item.m2_por_caja} m²` : ''}
            </p>
          )}
        </div>

        {/* Tipo de ajuste */}
        <div style={{ marginBottom:'14px' }}>
          <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
            color:C.textSec, marginBottom:'6px' }}>Tipo de movimiento</label>
          <select
            value={tipo}
            onChange={e => { setTipo(e.target.value); if (e.target.value === 'ajuste') setUnidadIngreso('venta') }}
            style={{ width:'100%', height:'40px', padding:'0 12px',
              border:`1px solid ${C.border}`, borderRadius:'9px',
              fontSize:'13.5px', color:C.text, background:C.bg, outline:'none' }}>
            {TIPOS_AJU.map(t => (
              <option key={t.key} value={t.key}>{t.label}</option>
            ))}
          </select>
        </div>

        {/* Selector de unidad de ingreso — solo si admite cajas y no es ajuste exacto */}
        {admiteCajas && tipo !== 'ajuste' && (
          <div style={{ marginBottom:'14px' }}>
            <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
              color:C.textSec, marginBottom:'6px' }}>Cargar en</label>
            <div style={{ display:'flex', gap:'8px' }}>
              {[
                { key:'venta', label:'Metros² (m²)' },
                { key:'caja',  label:'Cajas' },
              ].map(u => (
                <button key={u.key} type="button"
                  onClick={() => setUnidadIngreso(u.key)}
                  style={{ flex:1, height:'40px', borderRadius:'9px', cursor:'pointer',
                    background: unidadIngreso===u.key ? C.sidebar : C.bg,
                    border:`1.5px solid ${unidadIngreso===u.key ? C.gold : C.border}`,
                    color: unidadIngreso===u.key ? C.gold : C.textSec,
                    fontSize:'13px', fontWeight: unidadIngreso===u.key?'500':'400' }}>
                  {u.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Cantidad */}
        <div style={{ marginBottom:'14px' }}>
          <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
            color:C.textSec, marginBottom:'6px' }}>
            {tipo === 'ajuste'
              ? 'Nueva cantidad total (m²)'
              : (unidadIngreso === 'caja' ? 'Cantidad de cajas' : 'Cantidad')}
          </label>
          <input
            type="number" min="0" step={unidadIngreso === 'caja' ? '1' : '0.5'}
            value={cantidad}
            onChange={e => setCantidad(e.target.value)}
            placeholder="0"
            autoFocus
            style={{ width:'100%', height:'44px', padding:'0 14px',
              border:`1px solid ${C.border}`, borderRadius:'9px',
              fontSize:'18px', fontWeight:'600', textAlign:'right',
              color:C.text, background:C.bg, outline:'none' }}
            onFocus={e=>e.target.style.borderColor=C.gold}
            onBlur={e=>e.target.style.borderColor=C.border}
          />
          {previewM2 && (
            <p style={{ fontSize:'12px', color:C.success, marginTop:'6px', textAlign:'right' }}>
              = {previewM2} m² ({cantidad} caja{Number(cantidad)!==1?'s':''} × {item.m2_por_caja} m²)
            </p>
          )}
        </div>

        {/* Observaciones */}
        <div style={{ marginBottom:'18px' }}>
          <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
            color:C.textSec, marginBottom:'6px' }}>Motivo (opcional)</label>
          <input
            value={obs}
            onChange={e => setObs(e.target.value)}
            placeholder="Ej: Reposición de proveedor, merma, etc."
            style={{ width:'100%', height:'38px', padding:'0 12px',
              border:`1px solid ${C.border}`, borderRadius:'9px',
              fontSize:'13.5px', color:C.text, background:C.bg, outline:'none' }}
            onFocus={e=>e.target.style.borderColor=C.gold}
            onBlur={e=>e.target.style.borderColor=C.border}
          />
        </div>

        <div style={{ display:'flex', gap:'10px' }}>
          <button onClick={onCerrar}
            style={{ flex:1, height:'44px', borderRadius:'9px',
              background:'transparent', border:`1px solid ${C.border}`,
              color:C.textSec, fontSize:'14px', cursor:'pointer' }}>
            Cancelar
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={!cantidad || Number(cantidad) <= 0 || mutation.isPending}
            style={{ flex:2, height:'44px', borderRadius:'9px',
              background: (!cantidad||mutation.isPending) ? C.bgTer : C.sidebar,
              border:`1.5px solid ${(!cantidad||mutation.isPending) ? C.border : C.gold}`,
              color: (!cantidad||mutation.isPending) ? C.textMuted : C.gold,
              fontSize:'14px', fontWeight:'500',
              cursor: (!cantidad||mutation.isPending) ? 'not-allowed':'pointer' }}>
            {mutation.isPending ? 'Guardando...' : 'Confirmar ajuste'}
          </button>
        </div>
      </div>
    </>
  )
}

// ─── Panel de historial de movimientos ───────────────────────────────────────
const TIPO_MOV_CFG = {
  entrada:    { color: 'success', signo: '+' },
  devolucion: { color: 'success', signo: '+' },
  liberacion: { color: 'success', signo: '+' },
  salida:     { color: 'danger',  signo: '-' },
  reserva:    { color: 'warning', signo: '-' },
  ajuste:     { color: 'info',    signo: '' },
}

function PanelHistorial({ item, onCerrar }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['movimientos-stock', item.variante_id],
    queryFn: () => inventarioApi.movimientos({ variante_id: item.variante_id }).then(r => r.data),
  })
  const movimientos = data?.results || []

  return (
    <>
      <div onClick={onCerrar} style={{ position:'fixed', inset:0, zIndex:200,
        background:'rgba(26,23,20,0.4)', backdropFilter:'blur(2px)' }} />
      <div style={{ position:'fixed', top:0, right:0, bottom:0, zIndex:201,
        width:'min(460px,95vw)', background:C.bg,
        borderLeft:`1px solid ${C.border}`,
        boxShadow:'-8px 0 32px rgba(0,0,0,0.12)',
        display:'flex', flexDirection:'column',
        animation:'slideIn 200ms ease' }}>
        <div style={{ padding:'16px 20px', borderBottom:`1px solid ${C.border}`,
          display:'flex', justifyContent:'space-between', alignItems:'flex-start',
          flexShrink:0 }}>
          <div>
            <p style={{ fontSize:'11px', color:C.textMuted, fontFamily:'monospace' }}>
              {item.sku}
            </p>
            <h3 style={{ fontSize:'16px', fontWeight:'500', color:C.text, marginTop:'2px',
              fontFamily:'var(--font-display)' }}>
              {item.descripcion}
            </h3>
          </div>
          <button onClick={onCerrar} style={{ background:'transparent', border:'none',
            cursor:'pointer', color:C.textMuted, padding:'4px',
            display:'flex', alignItems:'center' }}>
            <X size={20} />
          </button>
        </div>

        {/* Stock actual resumido */}
        <div style={{ padding:'14px 20px', borderBottom:`1px solid ${C.border}`,
          background:C.bgSec, flexShrink:0 }}>
          <div style={{ display:'flex', gap:'20px' }}>
            {[
              { l:'En depósito', v:item.cantidad,   c:C.text    },
              { l:'Reservado',   v:item.reservado,  c:C.warning },
              { l:'Disponible',  v:item.disponible, c:C.success },
            ].map(f=>(
              <div key={f.l}>
                <p style={{ fontSize:'10.5px', color:C.textMuted, marginBottom:'2px' }}>{f.l}</p>
                <p style={{ fontSize:'20px', fontWeight:'600', color:f.c }}>
                  {Number(f.v).toFixed(2)}
                </p>
              </div>
            ))}
          </div>
          {item.ubicacion && (
            <p style={{ fontSize:'12px', color:C.goldDark, marginTop:'8px',
              display:'flex', alignItems:'center', gap:'4px' }}>
              <Warehouse size={12} /> {item.ubicacion}
            </p>
          )}
        </div>

        <div style={{ flex:1, overflowY:'auto', padding:'14px 20px',
          WebkitOverflowScrolling:'touch' }}>
          <p style={{ fontSize:'11px', fontWeight:'500', color:C.textMuted,
            textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'12px' }}>
            Historial de movimientos
          </p>

          {isLoading && (
            <p style={{ fontSize:'13px', color:C.textMuted, textAlign:'center', padding:'30px 0' }}>
              Cargando…
            </p>
          )}

          {isError && (
            <p style={{ fontSize:'13px', color:C.danger, textAlign:'center', padding:'30px 0' }}>
              No se pudo cargar el historial.
            </p>
          )}

          {!isLoading && !isError && movimientos.length === 0 && (
            <p style={{ fontSize:'13px', color:C.textMuted, textAlign:'center', padding:'30px 0' }}>
              Todavía no hay movimientos registrados para esta variante.
            </p>
          )}

          <div style={{ display:'flex', flexDirection:'column', gap:'10px' }}>
            {movimientos.map(m => {
              const cfg = TIPO_MOV_CFG[m.tipo] || { color:'textSec', signo:'' }
              return (
                <div key={m.id} style={{ padding:'10px 12px', borderRadius:'8px',
                  border:`1px solid ${C.border}`, background:C.bgSec }}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
                    <div>
                      <p style={{ fontSize:'12.5px', fontWeight:'600', color:C[cfg.color] || C.text }}>
                        {m.tipo_display}
                      </p>
                      <p style={{ fontSize:'11px', color:C.textMuted, marginTop:'1px' }}>
                        {formatFecha(m.fecha)}{m.usuario_nombre ? ` · ${m.usuario_nombre}` : ''}
                      </p>
                    </div>
                    <p style={{ fontSize:'13px', fontWeight:'600', color:C[cfg.color] || C.text,
                      whiteSpace:'nowrap' }}>
                      {cfg.signo}{Number(m.cantidad).toFixed(2)}
                    </p>
                  </div>
                  <p style={{ fontSize:'11px', color:C.textMuted, marginTop:'4px' }}>
                    {Number(m.cantidad_anterior).toFixed(2)} → {Number(m.cantidad_posterior).toFixed(2)}
                    {m.observaciones ? ` · ${m.observaciones}` : ''}
                  </p>
                </div>
              )
            })}
          </div>
        </div>
      </div>
      <style>{`@keyframes slideIn{from{transform:translateX(100%)}to{transform:translateX(0)}}`}</style>
    </>
  )
}

// ─── Fila de stock ────────────────────────────────────────────────────────────
function FilaStock({ item, onAjustar, onVerHistorial }) {
  const [hov, setHov] = useState(false)

  return (
    <tr
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
    >
      <td style={{ padding:'10px 14px', borderBottom:`1px solid ${C.border}` }}>
        <p style={{ fontSize:'12px', fontWeight:'500', color:C.text,
          fontFamily:'monospace' }}>
          {item.sku}
        </p>
        <p style={{ fontSize:'11px', color:C.textMuted, marginTop:'1px' }}>
          {item.producto_codigo}
        </p>
      </td>
      <td style={{ padding:'10px 14px', borderBottom:`1px solid ${C.border}` }}>
        <p style={{ fontSize:'13px', fontWeight:'500', color:C.text }}>
          {item.descripcion?.split(' — ').slice(0,2).join(' — ')}
          {item.calidad && <span style={{ fontSize:'10.5px', fontWeight:'500',
            color:C.goldDark, background:C.goldMuted, padding:'1px 6px',
            borderRadius:'4px', marginLeft:'6px' }}>{item.calidad}</span>}
        </p>
        <p style={{ fontSize:'11px', color:C.textMuted, marginTop:'1px' }}>
          {formatGs(item.precio_venta)}
          {item.ubicacion && <span> · {item.ubicacion}</span>}
        </p>
      </td>
      <td style={{ padding:'10px 14px', borderBottom:`1px solid ${C.border}`,
        textAlign:'right' }}>
        <p style={{ fontSize:'14px', fontWeight:'600', color:C.text }}>
          {Number(item.cantidad).toFixed(2)}
        </p>
      </td>
      <td style={{ padding:'10px 14px', borderBottom:`1px solid ${C.border}`,
        textAlign:'right' }}>
        <p style={{ fontSize:'13px', color:C.warning }}>
          {Number(item.reservado).toFixed(2)}
        </p>
      </td>
      <td style={{ padding:'10px 14px', borderBottom:`1px solid ${C.border}`,
        textAlign:'right' }}>
        <p style={{ fontSize:'14px', fontWeight:'600',
          color: item.estado === 'sin_stock' ? C.danger
               : item.estado === 'critico' ? C.warning
               : C.success }}>
          {Number(item.disponible).toFixed(2)}
        </p>
        {item.detalle_cajas && (
          <p style={{ fontSize:'10.5px', color:C.textMuted, marginTop:'1px' }}>
            {item.detalle_cajas}
          </p>
        )}
      </td>
      <td style={{ padding:'10px 14px', borderBottom:`1px solid ${C.border}` }}>
        <EstadoBadge estado={item.estado} disponible={item.disponible} />
      </td>
      <td style={{ padding:'10px 14px', borderBottom:`1px solid ${C.border}` }}>
        <div style={{ display:'flex', gap:'6px', opacity: hov ? 1 : 0, transition:'opacity 120ms' }}>
          <button
            onClick={() => onAjustar(item)}
            title="Ajustar stock"
            style={{ width:'30px', height:'30px', borderRadius:'7px',
              background:C.bgSec, border:`1px solid ${C.border}`,
              cursor:'pointer', color:C.textSec,
              display:'flex', alignItems:'center', justifyContent:'center' }}
            onMouseEnter={e=>{e.currentTarget.style.borderColor=C.gold;e.currentTarget.style.color=C.goldDark}}
            onMouseLeave={e=>{e.currentTarget.style.borderColor=C.border;e.currentTarget.style.color=C.textSec}}
          >
            <ArrowUpDown size={13} />
          </button>
          <button
            onClick={() => onVerHistorial(item)}
            title="Ver historial"
            style={{ width:'30px', height:'30px', borderRadius:'7px',
              background:C.bgSec, border:`1px solid ${C.border}`,
              cursor:'pointer', color:C.textSec,
              display:'flex', alignItems:'center', justifyContent:'center' }}
            onMouseEnter={e=>{e.currentTarget.style.borderColor=C.gold;e.currentTarget.style.color=C.goldDark}}
            onMouseLeave={e=>{e.currentTarget.style.borderColor=C.border;e.currentTarget.style.color=C.textSec}}
          >
            <History size={13} />
          </button>
        </div>
      </td>
    </tr>
  )
}

// ─── Página principal ─────────────────────────────────────────────────────────
export default function InventarioPage() {
  const queryClient = useQueryClient()
  const [busqueda,    setBusqueda]    = useState('')
  const [filtroEstado,setFiltroEstado]= useState('')
  const [filtroCateg, setFiltroCateg] = useState('')
  const [itemAjuste,  setItemAjuste]  = useState(null)
  const [itemHistorial,setItemHistorial]=useState(null)
  const [pagina,      setPagina]      = useState(1)
  const busquedaDebounced = useDebounce(busqueda, 380)
  const PAGE = 40

  // Actualizar en tiempo real cuando hay ventas o ajustes
  usePedidoSocket({
    rol: 'deposito',
    onMensaje: (msg) => {
      if (msg.tipo === 'alerta_stock') {
        queryClient.invalidateQueries({ queryKey: ['stock'] })
        if (msg.estado === 'sin_stock') {
          toast.error(`Sin stock: ${msg.nombre} (${msg.sku})`, { duration: 6000 })
        } else if (msg.estado === 'critico') {
          toast(`Stock bajo: ${msg.nombre} — ${msg.disponible} disponible`,
            { icon:'⚠️', duration: 5000 })
        }
      }
    },
  })

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['stock', busquedaDebounced, filtroEstado, filtroCateg, pagina],
    queryFn: () => inventarioApi.stockGeneral({
      search:    busquedaDebounced || undefined,
      estado:    filtroEstado|| undefined,
      categoria: filtroCateg || undefined,
      page:      pagina,
      page_size: PAGE,
    }).then(r => r.data),
    staleTime: 20_000,
    keepPreviousData: true,
  })

  const { data: categorias } = useQuery({
    queryKey: ['categorias'],
    queryFn: () => productosApi.categorias().then(r => r.data?.results || r.data || []),
    staleTime: 300_000,
  })

  const items    = data?.results || []
  const total    = data?.count   || 0
  const paginas  = data?.pages   || 1

  // Stats
  const conStock  = items.filter(i => i.estado === 'disponible').length
  const critico   = items.filter(i => i.estado === 'critico').length
  const sinStock  = items.filter(i => i.estado === 'sin_stock').length

  return (
    <Layout pageTitle="Inventario" breadcrumbs={['Inventario']}>

      {/* Alertas urgentes */}
      {(critico > 0 || sinStock > 0) && (
        <div style={{ marginBottom:'16px', display:'flex', flexDirection:'column', gap:'8px' }}>
          {sinStock > 0 && (
            <div style={{ display:'flex', alignItems:'center', gap:'10px',
              padding:'11px 16px', background:C.dangerBg,
              border:`1px solid ${C.dangerBorder}`, borderLeft:`3px solid ${C.danger}`,
              borderRadius:'10px' }}>
              <XCircle size={17} style={{ color:C.danger, flexShrink:0 }} />
              <p style={{ fontSize:'13.5px', color:C.text, flex:1 }}>
                <strong>{sinStock} variante{sinStock!==1?'s':''} sin stock</strong>
                {' '}— sin mercadería disponible para vender.
              </p>
              <button onClick={() => setFiltroEstado('sin_stock')}
                style={{ padding:'5px 12px', background:'transparent',
                  border:`1px solid ${C.danger}`, borderRadius:'7px',
                  color:C.danger, fontSize:'12px', cursor:'pointer', whiteSpace:'nowrap' }}>
                Ver
              </button>
            </div>
          )}
          {critico > 0 && (
            <div style={{ display:'flex', alignItems:'center', gap:'10px',
              padding:'11px 16px', background:C.warningBg,
              border:`1px solid ${C.warningBorder}`, borderLeft:`3px solid ${C.warning}`,
              borderRadius:'10px' }}>
              <AlertCircle size={17} style={{ color:C.warning, flexShrink:0 }} />
              <p style={{ fontSize:'13.5px', color:C.text, flex:1 }}>
                <strong>{critico} variante{critico!==1?'s':''} con stock bajo</strong>
                {' '}— por debajo del mínimo configurado.
              </p>
              <button onClick={() => setFiltroEstado('critico')}
                style={{ padding:'5px 12px', background:'transparent',
                  border:`1px solid ${C.warning}`, borderRadius:'7px',
                  color:C.warning, fontSize:'12px', cursor:'pointer', whiteSpace:'nowrap' }}>
                Ver
              </button>
            </div>
          )}
        </div>
      )}

      {/* Stats */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(130px,1fr))',
        gap:'10px', marginBottom:'20px' }}>
        {[
          { l:'Total variantes', v:total,    c:C.text,    onClick:()=>setFiltroEstado('') },
          { l:'Con stock',       v:conStock,  c:C.success, onClick:()=>setFiltroEstado('disponible') },
          { l:'Stock bajo',      v:critico,   c:C.warning, onClick:()=>setFiltroEstado('critico') },
          { l:'Sin stock',       v:sinStock,  c:C.danger,  onClick:()=>setFiltroEstado('sin_stock') },
        ].map(s=>(
          <div key={s.l}
            onClick={s.onClick}
            style={{ background:C.bg, border:`1px solid ${C.border}`,
              borderRadius:'10px', padding:'13px 15px', cursor:'pointer',
              transition:'border-color 120ms' }}
            onMouseEnter={e=>e.currentTarget.style.borderColor=C.gold}
            onMouseLeave={e=>e.currentTarget.style.borderColor=C.border}>
            <p style={{ fontSize:'10.5px', color:C.textMuted, fontWeight:'500',
              textTransform:'uppercase', letterSpacing:'0.05em', marginBottom:'5px' }}>
              {s.l}
            </p>
            <p style={{ fontSize:'24px', fontWeight:'600', color:s.c }}>{s.v}</p>
          </div>
        ))}
      </div>

      {/* Filtros */}
      <div style={{ display:'flex', gap:'10px', flexWrap:'wrap', marginBottom:'16px',
        alignItems:'center' }}>
        <div style={{ position:'relative', flex:1, minWidth:'200px' }}>
          <Search size={15} style={{ position:'absolute', left:'11px', top:'50%',
            transform:'translateY(-50%)', color:C.textMuted, pointerEvents:'none' }} />
          <input
            value={busqueda}
            onChange={e => { setBusqueda(e.target.value); setPagina(1) }}
            placeholder="Buscar por SKU, nombre, código..."
            style={{ width:'100%', height:'38px', padding:'0 34px',
              border:`1px solid ${C.border}`, borderRadius:'9px',
              fontSize:'13.5px', color:C.text, background:C.bg, outline:'none' }}
            onFocus={e=>e.target.style.borderColor=C.gold}
            onBlur={e=>e.target.style.borderColor=C.border}
          />
          {busqueda && <button onClick={()=>{setBusqueda('');setPagina(1)}}
            style={{ position:'absolute', right:'9px', top:'50%',
              transform:'translateY(-50%)', background:'transparent', border:'none',
              cursor:'pointer', color:C.textMuted, display:'flex', padding:'3px' }}>
            <X size={13}/>
          </button>}
        </div>

        <select value={filtroEstado} onChange={e=>{setFiltroEstado(e.target.value);setPagina(1)}}
          style={{ height:'38px', padding:'0 12px',
            border:`1px solid ${filtroEstado?C.gold:C.border}`,
            borderRadius:'9px', fontSize:'13px',
            color:filtroEstado?C.text:C.textMuted,
            background:filtroEstado?C.goldMuted:C.bg, outline:'none', cursor:'pointer' }}>
          <option value="">Todos los estados</option>
          <option value="disponible">Con stock</option>
          <option value="critico">Stock bajo</option>
          <option value="sin_stock">Sin stock</option>
        </select>

        <select value={filtroCateg} onChange={e=>{setFiltroCateg(e.target.value);setPagina(1)}}
          style={{ height:'38px', padding:'0 12px',
            border:`1px solid ${filtroCateg?C.gold:C.border}`,
            borderRadius:'9px', fontSize:'13px',
            color:filtroCateg?C.text:C.textMuted,
            background:filtroCateg?C.goldMuted:C.bg, outline:'none', cursor:'pointer' }}>
          <option value="">Todas las categorías</option>
          {(categorias||[]).map(c=>(
            <option key={c.id} value={c.id}>{c.nombre}</option>
          ))}
        </select>

        {(filtroEstado || filtroCateg || busqueda) && (
          <button onClick={()=>{setBusqueda('');setFiltroEstado('');setFiltroCateg('');setPagina(1)}}
            style={{ height:'38px', padding:'0 12px', display:'flex', alignItems:'center', gap:'5px',
              background:'transparent', border:`1px solid ${C.border}`, borderRadius:'9px',
              color:C.textSec, fontSize:'13px', cursor:'pointer' }}>
            <RotateCcw size={13}/> Limpiar
          </button>
        )}

        <button onClick={()=>refetch()}
          style={{ width:'38px', height:'38px', borderRadius:'9px',
            background:'transparent', border:`1px solid ${C.border}`,
            cursor:'pointer', color:C.textSec,
            display:'flex', alignItems:'center', justifyContent:'center', marginLeft:'auto' }}>
          <RefreshCw size={15}/>
        </button>
      </div>

      {/* Tabla */}
      <div style={{ background:C.bg, border:`1px solid ${C.border}`,
        borderRadius:'12px', overflow:'hidden' }}>
        {isLoading ? (
          <div style={{ padding:'40px', textAlign:'center', color:C.textMuted }}>
            Cargando inventario...
          </div>
        ) : items.length === 0 ? (
          <div style={{ padding:'60px 20px', textAlign:'center', color:C.textMuted }}>
            <Package size={40} style={{ margin:'0 auto 12px', opacity:0.2 }}/>
            <p style={{ fontSize:'15px', color:C.textSec }}>Sin resultados</p>
          </div>
        ) : (
          <div style={{ overflowX:'auto' }}>
            <table style={{ width:'100%', borderCollapse:'collapse' }}>
              <thead>
                <tr style={{ background:C.bgSec }}>
                  {['SKU','Producto','Depósito','Reservado','Disponible','Estado',''].map(h=>(
                    <th key={h} style={{ padding:'10px 14px', textAlign: ['Depósito','Reservado','Disponible'].includes(h)?'right':'left',
                      fontSize:'10.5px', fontWeight:'500', letterSpacing:'0.06em',
                      textTransform:'uppercase', color:C.textMuted,
                      borderBottom:`1px solid ${C.border}`, whiteSpace:'nowrap' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((item, i) => (
                  <FilaStock
                    key={i}
                    item={item}
                    onAjustar={setItemAjuste}
                    onVerHistorial={setItemHistorial}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Paginación */}
      {paginas > 1 && (
        <div style={{ display:'flex', justifyContent:'center', gap:'6px',
          marginTop:'20px' }}>
          {Array.from({length:Math.min(paginas,7)}, (_,i) => i+1).map(p=>(
            <button key={p} onClick={()=>setPagina(p)}
              style={{ width:'36px', height:'36px', borderRadius:'8px', cursor:'pointer',
                background: p===pagina ? C.sidebar : 'transparent',
                border:`1px solid ${p===pagina?C.gold:C.border}`,
                color: p===pagina ? C.gold : C.textSec,
                fontSize:'13.5px' }}>
              {p}
            </button>
          ))}
        </div>
      )}

      {/* Panel de ajuste */}
      {itemAjuste && (
        <PanelAjuste item={itemAjuste} onCerrar={() => setItemAjuste(null)} />
      )}

      {/* Panel de historial */}
      {itemHistorial && (
        <PanelHistorial item={itemHistorial} onCerrar={() => setItemHistorial(null)} />
      )}
    </Layout>
  )
}
