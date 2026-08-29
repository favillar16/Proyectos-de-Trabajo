# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Sistema de gestión comercial for a flooring/ceramics/sanitary-ware store in Paraguay ("Oga Porã"). Runs on a local WiFi network with **no internet dependency** — one PC acts as the server, sales staff use tablets, and the owner's notebook keeps a mirror that is read-only for stock/sales/caja but can edit the catalogue and push it back (see `docs/sync_bidireccional.md`). Stack: Django 4.2 + DRF + Channels (ASGI/WebSocket) + PostgreSQL 15, React 18 + Vite frontend, PWA-installable on Android tablets.

All user-facing text, model fields, and comments are in Spanish — keep new code consistent with that.

## Commands

### Backend (from `backend/`)
```
venv\Scripts\activate
python manage.py runserver              # HTTP only — no WebSocket support
daphne -e tcp:8000:interface=0.0.0.0 -e tcp6:8000:interface=\:\: config.asgi:application   # full app (HTTP+WS). Los dos endpoints hacen falta: los nombres de red resuelven primero a IPv6
python manage.py makemigrations usuarios productos inventario ventas caja costos facturacion sync
# las etiquetas de app son cortas ("productos"), no "apps.productos"
python manage.py migrate
python manage.py loaddata initial_data.json   # demo fixture
python manage.py seed_categorias              # seeds CategoriaGasto for apps.costos
python manage.py createsuperuser
python cargar_demo.py                         # loads demo catalog/stock data
python diagnostico_impresora.py               # standalone check of the thermal printer
python manage.py test apps                    # facturación, productos, caja, nota de presupuesto/pedido, sync
python manage.py test --settings=config.settings_test   # los mismos sin Postgres (SQLite; saltea 1 de concurrencia)
python manage.py cargar_lote_facturas --margen 40 --dry-run   # lote de agosto 2026 (docs/carga_final/)
python manage.py migrate --database=sync      # la base del registro de cambios del sync (SQLite aparte)
python manage.py sync_estado                  # diagnóstico de la sincronización
python manage.py sync_empujar --servidor ogapora.local   # manda al servidor lo editado acá
python manage.py sync_comparar --servidor ogapora.local  # diferencias de catálogo entre los dos equipos
python manage.py verificar_fiscal             # diagnóstico de la configuración fiscal
```

Test coverage is **partial**: 151 backend tests (`apps/facturacion/` full suite, plus `apps/productos/tests/`, `apps/ventas/tests/` and `apps/sync/tests/` for the bidirectional sync) and 22 frontend tests (`cd frontend && npm test`, vitest + jsdom — contextual help). Everything else has no automated tests — verify those changes manually against `docs/checklist_entrega.md`.

### Frontend (from `frontend/`)
```
npm run dev       # Vite dev server, binds :: (IPv4+IPv6) on 5173 so tablets and hostnames both reach it
npm run build
npm run preview
npm test          # vitest run — ayuda contextual
npm run test:watch
```
No lint script is configured in `package.json`.

### One-click scripts (repo root, Windows)
- `setup.bat` — first-time install: venv, pip install, migrate, seed_categorias, createsuperuser, npm install
- `iniciar.bat` — launches daphne (backend) and `npm run dev` (frontend) each in their own window

## Architecture

### Django apps (`backend/apps/`)
- **usuarios** — custom `Usuario` model (`AUTH_USER_MODEL`), no separate `is_active` flag (uses `activo`). Role-based access, not Django groups/permissions: roles are `admin`, `encargada_ventas`, `vendedor`, `cajero`, `deposito`. All authorization goes through hand-written permission classes in `apps/usuarios/permissions.py` (`EsAdmin`, `EsAdminOVendedor`, `PermisosPorAccion`, etc.) — check that file before adding a new endpoint rather than inventing ad hoc role checks.
- **productos** — catalog: `Categoria` → `Producto` → `Variante` (the actual sellable unit, one SKU each) → `ImagenProducto`/`ImagenVariante`. `Producto.codigo` and `Variante.sku` are auto-generated in `save()` with collision-retry loops (see `_generar_codigo`/`_generar_sku`) — don't set them manually except in tests/fixtures. `m2_por_caja` can be entered directly or derived from dimensions; `Variante.clean()` cross-validates the two. `Variante.codigo_barras` still exists as a column but **the barcode system was retired on 2026-08-26**: the scanner, the internal EAN generator, the label sheets and all the UI are gone. The column was deliberately left in place (no destructive migration) so the codes already loaded survive if the business ever picks it back up — nothing reads or writes it today, and it is exposed neither through the API nor the admin. If it is ever revived, note it is `unique=True` **and nullable**: `Variante.save()` still stores an empty code as `NULL` rather than `''`, so a query for "no barcode" must use `__isnull=True`. Migration `0005_variante_codigo_barras` is **not** a plain `AddField` — it was rewritten on 2026-08-27 as a `SeparateDatabaseAndState` because the store's database already had the column in the shape of the *other* (discarded) scanner implementation, `varchar(32) NOT NULL` with a partial unique index. That mismatch made every `Variante` insert fail with a not-null violation. The migration now adds the column on a fresh database and reconciles it on an existing one; read its header before touching it.

  Bulk catalog loads have two commands, one per CSV shape: `cargar_referencias_productos` (`backend/data_carga/referencias_productos.csv`, carries its own `precio_base`) and `cargar_lote_facturas` (`docs/carga_final/productos_a_cargar.csv`, cost-only — it **requires** a `--margen` to derive the sale price, groups rows sharing `nombre_producto` into one `Producto` with one `Variante` per colour, and its `--dry-run` runs the real path inside a rolled-back transaction so validation errors surface before the real load).
- **inventario** — `Stock` is one-to-one with `Variante` and is auto-created via a `post_save` signal on `Variante`. **Never mutate `Stock.cantidad`/`cantidad_reservada` directly** — always go through `Stock.registrar_movimiento(tipo, cantidad, usuario, ...)`, which writes the paired immutable `MovimientoStock` audit row in the same transaction. `cantidad_disponible = cantidad - cantidad_reservada`.
- **ventas** — `NotaPedido` (order) owns the stock lifecycle end-to-end: `reservar_stock()` on creation, `liberar_stock()` on cancel, `descontar_stock()` on payment confirmation (called from `apps.caja`). All three are `@transaction.atomic` and use `select_for_update()` to prevent overselling across concurrent vendedores. Order states: `pendiente → en_preparacion → listo → pagado` (or `cancelado`). Real-time updates go over Channels: `PedidoConsumer` (room `pedido_<id>`) and `RolConsumer` (room `rol_<rol>`) in `apps/ventas/consumers.py`; stock-critical alerts are pushed to `rol_admin`/`rol_deposito` from `_emitir_alerta_stock()` in `ventas/models.py`.

  `nota_pedido_doc.py` renders a pedido as the customer-facing note — PDF (reportlab canvas) and Excel (openpyxl), served from `GET /api/v1/ventas/pedidos/<pk>/nota/?formato=pdf|xlsx&tipo=presupuesto|pedido`. `tipo` only swaps the heading (`TITULOS`); `presupuesto` is the default because that is what the store hands a customer before the sale closes. The PDF geometry (`COLS`, `TABLA_TOP`, `FOOTER_H`, …) was measured off the document the store already used (`docs/Ejemplos Nota de Pedido/`) — those constants are not free parameters. The two *formats* are deliberately different documents: the PDF matches the original four-column layout, the Excel splits the unit into its own column and leaves TOTAL as a formula plus blank rows so it stays editable. Brand assets live in `apps/ventas/assets/`, both tinted `#B99C74` (the brand brown, sampled off the original note and the same accent the React UI uses): `logo_oga_pora.png` for the header and `logo_marca.png` — the monogram alone — for the footer watermark. Regenerate them from `docs/Ejemplos Nota de Pedido/OP NEGRO.jpeg` if the logo ever changes. The footer contact comes from `settings.CONTACTO_COMERCIAL`, **not** from `DATOS_FISCALES` — the phone/address given to a customer on a quote differ from the ones registered with the DNIT.
- **caja** — `SesionCaja` (one open session per cajero, enforced by a `UniqueConstraint`) and `Pago`. Confirming a `Pago` is what triggers `NotaPedido.descontar_stock()` and ticket printing. `printer.py` builds raw ESC/POS byte sequences (`TicketBuilder`, `FacturaBuilder`, `TicketCierreBuilder`) and sends them via `win32print` (Windows-only; falls back to a "simulado" no-op off Windows) — see the file's own architecture notes when touching ticket formatting. The Epson EcoTank L1250 that used to print the barcode label sheets was removed along with the barcode system — the thermal printer is the only one wired up, and the fiscal document will get its own. See `docs/perifericos.md`.
- **sync** — sincronización bidireccional del catálogo con la notebook. Sus tablas viven en una SQLite aparte (`sync.sqlite3`, router en `apps/sync/routers.py`) porque el restore del `pg_dump` borra `ceramica_db` entera. Los modelos sincronizables heredan de `ModeloSincronizable` (`uid` UUID + `actualizado_en` + `nodo_origen`); las PK siguen siendo enteras y el `uid` es identidad **aparte**, solo para el sync. Al agregar un modelo al alcance hay que sumarlo a `apps/sync/registro.py` **en orden de dependencias** (la categoría antes que el producto) y decidir en `apps/sync/conciliacion.py` si un choque de unicidad se fusiona o se regenera. Ver `docs/sync_bidireccional.md`.
- **costos** — gastos operativos, proveedores, empleados, pedidos a proveedores. Independent of the sales/stock flow; admin-only in the frontend.

### WebSocket wiring
`config/asgi.py` merges `apps.ventas.routing` + `apps.caja.routing` (currently empty) into one `URLRouter` under `JWTAuthMiddleware` (`apps/usuarios/ws_auth.py`) — **not** Channels' `AuthMiddlewareStack`, which expects a session cookie the JWT frontend never sends. The token travels as a `?token=` query param (see `hooks/usePedidoSocket.js`); consumers reject `AnonymousUser` with close code 4401. Channel layer is `InMemoryChannelLayer` (settings.py notes the Redis swap for production, not yet wired). Any new real-time feature should reuse the existing room-naming convention (`pedido_<id>`, `rol_<rol>`) rather than inventing new consumers unless it's a genuinely separate concern.

### Auth
JWT via `djangorestframework-simplejwt`, 8h access / 7d refresh, rotating refresh tokens. Frontend stores tokens in `zustand` (`authStore.js`, persisted to `localStorage` under key `ceramica-auth`); `services/api.js` has both a request interceptor (attaches the token) and a response interceptor (auto-refreshes once on 401, then hard-redirects to `/login` if refresh also fails).

### Frontend structure (`frontend/src/`)
- `pages/` — one page per module, gated by `<ProtectedRoute roles={[...]}>` in `App.jsx`. Route roles must be kept in sync with the backend permission classes for the same resource.
- `services/api.js` — single axios instance + per-domain API objects (`productosApi`, etc.). Base URL is derived from `window.location.hostname` at runtime (not hardcoded), so the same build works from `localhost`, the server PC, or any tablet IP without recompiling — preserve this pattern in new API/WS code (see `hooks/usePedidoSocket.js` for the WS equivalent).
- `hooks/useDevice.js` — breakpoints tuned specifically for the Redmi Pad SE tablets this store actually uses; `useSwipe` for touch gestures.
- `hooks/usePedidoSocket.js` — WebSocket hook with exponential backoff reconnect (2s→30s cap); invalidates/updates the matching React Query cache entries on message.
- PWA: `vite-plugin-pwa` in `vite.config.js` caches the app shell but **never** caches `/api/*` (`NetworkOnly`) — stock/pedidos/caja data must always be live; `/media/*` images use `StaleWhileRevalidate`. Keep this split when touching the Workbox config.

### Descubrimiento de red
Nada guarda una IP: el servidor se busca por nombre (`ogapora.local` / `ogapora`), por el último conocido, y si hace falta barriendo la subred, confirmando siempre con `GET /api/v1/salud/`. Dos trampas ya resueltas que conviene no reintroducir: los nombres resuelven **primero a IPv6**, así que daphne arranca con dos endpoints (`-e tcp:...` y `-e tcp6:...`) y Vite usa `host: '::'`; y Vite 5.4.12+ rechaza los hostnames con 403 salvo `server.allowedHosts`. Ver `docs/descubrimiento_red.md`.

### Multi-machine deployment model
Three roles, documented in `docs/pwa_tablet.md` and `docs/sync_notebook.md`:
1. **Server PC** — runs Postgres + daphne + Vite dev server; `ALLOWED_HOSTS=*` and `CORS_ALLOW_ALL_ORIGINS` are intentionally permissive (LAN-only appliance, not internet-facing).
2. **Tablets** — install the frontend as a PWA over `http://<server-ip>:5173`; always call the live API.
3. **Owner's notebook** — runs its own local Postgres. Every 5 min (`sync_notebook/` + Windows Task Scheduler) it **first pushes** the catalogue edits made there (`manage.py sync_empujar` → the server's `/api/v1/sync/` endpoints) and **then** pulls the whole server DB with `pg_dump`/`psql`, which replaces `ceramica_db` wholesale. That order is not negotiable: the restore wipes the DB, so pushing afterwards would push what the restore already overwrote.
   Only the catalogue is bidirectional. Stock, ventas, caja and facturación stay server-authoritative — a running balance and a comprobante sequence cannot be merged (`docs/sync_bidireccional.md` explains why).
   The change log lives in `backend/sync.sqlite3`, **outside** `ceramica_db` on purpose, so it survives the restore (`apps/sync/routers.py`).

Keep this asymmetry in mind — code should never assume every client can write to a single shared DB.
