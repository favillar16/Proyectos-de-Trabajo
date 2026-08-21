# Respaldo y migración del sistema

Cómo sacar una copia completa del sistema y cómo trasladarlo a otra PC —
por ejemplo, pasar todo lo cargado en el equipo de armado a la PC servidor
definitiva del local.

Herramientas: `respaldo\respaldo.bat` y `respaldo\restaurar.bat`.

---

## 1. Qué se respalda (y por qué son dos cosas)

Un respaldo del sistema son **siempre dos piezas juntas**:

| Pieza | Qué es | Dónde vive |
|---|---|---|
| Base de datos | Productos, stock, pedidos, ventas, caja, usuarios | PostgreSQL |
| Fotos de productos | Los archivos de imagen | `backend\media\` |

No alcanza con una sola, y este es el motivo: `ImagenProducto` e
`ImagenVariante` guardan en la base únicamente la **ruta** del archivo
(`MEDIA_ROOT = backend/media`), nunca la imagen. Entonces:

- Base sin fotos → catálogo completo con **todas las imágenes rotas**.
- Fotos sin base → archivos sueltos que nadie referencia.

`respaldo.bat` copia las dos y las guarda en la misma carpeta, para que no
se puedan separar por accidente.

> Esto también explica por qué las fotos de productos no van al repositorio
> de git: son datos del negocio, no código. El respaldo es el lugar donde
> tienen que estar.

---

## 2. Hacer un respaldo

En la PC servidor:

```bat
respaldo\respaldo.bat
```

Guarda en `respaldos\respaldo_AAAAMMDD_HHMMSS\`. Para guardar en un
pendrive o disco externo:

```bat
respaldo\respaldo.bat D:\
```

**No hace falta cerrar el sistema.** `pg_dump` toma una foto consistente de
la base aunque haya gente vendiendo en ese momento.

Cada respaldo queda así:

```
respaldo_20260820_143000\
  base_datos.sql     <- la base completa
  media\             <- todas las fotos
  info.json          <- fecha, equipo de origen, cantidad de fotos, commit
```

El `info.json` sirve para saber, meses después, de qué equipo y de qué
versión del sistema salió ese respaldo antes de restaurarlo en algún lado.

---

## 3. Migrar a la PC servidor definitiva

Este es el caso principal: todo lo cargado en el equipo de armado
(catálogo, fotos, usuarios) tiene que quedar en la PC que va a ser el
servidor del local.

### 3.1 En la PC nueva — instalación base

Primero la instalación normal, tal cual `docs/instalacion.md`:

1. Instalar **Python 3.11**, **Node 20 LTS** y **PostgreSQL 15**
   (agregando `C:\Program Files\PostgreSQL\15\bin` al PATH).
2. Copiar la carpeta del proyecto a la PC nueva.
3. Crear la base y el usuario en PostgreSQL, y armar `backend\.env` a
   partir de `backend\.env.example`.
4. Correr `setup.bat`.

Sí, `setup.bat` va a pedir crear un usuario administrador. Crearlo igual —
en el paso siguiente se reemplaza toda la base por la del respaldo, así que
ese usuario desaparece. Los usuarios buenos son los del equipo de origen.

### 3.2 Traer los datos

> Esto asume un pendrive. Si no hay uno a mano, saltar a **§3.5**:
> las fotos se trasladan por el repositorio de git y solo la base
> (~333 KB) viaja por otro medio.

1. En el **equipo de origen**: `respaldo\respaldo.bat D:\` (a un pendrive).
2. Llevar el pendrive a la PC nueva y copiar la carpeta
   `respaldo_AAAAMMDD_HHMMSS` completa.
3. En la **PC nueva**, con el sistema cerrado:
   ```bat
   respaldo\restaurar.bat D:\respaldo_20260820_143000
   ```
   Pide escribir `SI` para confirmar, porque borra y reemplaza la base de
   esa PC.

Sin argumentos (`restaurar.bat` a secas) toma el respaldo más nuevo de
`respaldos\`.

### 3.3 Verificar

1. `iniciar.bat`
2. Entrar con un usuario **del equipo de origen** (los de la PC nueva ya no
   existen).
3. Ir a Productos: tienen que estar todos, **con sus fotos**.
4. Ir a Inventario: el stock tiene que coincidir con el del equipo viejo.

### 3.4 Terminar de configurar el servidor

Una vez que los datos están:

1. **Reservar su IP en el router** — `guia_instalacion_dispositivos.md` §2.1
2. **Abrir los puertos en el firewall** — `docs/verificacion_red.md` §3
3. **Configurar la impresora** — `docs/pc_caja.md` §4
4. Reconfigurar los clientes que apuntaban a la IP vieja: tablets
   (`docs/pwa_tablet.md`) y notebook (`sync_notebook\config.env`).

---

### 3.5 Sin pendrive: las fotos por el repositorio

Si no hay pendrive a mano, la migración se parte en dos, porque las dos
piezas del respaldo tienen tamaños y sensibilidades muy distintas:

| Pieza | Tamaño | Cómo viaja |
|---|---|---|
| Fotos (`backend\media`) | ~35 MB, 338 archivos | **Por el repositorio de git** |
| Base de datos (`base_datos.sql`) | ~333 KB | Correo, Drive, WhatsApp Web — cualquier cosa |

Las fotos son la parte pesada y molesta de mover; la base entra en un
adjunto de correo. Por eso el reparto es ese y no al revés.

> **La base de datos no va al repositorio.** El repo del proyecto
> (`favillar16/Proyectos-de-Trabajo`) es **público**. Las fotos son el
> catálogo y publicarlas no cambia nada, pero el dump lleva clientes,
> ventas, precios de costo y los hashes de contraseña de los usuarios. Una
> vez subido a un repo público queda ahí aunque después se borre el commit.

**En el equipo de armado:**

```bat
respaldo\respaldo.bat        :: 1) respaldo normal, a respaldos\
respaldo\subir_fotos.bat     :: 2) commitea y sube backend\media a GitHub
```

`subir_fotos.bat` solo toca `backend\media` y `respaldo\fotos_manifiesto.json`
— cualquier otro cambio pendiente en el proyecto queda sin tocar. El
manifiesto anota cuántas fotos se subieron, para poder verificarlo del otro
lado.

Después, mandar **solo el `base_datos.sql`** de la carpeta
`respaldos\respaldo_AAAAMMDD_HHMMSS\` por el medio que sea. Son ~333 KB.

**En la PC servidor:**

1. Traer el proyecto con `git clone <url del repo> ceramica_final` — **el
   clone ya trae las fotos**, no hace falta nada más. Si el proyecto ya
   estaba copiado, correr `respaldo\traer_fotos.bat`, que hace el `pull` y
   verifica contra el manifiesto que estén las 338.
2. Instalación base normal (§3.1).
3. Poner el `base_datos.sql` recibido en una carpeta cualquiera, por
   ejemplo `C:\migracion\`, y restaurar:
   ```bat
   respaldo\restaurar.bat C:\migracion
   ```
   Va a avisar **"el respaldo no trae carpeta media"**. En este flujo está
   bien: las fotos ya llegaron por git y el restaurador no las borra.
4. Verificar como en §3.3 — productos **con foto** y stock.

**Cuando se cargan fotos nuevas después de migrar:** repetir
`subir_fotos.bat` en el equipo de origen y `traer_fotos.bat` en el
servidor. Pero ojo: una vez que el servidor definitivo está andando, el que
manda es él, y esto deja de ser un camino de ida y vuelta.

---

## 4. Lo que esto NO es

`restaurar.bat` **no** sirve para "pasarle los datos" a la PC de caja o a la
de depósito. Esas son clientes: no tienen base de datos propia y no deben
tenerla. El motivo está explicado en `docs/pc_caja.md` §1 — en resumen, dos
bases son dos stocks distintos, y eso termina en material vendido dos veces.

Para la notebook de la propietaria tampoco se usa esto: tiene su propio
mecanismo de espejo automático cada 5 minutos
(`docs/sync_notebook.md`).

---

## 5. Rutina de respaldo recomendada

El sistema no tiene respaldo automático — hay que correrlo.

**Mínimo:** un `respaldo.bat` a un pendrive **una vez por semana**, y
siempre antes de tocar algo grande (actualizar el sistema, mover la PC,
cambiar un disco).

**Mejor:** dejar el pendrive puesto y programar la tarea en Windows.
Programador de tareas → Crear tarea básica → diaria → Acción: iniciar
programa:

```
Programa:   C:\Users\usuario\ceramica_final\respaldo\respaldo.bat
Argumentos: D:\
```

Conservar al menos los últimos 4 respaldos antes de borrar los viejos. Los
respaldos no se borran solos.

> `respaldos\` está en `.gitignore`: son datos del negocio, no van al
> repositorio. Y un respaldo que vive en el mismo disco que el sistema no
> es un respaldo — sacarlo a un pendrive o disco externo.

---

## 6. Problemas

**"No se encontraron pg_dump.exe / psql.exe"**
PostgreSQL no está en el PATH. El script igual busca solo en
`C:\Program Files\PostgreSQL\*\bin`; si tampoco está ahí, agregar esa
carpeta al PATH del sistema.

**"pg_dump falló ... generó un archivo vacío"**
El servicio de PostgreSQL no está corriendo, o las credenciales de
`backend\.env` no son las correctas. Probar a mano:
`psql -U ceramica_user -d ceramica_db -c "SELECT 1;"`

**"No se pudo recrear la base ... permiso CREATEDB"**
El usuario de la app no puede crear bases. Desde psql como `postgres`:
```sql
ALTER ROLE ceramica_user CREATEDB;
```

**La restauración se corta con "database is being accessed by other users"**
Quedó el sistema abierto. Cerrar las dos ventanas negras de `iniciar.bat`
(y cualquier pgAdmin abierto) y volver a intentar.

**Restauré y los productos aparecen sin foto**
El respaldo se hizo sin la carpeta `media`, o se copió solo el
`base_datos.sql` en vez de la carpeta entera. Revisar `info.json`:
`fotos_cantidad` dice cuántas tenía que traer.

---

## Referencias

- `docs/instalacion.md` — instalación completa desde cero
- `docs/pc_caja.md` — por qué los clientes no llevan base de datos
- `docs/sync_notebook.md` — espejo automático de la notebook
- `docs/verificacion_red.md` — red y firewall
