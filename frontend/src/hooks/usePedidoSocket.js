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
  // Misma lógica que services/api.js: usa VITE_API_URL si está fijada,
  // si no deriva el host actual del navegador (funciona en localhost,
  // en la PC servidor y en tablets sin recompilar).
  const API_PORT = import.meta.env.VITE_API_PORT || '8000'
  const api = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:${API_PORT}/api/v1`
  const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host = api.replace(/^https?/, wsProtocol).replace('/api/v1', '')
  return host
})()

export function usePedidoSocket({ pedidoId, rol, onMensaje } = {}) {
  const ws          = useRef(null)
  const timeoutId   = useRef(null)
  const intentos    = useRef(0)
  const queryClient = useQueryClient()

  const conectar = useCallback(() => {
    const url = pedidoId
      ? `${WS_BASE}/ws/pedidos/${pedidoId}/`
      : `${WS_BASE}/ws/pedidos/rol/${rol}/`

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
    conectar()
    return () => {
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
