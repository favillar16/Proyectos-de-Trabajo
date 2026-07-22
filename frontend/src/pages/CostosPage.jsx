/**
 * CostosPage — Costos Operativos (Oga Porã)
 * Solapas: Gastos del mes · Proveedores · Pedidos a proveedor · Empleados
 * Incluye método de pago (efectivo/transferencia/crédito/cheque) con datos
 * de cheque y alertas de cheques por cobrar y pedidos por llegar.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus, Trash2, Edit2, X, Loader2, Users, Receipt, TrendingDown,
  Building2, Truck, Bell, AlertTriangle, Calendar, CreditCard, Check,
} from 'lucide-react'
import Layout from '../components/layout/Layout'
import { costosApi } from '../services/api'
import toast from 'react-hot-toast'

const C = {
  sidebar:'#453941', sidebarHov:'#362F31',
  gold:'#B99C74', goldDark:'#8a7355', goldMuted:'rgba(185,156,116,0.10)',
  border:'#e8e4df', bg:'#ffffff', bgSec:'#fafaf9', bgTer:'#f5f4f2',
  text:'#1a1714', textSec:'#6b6560', textMuted:'#9e9892',
  success:'#3d7a5a', successBg:'#edf7f1', successBorder:'#b8deca',
  warning:'#8a6a1a', warningBg:'#fef9ee', warningBorder:'#f0d98a',
  danger:'#9a3030', dangerBg:'#fef0f0', dangerBorder:'#f0b8b8',
  info:'#2a5c8a', infoBg:'#eef4fb',
}

const MESES = ['','Enero','Febrero','Marzo','Abril','Mayo','Junio',
  'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
const TIPO_COLOR = {
  proveedor:{ bg:C.infoBg, color:C.info, label:'Proveedor' },
  salario:  { bg:C.successBg, color:C.success, label:'Salario' },
  servicio: { bg:C.warningBg, color:C.warning, label:'Servicio' },
  otro:     { bg:C.bgTer, color:C.textSec, label:'Otro' },
}
const ESTADOS_GASTO = {
  pendiente:{ bg:C.warningBg, color:C.warning, label:'Pendiente' },
  pagado:   { bg:C.successBg, color:C.success, label:'Pagado' },
  cancelado:{ bg:C.dangerBg,  color:C.danger,  label:'Cancelado' },
}
const METODO_PAGO_LABEL = {
  efectivo:'Efectivo', transferencia:'Transferencia',
  credito:'Crédito', cheque:'Cheque', '':'—',
}
const ESTADOS_PEDPROV = {
  pendiente:{ bg:C.warningBg, color:C.warning, label:'Pendiente' },
  en_camino:{ bg:C.infoBg,    color:C.info,    label:'En camino' },
  recibido: { bg:C.successBg, color:C.success, label:'Recibido' },
  cancelado:{ bg:C.dangerBg,  color:C.danger,  label:'Cancelado' },
}

const formatGs = v => `Gs. ${Number(v||0).toLocaleString('es-PY')}`

const Badge = ({ cfg }) => <span style={{ padding:'2px 8px', borderRadius:'20px',
  fontSize:'11px', fontWeight:'500', background:cfg.bg, color:cfg.color }}>{cfg.label}</span>

const FInput = ({error,...p}) => <input {...p} style={{ width:'100%', height:'38px',
  padding:'0 10px', border:`1px solid ${error?C.danger:C.border}`, borderRadius:'8px',
  fontSize:'13.5px', color:C.text, background:C.bg, outline:'none', ...p.style }}
  onFocus={e=>e.target.style.borderColor=C.gold}
  onBlur={e=>e.target.style.borderColor=error?C.danger:C.border}/>

const FSelect = ({children,...p}) => <select {...p} style={{ width:'100%', height:'38px',
  padding:'0 10px', border:`1px solid ${C.border}`, borderRadius:'8px',
  fontSize:'13.5px', color:C.text, background:C.bg, outline:'none', ...p.style }}>
  {children}</select>

const Campo = ({label,error,children}) => <div style={{ marginBottom:'12px' }}>
  <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
    color:error?C.danger:C.textSec, marginBottom:'4px' }}>{label}</label>
  {children}
  {error && <p style={{ fontSize:'11px', color:C.danger, marginTop:'2px' }}>{error}</p>}
</div>

function Modal({ titulo, onCerrar, children, ancho='480px' }) {
  return <>
    <div onClick={onCerrar} style={{ position:'fixed', inset:0, zIndex:200,
      background:'rgba(26,23,20,0.45)', backdropFilter:'blur(2px)' }}/>
    <div style={{ position:'fixed', top:'50%', left:'50%', zIndex:201,
      transform:'translate(-50%,-50%)', width:`min(${ancho},94vw)`, maxHeight:'90vh',
      overflowY:'auto', background:C.bg, borderRadius:'16px', border:`1px solid ${C.border}`,
      boxShadow:'0 20px 50px rgba(0,0,0,0.15)', padding:'24px' }}>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:'18px' }}>
        <h3 style={{ fontSize:'16px', fontWeight:'500', color:C.text }}>{titulo}</h3>
        <button onClick={onCerrar} style={{ background:'transparent', border:'none',
          cursor:'pointer', color:C.textMuted, display:'flex', alignItems:'center' }}>
          <X size={18}/></button>
      </div>
      {children}
    </div>
  </>
}

const BtnGuardar = ({ pending, onClick, label }) => (
  <button onClick={onClick} disabled={pending}
    style={{ flex:2, height:'42px', borderRadius:'9px',
      background:pending?C.bgTer:C.sidebar,
      border:`1.5px solid ${pending?C.border:C.gold}`,
      color:pending?C.textMuted:C.gold, fontSize:'14px', fontWeight:'500',
      cursor:pending?'not-allowed':'pointer', display:'flex', alignItems:'center',
      justifyContent:'center', gap:'7px' }}>
    {pending?<><Loader2 size={14} style={{ animation:'spin 1s linear infinite' }}/> Guardando...</>:label}
  </button>
)
const BtnCancelar = ({ onClick }) => (
  <button onClick={onClick} style={{ flex:1, height:'42px', borderRadius:'9px',
    background:'transparent', border:`1px solid ${C.border}`, color:C.textSec,
    fontSize:'14px', cursor:'pointer' }}>Cancelar</button>
)

// ════════════════════════════════════════════════════════
// BANNER DE ALERTAS
// ════════════════════════════════════════════════════════
function BannerAlertas() {
  const { data } = useQuery({
    queryKey: ['costos-alertas'],
    queryFn: () => costosApi.alertas(7).then(r => r.data),
    staleTime: 15_000,
  })
  if (!data || data.total_alertas === 0) return null

  // Usar los cheques agrupados por proveedor (varios cheques del mismo
  // proveedor en el periodo se muestran como una sola alerta resumida).
  const grupos = data.cheques_agrupados || []

  const textoProximidad = (dias) =>
    dias < 0  ? `venció hace ${Math.abs(dias)} día${Math.abs(dias)!==1?'s':''}`
  : dias === 0 ? 'vence hoy'
  :              `vence en ${dias} día${dias!==1?'s':''}`

  return (
    <div style={{ marginBottom:'18px', display:'flex', flexDirection:'column', gap:'8px' }}>
      {grupos.map(grp => {
        const varios   = grp.cantidad > 1
        const critico  = grp.hay_vencidos
        return (
          <div key={`grp-${grp.proveedor}`} style={{ display:'flex', alignItems:'flex-start', gap:'10px',
            padding:'10px 14px', borderRadius:'10px',
            background: critico ? C.dangerBg : C.warningBg,
            border:`1px solid ${critico ? C.dangerBorder : C.warningBorder}` }}>
            <AlertTriangle size={16} style={{ color: critico ? C.danger : C.warning, flexShrink:0, marginTop:'2px' }}/>
            <div style={{ flex:1 }}>
              {varios ? (
                <>
                  <p style={{ fontSize:'13px', fontWeight:'600', color: critico ? C.danger : C.warning }}>
                    {grp.cantidad} cheques a {grp.proveedor} — total {formatGs(grp.monto_total)}
                  </p>
                  <p style={{ fontSize:'12px', color: critico ? C.danger : C.warning, marginTop:'2px', opacity:0.9 }}>
                    El más próximo {textoProximidad(grp.proximo_dias)}
                    {grp.hay_vencidos && grp.proximo_dias >= 0 ? ' · hay cheques vencidos' : ''}
                  </p>
                  {/* Detalle de cada cheque del grupo */}
                  <div style={{ marginTop:'6px', display:'flex', flexDirection:'column', gap:'2px' }}>
                    {grp.cheques.map(ch => (
                      <p key={`ch-${ch.id}`} style={{ fontSize:'11.5px',
                        color: critico ? C.danger : C.warning, opacity:0.85 }}>
                        • {formatGs(ch.monto)} {ch.cheque_numero ? `· Cheque ${ch.cheque_numero}` : ''}
                        {ch.periodo ? ` · periodo ${ch.periodo}` : ''} — {textoProximidad(ch.dias)}
                      </p>
                    ))}
                  </div>
                </>
              ) : (
                <p style={{ fontSize:'13px', color: critico ? C.danger : C.warning }}>
                  {grp.cheques[0].vencido
                    ? `Cheque a ${grp.proveedor} venció hace ${Math.abs(grp.cheques[0].dias)} día${Math.abs(grp.cheques[0].dias)!==1?'s':''}`
                    : grp.cheques[0].dias === 0
                      ? `Hoy se cumple el plazo de pago vía cheque a ${grp.proveedor}`
                      : `En ${grp.cheques[0].dias} día${grp.cheques[0].dias!==1?'s':''} se cumple el plazo de pago vía cheque a ${grp.proveedor}`}
                  {' '}— {formatGs(grp.cheques[0].monto)}
                  {grp.cheques[0].cheque_numero ? ` · Cheque ${grp.cheques[0].cheque_numero}` : ''}
                  {grp.cheques[0].periodo ? ` · periodo ${grp.cheques[0].periodo}` : ''}
                </p>
              )}
            </div>
          </div>
        )
      })}
      {data.pedidos.map(pd => (
        <div key={`pd-${pd.id}`} style={{ display:'flex', alignItems:'center', gap:'10px',
          padding:'10px 14px', borderRadius:'10px',
          background: pd.atrasado ? C.dangerBg : C.infoBg,
          border:`1px solid ${pd.atrasado ? C.dangerBorder : '#aecae8'}` }}>
          <Truck size={16} style={{ color: pd.atrasado ? C.danger : C.info, flexShrink:0 }}/>
          <p style={{ fontSize:'13px', color: pd.atrasado ? C.danger : C.info, flex:1 }}>
            {pd.atrasado
              ? `Pedido a ${pd.proveedor} está atrasado ${Math.abs(pd.dias)} día${Math.abs(pd.dias)!==1?'s':''}`
              : pd.dias === 0
                ? `Hoy es la entrega estimada del pedido a ${pd.proveedor}`
                : `En ${pd.dias} día${pd.dias!==1?'s':''} llega el pedido a ${pd.proveedor}`
            }
            {' '}— {pd.descripcion}
          </p>
        </div>
      ))}
    </div>
  )
}

// ════════════════════════════════════════════════════════
// MODAL GASTO (con método de pago + cheque)
// ════════════════════════════════════════════════════════
function ModalGasto({ gasto, anio, mes, categorias, empleados, proveedores, onCerrar, onGuardado }) {
  const esEdicion = Boolean(gasto)
  const [form, setForm] = useState({
    descripcion: gasto?.descripcion||'', monto: gasto?.monto||'',
    categoria_id: gasto?.categoria_id||'', empleado_id: gasto?.empleado_id||'',
    proveedor_id: gasto?.proveedor_id||'',
    anio: gasto?.anio||anio, mes: gasto?.mes||mes,
    estado: gasto?.estado||'pendiente', fecha_pago: gasto?.fecha_pago||'',
    metodo_pago: gasto?.metodo_pago||'',
    cheque_numero: gasto?.cheque_numero||'', cheque_banco: gasto?.cheque_banco||'',
    cheque_fecha_cobro: gasto?.cheque_fecha_cobro||'',
    comprobante: gasto?.comprobante||'', notas: gasto?.notas||'',
  })
  const [errores, setErrores] = useState({})
  const sf = (k,v) => { setForm(f=>({...f,[k]:v})); setErrores(e=>({...e,[k]:undefined})) }
  const catSel = categorias.find(c=>String(c.id)===String(form.categoria_id))
  const esSalario = catSel?.tipo === 'salario'
  const esProveedor = catSel?.tipo === 'proveedor'
  const esCheque = form.metodo_pago === 'cheque'

  const mut = useMutation({
    mutationFn: () => {
      const payload = { ...form }
      // Normalizar monto: quitar separadores de miles por si se ingresaron
      payload.monto = Number(String(form.monto).replace(/[^\d.]/g, ''))
      if (!payload.empleado_id) delete payload.empleado_id
      if (!payload.proveedor_id) delete payload.proveedor_id
      if (!payload.fecha_pago) delete payload.fecha_pago
      if (!payload.cheque_fecha_cobro) delete payload.cheque_fecha_cobro
      return esEdicion
        ? costosApi.actualizarGasto(gasto.id, payload).then(r=>r.data)
        : costosApi.crearGasto(payload).then(r=>r.data)
    },
    onSuccess: () => { toast.success(esEdicion?'Gasto actualizado':'Gasto registrado'); onGuardado() },
    onError: (err) => { setErrores(err.response?.data||{}); toast.error('Revisá los campos marcados') },
  })

  const guardar = () => {
    const e = {}
    if (!form.descripcion.trim()) e.descripcion = 'Requerido'
    const montoNum = Number(String(form.monto).replace(/[^\d.]/g, ''))
    if (!montoNum || montoNum <= 0) e.monto = 'Ingresá un monto válido'
    if (!form.categoria_id) e.categoria_id = 'Seleccioná una categoría'
    if (esCheque && !form.cheque_fecha_cobro) e.cheque_fecha_cobro = 'Obligatoria para cheque'
    if (Object.keys(e).length) {
      setErrores(e)
      toast.error('Faltan datos: ' + Object.values(e).join(', '))
      return
    }
    mut.mutate()
  }

  return <Modal titulo={esEdicion?'Editar gasto':'Registrar gasto'} onCerrar={onCerrar} ancho="540px">
    <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'0 12px' }}>
      <div style={{ gridColumn:'1/-1' }}>
        <Campo label="Descripción *" error={errores.descripcion}>
          <FInput value={form.descripcion} onChange={e=>sf('descripcion',e.target.value)}
            placeholder="Ej: Factura proveedor porcelanatos" error={errores.descripcion}/>
        </Campo>
      </div>
      <Campo label="Categoría *" error={errores.categoria_id}>
        <FSelect value={form.categoria_id} onChange={e=>sf('categoria_id',e.target.value)}>
          <option value="">Seleccionar...</option>
          {categorias.map(c=><option key={c.id} value={c.id}>{c.nombre}</option>)}
        </FSelect>
      </Campo>
      <Campo label="Monto (Gs.) *" error={errores.monto}>
        <FInput type="number" min="1" step="1000" value={form.monto}
          onChange={e=>sf('monto',e.target.value)} placeholder="0" error={errores.monto}
          style={{ textAlign:'right', fontWeight:'600' }}/>
      </Campo>

      {esProveedor && <div style={{ gridColumn:'1/-1' }}>
        <Campo label="Proveedor">
          <FSelect value={form.proveedor_id||''} onChange={e=>sf('proveedor_id',e.target.value||'')}>
            <option value="">Sin proveedor específico</option>
            {proveedores.map(p=><option key={p.id} value={p.id}>{p.nombre}</option>)}
          </FSelect>
        </Campo>
      </div>}

      {esSalario && <div style={{ gridColumn:'1/-1' }}>
        <Campo label="Empleado">
          <FSelect value={form.empleado_id||''} onChange={e=>sf('empleado_id',e.target.value||'')}>
            <option value="">Sin empleado específico</option>
            {empleados.map(emp=><option key={emp.id} value={emp.id}>{emp.nombre_completo}</option>)}
          </FSelect>
        </Campo>
      </div>}

      <Campo label="Mes *">
        <FSelect value={form.mes} onChange={e=>sf('mes',Number(e.target.value))}>
          {MESES.slice(1).map((m,i)=><option key={i+1} value={i+1}>{m}</option>)}
        </FSelect>
      </Campo>
      <Campo label="Año *">
        <FInput type="number" min="2020" max="2100" value={form.anio}
          onChange={e=>sf('anio',Number(e.target.value))}/>
      </Campo>

      <Campo label="Método de pago">
        <FSelect value={form.metodo_pago} onChange={e=>sf('metodo_pago',e.target.value)}>
          <option value="">— Sin especificar —</option>
          <option value="efectivo">Efectivo</option>
          <option value="transferencia">Transferencia</option>
          <option value="credito">Crédito</option>
          <option value="cheque">Cheque</option>
        </FSelect>
      </Campo>
      <Campo label="Estado">
        <FSelect value={form.estado} onChange={e=>sf('estado',e.target.value)}>
          <option value="pendiente">Pendiente</option>
          <option value="pagado">Pagado</option>
          <option value="cancelado">Cancelado</option>
        </FSelect>
      </Campo>

      {esCheque && <>
        <div style={{ gridColumn:'1/-1', marginTop:'4px', marginBottom:'4px' }}>
          <p style={{ fontSize:'11.5px', fontWeight:'500', color:C.goldDark,
            textTransform:'uppercase', letterSpacing:'0.05em' }}>Datos del cheque</p>
        </div>
        <Campo label="Nº de cheque">
          <FInput value={form.cheque_numero} onChange={e=>sf('cheque_numero',e.target.value)}
            placeholder="Ej: 0012345"/>
        </Campo>
        <Campo label="Banco">
          <FInput value={form.cheque_banco} onChange={e=>sf('cheque_banco',e.target.value)}
            placeholder="Ej: Banco Itaú"/>
        </Campo>
        <div style={{ gridColumn:'1/-1' }}>
          <Campo label="Fecha de cobro (plazo) *" error={errores.cheque_fecha_cobro}>
            <FInput type="date" value={form.cheque_fecha_cobro}
              onChange={e=>sf('cheque_fecha_cobro',e.target.value)} error={errores.cheque_fecha_cobro}/>
          </Campo>
        </div>
      </>}

      <div style={{ gridColumn:'1/-1' }}>
        <Campo label="Nº comprobante / factura">
          <FInput value={form.comprobante} onChange={e=>sf('comprobante',e.target.value)} placeholder="FAC-001234"/>
        </Campo>
        <Campo label="Notas">
          <textarea value={form.notas} onChange={e=>sf('notas',e.target.value)} rows={2}
            placeholder="Observaciones..." style={{ width:'100%', padding:'8px 10px',
              border:`1px solid ${C.border}`, borderRadius:'8px', fontSize:'13.5px',
              color:C.text, background:C.bg, outline:'none', resize:'vertical', fontFamily:'inherit' }}
            onFocus={e=>e.target.style.borderColor=C.gold}
            onBlur={e=>e.target.style.borderColor=C.border}/>
        </Campo>
      </div>
    </div>
    <div style={{ display:'flex', gap:'10px' }}>
      <BtnCancelar onClick={onCerrar}/>
      <BtnGuardar pending={mut.isPending} onClick={guardar} label={esEdicion?'Guardar cambios':'Registrar gasto'}/>
    </div>
  </Modal>
}

// ════════════════════════════════════════════════════════
// SOLAPA GASTOS
// ════════════════════════════════════════════════════════
function SolapaGastos() {
  const qc = useQueryClient()
  const hoy = new Date()
  const [anio, setAnio] = useState(hoy.getFullYear())
  const [mes,  setMes]  = useState(hoy.getMonth()+1)
  const [modal, setModal] = useState(false)
  const [editando, setEditando] = useState(null)

  const {data, isLoading} = useQuery({ queryKey:['gastos',anio,mes],
    queryFn:()=>costosApi.gastos({anio,mes}).then(r=>r.data), staleTime:30_000 })
  const {data:catData} = useQuery({ queryKey:['cat-gasto'],
    queryFn:()=>costosApi.categorias({activas:1}).then(r=>r.data), staleTime:300_000 })
  const {data:empData} = useQuery({ queryKey:['empleados'],
    queryFn:()=>costosApi.empleados({activos:1}).then(r=>r.data), staleTime:300_000 })
  const {data:provData} = useQuery({ queryKey:['proveedores'],
    queryFn:()=>costosApi.proveedores({activos:1}).then(r=>r.data), staleTime:300_000 })

  const gastos = data?.results||[]
  const total  = data?.total||0
  const categorias = catData?.results||[]
  const delMut = useMutation({ mutationFn: id => costosApi.eliminarGasto(id),
    onSuccess: () => { qc.invalidateQueries({queryKey:['gastos']}); qc.invalidateQueries({queryKey:['costos-alertas']}); toast.success('Gasto eliminado') } })
  // Marcar un gasto como pagado directamente desde la fila (un solo toque).
  // Al pasar a 'pagado', el backend lo excluye de las alertas y aquí se
  // refresca la consulta de alertas para que la notificación desaparezca.
  const pagarMut = useMutation({
    mutationFn: (id) => costosApi.actualizarGasto(id, { estado: 'pagado', fecha_pago: new Date().toISOString().slice(0,10) }).then(r=>r.data),
    onSuccess: () => {
      qc.invalidateQueries({queryKey:['gastos']})
      qc.invalidateQueries({queryKey:['costos-alertas']})
      qc.invalidateQueries({queryKey:['costos-resumen']})
      toast.success('Gasto marcado como pagado')
    },
    onError: () => toast.error('No se pudo marcar como pagado'),
  })
  const anios = Array.from({length:5},(_,i)=>hoy.getFullYear()-2+i)

  // Si no hay categorías cargadas, ofrecer crear las base
  const CATEGORIAS_BASE = [
    { nombre:'Pago a proveedor', tipo:'proveedor', orden:1 },
    { nombre:'Salario',          tipo:'salario',   orden:2 },
    { nombre:'Alquiler',         tipo:'servicio',  orden:3 },
    { nombre:'Servicios (luz, agua, internet)', tipo:'servicio', orden:4 },
    { nombre:'Impuestos',        tipo:'otro',      orden:5 },
    { nombre:'Mantenimiento',    tipo:'otro',      orden:6 },
    { nombre:'Otros gastos',     tipo:'otro',      orden:7 },
  ]
  const seedMut = useMutation({
    mutationFn: async () => {
      for (const c of CATEGORIAS_BASE) { await costosApi.crearCategoria(c) }
    },
    onSuccess: () => { qc.invalidateQueries({queryKey:['cat-gasto']}); toast.success('Categorías creadas') },
    onError: () => toast.error('No se pudieron crear las categorías'),
  })
  const sinCategorias = catData && categorias.length === 0

  return <div>
    {sinCategorias && (
      <div style={{ marginBottom:'16px', padding:'14px 16px', borderRadius:'11px',
        background:C.warningBg, border:`1px solid ${C.warningBorder}`,
        display:'flex', alignItems:'center', justifyContent:'space-between', gap:'12px', flexWrap:'wrap' }}>
        <p style={{ fontSize:'13px', color:C.warning }}>
          No hay categorías de gasto cargadas. Creá las categorías base para empezar a registrar gastos.
        </p>
        <button onClick={()=>seedMut.mutate()} disabled={seedMut.isPending}
          style={{ padding:'8px 16px', background:C.sidebar, border:`1px solid ${C.gold}`,
            borderRadius:'9px', color:C.gold, fontSize:'13px', fontWeight:'500',
            cursor:seedMut.isPending?'wait':'pointer', whiteSpace:'nowrap' }}>
          {seedMut.isPending ? 'Creando...' : 'Crear categorías base'}
        </button>
      </div>
    )}
    <div style={{ display:'flex', gap:'10px', alignItems:'center', marginBottom:'16px', flexWrap:'wrap' }}>
      <FSelect value={mes} onChange={e=>setMes(Number(e.target.value))} style={{ width:'140px' }}>
        {MESES.slice(1).map((m,i)=><option key={i+1} value={i+1}>{m}</option>)}
      </FSelect>
      <FSelect value={anio} onChange={e=>setAnio(Number(e.target.value))} style={{ width:'90px' }}>
        {anios.map(a=><option key={a} value={a}>{a}</option>)}
      </FSelect>
      <div style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:'12px' }}>
        <div style={{ textAlign:'right' }}>
          <p style={{ fontSize:'11px', color:C.textMuted }}>Total del período</p>
          <p style={{ fontSize:'18px', fontWeight:'700', color:C.danger }}>{formatGs(total)}</p>
        </div>
        <button onClick={()=>{setEditando(null);setModal(true)}}
          style={{ display:'flex', alignItems:'center', gap:'6px', padding:'8px 16px',
            background:C.sidebar, border:`1px solid ${C.gold}`, borderRadius:'9px',
            color:C.gold, fontSize:'13px', fontWeight:'500', cursor:'pointer' }}>
          <Plus size={14}/> Registrar gasto
        </button>
      </div>
    </div>

    <div style={{ background:C.bg, border:`1px solid ${C.border}`, borderRadius:'12px', overflow:'hidden' }}>
      {isLoading ? <div style={{ padding:'40px', textAlign:'center', color:C.textMuted }}>Cargando...</div>
      : gastos.length===0 ? <div style={{ padding:'50px', textAlign:'center', color:C.textMuted }}>
          <TrendingDown size={40} style={{ margin:'0 auto 12px', opacity:0.2 }}/>
          <p style={{ fontSize:'15px', color:C.textSec }}>Sin gastos para {MESES[mes]} {anio}</p>
        </div>
      : <div style={{ overflowX:'auto' }}>
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead><tr style={{ background:C.bgSec }}>
              {['Descripción','Categoría','Proveedor','Monto','Método','Estado',''].map(h=>(
                <th key={h} style={{ padding:'9px 14px', textAlign:'left', fontSize:'10.5px',
                  fontWeight:'500', letterSpacing:'0.06em', textTransform:'uppercase',
                  color:C.textMuted, borderBottom:`1px solid ${C.border}` }}>{h}</th>))}
            </tr></thead>
            <tbody>
              {gastos.map(g=>(
                <tr key={g.id} style={{ borderBottom:`1px solid ${C.border}` }}>
                  <td style={{ padding:'10px 14px' }}>
                    <p style={{ fontSize:'13px', fontWeight:'500', color:C.text }}>{g.descripcion}</p>
                    {g.metodo_pago==='cheque' && g.cheque_fecha_cobro &&
                      <p style={{ fontSize:'11px', color:C.warning }}>
                        Cheque cobra: {new Date(g.cheque_fecha_cobro).toLocaleDateString('es-PY')}
                        {typeof g.dias_cheque==='number' && g.dias_cheque>=0 ? ` (en ${g.dias_cheque}d)` : ''}
                      </p>}
                  </td>
                  <td style={{ padding:'10px 14px' }}>
                    <Badge cfg={TIPO_COLOR[g.categoria_tipo]||TIPO_COLOR.otro}/>
                    <p style={{ fontSize:'11px', color:C.textMuted, marginTop:'2px' }}>{g.categoria_nombre}</p>
                  </td>
                  <td style={{ padding:'10px 14px', fontSize:'12.5px', color:C.textSec }}>{g.proveedor_nombre||g.empleado_nombre||'—'}</td>
                  <td style={{ padding:'10px 14px', textAlign:'right' }}>
                    <p style={{ fontSize:'14px', fontWeight:'600', color:C.danger }}>{formatGs(g.monto)}</p>
                  </td>
                  <td style={{ padding:'10px 14px', fontSize:'12px', color:C.textSec }}>{METODO_PAGO_LABEL[g.metodo_pago]||'—'}</td>
                  <td style={{ padding:'10px 14px' }}><Badge cfg={ESTADOS_GASTO[g.estado]||ESTADOS_GASTO.pendiente}/></td>
                  <td style={{ padding:'10px 14px' }}>
                    <div style={{ display:'flex', gap:'5px' }}>
                      {g.estado === 'pendiente' && (
                        <button
                          onClick={()=>{if(confirm('¿Marcar este gasto como pagado?'))pagarMut.mutate(g.id)}}
                          disabled={pagarMut.isPending}
                          title="Marcar como pagado"
                          style={{ width:'28px', height:'28px', borderRadius:'7px', cursor:'pointer',
                            background:C.successBg, border:`1px solid ${C.successBorder||C.success}`, color:C.success,
                            display:'flex', alignItems:'center', justifyContent:'center' }}><Check size={13}/></button>
                      )}
                      <button onClick={()=>{setEditando(g);setModal(true)}}
                        style={{ width:'28px', height:'28px', borderRadius:'7px', cursor:'pointer',
                          background:C.bgSec, border:`1px solid ${C.border}`, color:C.textSec,
                          display:'flex', alignItems:'center', justifyContent:'center' }}><Edit2 size={12}/></button>
                      <button onClick={()=>{if(confirm('¿Eliminar este gasto?'))delMut.mutate(g.id)}}
                        style={{ width:'28px', height:'28px', borderRadius:'7px', cursor:'pointer',
                          background:C.bgSec, border:`1px solid ${C.border}`, color:C.danger,
                          display:'flex', alignItems:'center', justifyContent:'center' }}><Trash2 size={12}/></button>
                    </div>
                  </td>
                </tr>))}
            </tbody>
          </table>
        </div>}
    </div>

    {modal && <ModalGasto gasto={editando} anio={anio} mes={mes}
      categorias={categorias} empleados={empData?.results||[]} proveedores={provData?.results||[]}
      onCerrar={()=>{setModal(false);setEditando(null)}}
      onGuardado={()=>{qc.invalidateQueries({queryKey:['gastos']});qc.invalidateQueries({queryKey:['costos-alertas']});setModal(false);setEditando(null)}}/>}
  </div>
}

// ════════════════════════════════════════════════════════
// SOLAPA PROVEEDORES
// ════════════════════════════════════════════════════════
function ModalProveedor({ proveedor, onCerrar, onGuardado }) {
  const esEdicion = Boolean(proveedor)
  const [form, setForm] = useState({
    nombre: proveedor?.nombre||'', rubro: proveedor?.rubro||'',
    contacto: proveedor?.contacto||'', telefono: proveedor?.telefono||'',
    email: proveedor?.email||'', ruc: proveedor?.ruc||'',
    direccion: proveedor?.direccion||'', notas: proveedor?.notas||'',
  })
  const [errores, setErrores] = useState({})
  const sf = (k,v)=>{ setForm(f=>({...f,[k]:v})); setErrores(e=>({...e,[k]:undefined})) }
  const mut = useMutation({
    mutationFn:()=>esEdicion
      ?costosApi.actualizarProveedor(proveedor.id,form).then(r=>r.data)
      :costosApi.crearProveedor(form).then(r=>r.data),
    onSuccess:()=>{ toast.success(esEdicion?'Proveedor actualizado':'Proveedor creado'); onGuardado() },
    onError:(err)=>{ setErrores(err.response?.data||{}); toast.error('Revisá los campos') }
  })
  const guardar = ()=>{ if(!form.nombre.trim()){setErrores({nombre:'Requerido'});return} mut.mutate() }

  return <Modal titulo={esEdicion?'Editar proveedor':'Nuevo proveedor'} onCerrar={onCerrar}>
    <Campo label="Nombre / Razón social *" error={errores.nombre}>
      <FInput value={form.nombre} onChange={e=>sf('nombre',e.target.value)}
        placeholder="Ej: Cerámica San Lorenzo S.A." error={errores.nombre}/>
    </Campo>
    <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'0 12px' }}>
      <Campo label="Rubro"><FInput value={form.rubro} onChange={e=>sf('rubro',e.target.value)} placeholder="Ej: Porcelanatos"/></Campo>
      <Campo label="RUC"><FInput value={form.ruc} onChange={e=>sf('ruc',e.target.value)} placeholder="80012345-6"/></Campo>
      <Campo label="Contacto"><FInput value={form.contacto} onChange={e=>sf('contacto',e.target.value)} placeholder="Nombre del contacto"/></Campo>
      <Campo label="Teléfono"><FInput value={form.telefono} onChange={e=>sf('telefono',e.target.value)} placeholder="0981 123 456"/></Campo>
      <Campo label="Email"><FInput type="email" value={form.email} onChange={e=>sf('email',e.target.value)} placeholder="ventas@proveedor.com"/></Campo>
      <Campo label="Dirección"><FInput value={form.direccion} onChange={e=>sf('direccion',e.target.value)} placeholder="Ciudad"/></Campo>
    </div>
    <Campo label="Notas">
      <textarea value={form.notas} onChange={e=>sf('notas',e.target.value)} rows={2}
        style={{ width:'100%', padding:'8px 10px', border:`1px solid ${C.border}`, borderRadius:'8px',
          fontSize:'13.5px', color:C.text, background:C.bg, outline:'none', resize:'vertical', fontFamily:'inherit' }}
        onFocus={e=>e.target.style.borderColor=C.gold} onBlur={e=>e.target.style.borderColor=C.border}/>
    </Campo>
    <div style={{ display:'flex', gap:'10px' }}>
      <BtnCancelar onClick={onCerrar}/>
      <BtnGuardar pending={mut.isPending} onClick={guardar} label={esEdicion?'Guardar':'Crear proveedor'}/>
    </div>
  </Modal>
}

function SolapaProveedores() {
  const qc = useQueryClient()
  const [modal, setModal] = useState(false)
  const [editando, setEditando] = useState(null)
  const {data, isLoading} = useQuery({ queryKey:['proveedores'],
    queryFn:()=>costosApi.proveedores().then(r=>r.data), staleTime:60_000 })
  const proveedores = data?.results||[]
  const delMut = useMutation({ mutationFn: id=>costosApi.desactivarProveedor(id),
    onSuccess: ()=>{ qc.invalidateQueries({queryKey:['proveedores']}); toast.success('Proveedor desactivado') } })

  return <div>
    <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:'16px' }}>
      <button onClick={()=>{setEditando(null);setModal(true)}}
        style={{ display:'flex', alignItems:'center', gap:'6px', padding:'8px 16px',
          background:C.sidebar, border:`1px solid ${C.gold}`, borderRadius:'9px',
          color:C.gold, fontSize:'13px', fontWeight:'500', cursor:'pointer' }}>
        <Plus size={14}/> Nuevo proveedor
      </button>
    </div>
    <div style={{ background:C.bg, border:`1px solid ${C.border}`, borderRadius:'12px', overflow:'hidden' }}>
      {isLoading ? <div style={{ padding:'40px', textAlign:'center', color:C.textMuted }}>Cargando...</div>
      : proveedores.length===0 ? <div style={{ padding:'50px', textAlign:'center', color:C.textMuted }}>
          <Building2 size={40} style={{ margin:'0 auto 12px', opacity:0.2 }}/>
          <p style={{ fontSize:'15px', color:C.textSec }}>Sin proveedores registrados</p></div>
      : <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead><tr style={{ background:C.bgSec }}>
            {['Nombre','Rubro','Contacto','Teléfono','Estado',''].map(h=>(
              <th key={h} style={{ padding:'9px 14px', textAlign:'left', fontSize:'10.5px',
                fontWeight:'500', letterSpacing:'0.06em', textTransform:'uppercase',
                color:C.textMuted, borderBottom:`1px solid ${C.border}` }}>{h}</th>))}
          </tr></thead>
          <tbody>
            {proveedores.map(p=>(
              <tr key={p.id} style={{ borderBottom:`1px solid ${C.border}`, opacity:p.activo?1:0.55 }}>
                <td style={{ padding:'10px 14px', fontSize:'13px', fontWeight:'500', color:C.text }}>{p.nombre}
                  {p.ruc && <p style={{ fontSize:'11px', color:C.textMuted, fontWeight:'400' }}>RUC: {p.ruc}</p>}
                </td>
                <td style={{ padding:'10px 14px', fontSize:'13px', color:C.textSec }}>{p.rubro||'—'}</td>
                <td style={{ padding:'10px 14px', fontSize:'13px', color:C.textSec }}>{p.contacto||'—'}</td>
                <td style={{ padding:'10px 14px', fontSize:'13px', color:C.textSec }}>{p.telefono||'—'}</td>
                <td style={{ padding:'10px 14px' }}>
                  <span style={{ fontSize:'12px', fontWeight:'500', color:p.activo?C.success:C.danger }}>
                    {p.activo?'Activo':'Inactivo'}</span></td>
                <td style={{ padding:'10px 14px' }}>
                  <div style={{ display:'flex', gap:'5px' }}>
                    <button onClick={()=>{setEditando(p);setModal(true)}}
                      style={{ width:'28px', height:'28px', borderRadius:'7px', cursor:'pointer',
                        background:C.bgSec, border:`1px solid ${C.border}`, color:C.textSec,
                        display:'flex', alignItems:'center', justifyContent:'center' }}><Edit2 size={12}/></button>
                    {p.activo && <button onClick={()=>{if(confirm('¿Desactivar proveedor?'))delMut.mutate(p.id)}}
                      style={{ width:'28px', height:'28px', borderRadius:'7px', cursor:'pointer',
                        background:C.bgSec, border:`1px solid ${C.border}`, color:C.danger,
                        display:'flex', alignItems:'center', justifyContent:'center' }}><X size={12}/></button>}
                  </div></td>
              </tr>))}
          </tbody>
        </table>}
    </div>
    {modal && <ModalProveedor proveedor={editando} onCerrar={()=>{setModal(false);setEditando(null)}}
      onGuardado={()=>{qc.invalidateQueries({queryKey:['proveedores']});setModal(false);setEditando(null)}}/>}
  </div>
}

// ════════════════════════════════════════════════════════
// SOLAPA PEDIDOS A PROVEEDOR
// ════════════════════════════════════════════════════════
function ModalPedidoProveedor({ pedido, proveedores, onCerrar, onGuardado }) {
  const esEdicion = Boolean(pedido)
  const hoyStr = new Date().toISOString().slice(0,10)
  const [form, setForm] = useState({
    proveedor_id: pedido?.proveedor_id||'', descripcion: pedido?.descripcion||'',
    monto_estimado: pedido?.monto_estimado||'',
    fecha_pedido: pedido?.fecha_pedido||hoyStr,
    fecha_entrega_estimada: pedido?.fecha_entrega_estimada||'',
    estado: pedido?.estado||'pendiente', notas: pedido?.notas||'',
  })
  const [errores, setErrores] = useState({})
  const sf = (k,v)=>{ setForm(f=>({...f,[k]:v})); setErrores(e=>({...e,[k]:undefined})) }
  const mut = useMutation({
    mutationFn:()=>{
      const payload = {...form}
      if(!payload.monto_estimado) delete payload.monto_estimado
      return esEdicion
        ? costosApi.actualizarPedidoProveedor(pedido.id,payload).then(r=>r.data)
        : costosApi.crearPedidoProveedor(payload).then(r=>r.data)
    },
    onSuccess:()=>{ toast.success(esEdicion?'Pedido actualizado':'Pedido registrado'); onGuardado() },
    onError:(err)=>{ setErrores(err.response?.data||{}); toast.error('Revisá los campos') }
  })
  const guardar = ()=>{
    const e={}
    if(!form.proveedor_id) e.proveedor_id='Requerido'
    if(!form.descripcion.trim()) e.descripcion='Requerido'
    if(!form.fecha_entrega_estimada) e.fecha_entrega_estimada='Requerido'
    if(Object.keys(e).length){setErrores(e);return}
    mut.mutate()
  }

  return <Modal titulo={esEdicion?'Editar pedido a proveedor':'Nuevo pedido a proveedor'} onCerrar={onCerrar}>
    <Campo label="Proveedor *" error={errores.proveedor_id}>
      <FSelect value={form.proveedor_id} onChange={e=>sf('proveedor_id',e.target.value)}>
        <option value="">Seleccionar...</option>
        {proveedores.map(p=><option key={p.id} value={p.id}>{p.nombre}</option>)}
      </FSelect>
    </Campo>
    <Campo label="¿Qué se pidió? *" error={errores.descripcion}>
      <FInput value={form.descripcion} onChange={e=>sf('descripcion',e.target.value)}
        placeholder="Ej: 200 cajas porcelanato 60x60 beige" error={errores.descripcion}/>
    </Campo>
    <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'0 12px' }}>
      <Campo label="Monto estimado (Gs.)">
        <FInput type="number" min="0" step="1000" value={form.monto_estimado}
          onChange={e=>sf('monto_estimado',e.target.value)} placeholder="Opcional"
          style={{ textAlign:'right' }}/>
      </Campo>
      <Campo label="Estado">
        <FSelect value={form.estado} onChange={e=>sf('estado',e.target.value)}>
          <option value="pendiente">Pendiente</option>
          <option value="en_camino">En camino</option>
          <option value="recibido">Recibido</option>
          <option value="cancelado">Cancelado</option>
        </FSelect>
      </Campo>
      <Campo label="Fecha del pedido">
        <FInput type="date" value={form.fecha_pedido} onChange={e=>sf('fecha_pedido',e.target.value)}/>
      </Campo>
      <Campo label="Entrega estimada (plazo) *" error={errores.fecha_entrega_estimada}>
        <FInput type="date" value={form.fecha_entrega_estimada}
          onChange={e=>sf('fecha_entrega_estimada',e.target.value)} error={errores.fecha_entrega_estimada}/>
      </Campo>
    </div>
    <Campo label="Notas">
      <textarea value={form.notas} onChange={e=>sf('notas',e.target.value)} rows={2}
        placeholder="Condiciones, observaciones..." style={{ width:'100%', padding:'8px 10px',
          border:`1px solid ${C.border}`, borderRadius:'8px', fontSize:'13.5px',
          color:C.text, background:C.bg, outline:'none', resize:'vertical', fontFamily:'inherit' }}
        onFocus={e=>e.target.style.borderColor=C.gold} onBlur={e=>e.target.style.borderColor=C.border}/>
    </Campo>
    <div style={{ display:'flex', gap:'10px' }}>
      <BtnCancelar onClick={onCerrar}/>
      <BtnGuardar pending={mut.isPending} onClick={guardar} label={esEdicion?'Guardar':'Registrar pedido'}/>
    </div>
  </Modal>
}

function SolapaPedidosProveedor() {
  const qc = useQueryClient()
  const [modal, setModal] = useState(false)
  const [editando, setEditando] = useState(null)
  const {data, isLoading} = useQuery({ queryKey:['pedidos-prov'],
    queryFn:()=>costosApi.pedidosProveedor().then(r=>r.data), staleTime:30_000 })
  const {data:provData} = useQuery({ queryKey:['proveedores'],
    queryFn:()=>costosApi.proveedores({activos:1}).then(r=>r.data), staleTime:300_000 })
  const pedidos = data?.results||[]
  const delMut = useMutation({ mutationFn: id=>costosApi.eliminarPedidoProveedor(id),
    onSuccess: ()=>{ qc.invalidateQueries({queryKey:['pedidos-prov']}); qc.invalidateQueries({queryKey:['costos-alertas']}); toast.success('Pedido eliminado') } })

  const fmtFecha = f => f ? new Date(f).toLocaleDateString('es-PY') : '—'

  return <div>
    <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:'16px' }}>
      <button onClick={()=>{setEditando(null);setModal(true)}}
        style={{ display:'flex', alignItems:'center', gap:'6px', padding:'8px 16px',
          background:C.sidebar, border:`1px solid ${C.gold}`, borderRadius:'9px',
          color:C.gold, fontSize:'13px', fontWeight:'500', cursor:'pointer' }}>
        <Plus size={14}/> Nuevo pedido
      </button>
    </div>
    <div style={{ background:C.bg, border:`1px solid ${C.border}`, borderRadius:'12px', overflow:'hidden' }}>
      {isLoading ? <div style={{ padding:'40px', textAlign:'center', color:C.textMuted }}>Cargando...</div>
      : pedidos.length===0 ? <div style={{ padding:'50px', textAlign:'center', color:C.textMuted }}>
          <Truck size={40} style={{ margin:'0 auto 12px', opacity:0.2 }}/>
          <p style={{ fontSize:'15px', color:C.textSec }}>Sin pedidos a proveedores</p></div>
      : <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead><tr style={{ background:C.bgSec }}>
            {['Proveedor','Descripción','Entrega estimada','Estado',''].map(h=>(
              <th key={h} style={{ padding:'9px 14px', textAlign:'left', fontSize:'10.5px',
                fontWeight:'500', letterSpacing:'0.06em', textTransform:'uppercase',
                color:C.textMuted, borderBottom:`1px solid ${C.border}` }}>{h}</th>))}
          </tr></thead>
          <tbody>
            {pedidos.map(p=>{
              const atrasado = typeof p.dias_entrega==='number' && p.dias_entrega<0 &&
                ['pendiente','en_camino'].includes(p.estado)
              return <tr key={p.id} style={{ borderBottom:`1px solid ${C.border}` }}>
                <td style={{ padding:'10px 14px', fontSize:'13px', fontWeight:'500', color:C.text }}>{p.proveedor_nombre}</td>
                <td style={{ padding:'10px 14px', fontSize:'12.5px', color:C.textSec }}>
                  {p.descripcion}
                  {p.monto_estimado && <p style={{ fontSize:'11px', color:C.textMuted }}>~ {formatGs(p.monto_estimado)}</p>}
                </td>
                <td style={{ padding:'10px 14px', fontSize:'12.5px', color: atrasado?C.danger:C.textSec }}>
                  {fmtFecha(p.fecha_entrega_estimada)}
                  {typeof p.dias_entrega==='number' && ['pendiente','en_camino'].includes(p.estado) &&
                    <p style={{ fontSize:'11px', color: atrasado?C.danger:C.textMuted }}>
                      {atrasado ? `Atrasado ${Math.abs(p.dias_entrega)}d` : `En ${p.dias_entrega}d`}</p>}
                </td>
                <td style={{ padding:'10px 14px' }}><Badge cfg={ESTADOS_PEDPROV[p.estado]||ESTADOS_PEDPROV.pendiente}/></td>
                <td style={{ padding:'10px 14px' }}>
                  <div style={{ display:'flex', gap:'5px' }}>
                    <button onClick={()=>{setEditando(p);setModal(true)}}
                      style={{ width:'28px', height:'28px', borderRadius:'7px', cursor:'pointer',
                        background:C.bgSec, border:`1px solid ${C.border}`, color:C.textSec,
                        display:'flex', alignItems:'center', justifyContent:'center' }}><Edit2 size={12}/></button>
                    <button onClick={()=>{if(confirm('¿Eliminar pedido?'))delMut.mutate(p.id)}}
                      style={{ width:'28px', height:'28px', borderRadius:'7px', cursor:'pointer',
                        background:C.bgSec, border:`1px solid ${C.border}`, color:C.danger,
                        display:'flex', alignItems:'center', justifyContent:'center' }}><Trash2 size={12}/></button>
                  </div></td>
              </tr>})}
          </tbody>
        </table>}
    </div>
    {modal && <ModalPedidoProveedor pedido={editando} proveedores={provData?.results||[]}
      onCerrar={()=>{setModal(false);setEditando(null)}}
      onGuardado={()=>{qc.invalidateQueries({queryKey:['pedidos-prov']});qc.invalidateQueries({queryKey:['costos-alertas']});setModal(false);setEditando(null)}}/>}
  </div>
}

// ════════════════════════════════════════════════════════
// SOLAPA EMPLEADOS
// ════════════════════════════════════════════════════════
function ModalEmpleado({ empleado, onCerrar, onGuardado }) {
  const esEdicion = Boolean(empleado)
  const [form, setForm] = useState({
    nombre_completo:empleado?.nombre_completo||'', cargo:empleado?.cargo||'',
    salario_base:empleado?.salario_base||'', fecha_ingreso:empleado?.fecha_ingreso||'',
    notas:empleado?.notas||'',
  })
  const [errores, setErrores] = useState({})
  const sf = (k,v)=>{ setForm(f=>({...f,[k]:v})); setErrores(e=>({...e,[k]:undefined})) }
  const mut = useMutation({
    mutationFn:()=>esEdicion
      ?costosApi.actualizarEmpleado(empleado.id,form).then(r=>r.data)
      :costosApi.crearEmpleado(form).then(r=>r.data),
    onSuccess:()=>{ toast.success(esEdicion?'Empleado actualizado':'Empleado creado'); onGuardado() },
    onError:(err)=>{ setErrores(err.response?.data||{}); toast.error('Error al guardar') }
  })
  const guardar = ()=>{
    const e={}
    if(!form.nombre_completo.trim()) e.nombre_completo='Requerido'
    if(!form.salario_base||Number(form.salario_base)<=0) e.salario_base='Debe ser mayor a 0'
    if(Object.keys(e).length){setErrores(e);return}
    mut.mutate()
  }
  return <Modal titulo={esEdicion?'Editar empleado':'Nuevo empleado'} onCerrar={onCerrar}>
    <Campo label="Nombre completo *" error={errores.nombre_completo}>
      <FInput value={form.nombre_completo} onChange={e=>sf('nombre_completo',e.target.value)}
        placeholder="Ej: María González" error={errores.nombre_completo}/>
    </Campo>
    <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'0 12px' }}>
      <Campo label="Cargo"><FInput value={form.cargo} onChange={e=>sf('cargo',e.target.value)} placeholder="Ej: Vendedora"/></Campo>
      <Campo label="Salario mensual (Gs.) *" error={errores.salario_base}>
        <FInput type="number" min="1" step="50000" value={form.salario_base}
          onChange={e=>sf('salario_base',e.target.value)} placeholder="0"
          error={errores.salario_base} style={{ textAlign:'right', fontWeight:'600' }}/>
      </Campo>
      <Campo label="Fecha de ingreso"><FInput type="date" value={form.fecha_ingreso} onChange={e=>sf('fecha_ingreso',e.target.value)}/></Campo>
    </div>
    <Campo label="Notas">
      <textarea value={form.notas} onChange={e=>sf('notas',e.target.value)} rows={2}
        style={{ width:'100%', padding:'8px 10px', border:`1px solid ${C.border}`, borderRadius:'8px',
          fontSize:'13.5px', color:C.text, background:C.bg, outline:'none', resize:'vertical', fontFamily:'inherit' }}
        onFocus={e=>e.target.style.borderColor=C.gold} onBlur={e=>e.target.style.borderColor=C.border}/>
    </Campo>
    <div style={{ display:'flex', gap:'10px' }}>
      <BtnCancelar onClick={onCerrar}/>
      <BtnGuardar pending={mut.isPending} onClick={guardar} label={esEdicion?'Guardar':'Crear empleado'}/>
    </div>
  </Modal>
}

function SolapaEmpleados() {
  const qc = useQueryClient()
  const [modal, setModal] = useState(false)
  const [editando, setEditando] = useState(null)
  const {data, isLoading} = useQuery({ queryKey:['empleados'],
    queryFn:()=>costosApi.empleados().then(r=>r.data), staleTime:60_000 })
  const empleados = data?.results||[]
  const masaSalarial = empleados.filter(e=>e.activo).reduce((s,e)=>s+Number(e.salario_base),0)
  const toggleMut = useMutation({ mutationFn: emp=>costosApi.actualizarEmpleado(emp.id,{activo:!emp.activo}),
    onSuccess: ()=>{ qc.invalidateQueries({queryKey:['empleados']}); toast.success('Actualizado') } })

  return <div>
    <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:'16px', flexWrap:'wrap', gap:'10px' }}>
      <div style={{ padding:'12px 18px', background:C.dangerBg, border:`1px solid ${C.dangerBorder}`, borderRadius:'10px' }}>
        <p style={{ fontSize:'11px', color:C.textMuted }}>Masa salarial mensual</p>
        <p style={{ fontSize:'20px', fontWeight:'700', color:C.danger }}>{formatGs(masaSalarial)}</p>
      </div>
      <button onClick={()=>{setEditando(null);setModal(true)}}
        style={{ display:'flex', alignItems:'center', gap:'6px', padding:'8px 16px',
          background:C.sidebar, border:`1px solid ${C.gold}`, borderRadius:'9px',
          color:C.gold, fontSize:'13px', fontWeight:'500', cursor:'pointer' }}>
        <Plus size={14}/> Nuevo empleado</button>
    </div>
    <div style={{ background:C.bg, border:`1px solid ${C.border}`, borderRadius:'12px', overflow:'hidden' }}>
      {isLoading ? <div style={{ padding:'40px', textAlign:'center', color:C.textMuted }}>Cargando...</div>
      : empleados.length===0 ? <div style={{ padding:'50px', textAlign:'center', color:C.textMuted }}>Sin empleados</div>
      : <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead><tr style={{ background:C.bgSec }}>
            {['Nombre','Cargo','Salario mensual','Estado',''].map(h=>(
              <th key={h} style={{ padding:'9px 14px', textAlign:'left', fontSize:'10.5px',
                fontWeight:'500', letterSpacing:'0.06em', textTransform:'uppercase',
                color:C.textMuted, borderBottom:`1px solid ${C.border}` }}>{h}</th>))}
          </tr></thead>
          <tbody>
            {empleados.map(emp=>(
              <tr key={emp.id} style={{ borderBottom:`1px solid ${C.border}`, opacity:emp.activo?1:0.55 }}>
                <td style={{ padding:'10px 14px' }}>
                  <div style={{ display:'flex', alignItems:'center', gap:'8px' }}>
                    <div style={{ width:'32px', height:'32px', borderRadius:'50%', background:C.sidebar,
                      border:`1px solid ${C.gold}`, display:'flex', alignItems:'center', justifyContent:'center',
                      fontSize:'12px', fontWeight:'500', color:C.gold, flexShrink:0 }}>
                      {emp.nombre_completo.slice(0,2).toUpperCase()}</div>
                    <p style={{ fontSize:'13px', fontWeight:'500', color:C.text }}>{emp.nombre_completo}</p>
                  </div></td>
                <td style={{ padding:'10px 14px', fontSize:'13px', color:C.textSec }}>{emp.cargo||'—'}</td>
                <td style={{ padding:'10px 14px' }}>
                  <p style={{ fontSize:'14px', fontWeight:'600', color:C.danger }}>{formatGs(emp.salario_base)}</p></td>
                <td style={{ padding:'10px 14px' }}>
                  <span style={{ fontSize:'12px', fontWeight:'500', color:emp.activo?C.success:C.danger }}>
                    {emp.activo?'Activo':'Inactivo'}</span></td>
                <td style={{ padding:'10px 14px' }}>
                  <div style={{ display:'flex', gap:'5px' }}>
                    <button onClick={()=>{setEditando(emp);setModal(true)}}
                      style={{ width:'28px', height:'28px', borderRadius:'7px', cursor:'pointer',
                        background:C.bgSec, border:`1px solid ${C.border}`, color:C.textSec,
                        display:'flex', alignItems:'center', justifyContent:'center' }}><Edit2 size={12}/></button>
                    <button onClick={()=>toggleMut.mutate(emp)}
                      style={{ width:'28px', height:'28px', borderRadius:'7px', cursor:'pointer',
                        background:C.bgSec, border:`1px solid ${C.border}`, color:emp.activo?C.danger:C.success,
                        display:'flex', alignItems:'center', justifyContent:'center' }}><X size={12}/></button>
                  </div></td>
              </tr>))}
          </tbody>
        </table>}
    </div>
    {modal && <ModalEmpleado empleado={editando} onCerrar={()=>{setModal(false);setEditando(null)}}
      onGuardado={()=>{qc.invalidateQueries({queryKey:['empleados']});setModal(false);setEditando(null)}}/>}
  </div>
}

// ════════════════════════════════════════════════════════
// PÁGINA PRINCIPAL
// ════════════════════════════════════════════════════════
export default function CostosPage() {
  const [solapa, setSolapa] = useState('gastos')
  const SOLAPAS = [
    { id:'gastos',    label:'Gastos del mes',   icon:<Receipt size={15}/> },
    { id:'proveedores',label:'Proveedores',      icon:<Building2 size={15}/> },
    { id:'pedidos',   label:'Pedidos a proveedor',icon:<Truck size={15}/> },
    { id:'empleados', label:'Empleados',          icon:<Users size={15}/> },
  ]
  return <Layout pageTitle="Costos Operativos" breadcrumbs={['Costos Operativos']}>
    <BannerAlertas/>
    <div style={{ display:'flex', gap:'2px', borderBottom:`1px solid ${C.border}`, marginBottom:'20px', flexWrap:'wrap' }}>
      {SOLAPAS.map(s=>(
        <button key={s.id} onClick={()=>setSolapa(s.id)}
          style={{ display:'flex', alignItems:'center', gap:'6px', padding:'10px 18px',
            background:'transparent', border:'none',
            borderBottom:`2px solid ${solapa===s.id?C.gold:'transparent'}`,
            color:solapa===s.id?C.goldDark:C.textSec, fontWeight:solapa===s.id?'500':'400',
            fontSize:'13.5px', cursor:'pointer', transition:'all 120ms' }}>
          {s.icon} {s.label}</button>))}
    </div>
    {solapa==='gastos'      && <SolapaGastos/>}
    {solapa==='proveedores' && <SolapaProveedores/>}
    {solapa==='pedidos'     && <SolapaPedidosProveedor/>}
    {solapa==='empleados'   && <SolapaEmpleados/>}
    <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
  </Layout>
}
