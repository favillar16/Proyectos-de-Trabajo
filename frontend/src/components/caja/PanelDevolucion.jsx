/**
 * PanelDevolucion — devolución o cambio de mercadería ya cobrada.
 *
 * Se abre desde un cobro de la lista ("Cobros del turno" / "Turnos
 * anteriores"). La cajera toca lo que vuelve (se marca con todo lo que
 * queda; la cantidad se puede bajar), el motivo, y si el cliente se lleva
 * algo a cambio lo busca ahí mismo y lo marca: el backend arma el pedido de
 * cambio solo, sin que el vendedor tenga que hacer uno aparte. La pantalla
 * muestra la diferencia antes de confirmar: a cobrar, a reintegrar o nada.
 *
 * La cuenta de verdad la hace el backend (apps/caja/devoluciones.py): el
 * crédito sale de lo que el cliente pagó, no del precio de lista, y el
 * redondeo lo absorbe la última devolución de cada ítem. Lo que se ve acá
 * es una estimación con la misma regla, para que la cajera sepa qué va a
 * pasar antes de tocar la plata.
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Banknote, CreditCard, ArrowRightLeft, Loader2, AlertCircle, RotateCcw,
  CheckCircle, Printer, Search, X,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { cajaApi, inventarioApi } from '../../services/api'

const C = {
  sidebar:'#453941',
  gold:'#B99C74', goldDark:'#8a7355', goldMuted:'rgba(185,156,116,0.10)',
  border:'#e8e4df', bg:'#ffffff', bgSec:'#fafaf9', bgTer:'#f5f4f2',
  text:'#1a1714', textSec:'#6b6560', textMuted:'#9e9892',
  success:'#3d7a5a', successBg:'#edf7f1', successBorder:'#b8deca',
  warning:'#8a6a1a', warningBg:'#fef9ee', warningBorder:'#f0d98a',
  danger:'#9a3030', dangerBg:'#fef0f0', dangerBorder:'#f0b8b8',
}

const MOTIVOS = [
  { key:'cambio',            label:'Cambio de producto' },
  { key:'estado_inadecuado', label:'Estado inadecuado' },
  { key:'otro',              label:'Otro motivo' },
]

// Sin cheque: ni se recibe un papel a cobrar por una diferencia de
// mostrador, ni la caja reintegra con cheques (ver MEDIOS_PERMITIDOS en
// backend/apps/caja/devoluciones.py).
const MEDIOS = [
  { key:'efectivo',      label:'Efectivo',       icon:<Banknote size={16}/> },
  { key:'debito',        label:'Débito',         icon:<CreditCard size={16}/> },
  { key:'credito',       label:'Crédito',        icon:<CreditCard size={16}/> },
  { key:'transferencia', label:'Transferencia',  icon:<ArrowRightLeft size={16}/> },
]

const UNIDAD = { m2:'m²', pieza:'u.', juego:'jgo.', caja:'cajas', ml:'ml' }

function formatGs(v) { return `Gs. ${Math.round(Number(v||0)).toLocaleString('es-PY')}` }
function formatCant(v) {
  return Number(v||0).toLocaleString('es-PY', { maximumFractionDigits: 2 })
}

const etiqueta = {
  fontSize:'11px', fontWeight:'500', color:C.textMuted,
  textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'10px',
}
const input = {
  width:'100%', height:'40px', padding:'0 12px',
  border:`1px solid ${C.border}`, borderRadius:'8px',
  fontSize:'14px', color:C.text, background:C.bg, outline:'none',
}

export function PanelDevolucion({ pagoId, onListo, onCancelar }) {
  const [motivo, setMotivo]           = useState('cambio')
  const [detalle, setDetalle]         = useState('')
  const [cantidades, setCantidades]   = useState({})
  const [reingresa, setReingresa]     = useState({})
  // Lo que se lleva el cliente: { [variante_id]: { variante, cantidad } }
  const [llevados, setLlevados]       = useState({})
  const [busqueda, setBusqueda]       = useState('')
  const [termino, setTermino]         = useState('')
  const [medio, setMedio]             = useState('efectivo')
  const [recibido, setRecibido]       = useState('')
  const [observaciones, setObservaciones] = useState('')

  const { data: venta, isLoading, error } = useQuery({
    queryKey: ['devolucion-resumen', pagoId],
    queryFn:  () => cajaApi.resumenDevolucion(pagoId).then(r => r.data),
  })

  // La búsqueda espera a que la cajera deje de tipear.
  useEffect(() => {
    const t = setTimeout(() => setTermino(busqueda.trim()), 300)
    return () => clearTimeout(t)
  }, [busqueda])

  const { data: encontrados, isFetching: buscando } = useQuery({
    queryKey: ['cambio-busqueda', termino],
    queryFn:  () => inventarioApi.consultaRapida(termino).then(r => r.data.resultados || []),
    enabled:  termino.length >= 2,
  })

  const elegidos = Object.values(llevados)
  const agregarLlevado = (v) => {
    setLlevados(l => l[v.variante_id] ? l : { ...l, [v.variante_id]: { variante: v, cantidad: '1' } })
    setBusqueda('')
    setTermino('')
  }
  const quitarLlevado = (id) => setLlevados(l => { const n = { ...l }; delete n[id]; return n })
  const cantidadLlevado = (id, cantidad) =>
    setLlevados(l => ({ ...l, [id]: { ...l[id], cantidad } }))

  // Lo dañado no vuelve al stock vendible: con "estado inadecuado" la casilla
  // arranca destildada, pero la cajera puede cambiarla ítem por ítem.
  const vuelveAlStock = (itemId) =>
    reingresa[itemId] ?? (motivo !== 'estado_inadecuado')

  const credito = useMemo(() => {
    if (!venta) return 0
    return venta.items.reduce((suma, item) => {
      const cant = Number(cantidades[item.item_id] || 0)
      if (!(cant > 0)) return suma
      if (cant >= Number(item.cantidad_disponible)) return suma + Number(item.valor_restante)
      return suma + Math.round(cant * Number(item.precio_cobrado_unit))
    }, 0)
  }, [venta, cantidades])

  const nuevo = elegidos.reduce((suma, e) =>
    suma + Number(e.cantidad || 0) * Number(e.variante.precio_venta || 0), 0)
  const diferencia = nuevo - credito
  const aCobrar    = Math.max(diferencia, 0)
  const aReintegrar = Math.max(-diferencia, 0)

  const itemsElegidos = venta?.items.filter(i => Number(cantidades[i.item_id] || 0) > 0) || []
  const excedido = venta?.items.some(i =>
    Number(cantidades[i.item_id] || 0) > Number(i.cantidad_disponible))

  const faltaMotivo  = motivo === 'otro' && !detalle.trim()
  const faltaCambio  = motivo === 'cambio' && elegidos.length === 0
  const llevadoInvalido = elegidos.some(e => !(Number(e.cantidad) > 0))
  const llevadoSinStock = elegidos.some(e => Number(e.cantidad) > Number(e.variante.disponible))
  const faltaEfectivo = aCobrar > 0 && medio === 'efectivo' && Number(recibido || 0) < aCobrar

  const puedeConfirmar = venta && !venta.bloqueo && itemsElegidos.length > 0 &&
    !excedido && !faltaMotivo && !faltaCambio && !faltaEfectivo &&
    !llevadoInvalido && !llevadoSinStock

  const confirmarMut = useMutation({
    mutationFn: () => cajaApi.registrarDevolucion({
      pago_id: pagoId,
      motivo,
      motivo_detalle: detalle,
      observaciones,
      items: itemsElegidos.map(i => ({
        item_id: i.item_id,
        cantidad: cantidades[i.item_id],
        reingresa_stock: vuelveAlStock(i.item_id),
      })),
      items_cambio: elegidos.map(e => ({
        variante_id: e.variante.variante_id, cantidad: e.cantidad,
      })),
      medio_pago: (aCobrar > 0 || aReintegrar > 0) ? medio : '',
      monto_recibido: aCobrar > 0 && medio === 'efectivo' ? recibido : null,
    }).then(r => r.data),
    onSuccess: (data) => {
      if (data.impresion && !data.impresion.ok) {
        toast.error(`Devolución registrada, pero no se imprimió: ${data.impresion.error || 'impresora'}`)
      } else {
        toast.success(`Devolución ${data.devolucion.numero} registrada`)
      }
      if (data.errores_stock?.length) {
        toast.error('Hubo diferencias de stock en el pedido de cambio; revisá inventario.')
      }
      onListo(data)
    },
    onError: (err) => toast.error(err.response?.data?.error || 'No se pudo registrar la devolución'),
  })

  if (isLoading) {
    return (
      <div style={{ display:'flex', alignItems:'center', justifyContent:'center',
        height:'100%', color:C.textMuted }}>
        <Loader2 size={24} style={{ animation:'spin 1s linear infinite' }} />
      </div>
    )
  }
  if (error) {
    return (
      <div style={{ padding:'24px', color:C.danger, fontSize:'13px' }}>
        {error.response?.data?.error || 'No se pudo cargar la venta.'}
        <button onClick={onCancelar} style={{ marginLeft:'10px' }}>Volver</button>
      </div>
    )
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>
      {/* Header */}
      <div style={{ padding:'16px 20px', borderBottom:`1px solid ${C.border}`,
        display:'flex', alignItems:'center', justifyContent:'space-between', flexShrink:0 }}>
        <div>
          <p style={{ fontSize:'11px', color:C.textMuted, fontFamily:'monospace' }}>
            Devolución · {venta.pedido_numero} · {venta.numero_ticket}
          </p>
          <h2 style={{ fontSize:'17px', fontWeight:'500',
            fontFamily:'var(--font-display)', color:C.text, marginTop:'2px' }}>
            {venta.cliente}
          </h2>
        </div>
        <div style={{ textAlign:'right' }}>
          <p style={{ fontSize:'15px', fontWeight:'600', color:C.textSec }}>
            {formatGs(venta.monto_cobrado)}
          </p>
          <p style={{ fontSize:'11px', color:C.textMuted }}>cobrado en la venta</p>
        </div>
      </div>

      <div style={{ flex:1, overflowY:'auto', padding:'18px 20px',
        WebkitOverflowScrolling:'touch' }}>

        {venta.bloqueo && (
          <div style={{ display:'flex', gap:'8px', padding:'12px 14px', marginBottom:'16px',
            background:C.dangerBg, border:`1px solid ${C.dangerBorder}`, borderRadius:'10px',
            color:C.danger, fontSize:'13px' }}>
            <AlertCircle size={16} style={{ flexShrink:0, marginTop:'2px' }} />
            <span>{venta.bloqueo}</span>
          </div>
        )}

        {venta.devoluciones_previas?.length > 0 && (
          <p style={{ fontSize:'12px', color:C.warning, background:C.warningBg,
            border:`1px solid ${C.warningBorder}`, borderRadius:'8px',
            padding:'8px 12px', marginBottom:'16px' }}>
            Esta venta ya tiene devoluciones: {venta.devoluciones_previas.map(d => d.numero).join(', ')}.
            Solo se puede devolver lo que queda.
          </p>
        )}

        {/* Motivo */}
        <p style={etiqueta}>Motivo</p>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:'8px',
          marginBottom:'10px' }}>
          {MOTIVOS.map(m => (
            <button key={m.key} onClick={() => { setMotivo(m.key); setReingresa({}) }}
              style={{
                padding:'10px 8px', borderRadius:'10px', cursor:'pointer', fontSize:'13px',
                background: motivo === m.key ? C.sidebar : 'transparent',
                border:`1.5px solid ${motivo === m.key ? C.gold : C.border}`,
                color: motivo === m.key ? C.gold : C.textSec,
                fontWeight: motivo === m.key ? '600' : '500',
              }}>
              {m.label}
            </button>
          ))}
        </div>
        <input value={detalle} onChange={e => setDetalle(e.target.value)} maxLength={200}
          placeholder={motivo === 'otro' ? '¿Cuál es el motivo? (obligatorio)' : 'Detalle (opcional)'}
          style={{ ...input, marginBottom:'18px',
            borderColor: faltaMotivo ? C.dangerBorder : C.border }} />

        {/* Qué vuelve */}
        <p style={etiqueta}>Qué devuelve el cliente — tocá el producto</p>
        {venta.items.map(item => {
          const disponible = Number(item.cantidad_disponible)
          const valor = cantidades[item.item_id] ?? ''
          const marcado = Number(valor || 0) > 0
          const pasado = Number(valor || 0) > disponible
          const unidad = UNIDAD[item.unidad] || item.unidad
          const bloqueado = disponible <= 0 || Boolean(venta.bloqueo)
          // Tocar el renglón lo marca con todo lo que queda; tocarlo de nuevo
          // lo desmarca. La cantidad se puede bajar a mano.
          const alternar = () => {
            if (bloqueado) return
            setCantidades(c => ({ ...c, [item.item_id]: marcado ? '' : String(disponible) }))
          }
          return (
            <div key={item.item_id} style={{ padding:'10px 12px', marginBottom:'6px',
              borderRadius:'10px', border:`1.5px solid ${marcado ? C.gold : C.border}`,
              background: marcado ? C.goldMuted : C.bg,
              opacity: disponible > 0 ? 1 : 0.5 }}>
              <div style={{ display:'flex', justifyContent:'space-between', gap:'10px',
                alignItems:'center' }}>
                <input type="checkbox" checked={marcado} disabled={bloqueado} onChange={alternar}
                  style={{ width:'18px', height:'18px', flexShrink:0, cursor:'pointer' }} />
                <div style={{ minWidth:0, flex:1, cursor: bloqueado ? 'default' : 'pointer' }}
                  onClick={alternar}>
                  <p style={{ fontSize:'13px', fontWeight:'500', color:C.text }}>{item.producto}</p>
                  <p style={{ fontSize:'11px', color:C.textMuted }}>
                    {item.variante} · vendido {formatCant(item.cantidad_vendida)} {unidad}
                    {Number(item.cantidad_devuelta) > 0 && ` · ya volvió ${formatCant(item.cantidad_devuelta)}`}
                    {' · '}{formatGs(item.precio_cobrado_unit)} / {unidad} cobrado
                  </p>
                </div>
                <div style={{ display:'flex', alignItems:'center', gap:'6px', flexShrink:0 }}>
                  <input type="number" min="0" max={disponible} step="0.01"
                    disabled={bloqueado}
                    value={valor}
                    onChange={e => setCantidades(c => ({ ...c, [item.item_id]: e.target.value }))}
                    placeholder="0"
                    style={{ ...input, width:'88px', textAlign:'right',
                      borderColor: pasado ? C.dangerBorder : C.border }} />
                  <span style={{ fontSize:'12px', color:C.textMuted, width:'34px' }}>{unidad}</span>
                </div>
              </div>
              {pasado && (
                <p style={{ fontSize:'11px', color:C.danger, marginTop:'4px' }}>
                  Se pueden devolver hasta {formatCant(disponible)} {unidad}.
                </p>
              )}
              {Number(valor || 0) > 0 && (
                <label style={{ display:'flex', alignItems:'center', gap:'6px', marginTop:'6px',
                  fontSize:'12px', color:C.textSec, cursor:'pointer' }}>
                  <input type="checkbox" checked={vuelveAlStock(item.item_id)}
                    onChange={e => setReingresa(r => ({ ...r, [item.item_id]: e.target.checked }))} />
                  Vuelve al stock vendible
                  {!vuelveAlStock(item.item_id) && (
                    <span style={{ color:C.warning }}>— queda registrada pero no se ofrece a la venta</span>
                  )}
                </label>
              )}
            </div>
          )
        })}

        {/* Qué se lleva */}
        <p style={{ ...etiqueta, marginTop:'18px' }}>
          Por qué producto se cambia{motivo === 'cambio' ? '' : ' (opcional)'}
        </p>
        <div style={{ position:'relative', marginBottom:'8px' }}>
          <Search size={15} style={{ position:'absolute', left:'12px', top:'12px', color:C.textMuted }} />
          <input value={busqueda} onChange={e => setBusqueda(e.target.value)}
            disabled={Boolean(venta.bloqueo)}
            placeholder="Buscar por nombre, código o color"
            style={{ ...input, paddingLeft:'34px',
              borderColor: faltaCambio ? C.dangerBorder : C.border }} />
          {buscando && (
            <Loader2 size={15} style={{ position:'absolute', right:'12px', top:'12px',
              color:C.textMuted, animation:'spin 1s linear infinite' }} />
          )}
        </div>
        {termino.length >= 2 && encontrados && (
          <div style={{ border:`1px solid ${C.border}`, borderRadius:'10px', marginBottom:'10px',
            maxHeight:'220px', overflowY:'auto' }}>
            {encontrados.length === 0 && (
              <p style={{ padding:'10px 12px', fontSize:'12.5px', color:C.textMuted }}>
                No se encontró nada con “{termino}”.
              </p>
            )}
            {encontrados.map(v => {
              const sinStock = Number(v.disponible) <= 0
              return (
                <button key={v.variante_id} type="button" disabled={sinStock}
                  onClick={() => agregarLlevado(v)}
                  style={{ display:'flex', justifyContent:'space-between', gap:'10px', width:'100%',
                    padding:'9px 12px', border:'none', borderBottom:`1px solid ${C.border}`,
                    background:'transparent', textAlign:'left',
                    cursor: sinStock ? 'not-allowed' : 'pointer', opacity: sinStock ? 0.5 : 1 }}>
                  <span style={{ minWidth:0 }}>
                    <span style={{ display:'block', fontSize:'13px', color:C.text }}>{v.descripcion}</span>
                    <span style={{ fontSize:'11px', color:C.textMuted }}>
                      {v.sku} · disponible {formatCant(v.disponible)} {UNIDAD[v.unidad_venta] || v.unidad_venta}
                    </span>
                  </span>
                  <span style={{ fontSize:'13px', fontWeight:'500', color:C.goldDark, flexShrink:0 }}>
                    {formatGs(v.precio_venta)}
                  </span>
                </button>
              )
            })}
          </div>
        )}
        {elegidos.length === 0 ? (
          <p style={{ fontSize:'11.5px', color:C.textMuted, marginBottom:'18px' }}>
            {motivo === 'cambio'
              ? 'Buscá y tocá el producto que se lleva el cliente.'
              : 'Si no se lleva nada, es una devolución.'}
          </p>
        ) : (
          <div style={{ marginBottom:'18px' }}>
            {elegidos.map(({ variante: v, cantidad }) => {
              const unidad = UNIDAD[v.unidad_venta] || v.unidad_venta
              const pasado = Number(cantidad) > Number(v.disponible)
              return (
                <div key={v.variante_id} style={{ padding:'10px 12px', marginBottom:'6px',
                  borderRadius:'10px', border:`1.5px solid ${C.gold}`, background:C.goldMuted }}>
                  <div style={{ display:'flex', alignItems:'center', gap:'10px' }}>
                    <div style={{ minWidth:0, flex:1 }}>
                      <p style={{ fontSize:'13px', fontWeight:'500', color:C.text }}>{v.descripcion}</p>
                      <p style={{ fontSize:'11px', color:C.textMuted }}>
                        {formatGs(v.precio_venta)} / {unidad}
                        {' · '}{formatGs(Number(cantidad || 0) * Number(v.precio_venta))}
                      </p>
                    </div>
                    <input type="number" min="0" step="0.01" value={cantidad}
                      onChange={e => cantidadLlevado(v.variante_id, e.target.value)}
                      style={{ ...input, width:'88px', textAlign:'right',
                        borderColor: pasado || !(Number(cantidad) > 0) ? C.dangerBorder : C.border }} />
                    <span style={{ fontSize:'12px', color:C.textMuted, width:'34px' }}>{unidad}</span>
                    <button type="button" onClick={() => quitarLlevado(v.variante_id)}
                      title="Quitar"
                      style={{ width:'32px', height:'32px', borderRadius:'8px', flexShrink:0,
                        border:`1px solid ${C.border}`, background:C.bg, color:C.textSec,
                        cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center' }}>
                      <X size={14} />
                    </button>
                  </div>
                  {pasado && (
                    <p style={{ fontSize:'11px', color:C.danger, marginTop:'4px' }}>
                      Hay {formatCant(v.disponible)} {unidad} disponibles.
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* Cuenta */}
        <div style={{ background:C.bgSec, border:`1px solid ${C.border}`, borderRadius:'12px',
          padding:'14px 16px', marginBottom:'16px' }}>
          <Renglon texto="A favor del cliente (lo que devuelve)" valor={formatGs(credito)} />
          {elegidos.length > 0 && <Renglon texto="Lo que se lleva" valor={formatGs(nuevo)} />}
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline',
            paddingTop:'10px', marginTop:'6px', borderTop:`2px solid ${C.border}` }}>
            <span style={{ fontSize:'14px', fontWeight:'600', color:C.text }}>
              {aCobrar > 0 ? 'El cliente paga' : aReintegrar > 0 ? 'Se le reintegra' : 'Sin diferencia'}
            </span>
            <span style={{ fontSize:'20px', fontWeight:'700',
              color: aReintegrar > 0 ? C.danger : C.goldDark }}>
              {formatGs(aCobrar || aReintegrar)}
            </span>
          </div>
        </div>

        {(aCobrar > 0 || aReintegrar > 0) && (
          <>
            <p style={etiqueta}>{aCobrar > 0 ? 'Cobrar la diferencia con' : 'Reintegrar con'}</p>
            <div style={{ display:'grid', gridTemplateColumns:'repeat(4, 1fr)', gap:'6px',
              marginBottom:'12px' }}>
              {MEDIOS.map(m => (
                <button key={m.key} onClick={() => setMedio(m.key)}
                  style={{ padding:'9px 4px', borderRadius:'9px', cursor:'pointer',
                    display:'flex', flexDirection:'column', alignItems:'center', gap:'3px',
                    fontSize:'11.5px',
                    background: medio === m.key ? C.sidebar : 'transparent',
                    border:`1.5px solid ${medio === m.key ? C.gold : C.border}`,
                    color: medio === m.key ? C.gold : C.textSec }}>
                  {m.icon}{m.label}
                </button>
              ))}
            </div>
            {aCobrar > 0 && medio === 'efectivo' && (
              <div style={{ marginBottom:'12px' }}>
                <input type="number" min="0" step="1000" value={recibido}
                  onChange={e => setRecibido(e.target.value)}
                  placeholder={`Monto recibido (mín. ${formatGs(aCobrar)})`}
                  style={{ ...input, textAlign:'right',
                    borderColor: recibido && faltaEfectivo ? C.dangerBorder : C.border }} />
                {Number(recibido) > aCobrar && (
                  <p style={{ fontSize:'12.5px', color:C.success, marginTop:'5px', fontWeight:'500' }}>
                    Vuelto: {formatGs(Number(recibido) - aCobrar)}
                  </p>
                )}
              </div>
            )}
          </>
        )}

        <textarea value={observaciones} onChange={e => setObservaciones(e.target.value)}
          placeholder="Observaciones (opcional)" rows={2}
          style={{ ...input, height:'auto', padding:'10px 12px', resize:'vertical',
            fontFamily:'inherit', fontSize:'13px' }} />
      </div>

      {/* Footer */}
      <div style={{ padding:'14px 20px', borderTop:`1px solid ${C.border}`,
        display:'flex', gap:'10px', flexShrink:0 }}>
        <button onClick={onCancelar}
          style={{ flex:1, height:'46px', borderRadius:'10px', background:'transparent',
            border:`1px solid ${C.border}`, color:C.textSec, fontSize:'14px', cursor:'pointer' }}>
          Cancelar
        </button>
        <button onClick={() => confirmarMut.mutate()}
          disabled={!puedeConfirmar || confirmarMut.isPending}
          style={{ flex:2, height:'46px', borderRadius:'10px',
            background: puedeConfirmar ? C.sidebar : C.bgTer,
            border:`1.5px solid ${puedeConfirmar ? C.gold : C.border}`,
            color: puedeConfirmar ? C.gold : C.textMuted,
            fontSize:'14px', fontWeight:'500',
            cursor: puedeConfirmar ? 'pointer' : 'not-allowed',
            display:'flex', alignItems:'center', justifyContent:'center', gap:'7px' }}>
          {confirmarMut.isPending
            ? <><Loader2 size={16} style={{ animation:'spin 1s linear infinite' }}/> Registrando...</>
            : <><RotateCcw size={16}/> Confirmar {elegidos.length > 0 ? 'cambio' : 'devolución'}</>}
        </button>
      </div>
    </div>
  )
}

function Renglon({ texto, valor }) {
  return (
    <div style={{ display:'flex', justifyContent:'space-between', marginBottom:'6px' }}>
      <span style={{ fontSize:'13px', color:C.textSec }}>{texto}</span>
      <span style={{ fontSize:'13.5px', color:C.text, fontWeight:'500' }}>{valor}</span>
    </div>
  )
}

/** Lo que queda en pantalla después de confirmar (o al reimprimir). */
export function ComprobanteDevolucion({ datos, onCerrar, onReimprimir, reimprimiendo }) {
  const c = datos.comprobante
  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>
      <div style={{ padding:'16px 20px', borderBottom:`1px solid ${C.border}`,
        display:'flex', alignItems:'center', gap:'10px', flexShrink:0 }}>
        <CheckCircle size={22} style={{ color:C.success }} />
        <div>
          <h2 style={{ fontSize:'17px', fontWeight:'500', fontFamily:'var(--font-display)',
            color:C.text }}>
            {c.pedido_cambio ? 'Cambio registrado' : 'Devolución registrada'}
          </h2>
          <p style={{ fontSize:'12px', color:C.textMuted, fontFamily:'monospace' }}>{c.numero}</p>
        </div>
      </div>
      <div style={{ flex:1, overflowY:'auto', padding:'18px 20px' }}>
        {c.a_reintegrar > 0 && (
          <p style={{ padding:'12px 14px', borderRadius:'10px', marginBottom:'14px',
            background:C.warningBg, border:`1px solid ${C.warningBorder}`,
            color:C.warning, fontSize:'14px', fontWeight:'500' }}>
            Entregale al cliente {formatGs(c.a_reintegrar)} ({c.medio_reintegro.toLowerCase()}).
          </p>
        )}
        {c.a_cobrar > 0 && c.vuelto > 0 && (
          <p style={{ padding:'12px 14px', borderRadius:'10px', marginBottom:'14px',
            background:C.successBg, border:`1px solid ${C.successBorder}`,
            color:C.success, fontSize:'14px', fontWeight:'500' }}>
            Vuelto: {formatGs(c.vuelto)}
          </p>
        )}
        <pre style={{ fontFamily:"'Courier New', monospace", fontSize:'12px', lineHeight:1.45,
          background:C.bgSec, border:`1px solid ${C.border}`, borderRadius:'10px',
          padding:'14px', whiteSpace:'pre-wrap', color:C.text }}>
          {datos.texto}
        </pre>
      </div>
      <div style={{ padding:'14px 20px', borderTop:`1px solid ${C.border}`,
        display:'flex', gap:'10px', flexShrink:0 }}>
        {onReimprimir && (
          <button onClick={onReimprimir} disabled={reimprimiendo}
            style={{ flex:1, height:'46px', borderRadius:'10px', background:'transparent',
              border:`1px solid ${C.border}`, color:C.textSec, fontSize:'14px', cursor:'pointer',
              display:'flex', alignItems:'center', justifyContent:'center', gap:'6px' }}>
            <Printer size={15}/> Reimprimir
          </button>
        )}
        <button onClick={onCerrar}
          style={{ flex:2, height:'46px', borderRadius:'10px', background:C.sidebar,
            border:`1.5px solid ${C.gold}`, color:C.gold, fontSize:'14px', fontWeight:'500',
            cursor:'pointer' }}>
          Listo
        </button>
      </div>
    </div>
  )
}
