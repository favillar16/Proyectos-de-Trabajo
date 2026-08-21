# Sincronización de la notebook con el servidor del local

La notebook de la propietaria puede salir del local en cualquier momento.
Para que siempre tenga los datos del negocio sin depender de un servidor
web (sin costo de hosting), la notebook mantiene su **propia base de datos
local**, que se sobreescribe automáticamente con una copia de la del
servidor cada vez que ambas están conectadas a la misma red WiFi.

**La notebook es un espejo de solo lectura.** El servidor (la PC fija del
local) es siempre el origen de verdad. El sync va en un solo sentido:
servidor → notebook, nunca al revés. Si se carga una venta en la notebook
estando fuera del local, esa venta **no** viaja al servidor y se pierde en
el próximo sync — la notebook es para consultar (stock, reportes, pedidos),
no para operar la caja. Si en algún momento hace falta operar la caja desde
la notebook estando en el local, mejor usarla como una tablet más (contra
el servidor directamente), no contra su base de datos local.

Cómo funciona en la práctica:
- **En el local, con WiFi:** cada 5 minutos, la notebook chequea si el
  servidor responde y, si puede, descarga sus datos y reemplaza los
  propios. Los datos quedan frescos con un desfasaje máximo de ~5 minutos.
- **Fuera del local:** el chequeo falla rápido (no encuentra el servidor) y
  no hace nada. La notebook se queda con los datos de la última vez que
  estuvo en el local — desactualizados, pero disponibles, nunca en blanco.

Herramientas usadas: `pg_dump` + `psql` (vienen con la instalación de
PostgreSQL que ya pide `docs/instalacion.md`) y el Programador de tareas de
Windows. Nada nuevo que instalar aparte de eso.

---

## 1) Una sola vez, en el SERVIDOR (la PC fija del local)

### 1.1 Permitir conexiones desde la notebook

Por defecto, PostgreSQL solo acepta conexiones desde la propia PC. Hay que
habilitar la conexión desde la red local:

1. Ubicar `postgresql.conf` (normalmente en
   `C:\Program Files\PostgreSQL\<version>\data\postgresql.conf`) y
   verificar/ajustar:
   ```
   listen_addresses = '*'
   ```
2. En el mismo directorio, editar `pg_hba.conf` y agregar una línea para la
   subred del local (ajustar al rango real, típicamente `192.168.0.0/24` o
   `192.168.1.0/24`):
   ```
   host    ceramica_db    notebook_sync    192.168.0.0/24    scram-sha-256
   ```
3. Reiniciar el servicio de PostgreSQL (Servicios de Windows → `postgresql-x64-<version>` → Reiniciar).
4. Si Windows Firewall bloquea el puerto, permitir entrada al puerto de
   Postgres (por defecto `5432`) para la red privada/local.

### 1.2 Crear un usuario de solo lectura para el sync

No usar el usuario normal de la app (`ceramica_user`) para esto — la
notebook va a guardar esta contraseña en un archivo local, así que conviene
que ese usuario **no pueda escribir nada**.

**Doble clic en `sync_notebook\crear_rol_sync.bat`** (pide Administrador).
Genera una contraseña, crea el rol, verifica que pueda leer y que **no**
pueda escribir, y deja el bloque listo para pegar en
`sync_notebook\credenciales_sync.txt` (ese archivo está ignorado por git).

Para entrar como superusuario ofrece dos caminos:

1. **Con la contraseña de `postgres`** — `psql` la pide en el momento.
2. **Sin ella** (perdida u olvidada): antepone temporalmente una línea
   `trust` para `127.0.0.1` en `pg_hba.conf`, reinicia PostgreSQL, crea el
   rol y **restaura el archivo original** en un `finally`, pase lo que pase.
   Solo afecta conexiones desde la propia PC servidor y dura unos segundos.
   Igual deja una copia `.bak_<fecha>` del `pg_hba.conf` original.

Si se prefiere hacerlo a mano, es lo mismo que correr con `psql` como
superusuario:

```sql
CREATE ROLE notebook_sync WITH LOGIN PASSWORD 'elegir-una-contraseña-fuerte';
GRANT CONNECT ON DATABASE ceramica_db TO notebook_sync;
GRANT pg_read_all_data TO notebook_sync;
```

Anotar esa contraseña — se usa en el paso 2.2, en la notebook.

### 1.3 Fotos de productos — no hay nada que configurar

La base de datos guarda de cada foto solo la **ruta** del archivo
(`MEDIA_ROOT = backend/media`), nunca la imagen en sí. Si se sincroniza solo
la base, la notebook termina con el catálogo completo y **todos los
productos con la foto rota**.

Desde el 21/08/2026 el sync **baja las fotos por HTTP** del mismo servidor
que ya sirve `/media/` para las tablets. No hay que compartir carpetas, ni
crear usuarios de Windows, ni tocar permisos: si `SERVIDOR_HOST` está bien,
las fotos llegan solas.

> **Por qué se dejó de usar la carpeta compartida.** El proyecto vive dentro
> de `C:\Users\<usuario>` en la PC servidor, y el ACL NTFS de esa carpeta
> solo incluye a `SYSTEM`, `Administradores` y al dueño del perfil.
> Compartir `backend\media` con permiso "Todos: Leer" **no alcanza**: NTFS
> manda sobre el permiso del recurso compartido, y además Windows 11 bloquea
> el acceso invitado por SMB. Desde la notebook, que entra con otra cuenta de
> Windows, la carpeta contesta "acceso denegado" — y como las fotos son
> opcionales a propósito, el sync lo registraba como una advertencia y
> seguía: catálogo completo, 338 fotos rotas, y nadie se entera hasta que
> alguien abre el catálogo en la notebook. Bajarlas por HTTP saca del medio
> toda esa capa.

La carpeta compartida se sigue aceptando (`SERVIDOR_MEDIA_UNC` en
`config.env`): si está configurada **y** accesible, el sync la prefiere
porque la primera copia es más rápida. Si no responde, cae solo al HTTP. Lo
normal es dejar ese campo vacío.

### 1.4 Anotar la IP del servidor

La misma IP que ya se usa para las tablets (`docs/pwa_tablet.md`): en el
local es **`192.168.100.250`**, fijada en la propia PC servidor con
`fijar_ip.bat` porque el panel del router no es accesible (ver
`docs/instructivo_entrega_final.md`).

---

## 2) Una sola vez, en la NOTEBOOK

### 2.1 Tener PostgreSQL instalado localmente

Mismo paso que en `docs/instalacion.md` — la notebook necesita su propio
PostgreSQL corriendo (con una base `ceramica_db` vacía creada, igual que en
la instalación normal del servidor) para que el sync tenga algo donde
restaurar.

### 2.2 Configurar el sync

En la carpeta `sync_notebook/` del proyecto (esta misma que está en el
repo):

1. Copiar `config.env.example` como `config.env`.
2. Completar `SERVIDOR_HOST` con la IP del servidor (paso 1.4),
   `SERVIDOR_DB_PASSWORD` con la contraseña de `notebook_sync` (paso 1.2), y
   `LOCAL_DB_PASSWORD` con la contraseña del Postgres local de la notebook.
3. Dejar `SERVIDOR_MEDIA_URL` y `SERVIDOR_MEDIA_UNC` **vacíos** — las
   fotos se bajan solas por HTTP desde `SERVIDOR_HOST` (paso 1.3). Solo
   completar `SERVIDOR_MEDIA_URL` si el backend del servidor se movió a
   otro puerto o dirección.
4. Doble clic en `instalar_tarea_programada.bat`. Esto registra la tarea de
   Windows que corre el sync cada 5 minutos.

`config.env` no se sube al repositorio (tiene contraseñas) — queda solo en
esa notebook.

### 2.3 Probar que funciona

Con la notebook conectada a la red del local:

```bat
schtasks /run /tn "OgaPora - Sync Notebook"
```

Y revisar:
- `sync_notebook/logs/sync.log` → última línea debería decir
  "Sync completo — base local actualizada con los datos del servidor."
- `sync_notebook/estado/last_sync.json` → `"status": "ok"`

---

## Actualizar la base de la notebook al instante (`actualizar_notebook.bat`)

Además del sync automático cada 5 minutos, hay una herramienta para forzar
la actualización **en el momento**, sin esperar ni depender de la tarea
programada — por ejemplo, justo después de instalar una actualización del
sistema en el servidor y querer que la notebook quede al día ya mismo.

Doble clic en `sync_notebook/actualizar_notebook.bat`, estando la notebook
conectada a la misma red WiFi que el servidor. Usa el mismo `config.env` ya
configurado (paso 2.2) — no pide nada nuevo. Hace, en un solo paso: baja los
datos del servidor, **recrea la base local de cero** (mismo motivo que la
sección de abajo — evita tablas huérfanas) y restaura los datos ahí. Al
final queda un mensaje de éxito o de error con el detalle del problema en
`sync_notebook/tmp/` (`ultimo_dump.log`, `ultimo_recreate.log`,
`ultimo_restore.log`, según en qué paso haya fallado).

Es un archivo autónomo — no depende de `sync_notebook.ps1` ni hay que
copiar nada a mano para que funcione. Sirve para esta actualización y para
cualquier actualización futura del sistema: alcanza con volver a correr
este mismo archivo cada vez que haga falta traer los cambios más recientes
del servidor a la notebook.

## Actualizar la copia del script en la notebook

`sync_notebook.ps1` vive en el repo y se copia una vez a la notebook al
instalarlo (paso 2.2) — no se actualiza solo. Cada vez que se corrija este
script en el repo (como el cambio del 09/08/2026 de abajo), hay que volver
a copiar el archivo `sync_notebook/sync_notebook.ps1` actualizado a la
misma carpeta de la notebook (pisando el viejo), sin tocar `config.env`
(ese sí es local y no se toca). No hace falta reinstalar la tarea
programada — la va a tomar sola en la próxima corrida.

Esto solo afecta al **sync automático** cada 5 minutos. Si se prefiere
evitar la copia manual del script, alcanza con usar
`actualizar_notebook.bat` (arriba) cada vez que se necesite una
actualización — es independiente y no requiere pisar ningún archivo en la
notebook.

### 21/08/2026 — las fotos se bajan por HTTP, no por carpeta compartida

Armando el servidor definitivo en el local salió a la luz que la vía vieja
(robocopy contra `\\SERVIDOR\media`) **no podía funcionar** en esta
instalación: el proyecto está dentro de `C:\Users\<usuario>`, cuyo ACL NTFS solo
incluye a `SYSTEM`, `Administradores` y al dueño del perfil. El permiso
"Todos: Leer" del recurso compartido no alcanza porque NTFS es el más
restrictivo de los dos, y Windows 11 además bloquea el acceso invitado por
SMB. La notebook habría sincronizado los 393 productos con las 338 fotos
rotas, y el sync lo habría reportado como `ok` con una advertencia perdida en
el log — las fotos son opcionales a propósito y no hacen fracasar la corrida.

Ahora las fotos se bajan por HTTP del mismo `/media/` que ya consumen las
tablets (`sync_notebook/fotos_http.ps1`): la lista sale de la base recién
restaurada, se descarga solo lo que falta y se borra lo que ya no está en el
servidor. Sin cuentas de Windows, sin permisos NTFS, sin SMB.

Probado de punta a punta contra el servidor del local con una notebook
simulada: primera corrida 13,8 s con las 338 fotos y los conteos exactos
(393 productos, 425 variantes, 338 imágenes, 425 stock, 414 movimientos);
segunda corrida sin volver a bajar nada; y con un `SERVIDOR_MEDIA_UNC`
inaccesible cae solo al HTTP.

De paso se corrigió un problema que apareció en esa prueba: si la base local
de la notebook todavía no existe, `psql` escribe el aviso "no existe la base
de datos, omitiendo" por stderr y, con `$ErrorActionPreference = 'Stop'`,
PowerShell lo convertía en un error terminante que cortaba el sync entero
aunque el comando hubiera terminado bien. Los comandos externos ahora corren
a través de `Invoke-Nativo`, que sigue controlando el resultado real por
`$LASTEXITCODE`.

**Una sola vez, en la notebook:** copiar los `.ps1` actualizados de
`sync_notebook/` (ahora son dos: `sync_notebook.ps1` y `fotos_http.ps1`). Si
falta el segundo, el sync avisa en el log y sigue sin fotos.

### 09/08/2026 — la base local ahora se recrea de cero en cada sync

Antes, cada sync **restauraba encima** de la base ya existente en la
notebook. Si en algún momento el servidor borra una tabla o columna en una
migración (pasó el 09/08/2026 con el campo "Tipos de instalación"), esa
tabla le queda **huérfana** a la notebook — y la próxima vez que el dump
nuevo intenta recrear una tabla de la que esa huérfana depende (por
ejemplo "productos", por una foreign key), el restore se corta a la mitad
con un error de dependencias, dejando la base de la notebook a medio
actualizar (mezcla de esquema viejo y nuevo).

Ahora cada sync **borra y vuelve a crear** la base local completa antes de
restaurar, así nunca puede quedar un resto de una versión de esquema
anterior. Se probó localmente reproduciendo el escenario exacto (tabla
huérfana con foreign key a una tabla que el dump nuevo intenta recrear):
sin este cambio el restore fallaba con `cannot drop constraint ... because
other objects depend on it`; con el cambio, corre limpio.

Esto no necesita ningún cambio en `config.env` — usa las mismas
credenciales (`LOCAL_DB_USUARIO`/`LOCAL_DB_PASSWORD`) que ya estaban
configuradas, siempre que ese usuario tenga el atributo `CREATEDB` (se
verificó que `ceramica_user`, creado siguiendo `docs/instalacion.md`, ya
lo tiene). Si en alguna instalación puntual no lo tuviera, otorgarlo una
vez como superusuario:
```sql
ALTER ROLE ceramica_user CREATEDB;
```

**Una sola vez, en la notebook, antes de que corra el próximo sync
programado:** copiar el `sync_notebook.ps1` actualizado (ver arriba). Si
el sync ya corrió con el script viejo después de esta migración y quedó
en `status: "error"` con "psql (restore) falló", no hay ningún dato
corrupto que limpiar a mano — apenas se actualice el script, el próximo
sync se resuelve solo (recrea la base de cero).

---

## Diagnóstico rápido

- **`status: "omitido"` todo el tiempo, incluso en el local** → revisar que
  `SERVIDOR_HOST` en `config.env` sea la IP correcta y que el firewall del
  servidor no esté bloqueando el puerto de Postgres (paso 1.1.4).
- **`status: "error"` con "pg_dump falló"** → generalmente credenciales
  mal cargadas en `config.env`, o falta agregar la línea de `pg_hba.conf`
  (paso 1.1.2) para la IP/subred de la notebook.
- **`status: "error"` con "Recrear base local falló"** → revisar
  `sync_notebook/tmp/ultimo_recreate.log`; casi siempre falta el atributo
  `CREATEDB` en `LOCAL_DB_USUARIO` (ver sección de arriba) o
  `LOCAL_DB_PASSWORD` está mal en `config.env`.
- **`status: "error"` con "psql (restore) falló"** → revisar
  `sync_notebook/tmp/ultimo_restore.log` para el detalle exacto; con la
  base recreándose de cero en cada corrida, ya no debería deberse a
  esquemas desincronizados — más probable un problema real de datos en el
  dump.
- **El catálogo se ve completo pero sin fotos** → mirar la última línea de
  "Fotos sincronizadas" en `sync_notebook/logs/sync.log`. Si dice "fallaron",
  probar desde la notebook en el navegador
  `http://192.168.100.250:8000/media/` — si eso no abre, el problema es la
  red o que `iniciar.bat` no está corriendo en el servidor, no el sync.
  Si el log dice que falta `fotos_http.ps1`, copiar ese archivo a
  `sync_notebook/` en la notebook.
- **`actualizar_notebook.bat` termina con "ERROR"** → el mensaje en
  pantalla indica en qué paso falló; el detalle completo queda en
  `sync_notebook/tmp/ultimo_dump.log`, `ultimo_recreate.log` o
  `ultimo_restore.log` según corresponda (mismos archivos y mismas causas
  típicas que las tres entradas de arriba).
- **Desinstalar el sync** (por ejemplo, si se decide operar la notebook
  como una tablet más en vez de espejo local):
  ```bat
  schtasks /delete /tn "OgaPora - Sync Notebook" /f
  ```
