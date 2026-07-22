import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import toast from 'react-hot-toast'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import logoOgaPora from '../assets/logo_oga_pora.png'

export default function LoginPage() {
  const [form, setForm] = useState({ username: '', password: '' })
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const login = useAuthStore(s => s.login)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.username || !form.password) {
      toast.error('Completá usuario y contraseña')
      return
    }
    setLoading(true)
    try {
      await login(form.username, form.password)
      toast.success('Bienvenido al sistema')
      navigate('/')
    } catch (err) {
      const msg = err.response?.data?.detail || 'Credenciales incorrectas'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--color-sidebar)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Patrón decorativo de fondo */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: `
          radial-gradient(circle at 20% 20%, rgba(185,156,116,0.08) 0%, transparent 50%),
          radial-gradient(circle at 80% 80%, rgba(185,156,116,0.05) 0%, transparent 50%)
        `,
        pointerEvents: 'none',
      }} />

      {/* Card de login */}
      <div style={{
        background: 'var(--color-bg)',
        borderRadius: 'var(--border-radius-xl)',
        padding: '44px 40px',
        width: '100%',
        maxWidth: '400px',
        boxShadow: 'var(--shadow-lg)',
        position: 'relative',
      }}>

        {/* Logo + Nombre */}
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <img
            src={logoOgaPora}
            alt="Oga Porã"
            style={{
              width: '110px',
              height: '110px',
              objectFit: 'contain',
              borderRadius: '16px',
              margin: '0 auto 14px',
              display: 'block',
            }}
          />
          <h1 style={{
            fontFamily: 'var(--font-display)',
            fontSize: '22px',
            fontWeight: 600,
            color: 'var(--color-text-primary)',
            marginBottom: '4px',
          }}>
            Bienvenido
          </h1>
          <p style={{ fontSize: '13.5px', color: 'var(--color-text-secondary)' }}>
            Oga Porã — Acabados de Construcción
          </p>
        </div>

        {/* Formulario */}
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '16px' }}>
            <label style={{
              display: 'block', fontSize: '13px', fontWeight: '500',
              color: 'var(--color-text-secondary)', marginBottom: '6px',
            }}>
              Usuario
            </label>
            <input
              type="text"
              value={form.username}
              onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
              placeholder="Tu usuario"
              disabled={loading}
              style={{
                width: '100%', padding: '10px 14px',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--border-radius-md)',
                fontSize: '14px', color: 'var(--color-text-primary)',
                background: 'var(--color-bg)', outline: 'none',
                transition: 'border-color var(--transition-fast)',
              }}
              onFocus={e => e.target.style.borderColor = 'var(--color-gold)'}
              onBlur={e  => e.target.style.borderColor = 'var(--color-border)'}
            />
          </div>

          <div style={{ marginBottom: '24px' }}>
            <label style={{
              display: 'block', fontSize: '13px', fontWeight: '500',
              color: 'var(--color-text-secondary)', marginBottom: '6px',
            }}>
              Contraseña
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type={showPassword ? 'text' : 'password'}
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                placeholder="••••••••"
                disabled={loading}
                style={{
                  width: '100%', padding: '10px 40px 10px 14px',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--border-radius-md)',
                  fontSize: '14px', color: 'var(--color-text-primary)',
                  background: 'var(--color-bg)', outline: 'none',
                  transition: 'border-color var(--transition-fast)',
                }}
                onFocus={e => e.target.style.borderColor = 'var(--color-gold)'}
                onBlur={e  => e.target.style.borderColor = 'var(--color-border)'}
              />
              <button
                type="button"
                onClick={() => setShowPassword(s => !s)}
                style={{
                  position: 'absolute', right: '12px', top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: 'var(--color-text-muted)', padding: '2px',
                  display: 'flex', alignItems: 'center',
                }}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%', padding: '12px',
              background: loading ? 'var(--color-sidebar-hover)' : 'var(--color-sidebar)',
              border: '1px solid var(--color-gold)',
              borderRadius: 'var(--border-radius-md)',
              color: 'var(--color-gold)',
              fontSize: '14px', fontWeight: '500',
              cursor: loading ? 'not-allowed' : 'pointer',
              display: 'flex', alignItems: 'center',
              justifyContent: 'center', gap: '8px',
              transition: 'background var(--transition-fast)',
            }}
            onMouseEnter={e => { if (!loading) e.currentTarget.style.background = 'var(--color-sidebar-hover)' }}
            onMouseLeave={e => { if (!loading) e.currentTarget.style.background = 'var(--color-sidebar)' }}
          >
            {loading && <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />}
            {loading ? 'Ingresando...' : 'Ingresar al sistema'}
          </button>
        </form>

        <p style={{
          textAlign: 'center', fontSize: '12px',
          color: 'var(--color-text-muted)', marginTop: '24px',
        }}>
          Oga Porã — Acabados de Construcción v1.0
        </p>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
