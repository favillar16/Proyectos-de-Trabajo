import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Plus, Edit2, Trash2, Tag, Award, Layers, Wrench, Check } from 'lucide-react'
import { productosApi } from '../../services/api'
import toast from 'react-hot-toast'

const C = {
  sidebar:'#453941', gold:'#B99C74', goldDark:'#8a7355', goldMuted:'rgba(185,156,116,0.10)',
  border:'#e8e4df', bg:'#ffffff', bgSec:'#fafaf9', bgTer:'#f5f4f2',
  text:'#1a1714', textSec:'#5a544e', textMuted:'#9e9892',
  danger:'#c0392b', success:'#3d7a5a',
}

const TIPOS_CATEGORIA = [
  { v:'piso', l:'Pisos' }, { v:'porcelanato', l:'Porcelanatos' },
  { v:'ceramica', l:'Cerámicas' }, { v:'sanitario', l:'Sanitarios' },
  { v:'accesorio_bano', l:'Accesorios de Baño' }, { v:'cocina', l:'Artículos de Cocina' },
  { v:'otro', l:'Otro' },
]

// Configuración de cada catálogo: campos, API y query
const CATALOGOS = {
  categorias: {
    label: 'Categorías', icon: Layers,
    listar: () => productosApi.categorias().then(r => r.data),
    crear: productosApi.crearCategoria, editar: productosApi.editarCategoria, eliminar: productosApi.eliminarCategoria,
    queryKey: ['categorias'],
    campos: [
      { k:'nombre', label:'Nombre', tipo:'text', req:true, ph:'Ej: Porcelanatos Premium' },
      { k:'tipo', label:'Tipo', tipo:'select', req:true, opciones:TIPOS_CATEGORIA },
      { k:'descripcion', label:'Descripción', tipo:'text', ph:'Opcional' },
      { k:'orden', label:'Orden', tipo:'number', ph:'0' },
    ],
    vacio: { nombre:'', tipo:'otro', descripcion:'', orden:0, activa:true },
    resumen: (it) => `${TIPOS_CATEGORIA.find(t=>t.v===it.tipo)?.l || it.tipo}`,
  },
  marcas: {
    label: 'Marcas', icon: Award,
    listar: () => productosApi.marcas().then(r => r.data),
    crear: productosApi.crearMarca, editar: productosApi.editarMarca, eliminar: productosApi.eliminarMarca,
    queryKey: ['marcas'],
    campos: [
      { k:'nombre', label:'Nombre', tipo:'text', req:true, ph:'Ej: Cerámica San Lorenzo' },
      { k:'pais_origen', label:'País de origen', tipo:'text', ph:'Ej: Brasil' },
    ],
    vacio: { nombre:'', pais_origen:'', activa:true },
    resumen: (it) => it.pais_origen || '—',
  },
  acabados: {
    label: 'Acabados', icon: Tag,
    listar: () => productosApi.acabados().then(r => r.data),
    crear: productosApi.crearAcabado, editar: productosApi.editarAcabado, eliminar: productosApi.eliminarAcabado,
    queryKey: ['acabados'],
    campos: [
      { k:'nombre', label:'Nombre', tipo:'text', req:true, ph:'Ej: Mate, Brillante, Rústico' },
      { k:'descripcion', label:'Descripción', tipo:'text', ph:'Opcional' },
    ],
    vacio: { nombre:'', descripcion:'' },
    resumen: (it) => it.descripcion || '—',
  },
  tipos: {
    label: 'Tipos de instalación', icon: Wrench,
    listar: () => productosApi.tiposInstalacion().then(r => r.data),
    crear: productosApi.crearTipoInstalacion, editar: productosApi.editarTipoInstalacion, eliminar: productosApi.eliminarTipoInstalacion,
    queryKey: ['tipos-instalacion'],
    campos: [
      { k:'nombre', label:'Nombre', tipo:'text', req:true, ph:'Ej: Piso, Pared, Piscina' },
    ],
    vacio: { nombre:'' },
    resumen: () => '',
  },
}

function normalizarLista(data) {
  // Los endpoints devuelven {results:[...]} o [...] directo
  if (Array.isArray(data)) return data
  if (data?.results) return data.results
  return []
}

export default function GestionCatalogos({ onCerrar }) {
  const [tab, setTab] = useState('categorias')
  const cfg = CATALOGOS[tab]
  const qc = useQueryClient()

  const [editando, setEditando] = useState(null)   // null=ninguno, {}=nuevo, {...}=editar
  const [form, setForm] = useState({})

  const { data, isLoading } = useQuery({
    queryKey: cfg.queryKey,
    queryFn: cfg.listar,
  })
  const items = normalizarLista(data)

  const guardarMut = useMutation({
    mutationFn: () => editando?.id ? cfg.editar(editando.id, form) : cfg.crear(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cfg.queryKey })
      toast.success(editando?.id ? 'Actualizado' : 'Agregado')
      setEditando(null)
    },
    onError: (err) => {
      const d = err.response?.data
      const msg = d && typeof d === 'object'
        ? Object.entries(d).map(([k,v]) => `${k}: ${Array.isArray(v)?v.join(' '):v}`).join(' · ')
        : 'No se pudo guardar'
      toast.error(msg)
    },
  })

  const eliminarMut = useMutation({
    mutationFn: (id) => cfg.eliminar(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cfg.queryKey })
      toast.success('Eliminado')
    },
    onError: (err) => {
      // Si está en uso por productos, el backend devuelve error
      toast.error(err.response?.data?.detail || 'No se puede eliminar (puede estar en uso)')
    },
  })

  const abrirNuevo = () => { setForm({ ...cfg.vacio }); setEditando({}) }
  const abrirEditar = (it) => { setForm({ ...it }); setEditando(it) }

  const puedeGuardar = cfg.campos.filter(c => c.req).every(c => String(form[c.k] ?? '').trim() !== '')

  return (
    <div onClick={onCerrar} style={{ position:'fixed', inset:0, zIndex:200,
      background:'rgba(26,23,20,0.55)', backdropFilter:'blur(2px)',
      display:'flex', alignItems:'center', justifyContent:'center', padding:'20px' }}>
      <div onClick={e => e.stopPropagation()} style={{
        background:C.bg, borderRadius:'16px', width:'100%', maxWidth:'620px',
        maxHeight:'85vh', display:'flex', flexDirection:'column', overflow:'hidden',
        boxShadow:'0 20px 60px rgba(0,0,0,0.25)' }}>

        {/* Cabecera */}
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
          padding:'16px 20px', borderBottom:`1px solid ${C.border}` }}>
          <div>
            <h2 style={{ fontSize:'17px', fontWeight:'600', color:C.text }}>Gestión de catálogos</h2>
            <p style={{ fontSize:'12px', color:C.textMuted }}>Marcas, categorías, acabados y tipos</p>
          </div>
          <button onClick={onCerrar} style={{ background:'transparent', border:'none',
            cursor:'pointer', color:C.textMuted, padding:'4px' }}><X size={20}/></button>
        </div>

        {/* Pestañas */}
        <div style={{ display:'flex', gap:'4px', padding:'12px 20px 0', borderBottom:`1px solid ${C.border}`,
          overflowX:'auto' }}>
          {Object.entries(CATALOGOS).map(([key, c]) => {
            const Icono = c.icon
            const activa = tab === key
            return (
              <button key={key} onClick={() => { setTab(key); setEditando(null) }}
                style={{ display:'flex', alignItems:'center', gap:'6px', padding:'8px 12px',
                  background:'transparent', border:'none', cursor:'pointer',
                  borderBottom:`2px solid ${activa ? C.gold : 'transparent'}`,
                  color: activa ? C.goldDark : C.textSec,
                  fontSize:'13px', fontWeight: activa?'600':'400', whiteSpace:'nowrap' }}>
                <Icono size={14}/> {c.label}
              </button>
            )
          })}
        </div>

        {/* Contenido */}
        <div style={{ flex:1, overflowY:'auto', padding:'16px 20px' }}>
          {/* Formulario de alta/edición */}
          {editando !== null ? (
            <div style={{ background:C.bgSec, borderRadius:'12px', padding:'16px',
              border:`1px solid ${C.border}`, marginBottom:'16px' }}>
              <p style={{ fontSize:'13px', fontWeight:'600', color:C.text, marginBottom:'12px' }}>
                {editando?.id ? 'Editar' : 'Nuevo'} — {cfg.label}
              </p>
              {cfg.campos.map(campo => (
                <div key={campo.k} style={{ marginBottom:'10px' }}>
                  <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
                    color:C.textSec, marginBottom:'4px' }}>
                    {campo.label}{campo.req && <span style={{ color:C.danger }}> *</span>}
                  </label>
                  {campo.tipo === 'select' ? (
                    <select value={form[campo.k] ?? ''}
                      onChange={e => setForm(f => ({ ...f, [campo.k]: e.target.value }))}
                      style={{ width:'100%', height:'40px', padding:'0 10px',
                        border:`1px solid ${C.border}`, borderRadius:'8px',
                        fontSize:'13.5px', color:C.text, background:C.bg, outline:'none' }}>
                      {campo.opciones.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
                    </select>
                  ) : (
                    <input type={campo.tipo === 'number' ? 'number' : 'text'}
                      value={form[campo.k] ?? ''}
                      onChange={e => setForm(f => ({ ...f, [campo.k]:
                        campo.tipo === 'number' ? (e.target.value === '' ? '' : Number(e.target.value)) : e.target.value }))}
                      placeholder={campo.ph || ''}
                      style={{ width:'100%', height:'40px', padding:'0 12px',
                        border:`1px solid ${C.border}`, borderRadius:'8px',
                        fontSize:'13.5px', color:C.text, background:C.bg, outline:'none' }}
                      onFocus={e => e.target.style.borderColor = C.gold}
                      onBlur={e => e.target.style.borderColor = C.border} />
                  )}
                </div>
              ))}
              <div style={{ display:'flex', gap:'8px', marginTop:'14px' }}>
                <button onClick={() => setEditando(null)}
                  style={{ flex:1, height:'40px', borderRadius:'8px', cursor:'pointer',
                    background:'transparent', border:`1px solid ${C.border}`,
                    color:C.textSec, fontSize:'13px' }}>Cancelar</button>
                <button disabled={!puedeGuardar || guardarMut.isPending}
                  onClick={() => guardarMut.mutate()}
                  style={{ flex:1, height:'40px', borderRadius:'8px',
                    cursor: puedeGuardar ? 'pointer' : 'not-allowed',
                    background: puedeGuardar ? C.sidebar : C.bgTer,
                    border:`1px solid ${puedeGuardar ? C.gold : C.border}`,
                    color: puedeGuardar ? C.gold : C.textMuted, fontSize:'13px', fontWeight:'500' }}>
                  {guardarMut.isPending ? 'Guardando...' : 'Guardar'}
                </button>
              </div>
            </div>
          ) : (
            <button onClick={abrirNuevo}
              style={{ width:'100%', height:'42px', borderRadius:'10px', cursor:'pointer',
                background:C.goldMuted, border:`1px dashed ${C.gold}`, color:C.goldDark,
                fontSize:'13px', fontWeight:'500', display:'flex', alignItems:'center',
                justifyContent:'center', gap:'7px', marginBottom:'16px' }}>
              <Plus size={15}/> Agregar {cfg.label.toLowerCase()}
            </button>
          )}

          {/* Lista */}
          {isLoading ? (
            <p style={{ fontSize:'13px', color:C.textMuted, textAlign:'center', padding:'20px' }}>Cargando...</p>
          ) : items.length === 0 ? (
            <p style={{ fontSize:'13px', color:C.textMuted, textAlign:'center', padding:'20px' }}>
              No hay {cfg.label.toLowerCase()} cargados todavía.
            </p>
          ) : (
            <div style={{ display:'flex', flexDirection:'column', gap:'6px' }}>
              {items.map(it => (
                <div key={it.id} style={{ display:'flex', alignItems:'center', gap:'10px',
                  padding:'10px 12px', borderRadius:'9px', background:C.bg,
                  border:`1px solid ${C.border}` }}>
                  <div style={{ flex:1, minWidth:0 }}>
                    <p style={{ fontSize:'13.5px', fontWeight:'500', color:C.text }}>{it.nombre}</p>
                    {cfg.resumen(it) && (
                      <p style={{ fontSize:'11.5px', color:C.textMuted }}>{cfg.resumen(it)}</p>
                    )}
                  </div>
                  <button onClick={() => abrirEditar(it)} title="Editar"
                    style={{ width:'30px', height:'30px', borderRadius:'7px', cursor:'pointer',
                      background:C.bgSec, border:`1px solid ${C.border}`, color:C.textSec,
                      display:'flex', alignItems:'center', justifyContent:'center' }}><Edit2 size={13}/></button>
                  <button onClick={() => { if(confirm(`¿Eliminar "${it.nombre}"?`)) eliminarMut.mutate(it.id) }}
                    title="Eliminar"
                    style={{ width:'30px', height:'30px', borderRadius:'7px', cursor:'pointer',
                      background:C.bgSec, border:`1px solid ${C.border}`, color:C.danger,
                      display:'flex', alignItems:'center', justifyContent:'center' }}><Trash2 size={13}/></button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
