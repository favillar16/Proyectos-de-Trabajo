/**
 * PanelReportes
 * Botones para descargar los reportes de Stock, Balance de Ventas y
 * Extracto de Caja en formato PDF o Excel.
 * Pensado para incrustarse en el Dashboard (solo admin).
 */
import { useState } from 'react'
import { Package, BarChart3, Wallet, FileText, FileSpreadsheet, Loader2 } from 'lucide-react'
import { cajaApi } from '../../services/api'
import toast from 'react-hot-toast'

const C = {
  sidebar:'#453941', gold:'#B99C74', goldDark:'#8a7355', goldMuted:'rgba(185,156,116,0.10)',
  border:'#e8e4df', bg:'#ffffff', bgSec:'#fafaf9', bgTer:'#f5f4f2',
  text:'#1a1714', textSec:'#6b6560', textMuted:'#9e9892',
  success:'#3d7a5a',
}

// Dispara la descarga del blob recibido
function descargarBlob(blobData, nombreSugerido) {
  const url = window.URL.createObjectURL(new Blob([blobData]))
  const a = document.createElement('a')
  a.href = url
  a.download = nombreSugerido
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

const REPORTES = [
  { tipo:'stock',  label:'Stock',              desc:'Existencias por variante',     icon:Package,   nombre:'reporte_stock' },
  { tipo:'ventas', label:'Balance de Ventas',  desc:'Cobros del período',           icon:BarChart3, nombre:'balance_ventas' },
  { tipo:'caja',   label:'Extracto de Caja',   desc:'Sesiones y cierres',           icon:Wallet,    nombre:'extracto_caja' },
]

export default function PanelReportes() {
  // Rango por defecto: mes actual
  const hoy = new Date()
  const primerDia = new Date(hoy.getFullYear(), hoy.getMonth(), 1).toISOString().slice(0,10)
  const hoyStr = hoy.toISOString().slice(0,10)

  const [desde, setDesde] = useState(primerDia)
  const [hasta, setHasta] = useState(hoyStr)
  const [cargando, setCargando] = useState(null) // `${tipo}-${formato}`

  const descargar = async (tipo, formato, nombre) => {
    const key = `${tipo}-${formato}`
    setCargando(key)
    try {
      const params = tipo === 'stock' ? {} : { desde, hasta }
      const res = await cajaApi.descargarReporte(tipo, formato, params)
      const ext = formato === 'pdf' ? 'pdf' : 'xlsx'
      const fecha = hoyStr.replace(/-/g,'')
      descargarBlob(res.data, `${nombre}_${fecha}.${ext}`)
      toast.success(`Reporte de ${tipo} descargado`)
    } catch (err) {
      toast.error('No se pudo generar el reporte')
    } finally {
      setCargando(null)
    }
  }

  return (
    <div style={{ background:C.bg, border:`1px solid ${C.border}`, borderRadius:'14px',
      padding:'18px 20px' }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
        flexWrap:'wrap', gap:'12px', marginBottom:'16px' }}>
        <div>
          <h3 style={{ fontSize:'15px', fontWeight:'600', color:C.text }}>Reportes</h3>
          <p style={{ fontSize:'12px', color:C.textMuted }}>
            Descargá en PDF o Excel
          </p>
        </div>
        {/* Rango de fechas (aplica a Ventas y Caja) */}
        <div style={{ display:'flex', alignItems:'center', gap:'8px' }}>
          <div>
            <label style={{ display:'block', fontSize:'10.5px', color:C.textMuted, marginBottom:'2px' }}>Desde</label>
            <input type="date" value={desde} onChange={e=>setDesde(e.target.value)}
              style={{ height:'34px', padding:'0 8px', border:`1px solid ${C.border}`,
                borderRadius:'7px', fontSize:'12.5px', color:C.text, background:C.bg, outline:'none' }}/>
          </div>
          <div>
            <label style={{ display:'block', fontSize:'10.5px', color:C.textMuted, marginBottom:'2px' }}>Hasta</label>
            <input type="date" value={hasta} onChange={e=>setHasta(e.target.value)}
              style={{ height:'34px', padding:'0 8px', border:`1px solid ${C.border}`,
                borderRadius:'7px', fontSize:'12.5px', color:C.text, background:C.bg, outline:'none' }}/>
          </div>
        </div>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(240px,1fr))', gap:'10px' }}>
        {REPORTES.map(r => {
          const Icon = r.icon
          return (
            <div key={r.tipo} style={{ border:`1px solid ${C.border}`, borderRadius:'11px',
              padding:'14px', background:C.bgSec }}>
              <div style={{ display:'flex', alignItems:'center', gap:'9px', marginBottom:'10px' }}>
                <div style={{ width:'34px', height:'34px', borderRadius:'9px',
                  background:C.goldMuted, display:'flex', alignItems:'center', justifyContent:'center' }}>
                  <Icon size={17} style={{ color:C.goldDark }} />
                </div>
                <div>
                  <p style={{ fontSize:'13.5px', fontWeight:'500', color:C.text }}>{r.label}</p>
                  <p style={{ fontSize:'11px', color:C.textMuted }}>{r.desc}</p>
                </div>
              </div>
              <div style={{ display:'flex', gap:'7px' }}>
                <button
                  onClick={() => descargar(r.tipo, 'pdf', r.nombre)}
                  disabled={cargando === `${r.tipo}-pdf`}
                  style={{ flex:1, height:'36px', borderRadius:'8px', cursor:'pointer',
                    background:C.sidebar, border:`1px solid ${C.gold}`, color:C.gold,
                    fontSize:'12.5px', fontWeight:'500', display:'flex', alignItems:'center',
                    justifyContent:'center', gap:'5px' }}>
                  {cargando === `${r.tipo}-pdf`
                    ? <Loader2 size={13} style={{ animation:'spin 1s linear infinite' }} />
                    : <FileText size={13} />} PDF
                </button>
                <button
                  onClick={() => descargar(r.tipo, 'xlsx', r.nombre)}
                  disabled={cargando === `${r.tipo}-xlsx`}
                  style={{ flex:1, height:'36px', borderRadius:'8px', cursor:'pointer',
                    background:'transparent', border:`1px solid ${C.border}`, color:C.success,
                    fontSize:'12.5px', fontWeight:'500', display:'flex', alignItems:'center',
                    justifyContent:'center', gap:'5px' }}>
                  {cargando === `${r.tipo}-xlsx`
                    ? <Loader2 size={13} style={{ animation:'spin 1s linear infinite' }} />
                    : <FileSpreadsheet size={13} />} Excel
                </button>
              </div>
            </div>
          )
        })}
      </div>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  )
}
