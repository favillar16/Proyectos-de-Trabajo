/**
 * ProductosPage
 * Listado de productos con panel lateral deslizante para crear/editar.
 * Incluye búsqueda, filtros, stats y grid de cards.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Search, Package, Image, Edit2, Eye, X, SlidersHorizontal, Layers } from 'lucide-react'
import { productosApi } from '../services/api'
import Layout from '../components/layout/Layout'
import ProductoForm from '../components/productos/ProductoForm'
import GestionCatalogos from '../components/productos/GestionCatalogos'
import { useProductoForm } from '../hooks/useProductoForm'

const C = {
  sidebar:    '#453941',
  gold:       '#B99C74',
  goldDark:   '#8a7355',
  border:     '#e8e4df',
  bg:         '#ffffff',
  bgSec:      '#fafaf9',
  bgTer:      '#f5f4f2',
  text:       '#1a1714',
  textSec:    '#6b6560',
  textMuted:  '#9e9892',
  success:    '#3d7a5a',
  successBg:  '#edf7f1',
  danger:     '#9a3030',
  dangerBg:   '#fef0f0',
  warning:    '#8a6a1a',
  warningBg:  '#fef9ee',
}

// ─── Card de producto ─────────────────────────────────────────────────────────

function EstadoStock({ stock }) {
  const val = Number(stock)
  if (val <= 0)   return <span style={{ fontSize:'11px', fontWeight:'500', color: C.danger }}>Sin stock</span>
  if (val < 5)    return <span style={{ fontSize:'11px', fontWeight:'500', color: C.warning }}>Stock bajo</span>
  return <span style={{ fontSize:'11px', fontWeight:'500', color: C.success }}>{val.toFixed(2)} en stock</span>
}

function ProductoCard({ producto, onEditar, onVerDetalle }) {
  const [hovered, setHovered] = useState(false)
  const imagenUrl = producto.imagen_principal?.imagen_url || producto.imagen_principal?.imagen

  return (
    <div
      onClick={() => onVerDetalle(producto)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: C.bg, border: `1px solid ${C.border}`,
        borderRadius: '12px', overflow: 'hidden', cursor: 'pointer',
        transition: 'box-shadow 180ms, transform 180ms',
        boxShadow: hovered ? '0 4px 16px rgba(0,0,0,0.09)' : 'none',
        transform: hovered ? 'translateY(-2px)' : 'none',
      }}
    >
      {/* Imagen */}
      <div style={{
        height: '160px', position: 'relative', overflow: 'hidden',
        background: imagenUrl ? 'transparent' : C.bgTer,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {imagenUrl
          ? <img src={imagenUrl} alt={producto.nombre} style={{ width:'100%', height:'100%', objectFit:'cover' }} />
          : <Image size={36} style={{ color: C.border, opacity: 0.6 }} />
        }
        {producto.destacado && (
          <div style={{
            position:'absolute', top:'8px', left:'8px',
            background: C.sidebar, border:`1px solid ${C.gold}`,
            borderRadius:'20px', padding:'2px 8px',
            fontSize:'10px', fontWeight:'500', color: C.gold,
          }}>
            Destacado
          </div>
        )}
        {!producto.visible_showroom && (
          <div style={{
            position:'absolute', top:'8px', right:'8px',
            background:'rgba(0,0,0,0.55)', borderRadius:'6px', padding:'2px 7px',
            fontSize:'9.5px', color:'#fff',
          }}>
            Oculto
          </div>
        )}
      </div>

      {/* Body */}
      <div style={{ padding: '13px 14px 14px' }}>
        <p style={{ fontSize:'11px', color: C.textMuted, marginBottom:'3px' }}>
          {producto.categoria_nombre}
          {producto.marca_nombre && <span> · {producto.marca_nombre}</span>}
        </p>
        <h3 style={{
          fontSize:'13.5px', fontWeight:'500', color: C.text,
          marginBottom:'9px', lineHeight:'1.35',
          display:'-webkit-box', WebkitLineClamp:2,
          WebkitBoxOrient:'vertical', overflow:'hidden',
        }}>
          {producto.nombre}
        </h3>

        <div style={{ display:'flex', alignItems:'flex-end', justifyContent:'space-between', marginBottom:'12px' }}>
          <div>
            <p style={{ fontSize:'16px', fontWeight:'600', color: C.goldDark, lineHeight:1 }}>
              Gs. {Number(producto.precio_base).toLocaleString('es-PY')}
            </p>
            <p style={{ fontSize:'11px', color: C.textMuted, marginTop:'2px' }}>
              por {producto.unidad_venta}
            </p>
          </div>
          <div style={{ textAlign:'right' }}>
            <EstadoStock stock={producto.stock_total} />
            <p style={{ fontSize:'11px', color: C.textMuted, marginTop:'2px' }}>
              {producto.variantes_count} variante{producto.variantes_count !== 1 ? 's' : ''}
            </p>
          </div>
        </div>

        {/* Acciones */}
        <div
          style={{ display:'flex', gap:'6px', borderTop:`1px solid ${C.border}`, paddingTop:'11px' }}
          onClick={e => e.stopPropagation()}
        >
          <button
            onClick={() => onEditar(producto)}
            style={{
              flex:1, display:'flex', alignItems:'center', justifyContent:'center', gap:'4px',
              padding:'7px', fontSize:'12px', cursor:'pointer',
              background:'transparent', border:`1px solid ${C.border}`, borderRadius:'7px',
              color: C.textSec, transition:'all 120ms',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = C.gold; e.currentTarget.style.color = C.goldDark }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.color = C.textSec }}
          >
            <Edit2 size={12} /> Editar
          </button>
          <button
            onClick={() => onVerDetalle(producto)}
            style={{
              flex:1, display:'flex', alignItems:'center', justifyContent:'center', gap:'4px',
              padding:'7px', fontSize:'12px', cursor:'pointer',
              background: C.sidebar, border:`1px solid ${C.gold}`, borderRadius:'7px',
              color: C.gold, transition:'background 120ms',
            }}
            onMouseEnter={e => e.currentTarget.style.background = '#362F31'}
            onMouseLeave={e => e.currentTarget.style.background = C.sidebar}
          >
            <Eye size={12} /> Ver
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Skeleton de carga ────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div style={{
      background: C.bg, border:`1px solid ${C.border}`,
      borderRadius:'12px', overflow:'hidden',
    }}>
      <div style={{ height:'160px', background: C.bgTer, animation:'pulse 1.6s ease-in-out infinite' }} />
      <div style={{ padding:'13px 14px' }}>
        <div style={{ height:'10px', width:'40%', background: C.bgTer, borderRadius:'4px', marginBottom:'8px', animation:'pulse 1.6s ease-in-out infinite' }} />
        <div style={{ height:'14px', width:'85%', background: C.bgTer, borderRadius:'4px', marginBottom:'6px', animation:'pulse 1.6s ease-in-out infinite' }} />
        <div style={{ height:'14px', width:'60%', background: C.bgTer, borderRadius:'4px', animation:'pulse 1.6s ease-in-out infinite' }} />
      </div>
    </div>
  )
}

// ─── Panel lateral ────────────────────────────────────────────────────────────

function PanelLateral({ abierto, onCerrar, hook, productoEdicion }) {
  return (
    <>
      {/* Overlay */}
      {abierto && (
        <div
          onClick={onCerrar}
          style={{
            position:'fixed', inset:0, zIndex:150,
            background:'rgba(26,23,20,0.4)',
            backdropFilter:'blur(2px)',
          }}
        />
      )}

      {/* Panel */}
      <div style={{
        position:'fixed', top:0, right:0, bottom:0, zIndex:151,
        width: abierto ? '600px' : '0',
        maxWidth:'95vw',
        background: C.bg,
        borderLeft:`1px solid ${C.border}`,
        boxShadow: abierto ? '-8px 0 32px rgba(0,0,0,0.12)' : 'none',
        overflow:'hidden',
        transition:'width 220ms ease',
        display:'flex', flexDirection:'column',
      }}>
        {abierto && (
          <ProductoForm
            hook={hook}
            onCancelar={onCerrar}
            productoEdicion={productoEdicion}
          />
        )}
      </div>
    </>
  )
}

// ─── Página principal ─────────────────────────────────────────────────────────

export default function ProductosPage() {
  const [busqueda,       setBusqueda]       = useState('')
  const [categoriaFiltro,setCategoriaFiltro]= useState('')
  const [soloConStock,   setSoloConStock]   = useState(false)
  const [panelAbierto,   setPanelAbierto]   = useState(false)
  const [productoEdicion,setProductoEdicion]= useState(null)
  const [catalogosAbierto, setCatalogosAbierto] = useState(false)

  const hook = useProductoForm({
    onSuccess: () => { setPanelAbierto(false); setProductoEdicion(null) },
  })

  const { data, isLoading } = useQuery({
    queryKey: ['productos', busqueda, categoriaFiltro, soloConStock],
    queryFn: () => productosApi.listar({
      search:     busqueda      || undefined,
      categoria:  categoriaFiltro || undefined,
      con_stock:  soloConStock  || undefined,
    }).then(r => r.data),
    staleTime: 30_000,
  })

  const { data: categorias } = useQuery({
    queryKey: ['categorias'],
    queryFn: () => productosApi.categorias().then(r => r.data?.results || r.data || []),
  })

  const productos = data?.results || []

  const stats = [
    { label: 'Total',     valor: data?.count || 0,                                                    color: C.text    },
    { label: 'Con stock', valor: productos.filter(p => Number(p.stock_total) > 0).length,             color: C.success },
    { label: 'Sin stock', valor: productos.filter(p => Number(p.stock_total) === 0).length,           color: C.danger  },
    { label: 'Destacados',valor: productos.filter(p => p.destacado).length,                           color: C.goldDark},
  ]

  const abrirNuevo = () => {
    hook.resetForm()
    setProductoEdicion(null)
    setPanelAbierto(true)
  }

  const abrirEdicion = (producto) => {
    hook.cargarParaEdicion(producto)
    setProductoEdicion(producto)
    setPanelAbierto(true)
  }

  const cerrarPanel = () => {
    setPanelAbierto(false)
    setProductoEdicion(null)
    hook.resetForm()
  }

  return (
    <Layout
      pageTitle="Productos"
      breadcrumbs={['Productos']}
    >
      {/* ── Barra de acciones ── */}
      <div style={{ display:'flex', gap:'10px', flexWrap:'wrap', alignItems:'center', marginBottom:'20px' }}>
        {/* Búsqueda */}
        <div style={{ position:'relative', flex:1, minWidth:'200px' }}>
          <Search size={15} style={{
            position:'absolute', left:'11px', top:'50%',
            transform:'translateY(-50%)', color: C.textMuted, pointerEvents:'none',
          }} />
          <input
            value={busqueda}
            onChange={e => setBusqueda(e.target.value)}
            placeholder="Buscar por nombre, código o marca..."
            style={{
              width:'100%', padding:'8.5px 12px 8.5px 34px',
              border:`1px solid ${C.border}`, borderRadius:'9px',
              fontSize:'13.5px', color: C.text, background: C.bg,
              outline:'none', transition:'border-color 120ms',
            }}
            onFocus={e => e.target.style.borderColor = C.gold}
            onBlur={e  => e.target.style.borderColor = C.border}
          />
        </div>

        {/* Filtro categoría */}
        <select
          value={categoriaFiltro}
          onChange={e => setCategoriaFiltro(e.target.value)}
          style={{
            padding:'8.5px 12px', border:`1px solid ${C.border}`, borderRadius:'9px',
            fontSize:'13.5px', color: categoriaFiltro ? C.text : C.textMuted,
            background: C.bg, outline:'none', cursor:'pointer',
          }}
        >
          <option value="">Todas las categorías</option>
          {(categorias || []).map(c => (
            <option key={c.id} value={c.id}>{c.nombre}</option>
          ))}
        </select>

        {/* Filtro stock */}
        <button
          onClick={() => setSoloConStock(s => !s)}
          style={{
            display:'flex', alignItems:'center', gap:'6px',
            padding:'8.5px 12px',
            background: soloConStock ? C.sidebar : 'transparent',
            border:`1px solid ${soloConStock ? C.gold : C.border}`,
            borderRadius:'9px', fontSize:'13px', cursor:'pointer',
            color: soloConStock ? C.gold : C.textSec,
            transition:'all 120ms',
          }}
        >
          <SlidersHorizontal size={14} />
          Solo con stock
        </button>

        {/* Gestionar catálogos (marcas, categorías, acabados, tipos) */}
        <button
          onClick={() => setCatalogosAbierto(true)}
          style={{
            display:'flex', alignItems:'center', gap:'6px',
            padding:'8.5px 16px', background: C.bg,
            border:`1px solid ${C.border}`, borderRadius:'9px',
            color: C.textSec, fontSize:'13.5px', fontWeight:'500',
            cursor:'pointer', whiteSpace:'nowrap', transition:'border-color 120ms',
          }}
          onMouseEnter={e => e.currentTarget.style.borderColor = C.gold}
          onMouseLeave={e => e.currentTarget.style.borderColor = C.border}
        >
          <Layers size={15} /> Gestionar catálogos
        </button>

        {/* Nuevo producto */}
        <button
          onClick={abrirNuevo}
          style={{
            display:'flex', alignItems:'center', gap:'6px',
            padding:'8.5px 18px', background: C.sidebar,
            border:`1px solid ${C.gold}`, borderRadius:'9px',
            color: C.gold, fontSize:'13.5px', fontWeight:'500',
            cursor:'pointer', whiteSpace:'nowrap', transition:'background 120ms',
          }}
          onMouseEnter={e => e.currentTarget.style.background = '#362F31'}
          onMouseLeave={e => e.currentTarget.style.background = C.sidebar}
        >
          <Plus size={15} /> Nuevo producto
        </button>
      </div>

      {/* ── Stats ── */}
      <div style={{
        display:'grid', gridTemplateColumns:'repeat(4,1fr)',
        gap:'10px', marginBottom:'20px',
      }}>
        {stats.map(s => (
          <div key={s.label} style={{
            background: C.bg, border:`1px solid ${C.border}`,
            borderRadius:'10px', padding:'13px 15px',
          }}>
            <p style={{ fontSize:'10.5px', color: C.textMuted, fontWeight:'500',
              letterSpacing:'0.05em', textTransform:'uppercase', marginBottom:'5px' }}>
              {s.label}
            </p>
            <p style={{ fontSize:'22px', fontWeight:'600', color: s.color }}>
              {s.valor}
            </p>
          </div>
        ))}
      </div>

      {/* ── Grid ── */}
      {isLoading ? (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(230px,1fr))', gap:'14px' }}>
          {Array.from({ length: 8 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : productos.length === 0 ? (
        <div style={{ textAlign:'center', padding:'60px 20px', color: C.textMuted }}>
          <Package size={48} style={{ margin:'0 auto 14px', opacity:0.25 }} />
          <p style={{ fontSize:'16px', fontWeight:'500', color: C.textSec }}>
            {busqueda || categoriaFiltro ? 'Sin resultados' : 'No hay productos todavía'}
          </p>
          <p style={{ fontSize:'13.5px', marginTop:'4px' }}>
            {busqueda ? 'Probá con otro término' : 'Hacé clic en "Nuevo producto" para empezar'}
          </p>
          {!busqueda && !categoriaFiltro && (
            <button
              onClick={abrirNuevo}
              style={{
                marginTop:'18px', display:'inline-flex', alignItems:'center', gap:'7px',
                padding:'9px 20px', background: C.sidebar,
                border:`1px solid ${C.gold}`, borderRadius:'9px',
                color: C.gold, fontSize:'13.5px', cursor:'pointer',
              }}
            >
              <Plus size={15} /> Crear primer producto
            </button>
          )}
        </div>
      ) : (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(230px,1fr))', gap:'14px' }}>
          {productos.map(p => (
            <ProductoCard
              key={p.id}
              producto={p}
              onEditar={abrirEdicion}
              onVerDetalle={abrirEdicion}
            />
          ))}
        </div>
      )}

      {/* ── Panel lateral formulario ── */}
      <PanelLateral
        abierto={panelAbierto}
        onCerrar={cerrarPanel}
        hook={hook}
        productoEdicion={productoEdicion}
      />

      {/* ── Modal de gestión de catálogos ── */}
      {catalogosAbierto && (
        <GestionCatalogos onCerrar={() => setCatalogosAbierto(false)} />
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.45; }
        }
      `}</style>
    </Layout>
  )
}
