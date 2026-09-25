/**
 * InventarioPage
 * Vista completa de stock con:
 * - Resumen de alertas (crítico / sin stock)
 * - Tabla filtrable por estado, categoría, búsqueda
 * - Panel de ajuste manual de stock
 * - Historial de movimientos por variante
 * - WebSocket para actualizar en tiempo real cuando hay ventas
 */
import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  AlertCircle, XCircle, CheckCircle, Package,
  Search, SlidersHorizontal, RefreshCw, Plus,
  Minus, RotateCcw, History, X, ChevronDown,
  Warehouse, TrendingDown, TrendingUp, ArrowUpDown, ClipboardList,
  Printer, FileSpreadsheet, Lock,
} from 'lucide-react'
import Layout from '../components/layout/Layout'
import { inventarioApi, productosApi } from '../services/api'
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

// Con año: el registro de ajustes mira meses hacia atrás.
function formatFechaCompleta(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('es-PY', {
    day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit',
  })
}

const TIPO_AJUSTE_LABEL = {
  entrada:'Entrada de mercadería', salida:'Salida manual',
  ajuste:'Ajuste a cantidad exacta', devolucion:'Devolución de cliente',
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
    bajo:       { bg:C.warningBg, color:C.warning, border:C.warningBorder, icon:<AlertCircle size={11}/>, label:'Bajo (25%)' },
    critico:    { bg:C.dangerBg,  color:C.danger,  border:C.dangerBorder,  icon:<AlertCircle size={11}/>, label:'Crítico (15%)' },
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
function PanelAjuste({ item, onCerrar, onVerRegistro }) {
  const queryClient = useQueryClient()
  // Lo que devolvió el servidor al guardar. Mientras exista, el cuadro
  // muestra la constancia del ajuste en vez del formulario: antes el aviso
  // duraba dos segundos y no quedaba a la vista qué se había cambiado.
  const [constancia, setConstancia] = useState(null)
  const [tipo,   setTipo]   = useState('entrada')
  const [cantidad, setCantidad] = useState('')
  const [obs,    setObs]    = useState('')
  const [unidadIngreso, setUnidadIngreso] = useState('venta')

  // ¿Este producto admite carga en cajas / pallets?
  const admiteCajas   = item.vende_por_m2 && item.m2_por_caja > 0
  const admitePallets = admiteCajas && item.cajas_por_pallet > 0
  // Vista previa de la conversión cuando se carga en cajas o pallets
  const previewM2 = (!cantidad) ? null
    : unidadIngreso === 'caja' && admiteCajas
      ? (Number(cantidad) * Number(item.m2_por_caja)).toFixed(2)
      : unidadIngreso === 'pallet' && admitePallets
        ? (Number(cantidad) * Number(item.cajas_por_pallet) * Number(item.m2_por_caja)).toFixed(2)
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
      invalidarStock(queryClient)
      queryClient.invalidateQueries({ queryKey: ['registro-ajustes'] })
      setConstancia(data)
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

        {constancia ? (
          <ConstanciaAjuste constancia={constancia} item={item}
            onCerrar={onCerrar} onVerRegistro={onVerRegistro} />
        ) : (<>
        {/* Estado actual */}
        <div style={{ padding:'12px 16px', background:C.bgSec,
          border:`1px solid ${C.border}`, borderRadius:'10px', marginBottom:'16px' }}>
          <p style={{ fontSize:'13px', fontWeight:'500', color:C.text, marginBottom:'6px' }}>
            {item.descripcion}
          </p>
          <div style={{ display:'flex', gap:'16px' }}>
            {[
              { l:'En depósito', v:item.cantidad,   c:C.text    },
              { l:'Reservado',   v:item.cantidad_reservada,  c:C.warning },
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
                ...(admitePallets ? [{ key:'pallet', label:'Pallets' }] : []),
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
              : (unidadIngreso === 'caja' ? 'Cantidad de cajas'
                : unidadIngreso === 'pallet' ? 'Cantidad de pallets' : 'Cantidad')}
          </label>
          <input
            type="number" min="0" step={unidadIngreso === 'caja' || unidadIngreso === 'pallet' ? '1' : '0.5'}
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
          {previewM2 && unidadIngreso === 'caja' && (
            <p style={{ fontSize:'12px', color:C.success, marginTop:'6px', textAlign:'right' }}>
              = {previewM2} m² ({cantidad} caja{Number(cantidad)!==1?'s':''} × {item.m2_por_caja} m²)
            </p>
          )}
          {previewM2 && unidadIngreso === 'pallet' && (
            <p style={{ fontSize:'12px', color:C.success, marginTop:'6px', textAlign:'right' }}>
              = {previewM2} m² ({cantidad} pallet{Number(cantidad)!==1?'s':''} × {item.cajas_por_pallet} cajas × {item.m2_por_caja} m²)
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
        </>)}
      </div>
    </>
  )
}

// ─── Constancia de un ajuste recién guardado ─────────────────────────────────
function ConstanciaAjuste({ constancia, item, onCerrar, onVerRegistro }) {
  const m = constancia.movimiento || {}
  const filas = [
    ['Producto',   item.descripcion],
    ['Movimiento', TIPO_AJUSTE_LABEL[m.tipo] || m.tipo_display],
    ['Cantidad',   Number(m.cantidad).toFixed(2)],
    ['Motivo',     m.observaciones || 'Sin motivo cargado'],
    ['Registrado por', m.usuario_nombre],
    ['Fecha',      formatFechaCompleta(m.fecha)],
  ]
  return (
    <div>
      <div style={{ display:'flex', alignItems:'center', gap:'8px', marginBottom:'14px',
        padding:'10px 14px', borderRadius:'10px', background:C.successBg,
        border:`1px solid ${C.successBorder}` }}>
        <CheckCircle size={18} style={{ color:C.success, flexShrink:0 }} />
        <p style={{ fontSize:'13.5px', fontWeight:'500', color:C.text }}>Ajuste registrado</p>
      </div>

      <div style={{ display:'flex', alignItems:'center', justifyContent:'center', gap:'14px',
        padding:'14px', marginBottom:'14px', borderRadius:'10px',
        background:C.bgSec, border:`1px solid ${C.border}` }}>
        <div style={{ textAlign:'center' }}>
          <p style={{ fontSize:'10.5px', color:C.textMuted }}>Antes</p>
          <p style={{ fontSize:'20px', fontWeight:'600', color:C.textSec }}>
            {Number(m.cantidad_anterior).toFixed(2)}
          </p>
        </div>
        <span style={{ fontSize:'18px', color:C.textMuted }}>→</span>
        <div style={{ textAlign:'center' }}>
          <p style={{ fontSize:'10.5px', color:C.textMuted }}>Ahora</p>
          <p style={{ fontSize:'20px', fontWeight:'600', color:C.text }}>
            {Number(m.cantidad_posterior).toFixed(2)}
          </p>
        </div>
        <div style={{ textAlign:'center', paddingLeft:'14px', borderLeft:`1px solid ${C.border}` }}>
          <p style={{ fontSize:'10.5px', color:C.textMuted }}>Disponible</p>
          <p style={{ fontSize:'20px', fontWeight:'600', color:C.success }}>
            {Number(constancia.disponible).toFixed(2)}
          </p>
        </div>
      </div>

      <div style={{ display:'flex', flexDirection:'column', gap:'6px', marginBottom:'18px' }}>
        {filas.map(([l, v]) => (
          <div key={l} style={{ display:'flex', gap:'10px', fontSize:'12.5px' }}>
            <span style={{ width:'110px', flexShrink:0, color:C.textMuted }}>{l}</span>
            <span style={{ color:C.text }}>{v}</span>
          </div>
        ))}
      </div>

      <div style={{ display:'flex', gap:'10px' }}>
        <button onClick={onVerRegistro}
          style={{ flex:1, height:'44px', borderRadius:'9px',
            background:'transparent', border:`1px solid ${C.border}`,
            color:C.textSec, fontSize:'13.5px', cursor:'pointer',
            display:'flex', alignItems:'center', justifyContent:'center', gap:'6px' }}>
          <ClipboardList size={15} /> Registro de ajustes
        </button>
        <button onClick={onCerrar}
          style={{ flex:1, height:'44px', borderRadius:'9px',
            background:C.sidebar, border:`1.5px solid ${C.gold}`,
            color:C.gold, fontSize:'14px', fontWeight:'500', cursor:'pointer' }}>
          Listo
        </button>
      </div>
    </div>
  )
}

// ─── Registro de ajustes: todos los ajustes manuales, con su motivo ──────────
function PanelRegistroAjustes({ onCerrar }) {
  const [buscar, setBuscar] = useState('')
  const [desde,  setDesde]  = useState('')
  const [hasta,  setHasta]  = useState('')
  const buscarDebounced = useDebounce(buscar, 380)
  const [generando, setGenerando] = useState(null)   // 'pdf' | 'xlsx' | null

  const filtros = {
    buscar: buscarDebounced || undefined,
    desde:  desde || undefined,
    hasta:  hasta || undefined,
  }
  const { data, isLoading, isError } = useQuery({
    queryKey: ['registro-ajustes', buscarDebounced, desde, hasta],
    queryFn: () => inventarioApi.registroAjustes(filtros).then(r => r.data),
  })
  const ajustes = data?.results || []

  // El reporte sale con los mismos filtros que la lista en pantalla. El PDF
  // se abre en una pestaña para imprimirlo; el Excel se descarga.
  const generarReporte = async (formato) => {
    setGenerando(formato)
    try {
      const res = await inventarioApi.reporteAjustes(formato, filtros)
      if (formato === 'pdf') {
        const url = window.URL.createObjectURL(new Blob([res.data], { type:'application/pdf' }))
        window.open(url, '_blank', 'noopener')
        setTimeout(() => window.URL.revokeObjectURL(url), 60_000)
      } else {
        const url = window.URL.createObjectURL(new Blob([res.data]))
        const a = document.createElement('a')
        a.href = url
        a.download = `registro_ajustes_${new Date().toISOString().slice(0,10)}.xlsx`
        document.body.appendChild(a)
        a.click()
        a.remove()
        window.URL.revokeObjectURL(url)
      }
    } catch {
      toast.error('No se pudo generar el reporte')
    } finally {
      setGenerando(null)
    }
  }
  const sinDatos = !data || data.count === 0
  const botonReporte = (activo) => ({
    height:'36px', padding:'0 12px', borderRadius:'8px', fontSize:'13px',
    display:'flex', alignItems:'center', gap:'6px', whiteSpace:'nowrap',
    border:`1px solid ${activo ? C.gold : C.border}`,
    background: activo ? C.sidebar : C.bg,
    color: activo ? C.gold : C.textMuted,
    cursor: activo ? 'pointer' : 'not-allowed',
  })

  const campo = { height:'36px', padding:'0 10px', border:`1px solid ${C.border}`,
    borderRadius:'8px', fontSize:'13px', color:C.text, background:C.bg, outline:'none' }

  return (
    <>
      <div onClick={onCerrar} style={{ position:'fixed', inset:0, zIndex:200,
        background:'rgba(26,23,20,0.4)', backdropFilter:'blur(2px)' }} />
      <div style={{ position:'fixed', top:0, right:0, bottom:0, zIndex:201,
        width:'min(560px,95vw)', background:C.bg,
        borderLeft:`1px solid ${C.border}`,
        boxShadow:'-8px 0 32px rgba(0,0,0,0.12)',
        display:'flex', flexDirection:'column',
        animation:'slideIn 200ms ease' }}>
        <div style={{ padding:'16px 20px', borderBottom:`1px solid ${C.border}`,
          display:'flex', justifyContent:'space-between', alignItems:'flex-start', flexShrink:0 }}>
          <div>
            <h3 style={{ fontSize:'16px', fontWeight:'500', color:C.text,
              fontFamily:'var(--font-display)' }}>
              Registro de ajustes
            </h3>
            <p style={{ fontSize:'12px', color:C.textMuted, marginTop:'2px' }}>
              Cada cambio de stock hecho a mano, con quién lo hizo y por qué
            </p>
          </div>
          <button onClick={onCerrar} style={{ background:'transparent', border:'none',
            cursor:'pointer', color:C.textMuted, padding:'4px', display:'flex', alignItems:'center' }}>
            <X size={20} />
          </button>
        </div>

        <div style={{ padding:'12px 20px', borderBottom:`1px solid ${C.border}`,
          background:C.bgSec, display:'flex', flexWrap:'wrap', gap:'8px', flexShrink:0 }}>
          <input value={buscar} onChange={e => setBuscar(e.target.value)}
            placeholder="Producto, SKU o motivo..."
            style={{ ...campo, flex:'1 1 180px' }} />
          <label style={{ display:'flex', alignItems:'center', gap:'5px', fontSize:'12px', color:C.textMuted }}>
            Desde <input type="date" value={desde} onChange={e => setDesde(e.target.value)} style={campo} />
          </label>
          <label style={{ display:'flex', alignItems:'center', gap:'5px', fontSize:'12px', color:C.textMuted }}>
            Hasta <input type="date" value={hasta} onChange={e => setHasta(e.target.value)} style={campo} />
          </label>
          <div style={{ display:'flex', gap:'8px', width:'100%' }}>
            <button onClick={() => generarReporte('pdf')}
              disabled={sinDatos || !!generando}
              title="Abre el reporte en PDF para imprimirlo"
              style={botonReporte(!sinDatos && !generando)}>
              <Printer size={14} /> {generando === 'pdf' ? 'Generando…' : 'Imprimir reporte'}
            </button>
            <button onClick={() => generarReporte('xlsx')}
              disabled={sinDatos || !!generando}
              title="Descarga el reporte en Excel"
              style={{ ...botonReporte(!sinDatos && !generando),
                background: C.bg, color: (!sinDatos && !generando) ? C.textSec : C.textMuted,
                borderColor: C.border }}>
              <FileSpreadsheet size={14} /> {generando === 'xlsx' ? 'Generando…' : 'Excel'}
            </button>
            <span style={{ fontSize:'11.5px', color:C.textMuted, alignSelf:'center' }}>
              Con los filtros de arriba
            </span>
          </div>
        </div>

        <div style={{ flex:1, overflowY:'auto', padding:'14px 20px', WebkitOverflowScrolling:'touch' }}>
          {isLoading && (
            <p style={{ fontSize:'13px', color:C.textMuted, textAlign:'center', padding:'30px 0' }}>Cargando…</p>
          )}
          {isError && (
            <p style={{ fontSize:'13px', color:C.danger, textAlign:'center', padding:'30px 0' }}>
              No se pudo cargar el registro.
            </p>
          )}
          {!isLoading && !isError && ajustes.length === 0 && (
            <p style={{ fontSize:'13px', color:C.textMuted, textAlign:'center', padding:'30px 0' }}>
              No hay ajustes {buscar || desde || hasta ? 'que coincidan con el filtro' : 'registrados'}.
            </p>
          )}
          {data && data.count > ajustes.length && (
            <p style={{ fontSize:'11.5px', color:C.textMuted, marginBottom:'10px' }}>
              Mostrando los {ajustes.length} más recientes de {data.count}. Acotá las fechas para ver los anteriores.
            </p>
          )}

          <div style={{ display:'flex', flexDirection:'column', gap:'10px' }}>
            {ajustes.map(m => {
              const cfg = TIPO_MOV_CFG[m.tipo] || { color:'textSec', signo:'' }
              return (
                <div key={m.id} style={{ padding:'10px 12px', borderRadius:'8px',
                  border:`1px solid ${C.border}`, background:C.bgSec }}>
                  <div style={{ display:'flex', justifyContent:'space-between', gap:'10px' }}>
                    <div style={{ minWidth:0 }}>
                      <p style={{ fontSize:'13px', fontWeight:'500', color:C.text }}>{m.descripcion}</p>
                      <p style={{ fontSize:'11px', color:C.textMuted, fontFamily:'monospace' }}>{m.sku}</p>
                    </div>
                    <div style={{ textAlign:'right', flexShrink:0 }}>
                      <p style={{ fontSize:'12px', fontWeight:'600', color:C[cfg.color] || C.text }}>
                        {TIPO_AJUSTE_LABEL[m.tipo] || m.tipo_display}
                      </p>
                      <p style={{ fontSize:'13px', color:C.text, marginTop:'1px' }}>
                        {Number(m.cantidad_anterior).toFixed(2)} → <strong>{Number(m.cantidad_posterior).toFixed(2)}</strong>
                      </p>
                    </div>
                  </div>
                  <p style={{ fontSize:'12.5px', marginTop:'6px',
                    color: m.observaciones ? C.text : C.textMuted,
                    fontStyle: m.observaciones ? 'normal' : 'italic' }}>
                    {m.observaciones || 'Sin motivo cargado'}
                  </p>
                  <p style={{ fontSize:'11px', color:C.textMuted, marginTop:'3px' }}>
                    {formatFechaCompleta(m.fecha)}{m.usuario_nombre ? ` · ${m.usuario_nombre}` : ''}
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

// ─── Panel de historial de movimientos ───────────────────────────────────────
const TIPO_MOV_CFG = {
  entrada:    { color: 'success', signo: '+' },
  devolucion: { color: 'success', signo: '+' },
  liberacion: { color: 'success', signo: '+' },
  salida:     { color: 'danger',  signo: '-' },
  reserva:    { color: 'warning', signo: '-' },
  ajuste:     { color: 'info',    signo: '' },
}

// "Ventas" deja solo las salidas por venta con el cliente y el total: la
// propietaria lo usa para cruzar contra lo que anota en papel.
const VISTAS_HISTORIAL = [
  { id:'todo',   label:'Todo',   tipo:undefined },
  { id:'ventas', label:'Ventas', tipo:'salida'  },
]

function PanelHistorial({ item, onCerrar }) {
  const [vista, setVista] = useState('todo')
  const tipo = VISTAS_HISTORIAL.find(v => v.id === vista).tipo
  const { data, isLoading, isError } = useQuery({
    queryKey: ['movimientos-stock', item.variante_id, vista],
    queryFn: () => inventarioApi.movimientos({ variante_id: item.variante_id, tipo }).then(r => r.data),
  })
  const movimientos = data?.results || []
  const { data: reservasData } = useQuery({
    queryKey: ['reservas', 'variante', item.variante_id],
    queryFn: () => inventarioApi.reservas({ variante_id: item.variante_id }).then(r => r.data),
  })
  const reservas = reservasData?.results || []

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
              { l:'Reservado',   v:item.cantidad_reservada,  c:C.warning },
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
          {/* Para quién está apartado lo reservado */}
          {reservas.length > 0 && (
            <div style={{ marginTop:'10px', paddingTop:'10px', borderTop:`1px solid ${C.border}` }}>
              <p style={{ fontSize:'10.5px', color:C.textMuted, marginBottom:'4px' }}>
                Reservado para
              </p>
              {reservas.map(r => (
                <p key={r.pedido_id} style={{ fontSize:'12px', color:C.text, marginTop:'3px',
                  display:'flex', alignItems:'center', gap:'5px' }}>
                  <Lock size={11} style={{ color:C.warning, flexShrink:0 }} />
                  <strong style={{ color:C.warning }}>{Number(r.cantidad).toFixed(2)}</strong>
                  {r.cliente_nombre || 'Cliente sin nombre'}
                  <span style={{ color:C.textMuted }}>· {r.pedido_numero} · {r.estado_display}</span>
                </p>
              ))}
            </div>
          )}
        </div>

        <div style={{ flex:1, overflowY:'auto', padding:'14px 20px',
          WebkitOverflowScrolling:'touch' }}>
          <p style={{ fontSize:'11px', fontWeight:'500', color:C.textMuted,
            textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'10px' }}>
            Historial de movimientos
          </p>

          <div style={{ display:'flex', gap:'6px', marginBottom:'12px' }}>
            {VISTAS_HISTORIAL.map(v => (
              <button key={v.id} onClick={() => setVista(v.id)}
                style={{ padding:'6px 14px', borderRadius:'16px', fontSize:'12.5px',
                  cursor:'pointer', fontWeight: vista === v.id ? '600' : '400',
                  border:`1px solid ${vista === v.id ? C.gold : C.border}`,
                  background: vista === v.id ? C.goldMuted : 'transparent',
                  color: vista === v.id ? C.goldDark : C.textSec }}>
                {v.label}
              </button>
            ))}
          </div>

          {vista === 'ventas' && !isLoading && !isError && movimientos.length > 0 && (
            <p style={{ fontSize:'12.5px', color:C.textSec, marginBottom:'12px' }}>
              Total vendido: <strong style={{ color:C.text }}>{Number(data.total).toFixed(2)}</strong>
              {' '}en {movimientos.length} {movimientos.length === 1 ? 'venta' : 'ventas'}
            </p>
          )}

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
              {vista === 'ventas'
                ? 'Todavía no hay ventas registradas para esta variante.'
                : 'Todavía no hay movimientos registrados para esta variante.'}
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
                      {m.cliente_nombre && (
                        <p style={{ fontSize:'12.5px', color:C.text, marginTop:'1px' }}>
                          {m.cliente_nombre}
                        </p>
                      )}
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
          {Number(item.cantidad_reservada).toFixed(2)}
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
        {/* Siempre visibles: en la tablet no hay hover y la propietaria
            no encontraba el historial. */}
        <div style={{ display:'flex', gap:'6px', opacity: hov ? 1 : 0.75, transition:'opacity 120ms' }}>
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
  // El tablero enlaza a /inventario?estado=… — sin leerlo, la tarjeta
  // "Sin stock" del tablero abría Inventario sin filtrar.
  const [searchParams] = useSearchParams()
  const [filtroEstado,setFiltroEstado]= useState(() => {
    const e = searchParams.get('estado')
    return ['disponible','bajo','critico','sin_stock'].includes(e) ? e : ''
  })
  const [filtroCateg, setFiltroCateg] = useState('')
  const [itemAjuste,  setItemAjuste]  = useState(null)
  const [itemHistorial,setItemHistorial]=useState(null)
  const [verRegistro, setVerRegistro] = useState(false)
  const [pagina,      setPagina]      = useState(1)
  const busquedaDebounced = useDebounce(busqueda, 380)
  const PAGE = 40

  // Stock en vivo para cualquier rol: el canal de depósito de abajo solo
  // admite depósito y admin, y trae los avisos de alerta, no cada movimiento.
  usePedidoSocket({ canal: 'stock' })

  // Actualizar en tiempo real cuando hay ventas o ajustes
  usePedidoSocket({
    rol: 'deposito',
    onMensaje: (msg) => {
      if (msg.tipo === 'alerta_stock') {
        invalidarStock(queryClient)
        if (msg.estado === 'sin_stock') {
          toast.error(`Sin stock: ${msg.nombre} (${msg.sku})`, { duration: 6000 })
        } else if (msg.estado === 'critico') {
          toast.error(`Stock crítico (15%): ${msg.nombre} — ${msg.disponible} disponible`,
            { duration: 6000 })
        } else if (msg.estado === 'bajo') {
          toast(`Stock bajo (25%): ${msg.nombre} — ${msg.disponible} disponible`,
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

  // Stats — del conteo del backend sobre todas las variantes que coinciden
  // con búsqueda y categoría, no de la página visible: contar `items`
  // daba solo las 40 filas cargadas y no coincidía con el tablero.
  const resumen   = data?.resumen || {}
  const totalVar  = resumen.total      ?? total
  const conStock  = resumen.disponible ?? 0
  const bajo      = resumen.bajo       ?? 0
  const critico   = resumen.critico    ?? 0
  const sinStock  = resumen.sin_stock  ?? 0
  const filtrarEstado = (e) => { setFiltroEstado(e); setPagina(1) }

  return (
    <Layout pageTitle="Inventario" breadcrumbs={['Inventario']}>

      {/* Alertas urgentes */}
      {(sinStock > 0 || critico > 0 || bajo > 0) && (
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
              <button onClick={() => filtrarEstado('sin_stock')}
                style={{ padding:'5px 12px', background:'transparent',
                  border:`1px solid ${C.danger}`, borderRadius:'7px',
                  color:C.danger, fontSize:'12px', cursor:'pointer', whiteSpace:'nowrap' }}>
                Ver
              </button>
            </div>
          )}
          {critico > 0 && (
            <div style={{ display:'flex', alignItems:'center', gap:'10px',
              padding:'11px 16px', background:C.dangerBg,
              border:`1px solid ${C.dangerBorder}`, borderLeft:`3px solid ${C.danger}`,
              borderRadius:'10px' }}>
              <AlertCircle size={17} style={{ color:C.danger, flexShrink:0 }} />
              <p style={{ fontSize:'13.5px', color:C.text, flex:1 }}>
                <strong>{critico} variante{critico!==1?'s':''} en stock crítico</strong>
                {' '}— quedan al 15% o menos del stock inicial.
              </p>
              <button onClick={() => filtrarEstado('critico')}
                style={{ padding:'5px 12px', background:'transparent',
                  border:`1px solid ${C.danger}`, borderRadius:'7px',
                  color:C.danger, fontSize:'12px', cursor:'pointer', whiteSpace:'nowrap' }}>
                Ver
              </button>
            </div>
          )}
          {bajo > 0 && (
            <div style={{ display:'flex', alignItems:'center', gap:'10px',
              padding:'11px 16px', background:C.warningBg,
              border:`1px solid ${C.warningBorder}`, borderLeft:`3px solid ${C.warning}`,
              borderRadius:'10px' }}>
              <AlertCircle size={17} style={{ color:C.warning, flexShrink:0 }} />
              <p style={{ fontSize:'13.5px', color:C.text, flex:1 }}>
                <strong>{bajo} variante{bajo!==1?'s':''} con stock bajo</strong>
                {' '}— quedan al 25% o menos del stock inicial.
              </p>
              <button onClick={() => filtrarEstado('bajo')}
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
          { l:'Total variantes', v:totalVar,    c:C.text,    onClick:()=>filtrarEstado('') },
          { l:'Con stock',       v:conStock,  c:C.success, onClick:()=>filtrarEstado('disponible') },
          { l:'Stock bajo (25%)',    v:bajo,    c:C.warning, onClick:()=>filtrarEstado('bajo') },
          { l:'Stock crítico (15%)', v:critico, c:C.danger,  onClick:()=>filtrarEstado('critico') },
          { l:'Sin stock',       v:sinStock,  c:C.danger,  onClick:()=>filtrarEstado('sin_stock') },
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
            placeholder="Escaneá el código, o buscá por SKU o nombre..."
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
          <option value="bajo">Stock bajo (25%)</option>
          <option value="critico">Stock crítico (15%)</option>
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

        <button onClick={() => setVerRegistro(true)}
          style={{ height:'38px', padding:'0 14px', borderRadius:'9px',
            background:'transparent', border:`1px solid ${C.border}`,
            cursor:'pointer', color:C.textSec, fontSize:'13px', whiteSpace:'nowrap',
            display:'flex', alignItems:'center', gap:'6px' }}>
          <ClipboardList size={15}/> Registro de ajustes
        </button>
        <button onClick={()=>refetch()}
          style={{ width:'38px', height:'38px', borderRadius:'9px',
            background:'transparent', border:`1px solid ${C.border}`,
            cursor:'pointer', color:C.textSec,
            display:'flex', alignItems:'center', justifyContent:'center' }}>
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
        <PanelAjuste item={itemAjuste} onCerrar={() => setItemAjuste(null)}
          onVerRegistro={() => { setItemAjuste(null); setVerRegistro(true) }} />
      )}

      {verRegistro && <PanelRegistroAjustes onCerrar={() => setVerRegistro(false)} />}

      {/* Panel de historial */}
      {itemHistorial && (
        <PanelHistorial item={itemHistorial} onCerrar={() => setItemHistorial(null)} />
      )}
    </Layout>
  )
}
