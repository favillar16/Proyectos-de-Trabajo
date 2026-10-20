/**
 * ClientesPage
 * Lo que invirtió cada cliente en el local, de mayor a menor — solo admin.
 *
 * Existe para decidir a fin de año un descuento o un regalo a los que más
 * compraron, así que muestra solo plata: lo cobrado, menos lo reintegrado
 * por devoluciones. La cuenta y cómo se agrupa a un mismo cliente están en
 * backend/apps/caja/clientes.py.
 */
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Search, Loader2, ChevronDown, ChevronRight, FileText, FileSpreadsheet,
  Users, Award, BookUser,
} from 'lucide-react'
import Layout from '../components/layout/Layout'
import { cajaApi } from '../services/api'
import toast from 'react-hot-toast'

const C = {
  sidebar:'#453941',
  gold:'#B99C74', goldDark:'#8a7355', goldMuted:'rgba(185,156,116,0.10)',
  border:'#e8e4df', bg:'#ffffff', bgSec:'#fafaf9', bgTer:'#f5f4f2',
  text:'#1a1714', textSec:'#6b6560', textMuted:'#9e9892',
  success:'#3d7a5a', successBg:'#edf7f1',
  danger:'#9a3030',
  info:'#2a5c8a', infoBg:'#eef4fb',
}

function formatGs(v) { return `Gs. ${Math.round(Number(v || 0)).toLocaleString('es-PY')}` }
function formatFecha(iso) {
  if (!iso) return '—'
  const [a, m, d] = iso.split('-')
  return `${d}/${m}/${a}`
}

function useDebounce(value, delay = 350) {
  const [d, setD] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setD(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return d
}

function descargarBlob(blobData, nombre) {
  const url = window.URL.createObjectURL(new Blob([blobData]))
  const a = document.createElement('a')
  a.href = url
  a.download = nombre
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

function Tarjeta({ icono: Icono, etiqueta, valor, nota }) {
  return (
    <div style={{ flex:'1 1 180px', background:C.bg, border:`1px solid ${C.border}`,
      borderRadius:'12px', padding:'14px 16px' }}>
      <div style={{ display:'flex', alignItems:'center', gap:'6px', marginBottom:'6px' }}>
        <Icono size={14} style={{ color:C.goldDark }} />
        <span style={{ fontSize:'12px', color:C.textSec }}>{etiqueta}</span>
      </div>
      <p style={{ fontSize:'20px', fontWeight:'600', color:C.text }}>{valor}</p>
      {nota && <p style={{ fontSize:'11px', color:C.textMuted, marginTop:'2px' }}>{nota}</p>}
    </div>
  )
}

function FilaCliente({ cliente, abierto, onAlternar }) {
  const c = cliente
  return (
    <div style={{ borderBottom:`1px solid ${C.border}` }}>
      <button onClick={onAlternar}
        style={{ width:'100%', display:'flex', alignItems:'center', gap:'12px',
          padding:'12px 14px', background: abierto ? C.bgSec : C.bg, border:'none',
          cursor:'pointer', textAlign:'left', flexWrap:'wrap' }}>
        <span style={{ width:'28px', fontSize:'13px', fontWeight:'600',
          color: c.posicion <= 3 ? C.goldDark : C.textMuted }}>
          {c.posicion}
        </span>
        <div style={{ flex:'1 1 200px', minWidth:0 }}>
          <p style={{ fontSize:'14px', fontWeight:'500', color:C.text,
            overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
            {c.nombre || 'Sin nombre'}
            {c.en_padron && (
              <span style={{ marginLeft:'8px', fontSize:'10.5px', padding:'1px 7px',
                borderRadius:'20px', background:C.infoBg, color:C.info }}>
                padrón
              </span>
            )}
          </p>
          <p style={{ fontSize:'12px', color:C.textMuted }}>
            {c.documento || 'Sin CI/RUC'}{c.telefono ? ` · ${c.telefono}` : ''}
          </p>
        </div>
        <div style={{ flex:'0 1 170px', fontSize:'12px', color:C.textSec }}>
          {c.compras} compra{c.compras !== 1 ? 's' : ''} · última {formatFecha(c.ultima_compra)}
        </div>
        <div style={{ flex:'0 0 auto', textAlign:'right', minWidth:'130px' }}>
          <p style={{ fontSize:'15px', fontWeight:'600', color:C.text }}>{formatGs(c.total)}</p>
          {c.reintegrado > 0 && (
            <p style={{ fontSize:'11px', color:C.textMuted }}>
              ya restado {formatGs(c.reintegrado)} devuelto
            </p>
          )}
        </div>
        {abierto ? <ChevronDown size={16} style={{ color:C.textMuted }} />
                 : <ChevronRight size={16} style={{ color:C.textMuted }} />}
      </button>

      {abierto && (
        <div style={{ padding:'4px 14px 14px 54px', background:C.bgSec }}>
          {c.detalle.map((d, i) => (
            <div key={i} style={{ display:'flex', justifyContent:'space-between', gap:'10px',
              padding:'5px 0', fontSize:'12.5px', color:C.textSec,
              borderBottom: i < c.detalle.length - 1 ? `1px dashed ${C.border}` : 'none' }}>
              <span>
                {formatFecha(d.fecha)} · {d.pedido}
                {d.cambio ? ' · cambio' : ''}
                {d.monto < 0 ? ` · devolución ${d.ticket}` : ''}
              </span>
              <span style={{ fontWeight:'500', color: d.monto < 0 ? C.danger : C.text }}>
                {d.monto < 0 ? '− ' : ''}{formatGs(Math.abs(d.monto))}
              </span>
            </div>
          ))}
          {c.compras > 0 && (
            <p style={{ fontSize:'11.5px', color:C.textMuted, marginTop:'8px' }}>
              Ticket promedio: {formatGs(c.ticket_promedio)}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export default function ClientesPage() {
  const anioActual = new Date().getFullYear()
  const anios = [anioActual, anioActual - 1, anioActual - 2]
  const [anio, setAnio] = useState(anioActual)
  const [buscar, setBuscar] = useState('')
  const [abierto, setAbierto] = useState(null)
  const [descargando, setDescargando] = useState(null)
  const buscarDeb = useDebounce(buscar)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['clientes-resumen', anio, buscarDeb],
    queryFn: () => cajaApi.resumenClientes({ anio, buscar: buscarDeb || undefined })
      .then(r => r.data),
    // Sin parpadeo al cambiar de año o tipear: queda el listado anterior.
    placeholderData: prev => prev,
  })

  const descargar = async (formato) => {
    setDescargando(formato)
    try {
      const res = await cajaApi.descargarClientes(formato, { anio, buscar: buscarDeb || undefined })
      descargarBlob(res.data, `clientes_${anio}.${formato === 'pdf' ? 'pdf' : 'xlsx'}`)
    } catch {
      toast.error('No se pudo generar el listado')
    } finally {
      setDescargando(null)
    }
  }

  const clientes = data?.clientes || []
  const totales = data?.totales

  return (
    <Layout pageTitle="Clientes" breadcrumbs={['Clientes']}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center',
        marginBottom:'16px', flexWrap:'wrap', gap:'12px' }}>
        <p style={{ fontSize:'13.5px', color:C.textSec, maxWidth:'560px' }}>
          Lo que invirtió cada cliente: lo cobrado menos lo devuelto. Sirve para
          elegir a quién darle un descuento o un regalo a fin de año.
        </p>
        <div style={{ display:'flex', gap:'8px' }}>
          {[['pdf', 'PDF', FileText], ['xlsx', 'Excel', FileSpreadsheet]].map(([f, l, Icono]) => (
            <button key={f} onClick={() => descargar(f)} disabled={!!descargando}
              style={{ display:'flex', alignItems:'center', gap:'6px', height:'38px',
                padding:'0 14px', borderRadius:'9px', cursor:'pointer',
                background:C.bg, border:`1px solid ${C.border}`, color:C.textSec,
                fontSize:'13px' }}>
              {descargando === f ? <Loader2 size={14} className="animate-spin" /> : <Icono size={14} />}
              {l}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display:'flex', gap:'10px', marginBottom:'16px', flexWrap:'wrap' }}>
        <div style={{ display:'flex', gap:'6px' }}>
          {anios.map(a => (
            <button key={a} onClick={() => { setAnio(a); setAbierto(null) }}
              style={{ height:'38px', padding:'0 14px', borderRadius:'9px', cursor:'pointer',
                fontSize:'13px', fontWeight: anio === a ? '600' : '400',
                border:`1.5px solid ${anio === a ? C.gold : C.border}`,
                background: anio === a ? C.goldMuted : C.bg,
                color: anio === a ? C.goldDark : C.textSec }}>
              {a}
            </button>
          ))}
        </div>
        <div style={{ flex:'1 1 220px', position:'relative' }}>
          <Search size={15} style={{ position:'absolute', left:'12px', top:'50%',
            transform:'translateY(-50%)', color:C.textMuted }} />
          <input value={buscar} onChange={e => setBuscar(e.target.value)}
            placeholder="Buscar por nombre o CI/RUC"
            style={{ width:'100%', height:'38px', padding:'0 12px 0 34px',
              border:`1px solid ${C.border}`, borderRadius:'9px', fontSize:'13.5px',
              color:C.text, background:C.bg, outline:'none' }} />
        </div>
      </div>

      {totales && (
        <div style={{ display:'flex', gap:'10px', marginBottom:'16px', flexWrap:'wrap' }}>
          <Tarjeta icono={Users} etiqueta="Clientes con compras" valor={totales.clientes} />
          <Tarjeta icono={Award} etiqueta={`Total invertido en ${anio}`}
            valor={formatGs(totales.invertido)} />
          {totales.sin_identificar !== 0 && (
            <Tarjeta icono={BookUser} etiqueta="Ventas sin cliente"
              valor={formatGs(totales.sin_identificar)}
              nota="Cobros sin nombre ni CI/RUC: no se pueden atribuir a nadie." />
          )}
        </div>
      )}

      <div style={{ background:C.bg, border:`1px solid ${C.border}`, borderRadius:'12px',
        overflow:'hidden' }}>
        {isLoading ? (
          <div style={{ padding:'40px', display:'flex', justifyContent:'center' }}>
            <Loader2 size={22} className="animate-spin" style={{ color:C.gold }} />
          </div>
        ) : isError ? (
          <p style={{ padding:'24px', fontSize:'13.5px', color:C.danger }}>
            No se pudo cargar el listado de clientes.
          </p>
        ) : clientes.length === 0 ? (
          <p style={{ padding:'24px', fontSize:'13.5px', color:C.textMuted }}>
            {buscarDeb ? 'Ningún cliente coincide con la búsqueda.' : `Sin ventas cobradas en ${anio}.`}
          </p>
        ) : clientes.map(c => (
          <FilaCliente key={c.clave} cliente={c} abierto={abierto === c.clave}
            onAlternar={() => setAbierto(abierto === c.clave ? null : c.clave)} />
        ))}
      </div>
    </Layout>
  )
}
