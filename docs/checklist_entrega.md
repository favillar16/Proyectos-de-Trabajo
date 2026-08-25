# Checklist de entrega — Sistema de Gestión Comercial
## Cerámicas & Sanitarios — Mayo 2025

**Tiempo estimado de ejecución:** 3–4 horas en la PC del negocio  
**Quién lo ejecuta:** desarrollador + una persona del negocio para las pruebas funcionales

---

## BLOQUE 1 — Instalación limpia (30 min)

Estos pasos se hacen UNA SOLA VEZ en la PC que va a ser el servidor.

### 1.1 Prerequisitos

- [ ] PostgreSQL 15 instalado y corriendo
- [ ] Python 3.11+ instalado
- [ ] Node.js 18+ instalado
- [ ] Redis 7+ instalado (necesario para WebSocket / Django Channels)

Verificar en CMD:
```cmd
psql --version
python --version
node --version
redis-cli ping   ← debe responder PONG
```

### 1.2 Base de datos

```cmd
psql -U postgres
CREATE DATABASE ceramica_db;
CREATE USER ceramica_user WITH PASSWORD 'ceramica_pass_2025';
GRANT ALL PRIVILEGES ON DATABASE ceramica_db TO ceramica_user;
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
DB_NAME=ceramica_db
DB_USER=ceramica_user
DB_PASSWORD=ceramica_pass_2025
IMPRESORA_TERMICA_NOMBRE=<nombre exacto desde Panel de control>
```

### 1.5 Migraciones — PASO MÁS CRÍTICO

```cmd
python manage.py makemigrations usuarios
python manage.py makemigrations productos
python manage.py makemigrations inventario
python manage.py makemigrations ventas
python manage.py makemigrations caja
python manage.py migrate
```

Verificar que no haya errores. Si aparece `django.db.utils.OperationalError`, verificar que PostgreSQL esté corriendo y los datos del `.env` sean correctos.

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
| 14 | Escribir un SKU exacto (ej: `POR-001-BEI-1`) | Aparece primero en resultados | ☐ |
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
| 22 | Buscar "Porcelanato Roma" y agregar 2 variantes | Aparecen en el carrito con precio | ☐ |
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
| 60 | Abrir `http://<IP>:5173` en la Redmi Pad SE | Muestra el sistema sin errores | ☐ |
| 61 | Login desde la tablet | Funciona igual que en el servidor | ☐ |
| 62 | Abrir el showroom en la tablet (portrait) | Cards adaptadas, nav bar abajo | ☐ |
| 63 | Hacer swipe en la galería de fotos | Funciona correctamente con el dedo | ☐ |
| 64 | Desde la tablet: crear un pedido | En la PC del depósito aparece sin recargar | ☐ |
| 65 | Dos usuarios navegando simultáneamente | El sistema responde sin lentitud | ☐ |

### 3.3 Periféricos — lector de código de barras e impresoras

Detalle de instalación y problemas comunes en **`docs/perifericos.md`**.

Antes de empezar, correr el diagnóstico: `python diagnostico_impresora.py`.
Lista las impresoras instaladas y avisa si el nombre del `.env` no coincide.

**Lector FTX LC123BH5** — se enchufa el receptor USB y listo, no hay driver.
Guía completa en **`docs/LECTOR_CODIGO_BARRAS.md`**.

| # | Prueba | Esperado | OK |
|---|--------|----------|:--:|
| 66 | Escanear cualquier código en el Bloc de notas | Escribe el código y baja un renglón (si no baja el renglón, al lector le falta el sufijo Enter) | ☐ |
| 67 | Asignar códigos internos: `python manage.py asignar_codigos_barras --simular` | Lista las variantes sin código, sin escribir nada | ☐ |
| 68 | Correrlo de verdad, sin `--simular`, **en la PC servidor** | Asigna un EAN-13 con prefijo 200 a cada una | ☐ |
| 69 | Escanear una caja con EAN de fábrica en Productos → ficha → «Código de barras» | El campo se completa solo | ☐ |
| 70 | Guardar y escanear ese mismo código en la consulta rápida de stock | Deja la búsqueda hecha y muestra esa variante con su stock | ☐ |
| 71 | Escanear el mismo código en una nota de pedido nueva | Lo agrega al pedido; escanearlo otra vez le suma 1 | ☐ |
| 72 | Escanear un producto sin stock | Avisa "está sin stock" y NO lo agrega | ☐ |
| 73 | Escanear en Inventario, con la variante a la vista en la lista | Abre directo su panel de ajuste | ☐ |
| 73b | Escanear en Inventario una variante que NO está en la página actual | Filtra por su SKU y la deja a un toque | ☐ |
| 74 | Escanear un código que no existe | Avisa que no está asignado a ningún producto (no es un error: es lo esperado al dar de alta mercadería) | ☐ |
| 75 | Intentar asignar a otra variante un código ya usado | Lo rechaza y dice a qué producto pertenece | ☐ |
| 76 | Escribir a mano en el buscador, a velocidad normal | NO dispara una lectura: busca como texto | ☐ |
| 76b | Escanear con el foco puesto en un campo de texto de otra pantalla | El código además queda escrito en ese campo — verificar que no moleste en ninguna pantalla | ☐ |

**Epson EcoTank L1250** — etiquetas de código de barras. *No imprime facturas:
el comprobante fiscal sale por su propio equipo, todavía sin conectar.*

| # | Prueba | Esperado | OK |
|---|--------|----------|:--:|
| 77 | Instalarla en Panel de control y copiar su nombre exacto a `IMPRESORA_A4_NOMBRE` | `diagnostico_impresora.py` la marca como disponible | ☐ |
| 78 | En el diagnóstico, aceptar la hoja de etiquetas de prueba | Salen 6 etiquetas: 3 EAN-13 y 3 Code128 | ☐ |
| 79 | Pasar el lector por las 6 etiquetas impresas | Las 6 se leen | ☐ |
| 80 | Inventario → botón «Etiquetas» | Abre el PDF con las etiquetas de lo que está filtrado | ☐ |
| 81 | Imprimir con "ajustar a la página" y escanear | **No se lee** — confirma por qué hay que imprimir al 100% | ☐ |
| 82 | Reimprimir al 100% sobre la planilla autoadhesiva | Las etiquetas caen dentro del troquel y se leen | ☐ |
| 83 | Etiquetas con `desde` = 7 | Deja en blanco las 7 primeras celdas de la hoja | ☐ |

---

## BLOQUE 4 — Ajustes de configuración para producción (15 min)

Estos cambios se hacen ANTES de la entrega definitiva.

### 4.1 En `backend/.env`

```env
# Cambiar:
DEBUG=False
SECRET_KEY=<clave larga y aleatoria generada con get_random_secret_key()>
CORS_ALLOW_ALL_ORIGINS=False
CORS_ALLOWED_ORIGINS=http://<IP-servidor>:5173,http://localhost:5173
ALLOWED_HOSTS=localhost,127.0.0.1,<IP-servidor>

# Verificar:
DB_PASSWORD=<contraseña fuerte, no la de demo>
```

### 4.2 Colectar archivos estáticos

```cmd
python manage.py collectstatic --noinput
```

### 4.3 Cambiar contraseñas de demo

Desde la interfaz de Usuarios (como admin), cambiar las contraseñas de `vendedor`, `cajero`, `deposito` y `admin` por contraseñas reales elegidas con el negocio.

### 4.4 Verificación final de settings

```cmd
python manage.py check --deploy
```

Este comando informa de configuraciones inseguras para producción.

---

## BLOQUE 5 — Carga inicial de productos reales (variable)

Este bloque lo ejecuta el personal del negocio con ayuda.

### 5.1 Plan de carga

1. Empezar con los 20 productos más vendidos
2. Para cada producto: código, nombre, categoría, precio, foto (desde el celular)
3. Cargar variantes con dimensiones y stock real del depósito

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
Verificar que Redis esté corriendo:
```cmd
redis-cli ping
```
Si responde ERROR, iniciar Redis:
```cmd
net start Redis
```

### "La impresora no imprime" / "el lector no hace nada"

Ver `docs/perifericos.md` §3, que tiene la tabla de síntomas de los dos
aparatos. El atajo: `python diagnostico_impresora.py`.

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

*Última revisión: agosto 2026*
