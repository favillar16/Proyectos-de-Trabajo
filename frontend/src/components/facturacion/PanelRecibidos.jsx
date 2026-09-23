/**
 * Recibidos: lo que el local declara sobre un DTE que le emitió OTRO.
 *
 * Es el otro lado del mostrador, y por eso es una pestaña aparte y no un
 * panel más de la cola: la cola lista documentos **propios**, con su número y
 * su estado ante la DNIT. Acá el documento es de un proveedor y lo único que
 * tenemos de él es su CDC. Mezclarlos en la misma lista habría hecho que
 * "estado" significara dos cosas distintas según la fila.
 *
 * Los cuatro eventos (Manual §11.2.5), y la diferencia que importa:
 *
 *   · **Conclusivos** — conformidad y disconformidad. Pueden obligar al
 *     emisor a hacer algo: emitir una nota de crédito, cancelar el DTE.
 *   · **Informativos** — desconocimiento y notificación. Dejan una marca y
 *     no generan ninguna acción del otro lado.
 *
 * La pantalla lo dice explícitamente porque es lo que decide cuál usar, y no
 * se deduce del nombre.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Loader2, CheckCircle, Inbox } from 'lucide-react'
import toast from 'react-hot-toast'

import { facturacionApi } from '../../services/api'
import { C, campo, etiqueta, formatFecha } from './estilos'

const TIPOS = [
  { clave:'conformidad', label:'Conformidad', conclusivo:true,
    ayuda:'Se acepta el documento. Total, o parcial declarando cuándo se estima recibir.' },
  { clave:'disconformidad', label:'Disconformidad', conclusivo:true,
    ayuda:'Se rechaza, con motivo. Puede obligar al emisor a emitir una nota de crédito.' },
  { clave:'desconocimiento', label:'Desconocimiento', conclusivo:false,
    ayuda:'"Este documento no es mío, yo no hice esta operación".' },
  { clave:'notificacion', label:'Notificación de recepción', conclusivo:false,
    ayuda:'"Lo recibí, todavía no me expido". Es opcional.' },
]

const VACIO = {
  tipo: 'conformidad', cdc: '', tipo_conformidad: 1,
  fecha_recepcion: '', fecha_emision_documento: '', total_documento: '',
  motivo: '',
}

export default function PanelRecibidos() {
  const queryClient = useQueryClient()
  const [abierto, setAbierto] = useState(false)
  const [datos, setDatos] = useState({ ...VACIO })

  const { data: eventos = [] } = useQuery({
    queryKey: ['fe-eventos-receptor'],
    queryFn: () => facturacionApi.eventosReceptor().then(r => r.data),
  })

  const registrar = useMutation({
    mutationFn: () => facturacionApi.registrarEventoReceptor(datos),
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: ['fe-eventos-receptor'] })
      toast.success(`Evento registrado (${r.data.estado_display})`)
      setAbierto(false)
      setDatos({ ...VACIO })
    },
    onError: (err) => toast.error(
      err.response?.data?.error || 'No se pudo registrar el evento'),
  })

  const set = (k) => (e) => setDatos(d => ({ ...d, [k]: e.target.value }))
  const tipo = TIPOS.find(t => t.clave === datos.tipo)

  // Qué campos pide cada tipo. Se decide acá y no se muestran todos porque
  // un formulario con ocho campos de los que sirven tres invita a llenar
  // cualquier cosa — y el SIFEN rechaza lo que sobra igual que lo que falta.
  const pideMotivo = ['disconformidad', 'desconocimiento'].includes(datos.tipo)
  const pideFechas = ['desconocimiento', 'notificacion'].includes(datos.tipo)
  const pideTotal = datos.tipo === 'notificacion'
  const pideFechaRecepcion = pideFechas
    || (datos.tipo === 'conformidad' && Number(datos.tipo_conformidad) === 2)

  return (
    <div>
      <div style={{ display:'flex', alignItems:'center', gap:'12px',
        marginBottom:'16px', flexWrap:'wrap' }}>
        <p style={{ flex:1, minWidth:'220px', fontSize:'13px', color:C.textSec,
          margin:0, maxWidth:'64ch' }}>
          Lo que el local declara ante la DNIT sobre una factura que le emitió
          un <b>proveedor</b>. Se identifica por su CDC: ese documento no está
          en esta base, lo emitió otro.
        </p>
        <button onClick={() => setAbierto(a => !a)} style={{
          display:'flex', alignItems:'center', gap:'7px',
          padding:'9px 15px', borderRadius:'9px', cursor:'pointer',
          background: abierto ? 'transparent' : C.sidebar,
          border:`1px solid ${abierto ? C.border : C.gold}`,
          color: abierto ? C.textSec : C.gold, fontSize:'13px' }}>
          <Plus size={15}/> {abierto ? 'Cerrar' : 'Registrar evento'}
        </button>
      </div>

      {abierto && (
        <div style={{ border:`1px solid ${C.border}`, borderRadius:'11px',
          padding:'16px', marginBottom:'20px', background:C.bgSec }}>

          <div style={{ display:'grid', gap:'8px', marginBottom:'12px',
            gridTemplateColumns:'repeat(auto-fit, minmax(175px, 1fr))' }}>
            {TIPOS.map(t => (
              <button key={t.clave}
                onClick={() => setDatos(d => ({ ...VACIO, cdc: d.cdc, tipo: t.clave }))}
                style={{ padding:'10px 12px', borderRadius:'9px', cursor:'pointer',
                  textAlign:'left', fontFamily:'inherit',
                  background: datos.tipo === t.clave ? C.sidebar : C.bg,
                  border:`1.5px solid ${datos.tipo === t.clave ? C.gold : C.border}`,
                  color: datos.tipo === t.clave ? C.gold : C.textSec }}>
                <span style={{ fontSize:'13px', fontWeight:'500',
                  display:'block' }}>{t.label}</span>
                <span style={{ fontSize:'10.5px', opacity:0.85 }}>
                  {t.conclusivo ? 'Conclusivo' : 'Informativo'}
                </span>
              </button>
            ))}
          </div>

          <p style={{ fontSize:'12px', color:C.textMuted, margin:'0 0 14px' }}>
            {tipo?.ayuda}
          </p>

          <div style={{ marginBottom:'10px' }}>
            <label style={etiqueta}>CDC del documento del proveedor * (44 dígitos)</label>
            <input value={datos.cdc} onChange={set('cdc')}
              style={{ ...campo, fontFamily:'monospace' }}
              placeholder="01801731070001001000000122026091618831372117" />
            <p style={{ fontSize:'11px', color:C.textMuted, margin:'4px 0 0' }}>
              {datos.cdc.replace(/\s/g, '').length}/44
            </p>
          </div>

          {datos.tipo === 'conformidad' && (
            <div style={{ marginBottom:'10px' }}>
              <label style={etiqueta}>Tipo de conformidad</label>
              <select value={datos.tipo_conformidad}
                onChange={set('tipo_conformidad')}
                style={{ ...campo, cursor:'pointer' }}>
                <option value={1}>Total</option>
                <option value={2}>Parcial</option>
              </select>
            </div>
          )}

          {pideMotivo && (
            <div style={{ marginBottom:'10px' }}>
              <label style={etiqueta}>Motivo * (entre 5 y 500 caracteres)</label>
              <textarea value={datos.motivo} onChange={set('motivo')} rows={3}
                style={{ ...campo, resize:'vertical' }}
                placeholder="Ej: la mercadería facturada nunca se entregó" />
            </div>
          )}

          <div style={{ display:'grid', gap:'10px', marginBottom:'14px',
            gridTemplateColumns:'repeat(auto-fit, minmax(175px, 1fr))' }}>
            {pideFechas && (
              <div>
                <label style={etiqueta}>Fecha de emisión del documento *</label>
                <input type="datetime-local"
                  value={datos.fecha_emision_documento}
                  onChange={set('fecha_emision_documento')} style={campo} />
              </div>
            )}
            {pideFechaRecepcion && (
              <div>
                <label style={etiqueta}>
                  Fecha {datos.tipo === 'conformidad' ? 'estimada ' : ''}de recepción *
                </label>
                <input type="datetime-local" value={datos.fecha_recepcion}
                  onChange={set('fecha_recepcion')} style={campo} />
              </div>
            )}
            {pideTotal && (
              <div>
                <label style={etiqueta}>Total del documento (Gs) *</label>
                <input value={datos.total_documento}
                  onChange={set('total_documento')} style={campo}
                  inputMode="numeric" placeholder="500000" />
              </div>
            )}
          </div>

          <button onClick={() => registrar.mutate()}
            disabled={registrar.isPending || datos.cdc.trim().length !== 44}
            style={{ display:'flex', alignItems:'center', gap:'7px',
              padding:'10px 17px', borderRadius:'9px',
              cursor: datos.cdc.trim().length === 44 ? 'pointer' : 'not-allowed',
              opacity: datos.cdc.trim().length === 44 ? 1 : 0.5,
              background:C.sidebar, border:`1px solid ${C.gold}`,
              color:C.gold, fontSize:'13px' }}>
            {registrar.isPending
              ? <Loader2 size={15} style={{ animation:'spin 1s linear infinite' }}/>
              : <CheckCircle size={15}/>}
            Registrar y transmitir
          </button>
        </div>
      )}

      <div style={{ border:`1px solid ${C.border}`, borderRadius:'11px',
        overflow:'hidden' }}>
        <div style={{ padding:'11px 15px', background:C.bgSec,
          borderBottom:`1px solid ${C.border}`, fontSize:'13px',
          fontWeight:'600', color:C.text }}>
          Eventos registrados ({eventos.length})
        </div>
        {eventos.length === 0 ? (
          <p style={{ padding:'14px 15px', fontSize:'12.5px',
            color:C.textMuted, margin:0 }}>
            Todavía no se declaró nada sobre un documento de proveedor.
          </p>
        ) : eventos.map(e => (
          <div key={e.id} style={{ display:'flex', alignItems:'center',
            gap:'12px', padding:'9px 15px',
            borderBottom:`1px solid ${C.border}`, flexWrap:'wrap' }}>
            <Inbox size={14} color={C.textMuted} style={{ flexShrink:0 }}/>
            <span style={{ fontSize:'12.5px', color:C.text, minWidth:'150px' }}>
              {e.tipo_display}
              <span style={{ fontSize:'10.5px', color:C.textMuted,
                marginLeft:'6px' }}>
                {e.conclusivo ? 'conclusivo' : 'informativo'}
              </span>
            </span>
            <span style={{ fontSize:'11px', fontFamily:'monospace',
              color:C.textSec, flex:1, minWidth:'150px', overflow:'hidden',
              textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
              {e.cdc_legible || e.cdc}
            </span>
            <span style={{ fontSize:'11.5px', color:C.textMuted,
              minWidth:'110px' }}>{formatFecha(e.fecha_creacion)}</span>
            <span style={{ fontSize:'11.5px', color:C.textSec }}>
              {e.estado_display}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
