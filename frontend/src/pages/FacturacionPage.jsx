/**
 * FacturacionPage — panel de facturación electrónica (solo admin)
 *
 * Lo que resuelve: hasta ahora, para saber si un documento estaba trabado
 * había que entrar al servidor y correr `manage.py sifen_transmitir --listar`.
 * Acá se ve la cola, se descarga el KuDE que se le entrega al cliente, se
 * cancela un documento dentro del plazo y se declaran los números de
 * comprobante que quedaron sin usar.
 *
 * Tres cosas que la pantalla tiene que dejar claras, porque son las que se
 * malinterpretan:
 *
 *  1. **Cancelar no es lo mismo que una nota de crédito.** La cancelación
 *     anula el comprobante ante la DNIT y tiene plazo: 48 horas desde que el
 *     SIFEN lo aprobó (168 para notas y remisiones). Pasado eso, la
 *     corrección va por nota de crédito. El plazo se muestra en horas para
 *     que no haya que calcularlo.
 *  2. **Inutilizar es para números que nunca fueron un comprobante.** Un
 *     número emitido no se inutiliza: se cancela. El backend lo rechaza, pero
 *     la pantalla ni siquiera ofrece números usados — muestra solo los huecos
 *     reales del correlativo.
 *  3. **El KuDE no es la factura.** Es la representación gráfica del
 *     documento electrónico, que es el XML aprobado.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  FileText, RefreshCw, AlertCircle, CheckCircle, Clock, XCircle,
  Ban, FileWarning, Loader2, Send, FileMinus, FilePlus,
} from 'lucide-react'
import Layout from '../components/layout/Layout'
import FormAutofactura from '../components/facturacion/FormAutofactura'
import PanelRecibidos from '../components/facturacion/PanelRecibidos'
import ModalNota from '../components/facturacion/ModalNota'
// La paleta y los formateadores viven en un modulo compartido: las tres
// vistas de facturacion son partes de la misma pantalla y tener tres copias
// del mismo marron garantiza que un dia queden distintas.
import { C, formatGs, formatFecha } from '../components/facturacion/estilos'
import { facturacionApi } from '../services/api'
import toast from 'react-hot-toast'

/**
 * Las secciones de la pantalla.
 *
 * Están agrupadas por LA PREGUNTA QUE CONTESTAN, no por funcionalidad, que es
 * lo que evita que se encimen:
 *
 *   · Emitidos    — ¿qué emitimos y en qué estado está? (incluye los números
 *                   que quedaron sin usar, que son de nuestra numeración)
 *   · Transmisión — ¿qué mandamos y qué no llegó a mandarse?
 *   · Autofactura — lo único que se CREA acá: compras a no contribuyentes
 *   · Recibidos   — documentos que otros nos emitieron a nosotros
 *
 * Antes estaba todo apilado en una sola columna. Con dos pantallas más habría
 * quedado un scroll de cinco paneles donde "estado" significaba cosas
 * distintas según dónde se mirara.
 */
const SECCIONES = [
  { clave:'emitidos',    label:'Emitidos' },
  { clave:'transmision', label:'Transmisión' },
  { clave:'autofactura', label:'Autofactura' },
  { clave:'recibidos',   label:'Recibidos' },
]


const ESTADO_CFG = {
  pendiente: { label:'Pendiente de envío', color:C.info,    bg:C.infoBg,    icon:<Clock size={12}/> },
  firmado:   { label:'Firmado',            color:C.info,    bg:C.infoBg,    icon:<Clock size={12}/> },
  enviado:   { label:'Enviado',            color:C.warning, bg:C.warningBg, icon:<Send size={12}/> },
  aprobado:  { label:'Aprobado',           color:C.success, bg:C.successBg, icon:<CheckCircle size={12}/> },
  rechazado: { label:'Rechazado',          color:C.danger,  bg:C.dangerBg,  icon:<XCircle size={12}/> },
  cancelado: { label:'Cancelado',          color:C.textSec, bg:C.bgTer,     icon:<Ban size={12}/> },
}


// Las horas se redondean hacia abajo a propósito: decir "quedan 2 h" cuando
// quedan 2,9 es el error seguro; decir 3 cuando quedan 2,1 no lo es.
function plazoLegible(horas) {
  if (horas == null) return null
  if (horas <= 0) return 'vencido'
  if (horas < 1) return `${Math.floor(horas * 60)} min`
  return `${Math.floor(horas)} h`
}

function Badge({ estado }) {
  const cfg = ESTADO_CFG[estado] || ESTADO_CFG.pendiente
  return (
    <span style={{ display:'inline-flex', alignItems:'center', gap:'4px',
      padding:'3px 9px', borderRadius:'20px', background:cfg.bg, color:cfg.color,
      border:`1px solid ${cfg.color}33`, fontSize:'11px', fontWeight:'500',
      whiteSpace:'nowrap' }}>
      {cfg.icon} {cfg.label}
    </span>
  )
}

// ─── Modal de cancelación ─────────────────────────────────────────────────────
function ModalCancelar({ documento, onCerrar }) {
  const queryClient = useQueryClient()
  const [motivo, setMotivo] = useState('')
  const plazo = plazoLegible(documento.horas_para_cancelar)

  const cancelar = useMutation({
    mutationFn: () => facturacionApi.cancelar(documento.id, motivo).then(r => r.data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['fe-documentos'] })
      const estado = data?.evento?.estado
      if (estado === 'aprobado') {
        toast.success('El SIFEN aceptó la cancelación')
      } else if (estado === 'rechazado') {
        toast.error('El SIFEN rechazó la cancelación — mirá el detalle en la cola')
      } else {
        toast('Cancelación registrada: se transmite en la próxima corrida',
          { icon:'🕓', duration:6000 })
      }
      onCerrar()
    },
    onError: (err) => toast.error(err.response?.data?.error || 'No se pudo cancelar'),
  })

  return (
    <>
      <div onClick={onCerrar} style={{ position:'fixed', inset:0, zIndex:300,
        background:'rgba(26,23,20,0.45)', backdropFilter:'blur(2px)' }} />
      <div style={{ position:'fixed', zIndex:301, top:'50%', left:'50%',
        transform:'translate(-50%,-50%)', width:'min(520px,94vw)',
        background:C.bg, borderRadius:'14px', border:`1px solid ${C.border}`,
        boxShadow:'0 20px 60px rgba(0,0,0,0.22)', padding:'22px' }}>
        <h2 style={{ fontSize:'17px', fontWeight:'600', color:C.text, marginBottom:'4px' }}>
          Cancelar {documento.tipo_descripcion}
        </h2>
        <p style={{ fontSize:'13px', color:C.textSec, marginBottom:'14px' }}>
          {documento.numero} · {documento.receptor_razon_social || 'Consumidor final'} ·{' '}
          {formatGs(documento.total)}
        </p>

        <div style={{ padding:'10px 12px', borderRadius:'9px', marginBottom:'14px',
          background: plazo === 'vencido' ? C.dangerBg : C.warningBg,
          border:`1px solid ${plazo === 'vencido' ? C.danger : C.warning}44`,
          fontSize:'12.5px', color: plazo === 'vencido' ? C.danger : C.warning }}>
          <AlertCircle size={13} style={{ verticalAlign:'-2px', marginRight:'5px' }} />
          {plazo === 'vencido'
            ? 'Venció el plazo para cancelar. La corrección va por nota de crédito.'
            : `Quedan ${plazo} de plazo. La cancelación anula el comprobante ante la DNIT: no devuelve el stock ni el dinero.`}
        </div>

        <label style={{ display:'block', fontSize:'12px', color:C.textSec, marginBottom:'5px' }}>
          Motivo (lo lee la DNIT — entre 5 y 500 caracteres)
        </label>
        <textarea
          value={motivo} onChange={e => setMotivo(e.target.value)} rows={3} autoFocus
          placeholder="Ej: el cliente desistió de la compra antes de retirar la mercadería"
          style={{ width:'100%', padding:'10px', border:`1px solid ${C.border}`,
            borderRadius:'9px', fontSize:'13.5px', color:C.text, resize:'vertical',
            fontFamily:'inherit', outline:'none' }}
        />
        <p style={{ fontSize:'11px', color:C.textMuted, marginTop:'4px' }}>
          {motivo.trim().length}/500
        </p>

        <div style={{ display:'flex', gap:'8px', marginTop:'16px' }}>
          <button onClick={onCerrar}
            style={{ flex:1, height:'42px', borderRadius:'9px', cursor:'pointer',
              background:'transparent', border:`1px solid ${C.border}`,
              color:C.textSec, fontSize:'13.5px' }}>
            Volver
          </button>
          <button
            disabled={motivo.trim().length < 5 || cancelar.isPending}
            onClick={() => cancelar.mutate()}
            style={{ flex:1, height:'42px', borderRadius:'9px',
              cursor: motivo.trim().length < 5 ? 'not-allowed' : 'pointer',
              background:C.sidebar, border:`1px solid ${C.danger}`,
              color: motivo.trim().length < 5 ? C.textMuted : '#f0c4c4',
              fontSize:'13.5px', fontWeight:'500' }}>
            {cancelar.isPending ? 'Enviando...' : 'Cancelar el comprobante'}
          </button>
        </div>
      </div>
    </>
  )
}

// ─── Números sin usar / inutilización ─────────────────────────────────────────
/**
 * Cobros marcados como factura que no llegaron a generar documento
 * electrónico.
 *
 * Es el punto ciego de la cola de arriba: ahí se listan los documentos que
 * existen, así que una venta cuyo documento nunca se creó no aparece en
 * ninguna parte. Y no se crea en silencio cuando algo falla, porque emitir
 * está hecho para no tumbar un cobro con el cliente en el mostrador.
 *
 * La misma lista significa dos cosas distintas según el interruptor:
 *   · SIFEN apagado  → ventas a cargar a mano en el portal. Normal.
 *   · SIFEN prendido → alarma: deberían tener comprobante fiscal y no lo
 *     tienen.
 * Por eso el panel cambia de color y de texto según `sifen_habilitado`, en
 * vez de gritar siempre.
 */
function PanelVentasSinDocumento() {
  const { data, isLoading } = useQuery({
    queryKey: ['fe-ventas-sin-documento'],
    queryFn: () => facturacionApi.ventasSinDocumento().then(r => r.data),
  })

  const filas = data?.resultados || []
  const total = data?.total ?? 0
  const esAlarma = Boolean(data?.sifen_habilitado) && total > 0

  if (isLoading) return null
  if (total === 0) {
    return (
      <div style={{ marginTop:'22px', padding:'14px 16px', borderRadius:'11px',
        background:C.successBg, border:`1px solid ${C.success}33`,
        display:'flex', alignItems:'center', gap:'9px' }}>
        <CheckCircle size={15} color={C.success} style={{ flexShrink:0 }}/>
        <p style={{ fontSize:'12.5px', color:C.success, margin:0 }}>
          Todas las ventas facturadas tienen su documento electrónico.
        </p>
      </div>
    )
  }

  return (
    <div style={{ marginTop:'22px', borderRadius:'11px', overflow:'hidden',
      border:`1px solid ${esAlarma ? C.danger + '55' : C.border}` }}>
      <div style={{ padding:'13px 16px',
        background: esAlarma ? C.dangerBg : C.bgSec,
        borderBottom:`1px solid ${C.border}` }}>
        <div style={{ display:'flex', alignItems:'center', gap:'9px' }}>
          {esAlarma
            ? <AlertCircle size={16} color={C.danger} style={{ flexShrink:0 }}/>
            : <FileWarning size={16} color={C.textSec} style={{ flexShrink:0 }}/>}
          <h3 style={{ fontSize:'14px', fontWeight:'600', margin:0,
            color: esAlarma ? C.danger : C.text }}>
            Ventas facturadas sin documento electrónico ({total})
          </h3>
        </div>
        <p style={{ fontSize:'11.5px', color:C.textSec, margin:'6px 0 0' }}>
          {esAlarma
            ? 'El SIFEN está prendido: estas ventas deberían tener comprobante '
              + 'fiscal y no lo tienen. Hay que revisar por qué falló la emisión.'
            : 'El SIFEN está apagado, así que ninguna venta emite documento. '
              + 'Esta es la lista de las que se facturan cargándolas a mano en '
              + 'el portal.'}
        </p>
        {data?.truncado && (
          <p style={{ fontSize:'11px', color:C.textMuted, margin:'5px 0 0' }}>
            Se muestran las {filas.length} más recientes.
          </p>
        )}
      </div>

      <div style={{ maxHeight:'260px', overflowY:'auto' }}>
        {filas.map(f => (
          <div key={f.pago_id} style={{ display:'flex', alignItems:'center',
            gap:'12px', padding:'9px 16px', borderBottom:`1px solid ${C.border}`,
            flexWrap:'wrap' }}>
            <span style={{ fontSize:'12px', fontFamily:'monospace',
              color:C.textSec, minWidth:'150px' }}>
              {f.numero_ticket}
            </span>
            <span style={{ fontSize:'12px', color:C.textMuted, minWidth:'115px' }}>
              {formatFecha(f.fecha)}
            </span>
            <span style={{ fontSize:'12.5px', color:C.text, flex:1, minWidth:'140px' }}>
              {f.cliente_razon_social || '—'}
              {f.cliente_ruc && (
                <span style={{ color:C.textMuted, marginLeft:'7px' }}>
                  {f.cliente_ruc}
                </span>
              )}
            </span>
            <span style={{ fontSize:'12.5px', fontWeight:'600', color:C.goldDark }}>
              {formatGs(f.monto)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * El camino asincrónico: mandar documentos en lote y pedir su resultado.
 *
 * Se diferencia del envío normal en algo más que la velocidad: el SIFEN no
 * contesta si los aprobó, contesta un número de lote y procesa después. Por
 * eso son dos botones y no uno — "Enviar" y "Pedir resultado" son dos viajes
 * distintos, y entre medio los documentos quedan en "enviado", que no es ni
 * aprobado ni rechazado.
 *
 * Lo exige la Guía de Pruebas (5 aprobados y 5 rechazados en lote por cada
 * tipo de documento), pero también sirve en producción: mandar el cierre del
 * día de una vez en vez de veinte llamadas sueltas.
 */
function PanelLotes() {
  const queryClient = useQueryClient()
  const { data: lotes = [] } = useQuery({
    queryKey: ['fe-lotes'],
    queryFn: () => facturacionApi.lotes().then(r => r.data),
  })

  const refrescar = () => {
    queryClient.invalidateQueries({ queryKey: ['fe-lotes'] })
    queryClient.invalidateQueries({ queryKey: ['fe-documentos'] })
  }

  const enviar = useMutation({
    mutationFn: () => facturacionApi.enviarLote(),
    onSuccess: (r) => {
      refrescar()
      toast.success(`Lote ${r.data.numero} enviado con ${r.data.cantidad} documento(s)`)
    },
    onError: (err) => toast.error(
      err.response?.data?.error || 'No se pudo enviar el lote'),
  })

  const consultar = useMutation({
    mutationFn: () => facturacionApi.consultarLotes(),
    onSuccess: (r) => {
      refrescar()
      const n = (r.data.lotes || []).length
      toast.success(n ? `Se consultaron ${n} lote(s)` : 'No hay lotes esperando resultado')
    },
    onError: (err) => toast.error(
      err.response?.data?.error || 'No se pudo consultar'),
  })

  return (
    <div style={{ marginTop:'22px', border:`1px solid ${C.border}`,
      borderRadius:'11px', overflow:'hidden' }}>
      <div style={{ padding:'13px 16px', background:C.bgSec,
        borderBottom:`1px solid ${C.border}`, display:'flex',
        alignItems:'center', gap:'10px', flexWrap:'wrap' }}>
        <div style={{ flex:1, minWidth:'190px' }}>
          <h3 style={{ fontSize:'14px', fontWeight:'600', margin:0, color:C.text }}>
            Envío en lote (asincrónico)
          </h3>
          <p style={{ fontSize:'11.5px', color:C.textSec, margin:'5px 0 0' }}>
            El SIFEN devuelve un número y procesa después: enviar y pedir el
            resultado son dos pasos.
          </p>
        </div>
        <button onClick={() => enviar.mutate()} disabled={enviar.isPending}
          style={{ display:'flex', alignItems:'center', gap:'6px',
            padding:'8px 13px', borderRadius:'8px', cursor:'pointer',
            background:C.sidebar, border:`1px solid ${C.gold}`, color:C.gold,
            fontSize:'12.5px' }}>
          {enviar.isPending
            ? <Loader2 size={14} style={{ animation:'spin 1s linear infinite' }}/>
            : <Send size={14}/>}
          Enviar la cola en lote
        </button>
        <button onClick={() => consultar.mutate()} disabled={consultar.isPending}
          style={{ display:'flex', alignItems:'center', gap:'6px',
            padding:'8px 13px', borderRadius:'8px', cursor:'pointer',
            background:'transparent', border:`1px solid ${C.border}`,
            color:C.textSec, fontSize:'12.5px' }}>
          {consultar.isPending
            ? <Loader2 size={14} style={{ animation:'spin 1s linear infinite' }}/>
            : <RefreshCw size={14}/>}
          Pedir resultado
        </button>
      </div>

      {lotes.length === 0 ? (
        <p style={{ padding:'14px 16px', fontSize:'12.5px', color:C.textMuted,
          margin:0 }}>
          Todavía no se envió ningún lote.
        </p>
      ) : (
        <div style={{ maxHeight:'220px', overflowY:'auto' }}>
          {lotes.map(l => (
            <div key={l.id} style={{ display:'flex', alignItems:'center',
              gap:'12px', padding:'9px 16px',
              borderBottom:`1px solid ${C.border}`, flexWrap:'wrap' }}>
              <span style={{ fontSize:'12px', fontFamily:'monospace',
                color:C.text, minWidth:'110px' }}>
                Lote {l.numero}
              </span>
              <span style={{ fontSize:'11.5px', color:C.textMuted,
                minWidth:'115px' }}>
                {formatFecha(l.fecha_envio)}
              </span>
              <span style={{ fontSize:'12px', color:C.textSec, flex:1 }}>
                {l.estado_display} · {l.cantidad} doc.
                {l.aprobados > 0 && (
                  <span style={{ color:C.success, marginLeft:'8px' }}>
                    {l.aprobados} aprobado(s)
                  </span>
                )}
                {l.rechazados > 0 && (
                  <span style={{ color:C.danger, marginLeft:'8px' }}>
                    {l.rechazados} rechazado(s)
                  </span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function PanelInutilizacion() {
  const queryClient = useQueryClient()
  const [motivo, setMotivo] = useState('')
  const [rangoElegido, setRangoElegido] = useState(null)

  const { data, isLoading } = useQuery({
    queryKey: ['fe-numeros-sin-usar'],
    queryFn: () => facturacionApi.numerosSinUsar().then(r => r.data),
  })

  const inutilizar = useMutation({
    mutationFn: () => facturacionApi.inutilizar({
      tipo_documento: data.tipo_documento,
      establecimiento: data.establecimiento,
      punto_expedicion: data.punto_expedicion,
      desde: rangoElegido.desde,
      hasta: rangoElegido.hasta,
      motivo,
    }).then(r => r.data),
    onSuccess: (respuesta) => {
      queryClient.invalidateQueries({ queryKey: ['fe-numeros-sin-usar'] })
      toast.success('Rango declarado inutilizado')
      // El plazo de la Tabla J no impide declarar, pero el aviso tiene que
      // llegar a quien lo hizo: se declara fuera de termino y conviene que
      // lo sepa antes de que se lo diga la DNIT. Dura mas que el exito
      // porque hay que leerlo, no solo verlo pasar.
      if (respuesta?.advertencia) {
        toast(respuesta.advertencia, { icon: '⚠️', duration: 12000 })
      }
      setRangoElegido(null)
      setMotivo('')
    },
    onError: (err) => toast.error(err.response?.data?.error || 'No se pudo inutilizar'),
  })

  const rangos = data?.rangos || []

  return (
    <div style={{ background:C.bg, border:`1px solid ${C.border}`,
      borderRadius:'14px', padding:'18px 20px' }}>
      <h3 style={{ fontSize:'14.5px', fontWeight:'600', color:C.text }}>
        Números sin usar
      </h3>
      <p style={{ fontSize:'12px', color:C.textMuted, marginBottom:'14px' }}>
        Números del talonario que se consumieron y no llegaron a ser un
        comprobante. La DNIT exige declararlos: un salto en el correlativo sin
        justificar es una observación en una fiscalización.
      </p>

      {isLoading ? (
        <p style={{ fontSize:'13px', color:C.textMuted }}>Buscando...</p>
      ) : rangos.length === 0 ? (
        <div style={{ display:'flex', alignItems:'center', gap:'8px',
          padding:'12px 14px', background:C.successBg, borderRadius:'10px',
          border:`1px solid ${C.success}33`, fontSize:'13px', color:C.success }}>
          <CheckCircle size={15} /> El correlativo no tiene saltos.
        </div>
      ) : (
        <div style={{ display:'flex', flexDirection:'column', gap:'8px' }}>
          {rangos.map(r => {
            const elegido = rangoElegido?.desde === r.desde && rangoElegido?.hasta === r.hasta
            const cantidad = r.hasta - r.desde + 1
            return (
              <button key={`${r.desde}-${r.hasta}`}
                onClick={() => setRangoElegido(elegido ? null : r)}
                style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
                  padding:'11px 13px', borderRadius:'10px', cursor:'pointer', textAlign:'left',
                  background: elegido ? C.goldMuted : C.bgSec,
                  border:`1.5px solid ${elegido ? C.gold : C.border}` }}>
                <span style={{ fontSize:'13px', color:C.text, fontFamily:'monospace' }}>
                  {data.establecimiento}-{data.punto_expedicion}-
                  {String(r.desde).padStart(7,'0')}
                  {r.hasta !== r.desde && ` a ${String(r.hasta).padStart(7,'0')}`}
                </span>
                <span style={{ fontSize:'11.5px', color:C.textMuted }}>
                  {cantidad} número{cantidad !== 1 ? 's' : ''}
                </span>
              </button>
            )
          })}
        </div>
      )}

      {rangoElegido && (
        <div style={{ marginTop:'14px', paddingTop:'14px', borderTop:`1px solid ${C.border}` }}>
          <label style={{ display:'block', fontSize:'12px', color:C.textSec, marginBottom:'5px' }}>
            Motivo de la inutilización (5 a 500 caracteres)
          </label>
          <input
            value={motivo} onChange={e => setMotivo(e.target.value)}
            placeholder="Ej: se cortó la energía en medio de la emisión"
            style={{ width:'100%', height:'42px', padding:'0 12px',
              border:`1px solid ${C.border}`, borderRadius:'9px',
              fontSize:'13.5px', color:C.text, outline:'none' }}
          />
          <button
            disabled={motivo.trim().length < 5 || inutilizar.isPending}
            onClick={() => inutilizar.mutate()}
            style={{ marginTop:'10px', width:'100%', height:'42px', borderRadius:'9px',
              cursor: motivo.trim().length < 5 ? 'not-allowed' : 'pointer',
              background:C.sidebar, border:`1px solid ${C.gold}`,
              color: motivo.trim().length < 5 ? C.textMuted : C.gold,
              fontSize:'13.5px', fontWeight:'500' }}>
            {inutilizar.isPending ? 'Declarando...' : 'Declarar inutilizado'}
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Página ───────────────────────────────────────────────────────────────────
export default function FacturacionPage() {
  const [filtro, setFiltro] = useState('')
  const [aCancelar, setACancelar] = useState(null)
  // { documento, tipo } — un solo estado para las dos notas: es el mismo
  // gesto sobre la misma factura, y dos estados separados habrian dejado
  // abrir las dos ventanas a la vez.
  const [nota, setNota] = useState(null)
  const [bajando, setBajando] = useState(null)
  const [seccion, setSeccion] = useState('emitidos')

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['fe-documentos', filtro],
    queryFn: () => facturacionApi.documentos(
      filtro ? { estado: filtro } : {}).then(r => r.data),
    refetchInterval: 60_000,
  })

  const documentos = data?.documentos || []
  const resumen = data?.resumen || {}

  const descargarKude = async (documento) => {
    setBajando(documento.id)
    try {
      const res = await facturacionApi.kude(documento.id)
      const url = window.URL.createObjectURL(new Blob([res.data], { type:'application/pdf' }))
      // Se abre en una pestaña en vez de descargarse: lo normal es mirarlo e
      // imprimirlo para el cliente, no archivarlo.
      window.open(url, '_blank', 'noopener')
      setTimeout(() => window.URL.revokeObjectURL(url), 60_000)
    } catch {
      toast.error('No se pudo armar el KuDE')
    } finally {
      setBajando(null)
    }
  }

  return (
    <Layout pageTitle="Facturación electrónica" breadcrumbs={['Facturación']} fullWidth>
      {/* Secciones. Cada una contesta una pregunta distinta: ver SECCIONES. */}
      <div style={{ display:'flex', gap:'2px', marginBottom:'18px',
        borderBottom:`1px solid ${C.border}`, flexWrap:'wrap' }}>
        {SECCIONES.map(s => (
          <button key={s.clave} onClick={() => setSeccion(s.clave)}
            style={{ padding:'10px 16px', cursor:'pointer', background:'none',
              border:'none', borderBottom:`2px solid ${seccion === s.clave ? C.gold : 'transparent'}`,
              color: seccion === s.clave ? C.text : C.textSec,
              fontSize:'13.5px', fontWeight: seccion === s.clave ? '600' : '500',
              fontFamily:'inherit', marginBottom:'-1px' }}>
            {s.label}
          </button>
        ))}
      </div>

      {seccion === 'autofactura' && <FormAutofactura />}
      {seccion === 'recibidos' && <PanelRecibidos />}

      {seccion === 'transmision' && (
        <div>
          <PanelLotes />
          <PanelVentasSinDocumento />
        </div>
      )}

      {seccion === 'emitidos' && (
      <>
      {/* Resumen por estado */}
      <div style={{ display:'flex', gap:'8px', flexWrap:'wrap', marginBottom:'14px' }}>
        <button onClick={() => setFiltro('')}
          style={{ padding:'8px 14px', borderRadius:'9px', cursor:'pointer',
            fontSize:'12.5px', background: filtro === '' ? C.sidebar : 'transparent',
            border:`1px solid ${filtro === '' ? C.gold : C.border}`,
            color: filtro === '' ? C.gold : C.textSec }}>
          Todos
        </button>
        {Object.entries(ESTADO_CFG).map(([clave, cfg]) => (
          <button key={clave} onClick={() => setFiltro(clave === filtro ? '' : clave)}
            style={{ display:'flex', alignItems:'center', gap:'6px',
              padding:'8px 14px', borderRadius:'9px', cursor:'pointer', fontSize:'12.5px',
              background: filtro === clave ? cfg.bg : 'transparent',
              border:`1px solid ${filtro === clave ? cfg.color : C.border}`,
              color: filtro === clave ? cfg.color : C.textSec }}>
            {cfg.icon} {cfg.label}
            <span style={{ fontWeight:'600' }}>{resumen[clave] ?? 0}</span>
          </button>
        ))}
        <button onClick={() => refetch()} title="Actualizar"
          style={{ marginLeft:'auto', width:'38px', height:'38px', borderRadius:'9px',
            background:'transparent', border:`1px solid ${C.border}`, cursor:'pointer',
            color:C.textSec, display:'flex', alignItems:'center', justifyContent:'center' }}>
          <RefreshCw size={16} style={isFetching ? { animation:'spin 1s linear infinite' } : undefined} />
        </button>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 340px', gap:'14px',
        alignItems:'start' }}>

        {/* Cola de documentos */}
        <div style={{ background:C.bg, border:`1px solid ${C.border}`,
          borderRadius:'14px', overflow:'hidden' }}>
          {isLoading ? (
            <p style={{ padding:'30px', textAlign:'center', color:C.textMuted, fontSize:'13px' }}>
              Cargando documentos...
            </p>
          ) : documentos.length === 0 ? (
            <div style={{ padding:'46px 20px', textAlign:'center', color:C.textMuted }}>
              <FileText size={40} style={{ opacity:0.2, marginBottom:'10px' }} />
              <p style={{ fontSize:'14px' }}>
                {filtro ? 'Sin documentos en ese estado' : 'Todavía no se emitió ningún documento electrónico'}
              </p>
            </div>
          ) : documentos.map(d => {
            const plazo = plazoLegible(d.horas_para_cancelar)
            return (
              <div key={d.id} style={{ padding:'13px 16px', borderBottom:`1px solid ${C.border}` }}>
                <div style={{ display:'flex', alignItems:'flex-start',
                  justifyContent:'space-between', gap:'12px' }}>
                  <div style={{ minWidth:0, flex:1 }}>
                    <div style={{ display:'flex', alignItems:'center', gap:'8px', marginBottom:'3px' }}>
                      <span style={{ fontSize:'13.5px', fontWeight:'600', color:C.text,
                        fontFamily:'monospace' }}>{d.numero}</span>
                      <Badge estado={d.estado} />
                      <span style={{ fontSize:'11px', color:C.textMuted }}>
                        {d.tipo_descripcion}
                      </span>
                    </div>
                    <p style={{ fontSize:'12.5px', color:C.textSec }}>
                      {d.receptor_razon_social || 'Consumidor final'}
                      {d.receptor_ruc && <span style={{ color:C.textMuted }}> · {d.receptor_ruc}</span>}
                      <span style={{ color:C.textMuted }}> · {formatFecha(d.fecha_emision)}</span>
                    </p>
                    <p style={{ fontSize:'10.5px', color:C.textMuted, fontFamily:'monospace',
                      marginTop:'2px' }}>
                      {d.cdc_legible}
                    </p>
                    {d.estado === 'rechazado' && d.codigo_respuesta && (
                      <p style={{ fontSize:'11.5px', color:C.danger, marginTop:'4px' }}>
                        <FileWarning size={11} style={{ verticalAlign:'-1px' }} />{' '}
                        Rechazo {d.codigo_respuesta} — no se reintenta solo
                      </p>
                    )}
                    {plazo && plazo !== 'vencido' && d.estado === 'aprobado' && (
                      <p style={{ fontSize:'11.5px', color:C.warning, marginTop:'4px' }}>
                        Se puede cancelar por {plazo} más
                      </p>
                    )}
                  </div>

                  <div style={{ textAlign:'right', flexShrink:0 }}>
                    <p style={{ fontSize:'14px', fontWeight:'600', color:C.goldDark }}>
                      {formatGs(d.total)}
                    </p>
                    <div style={{ display:'flex', gap:'6px', marginTop:'7px' }}>
                      <button onClick={() => descargarKude(d)} disabled={bajando === d.id}
                        title="Abrir el KuDE en PDF"
                        style={{ display:'flex', alignItems:'center', gap:'5px',
                          padding:'6px 10px', borderRadius:'8px', cursor:'pointer',
                          background:C.bgTer, border:`1px solid ${C.border}`,
                          color:C.textSec, fontSize:'12px' }}>
                        {bajando === d.id
                          ? <Loader2 size={12} style={{ animation:'spin 1s linear infinite' }} />
                          : <FileText size={12} />} KuDE
                      </button>
                      {/* Las notas solo se emiten SOBRE UNA FACTURA: el
                          backend lo exige y la pantalla no ofrece lo que
                          va a ser rechazado. */}
                      {d.tipo_documento === 1 && (
                        <>
                          <button onClick={() => setNota({ documento:d, tipo:'credito' })}
                            title="Revertir esta factura con una nota de crédito"
                            style={{ display:'flex', alignItems:'center', gap:'5px',
                              padding:'6px 10px', borderRadius:'8px', cursor:'pointer',
                              background:C.bgTer, border:`1px solid ${C.border}`,
                              color:C.textSec, fontSize:'12px' }}>
                            <FileMinus size={12} /> N. crédito
                          </button>
                          <button onClick={() => setNota({ documento:d, tipo:'debito' })}
                            title="Sumar un importe con una nota de débito"
                            style={{ display:'flex', alignItems:'center', gap:'5px',
                              padding:'6px 10px', borderRadius:'8px', cursor:'pointer',
                              background:C.bgTer, border:`1px solid ${C.border}`,
                              color:C.textSec, fontSize:'12px' }}>
                            <FilePlus size={12} /> N. débito
                          </button>
                        </>
                      )}
                      <button
                        onClick={() => setACancelar(d)}
                        disabled={Boolean(d.impedimento_cancelacion)}
                        title={d.impedimento_cancelacion || 'Cancelar ante la DNIT'}
                        style={{ display:'flex', alignItems:'center', gap:'5px',
                          padding:'6px 10px', borderRadius:'8px',
                          cursor: d.impedimento_cancelacion ? 'not-allowed' : 'pointer',
                          background:'transparent',
                          border:`1px solid ${d.impedimento_cancelacion ? C.border : C.danger}`,
                          color: d.impedimento_cancelacion ? C.textMuted : C.danger,
                          fontSize:'12px', opacity: d.impedimento_cancelacion ? 0.5 : 1 }}>
                        <Ban size={12} /> Cancelar
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        <PanelInutilizacion />
      </div>
      </>
      )}

      {aCancelar && (
        <ModalCancelar documento={aCancelar} onCerrar={() => setACancelar(null)} />
      )}

      {nota && (
        <ModalNota documento={nota.documento} tipo={nota.tipo}
          onCerrar={() => setNota(null)} />
      )}

      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </Layout>
  )
}
