/**
 * UsuariosPage
 * Gestión de usuarios del sistema — solo visible para rol admin.
 * Permite crear, editar rol, activar/desactivar y cambiar contraseña.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus, Edit2, Lock, UserCheck, UserX,
  X, Loader2, ChevronDown, Shield,
  Eye, EyeOff,
} from 'lucide-react'
import Layout from '../components/layout/Layout'
import { usuariosApi } from '../services/api'
import { useAuthStore } from '../store/authStore'
import toast from 'react-hot-toast'

const C = {
  sidebar:'#453941', sidebarHov:'#362F31',
  gold:'#B99C74', goldDark:'#8a7355', goldMuted:'rgba(185,156,116,0.10)',
  border:'#e8e4df', bg:'#ffffff', bgSec:'#fafaf9', bgTer:'#f5f4f2',
  text:'#1a1714', textSec:'#6b6560', textMuted:'#9e9892',
  success:'#3d7a5a', successBg:'#edf7f1', successBorder:'#b8deca',
  danger:'#9a3030',  dangerBg:'#fef0f0',  dangerBorder:'#f0b8b8',
  info:'#2a5c8a',    infoBg:'#eef4fb',
}

const ROL_CFG = {
  admin:            { label:'Administrador',      color:C.danger,  bg:C.dangerBg,  border:C.dangerBorder  },
  encargada_ventas: { label:'Encargada de Ventas',color:C.goldDark, bg:C.goldMuted, border:C.gold          },
  vendedor:         { label:'Vendedor',           color:C.success, bg:C.successBg, border:C.successBorder },
  cajero:           { label:'Cajero',             color:C.info,    bg:C.infoBg,    border:'#aecae8'        },
  deposito:         { label:'Depósito',           color:'#8a6a1a', bg:'#fef9ee',   border:'#f0d98a'        },
}

const ROL_PERMISOS = {
  admin:            ['Todo el sistema', 'Gestión de usuarios', 'KPIs y reportes', 'Todos los módulos'],
  encargada_ventas: ['Todo lo del vendedor', 'Modificar precios en pedidos', 'Precio negociado con clientes'],
  vendedor:         ['Showroom y catálogo', 'Crear notas de pedido', 'Ver stock'],
  cajero:           ['Módulo de caja', 'Cobrar pedidos', 'Imprimir tickets', 'Ver pedidos listos'],
  deposito:         ['Ver pedidos pendientes', 'Preparar pedidos', 'Ajustar stock', 'Inventario'],
}

function RolBadge({ rol }) {
  const cfg = ROL_CFG[rol] || ROL_CFG.vendedor
  return (
    <span style={{ display:'inline-flex', alignItems:'center', gap:'4px',
      padding:'3px 9px', borderRadius:'20px',
      background:cfg.bg, color:cfg.color, border:`1px solid ${cfg.border}`,
      fontSize:'11px', fontWeight:'500' }}>
      {cfg.label}
    </span>
  )
}

// ─── Modal de creación/edición ────────────────────────────────────────────────
function ModalUsuario({ usuario, onCerrar }) {
  const queryClient = useQueryClient()
  const esEdicion = Boolean(usuario)

  const [form, setForm] = useState({
    username:        usuario?.username        || '',
    nombre_completo: usuario?.nombre_completo || '',
    rol:             usuario?.rol             || 'vendedor',
    password:        '',
    password2:       '',
    activo:          usuario?.activo ?? true,
  })
  const [mostrarPass, setMostrarPass] = useState(false)
  const [errores, setErrores] = useState({})

  const mutation = useMutation({
    mutationFn: () => esEdicion
      ? usuariosApi.actualizar(usuario.id, {
          nombre_completo: form.nombre_completo,
          rol:    form.rol,
          activo: form.activo,
        }).then(r => r.data)
      : usuariosApi.crear({
          username:        form.username,
          nombre_completo: form.nombre_completo,
          rol:             form.rol,
          password:        form.password,
        }).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['usuarios'] })
      toast.success(esEdicion ? 'Usuario actualizado' : 'Usuario creado correctamente')
      onCerrar()
    },
    onError: (err) => {
      const data = err.response?.data || {}
      if (typeof data === 'object') setErrores(data)
      else toast.error('Error al guardar el usuario')
    },
  })

  const validar = () => {
    const e = {}
    if (!form.nombre_completo.trim()) e.nombre_completo = 'Requerido'
    if (!esEdicion) {
      if (!form.username.trim()) e.username = 'Requerido'
      if (!form.password)        e.password = 'Requerido'
      if (form.password !== form.password2) e.password2 = 'Las contraseñas no coinciden'
    }
    setErrores(e)
    return Object.keys(e).length === 0
  }

  const guardar = () => { if (validar()) mutation.mutate() }

  const campo = (key, label, type='text', placeholder='', requerido=false) => (
    <div style={{ marginBottom:'14px' }}>
      <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
        color: errores[key] ? C.danger : C.textSec, marginBottom:'5px' }}>
        {label}{requerido && <span style={{ color:C.gold }}> *</span>}
      </label>
      <div style={{ position:'relative' }}>
        <input
          type={type === 'password' ? (mostrarPass ? 'text' : 'password') : type}
          value={form[key]}
          onChange={e => { setForm(f=>({...f,[key]:e.target.value})); setErrores(er=>({...er,[key]:undefined})) }}
          placeholder={placeholder}
          style={{ width:'100%', height:'40px', padding:'0 12px',
            border:`1px solid ${errores[key] ? C.danger : C.border}`,
            borderRadius:'9px', fontSize:'14px', color:C.text,
            background:C.bg, outline:'none' }}
          onFocus={e=>e.target.style.borderColor=errores[key]?C.danger:C.gold}
          onBlur={e=>e.target.style.borderColor=errores[key]?C.danger:C.border}
        />
        {type==='password' && (
          <button onClick={()=>setMostrarPass(v=>!v)}
            style={{ position:'absolute', right:'10px', top:'50%',
              transform:'translateY(-50%)', background:'transparent',
              border:'none', cursor:'pointer', color:C.textMuted,
              display:'flex', alignItems:'center', padding:'3px' }}>
            {mostrarPass ? <EyeOff size={14}/> : <Eye size={14}/>}
          </button>
        )}
      </div>
      {errores[key] && <p style={{ fontSize:'11px', color:C.danger, marginTop:'3px' }}>{errores[key]}</p>}
    </div>
  )

  return (
    <>
      <div onClick={onCerrar} style={{ position:'fixed', inset:0, zIndex:200,
        background:'rgba(26,23,20,0.45)', backdropFilter:'blur(2px)' }} />
      <div style={{ position:'fixed', top:'50%', left:'50%', zIndex:201,
        transform:'translate(-50%,-50%)',
        width:'min(440px,94vw)', background:C.bg,
        border:`1px solid ${C.border}`, borderRadius:'16px',
        boxShadow:'0 20px 50px rgba(0,0,0,0.15)', padding:'24px' }}>

        <div style={{ display:'flex', justifyContent:'space-between',
          alignItems:'center', marginBottom:'20px' }}>
          <h3 style={{ fontSize:'16px', fontWeight:'500', color:C.text }}>
            {esEdicion ? 'Editar usuario' : 'Nuevo usuario'}
          </h3>
          <button onClick={onCerrar} style={{ background:'transparent', border:'none',
            cursor:'pointer', color:C.textMuted, padding:'4px',
            display:'flex', alignItems:'center' }}>
            <X size={18}/>
          </button>
        </div>

        {!esEdicion && campo('username', 'Nombre de usuario', 'text', 'Ej: maria.gonzalez', true)}
        {campo('nombre_completo', 'Nombre completo', 'text', 'Ej: María González', true)}

        {/* Selector de rol */}
        <div style={{ marginBottom:'14px' }}>
          <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
            color:C.textSec, marginBottom:'5px' }}>Rol *</label>
          <select value={form.rol} onChange={e=>setForm(f=>({...f,rol:e.target.value}))}
            style={{ width:'100%', height:'40px', padding:'0 12px',
              border:`1px solid ${C.border}`, borderRadius:'9px',
              fontSize:'14px', color:C.text, background:C.bg, outline:'none' }}>
            {Object.entries(ROL_CFG).map(([k,v])=>(
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
          {/* Permisos del rol seleccionado */}
          <div style={{ marginTop:'8px', padding:'10px 12px',
            background:C.bgSec, border:`1px solid ${C.border}`,
            borderRadius:'8px' }}>
            <p style={{ fontSize:'11px', fontWeight:'500', color:C.textMuted,
              marginBottom:'5px' }}>
              Accesos de este rol:
            </p>
            {(ROL_PERMISOS[form.rol] || []).map((p,i)=>(
              <p key={i} style={{ fontSize:'12px', color:C.textSec,
                display:'flex', alignItems:'center', gap:'5px', marginBottom:'2px' }}>
                <span style={{ color:C.success, fontSize:'10px' }}>✓</span> {p}
              </p>
            ))}
          </div>
        </div>

        {!esEdicion && (
          <>
            {campo('password',  'Contraseña', 'password', 'Mínimo 6 caracteres', true)}
            {campo('password2', 'Confirmar contraseña', 'password', 'Repetir contraseña', true)}
          </>
        )}

        {esEdicion && (
          <div style={{ marginBottom:'14px' }}>
            <label style={{ display:'flex', alignItems:'center', gap:'8px',
              cursor:'pointer', fontSize:'13px', color:C.textSec }}>
              <div onClick={()=>setForm(f=>({...f,activo:!f.activo}))}
                style={{ width:'36px', height:'20px', borderRadius:'10px',
                  background: form.activo ? C.sidebar : C.border,
                  border: `1px solid ${form.activo ? C.gold : C.border}`,
                  position:'relative', transition:'all 150ms', flexShrink:0, cursor:'pointer' }}>
                <div style={{ width:'14px', height:'14px', borderRadius:'50%',
                  background: form.activo ? C.gold : C.textMuted,
                  position:'absolute', top:'2px',
                  left: form.activo ? '19px' : '2px',
                  transition:'left 150ms' }} />
              </div>
              Usuario activo
            </label>
          </div>
        )}

        <div style={{ display:'flex', gap:'10px', marginTop:'4px' }}>
          <button onClick={onCerrar}
            style={{ flex:1, height:'42px', borderRadius:'9px',
              background:'transparent', border:`1px solid ${C.border}`,
              color:C.textSec, fontSize:'14px', cursor:'pointer' }}>
            Cancelar
          </button>
          <button onClick={guardar} disabled={mutation.isPending}
            style={{ flex:2, height:'42px', borderRadius:'9px',
              background: mutation.isPending ? C.bgTer : C.sidebar,
              border:`1.5px solid ${mutation.isPending ? C.border : C.gold}`,
              color: mutation.isPending ? C.textMuted : C.gold,
              fontSize:'14px', fontWeight:'500',
              cursor: mutation.isPending?'not-allowed':'pointer',
              display:'flex', alignItems:'center', justifyContent:'center', gap:'7px' }}>
            {mutation.isPending
              ? <><Loader2 size={15} style={{ animation:'spin 1s linear infinite' }}/> Guardando...</>
              : esEdicion ? 'Guardar cambios' : 'Crear usuario'}
          </button>
        </div>
      </div>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </>
  )
}

// ─── Modal de cambio de contraseña ────────────────────────────────────────────
function ModalPassword({ usuario, onCerrar }) {
  const [pass1, setPass1] = useState('')
  const [pass2, setPass2] = useState('')
  const [error, setError] = useState('')
  const [ver,   setVer]   = useState(false)

  const mutation = useMutation({
    mutationFn: () => usuariosApi.cambiarPassword(usuario.id, {
      password_nuevo:     pass1,
      password_confirmar: pass2,
    }).then(r => r.data),
    onSuccess: () => { toast.success('Contraseña actualizada'); onCerrar() },
    onError: (err) => {
      const msg = err.response?.data?.error
        || Object.values(err.response?.data || {}).flat().join(' ')
        || 'Error al cambiar contraseña'
      setError(msg)
    },
  })

  const guardar = () => {
    if (!pass1) { setError('Ingresá la nueva contraseña'); return }
    if (pass1 !== pass2) { setError('Las contraseñas no coinciden'); return }
    if (pass1.length < 6) { setError('Mínimo 6 caracteres'); return }
    setError('')
    mutation.mutate()
  }

  return (
    <>
      <div onClick={onCerrar} style={{ position:'fixed', inset:0, zIndex:200,
        background:'rgba(26,23,20,0.45)', backdropFilter:'blur(2px)' }} />
      <div style={{ position:'fixed', top:'50%', left:'50%', zIndex:201,
        transform:'translate(-50%,-50%)',
        width:'min(380px,94vw)', background:C.bg,
        border:`1px solid ${C.border}`, borderRadius:'16px',
        boxShadow:'0 20px 50px rgba(0,0,0,0.15)', padding:'24px' }}>
        <div style={{ display:'flex', justifyContent:'space-between', marginBottom:'18px' }}>
          <div>
            <h3 style={{ fontSize:'16px', fontWeight:'500', color:C.text }}>Cambiar contraseña</h3>
            <p style={{ fontSize:'12px', color:C.textMuted, marginTop:'2px' }}>{usuario.nombre_completo}</p>
          </div>
          <button onClick={onCerrar} style={{ background:'transparent', border:'none',
            cursor:'pointer', color:C.textMuted, padding:'4px',
            display:'flex', alignItems:'center' }}><X size={18}/></button>
        </div>

        {[['pass1','Nueva contraseña',setPass1,pass1],['pass2','Confirmar',setPass2,pass2]].map(([k,l,s,v])=>(
          <div key={k} style={{ marginBottom:'12px' }}>
            <label style={{ display:'block', fontSize:'12px', fontWeight:'500',
              color:C.textSec, marginBottom:'5px' }}>{l}</label>
            <div style={{ position:'relative' }}>
              <input
                type={ver?'text':'password'}
                value={v}
                onChange={e=>{s(e.target.value);setError('')}}
                style={{ width:'100%', height:'40px', padding:'0 36px 0 12px',
                  border:`1px solid ${error?C.danger:C.border}`, borderRadius:'9px',
                  fontSize:'14px', color:C.text, background:C.bg, outline:'none' }}
                onFocus={e=>e.target.style.borderColor=C.gold}
                onBlur={e=>e.target.style.borderColor=error?C.danger:C.border}
              />
              {k==='pass1' && (
                <button onClick={()=>setVer(v=>!v)}
                  style={{ position:'absolute', right:'10px', top:'50%',
                    transform:'translateY(-50%)', background:'transparent',
                    border:'none', cursor:'pointer', color:C.textMuted,
                    display:'flex', alignItems:'center', padding:'3px' }}>
                  {ver?<EyeOff size={14}/>:<Eye size={14}/>}
                </button>
              )}
            </div>
          </div>
        ))}

        {error && <p style={{ fontSize:'12px', color:C.danger, marginBottom:'12px' }}>{error}</p>}

        <div style={{ display:'flex', gap:'10px' }}>
          <button onClick={onCerrar}
            style={{ flex:1, height:'42px', borderRadius:'9px',
              background:'transparent', border:`1px solid ${C.border}`,
              color:C.textSec, fontSize:'14px', cursor:'pointer' }}>
            Cancelar
          </button>
          <button onClick={guardar} disabled={mutation.isPending}
            style={{ flex:2, height:'42px', borderRadius:'9px',
              background: mutation.isPending?C.bgTer:C.sidebar,
              border:`1.5px solid ${mutation.isPending?C.border:C.gold}`,
              color: mutation.isPending?C.textMuted:C.gold,
              fontSize:'14px', fontWeight:'500', cursor:'pointer',
              display:'flex', alignItems:'center', justifyContent:'center', gap:'7px' }}>
            {mutation.isPending?<><Loader2 size={15} style={{ animation:'spin 1s linear infinite' }}/> Guardando...</>:'Cambiar contraseña'}
          </button>
        </div>
      </div>
    </>
  )
}

// ─── Fila de usuario ──────────────────────────────────────────────────────────
function FilaUsuario({ usuario, esYo, onEditar, onPassword, onToggleActivo }) {
  const [hov, setHov] = useState(false)

  return (
    <tr onMouseEnter={()=>setHov(true)} onMouseLeave={()=>setHov(false)}>
      <td style={{ padding:'12px 16px', borderBottom:`1px solid ${C.border}` }}>
        <div style={{ display:'flex', alignItems:'center', gap:'10px' }}>
          <div style={{ width:'36px', height:'36px', borderRadius:'50%',
            background: usuario.activo ? C.sidebar : C.bgTer,
            border:`1px solid ${usuario.activo ? C.gold : C.border}`,
            display:'flex', alignItems:'center', justifyContent:'center',
            fontSize:'13px', fontWeight:'500',
            color: usuario.activo ? C.gold : C.textMuted, flexShrink:0 }}>
            {usuario.nombre_completo.slice(0,2).toUpperCase()}
          </div>
          <div>
            <p style={{ fontSize:'13.5px', fontWeight:'500', color:C.text }}>
              {usuario.nombre_completo}
              {esYo && <span style={{ fontSize:'10.5px', color:C.textMuted,
                marginLeft:'6px' }}>(vos)</span>}
            </p>
            <p style={{ fontSize:'11.5px', color:C.textMuted, fontFamily:'monospace' }}>
              {usuario.username}
            </p>
          </div>
        </div>
      </td>
      <td style={{ padding:'12px 16px', borderBottom:`1px solid ${C.border}` }}>
        <RolBadge rol={usuario.rol} />
      </td>
      <td style={{ padding:'12px 16px', borderBottom:`1px solid ${C.border}` }}>
        <span style={{ fontSize:'12px', fontWeight:'500',
          color: usuario.activo ? C.success : C.danger }}>
          {usuario.activo ? 'Activo' : 'Inactivo'}
        </span>
      </td>
      <td style={{ padding:'12px 16px', borderBottom:`1px solid ${C.border}` }}>
        <p style={{ fontSize:'11.5px', color:C.textMuted }}>
          {usuario.ultimo_acceso
            ? new Date(usuario.ultimo_acceso).toLocaleDateString('es-PY')
            : 'Nunca'}
        </p>
      </td>
      <td style={{ padding:'12px 16px', borderBottom:`1px solid ${C.border}` }}>
        <div style={{ display:'flex', gap:'5px', opacity:hov?1:0, transition:'opacity 120ms' }}>
          <button onClick={()=>onEditar(usuario)} title="Editar"
            style={{ width:'30px', height:'30px', borderRadius:'7px', cursor:'pointer',
              background:C.bgSec, border:`1px solid ${C.border}`, color:C.textSec,
              display:'flex', alignItems:'center', justifyContent:'center' }}
            onMouseEnter={e=>{e.currentTarget.style.borderColor=C.gold;e.currentTarget.style.color=C.goldDark}}
            onMouseLeave={e=>{e.currentTarget.style.borderColor=C.border;e.currentTarget.style.color=C.textSec}}>
            <Edit2 size={13}/>
          </button>
          <button onClick={()=>onPassword(usuario)} title="Cambiar contraseña"
            style={{ width:'30px', height:'30px', borderRadius:'7px', cursor:'pointer',
              background:C.bgSec, border:`1px solid ${C.border}`, color:C.textSec,
              display:'flex', alignItems:'center', justifyContent:'center' }}
            onMouseEnter={e=>{e.currentTarget.style.borderColor=C.gold;e.currentTarget.style.color=C.goldDark}}
            onMouseLeave={e=>{e.currentTarget.style.borderColor=C.border;e.currentTarget.style.color=C.textSec}}>
            <Lock size={13}/>
          </button>
          {!esYo && (
            <button onClick={()=>onToggleActivo(usuario)}
              title={usuario.activo ? 'Desactivar' : 'Activar'}
              style={{ width:'30px', height:'30px', borderRadius:'7px', cursor:'pointer',
                background:C.bgSec, border:`1px solid ${C.border}`,
                color: usuario.activo ? C.danger : C.success,
                display:'flex', alignItems:'center', justifyContent:'center' }}
              onMouseEnter={e=>e.currentTarget.style.borderColor=usuario.activo?C.danger:C.success}
              onMouseLeave={e=>e.currentTarget.style.borderColor=C.border}>
              {usuario.activo ? <UserX size={13}/> : <UserCheck size={13}/>}
            </button>
          )}
        </div>
      </td>
    </tr>
  )
}

// ─── Página principal ─────────────────────────────────────────────────────────
export default function UsuariosPage() {
  const { usuario: yo } = useAuthStore()
  const queryClient = useQueryClient()
  const [modalUsuario,  setModalUsuario]  = useState(null) // null | 'nuevo' | usuario
  const [modalPassword, setModalPassword] = useState(null)
  const [filtroRol,     setFiltroRol]     = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['usuarios', filtroRol],
    queryFn: () => usuariosApi.listar({ rol: filtroRol || undefined }).then(r => r.data),
    staleTime: 30_000,
  })

  const usuarios = data?.results || []

  const toggleActivo = useMutation({
    mutationFn: (u) => usuariosApi.actualizar(u.id, { activo: !u.activo }).then(r => r.data),
    onSuccess: (u) => {
      queryClient.invalidateQueries({ queryKey: ['usuarios'] })
      toast.success(`Usuario ${u.activo ? 'activado' : 'desactivado'}`)
    },
    onError: () => toast.error('Error al cambiar el estado del usuario'),
  })

  return (
    <Layout pageTitle="Usuarios" breadcrumbs={['Usuarios']}>

      {/* Header */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center',
        marginBottom:'20px', flexWrap:'wrap', gap:'12px' }}>
        <div style={{ display:'flex', alignItems:'center', gap:'8px' }}>
          <Shield size={18} style={{ color:C.goldDark }} />
          <p style={{ fontSize:'13.5px', color:C.textSec }}>
            Gestión de roles y accesos del sistema
          </p>
        </div>
        <button onClick={()=>setModalUsuario('nuevo')}
          style={{ display:'flex', alignItems:'center', gap:'6px',
            padding:'8px 18px', background:C.sidebar,
            border:`1px solid ${C.gold}`, borderRadius:'9px',
            color:C.gold, fontSize:'13.5px', fontWeight:'500',
            cursor:'pointer' }}>
          <Plus size={15}/> Nuevo usuario
        </button>
      </div>

      {/* Filtro de rol */}
      <div style={{ display:'flex', gap:'6px', marginBottom:'16px', flexWrap:'wrap' }}>
        {[{v:'',l:'Todos'}, ...Object.entries(ROL_CFG).map(([v,c])=>({v,l:c.label}))].map(r=>(
          <button key={r.v} onClick={()=>setFiltroRol(r.v)}
            style={{ padding:'6px 14px', borderRadius:'20px', cursor:'pointer',
              fontSize:'12.5px', fontWeight: filtroRol===r.v?'500':'400',
              background: filtroRol===r.v ? C.sidebar : 'transparent',
              border:`1px solid ${filtroRol===r.v ? C.gold : C.border}`,
              color: filtroRol===r.v ? C.gold : C.textSec,
              transition:'all 120ms' }}>
            {r.l}
            {r.v && (
              <span style={{ marginLeft:'5px', fontSize:'11px', opacity:.7 }}>
                ({usuarios.filter(u=>u.rol===r.v).length})
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tabla */}
      <div style={{ background:C.bg, border:`1px solid ${C.border}`,
        borderRadius:'12px', overflow:'hidden' }}>
        {isLoading ? (
          <div style={{ padding:'40px', textAlign:'center', color:C.textMuted }}>
            Cargando usuarios...
          </div>
        ) : usuarios.length === 0 ? (
          <div style={{ padding:'50px 20px', textAlign:'center', color:C.textMuted }}>
            <p style={{ fontSize:'15px', color:C.textSec }}>Sin usuarios encontrados</p>
          </div>
        ) : (
          <div style={{ overflowX:'auto' }}>
            <table style={{ width:'100%', borderCollapse:'collapse' }}>
              <thead>
                <tr style={{ background:C.bgSec }}>
                  {['Usuario','Rol','Estado','Último acceso',''].map(h=>(
                    <th key={h} style={{ padding:'10px 16px', textAlign:'left',
                      fontSize:'10.5px', fontWeight:'500', letterSpacing:'0.06em',
                      textTransform:'uppercase', color:C.textMuted,
                      borderBottom:`1px solid ${C.border}`, whiteSpace:'nowrap' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {usuarios.map(u=>(
                  <FilaUsuario
                    key={u.id}
                    usuario={u}
                    esYo={u.id === yo?.id}
                    onEditar={u=>setModalUsuario(u)}
                    onPassword={u=>setModalPassword(u)}
                    onToggleActivo={u=>toggleActivo.mutate(u)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modales */}
      {modalUsuario && (
        <ModalUsuario
          usuario={modalUsuario === 'nuevo' ? null : modalUsuario}
          onCerrar={()=>setModalUsuario(null)}
        />
      )}
      {modalPassword && (
        <ModalPassword
          usuario={modalPassword}
          onCerrar={()=>setModalPassword(null)}
        />
      )}
    </Layout>
  )
}
