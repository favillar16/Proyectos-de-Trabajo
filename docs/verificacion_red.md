# Verificación de red y conexión entre dispositivos

Cómo comprobar que los equipos del local se ven entre sí, y cómo aislar el
problema cuando algo no carga. Sirve tanto para el armado inicial como para
el diagnóstico rápido un día que "no anda".

---

## 1. Los dispositivos no se conectan entre sí

Vale aclararlo primero porque cambia todo el diagnóstico: la red del sistema
es una **estrella**, no una malla.

```
                 ┌──────────────┐
                 │  PC SERVIDOR │   PostgreSQL + daphne (8000) + Vite (5173)
                 │   (la fija)  │
                 └──────┬───────┘
        ┌───────────────┼───────────────┬───────────────┐
        │               │               │               │
   ┌────┴────┐    ┌─────┴────┐    ┌─────┴────┐    ┌─────┴────┐
   │ PC Caja │    │PC Depósito│   │ Tablet 1 │    │ Tablet 2 │
   └─────────┘    └──────────┘    └──────────┘    └──────────┘
```

La tablet 1 **nunca** habla con la tablet 2. Las dos hablan con el servidor,
y el servidor les avisa a las dos. Por eso no hay nada que "emparejar" entre
dispositivos: alcanza con que cada uno llegue al servidor.

Lo que hace que un cambio aparezca en el resto sin recargar es el WebSocket
(Django Channels): `PedidoConsumer` (sala `pedido_<id>`) y `RolConsumer`
(sala `rol_<rol>`), en `apps/ventas/consumers.py`. Cuando se confirma un
pago, el servidor emite a la sala y todos los que estén escuchando se
enteran.

**Consecuencia práctica:** si un dispositivo no funciona, el problema está
entre ese dispositivo y el servidor. Nunca entre dos clientes.

### Los tres puertos

| Puerto | Qué es | Quién tiene que alcanzarlo |
|---|---|---|
| `5432` | PostgreSQL | Solo el servidor (y la notebook, para el sync) |
| `8000` | API REST + WebSocket (daphne) | Todos los clientes |
| `5173` | Frontend (Vite) | Todos los clientes |

Los clientes usan **5173 y 8000**. Ningún cliente necesita el 5432 — si
alguien está tratando de abrir Postgres desde la caja, algo se entendió mal
(ver `docs/pc_caja.md` §1).

---

## 2. Verificación en capas

Siempre de abajo hacia arriba. La primera que falle es el problema; no tiene
sentido revisar las de más arriba.

### Capa 1 — ¿Están en la misma red?

En el **servidor**, obtener su IP:

```powershell
ipconfig
```
Buscar **"Dirección IPv4"** (ej. `192.168.0.10`).

En el **cliente** (PC de caja o depósito):

```powershell
ping 192.168.0.10
```

- ✅ Responde → seguir a la capa 2.
- ❌ "Tiempo de espera agotado" → los equipos no están en la misma red.
  Revisar que ambos estén en el **mismo WiFi** (ojo con redes de invitados,
  o con una banda 2.4 GHz y otra 5 GHz que el router tenga aisladas), y que
  la red esté marcada como **privada** en Windows, no pública.

> Algunos routers tienen **"aislamiento de clientes" / "AP isolation"**
> activado, que impide que los dispositivos se vean entre sí aunque estén en
> el mismo WiFi. Si el ping falla y la red parece bien configurada, revisar
> esa opción en el router y desactivarla.

### Capa 2 — ¿Están abiertos los puertos?

Desde el cliente:

```powershell
Test-NetConnection -ComputerName 192.168.0.10 -Port 5173
Test-NetConnection -ComputerName 192.168.0.10 -Port 8000
```

Los dos tienen que dar `TcpTestSucceeded : True`.

- ❌ Ping anda pero los puertos no → o el sistema no está corriendo en el
  servidor (¿se corrió `iniciar.bat`? ¿siguen abiertas las dos ventanas
  negras?), o lo está bloqueando el **Firewall de Windows** — ver §3.

### Capa 3 — ¿Responde el backend?

Desde el navegador de cualquier cliente:

```
http://192.168.0.10:8000/admin/
```

Tiene que aparecer la pantalla de login de Django (no hace falta entrar).
Si aparece, el backend está vivo y accesible por la red.

### Capa 4 — ¿Responde el frontend?

```
http://192.168.0.10:5173
```

Tiene que cargar la pantalla de login del sistema.

Si carga el login pero después de entrar las pantallas quedan vacías o dan
error, es la capa 3 la que falla: el frontend está sirviéndose bien pero no
alcanza al backend. Confirmarlo abriendo `F12 → Consola` en el navegador.

### Capa 5 — ¿Anda el tiempo real?

Esta es la prueba que confirma que el enlace entre dispositivos funciona de
verdad. Con **dos dispositivos** abiertos al mismo tiempo:

1. En la **tablet**, abrir un pedido pendiente y dejarlo en pantalla.
2. En la **PC de caja**, confirmar el pago de ese pedido.
3. En la tablet, **sin recargar**, el pedido tiene que pasar a `pagado`
   solo, en un par de segundos.

Si el dato cambia recién al recargar la página, el WebSocket no está
conectando aunque la API sí funcione. Verificar en el navegador del cliente:
`F12 → Network → filtro WS` — tiene que haber una conexión a
`ws://192.168.0.10:8000/ws/pedidos/...` en estado `101 Switching Protocols`.

> Causa habitual: el servidor se arrancó con `python manage.py runserver` en
> vez de `daphne`. `runserver` sirve la API pero **no** soporta WebSocket, y
> el síntoma es exactamente este. Usar siempre `iniciar.bat`.

---

## 3. Firewall de Windows en el servidor

Si los puertos no responden desde otros equipos pero sí desde el propio
servidor (`http://localhost:5173`), es el firewall.

Abrir los dos puertos, en PowerShell **como administrador** en el servidor:

```powershell
New-NetFirewallRule -DisplayName "Oga Pora - Frontend (5173)" `
  -Direction Inbound -Protocol TCP -LocalPort 5173 -Action Allow -Profile Private

New-NetFirewallRule -DisplayName "Oga Pora - Backend (8000)" `
  -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
```

`-Profile Private` a propósito: la red del local tiene que estar clasificada
como **privada**. Verificarlo con:

```powershell
Get-NetConnectionProfile
```

Si dice `NetworkCategory : Public`, cambiarlo:

```powershell
Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private
```

---

## 4. Que la conexión no se caiga sola

El sistema ya está hecho para no depender de IPs escritas en ningún lado:
`services/api.js` y `hooks/usePedidoSocket.js` deducen la dirección del
backend del host con el que se abrió la página. Entrás por
`http://LO-QUE-SEA:5173` y la API y el WebSocket siguen ese mismo host
automáticamente, sin recompilar ni configurar nada por equipo.

Lo único que hay que estabilizar es **el punto de entrada**:

**Plan A — Reservar la IP del servidor en el router.** Es lo confiable.
Pasos detallados en `guia_instalacion_dispositivos.md` §2.1 (DHCP →
reserva por MAC). Con esto la IP no cambia aunque se reinicie el router, y
no hay que tocar nada en ningún dispositivo nunca más.

**Plan B — Nombre de red en vez de IP.** Windows publica el equipo como
`http://NOMBRE-DEL-SERVIDOR.local:5173`. Sirve de emergencia si la IP
cambió, pero **no reemplaza al plan A**: Chrome en Android resuelve `.local`
de forma inconsistente. Conviene probarlo una vez en cada tablet cuando hay
tiempo, para saber si funciona en esta red antes de necesitarlo apurado.

**Reconexión automática:** si el WiFi se corta un momento, el hook
`usePedidoSocket` reintenta solo con backoff exponencial (2s → 30s). No hay
que recargar la app a mano; alcanza con esperar unos segundos a que vuelva
la red.

---

## 5. Tablets

Además de todo lo anterior, las tablets tienen un paso propio: Chrome no
deja instalar la PWA desde `http://` salvo que se marque ese origen como
confiable. Está documentado en `docs/pwa_tablet.md`, junto con la
recuperación rápida si la IP cambió.

Chequeo rápido en una tablet:

1. Abrir Chrome (no el ícono instalado) → `http://IP-DEL-SERVIDOR:5173`
   → ¿carga el login?
2. Entrar con un usuario y abrir una pantalla con datos (Productos) →
   ¿aparecen los productos y sus fotos?
3. Abrir el ícono **"Oga Porã"** instalado → ¿carga igual que en Chrome?

Si el paso 1 anda y el 3 no, el problema es el origen confiable de Chrome
(`pwa_tablet.md`), no la red.

---

## 6. Tabla de síntomas

| Síntoma | Capa | Causa más probable |
|---|---|---|
| "No se puede acceder a este sitio" en todos los equipos | — | El servidor está apagado o no se corrió `iniciar.bat` |
| Anda en el servidor pero en ningún otro equipo | 2 | Firewall de Windows (§3) o red marcada como pública |
| Ping falla entre equipos del mismo WiFi | 1 | Aislamiento de clientes en el router, o redes distintas |
| Carga el login pero las pantallas quedan vacías | 3 | daphne caído; frontend arriba, backend no |
| Error 400 "Bad Request" del backend | 3 | `ALLOWED_HOSTS` en `backend/.env` no incluye la IP |
| Los datos solo se actualizan al recargar | 5 | Se arrancó con `runserver` en vez de `daphne` |
| Andaba y de un día para el otro dejó de andar | 4 | La IP del servidor cambió — reservarla en el router |
| Las fotos no cargan pero los datos sí | 3 | `DEBUG=False` en el `.env` (Django deja de servir `/media/`) |
| Una tablet no abre desde el ícono pero sí desde Chrome | — | Origen confiable de Chrome (`pwa_tablet.md`) |

---

## Referencias

- `guia_instalacion_dispositivos.md` — topología y orden de instalación
- `docs/pc_caja.md` — armado del puesto de caja e impresora
- `docs/pwa_tablet.md` — instalación y diagnóstico de tablets
- `docs/instalacion.md` — instalación completa del servidor
