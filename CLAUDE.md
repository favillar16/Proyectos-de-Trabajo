# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Sistema de gestión comercial for a flooring/ceramics/sanitary-ware store in Paraguay ("Oga Porã"). Runs on a local WiFi network with **no internet dependency** — one PC acts as the server, sales staff use tablets, and the owner's notebook keeps a read-only mirror. Stack: Django 4.2 + DRF + Channels (ASGI/WebSocket) + PostgreSQL 15, React 18 + Vite frontend, PWA-installable on Android tablets.

All user-facing text, model fields, and comments are in Spanish — keep new code consistent with that.

## Commands

### Backend (from `backend/`)
```
venv\Scripts\activate
python manage.py runserver              # HTTP only — no WebSocket support
daphne -b 0.0.0.0 -p 8000 config.asgi:application   # full app (HTTP+WS), what production/demo actually uses
python manage.py makemigrations usuarios productos inventario ventas caja costos facturacion
python manage.py migrate
python manage.py loaddata initial_data.json   # demo fixture
python manage.py seed_categorias              # seeds CategoriaGasto for apps.costos
python manage.py createsuperuser
python cargar_demo.py                         # loads demo catalog/stock data
python diagnostico_impresora.py               # standalone thermal-printer connectivity check
python manage.py test apps.facturacion        # 117 tests
python manage.py verificar_fiscal             # diagnóstico de la configuración fiscal
```

Test coverage is **partial**: `apps/facturacion/` has a full suite (117 backend tests) and the contextual help has 22 frontend tests (`cd frontend && npm test`, vitest + jsdom). Everything else has no automated tests — verify those changes manually against `docs/checklist_entrega.md` (59 functional test cases).

### Frontend (from `frontend/`)
```
npm run dev       # Vite dev server, binds 0.0.0.0:5173 so tablets can reach it over WiFi
npm run build
npm run preview
npm test          # vitest run — tests de la ayuda contextual
npm run test:watch
```
No lint script is configured in `package.json`.

### One-click scripts (repo root, Windows)
- `setup.bat` — first-time install: venv, pip install, migrate, seed_categorias, createsuperuser, npm install
- `iniciar.bat` — launches daphne (backend) and `npm run dev` (frontend) each in their own window

## Architecture

### Django apps (`backend/apps/`)
- **usuarios** — custom `Usuario` model (`AUTH_USER_MODEL`), no separate `is_active` flag (uses `activo`). Role-based access, not Django groups/permissions: roles are `admin`, `encargada_ventas`, `vendedor`, `cajero`, `deposito`. All authorization goes through hand-written permission classes in `apps/usuarios/permissions.py` (`EsAdmin`, `EsAdminOVendedor`, `PermisosPorAccion`, etc.) — check that file before adding a new endpoint rather than inventing ad hoc role checks.
- **productos** — catalog: `Categoria` → `Producto` → `Variante` (the actual sellable unit, one SKU each) → `ImagenProducto`/`ImagenVariante`. `Producto.codigo` and `Variante.sku` are auto-generated in `save()` with collision-retry loops (see `_generar_codigo`/`_generar_sku`) — don't set them manually except in tests/fixtures. `m2_por_caja` can be entered directly or derived from dimensions; `Variante.clean()` cross-validates the two.
- **inventario** — `Stock` is one-to-one with `Variante` and is auto-created via a `post_save` signal on `Variante`. **Never mutate `Stock.cantidad`/`cantidad_reservada` directly** — always go through `Stock.registrar_movimiento(tipo, cantidad, usuario, ...)`, which writes the paired immutable `MovimientoStock` audit row in the same transaction. `cantidad_disponible = cantidad - cantidad_reservada`.
- **ventas** — `NotaPedido` (order) owns the stock lifecycle end-to-end: `reservar_stock()` on creation, `liberar_stock()` on cancel, `descontar_stock()` on payment confirmation (called from `apps.caja`). All three are `@transaction.atomic` and use `select_for_update()` to prevent overselling across concurrent vendedores. Order states: `pendiente → en_preparacion → listo → pagado` (or `cancelado`). Real-time updates go over Channels: `PedidoConsumer` (room `pedido_<id>`) and `RolConsumer` (room `rol_<rol>`) in `apps/ventas/consumers.py`; stock-critical alerts are pushed to `rol_admin`/`rol_deposito` from `_emitir_alerta_stock()` in `ventas/models.py`.
- **caja** — `SesionCaja` (one open session per cajero, enforced by a `UniqueConstraint`) and `Pago`. Confirming a `Pago` is what triggers `NotaPedido.descontar_stock()` and ticket printing. `printer.py` builds raw ESC/POS byte sequences (`TicketBuilder`, `FacturaBuilder`, `TicketCierreBuilder`) and sends them via `win32print` (Windows-only; falls back to a "simulado" no-op off Windows) — see the file's own architecture notes when touching ticket formatting.
- **costos** — gastos operativos, proveedores, empleados, pedidos a proveedores. Independent of the sales/stock flow; admin-only in the frontend.

### WebSocket wiring
`config/asgi.py` merges `apps.ventas.routing` + `apps.caja.routing` (currently empty) into one `URLRouter` under `AuthMiddlewareStack`. Channel layer is `InMemoryChannelLayer` (settings.py notes the Redis swap for production, not yet wired). Any new real-time feature should reuse the existing room-naming convention (`pedido_<id>`, `rol_<rol>`) rather than inventing new consumers unless it's a genuinely separate concern.

### Auth
JWT via `djangorestframework-simplejwt`, 8h access / 7d refresh, rotating refresh tokens. Frontend stores tokens in `zustand` (`authStore.js`, persisted to `localStorage` under key `ceramica-auth`); `services/api.js` has both a request interceptor (attaches the token) and a response interceptor (auto-refreshes once on 401, then hard-redirects to `/login` if refresh also fails).

### Frontend structure (`frontend/src/`)
- `pages/` — one page per module, gated by `<ProtectedRoute roles={[...]}>` in `App.jsx`. Route roles must be kept in sync with the backend permission classes for the same resource.
- `services/api.js` — single axios instance + per-domain API objects (`productosApi`, etc.). Base URL is derived from `window.location.hostname` at runtime (not hardcoded), so the same build works from `localhost`, the server PC, or any tablet IP without recompiling — preserve this pattern in new API/WS code (see `hooks/usePedidoSocket.js` for the WS equivalent).
- `hooks/useDevice.js` — breakpoints tuned specifically for the Redmi Pad SE tablets this store actually uses; `useSwipe` for touch gestures.
- `hooks/usePedidoSocket.js` — WebSocket hook with exponential backoff reconnect (2s→30s cap); invalidates/updates the matching React Query cache entries on message.
- PWA: `vite-plugin-pwa` in `vite.config.js` caches the app shell but **never** caches `/api/*` (`NetworkOnly`) — stock/pedidos/caja data must always be live; `/media/*` images use `StaleWhileRevalidate`. Keep this split when touching the Workbox config.

### Multi-machine deployment model
Three roles, documented in `docs/pwa_tablet.md` and `docs/sync_notebook.md`:
1. **Server PC** — runs Postgres + daphne + Vite dev server; `ALLOWED_HOSTS=*` and `CORS_ALLOW_ALL_ORIGINS` are intentionally permissive (LAN-only appliance, not internet-facing).
2. **Tablets** — install the frontend as a PWA over `http://<server-ip>:5173`; always call the live API.
3. **Owner's notebook** — runs its own local Postgres, one-way mirrored from the server every 5 min via `pg_dump`/`psql` + Windows Task Scheduler (`sync_notebook/`). It is read-only in practice: anything written there is overwritten on the next sync, never pushed back.

Keep this asymmetry in mind — code should never assume every client can write to a single shared DB.
