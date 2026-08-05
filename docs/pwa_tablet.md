# Instalación de la app en la tablet (PWA)

El frontend ahora es una **PWA** (Progressive Web App): el mismo sitio de
siempre, pero instalable en Android como si fuera una app nativa (ícono
propio, pantalla completa, sin barra de Chrome). No hay código nuevo que
mantener por separado — es la misma app React de escritorio.

Qué se agregó al repo:
- `frontend/vite.config.js` → plugin `vite-plugin-pwa` (manifest + service worker)
- `frontend/public/icons/` → íconos de la app (192px, 512px, 512px maskable)
- `frontend/public/favicon.ico`
- `backend/.env` y `backend/config/settings.py` → `ALLOWED_HOSTS=*` (necesario
  para que la tablet llame a la API por la IP de la PC servidor; ver comentario
  en esos archivos)

---

## ⚠️ Paso obligatorio en la tablet (una sola vez)

Los navegadores solo permiten instalar una PWA (y activar su modo offline)
desde un **origen seguro**: `https://` o `localhost`. La tablet accede por
`http://IP-DE-LA-PC:5173`, que Chrome considera "no seguro" por defecto, y
sin este paso **el botón de instalar no va a aparecer**.

Hay que decirle a Chrome, una sola vez, que confíe en esa dirección:

1. En la tablet, abrir Chrome y escribir en la barra de direcciones:
   `chrome://flags/#unsafely-treat-insecure-origin-as-secure`
2. En el campo de texto, escribir la dirección exacta del servidor, por ejemplo:
   `http://192.168.0.10:5173`
   *(la IP real se obtiene en la PC servidor con `ipconfig`, buscando
   "Dirección IPv4" — es la misma que ya se usa hoy para abrir el sistema
   desde la tablet)*
3. Cambiar el desplegable de "Disabled" a **"Enabled"**
4. Tocar **"Relaunch"** (Chrome se reinicia)

Si la IP de la PC servidor cambia (por ejemplo, se reinicia el router y el
DHCP asigna otra), hay que repetir este paso con la nueva IP. Para evitarlo,
lo ideal es reservar esa IP en el router (IP fija por MAC) antes de la
puesta a prueba.

## Instalar la app

1. En la tablet, abrir Chrome y entrar a `http://IP-DE-LA-PC:5173` (la misma
   dirección configurada arriba)
2. Tocar el menú (⋮) → **"Instalar aplicación"** (o el banner que aparece solo)
3. Confirmar. Queda un ícono "Oga Porã" en la pantalla de inicio, que abre la
   app en pantalla completa, sin navegador visible

## Qué se cachea y qué no

- El "shell" de la app (HTML/JS/CSS) se guarda en caché para que abra rápido
  y no quede en blanco si el wifi tiene un corte momentáneo.
- Las llamadas a la API (`/api/...`) **nunca** se cachean — stock, pedidos y
  caja siempre se piden en vivo al servidor. Si no hay conexión al servidor,
  la app abre pero las pantallas con datos no van a cargar (es el
  comportamiento esperado: mejor mostrar "sin conexión" que datos viejos).
- Las fotos de productos (`/media/...`) sí se cachean, para que el showroom
  no dependa de recargar cada imagen en cada visita.

## Diagnóstico rápido si algo falla en la demo

- **No aparece "Instalar aplicación"** → falta el paso de `chrome://flags` de
  arriba, o se hizo con una IP que no coincide exactamente con la de la barra
  de direcciones (con o sin `http://`, con el puerto `:5173` incluido).
- **La app instala pero no carga datos** → revisar que el backend
  (`daphne ... 0.0.0.0:8000`) esté corriendo en la PC servidor y que la
  tablet esté en la misma red WiFi.
- **Error 400 "Bad Request" o similar viniendo del backend** → revisar que
  `backend/.env` tenga `ALLOWED_HOSTS=*` (o al menos incluya la IP de la PC
  servidor).
