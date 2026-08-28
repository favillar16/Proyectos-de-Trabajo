# Checklist de entrega — Sistema de Gestión Comercial
## Óga Porã E.A.S. — revisado agosto 2026

**Tiempo estimado de ejecución:** 3–4 horas en la PC del negocio  
**Quién lo ejecuta:** desarrollador + una persona del negocio para las pruebas funcionales  
**Casos funcionales:** 76 (bloques 2 y 3)

---

## BLOQUE 1 — Instalación limpia (30 min)

Estos pasos se hacen UNA SOLA VEZ en la PC que va a ser el servidor.

### 1.1 Prerequisitos

- [ ] PostgreSQL 15 instalado y corriendo
- [ ] Python 3.11+ instalado
- [ ] Node.js 18+ instalado

Verificar en CMD:
```cmd
psql --version
python --version
node --version
```

> **Redis NO hace falta.** El channel layer de Django Channels es
> `InMemoryChannelLayer` (`backend/config/settings.py`), y alcanza porque corre
> un único proceso daphne. `channels-redis` figura en `requirements.txt` pero el
> código no lo usa. Solo haría falta si se corrieran varios workers en paralelo.

### 1.2 Base de datos

```cmd
psql -U postgres
CREATE DATABASE oga_pora;
\q
```

### 1.3 Entorno virtual e instalación de paquetes

```cmd
cd ceramica_final\backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**Paquetes críticos a verificar:**
```cmd
python -c "import django; print(django.__version__)"        ← debe ser 4.2.x
python -c "import channels; print(channels.__version__)"    ← debe ser 4.x
python -c "import win32print; print('OK')"                  ← para impresora térmica
```

### 1.4 Variables de entorno

Copiar `.env.example` a `.env` y completar:
```
SECRET_KEY=<generar con: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
DEBUG=True
DB_NAME=oga_pora
DB_USER=postgres
DB_PASSWORD=ceramica_pass_2025
IMPRESORA_TERMICA_NOMBRE=<nombre exacto desde Panel de control>
```

> **`ALLOWED_HOSTS` y CORS quedan abiertos a propósito.** No hay detección
> automática de IPs: `backend/config/settings.py` usa `ALLOWED_HOSTS=*` y
> `CORS_ALLOW_ALL_ORIGINS=True` por defecto, porque la tablet llama a la API
> por la IP LAN de la PC servidor y esa IP cambia según dónde se instale. Es
> deliberado para un appliance de red local cerrada, **no** para exponer a
> internet. Si el servidor tiene IP fija (ver `fijar_ip.bat`), reemplazar el
> `*` por esa IP en el `.env` es más seguro y no rompe nada.

### 1.5 Migraciones — PASO MÁS CRÍTICO

```cmd
python manage.py migrate
python manage.py showmigrations
```

Todas las líneas de `showmigrations` tienen que quedar en `[X]`. **Si queda
alguna en `[ ]`, el sistema no está listo** aunque arranque y se vea bien:
una migración sin aplicar rompe justo la operación que la necesita, no el
arranque.

> **Esto ya mordió una vez.** El 27/08/2026 la base del local tenía
> `productos.0005` y `0006` sin aplicar, y por eso **no se podía crear ningún
> producto**: cada alta moría con `null value in column "codigo_barras"`. El
> sistema abría, vendía y cobraba con normalidad; solo fallaba el alta. La
> migración `0005` ya está escrita para resolver ese caso sola, pero el
> `showmigrations` es lo que avisa antes de que pase.

No hace falta correr `makemigrations`: las migraciones están versionadas. Si
`makemigrations --check --dry-run` dice algo distinto de «No changes
detected», hay un modelo cambiado sin migrar y eso se resuelve **antes** de
seguir, no en el local.

Si aparece `django.db.utils.OperationalError`, verificar que PostgreSQL esté
corriendo y que los datos del `.env` sean correctos.

### 1.6 Datos iniciales y demo

```cmd
python manage.py loaddata initial_data.json
python cargar_demo.py
```

El script debe imprimir al final:
```
  Productos creados:   18
  Total variantes:     52+
  Sistema listo para la demo.
```

> ⚠️ **Esto es solo para una instalación limpia de demostración.** El servidor
> del local **no** corre con estos datos: tiene el catálogo real. Si estás
> probando **contra la base real, saltá este paso**: `cargar_demo.py` agregaría
> 18 productos de fantasía al catálogo del negocio. La carga real se hace con
> `docs/carga_final/` (ver su `README.md`).

### 1.7 Crear superusuario admin

```cmd
python manage.py createsuperuser
```
Usar: username=`admin`, password segura para producción.

### 1.8 Frontend

```cmd
cd ..\frontend
npm install
npm run dev
```

Abrir `http://localhost:5173` — debe aparecer la pantalla de login.

---

## BLOQUE 2 — Pruebas funcionales por módulo (90 min)

Ejecutar con el usuario `vendedor / demo2025` salvo que se indique otro.

### 2.1 Autenticación

| # | Prueba | Esperado | OK |
|---|--------|----------|:--:|
| 1 | Login con `vendedor / demo2025` | Entra al sistema, ve el showroom | ☐ |
| 2 | Login con credenciales incorrectas | Mensaje de error, no entra | ☐ |
| 3 | Cerrar sesión y volver a entrar | Funciona sin errores | ☐ |
| 4 | Con `admin / demo2025`, ir a `/usuarios` | Ve la lista de usuarios | ☐ |
| 5 | Con `cajero / demo2025`, intentar ir a `/usuarios` | Redirige o muestra error de acceso | ☐ |

### 2.2 Showroom

| # | Prueba | Esperado | OK |
|---|--------|----------|:--:|
| 6 | Abrir showroom | Grid con productos y fotos (si se cargaron) | ☐ |
| 7 | Filtrar por "Porcelanatos" | Solo productos de esa categoría | ☐ |
| 8 | Activar "Con stock" | Desaparecen los sin stock | ☐ |
| 9 | Tocar una card de producto | Abre panel lateral con galería y stock | ☐ |
| 10 | Deslizar entre fotos en el panel | Funciona con touch y con click | ☐ |
| 11 | Tocar el botón de zoom de una foto | Abre lightbox fullscreen | ☐ |
| 12 | Botón flotante de scanner (abajo derecha) | Abre consulta rápida de stock | ☐ |
| 13 | Escribir "POR" en la consulta | Muestra resultados con stock agrupados | ☐ |
| 14 | Escribir un SKU exacto, copiado de la pantalla de Productos | Aparece primero en resultados | ☐ |
| 15 | En tablet, rotar a portrait | La UI se adapta, panel detalle desde abajo | ☐ |

### 2.3 Catálogo de productos

| # | Prueba | Esperado | OK |
|---|--------|----------|:--:|
| 16 | Ir a Productos (como admin) | Grid con stats de catálogo | ☐ |
| 17 | Crear nuevo producto (3 pasos) | Se crea y aparece en el grid | ☐ |
| 18 | Agregar una variante con stock inicial 10 | El stock queda en 10 | ☐ |
| 19 | Subir una imagen desde el paso 3 | La imagen aparece en el showroom | ☐ |
| 20 | Con rol `cajero`, intentar crear producto | Acceso denegado (403) | ☐ |

### 2.4 Flujo completo de venta (prueba más importante)

Ejecutar con 3 ventanas abiertas: una como vendedor, una como depósito, una como cajero.

| # | Prueba | Esperado | OK |
|---|--------|----------|:--:|
| 21 | **Vendedor:** ir a Pedidos → Nuevo pedido | Abre formulario en panel derecho | ☐ |
| 22 | Buscar un producto del catálogo y agregar 2 variantes | Aparecen en el carrito con precio | ☐ |
| 23 | Enviar al depósito y caja | Mensaje de éxito, aparece en la lista | ☐ |
| 24 | **Depósito** (en otra ventana): aparece el pedido | Notificación y pedido visible sin recargar | ☐ |
| 25 | Depósito marca ambos ítems como preparados (✓) | Se iluminan en verde | ☐ |
| 26 | Depósito presiona "Marcar como listo para cobrar" | Estado cambia a "Listo" | ☐ |
| 27 | **Cajero** (en otra ventana): aparece el pedido | Notificación y pedido en la cola izquierda | ☐ |
| 28 | Cajero selecciona el pedido, elige "Efectivo" | Muestra monto y atajos de billetes | ☐ |
| 29 | Ingresar monto mayor al total | Muestra el vuelto correctamente | ☐ |
| 30 | Confirmar pago | Ticket aparece en pantalla | ☐ |
| 31 | Verificar en Inventario: el stock bajó | La cantidad disminuyó exactamente | ☐ |
| 32 | **Vendedor:** el pedido aparece como "Pagado" | Sin recargar la página | ☐ |

### 2.5 Control de stock y reservas

| # | Prueba | Esperado | OK |
|---|--------|----------|:--:|
| 33 | Buscar variante con stock=1 en el showroom | Muestra "1 disponible" | ☐ |
| 34 | Crear pedido por esa 1 unidad (sin confirmar) | Stock disponible baja a 0 en el showroom | ☐ |
| 35 | Intentar crear otro pedido por la misma unidad | Error: stock insuficiente | ☐ |
| 36 | Cancelar el primer pedido | El stock vuelve a 1 disponible | ☐ |
| 37 | Ir a Inventario y hacer ajuste manual (+5 cajas) | El stock sube correctamente | ☐ |
| 38 | Bajar el stock a 0 con un ajuste de salida | Aparece alerta "Sin stock" en el panel | ☐ |

### 2.6 Módulo de caja

| # | Prueba | Esperado | OK |
|---|--------|----------|:--:|
| 39 | Entrar como cajero a `/caja` | Muestra pantalla de apertura | ☐ |
| 40 | Abrir caja con Gs. 500.000 | Cambia a pantalla de cola de pedidos | ☐ |
| 41 | Ver lista de pedidos listos | Aparecen los marcados como "Listo" | ☐ |
| 42 | Cobrar con tarjeta de débito | No pide monto recibido ni vuelto | ☐ |
| 43 | Cobrar con efectivo, ingresar billete redondo | Calcula vuelto al instante | ☐ |
| 44 | El ticket aparece después del pago | Datos correctos: cliente, ítems, total, vuelto | ☐ |
| 45 | Botón "Reimprimir" | Envía a la impresora nuevamente | ☐ |
| 46 | Cerrar caja | Muestra resumen del día por medio de pago | ☐ |

### 2.7 Impresora térmica

| # | Prueba | Esperado | OK |
|---|--------|----------|:--:|
| 47 | Ejecutar `python diagnostico_impresora.py` | Lista la impresora FTX FTXP-80W | ☐ |
| 48 | Confirmar un pago en caja | Ticket sale de la impresora automáticamente | ☐ |
| 49 | Desconectar la impresora y confirmar pago | El pago se registra igual, aparece alerta | ☐ |
| 50 | Reconectar y usar "Reimprimir" | El ticket sale sin crear un pago duplicado | ☐ |

### 2.8 Dashboard (solo admin)

| # | Prueba | Esperado | OK |
|---|--------|----------|:--:|
| 51 | Entrar como admin al dashboard | Muestra KPIs, gráfico y feed de ventas | ☐ |
| 52 | Cambiar entre 7d / 30d / 90d | Los números y el gráfico cambian | ☐ |
| 53 | Con ventas recién hechas, aparecen en el feed | Las últimas ventas se ven abajo | ☐ |
| 54 | Clic en "Ver inventario" desde alerta de stock | Filtra a "Sin stock" automáticamente | ☐ |

### 2.9 Gestión de usuarios (solo admin)

| # | Prueba | Esperado | OK |
|---|--------|----------|:--:|
| 55 | Crear usuario nuevo con rol Cajero | Aparece en la lista | ☐ |
| 56 | Login con el nuevo usuario | Accede solo a módulos de cajero | ☐ |
| 57 | Cambiar contraseña del nuevo usuario | El usuario puede loguearse con la nueva | ☐ |
| 58 | Desactivar el nuevo usuario | No puede loguearse, aparece como Inactivo | ☐ |
| 59 | Intentar cambiar tu propio rol de admin | El sistema lo impide con mensaje de error | ☐ |

### 2.10 Ayuda contextual (F1 y botón «?»)

| # | Prueba | Esperado | OK |
|---|--------|----------|:--:|
| 60 | En cualquier pantalla, apretar **F1** | Abre el panel de ayuda de esa pantalla, y Chrome **no** abre la suya | ☐ |
| 61 | Con el panel abierto, apretar Escape | Se cierra | ☐ |
| 62 | En la tablet (sin teclas de función), tocar el botón «?» flotante | Abre el mismo panel | ☐ |
| 63 | Abrir la ayuda de la misma pantalla con dos roles distintos | El contenido cambia según el rol | ☐ |

> El caso 60 es el único que **no** se puede cubrir con tests automatizados: que
> Chrome respete el `preventDefault()` es comportamiento del navegador. Los otros
> tres están cubiertos por `cd frontend && npm test`.

---

## BLOQUE 3 — Pruebas de red y múltiples dispositivos (30 min)

### 3.1 Configurar acceso en red local

En el servidor (PC principal), agregar la IP local al `.env`:
```
ALLOWED_HOSTS=localhost,127.0.0.1,<IP-del-servidor>
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://<IP-del-servidor>:5173
CORS_ALLOW_ALL_ORIGINS=False
```

Reiniciar el backend.

### 3.2 Conectar desde las tablets y otras PCs

| # | Prueba | Esperado | OK |
|---|--------|----------|:--:|
| 64 | Abrir `http://<IP>:5173` en la Redmi Pad SE | Muestra el sistema sin errores | ☐ |
| 65 | Login desde la tablet | Funciona igual que en el servidor | ☐ |
| 66 | Abrir el showroom en la tablet (portrait) | Cards adaptadas, nav bar abajo | ☐ |
| 67 | Hacer swipe en la galería de fotos | Funciona correctamente con el dedo | ☐ |
| 68 | Desde la tablet: crear un pedido | En la PC del depósito aparece sin recargar | ☐ |
| 69 | Dos usuarios navegando simultáneamente | El sistema responde sin lentitud | ☐ |

### 3.3 Periféricos — impresora

Detalle de instalación y problemas comunes en **`docs/perifericos.md`**.

Antes de empezar, correr el diagnóstico: `python diagnostico_impresora.py`.
Lista las impresoras instaladas y avisa si el nombre del `.env` no coincide.

> **El sistema de código de barras se retiró el 26/08/2026.** El lector FTX
> LC123BH5 y la Epson L1250 ya no forman parte del sistema, así que las pruebas
> 66 a 83 de la versión anterior de este checklist quedaron sin objeto.

**Térmica FTX FTXP-80W** — tickets y comprobantes de mostrador.

| # | Prueba | Esperado | OK |
|---|--------|----------|:--:|
| 70 | Instalarla en Panel de control y copiar su nombre exacto a `IMPRESORA_TERMICA_NOMBRE` | `diagnostico_impresora.py` la marca como disponible | ☐ |
| 71 | En el diagnóstico, aceptar el ticket de prueba | Sale el ticket y corta el papel | ☐ |
| 72 | Cobrar un pedido de prueba desde Caja | El ticket sale solo al confirmar el pago | ☐ |
| 73 | Reimprimir ese mismo ticket desde la lista de pagos | Sale idéntico al original | ☐ |
| 74 | Cerrar la sesión de caja | Sale el ticket de cierre con los totales | ☐ |
| 75 | Cargar los datos fiscales del `.env` (ver `docs/carga_final/datos_fiscales.md`) y correr `python manage.py verificar_fiscal` | Quedan marcados solo los códigos SIFEN y el certificado — ver la nota de abajo | ☐ |
| 76 | Cobrar eligiendo «factura» y mirar el papel que sale | Sale con RUC 80173107-0. **Que diga o no un timbrado depende de la decisión pendiente** | ☐ |

> ⚠️ **Óga Porã emite por la solución gratuita del DNIT (e-Kuatia'i), que no
> tiene API.** La factura electrónica se carga a mano en el portal: **este
> sistema no la emite**, y `SIFEN_HABILITADO` se queda en `False`.
>
> Por eso el caso 71 **no** puede terminar sin faltantes: los códigos SIFEN de
> departamento/distrito/ciudad y el certificado son datos de la solución
> propia, que no aplica.
>
> Y el caso 72 depende de una decisión abierta: el timbrado **18936285**
> pertenece a los documentos del portal, no a un papel impreso por esta PC, y
> el negocio **no está habilitado como autoimpresor**. Ver
> `docs/carga_final/datos_fiscales.md`.

---

## BLOQUE 4 — Ajustes de configuración para producción (15 min)

Estos cambios se hacen ANTES de la entrega definitiva.

### 4.1 En `backend/.env`

El `.env` **no está versionado**: cada máquina tiene el suyo, así que este
bloque hay que hacerlo en la PC servidor aunque ya esté hecho en la notebook.

```env
# Cambiar:
DEBUG=False
SECRET_KEY=<clave larga y aleatoria generada con get_random_secret_key()>
CORS_ALLOW_ALL_ORIGINS=False
CORS_ALLOWED_ORIGINS=http://<IP-servidor>:5173,http://localhost:5173
ALLOWED_HOSTS=localhost,127.0.0.1,<IP-servidor>

# Verificar:
DB_PASSWORD=<contraseña fuerte, no la de demo>
SIFEN_HABILITADO=False
```

> **`DEBUG=False` importa más de lo que parece.** Con `DEBUG=True` cualquier
> error 404 o 500 devuelve una página de Django con el URLconf completo y el
> traceback. En una red WiFi de local eso lo ve cualquiera que se conecte.
> Después de cambiarlo hay que correr el paso 4.2 sí o sí: sin
> `collectstatic`, con `DEBUG=False` el `/admin/` responde 500.

> **`SIFEN_HABILITADO` tiene que quedar en `False` hasta que esté el
> certificado.** En `True` el sistema numera las facturas con el correlativo
> oficial `001-001-NNNNNNN` e imprime el CDC con la leyenda «consulte este
> documento en ekuatia.set.gov.py» — pero todavía no hay certificado ni
> worker que transmita, así que ese CDC no existiría en el portal y el
> correlativo empezaría a correr sin respaldo. Con `False` la caja funciona
> igual que siempre: ticket y factura impresa con RUC y timbrado.
> Verificar con `python manage.py verificar_fiscal`.

### 4.2 Colectar archivos estáticos

```cmd
python manage.py collectstatic --noinput
```

### 4.3 Cuentas del personal

Dos cosas distintas:

1. **Contraseñas.** Desde la interfaz de Usuarios (como admin), cambiar las de
   `admin` y las de cualquier cuenta de demo que se vaya a usar de verdad, por
   contraseñas reales elegidas con el negocio.
2. **Cuentas activas.** Al 27/08/2026 las únicas cuentas activas son `admin`,
   `Administrador` y `juanperez1` (encargada de ventas). Las de `vendedor`,
   `cajero` y `deposito` están **desactivadas**, y las `_test_*` son restos de
   pruebas. Sin una cuenta activa por cada persona que va a atender, el primer
   día nadie puede entrar. Dar de alta las reales y borrar las `_test_*`.

Para ver el estado:

```cmd
python manage.py shell -c "from apps.usuarios.models import Usuario; [print(u.username, u.rol, u.activo) for u in Usuario.objects.order_by('username')]"
```

### 4.4 Verificación final de settings

```cmd
python manage.py check --deploy
```

Este comando informa de configuraciones inseguras para producción.

**Lo esperado hoy son 4 warnings, y los 4 se aceptan a propósito:**

| Warning | Por qué se acepta |
|---|---|
| `security.W004` (HSTS) | El sistema corre por HTTP en la LAN, sin certificado |
| `security.W008` (SSL redirect) | idem — redirigir a HTTPS dejaría todo el local sin acceso |
| `security.W012` (`SESSION_COOKIE_SECURE`) | idem |
| `security.W016` (`CSRF_COOKIE_SECURE`) | idem |

Los cuatro salen de la misma decisión de diseño: es un appliance de red local
sin internet, no un sitio expuesto. **Si aparece un warning distinto de esos
cuatro, hay que mirarlo.**

---

## BLOQUE 5 — Carga inicial de productos reales (variable)

Este bloque lo ejecuta el personal del negocio con ayuda.

### 5.1 Plan de carga

El lote de compras de agosto 2026 (26 facturas, 184 líneas) **no se carga a
mano**: está transcripto en `docs/carga_final/productos_a_cargar.csv` y entra
con un comando.

```cmd
python manage.py cargar_lote_facturas --margen 40 --dry-run
```

El `--dry-run` hace la carga completa y la deshace, así que muestra exactamente
lo que va a pasar. Leer la salida, y recién entonces correrlo sin `--dry-run`.
El detalle de las opciones (margen por rubro, redondeo, qué filas se saltean y
por qué) está en `docs/carga_final/README.md`.

**Antes de correrlo hay que definir el margen de venta**: el CSV solo trae
precios de costo. Sin `--margen` el comando se niega a correr, a propósito.

Lo que quede fuera del lote —los 6 datos ilegibles y las 8 decisiones de
negocio de `docs/carga_final/pendientes_verificacion.md`— se carga a mano:

1. Para cada producto: nombre, categoría, precio, foto (desde el celular)
2. Cargar variantes con dimensiones y stock real del depósito

### 5.2 Fotografía de productos

- Resolución mínima recomendada: 800×800 px
- Formato: JPG o WebP
- Fondo: blanco o neutro uniforme
- Subir desde la sección Productos → Nuevo producto → Paso 3 (imágenes)

### 5.3 Inventario inicial

Después de cargar los productos, ingresar el stock real desde el módulo de Inventario → Ajuste → Entrada de mercadería para cada variante.

---

## Problemas conocidos y soluciones

### "No se puede conectar a la base de datos"
Verificar que PostgreSQL esté corriendo:
```cmd
net start postgresql-x64-15
```

### "WebSocket no conecta" (pedidos no se actualizan en tiempo real)
**No es Redis** — el sistema no lo usa. Casi siempre es una de estas dos:

1. **Se arrancó con `runserver` en vez de `daphne`.** `runserver` solo sirve
   HTTP: los pedidos y las alertas de stock no se actualizan solos. Usar
   `iniciar.bat`, o a mano:
   ```cmd
   daphne -b 0.0.0.0 -p 8000 config.asgi:application
   ```
2. **El equipo perdió el WiFi.** El hook de WebSocket reintenta solo con
   backoff (2 s → 30 s), así que puede tardar hasta medio minuto en volver.

### "La impresora no imprime" (térmica)
1. Ejecutar `python diagnostico_impresora.py`
2. El nombre en `.env` debe coincidir **exactamente** con el nombre en Panel de control → Dispositivos e impresoras
3. Si funciona desde Notepad pero no desde el sistema, es un problema de permisos del puerto: ejecutar el servidor Django como administrador

### "Error 403 Forbidden en la API"
El usuario no tiene el rol necesario para esa acción. Verificar en Usuarios que el rol asignado sea el correcto.

### "Error de migración: relation already exists"
La tabla ya existía de una ejecución anterior. Ejecutar:
```cmd
python manage.py migrate --fake-initial
```

### El frontend muestra "Error de conexión"
Verificar que el backend esté corriendo en el puerto 8000 — con `iniciar.bat`
(recomendado) o a mano con Daphne:
```cmd
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```
`python manage.py runserver` también responde en ese puerto, pero solo sirve
HTTP: si el error de conexión era en realidad falta de actualizaciones en
vivo (pedidos, alertas de stock), `runserver` no lo va a arreglar porque no
soporta WebSocket — hace falta Daphne.

---

## Lista de entregables

- [ ] ZIP con el código fuente completo (`ceramica_final.zip`)
- [ ] Este documento de checklist completado con ✓ en cada prueba
- [ ] IP de la PC servidor reservada en el router (`guia_instalacion_dispositivos.md` §2) —
      sin esto, un reinicio del router puede dejar tablets y PCs sin acceso
- [ ] Contraseñas del sistema entregadas al propietario por escrito
- [ ] Capacitación de 1 hora con cada rol (vendedor, cajero, depósito)
- [ ] Manual de usuario en formato PDF (pendiente)

---

*Última revisión: 27/08/2026 — se corrigieron los pasos que ya no coincidían con
el sistema real (Redis, nombre de la base, `ALLOWED_HOSTS`/CORS, datos de demo)
y se agregaron los casos de la ayuda contextual. El lector de código de barras
y la Epson L1250 quedaron fuera del alcance el 26/08 y no tienen casos.*
