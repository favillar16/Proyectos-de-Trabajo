/**
 * ShowroomPage — v3 optimizado para Xiaomi Redmi Pad SE
 *
 * Cambios respecto a v2:
 * - Grid adaptativo basado en ancho real (columnasSugeridas del hook useDevice)
 * - Targets táctiles mínimo 48px en todos los controles interactivos
 * - Sin hover states en touch (no existe en Android)
 * - Filtros colapsables en tablet para ganar espacio vertical
 * - Panel de detalle fullscreen en portrait, lateral en landscape
 * - Barra de filtros sticky para navegación rápida
 * - Cards con texto legible sin zoom (mín 14px)
 * - Paginación con botones grandes en touch
 */
import { useState, useEffect, useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Search, X, Grid3X3, List, SlidersHorizontal,
  ChevronLeft, ChevronRight, Package, Layers,
  Star, CheckCircle, AlertCircle, XCircle,
  ArrowUpDown, Tag, Building2, RotateCcw, ChevronDown,
  ScanLine, ShoppingCart, Plus, Minus, Trash2, Send, Loader2,
} from 'lucide-react'
import Layout from '../components/layout/Layout'
import GaleriaImagenes from '../components/showroom/GaleriaImagenes'
import ConsultaStock from '../components/showroom/ConsultaStock'
import { useShowroom, VISTA, ORDEN } from '../hooks/useShowroom'
import { useDevice } from '../hooks/useDevice'
import { useEscaner } from '../hooks/useEscaner'
import { useAuthStore } from '../store/authStore'
import { ventasApi } from '../services/api'
import { mensajeErrorApi } from '../utils/apiErrors'
import toast from 'react-hot-toast'

const C = {
  sidebar:    '#453941', sidebarHov:'#362F31',
  gold:       '#B99C74', goldLight:'#d4bc98', goldDark:'#8a7355',
  goldMuted:  'rgba(185,156,116,0.11)',
  border:     '#e8e4df', borderStrong:'#d0cbc4',
  bg:         '#ffffff', bgSec:'#fafaf9', bgTer:'#f5f4f2',
  text:       '#1a1714', textSec:'#6b6560', textMuted:'#9e9892',
  success:    '#3d7a5a', successBg:'#edf7f1',
  warning:    '#8a6a1a', warningBg:'#fef9ee',
  danger:     '#9a3030', dangerBg:'#fef0f0',
}

function useDebounce(value, delay = 380) {
  const [d, setD] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setD(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return d
}

function formatGs(v) { return `Gs. ${Number(v).toLocaleString('es-PY')}` }

// ─── Badge de stock ───────────────────────────────────────────────────────────
function BadgeStock({ estado, cantidad, grande = false }) {
  const cfg = {
    disponible: { bg: C.successBg, color: C.success, icon: <CheckCircle size={grande?12:10} />, label: `${Number(cantidad).toFixed(2)} disp.` },
    critico:    { bg: C.warningBg, color: C.warning,  icon: <AlertCircle size={grande?12:10} />, label: 'Stock bajo'  },
    sin_stock:  { bg: C.dangerBg,  color: C.danger,   icon: <XCircle     size={grande?12:10} />, label: 'Sin stock'   },
  }
  const s = cfg[estado] || cfg.sin_stock
  return (
    <span style={{
      display:'inline-flex', alignItems:'center', gap:'3px',
      padding: grande ? '4px 10px' : '2px 7px',
      borderRadius:'20px', background:s.bg, color:s.color,
      fontSize: grande ? '12px' : '10.5px', fontWeight:'500',
    }}>
      {s.icon} {s.label}
    </span>
  )
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────
function SkeletonCard() {
  return (
    <div style={{ background:C.bg, border:`1px solid ${C.border}`, borderRadius:'14px', overflow:'hidden' }}>
      <div style={{ aspectRatio:'4/3', background:C.bgTer, animation:'sk 1.6s ease-in-out infinite' }} />
      <div style={{ padding:'14px' }}>
        {[70,90,50].map((w,i)=>(
          <div key={i} style={{ height:i===1?'16px':'11px', width:`${w}%`,
            background:C.bgTer, borderRadius:'4px', marginBottom:'8px',
            animation:'sk 1.6s ease-in-out infinite' }} />
        ))}
      </div>
    </div>
  )
}

// ─── Card grid ────────────────────────────────────────────────────────────────
function ProductoCardGrid({ producto, onClick, isTouch }) {
  const [presionado, setPresionado] = useState(false)
  const imgUrl = producto.imagen_principal?.imagen_url || producto.imagen_principal?.imagen
  const st = Number(producto.stock_total)
  const estado = st <= 0 ? 'sin_stock' : st < 3 ? 'critico' : 'disponible'

  // En touch: feedback visual con active state en lugar de hover
  const estilo = isTouch ? {
    background:  presionado ? C.bgSec : C.bg,
    border:      `1px solid ${presionado ? C.goldDark : C.border}`,
    transform:   presionado ? 'scale(0.985)' : 'scale(1)',
    boxShadow:   'none',
  } : {
    background:  C.bg,
    border:      `1px solid ${C.border}`,
    transform:   'none',
    boxShadow:   'none',
    transition:  'all 180ms',
  }

  return (
    <div
      onClick={() => onClick(producto)}
      onTouchStart={() => setPresionado(true)}
      onTouchEnd={()   => setTimeout(() => setPresionado(false), 120)}
      onMouseEnter={isTouch ? undefined : e => {
        e.currentTarget.style.boxShadow = '0 6px 20px rgba(0,0,0,0.10)'
        e.currentTarget.style.transform = 'translateY(-3px)'
        e.currentTarget.style.borderColor = C.goldDark
      }}
      onMouseLeave={isTouch ? undefined : e => {
        e.currentTarget.style.boxShadow = 'none'
        e.currentTarget.style.transform = 'none'
        e.currentTarget.style.borderColor = C.border
      }}
      style={{
        ...estilo,
        borderRadius:'14px', overflow:'hidden', cursor:'pointer',
        transition: 'all 150ms',
        WebkitTapHighlightColor: 'transparent',
      }}
    >
      {/* Imagen con aspect ratio fijo */}
      <div style={{ aspectRatio:'4/3', position:'relative', overflow:'hidden', background:C.bgTer }}>
        {imgUrl
          ? <img src={imgUrl} alt={producto.nombre}
              style={{ width:'100%', height:'100%', objectFit:'cover' }}
              loading="lazy" />
          : <div style={{ width:'100%', height:'100%', display:'flex',
              alignItems:'center', justifyContent:'center', color:C.border }}>
              <Package size={32} style={{ opacity:0.35 }} />
            </div>
        }
        {producto.destacado && (
          <div style={{ position:'absolute', top:'8px', left:'8px',
            background:C.sidebar, border:`1px solid ${C.gold}`,
            borderRadius:'20px', padding:'3px 10px',
            fontSize:'11px', fontWeight:'500', color:C.gold,
            display:'flex', alignItems:'center', gap:'3px' }}>
            <Star size={10} fill={C.gold} /> Destacado
          </div>
        )}
        <div style={{ position:'absolute', bottom:'8px', right:'8px' }}>
          <BadgeStock estado={estado} cantidad={producto.stock_total} />
        </div>
      </div>

      {/* Info — texto legible sin zoom */}
      <div style={{ padding:'14px 15px 15px' }}>
        <p style={{ fontSize:'11px', color:C.textMuted, marginBottom:'4px' }}>
          {producto.categoria_nombre}
          {producto.marca_nombre && <> · {producto.marca_nombre}</>}
        </p>
        <h3 style={{
          fontSize:'15px', fontWeight:'500', color:C.text,
          lineHeight:'1.35', marginBottom:'12px',
          display:'-webkit-box', WebkitLineClamp:2,
          WebkitBoxOrient:'vertical', overflow:'hidden', minHeight:'40px',
        }}>
          {producto.nombre}
        </h3>
        <div style={{ display:'flex', alignItems:'baseline', justifyContent:'space-between' }}>
          <div>
            <p style={{ fontSize:'18px', fontWeight:'600', color:C.goldDark, lineHeight:1 }}>
              {formatGs(producto.precio_base)}
            </p>
            <p style={{ fontSize:'11px', color:C.textMuted, marginTop:'3px' }}>
              por {producto.unidad_venta}
            </p>
          </div>
          <p style={{ fontSize:'12px', color:C.textSec }}>
            {producto.variantes_count} var.
          </p>
        </div>
      </div>
    </div>
  )
}

// ─── Fila lista ───────────────────────────────────────────────────────────────
function ProductoFila({ producto, onClick, isTouch }) {
  const [presionado, setPresionado] = useState(false)
  const imgUrl = producto.imagen_principal?.imagen_url || producto.imagen_principal?.imagen
  const st = Number(producto.stock_total)
  const estado = st <= 0 ? 'sin_stock' : st < 3 ? 'critico' : 'disponible'

  return (
    <div
      onClick={() => onClick(producto)}
      onTouchStart={() => setPresionado(true)}
      onTouchEnd={()   => setTimeout(() => setPresionado(false), 120)}
      style={{
        display:'flex', alignItems:'center', gap:'14px',
        // Mínimo 64px de altura para target táctil cómodo
        padding:'14px 16px', minHeight:'64px',
        background: presionado ? C.bgSec : C.bg,
        borderBottom:`1px solid ${C.border}`, cursor:'pointer',
        transition:'background 100ms',
        WebkitTapHighlightColor:'transparent',
      }}
    >
      <div style={{ width:'60px', height:'60px', flexShrink:0, borderRadius:'10px',
        overflow:'hidden', background:C.bgTer,
        display:'flex', alignItems:'center', justifyContent:'center' }}>
        {imgUrl
          ? <img src={imgUrl} alt="" style={{ width:'100%', height:'100%', objectFit:'cover' }} loading="lazy" />
          : <Package size={22} style={{ color:C.border, opacity:0.5 }} />}
      </div>
      <div style={{ flex:1, minWidth:0 }}>
        <p style={{ fontSize:'11px', color:C.textMuted, marginBottom:'2px' }}>
          [{producto.codigo}] {producto.categoria_nombre}
        </p>
        <p style={{ fontSize:'15px', fontWeight:'500', color:C.text,
          overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
          {producto.nombre}
        </p>
        <p style={{ fontSize:'12px', color:C.textSec, marginTop:'2px' }}>
          {producto.variantes_count} variante{producto.variantes_count!==1?'s':''}
        </p>
      </div>
      <div style={{ textAlign:'right', flexShrink:0 }}>
        <p style={{ fontSize:'16px', fontWeight:'600', color:C.goldDark }}>
          {formatGs(producto.precio_base)}
        </p>
        <p style={{ fontSize:'11px', color:C.textMuted, marginBottom:'4px' }}>por {producto.unidad_venta}</p>
        <BadgeStock estado={estado} cantidad={producto.stock_total} />
      </div>
    </div>
  )
}

// ─── Panel de detalle ─────────────────────────────────────────────────────────
function PanelDetalle({ producto, detalle, stock, cargando, onCerrar, device, onAgregar, puedeCrearPedido }) {
  const [varianteSel, setVarianteSel] = useState(null)
  const [cantidad, setCantidad] = useState(1)

  // Resetear selección cuando cambia el producto
  useEffect(() => {
    setVarianteSel(null)
    setCantidad(1)
  }, [producto?.id])

  // Stock disponible de la variante elegida — limita cuánto se puede pedir
  const stockSel = varianteSel
    ? Math.max(0, Number(varianteSel.stock?.disponible ?? varianteSel.stock?.cantidad ?? 0))
    : Infinity

  if (!producto) return null

  const imagenes  = detalle?.imagenes  || []
  const variantes = detalle?.variantes || []

  // En portrait tablet: fullscreen. En landscape o desktop: panel lateral
  const esFullscreen = device.isPortrait && device.isTouch
  const alturaGaleria = esFullscreen ? Math.round(device.height * 0.38) : 280

  return (
    <>
      <div onClick={onCerrar} style={{ position:'fixed', inset:0, zIndex:200,
        background:'rgba(26,23,20,0.5)', backdropFilter:'blur(3px)' }} />

      <div style={{
        position:'fixed', zIndex:201,
        // Portrait touch → fullscreen desde abajo; resto → panel derecho
        ...(esFullscreen ? {
          bottom:0, left:0, right:0,
          height:'90vh',
          borderRadius:'20px 20px 0 0',
          animation:'slideUp 220ms ease',
        } : {
          top:0, right:0, bottom:0,
          width:'min(520px,92vw)',
          borderLeft:`1px solid ${C.border}`,
          animation:'slideIn 200ms ease',
        }),
        background:C.bg,
        boxShadow:'0 -8px 40px rgba(0,0,0,0.18)',
        display:'flex', flexDirection:'column',
        // Espacio seguro en la parte inferior (Android gesture nav)
        paddingBottom:'env(safe-area-inset-bottom,0px)',
      }}>
        {/* Handle de arrastre — solo en fullscreen */}
        {esFullscreen && (
          <div style={{ display:'flex', justifyContent:'center', padding:'10px 0 4px' }}>
            <div style={{ width:'36px', height:'4px', borderRadius:'2px', background:C.borderStrong }} />
          </div>
        )}

        {/* Header */}
        <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between',
          padding:'14px 20px', borderBottom:`1px solid ${C.border}`, flexShrink:0 }}>
          <div style={{ flex:1, minWidth:0, paddingRight:'12px' }}>
            <p style={{ fontSize:'11px', color:C.textMuted, marginBottom:'2px' }}>
              [{producto.codigo}] {producto.categoria_nombre}
              {producto.marca_nombre && ` · ${producto.marca_nombre}`}
            </p>
            <h2 style={{ fontSize:'18px', fontWeight:'500',
              fontFamily:'var(--font-display)', color:C.text, lineHeight:1.3 }}>
              {producto.nombre}
            </h2>
          </div>
          {/* Botón cerrar — mínimo 44×44px */}
          <button onClick={onCerrar} style={{ background:'transparent', border:'none',
            cursor:'pointer', color:C.textMuted,
            width:'44px', height:'44px',
            display:'flex', alignItems:'center', justifyContent:'center',
            borderRadius:'10px', flexShrink:0,
            WebkitTapHighlightColor:'transparent',
          }}>
            <X size={22} />
          </button>
        </div>

        {/* Contenido scrollable */}
        <div style={{ flex:1, overflowY:'auto', padding:'18px 20px',
          WebkitOverflowScrolling:'touch' }}>
          {cargando ? (
            <div style={{ display:'flex', flexDirection:'column', gap:'14px' }}>
              <div style={{ height:`${alturaGaleria}px`, background:C.bgTer,
                borderRadius:'12px', animation:'sk 1.6s infinite' }} />
              {[90,70,80].map((w,i)=>(
                <div key={i} style={{ height:'14px', width:`${w}%`,
                  background:C.bgTer, borderRadius:'4px', animation:'sk 1.6s infinite' }} />
              ))}
            </div>
          ) : (
            <>
              <GaleriaImagenes imagenes={imagenes} altura={alturaGaleria} />

              {/* Precio */}
              <div style={{ marginTop:'18px', paddingBottom:'14px',
                borderBottom:`1px solid ${C.border}` }}>
                <div style={{ display:'flex', alignItems:'baseline', gap:'10px', marginBottom:'6px' }}>
                  <p style={{ fontSize:'24px', fontWeight:'600', color:C.goldDark }}>
                    {formatGs(producto.precio_base)}
                  </p>
                  <p style={{ fontSize:'14px', color:C.textMuted }}>por {producto.unidad_venta}</p>
                </div>
              </div>

              {/* Stock por variante */}
              {stock.length > 0 && (
                <div style={{ marginTop:'20px' }}>
                  <p style={{ fontSize:'11px', fontWeight:'500', color:C.textMuted,
                    textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'10px' }}>
                    Stock disponible
                  </p>
                  <div style={{ display:'flex', flexDirection:'column', gap:'7px' }}>
                    {stock.map((item,i)=>(
                      <div key={i} style={{ display:'flex', alignItems:'center',
                        justifyContent:'space-between',
                        padding:'12px 14px', minHeight:'52px',
                        borderRadius:'10px', background:C.bgSec, border:`1px solid ${C.border}` }}>
                        <div style={{ flex:1, minWidth:0 }}>
                          <p style={{ fontSize:'14px', fontWeight:'500', color:C.text }}>
                            {item.descripcion || item.sku}
                          </p>
                          <p style={{ fontSize:'11.5px', color:C.textMuted, marginTop:'2px' }}>
                            SKU: {item.sku}{item.ubicacion && ` · ${item.ubicacion}`}
                          </p>
                        </div>
                        <BadgeStock estado={item.estado} cantidad={item.disponible} grande />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Imágenes de variantes */}
              {variantes.some(v=>v.imagenes?.length>0) && (
                <div style={{ marginTop:'20px' }}>
                  <p style={{ fontSize:'11px', fontWeight:'500', color:C.textMuted,
                    textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'10px' }}>
                    Variantes
                  </p>
                  {variantes.filter(v=>v.imagenes?.length>0).map((v,i)=>(
                    <div key={i} style={{ marginBottom:'14px' }}>
                      <p style={{ fontSize:'13px', fontWeight:'500', color:C.text, marginBottom:'7px' }}>
                        {v.color}{v.acabado?.nombre?` — ${v.acabado.nombre}`:''}
                        {v.dimension_display?` (${v.dimension_display})`:''}
                      </p>
                      <GaleriaImagenes imagenes={v.imagenes} altura={160} compact />
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer CTA — selección de variante + agregar (solo vendedor/admin) */}
        {puedeCrearPedido && (
        <div style={{ padding:'14px 20px', borderTop:`1px solid ${C.border}`,
          background:C.bgSec, flexShrink:0 }}>
          {variantes.length === 0 ? (
            <p style={{ fontSize:'13px', color:C.textMuted, textAlign:'center', padding:'4px 0' }}>
              Este producto no tiene variantes disponibles
            </p>
          ) : (
            <>
              {/* Selector de variante */}
              <p style={{ fontSize:'11px', fontWeight:'500', color:C.textMuted,
                textTransform:'uppercase', letterSpacing:'0.05em', marginBottom:'8px' }}>
                Elegí una variante
              </p>
              <div style={{ display:'flex', flexDirection:'column', gap:'6px',
                maxHeight:'160px', overflowY:'auto', marginBottom:'12px' }}>
                {variantes.map(v => {
                  const st = v.stock?.disponible ?? v.stock?.cantidad ?? 0
                  const sinStock = Number(st) <= 0
                  const sel = varianteSel?.id === v.id
                  return (
                    <button key={v.id}
                      disabled={sinStock}
                      onClick={() => {
                        setVarianteSel(v)
                        setCantidad(c => Math.max(1, Math.min(c, Math.floor(Number(st)) || 1)))
                      }}
                      style={{
                        display:'flex', alignItems:'center', justifyContent:'space-between',
                        gap:'10px', padding:'10px 12px', borderRadius:'9px',
                        background: sel ? C.goldMuted : C.bg,
                        border:`1.5px solid ${sel ? C.gold : C.border}`,
                        cursor: sinStock ? 'not-allowed' : 'pointer',
                        opacity: sinStock ? 0.5 : 1, textAlign:'left',
                        WebkitTapHighlightColor:'transparent',
                      }}>
                      <div style={{ minWidth:0, flex:1 }}>
                        <p style={{ fontSize:'13px', fontWeight:'500', color:C.text }}>
                          {v.color || 'Sin color'}
                          {v.dimension_display ? ` · ${v.dimension_display}` : ''}
                          {v.acabado?.nombre ? ` · ${v.acabado.nombre}` : ''}
                        </p>
                        <p style={{ fontSize:'11px', color: sinStock ? C.danger : C.textMuted }}>
                          {sinStock ? 'Sin stock' : `Stock: ${Number(st).toFixed(2)}`} · {formatGs(v.precio_venta)}
                        </p>
                      </div>
                      {sel && <CheckCircle size={17} style={{ color:C.gold, flexShrink:0 }} />}
                    </button>
                  )
                })}
              </div>

              {/* Cantidad + agregar */}
              {varianteSel && stockSel < Infinity && (
                <p style={{ fontSize:'10.5px', color:C.textMuted, marginBottom:'6px' }}>
                  Máximo disponible: {Math.floor(stockSel)}
                </p>
              )}
              <div style={{ display:'flex', alignItems:'center', gap:'10px' }}>
                <div style={{ display:'flex', alignItems:'center', gap:'6px' }}>
                  <button
                    onClick={() => setCantidad(c => Math.max(1, c - 1))}
                    style={{ width: device.isTouch?'44px':'38px', height: device.isTouch?'44px':'38px',
                      borderRadius:'9px', background:C.bg, border:`1px solid ${C.border}`,
                      cursor:'pointer', color:C.textSec, display:'flex', alignItems:'center',
                      justifyContent:'center', WebkitTapHighlightColor:'transparent' }}>
                    <Minus size={16} />
                  </button>
                  <input
                    type="number" min="1" max={stockSel === Infinity ? undefined : stockSel} step="1"
                    value={cantidad}
                    onChange={e => setCantidad(Math.min(Math.max(1, Number(e.target.value) || 1), Math.max(1, Math.floor(stockSel))))}
                    style={{ width:'56px', height: device.isTouch?'44px':'38px', textAlign:'center',
                      border:`1px solid ${C.border}`, borderRadius:'9px',
                      fontSize:'15px', fontWeight:'500', color:C.text, background:C.bg, outline:'none' }}
                  />
                  <button
                    onClick={() => setCantidad(c => Math.min(c + 1, Math.max(1, Math.floor(stockSel))))}
                    disabled={cantidad >= stockSel}
                    style={{ width: device.isTouch?'44px':'38px', height: device.isTouch?'44px':'38px',
                      borderRadius:'9px', background:C.bg, border:`1px solid ${C.border}`,
                      cursor: cantidad >= stockSel ? 'not-allowed' : 'pointer',
                      opacity: cantidad >= stockSel ? 0.4 : 1,
                      color:C.textSec, display:'flex', alignItems:'center',
                      justifyContent:'center', WebkitTapHighlightColor:'transparent' }}>
                    <Plus size={16} />
                  </button>
                </div>
                <button
                  disabled={!varianteSel}
                  onClick={() => {
                    if (!varianteSel) return
                    onAgregar(producto, varianteSel, cantidad)
                    setVarianteSel(null)
                    setCantidad(1)
                  }}
                  style={{
                    flex:1, height: device.isTouch?'52px':'44px', borderRadius:'12px',
                    background: varianteSel ? C.sidebar : C.bgTer,
                    border:`1px solid ${varianteSel ? C.gold : C.border}`,
                    color: varianteSel ? C.gold : C.textMuted,
                    fontSize:'15px', fontWeight:'500',
                    cursor: varianteSel ? 'pointer' : 'not-allowed',
                    display:'flex', alignItems:'center', justifyContent:'center', gap:'7px',
                    WebkitTapHighlightColor:'transparent',
                  }}>
                  <ShoppingCart size={18} />
                  Agregar al pedido
                </button>
              </div>
            </>
          )}
        </div>
        )}
      </div>
    </>
  )
}

// ─── Barra de filtros con colapso en tablet ───────────────────────────────────
function BarraFiltros({ showroom, device }) {
  const { busqueda, setBusqueda, categoria, setCategoria, marca, setMarca,
    soloStock, setSoloStock, orden, setOrden, vista, setVista,
    categorias, marcas, hayFiltrosActivos, limpiarFiltros,
    totalProductos, isFetching } = showroom

  const [filtrosExpandidos, setFiltrosExpandidos] = useState(!device.isTouch)
  const [busLocal, setBusLocal] = useState(busqueda)
  const dBus = useDebounce(busLocal, 380)

  useEffect(() => { setBusqueda(dBus) }, [dBus])

  const alturaMin = device.isTouch ? '48px' : '36px'

  return (
    <div style={{ background:C.bg, border:`1px solid ${C.border}`,
      borderRadius:'14px', padding:'14px 16px', marginBottom:'16px' }}>

      {/* Fila 1: búsqueda siempre visible */}
      <div style={{ display:'flex', gap:'10px', alignItems:'center' }}>
        <div style={{ flex:1, position:'relative' }}>
          <Search size={16} style={{ position:'absolute', left:'12px', top:'50%',
            transform:'translateY(-50%)', color:C.textMuted, pointerEvents:'none' }} />
          <input
            value={busLocal}
            onChange={e=>setBusLocal(e.target.value)}
            placeholder="Buscar por nombre, código, marca..."
            style={{
              width:'100%', padding:'0 36px',
              height: alturaMin,
              border:`1px solid ${C.border}`, borderRadius:'10px',
              fontSize:'15px', color:C.text, background:C.bg, outline:'none',
            }}
            onFocus={e=>e.target.style.borderColor=C.gold}
            onBlur={e=>e.target.style.borderColor=C.border}
          />
          {busLocal && (
            <button onClick={()=>{setBusLocal('');setBusqueda('')}}
              style={{ position:'absolute', right:'10px', top:'50%',
                transform:'translateY(-50%)', background:'transparent',
                border:'none', cursor:'pointer', color:C.textMuted,
                // Padding para agrandar target táctil
                padding:'8px', margin:'-8px', display:'flex', alignItems:'center' }}>
              <X size={15} />
            </button>
          )}
        </div>

        {/* Toggle vista */}
        <div style={{ display:'flex', border:`1px solid ${C.border}`,
          borderRadius:'10px', overflow:'hidden', flexShrink:0 }}>
          {[{v:VISTA.GRID,i:<Grid3X3 size={17}/>},{v:VISTA.LISTA,i:<List size={17}/>}].map(({v,i})=>(
            <button key={v} onClick={()=>setVista(v)}
              style={{ padding:'0 14px', height:alturaMin, border:'none', cursor:'pointer',
                background:vista===v?C.sidebar:'transparent',
                color:vista===v?C.gold:C.textSec,
                display:'flex', alignItems:'center',
                WebkitTapHighlightColor:'transparent' }}>
              {i}
            </button>
          ))}
        </div>

        {/* Botón expandir filtros (solo tablet) */}
        {device.isTouch && (
          <button
            onClick={()=>setFiltrosExpandidos(f=>!f)}
            style={{ display:'flex', alignItems:'center', gap:'5px',
              height:alturaMin, padding:'0 14px',
              background: hayFiltrosActivos ? C.sidebar : 'transparent',
              border:`1px solid ${hayFiltrosActivos ? C.gold : C.border}`,
              borderRadius:'10px', cursor:'pointer', flexShrink:0,
              color: hayFiltrosActivos ? C.gold : C.textSec,
              WebkitTapHighlightColor:'transparent',
            }}>
            <SlidersHorizontal size={16} />
            {hayFiltrosActivos && <span style={{ fontSize:'12px', fontWeight:'500' }}>●</span>}
            <ChevronDown size={14} style={{
              transform: filtrosExpandidos ? 'rotate(180deg)' : 'none',
              transition:'transform 200ms',
            }} />
          </button>
        )}
      </div>

      {/* Fila 2: filtros avanzados (colapsables en tablet) */}
      {filtrosExpandidos && (
        <div style={{ display:'flex', gap:'8px', flexWrap:'wrap',
          alignItems:'center', marginTop:'12px' }}>

          {/* Categoría */}
          <select value={categoria} onChange={e=>setCategoria(e.target.value)}
            style={{ height:alturaMin, padding:'0 12px',
              border:`1px solid ${categoria?C.gold:C.border}`, borderRadius:'9px',
              fontSize:'14px', color:categoria?C.text:C.textMuted,
              background:categoria?C.goldMuted:C.bg, outline:'none', cursor:'pointer' }}>
            <option value="">Todas las categorías</option>
            {categorias.map(c=><option key={c.id} value={c.id}>{c.nombre}</option>)}
          </select>

          {/* Marca */}
          <select value={marca} onChange={e=>setMarca(e.target.value)}
            style={{ height:alturaMin, padding:'0 12px',
              border:`1px solid ${marca?C.gold:C.border}`, borderRadius:'9px',
              fontSize:'14px', color:marca?C.text:C.textMuted,
              background:marca?C.goldMuted:C.bg, outline:'none', cursor:'pointer' }}>
            <option value="">Todas las marcas</option>
            {marcas.map(m=><option key={m.id} value={m.id}>{m.nombre}</option>)}
          </select>

          {/* Solo con stock */}
          <button onClick={()=>setSoloStock(s=>!s)}
            style={{ display:'flex', alignItems:'center', gap:'6px',
              height:alturaMin, padding:'0 14px', borderRadius:'9px',
              background:soloStock?C.sidebar:'transparent',
              border:`1px solid ${soloStock?C.gold:C.border}`,
              color:soloStock?C.gold:C.textSec,
              fontSize:'14px', cursor:'pointer',
              WebkitTapHighlightColor:'transparent' }}>
            <CheckCircle size={15} /> Con stock
          </button>

          {/* Orden */}
          <select value={orden} onChange={e=>setOrden(e.target.value)}
            style={{ height:alturaMin, padding:'0 12px', marginLeft:'auto',
              border:`1px solid ${C.border}`, borderRadius:'9px',
              fontSize:'14px', color:C.textSec, background:C.bg, outline:'none', cursor:'pointer' }}>
            <option value={ORDEN.DESTACADO}>Destacados primero</option>
            <option value={ORDEN.NOMBRE_AZ}>Nombre A→Z</option>
            <option value={ORDEN.PRECIO_ASC}>Precio ↑</option>
            <option value={ORDEN.PRECIO_DESC}>Precio ↓</option>
            <option value={ORDEN.NUEVO}>Más recientes</option>
          </select>

          {hayFiltrosActivos && (
            <button onClick={limpiarFiltros}
              style={{ display:'flex', alignItems:'center', gap:'4px',
                height:alturaMin, padding:'0 12px', borderRadius:'9px',
                background:'transparent', border:`1px solid ${C.border}`,
                color:C.textSec, fontSize:'13.5px', cursor:'pointer',
                WebkitTapHighlightColor:'transparent' }}>
              <RotateCcw size={13} /> Limpiar
            </button>
          )}
        </div>
      )}

      {/* Contador */}
      <div style={{ marginTop:'10px', display:'flex', alignItems:'center', gap:'7px' }}>
        <p style={{ fontSize:'12.5px', color:C.textMuted }}>
          {isFetching ? 'Actualizando...'
            : `${totalProductos} producto${totalProductos!==1?'s':''} encontrado${totalProductos!==1?'s':''}`}
        </p>
        {isFetching && <div style={{ width:'13px', height:'13px', borderRadius:'50%',
          border:`2px solid ${C.border}`, borderTopColor:C.gold,
          animation:'spin 0.8s linear infinite' }} />}
      </div>
    </div>
  )
}

// ─── Paginación con botones grandes ──────────────────────────────────────────
function Paginacion({ pagina, totalPaginas, setPagina, isTouch }) {
  if (totalPaginas <= 1) return null
  const delta = 2
  const rango = []
  for (let i=Math.max(1,pagina-delta); i<=Math.min(totalPaginas,pagina+delta); i++) rango.push(i)
  const sz = isTouch ? '48px' : '36px'

  const Btn = ({ n, activo, onClick: oc, children }) => (
    <button onClick={oc} style={{ width:sz, height:sz, borderRadius:'10px',
      background:activo?C.sidebar:'transparent',
      border:`1px solid ${activo?C.gold:C.border}`,
      color:activo?C.gold:C.textSec, fontWeight:activo?'500':'400',
      fontSize:'14px', cursor:'pointer',
      display:'flex', alignItems:'center', justifyContent:'center',
      WebkitTapHighlightColor:'transparent' }}>
      {children || n}
    </button>
  )

  return (
    <div style={{ display:'flex', justifyContent:'center', alignItems:'center',
      gap:'6px', marginTop:'28px', paddingBottom:'8px' }}>
      <Btn activo={false} oc={()=>setPagina(p=>Math.max(1,p-1))}
        onClick={()=>setPagina(p=>Math.max(1,p-1))}>
        <ChevronLeft size={18} />
      </Btn>
      {rango[0]>1 && <><Btn n={1} activo={pagina===1} onClick={()=>setPagina(1)} />
        {rango[0]>2 && <span style={{ color:C.textMuted, fontSize:'14px' }}>…</span>}</>}
      {rango.map(n=><Btn key={n} n={n} activo={n===pagina} onClick={()=>setPagina(n)} />)}
      {rango[rango.length-1]<totalPaginas && (
        <>{rango[rango.length-1]<totalPaginas-1 &&
          <span style={{ color:C.textMuted, fontSize:'14px' }}>…</span>}
          <Btn n={totalPaginas} activo={pagina===totalPaginas} onClick={()=>setPagina(totalPaginas)} />
        </>
      )}
      <Btn activo={false} onClick={()=>setPagina(p=>Math.min(totalPaginas,p+1))}>
        <ChevronRight size={18} />
      </Btn>
    </div>
  )
}

// ─── Carrito flotante del showroom ────────────────────────────────────────────
function CarritoShowroom({ items, onCambiarCantidad, onEliminar, onVaciar, onCerrar, device }) {
  const queryClient = useQueryClient()
  const [cliente, setCliente] = useState({ nombre:'', telefono:'' })

  const total = items.reduce((s, i) => s + Number(i.precio_unitario) * Number(i.cantidad), 0)

  const mutation = useMutation({
    mutationFn: () => ventasApi.crear({
      cliente_nombre:   cliente.nombre,
      cliente_telefono: cliente.telefono,
      descuento: 0,
      items: items.map(i => ({
        variante_id:     i.variante_id,
        cantidad:        Number(i.cantidad),
        precio_unitario: Number(i.precio_unitario),
        descuento_item:  0,
        observaciones:   '',
      })),
    }).then(r => r.data),
    onSuccess: (pedido) => {
      queryClient.invalidateQueries({ queryKey: ['pedidos'] })
      toast.success(`Nota ${pedido.numero} enviada al depósito y caja`)
      onVaciar()
      onCerrar()
    },
    onError: (err) => {
      toast.error(mensajeErrorApi(err, 'Error al crear el pedido'))
    },
  })

  return (
    <>
      <div onClick={onCerrar} style={{ position:'fixed', inset:0, zIndex:210,
        background:'rgba(26,23,20,0.5)', backdropFilter:'blur(3px)' }} />
      <div style={{
        position:'fixed', zIndex:211, top:0, right:0, bottom:0,
        width:'min(460px,94vw)', background:C.bg,
        borderLeft:`1px solid ${C.border}`, boxShadow:'0 -8px 40px rgba(0,0,0,0.18)',
        display:'flex', flexDirection:'column',
        paddingBottom:'env(safe-area-inset-bottom,0px)',
        animation:'slideIn 200ms ease',
      }}>
        {/* Header */}
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
          padding:'15px 20px', borderBottom:`1px solid ${C.border}`, flexShrink:0 }}>
          <div style={{ display:'flex', alignItems:'center', gap:'9px' }}>
            <ShoppingCart size={19} style={{ color:C.goldDark }} />
            <h2 style={{ fontSize:'16px', fontWeight:'500', color:C.text }}>
              Nota de pedido ({items.length})
            </h2>
          </div>
          <button onClick={onCerrar} style={{ background:'transparent', border:'none',
            cursor:'pointer', color:C.textMuted, width:'40px', height:'40px',
            display:'flex', alignItems:'center', justifyContent:'center', borderRadius:'10px' }}>
            <X size={22} />
          </button>
        </div>

        {/* Items */}
        <div style={{ flex:1, overflowY:'auto', WebkitOverflowScrolling:'touch' }}>
          {items.length === 0 ? (
            <div style={{ padding:'50px 20px', textAlign:'center', color:C.textMuted }}>
              <ShoppingCart size={40} style={{ margin:'0 auto 12px', opacity:0.2 }} />
              <p style={{ fontSize:'14px' }}>El pedido está vacío</p>
            </div>
          ) : items.map((item, idx) => (
            <div key={`${item.variante_id}-${idx}`} style={{ padding:'12px 16px',
              borderBottom:`1px solid ${C.border}` }}>
              <div style={{ display:'flex', justifyContent:'space-between', gap:'10px', marginBottom:'8px' }}>
                <div style={{ flex:1, minWidth:0 }}>
                  <p style={{ fontSize:'13.5px', fontWeight:'500', color:C.text }}>{item.descripcion}</p>
                  <p style={{ fontSize:'11.5px', color:C.textMuted }}>
                    {formatGs(item.precio_unitario)} · {item.sku}
                  </p>
                </div>
                <button onClick={() => onEliminar(idx)}
                  style={{ background:'transparent', border:'none', cursor:'pointer',
                    color:C.textMuted, padding:'2px', flexShrink:0 }}>
                  <Trash2 size={16} />
                </button>
              </div>
              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
                <div style={{ display:'flex', alignItems:'center', gap:'6px' }}>
                  <button onClick={() => onCambiarCantidad(idx, Math.max(1, Number(item.cantidad) - 1))}
                    style={{ width:'32px', height:'32px', borderRadius:'8px', background:C.bgSec,
                      border:`1px solid ${C.border}`, cursor:'pointer', color:C.textSec,
                      display:'flex', alignItems:'center', justifyContent:'center' }}>
                    <Minus size={14} />
                  </button>
                  <input type="number" min="1" max={item.stock_disponible ?? undefined} value={item.cantidad}
                    onChange={e => onCambiarCantidad(idx, Math.max(1, Number(e.target.value) || 1))}
                    style={{ width:'52px', height:'32px', textAlign:'center',
                      border:`1px solid ${C.border}`, borderRadius:'8px',
                      fontSize:'14px', fontWeight:'500', color:C.text, background:C.bg, outline:'none' }} />
                  <button
                    disabled={item.stock_disponible != null && Number(item.cantidad) >= item.stock_disponible}
                    onClick={() => onCambiarCantidad(idx, Number(item.cantidad) + 1)}
                    style={{ width:'32px', height:'32px', borderRadius:'8px', background:C.bgSec,
                      border:`1px solid ${C.border}`, cursor:'pointer', color:C.textSec,
                      display:'flex', alignItems:'center', justifyContent:'center',
                      opacity: (item.stock_disponible != null && Number(item.cantidad) >= item.stock_disponible) ? 0.4 : 1 }}>
                    <Plus size={14} />
                  </button>
                </div>
                <p style={{ fontSize:'14px', fontWeight:'700', color:C.goldDark }}>
                  {formatGs(Number(item.precio_unitario) * Number(item.cantidad))}
                </p>
              </div>
              {item.stock_disponible != null && Number(item.cantidad) >= item.stock_disponible && (
                <p style={{ fontSize:'10.5px', color:C.warning, marginTop:'4px' }}>
                  Máximo disponible: {item.stock_disponible}
                </p>
              )}
            </div>
          ))}

          {/* Datos del cliente */}
          {items.length > 0 && (
            <div style={{ padding:'14px 16px' }}>
              <p style={{ fontSize:'11px', fontWeight:'500', color:C.textMuted,
                textTransform:'uppercase', letterSpacing:'0.05em', marginBottom:'8px' }}>
                Cliente (opcional)
              </p>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'8px' }}>
                <input value={cliente.nombre} onChange={e => setCliente(c => ({...c, nombre:e.target.value}))}
                  placeholder="Nombre"
                  style={{ height:'40px', padding:'0 10px', border:`1px solid ${C.border}`,
                    borderRadius:'8px', fontSize:'14px', color:C.text, background:C.bg, outline:'none' }} />
                <input value={cliente.telefono} onChange={e => setCliente(c => ({...c, telefono:e.target.value}))}
                  placeholder="Teléfono"
                  style={{ height:'40px', padding:'0 10px', border:`1px solid ${C.border}`,
                    borderRadius:'8px', fontSize:'14px', color:C.text, background:C.bg, outline:'none' }} />
              </div>
            </div>
          )}
        </div>

        {/* Footer con total y envío */}
        {items.length > 0 && (
          <div style={{ padding:'14px 20px', borderTop:`1px solid ${C.border}`,
            background:C.bgSec, flexShrink:0 }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline',
              marginBottom:'12px' }}>
              <span style={{ fontSize:'15px', fontWeight:'600', color:C.text }}>Total</span>
              <span style={{ fontSize:'20px', fontWeight:'700', color:C.goldDark }}>{formatGs(total)}</span>
            </div>
            <div style={{ display:'flex', gap:'10px' }}>
              <button onClick={onVaciar}
                style={{ padding:'0 16px', height: device.isTouch?'52px':'46px', borderRadius:'11px',
                  background:'transparent', border:`1px solid ${C.border}`, color:C.textSec,
                  fontSize:'14px', cursor:'pointer', WebkitTapHighlightColor:'transparent' }}>
                Vaciar
              </button>
              <button
                disabled={mutation.isPending}
                onClick={() => mutation.mutate()}
                style={{ flex:1, height: device.isTouch?'52px':'46px', borderRadius:'11px',
                  background:C.sidebar, border:`1px solid ${C.gold}`, color:C.gold,
                  fontSize:'15px', fontWeight:'500', cursor:'pointer',
                  display:'flex', alignItems:'center', justifyContent:'center', gap:'8px',
                  WebkitTapHighlightColor:'transparent' }}>
                {mutation.isPending
                  ? <><Loader2 size={17} style={{ animation:'spin 1s linear infinite' }} /> Enviando...</>
                  : <><Send size={17} /> Enviar al depósito y caja</>}
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  )
}

// ─── Página ───────────────────────────────────────────────────────────────────
export default function ShowroomPage() {
  const showroom = useShowroom()
  const device   = useDevice()
  const { usuario } = useAuthStore()
  // Admin, Encargada de Ventas y vendedor pueden crear notas de pedido
  const puedeCrearPedido = usuario?.puede_crear_pedido
    ?? ['admin', 'encargada_ventas', 'vendedor'].includes(usuario?.rol)
  const { productos, isLoading, vista, pagina, totalPaginas, setPagina,
    productoSeleccionado, productoDetalle, stockDetalle, detalleLoading,
    setProductoSeleccionado } = showroom

  const [consultaAbierta, setConsultaAbierta] = useState(false)
  // Código leído con el lector estando el panel de consulta cerrado. Se abre
  // el panel y se le pasa: escanear tiene que funcionar sin que nadie toque
  // nada primero, que es todo el punto del lector en el showroom.
  const [codigoEscaneado, setCodigoEscaneado] = useState('')

  useEscaner((codigo) => {
    setCodigoEscaneado(codigo)
    setConsultaAbierta(true)
  }, { activo: !consultaAbierta })
  const [carrito, setCarrito] = useState([])
  const [carritoAbierto, setCarritoAbierto] = useState(false)

  const agregarAlCarrito = useCallback((producto, variante, cantidad) => {
    // Tope de stock disponible al momento de agregar/mergear — evita que el
    // carrito acumule más cantidad de la que realmente hay, aunque el ítem
    // ya esté en el carrito (antes solo se validaba al elegir la variante).
    const stockDisp = variante.stock?.disponible != null ? Number(variante.stock.disponible) : Infinity
    setCarrito(prev => {
      const idx = prev.findIndex(i => i.variante_id === variante.id)
      if (idx >= 0) {
        return prev.map((i, n) => n === idx
          ? { ...i, cantidad: Math.min(stockDisp, Number(i.cantidad) + Number(cantidad)), stock_disponible: stockDisp }
          : i)
      }
      const partes = [producto?.nombre || '']
      if (variante.dimension_display) partes.push(variante.dimension_display)
      if (variante.color)             partes.push(variante.color)
      if (variante.acabado?.nombre)   partes.push(variante.acabado.nombre)
      return [...prev, {
        variante_id:     variante.id,
        sku:             variante.sku,
        descripcion:     partes.filter(Boolean).join(' — '),
        precio_unitario: variante.precio_venta,
        cantidad:        Math.min(stockDisp, Number(cantidad)),
        stock_disponible: stockDisp,
      }]
    })
    toast.success('Agregado al pedido', { duration: 1200 })
    setProductoSeleccionado(null)
  }, [setProductoSeleccionado])

  const cambiarCantidad = useCallback((idx, cant) => {
    setCarrito(prev => prev.map((i, n) => n === idx
      ? { ...i, cantidad: Math.min(Number(cant), i.stock_disponible ?? Infinity) }
      : i))
  }, [])
  const eliminarDelCarrito = useCallback((idx) => {
    setCarrito(prev => prev.filter((_, n) => n !== idx))
  }, [])
  const vaciarCarrito = useCallback(() => setCarrito([]), [])

  const totalItemsCarrito = carrito.reduce((s, i) => s + Number(i.cantidad), 0)

  const colTemplate = vista === VISTA.GRID
    ? `repeat(${device.columnasSugeridas}, 1fr)`
    : '1fr'

  return (
    <Layout pageTitle="Showroom" breadcrumbs={['Showroom']} fullWidth>
      <BarraFiltros showroom={showroom} device={device} />

      {isLoading ? (
        <div style={{ display:'grid', gridTemplateColumns:colTemplate, gap:'14px' }}>
          {Array.from({length:device.columnasSugeridas*3}).map((_,i)=><SkeletonCard key={i} />)}
        </div>

      ) : productos.length === 0 ? (
        <div style={{ textAlign:'center', padding:'80px 20px', color:C.textMuted }}>
          <Layers size={52} style={{ margin:'0 auto 16px', opacity:0.2 }} />
          <p style={{ fontSize:'20px', fontWeight:'500',
            fontFamily:'var(--font-display)', color:C.textSec, marginBottom:'6px' }}>
            Sin productos
          </p>
          <p style={{ fontSize:'15px' }}>Probá con otros filtros</p>
          <button onClick={showroom.limpiarFiltros}
            style={{ marginTop:'20px', display:'inline-flex', alignItems:'center', gap:'7px',
              padding:'12px 20px', background:'transparent',
              border:`1px solid ${C.border}`, borderRadius:'10px',
              color:C.textSec, fontSize:'14px', cursor:'pointer',
              WebkitTapHighlightColor:'transparent' }}>
            <RotateCcw size={15} /> Limpiar filtros
          </button>
        </div>

      ) : vista === VISTA.GRID ? (
        <div style={{ display:'grid', gridTemplateColumns:colTemplate, gap:'14px' }}>
          {productos.map(p=>(
            <ProductoCardGrid key={p.id} producto={p}
              onClick={setProductoSeleccionado} isTouch={device.isTouch} />
          ))}
        </div>

      ) : (
        <div style={{ background:C.bg, border:`1px solid ${C.border}`,
          borderRadius:'14px', overflow:'hidden' }}>
          {productos.map(p=>(
            <ProductoFila key={p.id} producto={p}
              onClick={setProductoSeleccionado} isTouch={device.isTouch} />
          ))}
        </div>
      )}

      <Paginacion pagina={pagina} totalPaginas={totalPaginas}
        setPagina={setPagina} isTouch={device.isTouch} />

      <PanelDetalle
        producto={productoSeleccionado}
        detalle={productoDetalle}
        stock={stockDetalle}
        cargando={detalleLoading}
        onCerrar={()=>setProductoSeleccionado(null)}
        device={device}
        onAgregar={agregarAlCarrito}
        puedeCrearPedido={puedeCrearPedido}
      />

      {/* ── Modal de consulta rápida de stock ── */}
      <ConsultaStock
        modo="modal"
        abierto={consultaAbierta}
        codigoInicial={codigoEscaneado}
        onCerrar={() => { setConsultaAbierta(false); setCodigoEscaneado('') }}
        onAgregarPedido={(item) => {
          // item viene de la consulta rápida: { variante, producto, ... }
          setConsultaAbierta(false)
          if (item?.variante) {
            agregarAlCarrito(
              item.producto || { nombre: item.producto_nombre },
              item.variante,
              item.cantidad || 1,
            )
          }
        }}
      />

      {/* ── Carrito del showroom ── */}
      {carritoAbierto && (
        <CarritoShowroom
          items={carrito}
          onCambiarCantidad={cambiarCantidad}
          onEliminar={eliminarDelCarrito}
          onVaciar={vaciarCarrito}
          onCerrar={() => setCarritoAbierto(false)}
          device={device}
        />
      )}

      {/* ── Botón flotante del carrito (cuando hay items) ── */}
      {puedeCrearPedido && carrito.length > 0 && !carritoAbierto && !productoSeleccionado && (
        <button
          onClick={() => setCarritoAbierto(true)}
          title="Ver nota de pedido"
          style={{
            position:'fixed',
            bottom: device.isTouch ? '148px' : '88px',
            right:'24px', zIndex:81,
            height: device.isTouch ? '56px' : '50px',
            padding:'0 20px 0 16px', borderRadius:'28px',
            background:C.sidebar, border:`1.5px solid ${C.gold}`, color:C.gold,
            cursor:'pointer', display:'flex', alignItems:'center', gap:'9px',
            boxShadow:'0 4px 16px rgba(0,0,0,0.22)',
            WebkitTapHighlightColor:'transparent',
          }}>
          <div style={{ position:'relative', display:'flex' }}>
            <ShoppingCart size={device.isTouch ? 22 : 19} />
            <span style={{ position:'absolute', top:'-8px', right:'-10px',
              minWidth:'18px', height:'18px', padding:'0 4px', borderRadius:'9px',
              background:C.gold, color:C.sidebar, fontSize:'11px', fontWeight:'700',
              display:'flex', alignItems:'center', justifyContent:'center' }}>
              {totalItemsCarrito}
            </span>
          </div>
          <span style={{ fontSize:'14px', fontWeight:'500' }}>Ver pedido</span>
        </button>
      )}

      {/* ── Botón flotante de consulta rápida ── */}
      {!consultaAbierta && !productoSeleccionado && (
        <button
          onClick={() => setConsultaAbierta(true)}
          title="Consulta rápida de stock"
          style={{
            position: 'fixed',
            bottom: device.isTouch ? '80px' : '28px',
            right: '24px',
            zIndex: 80,
            width: device.isTouch ? '56px' : '48px',
            height: device.isTouch ? '56px' : '48px',
            borderRadius: '50%',
            background: C.sidebar,
            border: `1.5px solid ${C.gold}`,
            color: C.gold,
            cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 4px 16px rgba(0,0,0,0.22)',
            transition: 'transform 120ms, box-shadow 120ms',
            WebkitTapHighlightColor: 'transparent',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.transform = 'scale(1.07)'
            e.currentTarget.style.boxShadow = '0 6px 20px rgba(0,0,0,0.28)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.transform = 'scale(1)'
            e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.22)'
          }}
        >
          <ScanLine size={device.isTouch ? 24 : 20} />
        </button>
      )}

      <style>{`
        @keyframes sk { 0%,100%{opacity:1} 50%{opacity:.45} }
        @keyframes spin { to{transform:rotate(360deg)} }
        @keyframes slideIn { from{transform:translateX(100%)} to{transform:translateX(0)} }
        @keyframes slideUp { from{transform:translateY(100%)} to{transform:translateY(0)} }
      `}</style>
    </Layout>
  )
}
