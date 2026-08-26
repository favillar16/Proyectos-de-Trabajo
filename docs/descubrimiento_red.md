# Encontrar al servidor sin depender de una IP

**Última actualización:** 26/08/2026

## El problema

En el local no hay acceso al panel del router, así que no se puede reservar la
IP de la PC servidor por DHCP. Hoy está fijada desde la propia PC con
`fijar_ip.ps1` (192.168.100.250), que funciona, pero si el router se reemplaza
o se resetea la subred entera pasa a ser otra y esa dirección deja de existir.
Todo lo que tenga una IP escrita adentro se rompe ese día.

La solución es que nada guarde una dirección: que la busquen.

## Dos preguntas distintas

Se resuelven por separado porque tienen respuestas distintas.

| Pregunta | Cómo se responde | Quién la usa |
|---|---|---|
| ¿Estoy en el local? | SSID + BSSID de la red WiFi | el agente de sync de la notebook |
| ¿Dónde está el servidor? | nombre de red → cache → barrido | la app web y el agente de sync |

La primera importa porque la notebook se lleva afuera del predio. La segunda,
porque la dirección puede cambiar.

### ¿Estoy en el local? — SSID y BSSID

```powershell
. .\sync_notebook\resolver_servidor.ps1
Get-RedWifiActual          # -> SSID = OGA PORA, BSSID = 80:ae:3c:e4:4d:92
Test-EnRedDelLocal -SsidEsperado 'OGA PORA'
```

El **BSSID es la MAC de la antena del router**, y se lee del propio adaptador
WiFi con `netsh wlan show interfaces` — no hace falta entrar al panel del
router. Es un identificador más fuerte que el SSID, que cualquiera puede
copiar poniendo una red con el mismo nombre.

Se configura en `sync_notebook/config.env`:

```
RED_WIFI_SSID=OGA PORA
RED_WIFI_BSSID=80:ae:3c:e4:4d:92     # vacío = no se chequea
```

Si el equipo está por cable no hay SSID que mirar: se lo da por adentro y la
decisión queda en manos de la sonda de identidad.

### ¿Dónde está el servidor? — la sonda `/api/v1/salud/`

Todo equipo que corre el backend contesta, sin autenticación:

```json
{"sistema":"oga-pora","rol":"servidor","nombre":"OGAPORA","red_wifi":"OGA PORA","api":"v1"}
```

Es lo que convierte "hay algo en el puerto 8000" en "este es nuestro servidor".
El campo `rol` distingue la PC del local (`servidor`) del espejo de la
propietaria (`notebook`), y evita que la notebook se sincronice contra sí
misma. Se configura en `backend/.env`:

```
NODO_ROL=servidor        # o 'notebook'
NODO_NOMBRE=             # vacío = hostname de Windows
RED_WIFI_LOCAL=OGA PORA
```

El endpoint es deliberadamente público: solo dice "acá vive Oga Porã", no
expone ningún dato del negocio.

### Orden de búsqueda

Igual en el frontend (`frontend/src/services/servidor.js`) y en PowerShell
(`sync_notebook/resolver_servidor.ps1`), del más barato al más caro:

1. **Configurado a mano** — `VITE_API_URL` / `SERVIDOR_HOST`, si alguien lo fijó.
2. **El último que funcionó** — cache en `localStorage` / `sync_notebook/estado/servidor.json`.
3. **Nombres de red** — `ogapora.local` (mDNS) y `ogapora` (NetBIOS).
4. **Direcciones probables** — octetos típicos (250, 100, 10, 2…) + tabla ARP, preguntando HTTP directo.
5. **Barrido del resto de la subred** — filtrando por ping.

Cada candidato se confirma con `/salud/`. Un fallo de red en la app borra el
servidor conocido, que es justo el síntoma de que cambió de dirección: el
próximo pedido vuelve a buscarlo.

## Dos trampas que costaron encontrar

### Los nombres resuelven primero a IPv6

```
ogapora.local -> fe80::8a22:c43:3903:cbc9%9        (IPv6 link-local)
                 2803:2a00:2401:3881:697d:...      (IPv6 global)
                 192.168.100.250                    (IPv4, al final)
```

El cliente intenta IPv6 primero. Con `daphne -b 0.0.0.0` y `host: '0.0.0.0'`
en Vite no hay nadie escuchando ahí, así que entrar por nombre daba **timeout**
aunque la IP funcionara perfecto. Por eso:

- `iniciar.bat` arranca daphne con dos endpoints:
  `daphne -e tcp:8000:interface=0.0.0.0 -e tcp6:8000:interface=\:\:`
  (los `\:\:` van escapados porque twisted usa `:` como separador de campos)
- `vite.config.js` usa `host: '::'`, que en Node escucha IPv4 e IPv6 a la vez.

### Vite bloquea los nombres de host

Desde 5.4.12, el servidor de desarrollo de Vite responde `403 Blocked request.
This host is not allowed` a cualquier `Host:` que no sea una IP o `localhost`.
Se abrió con `server.allowedHosts: true`, por la misma razón que el backend
tiene `ALLOWED_HOSTS='*'`: es un appliance de red local sin salida a internet
y el nombre del equipo puede cambiar.

## Qué funciona desde dónde

| Desde | Por nombre | Por IP |
|---|---|---|
| PC servidor | ✅ | ✅ |
| Notebook (Windows) | ✅ `ogapora.local` o `ogapora` | ✅ |
| Tablets Android | ❌ *(ver abajo)* | ✅ |

**Chrome en Android no resuelve nombres `.local`** — no tiene resolvedor mDNS
disponible para el navegador. En las tablets hay que usar la IP **la primera
vez**, al instalar la PWA. Después no importa: el shell de la app queda
cacheado por el service worker, así que arranca aunque el servidor no esté en
la dirección vieja, y `servidor.js` lo busca de nuevo por su cuenta (pasos 4 y
5, que sí funcionan en Android porque son IPs). O sea: la IP se usa una vez
para instalar, nunca más para funcionar.

## Comprobar que está todo bien

```powershell
# ¿Qué red estoy viendo?
. .\sync_notebook\resolver_servidor.ps1 ; Get-RedWifiActual

# ¿Encuentro el servidor, y por qué camino?
Find-Servidor -HostFijo auto -ArchivoCache .\sync_notebook\estado\servidor.json

# ¿Contesta la sonda?
Invoke-RestMethod http://ogapora.local:8000/api/v1/salud/

# ¿Los nombres resuelven?
[System.Net.Dns]::GetHostAddresses('ogapora.local')
```

En el navegador, la app deja el servidor en uso en `localStorage`, clave
`ogapora-servidor`.

## Archivos

| Archivo | Qué hace |
|---|---|
| `backend/config/salud.py` | endpoint de identidad |
| `backend/config/settings.py` | bloque `NODO` |
| `frontend/src/services/servidor.js` | búsqueda desde el navegador |
| `frontend/src/services/api.js` | resuelve el `baseURL` en cada request |
| `frontend/src/hooks/usePedidoSocket.js` | el WebSocket sigue al mismo servidor |
| `frontend/vite.config.js` | `allowedHosts` + `host: '::'` |
| `sync_notebook/resolver_servidor.ps1` | SSID/BSSID + búsqueda desde PowerShell |
| `sync_notebook/config.env` | `SERVIDOR_HOST=auto`, SSID y BSSID |
| `iniciar.bat` | daphne con endpoints IPv4 + IPv6 |
