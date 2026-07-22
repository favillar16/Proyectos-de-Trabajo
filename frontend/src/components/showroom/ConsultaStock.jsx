/**
 * ConsultaStock
 * Widget de búsqueda rápida de stock para el showroom.
 *
 * Casos de uso:
 * 1. Vendedor en showroom busca "POR-001" → ve stock de todas sus variantes
 * 2. Cliente pregunta por "porcelanato gris 60x60" → búsqueda por nombre
 * 3. Vendedor escanea código → resultado inmediato
 *
 * Modos:
 * - Inline: se embebe en el showroom como panel lateral
 * - Modal: se abre desde un botón flotante (útil en tablets)
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Search, X, Package, CheckCircle, AlertCircle,
  XCircle, RefreshCw, Warehouse, ChevronRight,
  ScanLine, Info,
} from 'lucide-react'
import { inventarioApi } from '../../services/api'
import { useDevice } from '../../hooks/useDevice'

const C = {
  sidebar:    '#453941', sidebarHov:'#362F31',
  gold:       '#B99C74', goldDark:'#8a7355', goldMuted:'rgba(185,156,116,0.10)',
  border:     '#e8e4df', borderStrong:'#d0cbc4',
  bg:         '#ffffff', bgSec:'#fafaf9', bgTer:'#f5f4f2',
  text:       '#1a1714', textSec:'#6b6560', textMuted:'#9e9892',
  success:    '#3d7a5a', successBg:'#edf7f1', successBorder:'#b8deca',
  warning:    '#8a6a1a', warningBg:'#fef9ee', warningBorder:'#f0d98a',
  danger:     '#9a3030', dangerBg:'#fef0f0',  dangerBorder:'#f0b8b8',
}

function useDebounce(value, delay = 400) {
  const [d, setD] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setD(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return d
}

function formatGs(v) {
  return `Gs. ${Number(v).toLocaleString('es-PY')}`
}

// ─── Badge de estado ──────────────────────────────────────────────────────────
function EstadoBadge({ estado, disponible, grande = false }) {
  const cfg = {
    disponible: {
      bg: C.successBg, color: C.success,
      border: C.successBorder,
      icon: <CheckCircle size={grande ? 14 : 11} />,
      label: `${Number(disponible).toFixed(2)} disponible`,
    },
    critico: {
      bg: C.warningBg, color: C.warning,
      border: C.warningBorder,
      icon: <AlertCircle size={grande ? 14 : 11} />,
      label: `${Number(disponible).toFixed(2)} — stock bajo`,
    },
    sin_stock: {
      bg: C.dangerBg, color: C.danger,
      border: C.dangerBorder,
      icon: <XCircle size={grande ? 14 : 11} />,
      label: 'Sin stock',
    },
  }
  const s = cfg[estado] || cfg.sin_stock
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      padding: grande ? '5px 11px' : '3px 8px',
      borderRadius: '20px',
      background: s.bg, color: s.color,
      border: `1px solid ${s.border}`,
      fontSize: grande ? '13px' : '11px', fontWeight: '500',
      whiteSpace: 'nowrap',
    }}>
      {s.icon} {s.label}
    </span>
  )
}

// ─── Fila de resultado ────────────────────────────────────────────────────────
function FilaResultado({ item, onSeleccionar, isTouch }) {
  const [presionado, setPres] = useState(false)
  const tieneImagen = Boolean(item.imagen_url)

  return (
    <div
      onClick={() => onSeleccionar?.(item)}
      onTouchStart={() => setPres(true)}
      onTouchEnd={() => setTimeout(() => setPres(false), 120)}
      style={{
        display: 'flex', alignItems: 'center', gap: '12px',
        padding: '12px 16px',
        minHeight: isTouch ? '64px' : '56px',
        background: presionado ? C.bgSec : C.bg,
        borderBottom: `1px solid ${C.border}`,
        cursor: onSeleccionar ? 'pointer' : 'default',
        transition: 'background 100ms',
        WebkitTapHighlightColor: 'transparent',
      }}
    >
      {/* Miniatura */}
      <div style={{
        width: '48px', height: '48px', flexShrink: 0,
        borderRadius: '9px', overflow: 'hidden',
        background: C.bgTer,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        border: `1px solid ${C.border}`,
      }}>
        {tieneImagen
          ? <img src={item.imagen_url} alt=""
              style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          : <Package size={18} style={{ color: C.border, opacity: 0.5 }} />
        }
      </div>

      {/* Info principal */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '2px' }}>
          <p style={{ fontSize: '11px', color: C.textMuted, fontFamily: 'monospace' }}>
            {item.sku}
          </p>
          {item.ubicacion && (
            <span style={{
              fontSize: '10px', color: C.textSec,
              background: C.bgTer, border: `1px solid ${C.border}`,
              padding: '1px 6px', borderRadius: '4px',
            }}>
              <Warehouse size={8} style={{ display: 'inline', marginRight: '2px' }} />
              {item.ubicacion}
            </span>
          )}
        </div>
        <p style={{
          fontSize: '14px', fontWeight: '500', color: C.text,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          marginBottom: '3px',
        }}>
          {item.descripcion}
        </p>
        <p style={{ fontSize: '12px', color: C.goldDark, fontWeight: '500' }}>
          {formatGs(item.precio_venta)}
          <span style={{ color: C.textMuted, fontWeight: '400' }}> / {item.unidad_venta}</span>
        </p>
      </div>

      {/* Estado de stock */}
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <EstadoBadge estado={item.estado} disponible={item.disponible} />
        {Number(item.cantidad_reservada) > 0 && (
          <p style={{ fontSize: '10px', color: C.textMuted, marginTop: '3px' }}>
            {Number(item.cantidad_reservada).toFixed(2)} reservado
          </p>
        )}
      </div>

      {onSeleccionar && (
        <ChevronRight size={16} style={{ color: C.textMuted, flexShrink: 0 }} />
      )}
    </div>
  )
}

// ─── Resumen de un producto con todas sus variantes ───────────────────────────
function ResumenProducto({ resultados }) {
  // Agrupar por producto
  const porProducto = {}
  resultados.forEach(r => {
    if (!porProducto[r.producto_id]) {
      porProducto[r.producto_id] = {
        id:     r.producto_id,
        codigo: r.producto_codigo,
        nombre: r.producto_nombre,
        items:  [],
      }
    }
    porProducto[r.producto_id].items.push(r)
  })

  return (
    <div>
      {Object.values(porProducto).map(prod => {
        const totalDisp = prod.items.reduce((s, i) => s + Number(i.disponible), 0)
        const conStock  = prod.items.filter(i => i.estado !== 'sin_stock').length
        const total     = prod.items.length

        return (
          <div key={prod.id} style={{ marginBottom: '1px' }}>
            {/* Cabecera del producto */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '10px 16px',
              background: C.bgSec,
              borderBottom: `1px solid ${C.border}`,
              borderTop: `1px solid ${C.border}`,
            }}>
              <div>
                <span style={{ fontSize: '11px', color: C.textMuted, fontFamily: 'monospace' }}>
                  {prod.codigo}
                </span>
                <p style={{ fontSize: '14px', fontWeight: '500', color: C.text }}>
                  {prod.nombre}
                </p>
              </div>
              <div style={{ textAlign: 'right' }}>
                <p style={{ fontSize: '13px', fontWeight: '600', color: C.goldDark }}>
                  {totalDisp.toFixed(2)} total
                </p>
                <p style={{ fontSize: '11px', color: C.textMuted }}>
                  {conStock}/{total} variantes con stock
                </p>
              </div>
            </div>

            {/* Variantes */}
            {prod.items.map((item, i) => (
              <FilaResultado key={i} item={item} isTouch={false} />
            ))}
          </div>
        )
      })}
    </div>
  )
}

// ─── Panel de detalle de un ítem seleccionado ─────────────────────────────────
function DetalleItem({ item, onVolver }) {
  if (!item) return null
  return (
    <div style={{ padding: '16px' }}>
      <button
        onClick={onVolver}
        style={{
          display: 'flex', alignItems: 'center', gap: '5px',
          background: 'transparent', border: 'none', cursor: 'pointer',
          color: C.textSec, fontSize: '13px', padding: '4px 0',
          marginBottom: '14px',
        }}
      >
        <ChevronRight size={14} style={{ transform: 'rotate(180deg)' }} />
        Volver a resultados
      </button>

      {/* Imagen */}
      {item.imagen_url && (
        <div style={{
          height: '180px', borderRadius: '12px', overflow: 'hidden',
          marginBottom: '16px', background: C.bgTer,
        }}>
          <img src={item.imagen_url} alt={item.descripcion}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        </div>
      )}

      {/* Datos del ítem */}
      <p style={{ fontSize: '11px', color: C.textMuted, fontFamily: 'monospace', marginBottom: '4px' }}>
        {item.producto_codigo} · SKU: {item.sku}
      </p>
      <h3 style={{ fontSize: '17px', fontWeight: '500', color: C.text,
        fontFamily: 'var(--font-display)', marginBottom: '4px', lineHeight: 1.3 }}>
        {item.descripcion}
      </h3>
      <p style={{ fontSize: '20px', fontWeight: '600', color: C.goldDark, marginBottom: '16px' }}>
        {formatGs(item.precio_venta)}
        <span style={{ fontSize: '13px', color: C.textMuted, fontWeight: '400' }}>
          {' '}/{item.unidad_venta}
        </span>
      </p>

      {/* Stock detallado */}
      <div style={{
        background: C.bgSec, border: `1px solid ${C.border}`,
        borderRadius: '12px', overflow: 'hidden', marginBottom: '14px',
      }}>
        {[
          { label: 'Disponible',  valor: item.disponible,         color: C.success,  bold: true },
          { label: 'En depósito', valor: item.cantidad,           color: C.text      },
          { label: 'Reservado',   valor: item.cantidad_reservada, color: C.warning   },
          { label: 'Mínimo',      valor: item.stock_minimo,       color: C.textMuted },
        ].map(({ label, valor, color, bold }) => (
          <div key={label} style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '11px 16px', borderBottom: `1px solid ${C.border}`,
          }}>
            <span style={{ fontSize: '13.5px', color: C.textSec }}>{label}</span>
            <span style={{ fontSize: '15px', fontWeight: bold ? '600' : '500', color }}>
              {Number(valor).toFixed(2)}
            </span>
          </div>
        ))}
        <div style={{ padding: '11px 16px' }}>
          <span style={{ fontSize: '13.5px', color: C.textSec }}>Estado</span>
          <div style={{ marginTop: '6px' }}>
            <EstadoBadge estado={item.estado} disponible={item.disponible} grande />
          </div>
        </div>
      </div>

      {/* Ubicación */}
      {item.ubicacion && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '8px',
          padding: '12px 16px',
          background: C.goldMuted,
          border: `1px solid ${C.border}`,
          borderRadius: '10px', marginBottom: '14px',
        }}>
          <Warehouse size={18} style={{ color: C.goldDark, flexShrink: 0 }} />
          <div>
            <p style={{ fontSize: '11px', color: C.textMuted, marginBottom: '1px' }}>Ubicación en depósito</p>
            <p style={{ fontSize: '14px', fontWeight: '500', color: C.text }}>{item.ubicacion}</p>
          </div>
        </div>
      )}

      {/* Última actualización */}
      <p style={{ fontSize: '11px', color: C.textMuted, textAlign: 'center' }}>
        Actualizado: {new Date(item.fecha_actualizacion).toLocaleString('es-PY', {
          day: '2-digit', month: '2-digit', year: 'numeric',
          hour: '2-digit', minute: '2-digit',
        })}
      </p>
    </div>
  )
}

// ─── Widget principal exportado ───────────────────────────────────────────────
/**
 * Props:
 *   modo          'inline' | 'modal'   Cómo se integra en la página
 *   abierto       boolean              Controla visibilidad (modo modal)
 *   onCerrar      () => void           Callback al cerrar (modo modal)
 *   onAgregarPedido (item) => void     Callback al seleccionar un ítem para pedido
 */
export default function ConsultaStock({
  modo          = 'inline',
  abierto       = true,
  onCerrar,
  onAgregarPedido,
}) {
  const [query,          setQuery]          = useState('')
  const [itemSeleccionado, setItemSeleccionado] = useState(null)
  const inputRef = useRef(null)
  const device   = useDevice()
  const dQuery   = useDebounce(query, 400)

  // Foco automático al abrir
  useEffect(() => {
    if (abierto) {
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [abierto])

  // Limpiar al cerrar
  useEffect(() => {
    if (!abierto) {
      setQuery('')
      setItemSeleccionado(null)
    }
  }, [abierto])

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['stock-consulta', dQuery],
    queryFn:  () => inventarioApi.consultaRapida(dQuery).then(r => r.data),
    enabled:  dQuery.length >= 2,
    staleTime: 8_000,
  })

  const resultados  = data?.resultados || []
  const hayResultados = resultados.length > 0
  const sinResultados = dQuery.length >= 2 && !isLoading && resultados.length === 0

  const limpiar = useCallback(() => {
    setQuery('')
    setItemSeleccionado(null)
    inputRef.current?.focus()
  }, [])

  if (!abierto && modo === 'modal') return null

  const contenido = (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100%',
    }}>
      {/* ── Header ── */}
      <div style={{
        padding: '16px 16px 12px',
        borderBottom: `1px solid ${C.border}`,
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginBottom: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{
              width: '30px', height: '30px', borderRadius: '8px',
              background: C.sidebar,
              border: `1px solid ${C.gold}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <ScanLine size={16} style={{ color: C.gold }} />
            </div>
            <div>
              <p style={{ fontSize: '14px', fontWeight: '500', color: C.text }}>
                Consulta de stock
              </p>
              <p style={{ fontSize: '11px', color: C.textMuted }}>
                Buscá por código, SKU o nombre
              </p>
            </div>
          </div>
          {modo === 'modal' && onCerrar && (
            <button onClick={onCerrar} style={{ background: 'transparent', border: 'none',
              cursor: 'pointer', color: C.textMuted, padding: '6px',
              display: 'flex', alignItems: 'center',
              width: '36px', height: '36px', justifyContent: 'center', borderRadius: '8px',
              WebkitTapHighlightColor: 'transparent' }}>
              <X size={20} />
            </button>
          )}
        </div>

        {/* Campo de búsqueda */}
        <div style={{ position: 'relative' }}>
          <Search size={16} style={{
            position: 'absolute', left: '12px', top: '50%',
            transform: 'translateY(-50%)', color: C.textMuted, pointerEvents: 'none',
          }} />
          <input
            ref={inputRef}
            value={query}
            onChange={e => { setQuery(e.target.value); setItemSeleccionado(null) }}
            placeholder="Ej: POR-001 · 60x60 · gris..."
            autoComplete="off"
            autoCorrect="off"
            spellCheck={false}
            style={{
              width: '100%',
              height: device.isTouch ? '48px' : '40px',
              padding: '0 40px 0 38px',
              border: `1px solid ${query.length >= 2 ? C.gold : C.border}`,
              borderRadius: '10px', fontSize: '15px',
              color: C.text, background: C.bg, outline: 'none',
              transition: 'border-color 150ms',
            }}
          />
          {/* Spinner o limpiar */}
          <div style={{
            position: 'absolute', right: '10px', top: '50%',
            transform: 'translateY(-50%)',
          }}>
            {isFetching ? (
              <div style={{ width: '16px', height: '16px', borderRadius: '50%',
                border: `2px solid ${C.border}`, borderTopColor: C.gold,
                animation: 'spin 0.8s linear infinite' }} />
            ) : query ? (
              <button onClick={limpiar} style={{ background: 'transparent', border: 'none',
                cursor: 'pointer', color: C.textMuted,
                display: 'flex', alignItems: 'center', padding: '4px',
                WebkitTapHighlightColor: 'transparent' }}>
                <X size={15} />
              </button>
            ) : null}
          </div>
        </div>

        {/* Ayuda rápida */}
        {!query && (
          <div style={{ marginTop: '10px', display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
            {['POR', 'CER', 'SAN'].map(tip => (
              <button
                key={tip}
                onClick={() => setQuery(tip)}
                style={{
                  padding: '4px 10px', borderRadius: '6px',
                  background: C.bgTer, border: `1px solid ${C.border}`,
                  fontSize: '12px', color: C.textSec, cursor: 'pointer',
                  WebkitTapHighlightColor: 'transparent',
                }}
              >
                {tip}…
              </button>
            ))}
            <span style={{ fontSize: '11px', color: C.textMuted, alignSelf: 'center' }}>
              Sugerencias rápidas
            </span>
          </div>
        )}
      </div>

      {/* ── Contenido ── */}
      <div style={{ flex: 1, overflowY: 'auto', WebkitOverflowScrolling: 'touch' }}>

        {/* Detalle de ítem seleccionado */}
        {itemSeleccionado ? (
          <DetalleItem
            item={itemSeleccionado}
            onVolver={() => setItemSeleccionado(null)}
          />
        ) : (

          /* Resultados */
          <>
            {/* Estado: cargando primera vez */}
            {isLoading && (
              <div style={{ padding: '40px 20px', textAlign: 'center' }}>
                <div style={{ width: '28px', height: '28px', borderRadius: '50%',
                  border: `3px solid ${C.border}`, borderTopColor: C.gold,
                  animation: 'spin 0.8s linear infinite', margin: '0 auto 12px' }} />
                <p style={{ fontSize: '13.5px', color: C.textMuted }}>Buscando...</p>
              </div>
            )}

            {/* Sin resultados */}
            {sinResultados && (
              <div style={{ padding: '40px 20px', textAlign: 'center', color: C.textMuted }}>
                <Package size={36} style={{ margin: '0 auto 12px', opacity: 0.25 }} />
                <p style={{ fontSize: '15px', fontWeight: '500', color: C.textSec }}>
                  Sin resultados
                </p>
                <p style={{ fontSize: '13px', marginTop: '4px' }}>
                  No hay stock registrado para <strong>"{dQuery}"</strong>
                </p>
                <button onClick={limpiar}
                  style={{ marginTop: '14px', display: 'inline-flex', alignItems: 'center', gap: '5px',
                    padding: '8px 16px', background: 'transparent',
                    border: `1px solid ${C.border}`, borderRadius: '8px',
                    color: C.textSec, fontSize: '13px', cursor: 'pointer',
                    WebkitTapHighlightColor: 'transparent' }}>
                  <X size={13} /> Limpiar búsqueda
                </button>
              </div>
            )}

            {/* Estado vacío inicial */}
            {!query && (
              <div style={{ padding: '32px 20px', textAlign: 'center', color: C.textMuted }}>
                <ScanLine size={40} style={{ margin: '0 auto 12px', opacity: 0.2 }} />
                <p style={{ fontSize: '14px', fontWeight: '500', color: C.textSec }}>
                  Consulta rápida de stock
                </p>
                <p style={{ fontSize: '13px', marginTop: '4px', lineHeight: 1.6 }}>
                  Escribí el código de producto,<br />
                  SKU de variante o nombre.
                </p>
              </div>
            )}

            {/* Resultados */}
            {hayResultados && !isLoading && (
              <>
                {/* Cabecera de resultados */}
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '10px 16px',
                  background: C.bgSec, borderBottom: `1px solid ${C.border}`,
                }}>
                  <p style={{ fontSize: '12px', color: C.textMuted }}>
                    {data.total} resultado{data.total !== 1 ? 's' : ''} para{' '}
                    <strong style={{ color: C.text }}>"{data.query}"</strong>
                  </p>
                  <button
                    onClick={() => refetch()}
                    style={{ background: 'transparent', border: 'none', cursor: 'pointer',
                      color: C.textMuted, display: 'flex', alignItems: 'center', gap: '4px',
                      fontSize: '11px', padding: '4px',
                      WebkitTapHighlightColor: 'transparent' }}
                  >
                    <RefreshCw size={12} /> Actualizar
                  </button>
                </div>

                {/* Lista agrupada por producto */}
                <ResumenProducto
                  resultados={resultados}
                />

                {/* Acción de pedido si hay callback */}
                {onAgregarPedido && resultados.some(r => r.estado !== 'sin_stock') && (
                  <div style={{ padding: '14px 16px', borderTop: `1px solid ${C.border}` }}>
                    <p style={{ fontSize: '12px', color: C.textMuted, marginBottom: '8px',
                      display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Info size={12} /> Tocá una variante para ver el detalle y agregar al pedido
                    </p>
                  </div>
                )}
              </>
            )}
          </>
        )}

        {/* Detalle + botón pedido */}
        {itemSeleccionado && onAgregarPedido && itemSeleccionado.estado !== 'sin_stock' && (
          <div style={{ padding: '0 16px 16px' }}>
            <button
              onClick={() => onAgregarPedido(itemSeleccionado)}
              style={{
                width: '100%',
                height: device.isTouch ? '52px' : '44px',
                borderRadius: '10px',
                background: C.sidebar, border: `1px solid ${C.gold}`,
                color: C.gold, fontSize: '14px', fontWeight: '500', cursor: 'pointer',
                transition: 'background 120ms',
                WebkitTapHighlightColor: 'transparent',
              }}
              onMouseEnter={e => e.currentTarget.style.background = C.sidebarHov}
              onMouseLeave={e => e.currentTarget.style.background = C.sidebar}
            >
              Agregar a nota de pedido
            </button>
          </div>
        )}
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )

  // ── Modo modal ────────────────────────────────────────────────────────────
  if (modo === 'modal') {
    return (
      <>
        {/* Overlay */}
        <div onClick={onCerrar} style={{
          position: 'fixed', inset: 0, zIndex: 300,
          background: 'rgba(26,23,20,0.45)', backdropFilter: 'blur(3px)',
        }} />

        {/* Panel */}
        <div style={{
          position: 'fixed', zIndex: 301,
          top: 0, right: 0, bottom: 0,
          width: 'min(420px, 95vw)',
          background: C.bg,
          borderLeft: `1px solid ${C.border}`,
          boxShadow: '-10px 0 40px rgba(0,0,0,0.15)',
          display: 'flex', flexDirection: 'column',
          animation: 'slideIn 200ms ease',
        }}>
          {contenido}
        </div>

        <style>{`
          @keyframes slideIn {
            from { transform: translateX(100%); }
            to   { transform: translateX(0); }
          }
        `}</style>
      </>
    )
  }

  // ── Modo inline ───────────────────────────────────────────────────────────
  return (
    <div style={{
      background: C.bg,
      border: `1px solid ${C.border}`,
      borderRadius: '14px',
      overflow: 'hidden',
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {contenido}
    </div>
  )
}
