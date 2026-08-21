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

Completado el 20–21/08/2026 en la PC servidor (`DESKTOP-Q9T1TPI`):
instalación base, migración de datos (393 productos, 425 variantes, 338
fotos, 5 usuarios, 414 movimientos — verificado exacto), fix del bug de
fotos con `DEBUG=False` (commit `fec3ded`, ya en `main`). Detalle completo
en `docs/todo_montaje_servidor.md`.

---

## 1. PC Servidor (esto primero, todo depende de esto)

- [ ] Marcar la red WiFi como **Privada**, no Pública (PowerShell como
      Administrador):
      ```powershell
      Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private
      ```
- [ ] Abrir los puertos del firewall (misma ventana de Administrador):
      ```powershell
      New-NetFirewallRule -DisplayName "Oga Pora - Frontend (5173)" -Direction Inbound -Protocol TCP -LocalPort 5173 -Action Allow -Profile Private
      New-NetFirewallRule -DisplayName "Oga Pora - Backend (8000)" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
      ```
- [ ] **Reservar la IP de esta PC en el router** (DHCP → reserva por MAC) —
      `guia_instalacion_dispositivos.md` §2. Evita tener que reconfigurar
      todos los demás equipos si el router se reinicia.
- [ ] Anotar acá la IP definitiva: `____________________`
- [ ] Anotar el hostname (`hostname` en PowerShell): `____________________`
- [ ] **Cambiar la contraseña del usuario `admin`** — hoy es `demo2025`
      (la credencial de demo, heredada sin rotar del equipo de armado). No
      operar el negocio real con esa contraseña puesta.
- [ ] Correr `iniciar.bat` y confirmar que abre sin errores en las dos
      ventanas (daphne + Vite)
- [ ] Desde OTRO equipo en la misma red, probar:
      ```powershell
      Test-NetConnection -ComputerName <IP-SERVIDOR> -Port 5173
      Test-NetConnection -ComputerName <IP-SERVIDOR> -Port 8000
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
- [ ] Habilitar conexiones remotas de PostgreSQL: `listen_addresses = '*'`
      en `postgresql.conf` + línea para la subred del local en
      `pg_hba.conf` (`sync_notebook.md` §1.1). Reiniciar el servicio.
- [ ] Crear el rol de solo lectura para el sync:
      ```sql
      CREATE ROLE notebook_sync WITH LOGIN PASSWORD 'elegir-una-contraseña-fuerte';
      GRANT CONNECT ON DATABASE ceramica_db TO notebook_sync;
      GRANT pg_read_all_data TO notebook_sync;
      ```
      Anotar la contraseña elegida — se usa abajo.
- [ ] Compartir `backend\media` en red (solo lectura) para que las fotos no
      salgan rotas en la notebook (`sync_notebook.md` §1.3). Anotar la ruta
      resultante, ej. `\\DESKTOP-Q9T1TPI\media`.

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
        agregar `http://<IP-SERVIDOR>:5173` → Enabled → Relaunch
  - [ ] Entrar a `http://<IP-SERVIDOR>:5173`, confirmar que carga el login
  - [ ] Menú (⋮) → **Instalar aplicación** → confirmar
  - [ ] Abrir el ícono "Oga Porã" instalado y confirmar que carga igual
        que en Chrome
  - [ ] Probar una vez `http://<HOSTNAME-SERVIDOR>.local:5173` (plan B) —
        anotar si esta red lo resuelve o no, para no perder tiempo con
        esto el día que haga falta de apuro
- [ ] **Tablet 2:** repetir los mismos 5 pasos

---

## 4. PC Caja — ~10 minutos

Checklist completo con el detalle de la impresora: `docs/pc_caja.md`.

- [ ] Confirmar red: `Test-NetConnection -ComputerName <IP-SERVIDOR> -Port 5173`
- [ ] Chrome → `http://<IP-SERVIDOR>:5173` → iniciar sesión con usuario
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

- [ ] Confirmar red: `Test-NetConnection -ComputerName <IP-SERVIDOR> -Port 5173`
- [ ] Chrome → `http://<IP-SERVIDOR>:5173` → iniciar sesión con usuario
      **`deposito`**
- [ ] Crear acceso directo "Abrir como ventana"

---

## 6. Verificación final (con todos los equipos prendidos)

- [ ] Correr el checklist funcional completo: `docs/checklist_entrega.md`
      (59 casos)
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
| `guia_instalacion_dispositivos.md` | Topología de los 6 equipos y orden completo |
| `sync_notebook.md` | Detalle completo del espejo de la notebook |
| `pwa_tablet.md` | Instalación y diagnóstico de tablets |
| `pc_caja.md` | Puesto de caja e impresora compartida |
| `verificacion_red.md` | Diagnóstico de red por capas |
| `checklist_entrega.md` | 59 casos funcionales de prueba |
| `todo_montaje_servidor.md` | Registro general de qué queda pendiente |
