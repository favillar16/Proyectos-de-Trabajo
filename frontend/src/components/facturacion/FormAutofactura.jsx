/**
 * Autofactura: el comprobante de una COMPRA a alguien que no puede facturar.
 *
 * Es el único documento que se **crea** desde la pantalla de facturación, y
 * por eso tiene pestaña propia en vez de ser un panel más: todo lo demás de
 * esa pantalla mira documentos que ya existen (la cola, los lotes, los
 * recibidos). Mezclarlo con esos habría puesto un formulario largo en medio
 * de tres listas.
 *
 * No duplica nada del flujo de ventas: una autofactura no tiene pedido, ni
 * cliente, ni pasa por caja. El vendedor es la contraparte de una compra, no
 * un cliente del padrón — buscarlo ahí no tendría sentido.
 *
 * Los códigos geográficos salen del backend (`/facturacion/geografia/`), que
 * los lee de la librería de la DNIT. No se copian acá: son tablas del
 * organismo y una segunda copia quedaría desfasada.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Loader2, CheckCircle, FileText } from 'lucide-react'
import toast from 'react-hot-toast'

import { facturacionApi } from '../../services/api'
import { C, campo, etiqueta, formatGs, formatFecha } from './estilos'

const ITEM_VACIO = { descripcion: '', cantidad: '1', precio_unitario: '' }

/**
 * Selector de departamento → distrito → ciudad.
 *
 * Los tres van juntos porque el SIFEN los pide juntos (código y descripción
 * de cada nivel) y porque elegir un distrito de otro departamento es el error
 * que más rechazos genera. Cada nivel se habilita cuando el anterior tiene
 * valor: así no se puede armar una combinación imposible.
 */
function SelectorGeografico({ valor, onCambio, sufijo }) {
  const { data: deps } = useQuery({
    queryKey: ['fe-geografia'],
    queryFn: () => facturacionApi.geografia().then(r => r.data.departamentos || []),
    staleTime: Infinity,   // es una tabla fija: no tiene sentido recargarla
  })
  const { data: distritos } = useQuery({
    queryKey: ['fe-geografia', 'dis', valor[`departamento_${sufijo}`]],
    queryFn: () => facturacionApi
      .geografia({ departamento: valor[`departamento_${sufijo}`] })
      .then(r => r.data.distritos || []),
    enabled: Boolean(valor[`departamento_${sufijo}`]),
    staleTime: Infinity,
  })
  const { data: ciudades } = useQuery({
    queryKey: ['fe-geografia', 'ciu', valor[`distrito_${sufijo}`]],
    queryFn: () => facturacionApi
      .geografia({ distrito: valor[`distrito_${sufijo}`] })
      .then(r => r.data.ciudades || []),
    enabled: Boolean(valor[`distrito_${sufijo}`]),
    staleTime: Infinity,
  })

  // Cada nivel guarda código Y descripción: el XML lleva los dos, y
  // reconstruir la descripción después obligaría a tener la tabla dos veces.
  const elegir = (nivel, lista) => (e) => {
    const codigo = e.target.value
    const fila = (lista || []).find(x => String(x.codigo ?? x.id) === codigo)
    const cambios = {
      [`${nivel}_${sufijo}`]: codigo ? Number(codigo) : '',
      [`${nivel}_${sufijo}_desc`]: fila ? (fila.descripcion ?? fila.nombre ?? '') : '',
    }
    // Al cambiar un nivel, los de abajo dejan de ser válidos.
    if (nivel === 'departamento') {
      Object.assign(cambios, {
        [`distrito_${sufijo}`]: '', [`distrito_${sufijo}_desc`]: '',
        [`ciudad_${sufijo}`]: '', [`ciudad_${sufijo}_desc`]: '',
      })
    } else if (nivel === 'distrito') {
      Object.assign(cambios, {
        [`ciudad_${sufijo}`]: '', [`ciudad_${sufijo}_desc`]: '',
      })
    }
    onCambio(cambios)
  }

  const select = (nivel, lista, etiquetaTexto, habilitado) => (
    <div>
      <label style={etiqueta}>{etiquetaTexto}</label>
      <select
        value={valor[`${nivel}_${sufijo}`] || ''}
        onChange={elegir(nivel, lista)}
        disabled={!habilitado}
        style={{ ...campo, cursor: habilitado ? 'pointer' : 'not-allowed',
          opacity: habilitado ? 1 : 0.55 }}>
        <option value="">—</option>
        {(lista || []).map(x => (
          <option key={x.codigo ?? x.id} value={x.codigo ?? x.id}>
            {x.descripcion ?? x.nombre}
          </option>
        ))}
      </select>
    </div>
  )

  return (
    <div style={{ display:'grid', gap:'10px',
      gridTemplateColumns:'repeat(auto-fit, minmax(160px, 1fr))' }}>
      {select('departamento', deps, 'Departamento', true)}
      {select('distrito', distritos, 'Distrito',
        Boolean(valor[`departamento_${sufijo}`]))}
      {select('ciudad', ciudades, 'Ciudad',
        Boolean(valor[`distrito_${sufijo}`]))}
    </div>
  )
}

export default function FormAutofactura() {
  const queryClient = useQueryClient()
  const [abierto, setAbierto] = useState(false)
  const [vendedor, setVendedor] = useState({
    naturaleza_vendedor: 1,
    tipo_documento_vendedor: 1,
    numero_documento_vendedor: '', nombre_vendedor: '',
    direccion_vendedor: '', numero_casa_vendedor: '0',
    departamento_vendedor: '', departamento_vendedor_desc: '',
    distrito_vendedor: '', distrito_vendedor_desc: '',
    ciudad_vendedor: '', ciudad_vendedor_desc: '',
    lugar_transaccion: '',
    departamento_transaccion: '', departamento_transaccion_desc: '',
    distrito_transaccion: '', distrito_transaccion_desc: '',
    ciudad_transaccion: '', ciudad_transaccion_desc: '',
  })
  const [items, setItems] = useState([{ ...ITEM_VACIO }])

  const { data: emitidas = [] } = useQuery({
    queryKey: ['fe-autofacturas'],
    queryFn: () => facturacionApi.autofacturas().then(r => r.data),
  })

  const emitir = useMutation({
    mutationFn: () => facturacionApi.emitirAutofactura({ vendedor, items }),
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: ['fe-autofacturas'] })
      queryClient.invalidateQueries({ queryKey: ['fe-documentos'] })
      toast.success(`Autofactura ${r.data.autofactura.numero} emitida`)
      setAbierto(false)
      setItems([{ ...ITEM_VACIO }])
    },
    onError: (err) => toast.error(
      err.response?.data?.error || 'No se pudo emitir la autofactura'),
  })

  const set = (k) => (e) => setVendedor(v => ({ ...v, [k]: e.target.value }))
  const setItem = (i, k) => (e) => setItems(lista =>
    lista.map((it, j) => (j === i ? { ...it, [k]: e.target.value } : it)))

  const total = items.reduce(
    (a, it) => a + (Number(it.cantidad) || 0) * (Number(it.precio_unitario) || 0), 0)

  return (
    <div>
      <div style={{ display:'flex', alignItems:'center', gap:'12px',
        marginBottom:'16px', flexWrap:'wrap' }}>
        <div style={{ flex:1, minWidth:'220px' }}>
          <p style={{ fontSize:'13px', color:C.textSec, margin:0, maxWidth:'62ch' }}>
            La autofactura respalda una <b>compra</b> a alguien que no puede
            emitir factura — un particular, alguien sin RUC. No es una venta:
            no tiene pedido, no pasa por caja y no mueve stock.
          </p>
        </div>
        <button onClick={() => setAbierto(a => !a)} style={{
          display:'flex', alignItems:'center', gap:'7px',
          padding:'9px 15px', borderRadius:'9px', cursor:'pointer',
          background: abierto ? 'transparent' : C.sidebar,
          border:`1px solid ${abierto ? C.border : C.gold}`,
          color: abierto ? C.textSec : C.gold, fontSize:'13px' }}>
          <Plus size={15}/> {abierto ? 'Cerrar' : 'Nueva autofactura'}
        </button>
      </div>

      {abierto && (
        <div style={{ border:`1px solid ${C.border}`, borderRadius:'11px',
          padding:'16px', marginBottom:'20px', background:C.bgSec }}>

          <h4 style={{ fontSize:'12.5px', fontWeight:'600', color:C.textMuted,
            textTransform:'uppercase', letterSpacing:'0.05em', margin:'0 0 11px' }}>
            Vendedor
          </h4>
          <div style={{ display:'grid', gap:'10px', marginBottom:'12px',
            gridTemplateColumns:'repeat(auto-fit, minmax(170px, 1fr))' }}>
            <div>
              <label style={etiqueta}>Nombre y apellido *</label>
              <input value={vendedor.nombre_vendedor}
                onChange={set('nombre_vendedor')} style={campo}
                placeholder="Juan Pérez" />
            </div>
            <div>
              <label style={etiqueta}>Cédula *</label>
              <input value={vendedor.numero_documento_vendedor}
                onChange={set('numero_documento_vendedor')} style={campo}
                placeholder="1234567" />
            </div>
            <div>
              <label style={etiqueta}>Dirección *</label>
              <input value={vendedor.direccion_vendedor}
                onChange={set('direccion_vendedor')} style={campo}
                placeholder="Calle y número" />
            </div>
          </div>
          <div style={{ marginBottom:'16px' }}>
            <SelectorGeografico
              valor={vendedor} sufijo="vendedor"
              onCambio={(c) => setVendedor(v => ({ ...v, ...c }))} />
          </div>

          <h4 style={{ fontSize:'12.5px', fontWeight:'600', color:C.textMuted,
            textTransform:'uppercase', letterSpacing:'0.05em', margin:'0 0 4px' }}>
            Dónde ocurrió la operación
          </h4>
          <p style={{ fontSize:'11.5px', color:C.textMuted, margin:'0 0 11px' }}>
            El SIFEN lo pide aparte del domicilio del vendedor: no tienen por
            qué coincidir.
          </p>
          <div style={{ marginBottom:'10px' }}>
            <label style={etiqueta}>Lugar *</label>
            <input value={vendedor.lugar_transaccion}
              onChange={set('lugar_transaccion')} style={campo}
              placeholder="Local de Óga Porã" />
          </div>
          <div style={{ marginBottom:'16px' }}>
            <SelectorGeografico
              valor={vendedor} sufijo="transaccion"
              onCambio={(c) => setVendedor(v => ({ ...v, ...c }))} />
          </div>

          <h4 style={{ fontSize:'12.5px', fontWeight:'600', color:C.textMuted,
            textTransform:'uppercase', letterSpacing:'0.05em', margin:'0 0 4px' }}>
            Qué se compró
          </h4>
          <p style={{ fontSize:'11.5px', color:C.textMuted, margin:'0 0 11px' }}>
            Se escribe a mano: lo comprado a un particular no está en el
            catálogo. Va exento — comprarle a un no contribuyente no genera
            crédito fiscal.
          </p>
          {items.map((it, i) => (
            <div key={i} style={{ display:'flex', gap:'8px', marginBottom:'8px',
              alignItems:'flex-end', flexWrap:'wrap' }}>
              <div style={{ flex:3, minWidth:'170px' }}>
                <label style={etiqueta}>Descripción</label>
                <input value={it.descripcion} onChange={setItem(i, 'descripcion')}
                  style={campo} placeholder="Lote de cerámica usada" />
              </div>
              <div style={{ flex:1, minWidth:'90px' }}>
                <label style={etiqueta}>Cantidad</label>
                <input value={it.cantidad} onChange={setItem(i, 'cantidad')}
                  style={campo} inputMode="decimal" />
              </div>
              <div style={{ flex:1, minWidth:'110px' }}>
                <label style={etiqueta}>Precio unit.</label>
                <input value={it.precio_unitario}
                  onChange={setItem(i, 'precio_unitario')}
                  style={campo} inputMode="numeric" placeholder="25000" />
              </div>
              <button
                onClick={() => setItems(l => l.filter((_, j) => j !== i))}
                disabled={items.length === 1}
                title="Quitar ítem"
                style={{ height:'36px', width:'36px', borderRadius:'8px',
                  border:`1px solid ${C.border}`, background:C.bg,
                  color: items.length === 1 ? C.textMuted : C.danger,
                  cursor: items.length === 1 ? 'not-allowed' : 'pointer',
                  display:'flex', alignItems:'center', justifyContent:'center' }}>
                <Trash2 size={14}/>
              </button>
            </div>
          ))}
          <button onClick={() => setItems(l => [...l, { ...ITEM_VACIO }])}
            style={{ display:'flex', alignItems:'center', gap:'6px',
              padding:'6px 11px', borderRadius:'8px', cursor:'pointer',
              background:'transparent', border:`1px dashed ${C.border}`,
              color:C.textSec, fontSize:'12.5px', marginTop:'2px' }}>
            <Plus size={13}/> Agregar ítem
          </button>

          <div style={{ display:'flex', alignItems:'center', gap:'12px',
            marginTop:'18px', paddingTop:'14px',
            borderTop:`1px solid ${C.border}`, flexWrap:'wrap' }}>
            <span style={{ fontSize:'14px', fontWeight:'600', color:C.goldDark,
              flex:1 }}>
              Total: {formatGs(total)}
            </span>
            <button onClick={() => emitir.mutate()} disabled={emitir.isPending}
              style={{ display:'flex', alignItems:'center', gap:'7px',
                padding:'10px 17px', borderRadius:'9px', cursor:'pointer',
                background:C.sidebar, border:`1px solid ${C.gold}`,
                color:C.gold, fontSize:'13px' }}>
              {emitir.isPending
                ? <Loader2 size={15} style={{ animation:'spin 1s linear infinite' }}/>
                : <CheckCircle size={15}/>}
              Emitir autofactura
            </button>
          </div>
        </div>
      )}

      <div style={{ border:`1px solid ${C.border}`, borderRadius:'11px',
        overflow:'hidden' }}>
        <div style={{ padding:'11px 15px', background:C.bgSec,
          borderBottom:`1px solid ${C.border}`, fontSize:'13px',
          fontWeight:'600', color:C.text }}>
          Autofacturas emitidas ({emitidas.length})
        </div>
        {emitidas.length === 0 ? (
          <p style={{ padding:'14px 15px', fontSize:'12.5px',
            color:C.textMuted, margin:0 }}>
            Todavía no se emitió ninguna.
          </p>
        ) : emitidas.map(a => (
          <div key={a.id} style={{ display:'flex', alignItems:'center',
            gap:'12px', padding:'9px 15px',
            borderBottom:`1px solid ${C.border}`, flexWrap:'wrap' }}>
            <FileText size={14} color={C.textMuted} style={{ flexShrink:0 }}/>
            <span style={{ fontSize:'12px', fontFamily:'monospace',
              color:C.textSec, minWidth:'125px' }}>{a.numero}</span>
            <span style={{ fontSize:'11.5px', color:C.textMuted,
              minWidth:'110px' }}>{formatFecha(a.fecha_emision)}</span>
            <span style={{ fontSize:'12.5px', color:C.text, flex:1,
              minWidth:'130px' }}>{a.vendedor || '—'}</span>
            <span style={{ fontSize:'12.5px', fontWeight:'600',
              color:C.goldDark }}>{formatGs(a.total)}</span>
            <span style={{ fontSize:'11.5px', color:C.textSec }}>
              {a.estado_display}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
