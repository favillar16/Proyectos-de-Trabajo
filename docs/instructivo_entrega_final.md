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
| IP del servidor | `192.168.100.250` (**fija**, puesta por `fijar_ip.bat`) |
| MAC del adaptador WiFi | `10-5A-95-76-C9-20` |
| Router / puerta de enlace | `192.168.100.1` |
| Dirección del sistema | `http://192.168.100.250:5173` |
| API / backend | `http://192.168.100.250:8000` |
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

## Paso 2 — Fijar la IP del servidor con `fijar_ip.bat` (2 minutos)

**Por qué:** si la IP la reparte el router por DHCP, es prestada. El día que se
corte la luz o se reinicie el router puede darle otra a esta PC — y ese día las
2 tablets, la PC de caja, la de depósito y la notebook dejan de encontrar el
sistema **todas juntas**, y hay que reconfigurarlas una por una.

Lo normal sería reservar la IP en el router, pero no hay acceso a su panel
(es un Nokia del proveedor y la clave no está disponible). Así que se resuelve
del otro lado: la IP se la ponemos fija a la PC.

1. Doble clic en **`fijar_ip.bat`** (raíz del proyecto) → permiso de
   Administrador → **Sí**.
2. La red se corta un instante y vuelve. Al final tiene que decir
   `IP : 192.168.100.250 (Manual)`.

**Por qué `.250` y no la que tenía:** el barrido de la red mostró que el router
reparte las direcciones **desde abajo** (.3, .4, .7, .9, .13, .15, .16 ocupadas
el 21/08/2026). Nunca va a llegar hasta `.250`, así que no hay riesgo de que se
la dé a otro equipo. El script igual comprueba que esté libre **antes** de
tomarla, y si está ocupada no cambia nada y avisa.

**Verificar que quedó:**

```powershell
ipconfig | findstr /i "IPv4"
```

Tiene que decir `192.168.100.250`. Reiniciá la PC y volvé a mirar: tiene que
seguir igual.

> **Para volver atrás** (por ejemplo si algún día se cambia de router):
> `fijar_ip.bat deshacer` → vuelve a DHCP.
>
> **Si algún día conseguís la clave del router**, lo prolijo es además
> reservar `192.168.100.250` para la MAC `10-5A-95-76-C9-20` en
> **LAN → DHCP Server → "IPv4 address reservations"** (así se llama el menú en
> este Nokia). No es obligatorio: con la IP fija ya alcanza.

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
- Probar entrar con una de ellas en `http://192.168.100.250:5173` antes de
  seguir.

---

## Paso 4 — Crear el usuario de la notebook (2 minutos)

Solo si hoy se va a configurar la notebook de la propietaria.

**Doble clic en `sync_notebook\crear_rol_sync.bat`** → Administrador → Sí.

Crea el rol `notebook_sync`, que puede **leer** toda la base y **no puede
escribir nada** (el sync nunca debe entrar con el usuario de la app: la
notebook es un espejo de solo lectura). El script:

- genera la contraseña solo, alfanumérica, para que se pueda pegar sin
  problemas de comillas;
- verifica que el rol pueda leer y que efectivamente no pueda escribir;
- deja todo listo para pegar en `sync_notebook\credenciales_sync.txt`, en
  esa misma carpeta.

Va a preguntar cómo entrar como superusuario:

- **Opción 1** — tenés la contraseña de `postgres`: la pide `psql` y listo.
- **Opción 2** — no la tenés: habilita el acceso local sin contraseña unos
  segundos (solo desde esta misma PC), crea el rol y deja `pg_hba.conf`
  exactamente como estaba, con copia de seguridad.

Después, en la notebook, pegar ese bloque en `sync_notebook\config.env` y
completar solo los `LOCAL_DB_*` con los datos del PostgreSQL de la notebook.
Las fotos no necesitan configuración: se bajan por HTTP (dejar
`SERVIDOR_MEDIA_UNC` y `SERVIDOR_MEDIA_URL` vacíos).

⚠️ En la notebook tienen que estar **los tres** `.ps1` de `sync_notebook/`:
`sync_notebook.ps1`, `fotos_http.ps1` y (solo si se corre desde ahí)
`crear_rol_sync.ps1`. Con `git pull` vienen solos.

---

## Paso 5 — Probar desde otro equipo (2 minutos)

Antes de ponerse a configurar tablets y puestos, comprobar que la red quedó
abierta. Desde **cualquier otra PC del local**, en PowerShell:

```powershell
Test-NetConnection -ComputerName 192.168.100.250 -Port 5173
Test-NetConnection -ComputerName 192.168.100.250 -Port 8000
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
