import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { useAuthStore } from './store/authStore'
import ErrorBoundary from './components/ErrorBoundary'

// Páginas
import LoginPage from './pages/LoginPage'
import ShowroomPage from './pages/ShowroomPage'
import ProductosPage from './pages/ProductosPage'
import PedidosPage from './pages/PedidosPage'
import CajaPage from './pages/CajaPage'
import DashboardPage from './pages/DashboardPage'
import InventarioPage from './pages/InventarioPage'
import UsuariosPage from './pages/UsuariosPage'
import CostosPage   from './pages/CostosPage'

// Styles
import './styles/design-system.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 30, // 30 segundos
      retry: 1,
    },
  },
})

// ─── Guard de rutas protegidas ────────────────────────────────
function ProtectedRoute({ children, roles }) {
  const { isAuthenticated, usuario } = useAuthStore()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  if (roles && usuario && !roles.includes(usuario.rol)) {
    return <Navigate to="/showroom" replace />
  }

  return children
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ErrorBoundary>
        <Routes>
          {/* Pública */}
          <Route path="/login" element={<LoginPage />} />

          {/* Protegidas */}
          <Route path="/showroom" element={
            <ProtectedRoute>
              <ShowroomPage />
            </ProtectedRoute>
          } />
          <Route path="/productos" element={
            <ProtectedRoute roles={['admin', 'encargada_ventas', 'vendedor']}>
              <ProductosPage />
            </ProtectedRoute>
          } />
          <Route path="/pedidos" element={
            <ProtectedRoute roles={['admin', 'encargada_ventas', 'vendedor', 'deposito']}>
              <PedidosPage />
            </ProtectedRoute>
          } />
          <Route path="/caja" element={
            <ProtectedRoute roles={['admin', 'cajero']}>
              <CajaPage />
            </ProtectedRoute>
          } />
          <Route path="/inventario" element={
            <ProtectedRoute roles={['admin', 'deposito']}>
              <InventarioPage />
            </ProtectedRoute>
          } />
          <Route path="/dashboard" element={
            <ProtectedRoute roles={['admin']}>
              <DashboardPage />
            </ProtectedRoute>
          } />
          <Route path="/usuarios" element={
            <ProtectedRoute roles={['admin']}>
              <UsuariosPage />
            </ProtectedRoute>
          } />
          <Route path="/costos" element={
            <ProtectedRoute roles={['admin']}>
              <CostosPage />
            </ProtectedRoute>
          } />

          {/* Redirects */}
          <Route path="/" element={<Navigate to="/showroom" replace />} />
          <Route path="*" element={<Navigate to="/showroom" replace />} />
        </Routes>
        </ErrorBoundary>
      </BrowserRouter>

      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            fontFamily: 'var(--font-body)',
            fontSize: '14px',
            borderRadius: 'var(--border-radius-md)',
            border: '1px solid var(--color-border)',
          },
          success: {
            iconTheme: { primary: 'var(--color-gold)', secondary: '#fff' },
          },
        }}
      />
    </QueryClientProvider>
  )
}
