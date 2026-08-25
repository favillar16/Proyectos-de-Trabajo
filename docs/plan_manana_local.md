# Plan para mañana en el local — 22/08/2026

Checklist del día del armado final, con las tareas de cada equipo por
separado para poder repartirlas entre varias personas si hace falta. Da por
sentado que la PC servidor ya está armada (ver estado abajo) y que el
objetivo de mañana es dejar los otros 5 equipos operativos y hacer la
verificación final en el local.

**Orden recomendado** (cada paso depende del anterior):
1. PC Servidor — red y verificación
2. Notebook de la propietaria — necesita al servidor accesible para el
   paso único de crear `notebook_sync`
3. Tablets (2)
4. PC Caja y PC Depósito
5. Verificación final con todos los equipos prendidos a la vez

---

## Ya hecho (no repetir)

Completado el 20–21/08/2026 en la PC servidor (`OGAPORA`, antes `DESKTOP-Q9T1TPI`):
instalación base, migración de datos (393 productos, 425 variantes, 338
fotos, 5 usuarios, 414 movimientos — verificado exacto), fix del bug de
fotos con `DEBUG=False` (commit `fec3ded`, ya en `main`). Detalle completo
en `docs/todo_montaje_servidor.md`.

---

## 1. PC Servidor (esto primero, todo depende de esto)

- [ ] **Doble clic en `preparar_red.bat`** (en la raíz del proyecto) y aceptar
      el aviso de Administrador. Deja hecho de una sola vez:
      red del local marcada como **Privada**, puertos **5173**, **8000** y **5432**
      abiertos en el firewall, **suspensión desactivada** (un servidor
      dormido deja sin sistema a caja, depósito y tablets), carpeta
      `backend\media` compartida en solo lectura para la notebook, y
      PostgreSQL aceptando conexiones de `192.168.100.0/24`.
      Es idempotente: se puede volver a correr sin romper nada.
- [ ] **Doble clic en `fijar_ip.bat`** → IP fija `192.168.100.250`. No hay
      acceso al panel del router (Nokia del proveedor, sin clave), así que en
      vez de reservar la IP ahí se la fijamos a la PC. Elegida alta a
      propósito: el router reparte desde abajo y nunca llega a `.250`.
      Para revertir: `fijar_ip.bat deshacer`.
- [x] IP definitiva: `192.168.100.250` (Wi-Fi, red `OGA PORA`) — ya reflejada
      en `backend\.env`. MAC del Wi-Fi: `10-5A-95-76-C9-20`.
- [x] Hostname: `OGAPORA` (la PC se renombró; antes era `DESKTOP-Q9T1TPI`)
- [ ] **Cambiar las contraseñas de los usuarios** — al 21/08/2026 `admin`,
      `vendedor`, `cajero` y `deposito` **siguen todos con `demo2025`**
      (la credencial de demo, heredada sin rotar del equipo de armado). No
      se puede entregar el negocio así. Una por una, en el servidor:
      ```
      cd backend
      venv\Scripts\activate
      python manage.py changepassword admin
      ```
      (repetir con `cajero`, `deposito` y `vendedor`). Anotar las nuevas en
      un lugar seguro y dejárselas a la propietaria.
- [ ] Correr `iniciar.bat` y confirmar que abre sin errores en las dos
      ventanas (daphne + Vite)
- [ ] Desde OTRO equipo en la misma red, probar:
      ```powershell
      Test-NetConnection -ComputerName 192.168.100.250 -Port 5173
      Test-NetConnection -ComputerName 192.168.100.250 -Port 8000
      ```
      Los dos tienen que dar `TcpTestSucceeded : True`. Si falla, ver
      `docs/verificacion_red.md` (capas 1 y 2).

---

## 2. Notebook de la propietaria (la laptop)

Instrucciones completas: `docs/sync_notebook.md`. A diferencia de las PCs
de caja/depósito, esta lleva una instalación completa propia (Python, Node,
PostgreSQL, backend, frontend — igual que `docs/instalacion.md`), porque
tiene que poder mostrar datos aunque salga del local sin conexión.

**En el servidor (una sola vez):**
- [x] Conexiones remotas de PostgreSQL: `listen_addresses = '*'` ya estaba
      puesto y la línea de `192.168.100.0/24` en `pg_hba.conf` la agrega
      `preparar_red.bat` (punto 1). Verificar que quedó antes de seguir.
- [ ] Doble clic en `configurar_postgres.bat` (Administrador): le pone
      contraseña conocida al superusuario `postgres` y crea el rol de solo
      lectura `notebook_sync`, verificando que lea y que no escriba. Las dos
      contraseñas salen de `credenciales_servidor.txt` (ignorado por git).
- [x] Fotos: **nada que configurar**. Desde el 21/08/2026 el sync las baja
      por HTTP de `http://192.168.100.250:8000/media/` (`sync_notebook.md`
      §1.3). Dejar `SERVIDOR_MEDIA_UNC` y `SERVIDOR_MEDIA_URL` vacíos en
      `config.env`.

**En la notebook:**
- [ ] Instalación completa (Python 3.11, Node 20 LTS, PostgreSQL 15,
      `backend\.env` propio, base `ceramica_db` local vacía) — igual que
      `docs/instalacion.md`.
- [ ] Copiar `sync_notebook/config.env.example` → `config.env` y completar
      `SERVIDOR_HOST` (IP del servidor), `SERVIDOR_DB_PASSWORD` (la de
      `notebook_sync` de arriba), `LOCAL_DB_PASSWORD` (la del Postgres
      local de la notebook) y `SERVIDOR_MEDIA_UNC` (la ruta compartida de
      arriba).
- [ ] Doble clic en `sync_notebook/instalar_tarea_programada.bat`.
- [ ] Probar: `schtasks /run /tn "OgaPora - Sync Notebook"` y revisar
      `sync_notebook/estado/last_sync.json` → `"status": "ok"`.
- [ ] Confirmar que los productos se ven **con foto** en la notebook (no
      solo el catálogo).

**Importante para quien opere la notebook:** es un espejo de **solo
lectura** (servidor → notebook). No cargar ventas ahí — se pierden en el
próximo sync. Para operar la caja desde la notebook estando en el local,
usarla como una tablet más (punto 3), no contra su base local.

---

## 3. Tablets (2 unidades) — repetir en cada una

Instrucciones completas y diagnóstico: `docs/pwa_tablet.md`.

- [ ] **Tablet 1:**
  - [ ] `chrome://flags/#unsafely-treat-insecure-origin-as-secure` →
        agregar `http://192.168.100.250:5173` → Enabled → Relaunch
  - [ ] Entrar a `http://192.168.100.250:5173`, confirmar que carga el login
  - [ ] Menú (⋮) → **Instalar aplicación** → confirmar
  - [ ] Abrir el ícono "Oga Porã" instalado y confirmar que carga igual
        que en Chrome
  - [ ] Probar una vez `http://OGAPORA.local:5173` (plan B) —
        anotar si esta red lo resuelve o no, para no perder tiempo con
        esto el día que haga falta de apuro
- [ ] **Tablet 2:** repetir los mismos 5 pasos

---

## 4. PC Caja — ~10 minutos

Checklist completo con el detalle de la impresora: `docs/pc_caja.md`.

- [ ] Confirmar red: `Test-NetConnection -ComputerName 192.168.100.250 -Port 5173`
- [ ] Chrome → `http://192.168.100.250:5173` → iniciar sesión con usuario
      **`cajero`**
- [ ] Crear acceso directo "Abrir como ventana" (menú ⋮ → Más
      herramientas → Crear acceso directo)
- [ ] Conectar la impresora térmica **FTX FTXP-80W** por USB en esta PC,
      instalar driver, imprimir página de prueba de Windows
- [ ] Compartirla: Propiedades → **Compartir** → nombre sin espacios/acentos
      (ej. `TERMICA80`). Anotar: `\\NOMBRE-PC-CAJA\TERMICA80`
- [ ] **En el servidor:** agregar esa impresora compartida (Agregar
      impresora → "seleccionar una impresora compartida por nombre"), y
      poner en `backend\.env`:
      ```
      IMPRESORA_TERMICA_NOMBRE=\\NOMBRE-PC-CAJA\TERMICA80
      ```
      Reiniciar `iniciar.bat` para que tome el `.env` nuevo.
      ⚠️ La impresora debe quedar instalada para el **mismo usuario de
      Windows** que corre `iniciar.bat` en el servidor.
- [ ] Probar: en el servidor, `venv\Scripts\activate` +
      `python diagnostico_impresora.py`
- [ ] Prueba real: confirmar un pago desde la caja y verificar que el
      ticket sale solo

---

## 5. PC Depósito — ~2 minutos

- [ ] Confirmar red: `Test-NetConnection -ComputerName 192.168.100.250 -Port 5173`
- [ ] Chrome → `http://192.168.100.250:5173` → iniciar sesión con usuario
      **`deposito`**
- [ ] Crear acceso directo "Abrir como ventana"

---

## 6. Verificación final (con todos los equipos prendidos)

- [ ] Correr el checklist funcional completo: `docs/checklist_entrega.md`
      (85 casos)
- [ ] Prueba de tiempo real entre dispositivos: abrir un pedido en una
      tablet y dejarlo en pantalla, confirmar el pago en la PC de Caja, ver
      que la tablet lo pasa a `pagado` sola, **sin recargar**
      (`docs/verificacion_red.md` §2, capa 5)
- [ ] Prueba de arranque diario completo: apagar y prender todo en el orden
      real (servidor → caja/depósito → tablets), sin nada preconfigurado a
      mano (`guia_instalacion_dispositivos.md` §7)
- [ ] Hacer un respaldo fresco antes de irse del local:
      `respaldo\respaldo.bat D:\` (a un pendrive, no solo al disco del
      servidor)

---

## Queda para después (no es de mañana)

- Decisión de respaldo automático (A/B/C, recomendación B con `rclone`) —
  `docs/todo_montaje_servidor.md` §7. Hoy el respaldo existe pero hay que
  correrlo a mano.
- Actualizar `docs/todo_montaje_servidor.md` §8 punto 5 (queda desactualizado
  después del fix de `DEBUG=False`/`/media/` del commit `fec3ded`).

---

## Referencias

| Documento | Para qué |
|---|---|
| `instructivo_entrega_final.md` | Acciones manuales paso a paso para cerrar la entrega |
| `guia_instalacion_dispositivos.md` | Topología de los 6 equipos y orden completo |
| `sync_notebook.md` | Detalle completo del espejo de la notebook |
| `pwa_tablet.md` | Instalación y diagnóstico de tablets |
| `pc_caja.md` | Puesto de caja e impresora compartida |
| `verificacion_red.md` | Diagnóstico de red por capas |
| `checklist_entrega.md` | 85 casos funcionales de prueba |
| `todo_montaje_servidor.md` | Registro general de qué queda pendiente |
