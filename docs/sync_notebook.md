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
que ese usuario **no pueda escribir nada**. Ejecutar una vez, con `psql`
como superusuario:

```sql
CREATE ROLE notebook_sync WITH LOGIN PASSWORD 'elegir-una-contraseña-fuerte';
GRANT CONNECT ON DATABASE ceramica_db TO notebook_sync;
GRANT pg_read_all_data TO notebook_sync;
```

Anotar esa contraseña — se usa en el paso 2.2, en la notebook.

### 1.3 Compartir la carpeta de fotos (para que las imágenes no salgan rotas)

La base de datos guarda de cada foto solo la **ruta** del archivo
(`MEDIA_ROOT = backend/media`), nunca la imagen en sí. Si se sincroniza solo
la base, la notebook termina con el catálogo completo y **todos los
productos con la foto rota**, porque los archivos viven únicamente en la PC
servidor.

Para evitarlo hay que compartir esa carpeta una sola vez en el servidor:

1. En la PC servidor, ir a la carpeta del proyecto → `backend\media`.
2. Clic derecho → **Propiedades** → pestaña **Uso compartido** → **Uso
   compartido avanzado…**
3. Tildar **"Compartir esta carpeta"**, dejar el nombre del recurso como
   `media`.
4. **Permisos** → dejar solo **Leer** para el usuario que vaya a usar la
   notebook (o para `Todos`, si la red del local es cerrada). La notebook
   nunca necesita escribir acá.
5. Anotar la ruta de red resultante, por ejemplo `\\DESKTOP-UAIGET9\media`
   — se usa en el paso 2.2.

Es opcional: si se deja sin configurar, el sync de datos funciona igual y
solo se pierden las imágenes.

### 1.4 Anotar la IP del servidor

La misma IP que ya se usa para las tablets (`docs/pwa_tablet.md`). Conviene
reservarla como IP fija en el router (por MAC) para no tener que
reconfigurar nada si el DHCP la cambia.

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
3. Completar `SERVIDOR_MEDIA_UNC` con la ruta de red de las fotos
   (paso 1.3), por ejemplo `\\DESKTOP-UAIGET9\media`. Dejarlo vacío si se
   decidió no compartir esa carpeta — la notebook va a mostrar los
   productos sin imagen.
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
