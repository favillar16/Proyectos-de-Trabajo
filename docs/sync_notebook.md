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

### 1.3 Anotar la IP del servidor

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
2. Completar `SERVIDOR_HOST` con la IP del servidor (paso 1.3),
   `SERVIDOR_DB_PASSWORD` con la contraseña de `notebook_sync` (paso 1.2), y
   `LOCAL_DB_PASSWORD` con la contraseña del Postgres local de la notebook.
3. Doble clic en `instalar_tarea_programada.bat`. Esto registra la tarea de
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

## Diagnóstico rápido

- **`status: "omitido"` todo el tiempo, incluso en el local** → revisar que
  `SERVIDOR_HOST` en `config.env` sea la IP correcta y que el firewall del
  servidor no esté bloqueando el puerto de Postgres (paso 1.1.4).
- **`status: "error"` con "pg_dump falló"** → generalmente credenciales
  mal cargadas en `config.env`, o falta agregar la línea de `pg_hba.conf`
  (paso 1.1.2) para la IP/subred de la notebook.
- **`status: "error"` con "psql (restore) falló"** → revisar
  `sync_notebook/tmp/ultimo_restore.log` para el detalle exacto; suele ser
  la base local (`LOCAL_DB_NOMBRE`) inexistente o credenciales locales
  incorrectas.
- **Desinstalar el sync** (por ejemplo, si se decide operar la notebook
  como una tablet más en vez de espejo local):
  ```bat
  schtasks /delete /tn "OgaPora - Sync Notebook" /f
  ```
