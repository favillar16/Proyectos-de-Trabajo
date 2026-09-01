# Instructivo de despliegue — dejar el sistema terminado

**Fecha:** 26/08/2026
**Para:** poner en la PC servidor (`OGAPORA`) el descubrimiento por nombre y la
sincronización bidireccional, y dejar el sistema funcionando de punta a punta.

**Tiempo estimado:** 40–60 minutos, más el tiempo de las tablets.

---

## Antes de empezar

### Qué hay hoy y qué va a cambiar

| | Hoy | Después |
|---|---|---|
| Cómo se encuentra el servidor | IP fija `192.168.100.250`, escrita en cada equipo | Por nombre de red; si falla, se lo busca solo |
| Catálogo cargado en la notebook | Se pierde en el próximo sync | Viaja al servidor al volver al local |
| Stock, ventas, caja | Solo del servidor | Igual: solo del servidor (no se toca) |
| Sync de la notebook | Nunca corrió | Cada 5 minutos, automático |

### Lo que hace falta tener a mano

- [ ] Acceso físico o remoto a la PC servidor (`OGAPORA`)
- [ ] La contraseña de Windows de esa PC
- [ ] **El `SYNC_TOKEN` de la notebook.** Ya está generado. Para verlo:
      ```
      type C:\Users\usuario\ceramica_final\backend\.env | findstr SYNC_TOKEN
      ```
      Anotarlo: tiene que quedar **idéntico** en los dos equipos.
- [ ] Cómo se lleva el código al servidor: `git pull` si tiene el repo, o un
      pendrive con la carpeta del proyecto.

### Antes de tocar nada: un respaldo

En la **PC servidor**, con el sistema todavía funcionando:

```
cd C:\ceramica_final
respaldo\respaldo.bat D:\        :: a un pendrive
respaldo\respaldo.bat            :: sin pendrive: va a ..\respaldos\
```

Se puede correr con el sistema andando. Anotar la carpeta que crea
(`respaldo_AAAAMMDD_HHMMSS`). Si algo sale mal, `respaldo\restaurar.bat` vuelve
todo a este punto. **No saltear este paso.**

---

## PARTE 1 — La PC servidor

> Todo esto es en `OGAPORA`. Si algo falla, la sección "Si algo sale mal" del
> final dice cómo volver atrás.

### Paso 1.1 — Parar el sistema

Cerrar las dos ventanas negras (`Oga Pora - Servidor` y `Oga Pora - Interfaz`).
Verificar que quedaron cerradas:

```
netstat -ano | findstr ":8000 :5173"
```

No tiene que devolver nada. Si devuelve algo, cerrar esa ventana también.

### Paso 1.2 — Traer el código nuevo

Con repositorio:

```
cd C:\ceramica_final
git pull
```

Con pendrive: copiar **encima** las carpetas `backend\apps`, `backend\config`,
`frontend\src`, `frontend\vite.config.js`, `sync_notebook`, `docs`, `iniciar.bat`
y `.gitignore`.

> **No copiar `backend\.env`.** Ese archivo tiene la configuración propia de
> cada equipo (contraseña de la base, impresoras, datos fiscales). Se edita a
> mano en el paso siguiente.

### Paso 1.3 — Configurar el `.env` del servidor

Abrir `C:\ceramica_final\backend\.env` con el Bloc de notas y **agregar al
final**:

```
# ─── Identidad de este equipo en la red ──────────────────────────────────────
NODO_ROL=servidor
NODO_NOMBRE=
RED_WIFI_LOCAL=OGA PORA

# ─── Sincronización notebook ↔ servidor ──────────────────────────────────────
SYNC_TOKEN=<PEGAR ACÁ EL MISMO TOKEN QUE TIENE LA NOTEBOOK>
```

Tres cosas que importan:

- `NODO_ROL=servidor` **no es cosmético**: la notebook verifica que del otro
  lado haya un `rol=servidor` antes de mandarle nada. Si acá dice otra cosa, el
  sync se niega a funcionar (y está bien que se niegue).
- `NODO_NOMBRE=` vacío toma el nombre de Windows. Dejarlo vacío.
- El `SYNC_TOKEN` tiene que ser **carácter por carácter** el mismo que el de la
  notebook. Si no coincide, el servidor contesta 403 y no entra nada.

### Paso 1.4 — Migrar las bases

```
cd C:\ceramica_final\backend
venv\Scripts\activate
python manage.py migrate
python manage.py migrate --database=sync
```

El segundo comando crea `backend\sync.sqlite3`, el registro de cambios. Va en
un archivo aparte a propósito: el sync reemplaza `ceramica_db` entera, y si el
registro viviera adentro se borraría justo lo que falta mandar.

La migración `0006_identidad_sync` le pone un identificador único (`uid`) a
cada fila del catálogo. En un catálogo de ~450 productos tarda unos segundos.

**Verificar que no se perdió nada** (comparar con lo que había antes):

```
python manage.py shell -c "from apps.productos.models import Producto, Variante; from apps.inventario.models import Stock; print('productos', Producto.objects.count(), '| variantes', Variante.objects.count(), '| stock', Stock.objects.count())"
```

### Paso 1.5 — Comprobar la configuración

```
python manage.py sync_estado
```

Tiene que decir:

```
Este equipo
  nombre : OGAPORA
  rol    : servidor
  token  : configurado
```

Si dice `token : FALTA`, volver al paso 1.3.

### Paso 1.6 — Arrancar con el arranque nuevo

Cerrar la ventana de comandos y hacer doble clic en `iniciar.bat`.

> **El arranque cambió** y es importante entender por qué. Antes era
> `daphne -b 0.0.0.0`. Ahora son dos endpoints, IPv4 e IPv6:
>
> ```
> daphne -e tcp:8000:interface=0.0.0.0 -e tcp6:8000:interface=\:\: config.asgi:application
> ```
>
> Los nombres de red (`ogapora`, `ogapora.local`) resuelven **primero a IPv6**.
> Escuchando solo en IPv4, el navegador intenta IPv6, no encuentra a nadie y da
> timeout — aunque la IP funcione perfecto. Es el error más confuso de todos
> los que aparecieron armando esto.
>
> Si en algún momento alguien "arregla" esa línea volviéndola a `-b 0.0.0.0`,
> el acceso por nombre deja de andar y el síntoma no dice por qué.

### Paso 1.7 — Verificar el servidor

En la misma PC, en el navegador o en una ventana de comandos:

```
curl http://localhost:8000/api/v1/salud/
```

Tiene que contestar:

```json
{"sistema":"oga-pora","rol":"servidor","nombre":"OGAPORA","red_wifi":"OGA PORA","api":"v1",...}
```

Y que el nombre de red funcione desde la propia PC:

```
curl http://ogapora.local:8000/api/v1/salud/
```

Si el primero anda y el segundo da timeout, el arranque quedó sin el endpoint
IPv6 → revisar el paso 1.6.

---

## PARTE 2 — La notebook

### Paso 2.1 — Comprobar que ve al servidor

En la notebook, **conectada al WiFi del local**:

```
cd C:\Users\usuario\ceramica_final\sync_notebook
powershell -ExecutionPolicy Bypass -Command ". .\resolver_servidor.ps1; Find-Servidor -HostFijo auto | Format-List"
```

Tiene que devolver algo así:

```
Host      : ogapora.local
Identidad : @{sistema=oga-pora; rol=servidor; nombre=OGAPORA; ...}
Via       : nombre
```

`Via` dice por dónde lo encontró:

| `Via` | Significa |
|---|---|
| `nombre` | Lo ideal: por nombre de red |
| `cache` | Por el último que funcionó |
| `probables` | Por dirección probable o tabla ARP |
| `barrido` | Recorriendo la subred — funciona, pero conviene revisar por qué falló el nombre |

Si devuelve vacío: el servidor no está corriendo el código nuevo (volver a la
Parte 1) o la notebook no está en el WiFi del local.

### Paso 2.2 — Rescatar lo editado ANTES de que existiera el sync

> **Este es el paso más importante de todo el instructivo. No se saltea.**

El registro de cambios solo tiene lo que pasó **desde que el sync está
instalado** (26/08/2026). Todo lo que se editó en la notebook antes de eso es
invisible para él, y el paso 2.5 —que reemplaza la base de la notebook con la
del servidor— se lo lleva puesto sin avisar.

Eso ya pasó una vez: quedaron sin aplicar 7 nombres y los precios de
`ACC-048-OG` y `COC-032-OG` (`docs/traspaso_pendientes.md`). Hoy la notebook
tiene los valores corregidos y el servidor los viejos. Sin este paso, el primer
sync los revierte.

**Comparar los dos catálogos, sin tocar nada:**

```
cd C:\Users\usuario\ceramica_final\backend
venv\Scripts\activate
python manage.py sync_comparar --servidor ogapora.local
```

Muestra fila por fila qué difiere y de qué lado:

```
productos.Producto: 9 distintas, 0 solo acá
  ACC-048-OG
      precio_base: acá "126262.00"  ≠  servidor "97125.00"
  COC-032-OG
      precio_base: acá "1795274.00"  ≠  servidor "1380980.00"
  ...
```

**Ahora la decisión, mirando esa lista:**

| Si… | Qué hacer |
|---|---|
| Los valores de la notebook son los buenos | Repetir con `--marcar` |
| Los buenos son los del servidor | No hacer nada: el paso 2.5 los trae |
| Algunos de cada lado | `--marcar`, empujar, y corregir en el servidor los pocos que quedaron mal |

Para el caso de arriba (precios corregidos en la notebook, margen negativo en
el servidor), los buenos son los de la notebook:

```
python manage.py sync_comparar --servidor ogapora.local --marcar
```

Eso los anota en el registro para que viajen como cualquier otro cambio.

**Después, ver qué quedó listo para mandar:**

```
python manage.py sync_empujar --servidor ogapora.local --simular
```

Muestra el resumen sin mandar nada. Revisar que tenga sentido antes de seguir.

### Paso 2.3 — El primer empuje, a mano

```
python manage.py sync_empujar --servidor ogapora.local
```

Leer la salida. Si aparecen líneas en amarillo del tipo *"codigo venía como
GEN-076-OG, que ya estaba usado acá; se le asignó uno nuevo"*, es correcto y
esperado: los dos equipos generaron el mismo código para productos distintos, y
el que llegó se llevó uno nuevo. Conviene anotar cuáles para revisarlos después
en el sistema.

Si dice `0 en conflicto`, entró todo.

### Paso 2.4 — Revisar conflictos en el servidor

En la **PC servidor**:

```
python manage.py sync_estado --conflictos
```

Un conflicto significa que la misma fila se editó de los dos lados y ganó el
cambio más reciente. **Lo que perdió no se borró**, queda ahí con los dos lados
para poder compararlos y corregir a mano lo que corresponda.

### Paso 2.5 — El primer sync completo

> **Atención: este paso reemplaza la base de la notebook por la del servidor.**
> Por eso el empuje va antes. Si el paso 2.3 no salió bien, no seguir.

```
cd C:\Users\usuario\ceramica_final\sync_notebook
powershell -ExecutionPolicy Bypass -File .\sync_notebook.ps1
type logs\sync.log
```

El log tiene que terminar en `Sync completo — base local actualizada`.

### Paso 2.6 — Dejarlo automático

```
sync_notebook\instalar_tarea_programada.bat
```

Comprobar que quedó:

```
schtasks /query /tn "OgaPora - Sync Notebook"
```

Desde acá corre solo cada 5 minutos. Fuera del local no hace nada: mira el SSID
del WiFi y se omite sin tocar nada.

---

## PARTE 3 — Las tablets

### Lo que hay que saber antes

**Chrome en Android no resuelve nombres `.local`.** No es algo que se pueda
configurar: el navegador no tiene resolvedor mDNS. En las tablets hay que usar
la IP **una vez**, al instalar.

Eso no vuelve a atar las tablets a la IP. Una vez instalada, la PWA guarda el
shell de la app en el teléfono; si el servidor cambia de dirección, la app
arranca igual y **lo busca sola** recorriendo la red. La IP se usa para
instalar, no para funcionar.

### Paso 3.1 — Reinstalar la PWA en cada tablet

1. Abrir Chrome y entrar a `http://192.168.100.250:5173`
2. Menú ⋮ → **Instalar aplicación** (o "Agregar a pantalla de inicio")
3. Abrir la app instalada y entrar con el usuario de esa tablet
4. Comprobar que se ven los productos y que el buscador anda

> Si la tablet ya tenía la app instalada de antes, conviene desinstalarla y
> volver a instalarla, para que tome el código nuevo y no quede sirviendo el
> viejo desde la caché.

### Paso 3.2 — Probar que sobrevive a un cambio de dirección

Vale la pena hacerlo una vez, en **una** tablet, para saber que funciona:

1. Con la app abierta y andando, en el servidor: `ipconfig` y anotar la IP
2. Cerrar la app en la tablet
3. En el servidor, cambiar la IP a otra de la misma red (`fijar_ip.ps1 -IP 192.168.100.249`)
4. Abrir la app en la tablet: tarda unos segundos más y encuentra el servidor solo
5. Volver la IP a `192.168.100.250`

---

## PARTE 4 — Comprobación final

Marcar cada una:

**Servidor**
- [ ] `curl http://localhost:8000/api/v1/salud/` responde con `rol: servidor`
- [ ] `curl http://ogapora.local:8000/api/v1/salud/` responde igual
- [ ] `python manage.py sync_estado` dice `token : configurado`
- [ ] Se ven los productos en `http://localhost:5173`
- [ ] Los conteos de productos, variantes y stock son los de antes de migrar

**Notebook**
- [ ] `Find-Servidor -HostFijo auto` lo encuentra, idealmente `Via: nombre`
- [ ] Se ven los productos
- [ ] `schtasks /query /tn "OgaPora - Sync Notebook"` existe y está lista
- [ ] `sync_notebook\logs\sync.log` termina en `Sync completo`

**Tablets**
- [ ] Cada tablet abre la app y ve los productos
- [ ] Cada tablet entra con su usuario

**La prueba que vale por todas** — el circuito completo del sync:
- [ ] En la notebook, crear un producto de prueba llamado `PRUEBA DESPLIEGUE`
- [ ] Correr `sync_notebook\sync_notebook.ps1` a mano
- [ ] En el servidor, buscar `PRUEBA DESPLIEGUE` → **tiene que estar**
- [ ] Borrarlo desde el servidor
- [ ] Correr el sync otra vez → en la notebook **tiene que desaparecer**

Si esas cinco líneas pasan, el sistema está terminado.

---

## Si algo sale mal

| Síntoma | Causa más probable | Qué hacer |
|---|---|---|
| `curl` a `ogapora.local` da timeout pero a `localhost` anda | daphne quedó escuchando solo en IPv4 | Revisar que `iniciar.bat` tenga los dos `-e` (paso 1.6) |
| `Blocked request. This host is not allowed` | Vite viejo, o no se reinició | Copiar `frontend\vite.config.js` y reiniciar la ventana de la interfaz |
| `sync_empujar` dice `HTTP 403` | El `SYNC_TOKEN` no coincide | Comparar los dos `.env` carácter por carácter |
| `sync_comparar` marca cientos de filas | Se corrió antes de migrar el servidor, o contra el equipo equivocado | Verificar el paso 1.4 y volver a comparar sin `--marcar` |
| `sync_empujar` dice *"dice ser notebook, no el servidor"* | `NODO_ROL` mal en el servidor | Poner `NODO_ROL=servidor` y reiniciar el backend |
| `Find-Servidor` no devuelve nada | El servidor no tiene el código nuevo, o la notebook no está en el WiFi del local | Verificar el paso 1.7 y el SSID |
| El sync dice `omitido — Fuera de la red del local` | La notebook está en otra red | Es correcto. Conectarla al WiFi `OGA PORA` |
| La app no muestra productos | El backend no está corriendo | `netstat -ano \| findstr :8000`; si no hay nada, `iniciar.bat` |
| Faltan migraciones al arrancar | Se copió el código pero no se migró | `python manage.py migrate` y `migrate --database=sync` |

### Volver todo atrás

El código nuevo no borra ni cambia datos: solo **agrega** columnas (`uid`,
`actualizado_en`, `nodo_origen`) y una base SQLite aparte. Aun así, si hace
falta volver:

1. **Cerrar el sistema primero** — las dos ventanas negras de `iniciar.bat`.
   `restaurar.bat` borra y reemplaza la base; con el sistema abierto falla.
2. Restaurar y volver el código:

```
cd C:\ceramica_final
respaldo\restaurar.bat D:\respaldo_AAAAMMDD_HHMMSS
git checkout <commit anterior>          :: si se usó git
```

3. Arrancar de nuevo con `iniciar.bat`.

---

## Lo que queda pendiente después de esto

No hace falta para que el sistema funcione, pero sigue abierto:

- **Respaldo automático a Google Drive** — la decisión sigue abierta, está en
  `docs/todo_montaje_servidor.md` §7.
- **Facturación electrónica (SIFEN)** — esperando el certificado del DNIT.
  `SIFEN_HABILITADO=False` hasta entonces. Ver `docs/facturacion_electronica.md`.
- **Las 9 correcciones del 25/08** — se resuelven en el paso 2.2 con
  `sync_comparar --marcar`. Después del paso 2.3, confirmar en el servidor que
  `ACC-048-OG` y `COC-032-OG` quedaron con margen positivo.
- **Rotar las contraseñas demo** — decidido no hacerlo por ahora.

---

## Documentos relacionados

| Documento | Para qué |
|---|---|
| `docs/descubrimiento_red.md` | Cómo se encuentra al servidor sin IP; las dos trampas (IPv6 y Vite) |
| `docs/sync_bidireccional.md` | Cómo funciona el sync, el alcance y las reglas de conflicto |
| `docs/traspaso_pendientes.md` | Las correcciones que quedaron sin aplicar el 25/08 |
| `docs/sync_notebook.md` | La mitad servidor → notebook |
| `docs/instalacion.md` | Instalación desde cero |
| `docs/respaldo_y_migracion.md` | Respaldos y traslados |
| `docs/checklist_entrega.md` | Pruebas manuales de lo que no tiene tests |
