# Guía de instalación — Todos los dispositivos del local

Este documento es el punto de partida para dejar el sistema funcionando en
los **6 dispositivos** del negocio: 3 PCs de mesa, 2 tablets y la notebook
de la propietaria. Para el detalle fino de cada parte, remite a los
documentos específicos (`instalacion.md`, `pwa_tablet.md`,
`sync_notebook.md`) — acá está el resumen y el orden en que hay que hacerlo.

---

## 1. Topología — qué hace cada equipo

Solo **una** PC corre el sistema de verdad (backend + base de datos). El
resto son "ventanas" hacia esa PC: no instalan nada del sistema, solo abren
el navegador apuntando a ella. La notebook es la única excepción — tiene su
propia copia completa, para poder seguir funcionando cuando sale del local.

| # | Dispositivo | Rol | Qué corre localmente | Instalación |
|---|---|---|---|---|
| 1 | **PC Servidor** | Backend + base de datos + frontend | Django/Daphne, PostgreSQL, Vite | Completa — §2 |
| 2 | **PC Caja** | Cliente | Solo Chrome | Mínima — §3 |
| 3 | **PC Depósito** | Cliente | Solo Chrome | Mínima — §3 |
| 4–5 | **Tablet 1 y 2** | Cliente móvil (PWA) | Chrome, instalado como app | `pwa_tablet.md` — §4 |
| 6 | **Notebook propietaria** | Espejo local + cliente | Su propio Postgres/Django/frontend, sincronizado | `sync_notebook.md` — §5 |

**Todos los dispositivos necesitan estar en la misma red WiFi del local**
(salvo la notebook cuando está fuera).

---

## 2. PC Servidor (una sola vez)

Es la base de todo — el resto de los dispositivos no funciona si esta PC no
está prendida y corriendo. Instrucciones completas en `instalacion.md`;
resumen:

```bat
:: Con Python 3.11, Node 20 LTS y PostgreSQL 15 ya instalados
cd ceramica_final
setup.bat
```

Después de instalar:

1. **Reservar la IP de esta PC en el router** (IP fija por MAC). Todos los
   demás dispositivos (PCs, tablets, notebook) apuntan a esta IP — si
   cambia, hay que reconfigurar cada uno (ver "Si la IP cambia igual" más
   abajo y en `pwa_tablet.md`).

   Pasos generales (varían según la marca del router):
   1. Conseguir la dirección MAC de esta PC: en PowerShell,
      `Get-NetAdapter | Where-Object Status -eq Up | Select Name,MacAddress`
      (el adaptador Wi-Fi o Ethernet que esté "Up" es el que importa).
   2. Entrar a la administración del router — normalmente
      `http://192.168.0.1` o `http://192.168.1.1` desde un navegador en la
      misma red (usuario/contraseña suele estar en una etiqueta del router).
   3. Buscar una sección tipo **"DHCP" → "Reserva de IP" / "Static Lease" /
      "Address Reservation" / "IP-MAC Binding"** (el nombre exacto cambia
      según el fabricante).
   4. Asociar la MAC de esta PC a la IP que ya tiene asignada (o a una IP
      fija a elección, ej. `192.168.0.50`) y guardar. Puede pedir reiniciar
      el router.
2. Anotar esa IP — se necesita en los pasos §3, §4 y §5.
3. Para el día a día, arrancar el sistema con `iniciar.bat` (abre backend y
   frontend, y el navegador local automáticamente).

### Si la IP cambia igual (plan B: nombre en vez de número)

Windows expone esta PC en la red local por su nombre además de por IP —
esto **no reemplaza** la reserva de IP en el router (es más confiable), pero
sirve como alternativa si por algún motivo la IP cambió y todavía no se
actualizó en algún dispositivo:

```
http://DESKTOP-UAIGET9.local:5173
```

*(el nombre sale de `hostname` en la PC servidor — ya viene habilitado el
firewall de Windows para responder a estas consultas en la red local)*

⚠️ A diferencia de la IP, esto depende de que el router y el Chrome de cada
tablet soporten mDNS — no todos los equipos Android lo resuelven de forma
confiable. Probarlo una vez en cada tablet cuando haya tiempo, para saber
si funciona en esta red antes de necesitarlo en un apuro. Si no carga,
usar la IP como siempre.

---

## 3. PC Caja y PC Depósito (clientes — 2 minutos cada una)

> Para la **PC de Caja** hay un checklist propio con el detalle de la
> impresora térmica (que imprime desde el servidor, no desde la caja):
> **`docs/pc_caja.md`**. Lo de acá abajo es el resumen, y alcanza tal cual
> para la PC de Depósito.

No necesitan Python, Node ni PostgreSQL — solo Chrome y la IP del servidor
(§2.2). **Tampoco llevan base de datos**: hay una sola base, la del
servidor, y es lo que evita que el mismo material se venda dos veces
(el porqué, en `docs/pc_caja.md` §1).

1. Con el servidor ya corriendo, abrir Chrome y entrar a
   `http://IP-DEL-SERVIDOR:5173`
2. Iniciar sesión con el usuario correspondiente al puesto (`cajero` en la
   PC de caja, `deposito` en la de depósito)
3. Opcional, para que se sienta como una app propia y no una pestaña más:
   menú (⋮) → **Más herramientas → Crear acceso directo** → tildar "Abrir
   como ventana". Queda un ícono en el escritorio que abre directo al
   sistema, sin barra de direcciones.

Si esta PC no carga el sistema, lo primero a revisar siempre es que la PC
Servidor esté prendida y con `iniciar.bat` corriendo.

---

## 4. Tablets (2 unidades)

Instrucciones completas y diagnóstico en `pwa_tablet.md`. Resumen por
tablet (repetir en cada una):

1. Configurar una vez en Chrome: `chrome://flags/#unsafely-treat-insecure-origin-as-secure`
   → agregar `http://IP-DEL-SERVIDOR:5173` → Enabled → Relaunch
   *(sin este paso, Chrome no deja instalar la app — ver el porqué en `pwa_tablet.md`)*
2. Entrar a `http://IP-DEL-SERVIDOR:5173`
3. Menú (⋮) → **Instalar aplicación** → confirmar
4. Queda el ícono "Oga Porã" en la pantalla de inicio

---

## 5. Notebook de la propietaria

Instrucciones completas en `sync_notebook.md`. A diferencia de las PCs de
caja/depósito, **esta sí necesita una instalación completa** (Python, Node,
PostgreSQL, backend, frontend — igual que la PC Servidor, `instalacion.md`),
porque debe poder seguir mostrando datos aunque salga del local sin
conexión al servidor.

Resumen, después de tener la instalación completa corriendo en la notebook:

1. **Una vez, en el servidor:** habilitar conexiones remotas de PostgreSQL
   y crear el usuario de solo lectura `notebook_sync`
   (`sync_notebook.md`, sección 1).
2. **En la notebook:** completar `sync_notebook/config.env` con la IP del
   servidor y las credenciales, y correr
   `sync_notebook/instalar_tarea_programada.bat`.
3. Confirmar que sincroniza: `schtasks /run /tn "OgaPora - Sync Notebook"`
   y revisar `sync_notebook/estado/last_sync.json`.

**Importante:** la notebook es un espejo de **solo lectura**. Sirve para
consultar stock, pedidos y reportes estando fuera del local — no para
cargar ventas ahí (esos datos no vuelven al servidor). Si en algún momento
la notebook va a usarse para operar la caja estando en el local, mejor
usarla como una tablet más (§4, contra el servidor directo), no contra su
base de datos local.

---

## 6. Orden recomendado para no perder tiempo

1. **PC Servidor** — todo lo demás depende de que esta esté lista
2. Reservar su IP en el router
3. **Notebook** — requiere acceso al servidor para el paso único de crear
   `notebook_sync` (§5.1), conviene hacerlo mientras el instalador está
   ahí en el local
4. **Tablets** — 2 unidades, ~5 minutos cada una con el paso de Chrome flags
5. **PC Caja / PC Depósito** — las más rápidas, sin nada que instalar

---

## 7. Arranque diario (una vez todo instalado)

1. Prender la **PC Servidor** primero y correr `iniciar.bat` — esperar a
   que abra el navegador local, señal de que backend y frontend están arriba
2. Prender **PC Caja** y **PC Depósito** — abrir su acceso directo (§3)
3. **Tablets** — ya quedan instaladas, solo abrir el ícono "Oga Porã"
4. **Notebook** — si está en el local, sincroniza sola cada 5 minutos en
   segundo plano, no requiere ninguna acción

---

## 8. Respaldo (no es opcional)

El sistema no respalda solo. Un respaldo son **la base de datos + las fotos
de productos juntas** — ver `docs/respaldo_y_migracion.md`.

```bat
respaldo\respaldo.bat D:\
```

Mínimo una vez por semana a un pendrive, y siempre antes de tocar algo
grande. Es también la herramienta para **trasladar el sistema a otra PC**
(por ejemplo, del equipo de armado a la PC servidor definitiva).

---

## Problemas comunes

Para problemas de **red o de conexión entre dispositivos** (algo no carga,
los datos no se actualizan solos, la IP cambió), el documento específico es
**`docs/verificacion_red.md`**, que va por capas de abajo hacia arriba.

Para errores específicos (PostgreSQL, puertos ocupados, impresora, 403,
etc.) ver la sección **"Solución de problemas frecuentes"** de
`instalacion.md` y **"Problemas conocidos y soluciones"** de
`checklist_entrega.md`. Para problemas de tablets, de la caja o de la
notebook, cada documento respectivo (`pwa_tablet.md`, `pc_caja.md`,
`sync_notebook.md`) tiene su propia sección de diagnóstico.
