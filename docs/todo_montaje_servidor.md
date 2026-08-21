# TODO — Montaje de la PC Servidor

Checklist de trabajo pendiente para el día que se arme la PC servidor
definitiva del local, con las decisiones que quedaron abiertas y el contexto
necesario para retomarlo sin volver a investigar.

**Última actualización:** 21/08/2026
**Estado general:** servidor definitivo (`OGAPORA`) instalado y con los datos
migrados y verificados; falta la configuración de red del local, rotar las
contraseñas y armar los 5 puestos restantes. El checklist por equipo está en
`docs/plan_manana_local.md`.

---

## Estado al 20/08/2026

Lo que ya está hecho y probado:

| Cosa | Estado |
|---|---|
| Sistema completo corriendo | ✅ en el equipo de armado (`DESKTOP-UAIGET9`) |
| Catálogo cargado | ✅ 393 productos, 425 variantes, 338 fotos |
| Herramientas de respaldo | ✅ `respaldo\respaldo.bat` / `restaurar.bat`, probadas de punta a punta |
| Sync de la notebook | ✅ incluye fotos desde el 20/08/2026 |
| Documentación de despliegue | ✅ ver "Referencias" al final |
| **PC servidor definitiva** | ✅ instalada y migrada el 20–21/08/2026 (`OGAPORA`, ex `DESKTOP-Q9T1TPI`) |
| **Respaldo automático** | ❌ **pendiente + decisión abierta (§7)** |

Datos de la base al momento de escribir esto (sirven para verificar que la
migración no perdió nada):

```
productos=393  variantes=425  imagenes_producto=338
stock=425      usuarios=5     movimientos_stock=414
fotos en disco = 338 archivos, 34,9 MB
```

---

## 1. Antes de ir al local ✅ (hecho el 20/08/2026)

- [x] Confirmar que la PC servidor tiene: Windows 10/11, disco con espacio
      para la base + fotos + respaldos, y puerto de red o WiFi estable
- [x] Llevar un pendrive de al menos 1 GB para el traslado. **Si no hay
      pendrive:** las fotos van por el repositorio
      (`respaldo\subir_fotos.bat`) y solo el `base_datos.sql` (~333 KB)
      por correo/Drive — `docs/respaldo_y_migracion.md` §3.5
- [x] Llevar el instalador de Python 3.11, Node 20 LTS y PostgreSQL 15 por
      si la conexión del local es lenta
- [x] **Hacer un respaldo fresco del equipo de armado el mismo día**, no uno
      viejo: `respaldo\respaldo.bat D:\`

---

## 2. Instalación base en la PC servidor ✅ (hecho el 20/08/2026)

Guía completa: `docs/instalacion.md`

- [x] Instalar Python 3.11, Node 20 LTS, PostgreSQL 15
- [x] Agregar `C:\Program Files\PostgreSQL\15\bin` al PATH
- [x] Copiar la carpeta del proyecto
- [x] Crear base y usuario en PostgreSQL
- [x] Armar `backend\.env` desde `backend\.env.example`
- [x] Correr `setup.bat`
- [x] Dar permiso de crear bases al usuario de la app (lo necesita el
      restaurador): `ALTER ROLE ceramica_user CREATEDB;`

> El usuario admin que pide `setup.bat` se crea y después desaparece: el
> paso 3 reemplaza la base entera. Los usuarios buenos son los del equipo
> de armado.

---

## 3. Migrar los datos ✅ (hecho el 21/08/2026, conteos verificados exactos)

Guía completa: `docs/respaldo_y_migracion.md`

- [x] Copiar la carpeta `respaldo_AAAAMMDD_HHMMSS` del pendrive
      (sin pendrive: `git clone` trae las fotos y se restaura solo el
      `base_datos.sql` recibido aparte — §3.5 de esa guía)
- [x] Con el sistema cerrado: `respaldo\restaurar.bat D:\respaldo_...`
      (pide escribir `SI`)
- [x] `iniciar.bat` y entrar con un usuario **del equipo de armado**
- [x] Verificar contra la tabla de arriba: 393 productos, y que las fotos
      se vean (no alcanza con que estén los productos)

---

## 4. Red

Guía completa: `docs/verificacion_red.md`

Casi todo esto lo hace de una sola pasada `preparar_red.bat` (raíz del
proyecto, doble clic, pide Administrador): categoría de red privada, puertos
5173/8000 en el firewall, suspensión desactivada, `backend\media` compartida y
`pg_hba.conf` con la subred del local.

- [x] IP definitiva: `192.168.100.16` (Wi-Fi, red `OGA PORA`, DHCP)
- [x] Nombre de red de la PC (`hostname`): `OGAPORA`
- [x] MAC del adaptador Wi-Fi: `10-5A-95-76-C9-20`
- [ ] **Reservar esa IP en el router** (DHCP → reserva por MAC).
      `guia_instalacion_dispositivos.md` §2.1. Es lo que evita tener que
      reconfigurar todos los dispositivos si el router se reinicia.
- [ ] Marcar la red del local como **privada**, no pública (`preparar_red.bat`)
- [ ] Abrir los puertos 5173 y 8000 en el firewall (`preparar_red.bat`)
- [ ] **Desactivar la suspensión del servidor** (`preparar_red.bat`). Venía
      configurado para dormirse a los 45 minutos de inactividad: dormido, el
      sistema deja de existir para caja, depósito y tablets.
- [ ] Verificar desde otro equipo: `Test-NetConnection 192.168.100.16 -Port 8000`

> El servidor queda conectado por **Wi-Fi** (2,4 GHz, 802.11n), no por cable.
> Es el único punto de falla de todo el local: si alguna vez se puede pasar a
> Ethernet, conviene.

---

## 5. Puestos de trabajo

### PC Caja — `docs/pc_caja.md`
- [ ] Chrome + acceso directo "abrir como ventana", usuario `cajero`
- [ ] **Impresora térmica compartida** (§4 de ese doc). Recordar: el ticket
      se imprime desde el **servidor**, no desde la caja
- [ ] Poner en el `.env` del servidor: `IMPRESORA_TERMICA_NOMBRE=\\PC-CAJA\TERMICA80`
- [ ] Probar con `python diagnostico_impresora.py` en el servidor
- [ ] Prueba real: confirmar un pago desde la caja y ver salir el ticket

### PC Depósito
- [ ] Chrome + acceso directo, usuario `deposito`

### Tablets (2) — `docs/pwa_tablet.md`
- [ ] `chrome://flags/#unsafely-treat-insecure-origin-as-secure` con la IP
      nueva → Enabled → Relaunch
- [ ] Instalar la PWA
- [ ] Probar el plan B (`http://NOMBRE-PC.local:5173`) para saber si esta
      red lo resuelve, **antes** de necesitarlo en un apuro

### Notebook — `docs/sync_notebook.md`
- [ ] Crear el usuario `notebook_sync` en el servidor (§1.2)
- [ ] **Compartir `backend\media` en red** (§1.3) — es nuevo, sin esto la
      notebook muestra los productos sin foto
- [ ] Actualizar `sync_notebook\config.env`: `SERVIDOR_HOST` con la IP
      nueva y `SERVIDOR_MEDIA_UNC` con la carpeta compartida
- [ ] Verificar `sync_notebook\estado\last_sync.json` — el detalle ahora
      dice cuántas fotos sincronizó

---

## 6. Verificación final

- [ ] **Cambiar las contraseñas de `admin`, `cajero`, `deposito` y `vendedor`**.
      Al 21/08/2026 los cuatro siguen con `demo2025`, la credencial de demo
      heredada del equipo de armado. En el servidor, una por una:
      `cd backend` → `venv\Scripts\activate` →
      `python manage.py changepassword admin`. Dejarle las nuevas a la
      propietaria por escrito.
- [ ] Correr el `docs/checklist_entrega.md` (59 casos funcionales)
- [ ] Prueba de tiempo real entre dispositivos: abrir un pedido en la
      tablet, confirmar el pago en la caja, ver que la tablet cambia sola
      sin recargar (`docs/verificacion_red.md` §2, capa 5)
- [ ] Prueba de arranque diario completo
      (`guia_instalacion_dispositivos.md` §7)

---

## 7. Respaldo automático — DECISIÓN PENDIENTE

Hoy el respaldo existe pero **hay que correrlo a mano**. Esto es lo que
falta definir, y es lo más importante de la lista después de la migración.

### Contexto para retomarlo

Un respaldo son siempre **dos piezas juntas**: la base de datos y las fotos.
Las imágenes **no** están en la base — la columna `imagen` de
`imagenes_producto` es un `varchar(100)` con la ruta (29-46 bytes por fila);
los archivos viven en `backend\media`. Un `pg_dump` solo restaura 393
productos con las 338 imágenes rotas. `respaldo.bat` ya copia las dos.

### Idea a evaluar: subir el respaldo a Google Drive

Es factible. Tres caminos, de menos a más trabajo:

| | Qué es | Trabajo | Nota |
|---|---|---|---|
| **A** | Google Drive para escritorio (unidad `G:`) + `respaldo.bat "G:\Mi unidad\Respaldos"` | Cero código | Funciona hoy mismo |
| **B** | `rclone` sincronizando contra Drive | Config una vez | **Recomendado** |
| **C** | Botón dentro del sistema | Bastante más | Ver advertencias |

**Por qué B:** las fotos son ~35 MB que casi nunca cambian y la base son
~333 KB que cambian todos los días. Subir una copia completa por día son
~1 GB al mes, y Drive gratis tiene 15 GB — se llena en poco más de un año.
`rclone sync` transfiere solo lo que cambió: 300 KB por día en vez de 35 MB.

**Si se elige C, tener en cuenta:**
- Hay que crear un proyecto en Google Cloud y mantener OAuth (tokens que se
  renuevan)
- **No hay cola de tareas en el proyecto** (ni Celery ni equivalente). Una
  subida de 35 MB dentro de un request bloquea un worker de daphne — habría
  que lanzarla en un hilo o subproceso aparte
- Tiene que ser **solo admin** (`EsAdmin`): exporta la base entera,
  incluidos los hashes de contraseña, y la red corre con `ALLOWED_HOSTS=*`
  y `CORS_ALLOW_ALL_ORIGINS=True` a propósito
- Sirve como comodidad para un respaldo manual puntual, **no** como
  mecanismo principal — el que protege de verdad es el automático

**En cualquier caso:** el respaldo a Drive tiene que ser best-effort y
**nunca bloquear**. El sistema está diseñado para funcionar sin internet y
no puede empezar a depender de él. Si no hay conexión, el respaldo local se
tiene que hacer igual.

### Tareas

- [ ] **Decidir A, B o C** (recomendación: B)
- [ ] Definir frecuencia (mínimo semanal; ideal diario)
- [ ] Definir **quién** es responsable de verificar que el respaldo corre
- [ ] Programar la tarea en el Programador de tareas de Windows
- [ ] Probar una **restauración real** desde el respaldo automático — un
      respaldo que nunca se restauró no es un respaldo
- [ ] Definir cuántos respaldos se conservan antes de borrar los viejos

---

## 8. Cosas que van a morder si se olvidan

Descubiertas armando esto; están documentadas pero es fácil pasarlas por
alto:

1. **El ticket se imprime desde el servidor, no desde la caja.**
   `printer.py` corre dentro de Django con `win32print`. Impresora por USB
   en la caja sin compartir = el pago se registra pero no sale papel.
2. **Las fotos no están en la base.** Respaldo de base sin `media` = catálogo
   con todas las imágenes rotas.
3. **La caja y el depósito NO llevan base de datos.** El candado de stock
   (`select_for_update`) solo existe dentro de una base; dos bases terminan
   en el mismo pallet vendido dos veces (`docs/pc_caja.md` §1).
4. **Arrancar con `daphne`, no con `runserver`.** `runserver` sirve la API
   pero no soporta WebSocket: el síntoma es que los datos solo se actualizan
   al recargar. Usar siempre `iniciar.bat`.
5. **`DEBUG=False` deja de servir `/media/`** — ✅ **resuelto** el 21/08/2026
   (commit `fec3ded`). El helper `django.conf.urls.static.static()` tiene un
   `if not settings.DEBUG: return []` adentro, así que no alcanzaba con sacar
   el `if` propio: ahora `config/urls.py` sirve `/media/` con una ruta
   explícita a `django.views.static.serve`, sin depender de `DEBUG`. Si
   alguna vez las fotos vuelven a dar 404 con `DEBUG=False`, mirar ahí.
6. **La impresora tiene que estar instalada para el mismo usuario de Windows
   que corre `iniciar.bat`.** Si se agrega desde otra cuenta, Django no la
   encuentra.

---

## 9. Otras cosas abiertas (menor prioridad)

- [ ] **`frontend/dist/` está trackeado en git** pero `iniciar.bat` levanta
      `npm run dev`, así que ese build no es lo que se sirve. Si nadie lo
      consume, es mantenimiento gratis — decidir si se saca del repo.
- [ ] El channel layer es `InMemoryChannelLayer`. Alcanza porque hay un solo
      proceso daphne. Si alguna vez se corren varios workers, hay que pasar
      a Redis (`channels-redis` ya está en `requirements.txt`).
- [ ] No hay suite de tests automatizados; la verificación es manual contra
      `docs/checklist_entrega.md`.

---

## Referencias

| Documento | Para qué |
|---|---|
| `instructivo_entrega_final.md` | Acciones manuales paso a paso para cerrar la entrega |
| `guia_instalacion_dispositivos.md` | Topología de los 6 equipos y orden de instalación |
| `instalacion.md` | Instalación completa del servidor |
| `respaldo_y_migracion.md` | Respaldo y traslado a otra PC |
| `pc_caja.md` | Puesto de caja e impresora compartida |
| `verificacion_red.md` | Diagnóstico de red por capas |
| `pwa_tablet.md` | Tablets |
| `sync_notebook.md` | Espejo de la notebook |
| `checklist_entrega.md` | 59 casos funcionales de prueba |
