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

## 2026-08-05 — Reportes en PDF: tamaño de hoja A4/Oficio + corrección de desborde

**Commit:** sin commitear aún (ver `git status`) — pendiente de confirmar
mensaje con el usuario.

- **Agregado:** `render_pdf()` en `backend/apps/caja/reportes.py` ahora
  acepta `tamanio='a4'|'oficio'` (Oficio = 8.5×13", no está en
  `reportlab.lib.pagesizes`, se define a mano). Propagado desde
  `responder_reporte()` → las tres vistas de reporte (`?tamano=oficio` en
  la URL) → selector "Hoja (PDF)" agregado en `PanelReportes.jsx`.
- **Corregido (bug real, no solo la feature pedida):** las tablas de los
  reportes no tenían `colWidths`, así que reportlab nunca envolvía el
  texto — con nombres largos de producto/cliente la tabla se desbordaba de
  la hoja en vez de wrappear. Ahora cada celda es un `Paragraph` con ancho
  calculado (columnas numéricas angostas a la derecha, el resto reparte el
  ancho disponible).
- **Corregido (bug de seguridad/robustez):** el texto libre (nombre de
  producto, cliente) iba directo a `Paragraph`, que interpreta su contenido
  como markup tipo XML — un nombre con `&`, `<` o `"` rompía la generación
  del PDF. Verificado con un caso de prueba real
  (`Sanitario <Blanco> "Standard"`) antes del fix; ahora todo pasa por
  `xml.sax.saxutils.escape`.
- Se agregó pie de página (marca + número de página) para reportes largos.

---

## 2026-08-05 — Carga del catálogo real (facturas de compra + fotos)

**Commit:** sin commitear aún.

A pedido del usuario, se analizaron 97 fotos de la carpeta
`Referencias de Productos/` (en la raíz del repo, fuera de `backend/`) —
en su mayoría fotos de al menos 6 facturas de compra de "JS Comercial
S.R.L." fotografiadas página por página, más fotos de referencia de
producto con código/tamaño sobreimpreso, y capturas de catálogo de otro
proveedor (kits de baño SiderAgro).

- Se transcribió la mercadería facturada a
  `backend/data_carga/referencias_productos.csv` (código proveedor,
  categoría, color, dimensión, cantidad comprada, costo, precio de venta
  con margen ×1.4 acordado con el usuario).
- Comando nuevo `backend/apps/productos/management/commands/
  cargar_referencias_productos.py` (idempotente, `--dry-run` disponible):
  crea `Categoria → Producto → Variante → Stock` (entrada inicial vía
  `Stock.registrar_movimiento`, nunca tocando `cantidad` directo).
  **Ejecutado**: 84 productos nuevos cargados sobre los 18 de demo
  (102 total).
- 7 ítems de las fotos (2 inodoros Araxa, nivelador de piso, adhesivo Cola
  Bem) se dejaron **sin cargar a propósito** — ninguna foto traía precio y
  el modelo exige `precio_base > 0`. Quedan documentados en el CSV como
  `PENDIENTE precio`.
- Segundo comando `vincular_imagenes_referencia.py` +
  `data_carga/mapeo_imagenes.csv`: vincula cada foto como `ImagenProducto`.
  **Ejecutado dos veces** (primera pasada con códigos verificados
  re-leyendo cada imagen; segunda pasada incorporando las correcciones de
  agrupamiento que dio el usuario tras revisar el artifact de checklist
  visual que se le generó). Resultado final: **90 imágenes vinculadas a 60
  de los 84 productos**. Los 24 sin foto son productos sin ninguna
  candidata clara en la carpeta (bachas de acero inoxidable, inodoro
  Aveiro, y varias líneas de piso 60×60/45×45 de las últimas dos facturas
  de las que no se encontró foto de referencia) — se cargaron sin imagen,
  a pedido explícito del usuario, sin bloquear la entrega.
- **Bug propio detectado y corregido en el momento:** 5 variantes de
  "Porcelanato Inout Speciale 74×74" (mismo nombre de `Producto`, distinto
  color) se estaban tratando como duplicadas por el chequeo de
  idempotencia (`Producto.objects.filter(nombre=nombre)`) — solo se creó 1
  de 5. Corregido embebiendo el color en el nombre antes de re-correr.
  También se corrigió el chequeo de idempotencia de imágenes: Django
  sanitiza paréntesis del nombre de archivo al guardarlo
  (`WA0062(1).jpg` → `WA00621.jpg`), lo que rompía la comparación por
  nombre exacto y hubiera re-subido la misma foto en una segunda corrida.

---

## 2026-08-05 — Puesta en red para prueba con tablet + preparación del espejo de la notebook

- Backend (`daphne -b 0.0.0.0 -p 8000`) y frontend (`npm run dev`, ya
  bindeado a `0.0.0.0` por `vite.config.js`) corriendo para prueba real
  desde tablet. **IP de esta PC en la sesión de prueba:** `192.168.100.34`
  — va a cambiar en la PC servidor real del local, no asumir que se
  mantiene.
- **Cambio fuera del repo, no versionado por git — anotar para no
  perderlo:** se editó `C:\Program Files\PostgreSQL\17\data\pg_hba.conf`
  agregando una línea `host ceramica_db notebook_sync 192.168.100.0/24
  scram-sha-256` para permitir la sync de la notebook (`docs/
  sync_notebook.md`). `listen_addresses='*'` ya estaba puesto de antes.
  **Falta:** crear el rol `notebook_sync` y correr `SELECT
  pg_reload_conf();` — se necesita la contraseña del superusuario
  `postgres`, que no se compartió en esta sesión. El comando exacto para
  cuando se retome está en la conversación (`CREATE ROLE notebook_sync
  WITH LOGIN PASSWORD '...'; GRANT CONNECT ON DATABASE ceramica_db TO
  notebook_sync; GRANT pg_read_all_data TO notebook_sync;`).
- Para esta prueba puntual se optó por **no** esperar la sync automática:
  se generó un volcado (`pg_dump -Fc`) en
  `backend/data_carga/dump_notebook/ceramica_db.dump` para restaurar una
  copia congelada de hoy directo en la notebook (`pg_restore`), en paralelo
  a copiar `backend/media/` (el dump no incluye archivos de imagen, solo
  la ruta guardada en la fila de la BD).
- Se creó el usuario `Administrador` / rol `admin` (contraseña definida
  por el usuario) para el login de prueba desde tablet. **Pendiente antes
  de la entrega real:** rotar esa contraseña y confirmar si la va a usar
  la propietaria tal cual o se crea una cuenta separada para ella.
- **Nota operativa de esta sesión de prueba (no es bug del repo):** al
  lanzar `daphne` como comando en segundo plano del propio tool de shell,
  el proceso se cortó solo dos veces sin dejar error en el log (`status:
  killed`, no un crash). Se resolvió lanzándolo como proceso desatachado
  de Windows (`Start-Process` de PowerShell) en vez de un job de fondo del
  shell. Si vuelve a pasar en la próxima sesión, probar directamente con
  ese método en vez de perder tiempo reintentando el mismo camino.

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
4. **`DEBUG=True`** en `backend/.env` — bien para esta sesión de prueba,
   cambiar a `False` antes de la entrega real al cliente.
5. **7 productos cargados sin precio** (2 inodoros Araxa, nivelador de
   piso ×3 tamaños, adhesivo Cola Bem) — ver
   `backend/data_carga/referencias_productos.csv`, filas marcadas
   `PENDIENTE precio`. Completar precio y volver a correr
   `cargar_referencias_productos` (es idempotente, no duplica lo ya
   cargado).
6. **24 de los 84 productos cargados hoy no tienen foto** — ver el detalle
   en la memoria/artifact de esta sesión; algunos necesitan que se les
   saque una foto nueva (bachas de acero inoxidable, inodoro Aveiro), otros
   simplemente no tenían foto de referencia en la carpeta entregada.
7. **Rol `notebook_sync` sin crear** — ver la entrada de arriba
   ("Puesta en red..."). Bloqueado en la contraseña del superusuario
   `postgres` de esta PC.
8. **Contraseña del usuario `Administrador`** creada en esta sesión —
   rotar antes de la entrega si va a quedar como cuenta real de uso diario.

---

## Cómo continuar la próxima sesión

- Verificar que `frontend/dist` esté actualizado si se toca cualquier
  archivo de `frontend/src` (correr `npm run build` en `frontend/`).
- Antes de commitear, correr `python manage.py check` en `backend/` y
  `npx vite build` en `frontend/` — ambos deben pasar sin errores.
- Revisar la lista de "Pendientes conocidos" arriba antes de buscar
  hallazgos nuevos, para no repetir análisis ya hecho.
- Hay trabajo sin commitear de la sesión del 2026-08-05 (reportes A4/Oficio
  + carga de catálogo + `CLAUDE.md` nuevo) — confirmar con el usuario el
  mensaje de commit antes de tocarlo, no asumir que ya se guardó.
