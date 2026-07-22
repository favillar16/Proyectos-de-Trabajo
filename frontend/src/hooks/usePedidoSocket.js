/**
 * usePedidoSocket
 * Hook que mantiene una conexión WebSocket con reconexión automática.
 * Dos modos:
 *   - pedido específico: usePedidoSocket({ pedidoId: 42 })
 *   - canal de rol:      usePedidoSocket({ rol: 'deposito' })
 */
import { useEffect, useRef, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'

const WS_BASE = (() => {
  const api = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'
  const host = api.replace(/^https?/, 'ws').replace('/api/v1', '')
  return host
})()

export function usePedidoSocket({ pedidoId, rol, onMensaje } = {}) {
  const ws          = useRef(null)
  const reconectar  = useRef(null)
  const queryClient = useQueryClient()

  const conectar = useCallback(() => {
    const url = pedidoId
      ? `${WS_BASE}/ws/pedidos/${pedidoId}/`
      : `${WS_BASE}/ws/pedidos/rol/${rol}/`

    ws.current = new WebSocket(url)

    ws.current.onopen = () => {
      clearTimeout(reconectar.current)
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
      // Reconexión exponencial: 2s, 4s, 8s… máx 30s
      const delay = Math.min(30000, 2000 * (reconectar.current?.intentos ?? 1))
      reconectar.current = setTimeout(() => {
        reconectar.current = { intentos: (reconectar.current?.intentos ?? 1) + 1 }
        conectar()
      }, delay)
    }

    ws.current.onerror = () => {
      ws.current?.close()
    }
  }, [pedidoId, rol, onMensaje, queryClient])

  useEffect(() => {
    if (!pedidoId && !rol) return
    conectar()
    return () => {
      clearTimeout(reconectar.current)
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
