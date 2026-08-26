# Sincronización notebook ↔ servidor

**Última actualización:** 26/08/2026

## Qué resuelve

La propietaria carga mercadería y corrige precios en su notebook, a veces
estando fuera del local. Antes eso se perdía: el espejo era de una sola
dirección y el primer sync exitoso pisaba todo lo que se hubiera cargado ahí
(pasó de verdad — ver `docs/traspaso_pendientes.md`).

Ahora el catálogo viaja en los dos sentidos, y lo editado afuera espera
guardado hasta volver al local.

## El alcance, y por qué no es todo

| Datos | Dirección | Por qué |
|---|---|---|
| Productos, variantes, categorías, marcas, acabados, fotos, clientes, proveedores | **↔ los dos sentidos** | Es lo que se edita en la notebook. Se puede unir sin ambigüedad. |
| Stock y movimientos | → solo del servidor | `Stock.cantidad` es un **saldo corriente**, no un valor. Si el local vendió 10 cajas mientras la notebook estaba afuera y allá alguien tocó la cantidad, no existe un merge correcto: uno de los dos números está mal y nada puede saber cuál. |
| Ventas y caja | → solo del servidor | Mueven plata y stock reservado. `NotaPedido` usa `select_for_update()` porque está escrito para tener un solo dueño; dos equipos descontando del mismo stock sin verse producen sobreventa irreparable. |
| Facturación | → solo del servidor | `SecuenciaComprobante` numera comprobantes. Dos emisores del mismo número no es un problema de datos, es un problema con el DNIT. |
| Usuarios | → solo del servidor | Las contraseñas se administran en un solo lugar. |

Si algún día hace falta vender desde otro lado, la salida correcta es un
segundo punto de expedición habilitado, no un espejo que escribe.

## Cómo funciona

### Las dos mitades

```
   NOTEBOOK                                      SERVIDOR
   │                                             │
   │  1. sync_empujar  ── HTTP POST ──────────►  │  aplica el catálogo
   │     (solo catálogo)                         │  editado afuera
   │                                             │
   │  2. pg_dump + psql  ◄─────────────────────  │  base completa
   │     (reemplaza ceramica_db entera)          │  (incluye stock, ventas, caja)
```

**El orden no es negociable.** El paso 2 borra `ceramica_db` y la rehace. Si se
empujara después, se estaría empujando lo que el restore ya pisó.

### Por qué el registro de cambios vive en SQLite

Es la decisión que hace que todo lo demás funcione. `apps/sync` (`CambioSync`,
`ConflictoSync`, `EstadoSync`) **no vive en `ceramica_db`**: va en
`backend/sync.sqlite3`, con un router (`apps/sync/routers.py`).

Si viviera adentro de `ceramica_db`, cada restore exitoso borraría exactamente
lo que la notebook todavía no alcanzó a mandar. Al estar afuera, sobrevive.

SQLite y no otra base Postgres para que no haya un segundo servicio que
instalar, arrancar ni respaldar: es un archivo al lado del proyecto.

### La identidad: `uid`

Todo modelo sincronizable lleva `uid` (UUID), `actualizado_en` y `nodo_origen`
(mixin `ModeloSincronizable`).

**La clave primaria sigue siendo el entero de siempre.** El `uid` es una
identidad aparte, no un reemplazo: cambiar las PK a UUID obligaría a reescribir
cada FK, cada serializer, cada URL y los tickets impresos. El `uid` lo usa solo
el sync, y resuelve el problema real: la notebook offline crea el producto
id=454 y el local también, pero nunca el mismo UUID.

Por eso las filas viajan con las **claves foráneas expresadas por uid**: donde
el modelo dice `producto_id = 412`, el JSON lleva `producto: "<uuid>"`.

`actualizado_en` se fija en `save()` y no con `auto_now`, porque al aplicar un
cambio del otro nodo hay que **conservar la hora del equipo que lo hizo** — es
lo que decide el conflicto. Con `auto_now` se pisaría con la hora local y todo
cambio recién aplicado parecería el más nuevo del mundo.

## Conflictos

**Gana el cambio más reciente.** En un empate gana el servidor, porque es donde
trabaja todo el mundo y el que tiene el stock y las ventas atadas al catálogo.

Lo que pierde **no se tira**: queda en `ConflictoSync` con los dos lados
completos. Un rechazo silencioso es peor que una lista para revisar.

```
python manage.py sync_estado --conflictos
```

### Choques de unicidad

El `uid` resuelve la identidad, pero los modelos tienen además campos únicos
que cada base llena sola. Hay dos casos, y se resuelven al revés uno del otro:

| Caso | Campos | Qué se hace |
|---|---|---|
| **Es la misma cosa** | `Marca.nombre`, `Acabado.nombre`, `Categoria.nombre`, los atributos de una `Variante` | Se **fusionan**. "KLAUKOL" cargada en los dos lados no son dos marcas. La fila local adopta el uid que viene y los dos equipos quedan hablando de la misma. |
| **Son cosas distintas** | `Producto.codigo`, `Producto.slug`, `Variante.sku` | Se **regenera**. Los genera `save()` buscando el primer correlativo libre, así que dos equipos offline sacan POR-004 los dos. Al que llega se le da uno nuevo, y el cambio se informa. |
| **Error de carga** | `Variante.codigo_barras` | Ninguna de las dos. Es el EAN impreso en la caja: si dos variantes dicen tener el mismo, hay un error que ningún automatismo puede resolver. Entra en NULL y se anota. |

## Puesta en marcha

### 1. El token, en los dos equipos

Es un secreto compartido, **el mismo** en la PC servidor y en la notebook. No
se usa JWT de usuario a propósito: el agente corre solo, sin nadie que escriba
una contraseña, y darle un token de admin sería darle permiso sobre toda la API
para hacer una sola cosa.

```
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

En `backend/.env` de **los dos**:

```
SYNC_TOKEN=<el mismo valor en ambos>
```

Sin token, los endpoints de sync quedan cerrados. Es preferible que no anden a
que anden abiertos.

### 2. El rol de cada equipo

En `backend/.env`:

```
NODO_ROL=servidor      # en la PC del local
NODO_ROL=notebook      # en la notebook
```

No es cosmético: `sync_empujar` verifica que del otro lado haya un
`rol=servidor` antes de mandar nada, así la notebook no se sincroniza contra sí
misma ni contra otro espejo.

### 3. Migrar las dos bases

```
python manage.py migrate
python manage.py migrate --database=sync
```

La migración de identidad (`0006_identidad_sync` y compañía) va en tres pasos:
agrega `uid` sin restricción, le da un UUID distinto a cada fila y recién
entonces lo marca único. Agregarlo único de una vez le pone el **mismo** valor
a todas las filas y muere en el índice.

### 4. La tarea programada

```
sync_notebook\instalar_tarea_programada.bat
```

## Uso diario

Nada: la tarea corre sola cada 5 minutos y no hace ruido cuando la notebook
está fuera del local.

Para mirar cómo viene:

```
python manage.py sync_estado                 # resumen
python manage.py sync_estado --conflictos    # qué quedó sin aplicar
python manage.py sync_empujar --servidor ogapora.local --simular   # qué se mandaría
type sync_notebook\logs\sync.log             # el log del agente
```

### `sync_comparar` — el puente con lo anterior al sync

El registro de cambios solo tiene lo que pasó **desde que el sync está
instalado**. Lo que se editó antes es invisible para él, y el primer `pg_dump`
se lo lleva puesto. `sync_comparar` compara los dos catálogos fila por fila y,
con `--marcar`, anota las diferencias para que viajen:

```
python manage.py sync_comparar --servidor ogapora.local            # solo mirar
python manage.py sync_comparar --servidor ogapora.local --marcar   # marcar para mandar
```

Se usa una vez, al poner el sync en marcha (`docs/despliegue_servidor.md`, paso
2.2), y después cada vez que se sospeche que los dos equipos divergieron.
Compara los números como números: `"150000"` y `"150000.00"` son el mismo
precio y no cuentan como diferencia.

## Qué pasa si…

| Situación | Qué pasa |
|---|---|
| La notebook está fuera del local | El agente ve que el SSID no es el del negocio y ni lo intenta. Los cambios se van acumulando en `sync.sqlite3`. |
| El servidor cambió de IP | Se lo busca por nombre y, si hace falta, barriendo la subred (`docs/descubrimiento_red.md`). |
| Se corta el WiFi a mitad del empuje | Los lotes ya confirmados quedan marcados; el resto se reintenta solo en la próxima corrida. Máximo 500 cambios por lote. |
| Falla el empuje | **No se restaura la base.** Es preferible quedarse con datos viejos un rato más que perder ediciones que nunca llegaron al servidor. |
| Se editó lo mismo de los dos lados | Gana el más reciente; el otro queda en `sync_estado --conflictos`. |
| Una foto no sube | El producto igual llegó, le falta la imagen. Se avisa y se sigue. |

## Archivos

| Archivo | Qué hace |
|---|---|
| `apps/sync/models.py` | `CambioSync`, `ConflictoSync`, `EstadoSync` |
| `apps/sync/routers.py` | los manda a `sync.sqlite3` |
| `apps/sync/mixins.py` | `uid`, `actualizado_en`, `nodo_origen` |
| `apps/sync/registro.py` | qué se sincroniza y en qué orden |
| `apps/sync/signals.py` | anota cada edición local |
| `apps/sync/serializacion.py` | fila ↔ JSON, con FK por uid |
| `apps/sync/conciliacion.py` | choques de unicidad |
| `apps/sync/aplicar.py` | aplica un lote y resuelve conflictos |
| `apps/sync/views.py` | los tres endpoints |
| `apps/sync/cliente.py` | HTTP con `urllib`, sin dependencias nuevas |
| `management/commands/sync_empujar.py` | manda lo editado acá |
| `management/commands/sync_estado.py` | diagnóstico |
| `management/commands/sync_comparar.py` | compara los dos catálogos y marca diferencias |
| `sync_notebook/sync_notebook.ps1` | el agente: empuja y después restaura |

## Tests

```
python manage.py test apps.sync          # 51 tests
```

Cubren el registro de cambios y el rebote, la serialización con FK por uid, el
orden de dependencias, las reglas de conflicto, los choques de unicidad (que es
donde apareció el bug de `Producto.codigo` repetido) y los endpoints.
