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
    // El backend autentica el socket con el mismo JWT que la API REST (ver
    // apps/usuarios/ws_auth.py) — sin esto, la conexión se rechaza.
    const token = useAuthStore.getState().token
    const base = pedidoId
      ? `${WS_BASE}/ws/pedidos/${pedidoId}/`
      : `${WS_BASE}/ws/pedidos/rol/${rol}/`
    const url = token ? `${base}?token=${encodeURIComponent(token)}` : base

    // Se guarda la instancia en una variable local además de en el ref: el
    // cierre de ESTE socket en particular sólo debe reconectar si sigue
    // siendo el socket vigente al momento de dispararse `onclose` (más abajo).
    const socket = new WebSocket(url)
    ws.current = socket

    socket.onopen = () => {
      clearTimeout(timeoutId.current)
      intentos.current = 0
    }

    socket.onmessage = (e) => {
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

    socket.onclose = () => {
      // Si `ws.current` ya no es ESTE socket, es porque el cleanup del
      // efecto lo reemplazó (unmount, cambio de pedidoId/rol, o el doble
      // montaje de React.StrictMode en dev) — no hay que reconectar: antes
      // reconectaba igual y dejaba un socket fantasma vivo en paralelo al
      // nuevo, duplicando cada mensaje (y con él, el toast de cada cambio
      // de estado). Una bandera compartida no alcanza acá porque la
      // reconexión siguiente la vuelve a poner en falso antes de que el
      // cierre async de ESTA conexión llegue a mirarla; comparar identidad
      // de instancia no tiene esa carrera.
      if (ws.current !== socket) return
      // Reconexión exponencial: 2s, 4s, 8s… máx 30s
      const delay = Math.min(30000, 2000 * 2 ** intentos.current)
      timeoutId.current = setTimeout(() => {
        intentos.current += 1
        conectar()
      }, delay)
    }

    socket.onerror = () => {
      socket.close()
    }
  }, [pedidoId, rol, onMensaje, queryClient])

  useEffect(() => {
    if (!pedidoId && !rol) return
    conectar()
    return () => {
      clearTimeout(timeoutId.current)
      const socket = ws.current
      ws.current = null
      socket?.close()
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
