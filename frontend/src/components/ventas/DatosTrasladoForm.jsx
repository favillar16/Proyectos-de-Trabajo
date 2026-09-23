/**
 * DatosTrasladoForm — los datos del traslado de un pedido.
 *
 * Es lo que hacía falta para poder emitir la nota de remisión electrónica: el
 * XML ya salía bien, pero nadie tenía dónde cargar el motivo, el vehículo y la
 * dirección de entrega.
 *
 * Dos decisiones que explican cómo está armado:
 *
 * · **Abre lleno, no vacío.** El negocio entrega su propia venta con su camión
 *   casi siempre, así que el backend manda los valores sugeridos y el
 *   formulario arranca con ellos puestos. Quien lo carga solo pone la chapa,
 *   los kilómetros y la dirección. No es comodidad: cuanto menos haya que
 *   elegir, menos chances de elegir mal un código que después rechaza el SIFEN.
 *
 * · **Lo secundario está plegado.** De los veinticinco campos, cinco son los
 *   que se llenan siempre. El transportista tercerizado y el domicilio
 *   desglosado del destino viven en secciones colapsadas, porque mostrarlos
 *   todos de entrada haría que la pantalla se lea como un trámite y se llene
 *   de cualquier manera.
 *
 * Las tablas de códigos (motivos, modalidades, responsables) las sirve el
 * backend desde `codigos.py`. Acá no hay ninguna copia: si la DNIT cambia un
 * código, se toca un solo lugar.
 */
import { useState, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Truck, Save, Trash2, Loader2, ChevronDown, ChevronRight,
  AlertCircle, MapPin, User, X,
} from 'lucide-react'
import { facturacionApi } from '../../services/api'
import toast from 'react-hot-toast'

const C = {
  gold:'#B99C74', goldDark:'#8a7355', goldMuted:'rgba(185,156,116,0.10)',
  border:'#e8e4df', bg:'#ffffff', bgSec:'#fafaf9', bgTer:'#f5f4f2',
  text:'#1a1714', textSec:'#6b6560', textMuted:'#9e9892',
  success:'#3d7a5a', successBg:'#edf7f1', successBorder:'#b8deca',
  danger:'#9a3030', dangerBg:'#fef0f0', dangerBorder:'#f0b8b8',
  warning:'#8a6a1a', warningBg:'#fef9ee', warningBorder:'#f0d98a',
}

const hoy = () => new Date().toISOString().slice(0, 10)

/** Lo que el formulario manda cuando todavía no hay nada guardado. */
const VACIO = {
  motivo: 1, responsable: 1,
  fecha_inicio_traslado: hoy(), fecha_fin_traslado: '',
  kilometros: '',
  tipo_transporte: 1, modalidad: 1, responsable_flete: 5,
  vehiculo_tipo: 'Camion', vehiculo_marca: '',
  vehiculo_matricula: '', vehiculo_numero: '',
  transportista_nombre: '', transportista_ruc: '',
  transportista_documento: '', transportista_direccion: '',
  conductor_nombre: '', conductor_documento: '', conductor_direccion: '',
  direccion_salida: '', salida_numero_casa: '',
  direccion_entrega: '', entrega_numero_casa: '',
}

// ─── Piezas de formulario ────────────────────────────────────────────────────

function Campo({ etiqueta, error, ayuda, requerido, children }) {
  return (
    <div style={{ marginBottom:'14px', minWidth:0 }}>
      <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
        color:error ? C.danger : C.textSec, marginBottom:'5px' }}>
        {etiqueta}
        {requerido && <span style={{ color:C.gold, marginLeft:'3px' }}>*</span>}
      </label>
      {children}
      {error && (
        <p style={{ margin:'5px 0 0', fontSize:'11.5px', color:C.danger,
          display:'flex', alignItems:'flex-start', gap:'4px' }}>
          <AlertCircle size={13} style={{ flexShrink:0, marginTop:'1px' }} />
          {error}
        </p>
      )}
      {!error && ayuda && (
        <p style={{ margin:'5px 0 0', fontSize:'11.5px', color:C.textMuted }}>
          {ayuda}
        </p>
      )}
    </div>
  )
}

const estiloControl = (error) => ({
  width:'100%', height:'40px', padding:'0 10px',
  border:`1px solid ${error ? C.dangerBorder : C.border}`,
  borderRadius:'8px', fontSize:'13.5px', color:C.text,
  background:error ? C.dangerBg : C.bg, outline:'none',
  fontFamily:'inherit',
})

function Texto({ valor, onChange, error, ...resto }) {
  return <input value={valor ?? ''} onChange={e => onChange(e.target.value)}
    style={estiloControl(error)} {...resto} />
}

function Selector({ valor, onChange, opciones, error }) {
  return (
    <select value={valor ?? ''} onChange={e => onChange(Number(e.target.value))}
      style={{ ...estiloControl(error), appearance:'none',
        backgroundImage:'linear-gradient(45deg,transparent 50%,#9e9892 50%),linear-gradient(135deg,#9e9892 50%,transparent 50%)',
        backgroundPosition:'calc(100% - 16px) 17px, calc(100% - 11px) 17px',
        backgroundSize:'5px 5px, 5px 5px', backgroundRepeat:'no-repeat',
        paddingRight:'30px', cursor:'pointer' }}>
      {opciones.map(o => (
        <option key={o.codigo} value={o.codigo}>{o.descripcion}</option>
      ))}
    </select>
  )
}

function Fila({ children }) {
  return (
    <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(150px,1fr))',
      gap:'0 12px' }}>
      {children}
    </div>
  )
}

function Seccion({ titulo, icono: Icono, resumen, abiertaPorDefecto = false,
                   hayError = false, children }) {
  const [abierta, setAbierta] = useState(abiertaPorDefecto)
  // Un error adentro de una sección plegada sería invisible: se abre sola.
  useEffect(() => { if (hayError) setAbierta(true) }, [hayError])

  return (
    <div style={{ border:`1px solid ${hayError ? C.dangerBorder : C.border}`,
      borderRadius:'10px', marginBottom:'12px', overflow:'hidden',
      background: abierta ? C.bg : C.bgSec }}>
      <button type="button" onClick={() => setAbierta(a => !a)}
        style={{ width:'100%', display:'flex', alignItems:'center', gap:'9px',
          padding:'12px 14px', background:'transparent', border:'none',
          cursor:'pointer', textAlign:'left', color:C.text, fontFamily:'inherit' }}>
        {abierta ? <ChevronDown size={16} color={C.textMuted} />
                 : <ChevronRight size={16} color={C.textMuted} />}
        <Icono size={15} color={hayError ? C.danger : C.gold} />
        <span style={{ fontSize:'13.5px', fontWeight:'500', flex:1 }}>{titulo}</span>
        {!abierta && resumen && (
          <span style={{ fontSize:'12px', color:C.textMuted,
            overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
            maxWidth:'45%' }}>
            {resumen}
          </span>
        )}
      </button>
      {abierta && (
        <div style={{ padding:'2px 14px 4px', borderTop:`1px solid ${C.border}` }}>
          {children}
        </div>
      )}
    </div>
  )
}

// ─── El formulario ───────────────────────────────────────────────────────────

export default function DatosTrasladoForm({ pedido, onCerrar }) {
  const queryClient = useQueryClient()
  const [datos, setDatos] = useState(VACIO)
  const [errores, setErrores] = useState({})
  const [inicializado, setInicializado] = useState(false)

  const { data: opciones } = useQuery({
    queryKey: ['opciones-traslado'],
    queryFn: () => facturacionApi.opcionesTraslado().then(r => r.data),
    // Son las tablas de la DNIT: no cambian entre pedidos ni entre días.
    staleTime: 1000 * 60 * 60,
  })

  const { data: guardado, isLoading } = useQuery({
    queryKey: ['traslado', pedido?.id],
    queryFn: () => facturacionApi.traslado(pedido.id).then(r => r.data),
    enabled: Boolean(pedido?.id),
  })

  // Se arranca del dato guardado si existe; si no, de los sugeridos que manda
  // el backend. Una sola vez: después manda lo que la persona esté escribiendo.
  useEffect(() => {
    if (inicializado || !guardado || !opciones) return
    if (guardado.existe) {
      setDatos(d => ({ ...d, ...limpiarNulos(guardado) }))
    } else {
      setDatos(d => ({ ...d, ...opciones.sugeridos,
        direccion_entrega: pedido?.cliente_direccion || d.direccion_entrega }))
    }
    setInicializado(true)
  }, [guardado, opciones, inicializado, pedido])

  const guardar = useMutation({
    mutationFn: () => facturacionApi.guardarTraslado(pedido.id, aEnviar(datos)),
    onSuccess: () => {
      setErrores({})
      queryClient.invalidateQueries({ queryKey:['traslado', pedido.id] })
      toast.success('Datos de traslado guardados')
      onCerrar?.()
    },
    onError: (e) => {
      const detalle = e?.response?.data
      if (detalle && typeof detalle === 'object' && !Array.isArray(detalle)) {
        // El backend nombra el campo que está mal (lo hace `clean()` del
        // modelo). Se marcan los campos en vez de mostrar un cartel genérico
        // arriba: con veinticinco campos, "revisá los datos" no sirve de nada.
        setErrores(normalizarErrores(detalle))
        toast.error('Revisá los campos marcados')
      } else {
        toast.error('No se pudieron guardar los datos de traslado')
      }
    },
  })

  const borrar = useMutation({
    mutationFn: () => facturacionApi.borrarTraslado(pedido.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey:['traslado', pedido.id] })
      toast.success('Datos de traslado eliminados')
      onCerrar?.()
    },
    onError: (e) => {
      // 409: la remisión ya se emitió y el documento existe ante el DNIT.
      toast.error(e?.response?.data?.detail
        || 'No se pudieron eliminar los datos de traslado')
    },
  })

  const set = (campo) => (valor) => {
    setDatos(d => ({ ...d, [campo]: valor }))
    setErrores(e => (e[campo] ? { ...e, [campo]: undefined } : e))
  }

  const conTransportista = Boolean(datos.transportista_nombre?.trim())
  const erroresTransporte = useMemo(
    () => ['transportista_nombre','transportista_ruc','transportista_documento',
           'transportista_direccion','conductor_nombre','conductor_documento',
           'conductor_direccion'].some(k => errores[k]),
    [errores])
  const erroresDestino = useMemo(
    () => ['direccion_salida','salida_numero_casa','entrega_numero_casa']
      .some(k => errores[k]),
    [errores])

  if (!pedido) return null

  return (
    <>
      <div onClick={onCerrar} style={{ position:'fixed', inset:0, zIndex:160,
        background:'rgba(26,23,20,0.4)', backdropFilter:'blur(2px)' }} />
      <div style={{ position:'fixed', top:0, right:0, bottom:0, zIndex:161,
        width:'min(560px,95vw)', background:C.bg,
        borderLeft:`1px solid ${C.border}`,
        boxShadow:'-8px 0 32px rgba(0,0,0,0.12)',
        display:'flex', flexDirection:'column',
        animation:'slideIn 200ms ease' }}>

        {/* Encabezado */}
        <div style={{ padding:'16px 20px', borderBottom:`1px solid ${C.border}`,
          flexShrink:0, display:'flex', alignItems:'flex-start',
          justifyContent:'space-between', gap:'12px' }}>
          <div style={{ minWidth:0 }}>
            <p style={{ fontSize:'11px', color:C.textMuted, fontFamily:'monospace',
              margin:0 }}>
              {pedido.numero}
            </p>
            <h2 style={{ fontSize:'17px', fontWeight:'500', color:C.text,
              fontFamily:'var(--font-display)', margin:'2px 0 0',
              display:'flex', alignItems:'center', gap:'8px' }}>
              <Truck size={18} color={C.gold} />
              Datos del traslado
            </h2>
            <p style={{ fontSize:'12px', color:C.textMuted, margin:'6px 0 0' }}>
              Para la nota de remisión. Se cargan al preparar la entrega.
            </p>
          </div>
          <button onClick={onCerrar} style={{ background:'transparent',
            border:'none', cursor:'pointer', color:C.textMuted, padding:'6px',
            display:'flex', borderRadius:'8px', flexShrink:0 }}>
            <X size={20} />
          </button>
        </div>

        {/* Cuerpo */}
        <div style={{ flex:1, overflowY:'auto', WebkitOverflowScrolling:'touch',
          padding:'16px 20px' }}>
          {isLoading || !opciones ? (
            <div style={{ padding:'40px', textAlign:'center', color:C.textMuted }}>
              <Loader2 size={24} style={{ animation:'spin 1s linear infinite',
                margin:'0 auto 10px', display:'block' }} />
              Cargando...
            </div>
          ) : (
            <>
              {/* Lo que se llena siempre */}
              <Campo etiqueta="Motivo del traslado" requerido>
                <Selector valor={datos.motivo} onChange={set('motivo')}
                  opciones={opciones.motivos} error={errores.motivo} />
              </Campo>

              <Fila>
                <Campo etiqueta="Sale el" requerido error={errores.fecha_inicio_traslado}>
                  <Texto type="date" valor={datos.fecha_inicio_traslado}
                    onChange={set('fecha_inicio_traslado')}
                    error={errores.fecha_inicio_traslado} />
                </Campo>
                <Campo etiqueta="Llega el"
                  ayuda="Si se entrega el mismo día, dejalo vacío."
                  error={errores.fecha_fin_traslado}>
                  <Texto type="date" valor={datos.fecha_fin_traslado}
                    onChange={set('fecha_fin_traslado')}
                    error={errores.fecha_fin_traslado} />
                </Campo>
              </Fila>

              <Campo etiqueta="Kilómetros del recorrido" requerido
                error={errores.kilometros}
                ayuda="Estimado, ida. El SIFEN lo exige desde la Nota Técnica 010.">
                <Texto type="number" min="1" inputMode="numeric"
                  valor={datos.kilometros} onChange={set('kilometros')}
                  placeholder="12" error={errores.kilometros} />
              </Campo>

              <Campo etiqueta="Dirección de entrega" requerido
                error={errores.direccion_entrega}
                ayuda="Adónde va la mercadería.">
                <Texto valor={datos.direccion_entrega}
                  onChange={set('direccion_entrega')}
                  placeholder="Avda. Mcal. López 1234, Cnel. Oviedo"
                  error={errores.direccion_entrega} />
              </Campo>

              {/* Vehículo */}
              <Seccion titulo="Vehículo" icono={Truck} abiertaPorDefecto
                hayError={Boolean(errores.vehiculo_matricula || errores.vehiculo_numero)}>
                <Fila>
                  <Campo etiqueta="Tipo">
                    <Texto valor={datos.vehiculo_tipo}
                      onChange={set('vehiculo_tipo')} placeholder="Camion" />
                  </Campo>
                  <Campo etiqueta="Marca">
                    <Texto valor={datos.vehiculo_marca}
                      onChange={set('vehiculo_marca')} placeholder="Hyundai"
                      maxLength={10} />
                  </Campo>
                </Fila>
                <Fila>
                  <Campo etiqueta="Chapa (matrícula)"
                    error={errores.vehiculo_matricula}
                    ayuda="Máximo 7 caracteres (NT 005).">
                    <Texto valor={datos.vehiculo_matricula}
                      onChange={v => set('vehiculo_matricula')(v.toUpperCase())}
                      placeholder="ABC123" maxLength={7}
                      error={errores.vehiculo_matricula} />
                  </Campo>
                  <Campo etiqueta="o Nº interno"
                    error={errores.vehiculo_numero}
                    ayuda="Si el vehículo no tiene chapa.">
                    <Texto valor={datos.vehiculo_numero}
                      onChange={set('vehiculo_numero')} placeholder="INT-004"
                      error={errores.vehiculo_numero} />
                  </Campo>
                </Fila>
              </Seccion>

              {/* Transportista — plegado: el caso normal es el camión propio */}
              <Seccion titulo="Transportista y chofer" icono={User}
                hayError={erroresTransporte}
                resumen={conTransportista ? datos.transportista_nombre
                                          : 'Transporte propio'}>
                <p style={{ fontSize:'12px', color:C.textMuted,
                  margin:'12px 0 14px', lineHeight:1.5 }}>
                  Solo si la entrega la hace un tercero. Si va el camión del
                  local, dejá esto vacío. Cuando se carga un transportista, el
                  SIFEN exige también su documento y su dirección.
                </p>
                <Campo etiqueta="Nombre del transportista"
                  error={errores.transportista_nombre}>
                  <Texto valor={datos.transportista_nombre}
                    onChange={set('transportista_nombre')}
                    placeholder="Fletes del Este S.A."
                    error={errores.transportista_nombre} />
                </Campo>
                {conTransportista && (
                  <>
                    <Fila>
                      <Campo etiqueta="RUC" error={errores.transportista_ruc}>
                        <Texto valor={datos.transportista_ruc}
                          onChange={set('transportista_ruc')}
                          placeholder="80012345-6"
                          error={errores.transportista_ruc} />
                      </Campo>
                      <Campo etiqueta="o Cédula"
                        error={errores.transportista_documento}>
                        <Texto valor={datos.transportista_documento}
                          onChange={set('transportista_documento')}
                          placeholder="1234567"
                          error={errores.transportista_documento} />
                      </Campo>
                    </Fila>
                    <Campo etiqueta="Dirección del transportista"
                      error={errores.transportista_direccion}
                      ayuda="Máximo 60 caracteres.">
                      <Texto valor={datos.transportista_direccion}
                        onChange={set('transportista_direccion')}
                        maxLength={60}
                        error={errores.transportista_direccion} />
                    </Campo>
                    <Fila>
                      <Campo etiqueta="Chofer" error={errores.conductor_nombre}>
                        <Texto valor={datos.conductor_nombre}
                          onChange={set('conductor_nombre')}
                          placeholder="Juan Pérez"
                          error={errores.conductor_nombre} />
                      </Campo>
                      <Campo etiqueta="Cédula del chofer"
                        error={errores.conductor_documento}>
                        <Texto valor={datos.conductor_documento}
                          onChange={set('conductor_documento')}
                          placeholder="1234567"
                          error={errores.conductor_documento} />
                      </Campo>
                    </Fila>
                    <Campo etiqueta="Dirección del chofer"
                      error={errores.conductor_direccion}
                      ayuda="Máximo 60 caracteres.">
                      <Texto valor={datos.conductor_direccion}
                        onChange={set('conductor_direccion')} maxLength={60}
                        error={errores.conductor_direccion} />
                    </Campo>
                  </>
                )}
              </Seccion>

              {/* Detalles del transporte y direcciones */}
              <Seccion titulo="Salida y modalidad" icono={MapPin}
                hayError={erroresDestino}
                resumen={`${nombreDe(opciones.modalidades, datos.modalidad)} · ${nombreDe(opciones.tipos_transporte, datos.tipo_transporte)}`}>
                <Fila>
                  <Campo etiqueta="Transporte">
                    <Selector valor={datos.tipo_transporte}
                      onChange={set('tipo_transporte')}
                      opciones={opciones.tipos_transporte} />
                  </Campo>
                  <Campo etiqueta="Modalidad">
                    <Selector valor={datos.modalidad} onChange={set('modalidad')}
                      opciones={opciones.modalidades} />
                  </Campo>
                </Fila>
                <Fila>
                  <Campo etiqueta="Paga el flete">
                    <Selector valor={datos.responsable_flete}
                      onChange={set('responsable_flete')}
                      opciones={opciones.responsables_flete} />
                  </Campo>
                  <Campo etiqueta="Emite la nota">
                    <Selector valor={datos.responsable}
                      onChange={set('responsable')}
                      opciones={opciones.responsables} />
                  </Campo>
                </Fila>
                <Campo etiqueta="Dirección de salida"
                  error={errores.direccion_salida}
                  ayuda="Por defecto, el local. Cambialo si sale de otro lado.">
                  <Texto valor={datos.direccion_salida}
                    onChange={set('direccion_salida')}
                    error={errores.direccion_salida} />
                </Campo>
                <Fila>
                  <Campo etiqueta="Nº de casa (salida)"
                    error={errores.salida_numero_casa}>
                    <Texto valor={datos.salida_numero_casa}
                      onChange={set('salida_numero_casa')} placeholder="0"
                      error={errores.salida_numero_casa} />
                  </Campo>
                  <Campo etiqueta="Nº de casa (entrega)"
                    error={errores.entrega_numero_casa}>
                    <Texto valor={datos.entrega_numero_casa}
                      onChange={set('entrega_numero_casa')} placeholder="0"
                      error={errores.entrega_numero_casa} />
                  </Campo>
                </Fila>
              </Seccion>

              <div style={{ background:C.bgTer, borderRadius:'9px',
                padding:'11px 13px', fontSize:'11.5px', color:C.textMuted,
                lineHeight:1.55, marginTop:'4px' }}>
                Estos datos no emiten nada por sí solos: quedan guardados para
                cuando se genere la nota de remisión electrónica del pedido.
              </div>
            </>
          )}
        </div>

        {/* Pie */}
        <div style={{ padding:'12px 20px', borderTop:`1px solid ${C.border}`,
          flexShrink:0, display:'flex', alignItems:'center', gap:'10px',
          background:C.bgSec }}>
          {guardado?.existe && (
            <button onClick={() => borrar.mutate()} disabled={borrar.isPending}
              title="Eliminar los datos de traslado"
              style={{ height:'40px', padding:'0 12px', borderRadius:'9px',
                border:`1px solid ${C.dangerBorder}`, background:C.bg,
                color:C.danger, cursor:borrar.isPending ? 'wait' : 'pointer',
                display:'flex', alignItems:'center', gap:'6px',
                fontSize:'13px', fontFamily:'inherit' }}>
              {borrar.isPending
                ? <Loader2 size={15} style={{ animation:'spin 1s linear infinite' }} />
                : <Trash2 size={15} />}
            </button>
          )}
          <div style={{ flex:1 }} />
          <button onClick={onCerrar}
            style={{ height:'40px', padding:'0 16px', borderRadius:'9px',
              border:`1px solid ${C.border}`, background:C.bg, color:C.textSec,
              cursor:'pointer', fontSize:'13.5px', fontFamily:'inherit' }}>
            Cancelar
          </button>
          <button onClick={() => guardar.mutate()}
            disabled={guardar.isPending || isLoading}
            style={{ height:'40px', padding:'0 18px', borderRadius:'9px',
              border:'none', background:C.gold, color:'#fff',
              cursor:guardar.isPending ? 'wait' : 'pointer',
              display:'flex', alignItems:'center', gap:'7px',
              fontSize:'13.5px', fontWeight:'500', fontFamily:'inherit',
              opacity:(guardar.isPending || isLoading) ? 0.7 : 1 }}>
            {guardar.isPending
              ? <Loader2 size={15} style={{ animation:'spin 1s linear infinite' }} />
              : <Save size={15} />}
            Guardar
          </button>
        </div>
      </div>
    </>
  )
}

// ─── Auxiliares ──────────────────────────────────────────────────────────────

function nombreDe(opciones, codigo) {
  return opciones?.find(o => o.codigo === codigo)?.descripcion ?? ''
}

/**
 * Los null del backend se vuelven '' para que React no trate los campos como
 * no controlados. Un input que pasa de `null` a texto tira un warning y pierde
 * el cursor.
 */
function limpiarNulos(objeto) {
  const salida = {}
  for (const [k, v] of Object.entries(objeto)) salida[k] = v ?? ''
  return salida
}

/**
 * Los '' se vuelven null antes de mandar.
 *
 * Importa para los campos numéricos opcionales: DRF rechaza `''` en un entero
 * con "a valid integer is required", y el formulario mostraría un error en un
 * campo que la persona dejó vacío a propósito.
 */
function aEnviar(datos) {
  const opcionalesNumericos = ['kilometros', 'salida_ciudad',
    'entrega_departamento', 'entrega_distrito', 'entrega_ciudad']
  const salida = {}
  for (const [k, v] of Object.entries(datos)) {
    if (v === '' && (opcionalesNumericos.includes(k) || k.startsWith('fecha_'))) {
      salida[k] = null
    } else {
      salida[k] = v
    }
  }
  return salida
}

/** DRF manda listas de mensajes por campo; acá alcanza con el primero. */
function normalizarErrores(detalle) {
  const salida = {}
  for (const [campo, mensaje] of Object.entries(detalle)) {
    salida[campo] = Array.isArray(mensaje) ? mensaje[0] : String(mensaje)
  }
  return salida
}
