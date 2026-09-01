/**
 * NuevoPedidoForm — versión mejorada (UX)
 * El vendedor arma la nota de pedido en un flujo más claro:
 *  - Buscador grande y siempre visible arriba
 *  - Resultados táctiles, con feedback al agregar
 *  - Carrito con controles de cantidad grandes + atajos (+5/+10/caja)
 *  - Datos del cliente colapsables (no bloquean agregar productos)
 *  - Resumen y botón de envío siempre visibles abajo
 */
import { useState, useRef, useCallback, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Search, Plus, Minus, Trash2, ChevronDown, ChevronUp,
  User, FileText, Loader2, CheckCircle, Package,
  X, ShoppingCart, PackagePlus,
} from 'lucide-react'
import { ventasApi, productosApi } from '../../services/api'
import { useDevice } from '../../hooks/useDevice'
import { useAuthStore } from '../../store/authStore'
import { mensajeErrorApi } from '../../utils/apiErrors'
import toast from 'react-hot-toast'

const C = {
  sidebar:'#453941', sidebarHov:'#362F31',
  gold:'#B99C74', goldDark:'#8a7355', goldLight:'#d4bc98', goldMuted:'rgba(185,156,116,0.10)',
  border:'#e8e4df', bg:'#ffffff', bgSec:'#fafaf9', bgTer:'#f5f4f2',
  text:'#1a1714', textSec:'#6b6560', textMuted:'#9e9892',
  success:'#3d7a5a', successBg:'#edf7f1', successBorder:'#b8deca',
  danger:'#9a3030', dangerBg:'#fef0f0',
}

function formatGs(v) { return `Gs. ${Number(v || 0).toLocaleString('es-PY')}` }

function useDebounce(v, d=300) {
  const [dv,setDv]=useState(v)
  useEffect(()=>{ const t=setTimeout(()=>setDv(v),d); return()=>clearTimeout(t) },[v,d])
  return dv
}

// ─── Buscador de cliente del padrón (con RUC) ─────────────────────────────────
function BuscadorCliente({ clienteSel, onSeleccionar, onLimpiar }) {
  const [q, setQ] = useState('')
  const [abierto, setAbierto] = useState(false)
  const [creando, setCreando] = useState(false)
  const [nuevo, setNuevo] = useState({ razon_social:'', ruc:'', telefono:'' })
  const dq = useDebounce(q, 300)
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['clientes-buscar', dq],
    queryFn: () => ventasApi.clientes(dq).then(r => r.data),
    enabled: abierto && dq.length >= 2,
  })
  const clientes = data?.results || []

  const crearMut = useMutation({
    mutationFn: () => ventasApi.crearCliente(nuevo).then(r => r.data),
    onSuccess: (cli) => {
      queryClient.invalidateQueries({ queryKey: ['clientes-buscar'] })
      toast.success('Cliente guardado en el padrón')
      onSeleccionar(cli)
      setCreando(false); setAbierto(false); setQ('')
      setNuevo({ razon_social:'', ruc:'', telefono:'' })
    },
    onError: () => toast.error('No se pudo guardar el cliente'),
  })

  // Si ya hay un cliente del padrón seleccionado, mostrar la tarjeta
  if (clienteSel) {
    return (
      <div style={{ marginBottom:'12px', padding:'10px 12px', borderRadius:'10px',
        background:C.goldMuted, border:`1px solid ${C.gold}`,
        display:'flex', alignItems:'center', gap:'10px' }}>
        <User size={16} style={{ color:C.goldDark, flexShrink:0 }} />
        <div style={{ flex:1, minWidth:0 }}>
          <p style={{ fontSize:'13px', fontWeight:'500', color:C.text }}>
            {clienteSel.razon_social}
          </p>
          {clienteSel.ruc && (
            <p style={{ fontSize:'11.5px', color:C.goldDark }}>RUC: {clienteSel.ruc}</p>
          )}
        </div>
        <button onClick={onLimpiar}
          style={{ background:'transparent', border:'none', cursor:'pointer',
            color:C.textMuted, padding:'4px', display:'flex', flexShrink:0 }}
          title="Quitar cliente del padrón">
          <X size={16} />
        </button>
      </div>
    )
  }

  return (
    <div style={{ marginBottom:'12px' }}>
      {!abierto ? (
        <button onClick={() => setAbierto(true)}
          style={{ width:'100%', height:'40px', borderRadius:'8px', cursor:'pointer',
            background:C.bgSec, border:`1px dashed ${C.border}`, color:C.textSec,
            fontSize:'13px', display:'flex', alignItems:'center', justifyContent:'center', gap:'7px' }}>
          <Search size={14} /> Buscar cliente del padrón (con RUC)
        </button>
      ) : creando ? (
        <div style={{ padding:'12px', borderRadius:'10px', border:`1px solid ${C.gold}`,
          background:C.bgSec }}>
          <p style={{ fontSize:'12px', fontWeight:'500', color:C.textSec, marginBottom:'8px' }}>
            Nuevo cliente
          </p>
          {[
            { k:'razon_social', ph:'Nombre o razón social *' },
            { k:'ruc',          ph:'RUC / CI' },
            { k:'telefono',     ph:'Teléfono' },
          ].map(f => (
            <input key={f.k} value={nuevo[f.k]}
              onChange={e => setNuevo(n => ({ ...n, [f.k]: e.target.value }))}
              placeholder={f.ph}
              style={{ width:'100%', height:'38px', padding:'0 10px', marginBottom:'7px',
                border:`1px solid ${C.border}`, borderRadius:'7px',
                fontSize:'13.5px', color:C.text, background:C.bg, outline:'none' }} />
          ))}
          <div style={{ display:'flex', gap:'8px', marginTop:'2px' }}>
            <button onClick={() => { setCreando(false) }}
              style={{ flex:1, height:'38px', borderRadius:'7px', cursor:'pointer',
                background:'transparent', border:`1px solid ${C.border}`,
                color:C.textSec, fontSize:'13px' }}>
              Cancelar
            </button>
            <button
              disabled={!nuevo.razon_social.trim() || crearMut.isPending}
              onClick={() => crearMut.mutate()}
              style={{ flex:1, height:'38px', borderRadius:'7px',
                cursor: nuevo.razon_social.trim() ? 'pointer' : 'not-allowed',
                background: nuevo.razon_social.trim() ? C.sidebar : C.bgTer,
                border:`1px solid ${nuevo.razon_social.trim() ? C.gold : C.border}`,
                color: nuevo.razon_social.trim() ? C.gold : C.textMuted,
                fontSize:'13px', fontWeight:'500' }}>
              {crearMut.isPending ? 'Guardando...' : 'Guardar'}
            </button>
          </div>
        </div>
      ) : (
        <div>
          <div style={{ position:'relative' }}>
            <Search size={15} style={{ position:'absolute', left:'11px', top:'50%',
              transform:'translateY(-50%)', color:C.gold, pointerEvents:'none' }} />
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder="Nombre o RUC del cliente..."
              autoFocus
              style={{ width:'100%', height:'42px', padding:'0 70px 0 36px',
                border:`1.5px solid ${C.gold}`, borderRadius:'9px',
                fontSize:'14px', color:C.text, background:C.bg, outline:'none' }}
            />
            <button onClick={() => { setAbierto(false); setQ('') }}
              style={{ position:'absolute', right:'8px', top:'50%', transform:'translateY(-50%)',
                background:C.bgTer, border:'none', cursor:'pointer', color:C.textSec,
                borderRadius:'6px', padding:'4px 8px', fontSize:'11px' }}>
              Cerrar
            </button>
          </div>

          {dq.length >= 2 && (
            <div style={{ marginTop:'6px', maxHeight:'200px', overflowY:'auto' }}>
              {isLoading ? (
                <p style={{ fontSize:'12px', color:C.textMuted, padding:'10px', textAlign:'center' }}>
                  Buscando...
                </p>
              ) : clientes.length === 0 ? (
                <div style={{ padding:'10px', textAlign:'center' }}>
                  <p style={{ fontSize:'12.5px', color:C.textMuted, marginBottom:'8px' }}>
                    Sin resultados para "{dq}"
                  </p>
                  <button
                    onClick={() => { setNuevo(n => ({ ...n, razon_social: q })); setCreando(true) }}
                    style={{ fontSize:'12.5px', color:C.goldDark, background:'transparent',
                      border:'none', cursor:'pointer', textDecoration:'underline' }}>
                    + Agregar "{q}" al padrón
                  </button>
                </div>
              ) : (
                <div style={{ display:'flex', flexDirection:'column', gap:'4px' }}>
                  {clientes.map(c => (
                    <button key={c.id}
                      onClick={() => { onSeleccionar(c); setAbierto(false); setQ('') }}
                      style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
                        gap:'10px', padding:'9px 11px', borderRadius:'8px', cursor:'pointer',
                        background:C.bg, border:`1px solid ${C.border}`, textAlign:'left' }}>
                      <div style={{ minWidth:0 }}>
                        <p style={{ fontSize:'13px', fontWeight:'500', color:C.text }}>
                          {c.razon_social}
                        </p>
                        {c.ruc && <p style={{ fontSize:'11px', color:C.textMuted }}>RUC: {c.ruc}</p>}
                      </div>
                      {c.permite_ajuste_precio && (
                        <span style={{ fontSize:'10px', color:C.goldDark, background:C.goldMuted,
                          padding:'2px 6px', borderRadius:'4px', flexShrink:0 }}>
                          precio negociable
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          {dq.length > 0 && dq.length < 2 && (
            <p style={{ fontSize:'11.5px', color:C.textMuted, marginTop:'6px', textAlign:'center' }}>
              Escribí al menos 2 caracteres
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Buscador de variantes (grande, persistente) ──────────────────────────────
function BuscadorVariante({ onAgregar, idsEnCarrito }) {
  const [q, setQ] = useState('')
  const dq = useDebounce(q, 300)
  const ref = useRef()

  const { data, isLoading } = useQuery({
    queryKey: ['buscar-variantes', dq],
    queryFn: () => productosApi.showroom({ search: dq, page_size: 10 }).then(r => r.data),
    enabled: dq.length >= 2,
  })

  const productos = (data?.results || []).filter(p => p.variantes_count > 0)

  return (
    <div>
      <div style={{ position:'relative' }}>
        <Search size={17} style={{ position:'absolute', left:'13px', top:'50%',
          transform:'translateY(-50%)', color:C.gold, pointerEvents:'none' }} />
        <input
          ref={ref}
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder="Buscá por código, SKU o nombre..."
          autoFocus
          style={{
            width:'100%', height:'48px', padding:'0 40px 0 42px',
            border:`1.5px solid ${q ? C.gold : C.border}`, borderRadius:'11px',
            fontSize:'15px', color:C.text, background:C.bg, outline:'none',
            transition:'border-color 120ms',
          }}
          onFocus={e => e.target.style.borderColor = C.gold}
          onBlur={e => e.target.style.borderColor = q ? C.gold : C.border}
        />
        {q && <button onClick={()=>{setQ(''); ref.current?.focus()}} style={{ position:'absolute',
          right:'12px', top:'50%', transform:'translateY(-50%)',
          background:C.bgTer, border:'none', cursor:'pointer', color:C.textSec,
          borderRadius:'6px', width:'24px', height:'24px',
          display:'flex', alignItems:'center', justifyContent:'center' }}><X size={14}/></button>}
      </div>

      {/* Resultados */}
      {dq.length >= 2 && (
        <div style={{ marginTop:'10px' }}>
          {isLoading ? (
            <div style={{ padding:'20px', textAlign:'center', color:C.textMuted, fontSize:'13px' }}>
              Buscando...
            </div>
          ) : productos.length === 0 ? (
            <div style={{ padding:'20px', textAlign:'center', color:C.textMuted, fontSize:'13px' }}>
              Sin resultados para "{dq}"
            </div>
          ) : (
            <div style={{ display:'flex', flexDirection:'column', gap:'6px' }}>
              {productos.map(prod => (
                <ProductoEnBuscador
                  key={prod.id}
                  producto={prod}
                  idsEnCarrito={idsEnCarrito}
                  onAgregar={(v) => onAgregar(v, prod)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {dq.length > 0 && dq.length < 2 && (
        <p style={{ fontSize:'12px', color:C.textMuted, marginTop:'8px', textAlign:'center' }}>
          Escribí al menos 2 caracteres
        </p>
      )}
    </div>
  )
}

function ProductoEnBuscador({ producto, onAgregar, idsEnCarrito }) {
  const [expandido, setExpandido] = useState(false)
  const imgUrl = producto.imagen_principal?.imagen_url || producto.imagen_principal?.imagen

  const { data: detalleData } = useQuery({
    queryKey: ['producto-variantes', producto.id],
    queryFn: () => productosApi.detalle(producto.id).then(r => r.data),
    enabled: expandido,
  })

  return (
    <div style={{ border:`1px solid ${expandido ? C.gold : C.border}`, borderRadius:'10px',
      overflow:'hidden', transition:'border-color 120ms' }}>
      <div
        onClick={() => setExpandido(e => !e)}
        style={{
          display:'flex', alignItems:'center', gap:'11px',
          padding:'11px 13px', cursor:'pointer',
          background: expandido ? C.goldMuted : C.bg,
          transition:'background 100ms',
        }}
      >
        <div style={{ width:'44px', height:'44px', flexShrink:0, borderRadius:'9px',
          overflow:'hidden', background:C.bgTer,
          display:'flex', alignItems:'center', justifyContent:'center' }}>
          {imgUrl
            ? <img src={imgUrl} alt="" style={{ width:'100%', height:'100%', objectFit:'cover' }}/>
            : <Package size={18} style={{ color:C.border, opacity:0.5 }} />}
        </div>
        <div style={{ flex:1, minWidth:0 }}>
          <p style={{ fontSize:'14px', fontWeight:'500', color:C.text,
            overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
            {producto.nombre}
          </p>
          <p style={{ fontSize:'12px', color:C.textMuted }}>
            [{producto.codigo}] · {producto.variantes_count} variante{producto.variantes_count!==1?'s':''} · toca para ver
          </p>
        </div>
        <p style={{ fontSize:'13px', fontWeight:'600', color:C.goldDark, flexShrink:0 }}>
          {formatGs(producto.precio_base)}
        </p>
        <div style={{ width:'28px', height:'28px', borderRadius:'7px', flexShrink:0,
          background: expandido ? C.gold : C.bgTer,
          display:'flex', alignItems:'center', justifyContent:'center',
          transition:'background 120ms' }}>
          {expandido ? <ChevronUp size={16} style={{ color:C.bg }} />
                     : <ChevronDown size={16} style={{ color:C.textSec }} />}
        </div>
      </div>

      {expandido && (
        <div style={{ padding:'4px 10px 10px', background:C.bgSec,
          borderTop:`1px solid ${C.border}` }}>
          {!detalleData
            ? <p style={{ fontSize:'12px', color:C.textMuted, padding:'10px 4px' }}>Cargando variantes...</p>
            : detalleData.variantes.map(v => {
                const st = v.stock?.disponible ?? v.stock?.cantidad ?? 0
                const sinStock = Number(st) <= 0
                const yaEsta = idsEnCarrito?.includes(v.id)
                return (
                  <div key={v.id} style={{
                    display:'flex', alignItems:'center', gap:'10px',
                    padding:'9px 10px', marginTop:'5px',
                    background:C.bg, borderRadius:'9px',
                    border:`1px solid ${yaEsta ? C.success : (sinStock ? C.dangerBg : C.border)}`,
                    opacity: sinStock ? 0.6 : 1,
                  }}>
                    <div style={{ flex:1, minWidth:0 }}>
                      <p style={{ fontSize:'13px', fontWeight:'500', color:C.text }}>
                        {v.color || 'Sin color'}
                        {v.dimension_display ? ` · ${v.dimension_display}` : ''}
                        {v.acabado?.nombre ? ` · ${v.acabado.nombre}` : ''}
                      </p>
                      <p style={{ fontSize:'11.5px', color: sinStock ? C.danger : C.textMuted }}>
                        {sinStock ? 'Sin stock' : `Stock: ${Number(st).toFixed(2)} ${detalleData.unidad_venta}`}
                        {' · '}{v.sku}
                      </p>
                    </div>
                    <p style={{ fontSize:'13px', fontWeight:'600', color:C.goldDark, flexShrink:0 }}>
                      {formatGs(v.precio_venta)}
                    </p>
                    <button
                      disabled={sinStock}
                      onClick={e => { e.stopPropagation(); onAgregar(v) }}
                      style={{
                        height:'38px', padding:'0 14px', borderRadius:'9px',
                        background: sinStock ? C.bgTer : (yaEsta ? C.success : C.sidebar),
                        border: `1px solid ${sinStock ? C.border : (yaEsta ? C.success : C.gold)}`,
                        color: sinStock ? C.textMuted : (yaEsta ? C.bg : C.gold),
                        cursor: sinStock ? 'not-allowed' : 'pointer',
                        display:'flex', alignItems:'center', justifyContent:'center', gap:'5px',
                        flexShrink:0, fontSize:'13px', fontWeight:'500',
                        transition:'all 120ms',
                      }}
                    >
                      {yaEsta ? <><CheckCircle size={15} /> Sumar</> : <><Plus size={15} /> Agregar</>}
                    </button>
                  </div>
                )
              })
          }
        </div>
      )}
    </div>
  )
}

// ─── Fila de ítem en el carrito ───────────────────────────────────────────────
function FilaItem({ item, onChange, onEliminar, esTouch }) {
  const btnSize = esTouch ? 36 : 30
  const max = item.stock_disponible != null ? Number(item.stock_disponible) : Infinity
  const setQty = (n) => onChange('cantidad', Math.min(max, Math.max(0.01, Number(n.toFixed(2)))))
  const cant = Number(item.cantidad)
  const alMaximo = max < Infinity && cant >= max

  return (
    <div style={{
      padding:'12px 16px', borderBottom:`1px solid ${C.border}`, background:C.bg,
    }}>
      <div style={{ display:'flex', alignItems:'flex-start', gap:'10px', marginBottom:'9px' }}>
        <div style={{ flex:1, minWidth:0 }}>
          <p style={{ fontSize:'13.5px', fontWeight:'500', color:C.text }}>
            {item.descripcion}
          </p>
          <p style={{ fontSize:'11.5px', color:C.textMuted, marginTop:'1px' }}>
            {formatGs(item.precio_unitario)} / {item.unidad_venta} · {item.sku}
          </p>
        </div>
        <button onClick={onEliminar}
          style={{ background:'transparent', border:'none', cursor:'pointer',
            color:C.textMuted, padding:'4px', display:'flex', alignItems:'center', flexShrink:0 }}
          onMouseEnter={e => e.currentTarget.style.color = C.danger}
          onMouseLeave={e => e.currentTarget.style.color = C.textMuted}>
          <Trash2 size={16} />
        </button>
      </div>

      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:'8px' }}>
        {/* Controles de cantidad */}
        <div style={{ display:'flex', alignItems:'center', gap:'6px' }}>
          <button
            onClick={() => setQty(cant - (cant > 1 ? 1 : 0.5))}
            style={{ width:`${btnSize}px`, height:`${btnSize}px`, borderRadius:'8px',
              background:C.bgSec, border:`1px solid ${C.border}`, cursor:'pointer',
              color:C.textSec, display:'flex', alignItems:'center', justifyContent:'center' }}>
            <Minus size={15} />
          </button>
          <input
            type="number" min="0.01" max={max === Infinity ? undefined : max} step="0.5"
            value={item.cantidad}
            onChange={e => setQty(Number(e.target.value) || 0.01)}
            style={{ width:'62px', height:`${btnSize}px`, textAlign:'center', padding:'0 4px',
              border:`1px solid ${C.border}`, borderRadius:'8px',
              fontSize:'15px', fontWeight:'500', color:C.text, background:C.bg, outline:'none' }}
            onFocus={e => e.target.style.borderColor = C.gold}
            onBlur={e => e.target.style.borderColor = C.border}
          />
          <button
            disabled={alMaximo}
            onClick={() => setQty(cant + 1)}
            style={{ width:`${btnSize}px`, height:`${btnSize}px`, borderRadius:'8px',
              background:C.bgSec, border:`1px solid ${C.border}`, cursor: alMaximo ? 'not-allowed' : 'pointer',
              color:C.textSec, display:'flex', alignItems:'center', justifyContent:'center',
              opacity: alMaximo ? 0.4 : 1 }}>
            <Plus size={15} />
          </button>
          {/* Atajos rápidos para venta por cantidad */}
          <div style={{ display:'flex', gap:'4px', marginLeft:'4px' }}>
            {[5, 10].map(n => (
              <button key={n} disabled={alMaximo} onClick={() => setQty(cant + n)}
                style={{ height:`${btnSize}px`, padding:'0 9px', borderRadius:'8px',
                  background:'transparent', border:`1px solid ${C.border}`,
                  cursor: alMaximo ? 'not-allowed' : 'pointer',
                  color:C.goldDark, fontSize:'12px', fontWeight:'500',
                  opacity: alMaximo ? 0.4 : 1 }}>
                +{n}
              </button>
            ))}
          </div>
        </div>

        {/* Subtotal */}
        <p style={{ fontSize:'15px', fontWeight:'700', color:C.goldDark,
          textAlign:'right', flexShrink:0 }}>
          {formatGs(Number(item.precio_unitario) * cant)}
        </p>
      </div>
      {alMaximo && (
        <p style={{ fontSize:'10.5px', color:C.danger, marginTop:'4px' }}>
          Máximo disponible: {max}
        </p>
      )}
    </div>
  )
}

// ─── Componente principal ──────────────────────────────────────────────────────
export default function NuevoPedidoForm({ onPedidoCreado, onCancelar }) {
  const queryClient = useQueryClient()
  const device = useDevice()
  const { usuario } = useAuthStore()
  // Solo admin y Encargada de Ventas pueden modificar precios al armar el pedido
  const puedeEditarPrecio = Boolean(usuario?.puede_editar_precio)

  const [items, setItems] = useState([])
  const [cliente, setCliente] = useState({ nombre:'', telefono:'', observaciones:'' })
  const [descuento, setDescuento] = useState(0)
  const [clienteAbierto, setClienteAbierto] = useState(false)
  const [clienteSel, setClienteSel] = useState(null)      // cliente del padrón (con RUC)
  const [montoAjustado, setMontoAjustado] = useState('')  // precio final negociado (opcional)
  const [ajusteAbierto, setAjusteAbierto] = useState(false)

  const subtotal = items.reduce((s, i) => s + Number(i.precio_unitario) * Number(i.cantidad), 0)
  const totalCalculado = Math.max(0, subtotal - Number(descuento))
  // El total a mostrar/enviar es el ajustado solo si el usuario tiene la facultad
  const hayAjuste = puedeEditarPrecio && ajusteAbierto && montoAjustado !== '' && Number(montoAjustado) >= 0
  const total    = hayAjuste ? Number(montoAjustado) : totalCalculado
  const idsEnCarrito = items.map(i => i.variante_id)

  const agregarVariante = useCallback((variante, producto) => {
    // Tope de stock disponible — antes solo se validaba al elegir la
    // variante en el buscador; una vez en el carrito se podía subir la
    // cantidad libremente por encima del stock real.
    const stockDisp = variante.stock?.disponible != null
      ? Number(variante.stock.disponible)
      : (variante.stock?.cantidad != null ? Number(variante.stock.cantidad) : Infinity)
    setItems(prev => {
      const existe = prev.findIndex(i => i.variante_id === variante.id)
      if (existe >= 0) {
        return prev.map((i, idx) => idx === existe
          ? { ...i, cantidad: Math.min(stockDisp, Number(i.cantidad) + 1), stock_disponible: stockDisp }
          : i)
      }
      const partes = [producto?.nombre || variante.producto_nombre || '']
      if (variante.dimension_display) partes.push(variante.dimension_display)
      if (variante.color)             partes.push(variante.color)
      if (variante.acabado?.nombre)   partes.push(variante.acabado.nombre)
      return [...prev, {
        variante_id:    variante.id,
        sku:            variante.sku,
        descripcion:    partes.filter(Boolean).join(' — '),
        precio_unitario:variante.precio_venta,
        cantidad:       Math.min(stockDisp, 1),
        unidad_venta:   producto?.unidad_venta || 'm2',
        descuento_item: 0,
        observaciones:  '',
        stock_disponible: stockDisp,
      }]
    })
    toast.success('Agregado al pedido', { duration: 1000 })
  }, [])


  const actualizarItem = useCallback((idx, campo, valor) => {
    setItems(prev => prev.map((i, n) => n === idx ? { ...i, [campo]: valor } : i))
  }, [])

  const eliminarItem = useCallback((idx) => {
    setItems(prev => prev.filter((_, n) => n !== idx))
  }, [])

  const mutation = useMutation({
    mutationFn: () => ventasApi.crear({
      cliente_id:            clienteSel?.id || null,
      cliente_nombre:        cliente.nombre || clienteSel?.razon_social || '',
      cliente_ruc:           clienteSel?.ruc || '',
      cliente_telefono:      cliente.telefono || clienteSel?.telefono || '',
      cliente_observaciones: cliente.observaciones,
      descuento,
      total_ajustado:        hayAjuste ? Number(montoAjustado) : null,
      items: items.map(i => ({
        variante_id:    i.variante_id,
        cantidad:       Number(i.cantidad),
        precio_unitario:Number(i.precio_unitario),
        descuento_item: Number(i.descuento_item || 0),
        observaciones:  i.observaciones || '',
      })),
    }).then(r => r.data),
    onSuccess: (pedido) => {
      queryClient.invalidateQueries({ queryKey: ['pedidos'] })
      toast.success(`Nota ${pedido.numero} enviada a caja`)
      onPedidoCreado?.(pedido)
    },
    onError: (err) => {
      toast.error(mensajeErrorApi(err, 'Error al crear el pedido'))
    },
  })

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>
      {/* Header */}
      <div style={{ padding:'15px 20px', borderBottom:`1px solid ${C.border}`,
        display:'flex', alignItems:'center', justifyContent:'space-between', flexShrink:0 }}>
        <div style={{ display:'flex', alignItems:'center', gap:'10px' }}>
          <div style={{ width:'34px', height:'34px', borderRadius:'9px',
            background:C.sidebar, border:`1px solid ${C.gold}`,
            display:'flex', alignItems:'center', justifyContent:'center' }}>
            <FileText size={17} style={{ color:C.gold }} />
          </div>
          <div>
            <p style={{ fontSize:'15px', fontWeight:'500', color:C.text }}>Nueva nota de pedido</p>
            <p style={{ fontSize:'11.5px', color:C.textMuted }}>
              {items.length} producto{items.length!==1?'s':''}
              {items.length > 0 ? ` · ${formatGs(total)}` : ''}
            </p>
          </div>
        </div>
        {onCancelar && (
          <button onClick={onCancelar} style={{ background:'transparent', border:'none',
            cursor:'pointer', color:C.textMuted, padding:'6px', display:'flex',
            alignItems:'center', borderRadius:'8px' }}>
            <X size={20} />
          </button>
        )}
      </div>

      {/* Buscador SIEMPRE visible y prominente */}
      <div style={{ padding:'14px 20px', borderBottom:`1px solid ${C.border}`,
        background:C.bgSec, flexShrink:0 }}>
        <BuscadorVariante onAgregar={agregarVariante} idsEnCarrito={idsEnCarrito} />
      </div>

      {/* Contenido scrollable: carrito + cliente */}
      <div style={{ flex:1, overflowY:'auto', WebkitOverflowScrolling:'touch' }}>

        {/* Carrito */}
        {items.length === 0 ? (
          <div style={{ padding:'44px 20px', textAlign:'center', color:C.textMuted }}>
            <PackagePlus size={40} style={{ margin:'0 auto 12px', opacity:0.2 }} />
            <p style={{ fontSize:'15px', fontWeight:'500', color:C.textSec }}>
              Buscá productos arriba
            </p>
            <p style={{ fontSize:'13px', marginTop:'4px' }}>
              Tocá un producto para ver sus variantes y agregarlas al pedido
            </p>
          </div>
        ) : (
          <>
            <div style={{ padding:'10px 20px 4px' }}>
              <p style={{ fontSize:'11px', fontWeight:'500', color:C.textMuted,
                textTransform:'uppercase', letterSpacing:'0.06em' }}>
                Productos del pedido ({items.length})
              </p>
            </div>
            {items.map((item, idx) => (
              <FilaItem
                key={`${item.variante_id}-${idx}`}
                item={item}
                esTouch={device.isTouch}
                onChange={(campo, valor) => actualizarItem(idx, campo, valor)}
                onEliminar={() => eliminarItem(idx)}
              />
            ))}
          </>
        )}

        {/* Datos del cliente — colapsable */}
        <div style={{ borderTop:`1px solid ${C.border}`, marginTop: items.length ? '4px' : 0 }}>
          <button
            onClick={() => setClienteAbierto(a => !a)}
            style={{ width:'100%', padding:'14px 20px', background:'transparent',
              border:'none', cursor:'pointer', display:'flex', alignItems:'center',
              justifyContent:'space-between' }}>
            <span style={{ display:'flex', alignItems:'center', gap:'8px',
              fontSize:'13px', fontWeight:'500', color:C.textSec }}>
              <User size={15} />
              Datos del cliente
              {cliente.nombre && <span style={{ color:C.goldDark }}>· {cliente.nombre}</span>}
              <span style={{ fontSize:'11px', color:C.textMuted, fontWeight:'400' }}>(opcional)</span>
            </span>
            {clienteAbierto ? <ChevronUp size={16} style={{ color:C.textMuted }} />
                            : <ChevronDown size={16} style={{ color:C.textMuted }} />}
          </button>

          {clienteAbierto && (
            <div style={{ padding:'0 20px 16px' }}>
              {/* Buscador de cliente del padrón con RUC */}
              <BuscadorCliente
                clienteSel={clienteSel}
                onSeleccionar={(c) => {
                  setClienteSel(c)
                  setCliente(prev => ({
                    ...prev,
                    nombre: c.razon_social,
                    telefono: c.telefono || prev.telefono,
                  }))
                }}
                onLimpiar={() => setClienteSel(null)}
              />
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'10px' }}>
                {[
                  { key:'nombre',    label:'Nombre',   ph:'Cliente' },
                  { key:'telefono',  label:'Teléfono', ph:'09x xxx xxxx' },
                ].map(f => (
                  <div key={f.key}>
                    <label style={{ display:'block', fontSize:'11.5px', color:C.textSec,
                      marginBottom:'4px' }}>{f.label}</label>
                    <input
                      value={cliente[f.key]}
                      onChange={e => setCliente(c => ({...c, [f.key]: e.target.value}))}
                      placeholder={f.ph}
                      style={{ width:'100%', height:'40px', padding:'0 10px',
                        border:`1px solid ${C.border}`, borderRadius:'8px',
                        fontSize:'14px', color:C.text, background:C.bg, outline:'none' }}
                      onFocus={e => e.target.style.borderColor = C.gold}
                      onBlur={e => e.target.style.borderColor = C.border}
                    />
                  </div>
                ))}
              </div>
              {clienteSel?.ruc && (
                <p style={{ fontSize:'11.5px', color:C.goldDark, marginTop:'6px' }}>
                  RUC: {clienteSel.ruc}
                  {clienteSel.permite_ajuste_precio && ' · Cliente con precio negociable'}
                </p>
              )}
              <div style={{ marginTop:'10px' }}>
                <label style={{ display:'block', fontSize:'11.5px', color:C.textSec, marginBottom:'4px' }}>
                  Observaciones
                </label>
                <textarea
                  value={cliente.observaciones}
                  onChange={e => setCliente(c => ({...c, observaciones: e.target.value}))}
                  placeholder="Medidas especiales, entrega, referencias..."
                  rows={2}
                  style={{ width:'100%', padding:'8px 10px',
                    border:`1px solid ${C.border}`, borderRadius:'8px',
                    fontSize:'14px', color:C.text, background:C.bg, outline:'none',
                    resize:'vertical', fontFamily:'inherit' }}
                  onFocus={e => e.target.style.borderColor = C.gold}
                  onBlur={e => e.target.style.borderColor = C.border}
                />
              </div>
            </div>
          )}
        </div>

        {/* Descuento */}
        {items.length > 0 && (
          <div style={{ padding:'14px 20px', borderTop:`1px solid ${C.border}` }}>
            <div style={{ display:'flex', alignItems:'center', gap:'10px', justifyContent:'space-between' }}>
              <label style={{ fontSize:'13px', color:C.textSec }}>Descuento (Gs.)</label>
              <input
                type="number" min="0" step="1000"
                value={descuento}
                onChange={e => setDescuento(e.target.value)}
                placeholder="0"
                style={{ width:'140px', height:'40px', padding:'0 10px', textAlign:'right',
                  border:`1px solid ${C.border}`, borderRadius:'8px',
                  fontSize:'14px', color:C.text, background:C.bg, outline:'none' }}
                onFocus={e => e.target.style.borderColor = C.gold}
                onBlur={e => e.target.style.borderColor = C.border}
              />
            </div>
          </div>
        )}

        {/* Ajuste de monto final (precio negociado) — solo Encargada de Ventas / admin */}
        {items.length > 0 && puedeEditarPrecio && (
          <div style={{ padding:'14px 20px', borderTop:`1px solid ${C.border}` }}>
            <label style={{ display:'flex', alignItems:'center', gap:'8px', cursor:'pointer',
              fontSize:'13px', color:C.textSec }}>
              <input type="checkbox" checked={ajusteAbierto}
                onChange={e => { setAjusteAbierto(e.target.checked); if (!e.target.checked) setMontoAjustado('') }}
                style={{ width:'16px', height:'16px', accentColor:C.gold, cursor:'pointer' }} />
              Ajustar monto final (precio negociado)
            </label>
            {ajusteAbierto && (
              <div style={{ marginTop:'10px' }}>
                <div style={{ display:'flex', alignItems:'center', gap:'10px', justifyContent:'space-between' }}>
                  <span style={{ fontSize:'12px', color:C.textMuted }}>
                    Calculado: {formatGs(totalCalculado)}
                  </span>
                  <input
                    type="number" min="0" step="1000"
                    value={montoAjustado}
                    onChange={e => setMontoAjustado(e.target.value)}
                    placeholder="Monto final"
                    autoFocus
                    style={{ width:'160px', height:'42px', padding:'0 12px', textAlign:'right',
                      border:`1.5px solid ${C.gold}`, borderRadius:'9px',
                      fontSize:'16px', fontWeight:'600', color:C.goldDark, background:C.bg, outline:'none' }}
                  />
                </div>
                <p style={{ fontSize:'11.5px', color:C.textMuted, marginTop:'6px' }}>
                  Este será el monto que se pasa a caja. Usalo para clientes con precio acordado.
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer con totales y envío */}
      <div style={{ padding:'14px 20px', borderTop:`1px solid ${C.border}`,
        background:C.bgSec, flexShrink:0 }}>
        {items.length > 0 && (
          <div style={{ marginBottom:'12px' }}>
            {[
              { label:'Subtotal', valor:subtotal, muted:true },
              { label:'Descuento', valor:-Number(descuento), muted:true, sign:true },
              { label:'Total', valor:total, muted:false },
            ].filter(r => r.valor !== 0 || !r.muted).map(row => (
              <div key={row.label} style={{ display:'flex', justifyContent:'space-between',
                alignItems:'baseline', marginBottom:'4px' }}>
                <span style={{ fontSize: row.muted?'12px':'15px',
                  fontWeight: row.muted?'400':'600',
                  color: row.muted?C.textSec:C.text }}>{row.label}</span>
                <span style={{ fontSize: row.muted?'13px':'18px',
                  fontWeight: row.muted?'500':'700',
                  color: row.muted? (row.sign?C.danger:C.textSec) : C.goldDark }}>
                  {row.sign && row.valor < 0 ? '− ' : ''}{formatGs(Math.abs(row.valor))}
                </span>
              </div>
            ))}
          </div>
        )}

        <button
          disabled={items.length === 0 || mutation.isPending}
          onClick={() => mutation.mutate()}
          style={{
            width:'100%', height: device.isTouch?'54px':'46px',
            borderRadius:'11px',
            background: items.length === 0 ? C.bgTer : C.sidebar,
            border: items.length === 0 ? `1px solid ${C.border}` : `1px solid ${C.gold}`,
            color: items.length === 0 ? C.textMuted : C.gold,
            fontSize:'15px', fontWeight:'500', cursor: items.length === 0?'not-allowed':'pointer',
            display:'flex', alignItems:'center', justifyContent:'center', gap:'8px',
            transition:'background 120ms',
          }}
        >
          {mutation.isPending
            ? <><Loader2 size={17} style={{ animation:'spin 1s linear infinite' }} /> Enviando...</>
            : <><CheckCircle size={17} /> Enviar a caja</>
          }
        </button>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
