/**
 * DashboardPage — Dashboard administrativo
 *
 * KPIs: ventas de hoy / semana / mes con % vs período anterior
 * Gráfico: línea de ventas diarias (canvas nativo, sin dependencias)
 * Top productos: los 5 más vendidos del mes en ingresos
 * Medios de pago: distribución del mes
 * Pedidos activos: cola por estado en tiempo real
 * Stock: resumen con alertas
 * Feed: últimas ventas
 *
 * Solo visible para rol admin.
 * Para otros roles muestra accesos rápidos relevantes.
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  TrendingUp, TrendingDown, Minus, Scale,
  ShoppingCart, Package, Warehouse,
  CreditCard, Layers, FileText,
  AlertCircle, XCircle, CheckCircle,
  ChevronRight, RefreshCw, Clock,
  Truck, BarChart3, Banknote,
  ArrowRightLeft,
} from 'lucide-react'
import Layout from '../components/layout/Layout'
import PanelReportes from '../components/reportes/PanelReportes'
import { dashboardApi, inventarioApi, costosApi } from '../services/api'
import { useAuthStore } from '../store/authStore'

const C = {
  sidebar:   '#453941', sidebarHov:'#362F31',
  gold:      '#B99C74', goldDark:'#8a7355', goldLight:'#d4bc98',
  goldMuted: 'rgba(185,156,116,0.10)',
  border:    '#e8e4df',
  bg:        '#ffffff', bgSec:'#fafaf9', bgTer:'#f5f4f2',
  text:      '#1a1714', textSec:'#6b6560', textMuted:'#9e9892',
  success:   '#3d7a5a', successBg:'#edf7f1', successBorder:'#b8deca',
  warning:   '#8a6a1a', warningBg:'#fef9ee', warningBorder:'#f0d98a',
  danger:    '#9a3030', dangerBg:'#fef0f0', dangerBorder:'#f0b8b8',
  info:      '#2a5c8a', infoBg:'#eef4fb',
}

function formatGs(v, compact = false) {
  const n = Number(v || 0)
  if (compact) {
    if (n >= 1_000_000) return `Gs. ${(n / 1_000_000).toFixed(1)}M`
    if (n >= 1_000)     return `Gs. ${(n / 1_000).toFixed(0)}k`
  }
  return `Gs. ${n.toLocaleString('es-PY')}`
}

function getSaludo() {
  const h = new Date().getHours()
  if (h < 12) return 'Buenos días'
  if (h < 19) return 'Buenas tardes'
  return 'Buenas noches'
}

// ─── KPI Card ─────────────────────────────────────────────────────────────────
function KPICard({ label, valor, sub, pct, icon: Icon, color, onClick }) {
  const [hov, setHov] = useState(false)

  const pctColor = pct === null ? C.textMuted
    : pct > 0  ? C.success
    : pct < 0  ? C.danger
    : C.textMuted

  const PctIcon = pct === null ? Minus
    : pct > 0  ? TrendingUp
    : pct < 0  ? TrendingDown
    : Minus

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        background: C.bg, border: `1px solid ${hov && onClick ? C.goldDark : C.border}`,
        borderRadius: '14px', padding: '18px 20px',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'all 150ms',
        transform: hov && onClick ? 'translateY(-2px)' : 'none',
        boxShadow: hov && onClick ? '0 4px 14px rgba(0,0,0,0.07)' : 'none',
      }}
    >
      <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between',
        marginBottom:'10px' }}>
        <p style={{ fontSize:'11px', fontWeight:'500', color:C.textMuted,
          textTransform:'uppercase', letterSpacing:'0.06em' }}>
          {label}
        </p>
        <div style={{ width:'32px', height:'32px', borderRadius:'9px',
          background: color + '18',
          display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
          <Icon size={16} style={{ color }} />
        </div>
      </div>

      <p style={{ fontSize:'26px', fontWeight:'600', color:C.text, lineHeight:1,
        marginBottom:'5px' }}>
        {valor}
      </p>

      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <p style={{ fontSize:'12px', color:C.textMuted }}>{sub}</p>
        {pct !== undefined && (
          <div style={{ display:'flex', alignItems:'center', gap:'3px',
            fontSize:'12px', fontWeight:'500', color:pctColor }}>
            <PctIcon size={13} />
            {pct === null ? '—' : `${pct > 0 ? '+' : ''}${pct}%`}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Gráfico de línea (canvas nativo) ────────────────────────────────────────
function GraficoVentas({ datos, altura = 160 }) {
  const canvasRef = useRef(null)
  const [tooltip, setTooltip] = useState(null)

  const dibujar = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas || !datos?.length) return
    const ctx    = canvas.getContext('2d')
    const dpr    = window.devicePixelRatio || 1
    const W      = canvas.offsetWidth
    const H      = altura

    canvas.width  = W * dpr
    canvas.height = H * dpr
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, W, H)

    const pad   = { top: 12, right: 16, bottom: 28, left: 52 }
    const areaW = W - pad.left - pad.right
    const areaH = H - pad.top  - pad.bottom

    const maxVal = Math.max(...datos.map(d => d.total), 1)
    const minVal = 0

    const xPt = i => pad.left + (i / (datos.length - 1)) * areaW
    const yPt = v => pad.top + areaH - ((v - minVal) / (maxVal - minVal)) * areaH

    // Guías horizontales
    const guias = 4
    ctx.strokeStyle = 'rgba(0,0,0,0.06)'
    ctx.lineWidth   = 0.5
    for (let i = 0; i <= guias; i++) {
      const y = pad.top + (i / guias) * areaH
      ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke()
      const val = maxVal - (maxVal / guias) * i
      ctx.fillStyle  = '#9e9892'
      ctx.font       = '10px system-ui'
      ctx.textAlign  = 'right'
      ctx.fillText(val >= 1_000_000 ? `${(val/1_000_000).toFixed(1)}M`
        : val >= 1000 ? `${(val/1000).toFixed(0)}k` : val.toFixed(0),
        pad.left - 5, y + 3.5)
    }

    // Área bajo la curva
    ctx.beginPath()
    ctx.moveTo(xPt(0), yPt(datos[0].total))
    for (let i = 1; i < datos.length; i++) {
      const x0 = xPt(i-1), y0 = yPt(datos[i-1].total)
      const x1 = xPt(i),   y1 = yPt(datos[i].total)
      const cpx = (x0 + x1) / 2
      ctx.bezierCurveTo(cpx, y0, cpx, y1, x1, y1)
    }
    ctx.lineTo(xPt(datos.length - 1), pad.top + areaH)
    ctx.lineTo(xPt(0), pad.top + areaH)
    ctx.closePath()
    const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + areaH)
    grad.addColorStop(0,   'rgba(185,156,116,0.20)')
    grad.addColorStop(1,   'rgba(185,156,116,0.01)')
    ctx.fillStyle = grad
    ctx.fill()

    // Línea principal
    ctx.beginPath()
    ctx.moveTo(xPt(0), yPt(datos[0].total))
    for (let i = 1; i < datos.length; i++) {
      const x0 = xPt(i-1), y0 = yPt(datos[i-1].total)
      const x1 = xPt(i),   y1 = yPt(datos[i].total)
      const cpx = (x0 + x1) / 2
      ctx.bezierCurveTo(cpx, y0, cpx, y1, x1, y1)
    }
    ctx.strokeStyle = C.gold
    ctx.lineWidth   = 2
    ctx.stroke()

    // Puntos
    datos.forEach((d, i) => {
      ctx.beginPath()
      ctx.arc(xPt(i), yPt(d.total), 3, 0, Math.PI * 2)
      ctx.fillStyle = d.total > 0 ? C.gold : 'rgba(185,156,116,0.3)'
      ctx.fill()
    })

    // Etiquetas eje X (cada 5 días aprox)
    const paso = Math.max(1, Math.floor(datos.length / 6))
    ctx.fillStyle = '#9e9892'
    ctx.font      = '10px system-ui'
    ctx.textAlign = 'center'
    datos.forEach((d, i) => {
      if (i % paso === 0 || i === datos.length - 1) {
        ctx.fillText(d.fecha, xPt(i), H - 5)
      }
    })
  }, [datos, altura])

  useEffect(() => {
    dibujar()
    const ro = new ResizeObserver(dibujar)
    if (canvasRef.current) ro.observe(canvasRef.current)
    return () => ro.disconnect()
  }, [dibujar])

  const handleMouseMove = useCallback((e) => {
    if (!datos?.length) return
    const rect  = canvasRef.current.getBoundingClientRect()
    const pad   = { left: 52, right: 16 }
    const areaW = rect.width - pad.left - pad.right
    const relX  = e.clientX - rect.left - pad.left
    const idx   = Math.max(0, Math.min(datos.length - 1,
      Math.round((relX / areaW) * (datos.length - 1))))
    setTooltip({ idx, x: e.clientX - rect.left, y: e.clientY - rect.top })
  }, [datos])

  return (
    <div style={{ position:'relative' }}>
      <canvas
        ref={canvasRef}
        style={{ width:'100%', height:`${altura}px`, display:'block', cursor:'crosshair' }}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setTooltip(null)}
      />
      {tooltip && datos[tooltip.idx] && (
        <div style={{
          position:'absolute',
          left: Math.min(tooltip.x + 12, 999),
          top:  Math.max(tooltip.y - 52, 4),
          background: C.sidebar, border:`1px solid ${C.gold}`,
          borderRadius:'9px', padding:'7px 12px',
          fontSize:'12px', color:'#f0ece6',
          pointerEvents:'none', whiteSpace:'nowrap', zIndex:10,
          boxShadow:'0 4px 12px rgba(0,0,0,0.18)',
        }}>
          <p style={{ fontWeight:'500', marginBottom:'2px' }}>{datos[tooltip.idx].fecha}</p>
          <p style={{ color:C.gold }}>{formatGs(datos[tooltip.idx].total)}</p>
          <p style={{ color:C.goldLight, fontSize:'11px' }}>
            {datos[tooltip.idx].cantidad} venta{datos[tooltip.idx].cantidad !== 1 ? 's' : ''}
          </p>
        </div>
      )}
    </div>
  )
}

// ─── Barra de distribución ────────────────────────────────────────────────────
function BarraDistribucion({ items, total }) {
  if (!items?.length || !total) return (
    <p style={{ fontSize:'13px', color:C.textMuted, padding:'8px 0' }}>Sin datos</p>
  )
  const COLORES = [C.gold, C.success, C.info, C.warning]
  const ICONOS  = { efectivo:<Banknote size={14}/>, debito:<CreditCard size={14}/>,
    credito:<CreditCard size={14}/>, transferencia:<ArrowRightLeft size={14}/> }

  return (
    <div>
      <div style={{ display:'flex', height:'8px', borderRadius:'99px',
        overflow:'hidden', marginBottom:'12px', gap:'2px' }}>
        {items.map((item, i) => (
          <div key={item.medio} style={{
            flex: item.total / total,
            background: COLORES[i % COLORES.length],
            minWidth: '3px',
          }} />
        ))}
      </div>
      {items.map((item, i) => (
        <div key={item.medio} style={{ display:'flex', alignItems:'center',
          justifyContent:'space-between', marginBottom:'8px' }}>
          <div style={{ display:'flex', alignItems:'center', gap:'7px' }}>
            <div style={{ width:'10px', height:'10px', borderRadius:'50%',
              background: COLORES[i % COLORES.length], flexShrink:0 }} />
            <div style={{ display:'flex', alignItems:'center', gap:'5px',
              fontSize:'13px', color:C.textSec }}>
              {ICONOS[item.medio]}
              {item.label}
            </div>
          </div>
          <div style={{ textAlign:'right' }}>
            <p style={{ fontSize:'13px', fontWeight:'500', color:C.text }}>
              {formatGs(item.total, true)}
            </p>
            <p style={{ fontSize:'11px', color:C.textMuted }}>
              {Math.round(item.total / total * 100)}% · {item.cantidad} cobros
            </p>
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── Top productos ────────────────────────────────────────────────────────────
function TopProductos({ productos }) {
  if (!productos?.length) return (
    <p style={{ fontSize:'13px', color:C.textMuted, padding:'8px 0' }}>
      Sin ventas registradas aún
    </p>
  )

  const maxIngresos = Math.max(...productos.map(p => p.ingresos))

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:'10px' }}>
      {productos.map((p, i) => (
        <div key={p.codigo}>
          <div style={{ display:'flex', alignItems:'center',
            justifyContent:'space-between', marginBottom:'4px' }}>
            <div style={{ display:'flex', alignItems:'center', gap:'8px', minWidth:0 }}>
              <span style={{ fontSize:'12px', fontWeight:'600', color:C.gold,
                minWidth:'18px', textAlign:'right' }}>{i + 1}</span>
              <p style={{ fontSize:'13px', fontWeight:'500', color:C.text,
                overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                {p.nombre}
              </p>
            </div>
            <p style={{ fontSize:'13px', fontWeight:'600', color:C.goldDark,
              flexShrink:0, paddingLeft:'12px' }}>
              {formatGs(p.ingresos, true)}
            </p>
          </div>
          <div style={{ height:'4px', background:C.bgTer, borderRadius:'99px',
            overflow:'hidden', marginLeft:'26px' }}>
            <div style={{
              height:'100%', borderRadius:'99px',
              background: i === 0 ? C.gold : C.goldLight,
              width:`${(p.ingresos / maxIngresos * 100).toFixed(1)}%`,
              transition:'width 600ms ease',
            }} />
          </div>
          <p style={{ fontSize:'11px', color:C.textMuted, marginTop:'2px',
            marginLeft:'26px' }}>
            {p.unidades.toFixed(2)} unidades · {p.codigo}
          </p>
        </div>
      ))}
    </div>
  )
}

// ─── Cola de pedidos ──────────────────────────────────────────────────────────
function ColaPedidos({ activos, navigate }) {
  const items = [
    { estado:'pendiente',      label:'Pendientes',    color:C.info,    bg:C.infoBg,    icon:<Clock   size={14}/> },
    { estado:'en_preparacion', label:'En preparación',color:C.warning, bg:C.warningBg, icon:<Truck   size={14}/> },
    { estado:'listo',          label:'Listos',        color:C.success, bg:C.successBg, icon:<CheckCircle size={14}/> },
  ]

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:'8px' }}>
      {items.map(item => {
        const cant = activos?.[item.estado] || 0
        return (
          <div
            key={item.estado}
            onClick={() => navigate(`/pedidos?estado=${item.estado}`)}
            style={{
              display:'flex', alignItems:'center', justifyContent:'space-between',
              padding:'10px 14px', background:cant > 0 ? item.bg : C.bgSec,
              border:`1px solid ${cant > 0 ? item.color+'40' : C.border}`,
              borderRadius:'10px', cursor:'pointer', transition:'all 130ms',
            }}
          >
            <div style={{ display:'flex', alignItems:'center', gap:'8px',
              fontSize:'13px', color: cant > 0 ? item.color : C.textMuted }}>
              {item.icon} {item.label}
            </div>
            <div style={{ display:'flex', alignItems:'center', gap:'8px' }}>
              <span style={{ fontSize:'20px', fontWeight:'600',
                color: cant > 0 ? item.color : C.textMuted }}>
                {cant}
              </span>
              <ChevronRight size={14} style={{ color:C.textMuted }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── Feed de actividad ────────────────────────────────────────────────────────
function FeedVentas({ ventas }) {
  if (!ventas?.length) return (
    <div style={{ textAlign:'center', padding:'30px 0', color:C.textMuted }}>
      <BarChart3 size={32} style={{ margin:'0 auto 8px', opacity:0.2 }} />
      <p style={{ fontSize:'13px' }}>Aún no hay ventas registradas</p>
    </div>
  )

  return (
    <div style={{ display:'flex', flexDirection:'column' }}>
      {ventas.map((v, i) => (
        <div key={i} style={{ display:'flex', alignItems:'center', gap:'12px',
          padding:'9px 0', borderBottom: i < ventas.length-1 ? `1px solid ${C.border}` : 'none' }}>
          <div style={{ width:'36px', height:'36px', borderRadius:'9px',
            background:C.goldMuted, border:`1px solid ${C.border}`,
            display:'flex', alignItems:'center', justifyContent:'center',
            flexShrink:0 }}>
            <CreditCard size={15} style={{ color:C.goldDark }} />
          </div>
          <div style={{ flex:1, minWidth:0 }}>
            <p style={{ fontSize:'13px', fontWeight:'500', color:C.text,
              overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
              {v.cliente}
            </p>
            <p style={{ fontSize:'11.5px', color:C.textMuted }}>
              {v.medio} · {v.cajero} · {v.hace}
            </p>
          </div>
          <p style={{ fontSize:'14px', fontWeight:'600', color:C.goldDark, flexShrink:0 }}>
            {formatGs(v.monto, true)}
          </p>
        </div>
      ))}
    </div>
  )
}

// ─── Stock resumen ────────────────────────────────────────────────────────────
function StockResumen({ stock, navigate }) {
  const items = [
    { label:'Con stock', valor:stock?.ok      || 0, color:C.success, bg:C.successBg, path:'/inventario?estado=disponible' },
    { label:'Stock bajo',valor:stock?.critico || 0, color:C.warning, bg:C.warningBg, path:'/inventario?estado=critico'    },
    { label:'Sin stock', valor:stock?.sin_stock||0, color:C.danger,  bg:C.dangerBg,  path:'/inventario?estado=sin_stock'  },
  ]
  return (
    <div style={{ display:'flex', gap:'8px' }}>
      {items.map(s => (
        <div key={s.label}
          onClick={() => navigate(s.path)}
          style={{ flex:1, padding:'12px 10px', textAlign:'center',
            background: s.valor > 0 && s.label !== 'Con stock' ? s.bg : C.bgSec,
            border:`1px solid ${s.valor > 0 && s.label !== 'Con stock' ? s.color+'40' : C.border}`,
            borderRadius:'10px', cursor:'pointer', transition:'all 130ms' }}>
          <p style={{ fontSize:'22px', fontWeight:'600',
            color: s.valor > 0 && s.label !== 'Con stock' ? s.color : (s.label === 'Con stock' ? C.success : C.textMuted) }}>
            {s.valor}
          </p>
          <p style={{ fontSize:'10.5px', color:C.textMuted, marginTop:'2px' }}>{s.label}</p>
        </div>
      ))}
    </div>
  )
}

// ─── Skeleton de carga ────────────────────────────────────────────────────────
function Skeleton({ h = 80, r = 14 }) {
  return <div style={{ height:`${h}px`, background:C.bgTer, borderRadius:`${r}px`,
    animation:'pulse 1.6s ease-in-out infinite' }} />
}

// ─── Vista de roles no-admin ──────────────────────────────────────────────────
function AccesosRapidos({ usuario, navigate }) {
  const accesos = {
    vendedor:  [
      { icon:Layers,       label:'Ir al showroom',   desc:'Ver el catálogo',       path:'/showroom'   },
      { icon:ShoppingCart, label:'Mis pedidos',      desc:'Ver el estado',         path:'/pedidos'    },
    ],
    cajero:    [
      { icon:CreditCard,   label:'Abrir caja',       desc:'Comenzar turno',        path:'/caja'       },
      { icon:ShoppingCart, label:'Pedidos listos',   desc:'Para cobrar',           path:'/pedidos'    },
    ],
    deposito:  [
      { icon:Package,      label:'Pedidos pendientes',desc:'Para preparar',        path:'/pedidos'    },
      { icon:Warehouse,    label:'Inventario',       desc:'Ver stock',             path:'/inventario' },
    ],
  }

  const lista = accesos[usuario?.rol] || []
  const h = new Date().getHours()
  const saludo = h < 12 ? 'Buenos días' : h < 19 ? 'Buenas tardes' : 'Buenas noches'

  return (
    <div style={{ display:'flex', flexDirection:'column', alignItems:'center',
      justifyContent:'center', minHeight:'60vh', padding:'20px', gap:'20px' }}>
      <div style={{ textAlign:'center' }}>
        <p style={{ fontSize:'13px', color:C.gold, fontWeight:'500', marginBottom:'4px' }}>
          {saludo}
        </p>
        <h1 style={{ fontSize:'24px', fontWeight:'500', color:C.text,
          fontFamily:'var(--font-display)' }}>
          {usuario?.nombre_completo}
        </h1>
      </div>
      <div style={{ display:'flex', gap:'12px', flexWrap:'wrap', justifyContent:'center' }}>
        {lista.map(a => (
          <div key={a.path}
            onClick={() => navigate(a.path)}
            style={{ background:C.bg, border:`1px solid ${C.border}`, borderRadius:'14px',
              padding:'20px 24px', cursor:'pointer', textAlign:'center',
              minWidth:'180px', transition:'all 150ms' }}
            onMouseEnter={e=>{e.currentTarget.style.borderColor=C.gold; e.currentTarget.style.transform='translateY(-2px)'}}
            onMouseLeave={e=>{e.currentTarget.style.borderColor=C.border; e.currentTarget.style.transform='none'}}>
            <a.icon size={28} style={{ color:C.goldDark, marginBottom:'10px' }} />
            <p style={{ fontSize:'14px', fontWeight:'500', color:C.text }}>{a.label}</p>
            <p style={{ fontSize:'12px', color:C.textMuted, marginTop:'3px' }}>{a.desc}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Dashboard principal (solo admin) ────────────────────────────────────────
function DashboardAdmin({ navigate }) {
  const [rango, setRango] = useState(30)
  const hoy = new Date()

  const { data: kpi, isLoading, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['kpis', rango],
    queryFn: () => dashboardApi.kpis(rango).then(r => r.data),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  })

  // Costos del mes actual para el balance
  const { data: costosMes } = useQuery({
    queryKey: ['costos-resumen', hoy.getFullYear(), hoy.getMonth() + 1],
    queryFn: () => costosApi.resumen(hoy.getFullYear(), hoy.getMonth() + 1).then(r => r.data),
    staleTime: 60_000,
  })

  const totalMedios = kpi?.ventas?.por_medio?.reduce((s, m) => s + m.total, 0) || 0

  const ultimaActualizacion = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString('es-PY', { hour:'2-digit', minute:'2-digit' })
    : ''

  // Balance del mes: ingresos del día/mes vs costos del mes
  const ventasMes  = kpi?.ventas?.mes?.total || 0
  const gastosMes  = costosMes?.total_gastos || 0
  const balanceMes = ventasMes - gastosMes
  const margenPct  = ventasMes > 0 ? Math.round((balanceMes / ventasMes) * 100) : null

  return (
    <div>
      {/* Barra de control */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
        marginBottom:'20px', flexWrap:'wrap', gap:'10px' }}>
        <div>
          <h2 style={{ fontSize:'18px', fontWeight:'500', color:C.text,
            fontFamily:'var(--font-display)' }}>
            {getSaludo()} — Dashboard
          </h2>
          {ultimaActualizacion && (
            <p style={{ fontSize:'11.5px', color:C.textMuted, marginTop:'2px' }}>
              Actualizado a las {ultimaActualizacion}
            </p>
          )}
        </div>
        <div style={{ display:'flex', gap:'8px', alignItems:'center' }}>
          {/* Selector de rango */}
          <div style={{ display:'flex', border:`1px solid ${C.border}`, borderRadius:'9px',
            overflow:'hidden' }}>
            {[
              { v:7,  l:'7d'  },
              { v:30, l:'30d' },
              { v:90, l:'90d' },
            ].map(r => (
              <button key={r.v} onClick={() => setRango(r.v)}
                style={{ padding:'7px 13px', border:'none', cursor:'pointer',
                  background: rango===r.v ? C.sidebar : 'transparent',
                  color: rango===r.v ? C.gold : C.textSec,
                  fontSize:'13px', fontWeight: rango===r.v ? '500' : '400',
                  transition:'all 120ms' }}>
                {r.l}
              </button>
            ))}
          </div>
          <button onClick={() => refetch()}
            style={{ width:'36px', height:'36px', borderRadius:'9px',
              background:'transparent', border:`1px solid ${C.border}`,
              cursor:'pointer', color:C.textSec,
              display:'flex', alignItems:'center', justifyContent:'center' }}>
            <RefreshCw size={15} />
          </button>
        </div>
      </div>

      {/* ── KPIs principales ── */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',
        gap:'12px', marginBottom:'20px' }}>
        {isLoading ? (
          [0,1,2,3].map(i => <Skeleton key={i} h={112} />)
        ) : (
          <>
            <KPICard
              label="Ventas hoy"
              valor={formatGs(kpi?.ventas?.hoy?.total, true)}
              sub={`${kpi?.ventas?.hoy?.cantidad || 0} cobro${kpi?.ventas?.hoy?.cantidad !== 1 ? 's' : ''}`}
              pct={kpi?.ventas?.hoy?.vs_ayer}
              icon={CreditCard}
              color={C.goldDark}
              onClick={() => navigate('/caja')}
            />
            <KPICard
              label="Ventas esta semana"
              valor={formatGs(kpi?.ventas?.semana?.total, true)}
              sub={`${kpi?.ventas?.semana?.cantidad || 0} cobros`}
              pct={kpi?.ventas?.semana?.vs_ant}
              icon={TrendingUp}
              color={C.success}
            />
            <KPICard
              label={`Ventas últimos ${rango}d`}
              valor={formatGs(kpi?.ventas?.mes?.total, true)}
              sub={`${kpi?.ventas?.mes?.cantidad || 0} cobros`}
              pct={kpi?.ventas?.mes?.vs_ant}
              icon={BarChart3}
              color={C.info}
            />
            <KPICard
              label="Ticket promedio"
              valor={formatGs(kpi?.ventas?.ticket_prom, true)}
              sub={`últimos ${rango} días`}
              icon={ShoppingCart}
              color={C.warning}
            />
          </>
        )}
      </div>

      {/* ── Balance del mes (ingresos − costos) ── */}
      {costosMes && (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',
          gap:'10px', marginBottom:'20px',
          padding:'14px 16px', background:C.bg,
          border:`1px solid ${C.border}`, borderRadius:'14px' }}>
          <div>
            <p style={{ fontSize:'10.5px', fontWeight:'500', color:C.textMuted,
              textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'5px' }}>
              Ingresos del mes
            </p>
            <p style={{ fontSize:'20px', fontWeight:'600', color:C.success }}>
              {formatGs(ventasMes, true)}
            </p>
          </div>
          <div>
            <p style={{ fontSize:'10.5px', fontWeight:'500', color:C.textMuted,
              textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'5px' }}>
              Costos del mes
            </p>
            <p style={{ fontSize:'20px', fontWeight:'600', color:C.danger }}>
              − {formatGs(gastosMes, true)}
            </p>
            <p style={{ fontSize:'11px', color:C.textMuted, marginTop:'2px' }}>
              {costosMes.pendientes > 0 && `Gs. ${Number(costosMes.pendientes).toLocaleString('es-PY')} pendiente`}
            </p>
          </div>
          <div>
            <p style={{ fontSize:'10.5px', fontWeight:'500', color:C.textMuted,
              textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'5px' }}>
              Balance neto
            </p>
            <p style={{ fontSize:'22px', fontWeight:'700',
              color: balanceMes >= 0 ? C.success : C.danger }}>
              {balanceMes >= 0 ? '' : '− '}{formatGs(Math.abs(balanceMes), true)}
            </p>
            {margenPct !== null && (
              <p style={{ fontSize:'11px', marginTop:'2px',
                color: margenPct >= 0 ? C.success : C.danger }}>
                Margen: {margenPct}%
              </p>
            )}
          </div>
          <div style={{ display:'flex', alignItems:'center' }}>
            <button onClick={() => navigate('/costos')}
              style={{ padding:'7px 14px', background:'transparent',
                border:`1px solid ${C.border}`, borderRadius:'8px',
                color:C.textSec, fontSize:'12.5px', cursor:'pointer',
                display:'flex', alignItems:'center', gap:'5px', transition:'all 120ms' }}
              onMouseEnter={e=>{e.currentTarget.style.borderColor=C.gold;e.currentTarget.style.color=C.goldDark}}
              onMouseLeave={e=>{e.currentTarget.style.borderColor=C.border;e.currentTarget.style.color=C.textSec}}>
              Ver costos →
            </button>
          </div>
        </div>
      )}

      {/* ── Gráfico + Pedidos ── */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 280px',
        gap:'14px', marginBottom:'14px' }}>

        {/* Gráfico de ventas */}
        <div style={{ background:C.bg, border:`1px solid ${C.border}`,
          borderRadius:'14px', padding:'18px 20px' }}>
          <p style={{ fontSize:'12px', fontWeight:'500', color:C.textMuted,
            textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'14px' }}>
            Evolución de ventas
          </p>
          {isLoading
            ? <Skeleton h={160} r={8} />
            : <GraficoVentas datos={kpi?.ventas?.grafico} altura={160} />}
        </div>

        {/* Cola de pedidos */}
        <div style={{ background:C.bg, border:`1px solid ${C.border}`,
          borderRadius:'14px', padding:'18px 20px' }}>
          <p style={{ fontSize:'12px', fontWeight:'500', color:C.textMuted,
            textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'12px' }}>
            Pedidos activos
          </p>
          {isLoading
            ? <div style={{ display:'flex', flexDirection:'column', gap:'8px' }}>
                {[0,1,2].map(i=><Skeleton key={i} h={52} r={10} />)}
              </div>
            : <ColaPedidos activos={kpi?.pedidos_activos} navigate={navigate} />}
        </div>
      </div>

      {/* ── Top productos + Medios de pago ── */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr',
        gap:'14px', marginBottom:'14px' }}>

        <div style={{ background:C.bg, border:`1px solid ${C.border}`,
          borderRadius:'14px', padding:'18px 20px' }}>
          <p style={{ fontSize:'12px', fontWeight:'500', color:C.textMuted,
            textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'14px' }}>
            Top 5 productos — ingresos
          </p>
          {isLoading
            ? <div style={{ display:'flex', flexDirection:'column', gap:'12px' }}>
                {[80,70,60,50,40].map((w,i)=>(
                  <div key={i} style={{ height:'14px', width:`${w}%`, background:C.bgTer,
                    borderRadius:'4px', animation:'pulse 1.6s infinite' }} />
                ))}
              </div>
            : <TopProductos productos={kpi?.top_productos} />}
        </div>

        <div style={{ background:C.bg, border:`1px solid ${C.border}`,
          borderRadius:'14px', padding:'18px 20px' }}>
          <p style={{ fontSize:'12px', fontWeight:'500', color:C.textMuted,
            textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'14px' }}>
            Medios de pago
          </p>
          {isLoading
            ? <Skeleton h={120} r={8} />
            : <BarraDistribucion items={kpi?.ventas?.por_medio} total={totalMedios} />}
        </div>
      </div>

      {/* ── Stock + Feed de actividad ── */}
      <div style={{ display:'grid', gridTemplateColumns:'280px 1fr',
        gap:'14px', marginBottom:'8px' }}>

        <div style={{ background:C.bg, border:`1px solid ${C.border}`,
          borderRadius:'14px', padding:'18px 20px' }}>
          <p style={{ fontSize:'12px', fontWeight:'500', color:C.textMuted,
            textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'12px' }}>
            Resumen de stock
          </p>
          {isLoading
            ? <Skeleton h={80} r={10} />
            : <StockResumen stock={kpi?.stock} navigate={navigate} />}
          {!isLoading && (kpi?.stock?.sin_stock > 0 || kpi?.stock?.critico > 0) && (
            <button
              onClick={() => navigate('/inventario')}
              style={{ marginTop:'12px', width:'100%', height:'36px', borderRadius:'9px',
                background:'transparent',
                border:`1px solid ${kpi?.stock?.sin_stock > 0 ? C.danger : C.warning}`,
                color: kpi?.stock?.sin_stock > 0 ? C.danger : C.warning,
                fontSize:'12.5px', cursor:'pointer', transition:'all 120ms' }}>
              Ver inventario →
            </button>
          )}
        </div>

        <div style={{ background:C.bg, border:`1px solid ${C.border}`,
          borderRadius:'14px', padding:'18px 20px' }}>
          <p style={{ fontSize:'12px', fontWeight:'500', color:C.textMuted,
            textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'4px' }}>
            Últimas ventas
          </p>
          {isLoading
            ? <div style={{ display:'flex', flexDirection:'column', gap:'10px', marginTop:'8px' }}>
                {[0,1,2,3,4].map(i=><Skeleton key={i} h={44} r={6} />)}
              </div>
            : <FeedVentas ventas={kpi?.ultimas_ventas} />}
        </div>
      </div>

      {/* ── Reportes descargables ── */}
      <div style={{ marginTop:'20px' }}>
        <PanelReportes />
      </div>

      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.45} }
      `}</style>
    </div>
  )
}

// ─── Página principal ─────────────────────────────────────────────────────────
export default function DashboardPage() {
  const navigate = useNavigate()
  const { usuario } = useAuthStore()
  const esAdmin = usuario?.rol === 'admin'

  return (
    <Layout pageTitle="Inicio" breadcrumbs={['Inicio']} fullWidth>
      {esAdmin
        ? <DashboardAdmin navigate={navigate} />
        : <AccesosRapidos usuario={usuario} navigate={navigate} />
      }
    </Layout>
  )
}
