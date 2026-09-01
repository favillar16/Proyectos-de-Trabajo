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
  // Cada montaje del efecto se lleva su propio número de generación. La
  // búsqueda del servidor es asíncrona y puede terminar después de que el
  // componente se desmontó — o después de que volvió a montarse, que es lo que
  // hace React.StrictMode en dev. Una bandera booleana compartida no alcanza:
  // el segundo montaje la vuelve a poner en falso antes de que el `await` del
  // primero llegue a mirarla, y ahí se abre el socket huérfano. Comparar
  // generaciones no tiene esa carrera.
  const generacion  = useRef(0)
  const queryClient = useQueryClient()

  const conectar = useCallback(async (gen) => {
    // El servidor se descubre por nombre de red, igual que la API REST
    // (services/servidor.js) — así el socket sigue al servidor si cambia de IP.
    const wsBase = await baseUrlWs()
    if (gen !== generacion.current) return

    // El backend autentica el socket con el mismo JWT que la API REST (ver
    // apps/usuarios/ws_auth.py) — sin esto, la conexión se rechaza.
    const token = useAuthStore.getState().token
    const base = pedidoId
      ? `${wsBase}/ws/pedidos/${pedidoId}/`
      : `${wsBase}/ws/pedidos/rol/${rol}/`
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
      // de estado).
      if (ws.current !== socket) return
      // Reconexión exponencial: 2s, 4s, 8s… máx 30s
      const delay = Math.min(30000, 2000 * 2 ** intentos.current)
      timeoutId.current = setTimeout(() => {
        intentos.current += 1
        conectar(gen)
      }, delay)
    }

    socket.onerror = () => {
      socket.close()
    }
  }, [pedidoId, rol, onMensaje, queryClient])

  useEffect(() => {
    if (!pedidoId && !rol) return
    const gen = (generacion.current += 1)
    conectar(gen)
    return () => {
      // Invalida cualquier conexión que todavía esté esperando al
      // descubrimiento del servidor.
      generacion.current += 1
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
