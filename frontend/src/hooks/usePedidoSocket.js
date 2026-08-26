/**
 * usePedidoSocket
 * Hook que mantiene una conexión WebSocket con reconexión automática.
 * Dos modos:
 *   - pedido específico: usePedidoSocket({ pedidoId: 42 })
 *   - canal de rol:      usePedidoSocket({ rol: 'deposito' })
 */
import { useEffect, useRef, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../store/authStore'
import { baseUrlWs } from '../services/servidor'

export function usePedidoSocket({ pedidoId, rol, onMensaje } = {}) {
  const ws          = useRef(null)
  const timeoutId   = useRef(null)
  const intentos    = useRef(0)
  // La búsqueda del servidor es asíncrona: puede terminar después de que el
  // componente se desmontó. Sin esta bandera, abriríamos un socket huérfano.
  const cancelado   = useRef(false)
  const queryClient = useQueryClient()

  const conectar = useCallback(async () => {
    // El servidor se descubre por nombre de red, igual que la API REST
    // (services/servidor.js) — así el socket sigue al servidor si cambia de IP.
    const wsBase = await baseUrlWs()
    if (cancelado.current) return

    // El backend autentica el socket con el mismo JWT que la API REST (ver
    // apps/usuarios/ws_auth.py) — sin esto, la conexión se rechaza.
    const token = useAuthStore.getState().token
    const base = pedidoId
      ? `${wsBase}/ws/pedidos/${pedidoId}/`
      : `${wsBase}/ws/pedidos/rol/${rol}/`
    const url = token ? `${base}?token=${encodeURIComponent(token)}` : base

    ws.current = new WebSocket(url)

    ws.current.onopen = () => {
      clearTimeout(timeoutId.current)
      intentos.current = 0
    }

    ws.current.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        // Invalidar la query correspondiente para refrescar datos
        if (msg.pedido?.id) {
          queryClient.invalidateQueries({ queryKey: ['pedidos'] })
          queryClient.invalidateQueries({ queryKey: ['pedido', msg.pedido.id] })
          // Actualizar la cache directamente con los datos frescos
          queryClient.setQueryData(['pedido', msg.pedido.id], msg.pedido)
        }
        onMensaje?.(msg)
      } catch {/* ignorar mensajes malformados */}
    }

    ws.current.onclose = () => {
      if (cancelado.current) return
      // Reconexión exponencial: 2s, 4s, 8s… máx 30s
      const delay = Math.min(30000, 2000 * 2 ** intentos.current)
      timeoutId.current = setTimeout(() => {
        intentos.current += 1
        conectar()
      }, delay)
    }

    ws.current.onerror = () => {
      ws.current?.close()
    }
  }, [pedidoId, rol, onMensaje, queryClient])

  useEffect(() => {
    if (!pedidoId && !rol) return
    cancelado.current = false
    conectar()
    return () => {
      cancelado.current = true
      clearTimeout(timeoutId.current)
      ws.current?.close()
    }
  }, [pedidoId, rol])

  return {
    enviar: (data) => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send(JSON.stringify(data))
      }
    },
  }
}
