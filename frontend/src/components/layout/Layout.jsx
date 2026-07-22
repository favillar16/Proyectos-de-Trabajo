/**
 * Layout principal — Oga Porã
 *
 * Estructura:
 *   <Layout pageTitle="Productos" breadcrumbs={[...]}>
 *     <ContenidoDeLaPagina />
 *   </Layout>
 *
 * Sidebar colapsable en escritorio, overlay en tablet/móvil.
 * Navegación filtrada por rol del usuario autenticado.
 */
import { useState, useCallback } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Package, ShoppingCart, CreditCard,
  BarChart3, LogOut, Layers, Warehouse, ChevronRight,
  ChevronLeft, Bell, Settings, Menu, X, ChevronDown,
  Users, Calculator,
} from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import { useDevice } from '../../hooks/useDevice'
import logoOgaPora from '../../assets/logo_oga_pora.png'

// ─── Paleta inline (espejo de design-system.css) ─────────────────────────────
// Se definen aquí para poder usarlos en lógica JS (estados hover)
const C = {
  sidebar:        '#453941',
  sidebarHover:   '#362F31',
  sidebarActive:  '#2d2427',
  sidebarBorder:  'rgba(185,156,116,0.15)',
  gold:           '#B99C74',
  goldLight:      '#d4bc98',
  goldMuted:      'rgba(185,156,116,0.12)',
  textOnSidebar:  '#e8e0d5',
  textMuted:      'rgba(232,224,213,0.55)',
  bg:             '#ffffff',
  bgSecondary:    '#fafaf9',
  border:         '#e8e4df',
  textPrimary:    '#1a1714',
  textSecondary:  '#6b6560',
}

// ─── Ítems de navegación ──────────────────────────────────────────────────────
const NAV_ITEMS = [
  {
    label: 'Dashboard',
    icon:  LayoutDashboard,
    path:  '/dashboard',
    roles: ['admin'],
  },
  {
    label: 'Showroom',
    icon:  Layers,
    path:  '/showroom',
    roles: ['admin', 'encargada_ventas', 'vendedor'],
  },
  {
    label: 'Productos',
    icon:  Package,
    path:  '/productos',
    roles: ['admin', 'encargada_ventas', 'vendedor'],
  },
  {
    label: 'Inventario',
    icon:  Warehouse,
    path:  '/inventario',
    roles: ['admin', 'deposito'],
  },
  {
    label: 'Pedidos',
    icon:  ShoppingCart,
    path:  '/pedidos',
    roles: ['admin', 'encargada_ventas', 'vendedor', 'deposito'],
  },
  {
    label: 'Caja',
    icon:  CreditCard,
    path:  '/caja',
    roles: ['admin', 'cajero'],
  },
  {
    label: 'Usuarios',
    icon:  Users,
    path:  '/usuarios',
    roles: ['admin'],
  },
  {
    label: 'Costos',
    icon:  Calculator,
    path:  '/costos',
    roles: ['admin'],
  },
]

// Etiquetas de rol para mostrar en el footer del sidebar
const ROL_LABEL = {
  admin:            'Administrador',
  encargada_ventas: 'Encargada de Ventas',
  vendedor:         'Vendedor',
  cajero:           'Cajero',
  deposito:         'Depósito',
}

// ─── Avatar de usuario ────────────────────────────────────────────────────────
function UserAvatar({ nombre, size = 32 }) {
  const iniciales = nombre
    ? nombre.split(' ').slice(0, 2).map(p => p[0]).join('').toUpperCase()
    : '?'
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%',
      background: C.goldMuted,
      border: `1px solid ${C.sidebarBorder}`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexShrink: 0,
      fontSize: size * 0.35,
      fontWeight: 600,
      color: C.gold,
      letterSpacing: '0.02em',
    }}>
      {iniciales}
    </div>
  )
}

// ─── Item de navegación ───────────────────────────────────────────────────────
function NavItem({ item, collapsed, onClick }) {
  const Icon = item.icon
  const [hovered, setHovered] = useState(false)

  return (
    <NavLink
      to={item.path}
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      title={collapsed ? item.label : undefined}
      style={({ isActive }) => ({
        display:        'flex',
        alignItems:     'center',
        gap:            '10px',
        padding:        collapsed ? '10px' : '9px 12px',
        justifyContent: collapsed ? 'center' : 'flex-start',
        borderRadius:   '8px',
        marginBottom:   '1px',
        textDecoration: 'none',
        fontSize:       '13.5px',
        fontWeight:     isActive ? '500' : '400',
        letterSpacing:  '0.01em',
        color:          isActive ? C.gold : (hovered ? C.goldLight : C.textOnSidebar),
        background:     isActive ? C.goldMuted : (hovered ? 'rgba(255,255,255,0.04)' : 'transparent'),
        borderLeft:     isActive ? `2px solid ${C.gold}` : '2px solid transparent',
        transition:     'all 120ms ease',
        overflow:       'hidden',
        whiteSpace:     'nowrap',
      })}
    >
      <Icon
        size={17}
        style={{ flexShrink: 0, opacity: 0.9 }}
        strokeWidth={1.75}
      />
      {!collapsed && <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.label}</span>}
    </NavLink>
  )
}

// ─── Sidebar ──────────────────────────────────────────────────────────────────
function Sidebar({ collapsed, onToggle, onNavClick, isMobile = false }) {
  const { usuario, logout } = useAuthStore()
  const [logoutHover, setLogoutHover] = useState(false)
  const [toggleHover, setToggleHover] = useState(false)

  const itemsVisibles = NAV_ITEMS.filter(item =>
    !usuario?.rol || item.roles.includes(usuario.rol)
  )

  return (
    <aside style={{
      width:          collapsed ? '60px' : '240px',
      height:         '100vh',
      background:     C.sidebar,
      display:        'flex',
      flexDirection:  'column',
      transition:     isMobile ? 'none' : 'width 200ms ease',
      flexShrink:     0,
      zIndex:         100,
      borderRight:    `1px solid ${C.sidebarBorder}`,
      overflow:       'hidden',
    }}>

      {/* ── Cabecera con logo y toggle ── */}
      <div style={{
        display:       'flex',
        alignItems:    'center',
        gap:           '8px',
        padding:       collapsed ? '0 14px' : '0 14px 0 16px',
        height:        '56px',
        borderBottom:  `1px solid ${C.sidebarBorder}`,
        flexShrink:    0,
      }}>

        {/* Logo compacto */}
        <div style={{
          width: 32, height: 32,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
        }}>
          <img
            src={logoOgaPora}
            alt="Oga Porã"
            style={{ width: 32, height: 32, objectFit: 'contain', borderRadius: '6px' }}
          />
        </div>

        {/* Nombre del negocio */}
        {!collapsed && (
          <div style={{ flex: 1, overflow: 'hidden' }}>
            <p style={{
              fontFamily:  'var(--font-display)',
              fontSize:    '15px',
              fontWeight:  600,
              color:       C.gold,
              lineHeight:  1.25,
              whiteSpace:  'nowrap',
              overflow:    'hidden',
              textOverflow:'ellipsis',
            }}>
              Oga Porã
            </p>
            <p style={{
              fontSize:       '9.5px',
              color:          C.textMuted,
              letterSpacing:  '0.10em',
              textTransform:  'uppercase',
              marginTop:      '1px',
            }}>
              Acabados de Construcción
            </p>
          </div>
        )}

        {/* Botón colapsar — solo desktop */}
        {!isMobile && (
          <button
            onClick={onToggle}
            onMouseEnter={() => setToggleHover(true)}
            onMouseLeave={() => setToggleHover(false)}
            title={collapsed ? 'Expandir sidebar' : 'Colapsar sidebar'}
            style={{
              background:     toggleHover ? 'rgba(255,255,255,0.06)' : 'transparent',
              border:         'none',
              cursor:         'pointer',
              color:          toggleHover ? C.gold : C.textMuted,
              padding:        '5px',
              borderRadius:   '6px',
              display:        'flex',
              alignItems:     'center',
              justifyContent: 'center',
              flexShrink:     0,
              transition:     'all 120ms ease',
            }}
          >
            {collapsed
              ? <ChevronRight size={16} strokeWidth={2} />
              : <ChevronLeft  size={16} strokeWidth={2} />
            }
          </button>
        )}

        {/* Botón cerrar — solo móvil */}
        {isMobile && (
          <button
            onClick={onNavClick}
            style={{
              background: 'transparent', border: 'none',
              cursor: 'pointer', color: C.textMuted,
              padding: '5px', borderRadius: '6px',
              display: 'flex', alignItems: 'center',
              marginLeft: 'auto',
            }}
          >
            <X size={18} />
          </button>
        )}
      </div>

      {/* ── Navegación ── */}
      <nav style={{
        flex:      1,
        padding:   collapsed ? '10px 6px' : '10px 8px',
        overflowY: 'auto',
        overflowX: 'hidden',
      }}>
        {itemsVisibles.map(item => (
          <NavItem
            key={item.path}
            item={item}
            collapsed={collapsed}
            onClick={onNavClick}
          />
        ))}
      </nav>

      {/* ── Footer: usuario + logout ── */}
      <div style={{
        borderTop: `1px solid ${C.sidebarBorder}`,
        padding:   collapsed ? '10px 6px' : '10px 8px',
        flexShrink: 0,
      }}>
        {/* Info de usuario */}
        {!collapsed && usuario && (
          <div style={{
            display:       'flex',
            alignItems:    'center',
            gap:           '9px',
            padding:       '8px 10px',
            marginBottom:  '4px',
            borderRadius:  '8px',
            background:    'rgba(255,255,255,0.03)',
          }}>
            <UserAvatar nombre={usuario.nombre_completo} size={30} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{
                fontSize:     '12.5px',
                fontWeight:   '500',
                color:        C.textOnSidebar,
                lineHeight:   1.3,
                overflow:     'hidden',
                textOverflow: 'ellipsis',
                whiteSpace:   'nowrap',
              }}>
                {usuario.nombre_completo}
              </p>
              <p style={{
                fontSize:       '10.5px',
                color:          C.gold,
                marginTop:      '1px',
                textTransform:  'capitalize',
              }}>
                {ROL_LABEL[usuario.rol] || usuario.rol}
              </p>
            </div>
          </div>
        )}

        {/* Avatar solo cuando está colapsado */}
        {collapsed && usuario && (
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '4px' }}>
            <UserAvatar nombre={usuario.nombre_completo} size={32} />
          </div>
        )}

        {/* Botón logout */}
        <button
          onClick={logout}
          onMouseEnter={() => setLogoutHover(true)}
          onMouseLeave={() => setLogoutHover(false)}
          title="Cerrar sesión"
          style={{
            display:        'flex',
            alignItems:     'center',
            gap:            '8px',
            justifyContent: collapsed ? 'center' : 'flex-start',
            width:          '100%',
            padding:        '8px 10px',
            background:     logoutHover ? 'rgba(185,156,116,0.07)' : 'transparent',
            border:         'none',
            borderRadius:   '8px',
            color:          logoutHover ? C.gold : C.textMuted,
            cursor:         'pointer',
            fontSize:       '13px',
            transition:     'all 120ms ease',
          }}
        >
          <LogOut size={15} strokeWidth={1.75} style={{ flexShrink: 0 }} />
          {!collapsed && <span>Cerrar sesión</span>}
        </button>
      </div>
    </aside>
  )
}

// ─── Topbar ───────────────────────────────────────────────────────────────────
function Topbar({ pageTitle, breadcrumbs, onMenuClick, showMenuButton }) {
  const [bellHover,     setBellHover]     = useState(false)
  const [settingsHover, setSettingsHover] = useState(false)

  return (
    <header style={{
      height:        '56px',
      background:    C.bg,
      borderBottom:  `1px solid ${C.border}`,
      display:       'flex',
      alignItems:    'center',
      justifyContent:'space-between',
      padding:       '0 20px',
      position:      'sticky',
      top:           0,
      zIndex:        50,
      gap:           '12px',
    }}>

      {/* Botón menú (solo visible en tablet/móvil) */}
      {showMenuButton && (
        <button
          onClick={onMenuClick}
          style={{
            background: 'transparent', border: 'none',
            cursor: 'pointer', padding: '6px',
            color: C.textSecondary, borderRadius: '8px',
            display: 'flex', alignItems: 'center', flexShrink: 0,
          }}
        >
          <Menu size={20} />
        </button>
      )}

      {/* Título + breadcrumbs */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {breadcrumbs && breadcrumbs.length > 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            {breadcrumbs.map((crumb, i) => (
              <span key={i} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                {i > 0 && (
                  <ChevronRight size={12} style={{ color: C.textSecondary, opacity: 0.5, flexShrink: 0 }} />
                )}
                <span style={{
                  fontSize:     i === breadcrumbs.length - 1 ? '14px' : '13px',
                  fontWeight:   i === breadcrumbs.length - 1 ? '500' : '400',
                  color:        i === breadcrumbs.length - 1 ? C.textPrimary : C.textSecondary,
                  fontFamily:   i === breadcrumbs.length - 1 ? 'var(--font-display)' : 'inherit',
                  whiteSpace:   'nowrap',
                }}>
                  {crumb}
                </span>
              </span>
            ))}
          </div>
        ) : (
          <h1 style={{
            fontSize:   '15px',
            fontWeight: '500',
            color:      C.textPrimary,
            fontFamily: 'var(--font-display)',
            letterSpacing: '0.01em',
            overflow:   'hidden',
            textOverflow:'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {pageTitle}
          </h1>
        )}
      </div>

      {/* Acciones topbar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
        <TopbarButton
          icon={<Bell size={17} strokeWidth={1.75} />}
          title="Notificaciones"
          hovered={bellHover}
          onMouseEnter={() => setBellHover(true)}
          onMouseLeave={() => setBellHover(false)}
        />
        <TopbarButton
          icon={<Settings size={17} strokeWidth={1.75} />}
          title="Configuración"
          hovered={settingsHover}
          onMouseEnter={() => setSettingsHover(true)}
          onMouseLeave={() => setSettingsHover(false)}
        />
      </div>
    </header>
  )
}

function TopbarButton({ icon, title, hovered, onMouseEnter, onMouseLeave, onClick }) {
  return (
    <button
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      title={title}
      style={{
        background:  hovered ? '#f5f4f2' : 'transparent',
        border:      'none',
        cursor:      'pointer',
        color:       hovered ? C.textPrimary : C.textSecondary,
        padding:     '7px',
        borderRadius:'8px',
        display:     'flex',
        alignItems:  'center',
        justifyContent: 'center',
        transition:  'all 120ms ease',
      }}
    >
      {icon}
    </button>
  )
}

// ─── Layout principal ─────────────────────────────────────────────────────────
/**
 * Props:
 *   pageTitle   string              Título en la topbar
 *   breadcrumbs string[]            Ej: ['Productos', 'Porcelanatos', 'Editar']
 *   children    ReactNode           Contenido de la página
 *   fullWidth   boolean             Sin maxWidth (para showroom, grids grandes)
 *   noPadding   boolean             Sin padding (para páginas con layout propio)
 */
// ─── Barra de navegación inferior para tablet ─────────────────────────────────
// Se muestra cuando el sidebar está oculto (≤1180px en touch)

function TabletNavBar({ usuario, onMenuOpen }) {
  const location = useLocation()
  const items = NAV_ITEMS.filter(i =>
    !usuario?.rol || i.roles.includes(usuario.rol)
  ).slice(0, 4) // Max 4 ítems en la barra inferior

  return (
    <nav style={{
      position:        'fixed',
      bottom:          0, left: 0, right: 0,
      zIndex:          90,
      height:          '62px',
      background:      C.sidebar,
      borderTop:       `1px solid ${C.sidebarBorder}`,
      display:         'flex',
      alignItems:      'stretch',
      // Safe area para dispositivos con barra de gestos Android
      paddingBottom:   'env(safe-area-inset-bottom, 0px)',
    }}>
      {items.map(item => {
        const Icon    = item.icon
        const activo  = location.pathname.startsWith(item.path)
        return (
          <NavLink
            key={item.path}
            to={item.path}
            style={{
              flex:           1,
              display:        'flex',
              flexDirection:  'column',
              alignItems:     'center',
              justifyContent: 'center',
              gap:            '3px',
              textDecoration: 'none',
              color:          activo ? C.gold : 'rgba(232,224,213,0.55)',
              borderTop:      `2px solid ${activo ? C.gold : 'transparent'}`,
              transition:     'all 120ms',
              // Target táctil mínimo 48px
              minHeight:      '48px',
            }}
          >
            <Icon size={20} strokeWidth={1.75} />
            <span style={{ fontSize: '10px', fontWeight: activo ? '500' : '400' }}>
              {item.label}
            </span>
          </NavLink>
        )
      })}

      {/* Botón "más" para abrir sidebar como overlay */}
      <button
        onClick={onMenuOpen}
        style={{
          flex:           1,
          display:        'flex',
          flexDirection:  'column',
          alignItems:     'center',
          justifyContent: 'center',
          gap:            '3px',
          background:     'transparent',
          border:         'none',
          borderTop:      '2px solid transparent',
          cursor:         'pointer',
          color:          'rgba(232,224,213,0.55)',
          minHeight:      '48px',
        }}
      >
        <Menu size={20} strokeWidth={1.75} />
        <span style={{ fontSize: '10px' }}>Más</span>
      </button>
    </nav>
  )
}

// ─── Pie de página con copyright ──────────────────────────────────────────────
function PieCopyright({ noPadding }) {
  const anio = new Date().getFullYear()
  const colorTexto = '#9e9892'   // gris legible sobre fondo claro del contenido
  return (
    <footer style={{
      marginTop:   '24px',
      padding:     noPadding ? '14px 20px' : '14px 0 4px',
      borderTop:   `1px solid #e8e4df`,
      display:     'flex',
      flexWrap:    'wrap',
      alignItems:  'center',
      justifyContent: 'center',
      gap:         '6px',
      textAlign:   'center',
    }}>
      <span style={{ fontSize: '11.5px', color: colorTexto }}>
        © {anio} Oga Porã — Acabados de Construcción.
      </span>
      <span style={{ fontSize: '11.5px', color: colorTexto }}>
        Todos los derechos reservados.
      </span>
      <span style={{ fontSize: '11.5px', color: colorTexto, opacity: 0.7 }}>
        Sistema de Gestión Comercial v1.0
      </span>
    </footer>
  )
}

// ─── Layout principal ─────────────────────────────────────────────────────────
export default function Layout({
  children,
  pageTitle   = 'Inicio',
  breadcrumbs = [],
  fullWidth   = false,
  noPadding   = false,
}) {
  const [collapsed,  setCollapsed]  = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const device   = useDevice()
  const { usuario } = useAuthStore()

  const closeMobile   = useCallback(() => setMobileOpen(false), [])
  const toggleSidebar = useCallback(() => setCollapsed(c => !c), [])

  // En tablets touch, el sidebar se oculta y aparece nav bar inferior
  const mostrarTabletNav = device.isTouch && device.width < 1180
  const mostrarSidebarFijo = !mostrarTabletNav

  return (
    <div style={{
      display:    'flex',
      height:     '100vh',
      overflow:   'hidden',
      background: C.bgSecondary,
    }}>

      {/* ── Sidebar desktop (solo cuando no es tablet touch) ── */}
      {mostrarSidebarFijo && (
        <Sidebar
          collapsed={collapsed}
          onToggle={toggleSidebar}
          onNavClick={() => {}}
          isMobile={false}
        />
      )}

      {/* ── Sidebar overlay (tablet/móvil al abrir menú) ── */}
      {mobileOpen && (
        <div
          onClick={closeMobile}
          style={{
            position:       'fixed', inset: 0, zIndex: 200,
            background:     'rgba(26,23,20,0.55)',
            backdropFilter: 'blur(2px)',
          }}
        >
          <div onClick={e => e.stopPropagation()} style={{ height: '100%', display: 'inline-block' }}>
            <Sidebar
              collapsed={false}
              onToggle={closeMobile}
              onNavClick={closeMobile}
              isMobile={true}
            />
          </div>
        </div>
      )}

      {/* ── Área principal ── */}
      <div style={{
        flex:          1,
        display:       'flex',
        flexDirection: 'column',
        minWidth:      0,
        height:        '100vh',
        overflow:      'hidden',
      }}>
        <Topbar
          pageTitle={pageTitle}
          breadcrumbs={breadcrumbs}
          onMenuClick={() => setMobileOpen(true)}
          showMenuButton={mostrarTabletNav}
        />

        <main style={{
          flex:      1,
          overflowY: 'auto',
          overflowX: 'hidden',
          // El scroll del contenido vive acá; el sidebar y el topbar quedan fijos.
        }}>
          <div style={{
            padding:   noPadding ? 0 : '20px',
            maxWidth:  fullWidth ? 'none' : '1440px',
            width:     '100%',
            margin:    '0 auto',
            // Las páginas con noPadding (caja, showroom) manejan su propia
            // altura interna; el resto crece con su contenido.
            minHeight: noPadding ? '100%' : undefined,
            height:    noPadding ? '100%' : undefined,
            display:   'flex',
            flexDirection: 'column',
            boxSizing: 'border-box',
            // Espacio para la nav bar inferior en tablet
            paddingBottom: mostrarTabletNav
              ? (noPadding ? '62px' : 'calc(62px + 20px)')
              : (noPadding ? 0 : '20px'),
          }}>
            <div style={{ flex: 1 }}>
              {children}
            </div>
            <PieCopyright noPadding={noPadding} />
          </div>
        </main>
      </div>

      {/* ── Barra de navegación inferior — tablet ── */}
      {mostrarTabletNav && (
        <TabletNavBar usuario={usuario} onMenuOpen={() => setMobileOpen(true)} />
      )}

      {/* ── Estilos globales ── */}
      <style>{`
        /* Scrollbar sidebar */
        aside nav::-webkit-scrollbar { width: 3px; }
        aside nav::-webkit-scrollbar-thumb {
          background: rgba(185,156,116,0.2);
          border-radius: 2px;
        }
        aside > div:first-child { will-change: width; }

        /* Imágenes — deshabilitar long-press context menu en touch */
        img { -webkit-touch-callout: none; }

        /* Inputs y selects — tamaño mínimo en tablet */
        @media (max-width: 1180px) and (pointer: coarse) {
          input, select, button { min-height: 44px; }
          input[type="checkbox"],
          input[type="radio"]   { min-height: unset; }
        }
      `}</style>
    </div>
  )
}
