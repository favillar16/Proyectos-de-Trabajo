# Log de revisiones técnicas

Registro de auditorías de código y correcciones aplicadas fuera del checklist
de entrega funcional. Sirve como punto de partida para la próxima sesión de
trabajo — qué se revisó, qué se corrigió y qué quedó pendiente.

---

## 2026-08-04 — Revisión de conexión en red (PC ↔ tablets)

**Commit:** `34c694b — Cambios 04/08/2026`

- **Corregido (crítico):** `VITE_API_URL` estaba fijada a `http://localhost:8000/api/v1`
  en `frontend/.env`. Vite graba ese valor en el bundle de JS que se sirve a
  *todos* los dispositivos, así que cualquier tablet u otra PC que abriera el
  sistema por IP intentaba conectarse a su propio `localhost` en vez de al
  servidor. Rompía la API REST y el WebSocket en todo dispositivo que no
  fuera la PC servidor.
  - Fix: `frontend/src/services/api.js` y `frontend/src/hooks/usePedidoSocket.js`
    ahora derivan el host de `window.location.hostname` en vez de un valor
    fijo. `VITE_API_URL` sigue funcionando como override manual si se
    necesita forzar una URL específica.
  - `frontend/.env` actualizado (variable comentada, detección automática).
  - `frontend/dist` recompilado para que el build de producción también
    quede corregido.
- **Nota sin resolver:** `checklist_entrega.md` y `README.md` piden Redis 7
  para los WebSocket, pero `backend/config/settings.py` usa
  `InMemoryChannelLayer` (Redis está comentado). No rompe nada mientras
  corra un solo proceso Daphne, pero es documentación desactualizada.

---

## 2026-08-04 — Revisión de estructura completa (backend + frontend)

**Commit:** `dce1d4a — Ajustes a Estructura`

- **Corregido (crítico — endpoint débil):** `POST /ventas/pedidos/<id>/estado/`
  permitía que un `vendedor` o `depósito` marcara cualquier pedido "listo"
  como `pagado` directamente, sin pasar por el módulo de caja. Eso evitaba
  el registro del `Pago`, el descuento de stock y el ticket — un pedido
  podía quedar cerrado como pagado sin cobro real y sin rastro en los
  reportes de caja. Bloqueado en `backend/apps/ventas/views.py`
  (`CambioEstadoView`); el frontend nunca usaba ese camino, así que no
  afecta ningún flujo existente.
- **Feature completada:** el frontend ya tenía el botón "Ver historial" en
  Inventario con el texto *"se implementará en el sprint de reportes"* y la
  función `inventarioApi.movimientos()` ya definida, pero el endpoint del
  backend nunca se creó. Se agregó `GET /inventario/movimientos/?variante_id=<id>`
  (`backend/apps/inventario/views.py`, `urls.py`) y se conectó el panel en
  `InventarioPage.jsx` — ahora muestra el historial real de movimientos de
  stock (tipo, cantidad, usuario, fecha, observaciones).
- **Limpieza:** 73 archivos `.pyc`/`__pycache__` estaban versionados en git.
  Se agregó la exclusión a `.gitignore` y se desvincularon del repo (siguen
  en disco, se regeneran solos).
- **Nota entregada sin resolver en ese momento, resuelta después:** cualquier
  cajero podía aplicar hasta 100% de descuento al cobrar sin ningún control
  adicional (a diferencia de la edición de precios en el pedido, reservada a
  admin/encargada de ventas). Ver entrada siguiente.

---

## 2026-08-04 — Tope de descuento en caja + revisión de frontend

**Commit:** `dce1d4a` (descuento) y `3abde00 — Corrige 4 bugs de UX/funcionamiento en el frontend`

- **Corregido:** el descuento que puede aplicar un cajero al cobrar se topeó
  a **70%** (antes permitía hasta 100%, equivalente a regalar mercadería sin
  aprobación). Cambiado en `backend/apps/caja/views.py`
  (constante `DESCUENTO_CAJA_MAXIMO`) y en `frontend/src/pages/CajaPage.jsx`
  (input y cálculo de `pct`) para que ambos lados coincidan.
- **Revisión de frontend únicamente** (agente Explore + verificación manual),
  4 hallazgos corregidos:
  1. `CajaPage.jsx` usaba `C.goldLight`, un color inexistente en la paleta
     local del archivo — el nombre del cliente quedaba invisible en la card
     del pedido activo de la cola de cobro.
  2. `usePedidoSocket.js`: el backoff exponencial de reconexión (documentado
     "2s, 4s, 8s… máx 30s") estaba roto — una misma ref se usaba para el ID
     del timer y para el contador de intentos, pisándose entre sí. Separadas
     en dos refs (`timeoutId`, `intentos`).
  3. Errores al crear una nota de pedido (`NuevoPedidoForm.jsx`,
     `ShowroomPage.jsx`) se mostraban como JSON crudo truncado. Se creó
     `frontend/src/utils/apiErrors.js` (traductor de errores DRF a texto
     legible) y se reusó en ambos formularios.
  4. En `ProductosPage.jsx`, el botón "Ver detalle" (ícono de ojo) solo
     disparaba un toast con el nombre del producto — no mostraba nada real.
     Ahora abre el mismo panel de edición que "Editar" (con imágenes,
     variantes y precios).
  - Además: no se podía confirmar una factura en caja sin RUC/razón social
    cargados (ahora bloqueado con mensaje inline); la cantidad a pedir en el
    showroom no respetaba el stock disponible de la variante (ahora
    limitada, con aviso "Máximo disponible: X").

---

## Pendientes conocidos (no resueltos aún)

Quedaron identificados pero **sin corregir** — a revisar/decidir en la
próxima sesión:

1. **Redis vs `InMemoryChannelLayer`** — documentación pide Redis, el código
   no lo usa. Definir si se limpia la documentación o se activa Redis de
   cara a escalar a múltiples workers Daphne.
2. **`ReimprimirTicketView`** (`backend/apps/caja/views.py`) — cualquier
   cajero puede reimprimir el ticket de cualquier pago, no solo los de su
   propia sesión. Posiblemente intencional, confirmar con el negocio.
3. Validación de subida de imágenes (`ImagenProductoSerializer`,
   `ImagenVarianteSerializer`) depende solo de `ImageField` de Django/Pillow;
   sin límite de tamaño explícito a nivel de serializer más allá del límite
   global de 10MB en `settings.py`. Bajo riesgo (requiere rol
   admin/vendedor autenticado para subir), pero queda anotado.

---

## Cómo continuar la próxima sesión

- Verificar que `frontend/dist` esté actualizado si se toca cualquier
  archivo de `frontend/src` (correr `npm run build` en `frontend/`).
- Antes de commitear, correr `python manage.py check` en `backend/` y
  `npx vite build` en `frontend/` — ambos deben pasar sin errores.
- Revisar la lista de "Pendientes conocidos" arriba antes de buscar
  hallazgos nuevos, para no repetir análisis ya hecho.
