# Instructivo — acciones manuales para la entrega final

Lo que **tenés que hacer vos a mano** en el local, en orden. Todo lo que se
podía automatizar ya está resuelto en `preparar_red.bat`. Cada paso dice cómo
verificar que salió bien antes de pasar al siguiente.

**Fecha:** 21/08/2026 · **Servidor:** `OGAPORA` · **Red:** WiFi `OGA PORA`

---

## Datos del servidor (tenerlos a mano)

| Dato | Valor |
|---|---|
| Nombre de la PC (hostname) | `OGAPORA` |
| IP actual | `192.168.100.16` (por DHCP) |
| MAC del adaptador WiFi | `10-5A-95-76-C9-20` |
| Router / puerta de enlace | `192.168.100.1` |
| Dirección del sistema | `http://192.168.100.16:5173` |
| API / backend | `http://192.168.100.16:8000` |
| Plan B por nombre | `http://OGAPORA.local:5173` |

---

## Paso 1 — Correr `preparar_red.bat` (5 minutos)

Es lo primero de todo: sin esto ningún otro equipo puede ver el sistema.

1. Ir a la carpeta del proyecto y hacer **doble clic en `preparar_red.bat`**.
2. Windows va a pedir permiso de Administrador → **Sí**.
3. Se abre una ventana azul que va mostrando `[OK]` en cada paso.
4. Al final imprime un resumen. **Confirmar que dice `Categoria red : Private`.**

Deja hecho, de una sola pasada:

- Red del local marcada como **Privada** (en Pública, Windows bloquea todo)
- Puertos **5173** y **8000** abiertos en el firewall
- **Suspensión desactivada** — venía configurado para dormirse a los 45 minutos
  de inactividad, y un servidor dormido deja sin sistema a caja, depósito y
  tablets
- Carpeta `backend\media` compartida en solo lectura (la usa la notebook para
  las fotos)
- `pg_hba.conf` con la subred del local + PostgreSQL reiniciado

Se puede volver a correr las veces que haga falta, no rompe nada.

> **Si sale rojo diciendo que necesita Administrador:** se abrió el `.ps1` en
> vez del `.bat`. Usar `preparar_red.bat`.

---

## Paso 2 — Reservar la IP en el router (10 minutos)

**Por qué:** hoy la IP `192.168.100.16` la da el router por DHCP y es prestada.
Si el router se reinicia o se corta la luz, puede darle otra — y ese día las
2 tablets, la PC de caja, la de depósito y la notebook dejan de encontrar el
sistema todas juntas, y hay que reconfigurarlas una por una. La reserva ata esa
IP a esta PC para siempre.

1. Desde cualquier PC del local, abrir Chrome y entrar a **`http://192.168.100.1`**
2. Iniciar sesión. Si nunca se cambió, la contraseña suele estar **en una
   etiqueta abajo o atrás del router** (`admin`/`admin`, `admin` + la clave
   impresa, etc.).
3. Buscar la sección de reservas DHCP. Según la marca se llama distinto:
   - **TP-Link:** Advanced → Network → DHCP Server → *Address Reservation*
   - **Huawei:** Más funciones → Configuración LAN → *Asignación estática/DHCP*
   - **Tenda / Nexxt:** Advanced → DHCP Reservation
   - **Mikrotik:** IP → DHCP Server → Leases → botón derecho → *Make Static*
   - Otras: buscar las palabras *"reserva"*, *"static lease"*, *"IP fija"* o
     *"vinculación IP-MAC"*
4. Agregar la reserva con estos dos datos exactos:
   - **MAC:** `10-5A-95-76-C9-20` (algunos routers la piden con `:` en vez de
     `-` → `10:5A:95:76:C9:20`, y otros sin nada → `105A9576C920`)
   - **IP:** `192.168.100.16`
5. Guardar. Si el router pide reiniciarse, dejarlo reiniciar.

**Verificar que quedó:** en el servidor, apagar y prender el WiFi (o reiniciar
la PC) y correr en PowerShell:

```powershell
ipconfig | findstr /i "IPv4"
```

Tiene que seguir diciendo `192.168.100.16`.

> **Si no hay acceso al router** (no aparece la contraseña): avisame y le
> ponemos IP fija a la PC en vez de reserva. Es plan B, no plan A: si el rango
> DHCP del router incluye esa IP, algún día se la puede dar a otro equipo y
> genera un conflicto.

---

## Paso 3 — Cambiar las contraseñas (10 minutos) ⚠️

**Esto es bloqueante para entregar.** Los cuatro usuarios del sistema —
`admin`, `vendedor`, `cajero` y `deposito` — están todos con la contraseña de
demostración `demo2025`, heredada del equipo de armado. Cualquiera que haya
visto la guía de demo entra como administrador.

En el servidor, abrir PowerShell **en la carpeta del proyecto** y correr:

```powershell
cd backend
venv\Scripts\activate
python manage.py changepassword admin
```

Pide la contraseña nueva dos veces (no se ve mientras se escribe, es normal).
Repetir el último comando cambiando el usuario:

```powershell
python manage.py changepassword cajero
python manage.py changepassword deposito
python manage.py changepassword vendedor
```

**Después:**

- Anotar las cuatro contraseñas en papel y dejárselas a la propietaria.
- La de `admin` es la más sensible: da acceso a costos, precios y a los datos
  de todos los usuarios.
- Probar entrar con una de ellas en `http://192.168.100.16:5173` antes de
  seguir.

---

## Paso 4 — Crear el usuario de la notebook (5 minutos)

Solo si hoy se va a configurar la notebook de la propietaria. Necesitás la
contraseña del usuario `postgres` (la que se puso al instalar PostgreSQL).

```powershell
& "C:\Program Files\PostgreSQL\15\bin\psql.exe" -U postgres -d ceramica_db
```

Y dentro de `psql`, pegar (cambiando la contraseña):

```sql
CREATE ROLE notebook_sync WITH LOGIN PASSWORD 'elegir-una-contrasena-fuerte';
GRANT CONNECT ON DATABASE ceramica_db TO notebook_sync;
GRANT pg_read_all_data TO notebook_sync;
\q
```

Anotar esa contraseña: se usa en `sync_notebook/config.env` de la notebook,
junto con la ruta de las fotos `\\OGAPORA\media` (esa carpeta ya la compartió
el paso 1). El detalle completo está en `docs/sync_notebook.md`.

---

## Paso 5 — Probar desde otro equipo (2 minutos)

Antes de ponerse a configurar tablets y puestos, comprobar que la red quedó
abierta. Desde **cualquier otra PC del local**, en PowerShell:

```powershell
Test-NetConnection -ComputerName 192.168.100.16 -Port 5173
Test-NetConnection -ComputerName 192.168.100.16 -Port 8000
```

Los dos tienen que decir `TcpTestSucceeded : True`.

⚠️ Para que esto funcione, **`iniciar.bat` tiene que estar corriendo en el
servidor** (las dos ventanas negras abiertas, daphne y Vite).

**Si da `False`:**

1. ¿Está corriendo `iniciar.bat` en el servidor?
2. ¿El paso 1 terminó bien? Volver a correr `preparar_red.bat`.
3. ¿Las dos PCs están en la misma red WiFi `OGA PORA` y no una en la de
   invitados? (algunos routers aíslan la red de invitados a propósito)
4. Diagnóstico por capas: `docs/verificacion_red.md`

---

## Paso 6 — Armar los 5 puestos

A partir de acá seguir el checklist por equipo, que ya tiene la IP y el nombre
del servidor puestos: **`docs/plan_manana_local.md`**

- Notebook de la propietaria (punto 2)
- Tablet 1 y Tablet 2 (punto 3) — incluye el `chrome://flags` y la instalación
  de la PWA
- PC Caja (punto 4) — incluye la impresora térmica
- PC Depósito (punto 5)

**De la impresora, lo que más se olvida:** el ticket lo imprime el **servidor**,
no la PC de caja. Después de compartir la impresora en la caja hay que
agregarla también en el servidor y poner en `backend\.env`:

```
IMPRESORA_TERMICA_NOMBRE=\\NOMBRE-PC-CAJA\TERMICA80
```

y reiniciar `iniciar.bat`. Detalle en `docs/pc_caja.md`.

---

## Paso 7 — Verificación final y respaldo

Con todos los equipos prendidos al mismo tiempo:

1. Correr el checklist funcional: `docs/checklist_entrega.md` (59 casos).
2. **Prueba de tiempo real:** dejar un pedido abierto en pantalla en una
   tablet, confirmar el pago desde la PC de caja, y ver que la tablet pasa el
   pedido a `pagado` **sola, sin recargar**. Si no cambia solo, el servidor
   está corriendo con `runserver` en vez de `daphne` — usar `iniciar.bat`.
3. **Prueba de arranque diario:** apagar todo y prenderlo en el orden real
   (servidor → caja/depósito → tablets), sin tocar nada a mano.
4. **Respaldo fresco antes de irte del local**, a un pendrive, no al disco del
   servidor:
   ```
   respaldo\respaldo.bat D:\
   ```
   (cambiar `D:\` por la letra que le toque al pendrive)

---

## Queda pendiente después de la entrega

- **Respaldo automático** — hoy hay que correrlo a mano. Está la decisión
  abierta entre 3 opciones en `docs/todo_montaje_servidor.md` §7
  (recomendación: `rclone` a Google Drive, sube solo lo que cambió).
  Definir también **quién** revisa que corra.
- **Probar una restauración real** desde un respaldo: un respaldo que nunca se
  restauró no es un respaldo.
- El servidor quedó en **WiFi**, no por cable. Anda bien, pero es el único
  punto de falla de todo el local: si en algún momento se puede tirar un cable
  de red hasta el router, conviene.

---

## Si algo se rompe estando el sistema en uso

| Síntoma | Primero mirar |
|---|---|
| Nadie puede entrar desde ningún equipo | ¿Está prendido el servidor y corriendo `iniciar.bat`? |
| Andaba y de golpe dejó de andar en todos lados | ¿Se durmió el servidor? (lo arregla el paso 1) ¿Cambió la IP? (`ipconfig`) |
| Un solo equipo no entra | El WiFi de ese equipo, no el servidor |
| Se ven los productos pero sin fotos | `docs/todo_montaje_servidor.md` §8 punto 5 |
| Los datos solo cambian al recargar | Se arrancó con `runserver`; usar `iniciar.bat` |
| Se registra el pago pero no sale el ticket | La impresora, en `docs/pc_caja.md` §4 |
