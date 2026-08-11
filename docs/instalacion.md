# Guía de instalación — Sistema de Gestión Comercial

## Requisitos

| Componente | Mínimo | Recomendado |
|---|---|---|
| Sistema operativo | Windows 10 64-bit | Windows 10/11 64-bit |
| Python | 3.10+ | 3.11 |
| Node.js | 18+ | 20 LTS |
| PostgreSQL | 13+ | 15 |
| RAM | 4 GB | 8 GB |
| Disco | 20 GB libres | SSD 240 GB |

Los equipos i7-2600 con 8 GB RAM y SSD 240 GB son completamente compatibles.

---

## Antes de instalar — descargas necesarias

Instalar en este orden en el equipo que actuará como servidor:

1. **Python 3.11** → https://www.python.org/downloads/
   - Durante la instalación: marcar ✅ **"Add Python to PATH"**

2. **Node.js 20 LTS** → https://nodejs.org/
   - Instalar la versión marcada como **LTS**

3. **PostgreSQL 15** → https://www.postgresql.org/download/windows/
   - Anotar la contraseña que se defina para el usuario `postgres`
   - Al finalizar la instalación, agregar al PATH de Windows:
     `C:\Program Files\PostgreSQL\15\bin`

---

## Instalación automática (recomendada)

`setup.bat` automatiza casi todo, pero necesita dos cosas hechas **antes**
de correrlo — si faltan, se detiene con un error claro:

1. **La base de datos y el usuario de PostgreSQL ya creados** (Paso 1 de la
   sección manual, más abajo) — `setup.bat` no los crea, asume que existen.
2. **`backend\.env` ya creado**, con esos mismos datos:
   ```bat
   cd ceramica_final\backend
   copy .env.example .env
   :: Editar .env con el Bloc de notas: DB_PASSWORD debe coincidir con la
   :: contraseña que se le puso al usuario ceramica_user en el Paso 1.
   ```

Con eso listo, abrir **Símbolo del sistema como Administrador** en la
carpeta del proyecto (ej. `ceramica_final`) y ejecutar:

```bat
cd ceramica_final
setup.bat
```

El script realiza automáticamente:
- Verificación de Python, Node.js y PostgreSQL en el PATH
- Verificación de que `backend\.env` existe
- Entorno virtual Python e instalación de dependencias (`requirements.txt`)
- Migraciones de Django (`migrate`)
- Creación de categorías de gasto base (`seed_categorias`)
- Creación interactiva del usuario administrador (`createsuperuser` — pide
  usuario y contraseña en el momento, no hay contraseña por defecto)
- Instalación de dependencias del frontend (`npm install`)
- Detección de la IP local, para saber con qué dirección entrar desde
  tablets y otras PCs

No carga catálogo de demostración ni datos de ejemplo — para el sistema
final se espera que el catálogo real se cargue desde cero (Productos →
Variantes) o mediante los CSV de `backend/data_carga/` si ya están
preparados (ver `referencias_productos.csv` y `mapeo_imagenes.csv`).

---

## Instalación manual paso a paso

### Paso 1 — Base de datos PostgreSQL

Abrir **pgAdmin** (se instala con PostgreSQL) o abrir una ventana de comandos y ejecutar:

```bat
psql -U postgres
```

Dentro de psql:
```sql
CREATE USER ceramica_user WITH PASSWORD 'ceramica_pass_segura';
CREATE DATABASE ceramica_db OWNER ceramica_user;
GRANT ALL PRIVILEGES ON DATABASE ceramica_db TO ceramica_user;
\q
```

### Paso 2 — Backend Django

Abrir Símbolo del sistema en la carpeta del proyecto:

```bat
cd ceramica_final\backend

:: Entorno virtual
python -m venv venv
venv\Scripts\activate

:: Dependencias
pip install -r requirements.txt

:: Configurar variables de entorno
copy .env.example .env
:: Editar .env con el Bloc de notas: DB_PASSWORD debe coincidir con la
:: contraseña puesta en el Paso 1

:: Migraciones
python manage.py migrate

:: Categorías de gasto base (obligatorio, lo usa el módulo de Costos)
python manage.py seed_categorias

:: Crear superusuario — pide usuario y contraseña en el momento
python manage.py createsuperuser
```

> `python manage.py loaddata initial_data.json` carga un catálogo de
> **demostración** (productos, stock y usuarios de prueba) — usarlo solo
> para probar el sistema, no en la PC servidor del negocio real. Para el
> sistema final, cargar el catálogo real desde **Productos** dentro del
> sistema, o mediante los CSV de `backend/data_carga/` si ya están listos.

### Paso 3 — Frontend React

```bat
cd ceramica_final\frontend
npm install
```

---

## Iniciar el sistema

Para el día a día, un solo script abre las dos ventanas necesarias (backend
con Daphne — HTTP + WebSocket — y frontend con Vite) y el navegador local:

```bat
iniciar.bat
```

No cerrar las dos ventanas negras que abre — son el servidor y la interfaz;
cerrarlas corta el sistema para todos los dispositivos conectados.

Si se necesita arrancar cada parte a mano (para ver mejor un error, por
ejemplo):

**Backend:**
```bat
cd backend
venv\Scripts\activate
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

**Frontend (en otra ventana):**
```bat
cd frontend
npm run dev
```

> `python manage.py runserver` también funciona para el backend, pero solo
> sirve HTTP — sin WebSocket no hay actualizaciones en vivo de pedidos ni
> alertas de stock (ver `CLAUDE.md`). Usar siempre Daphne para el día a día.

---

## URLs de acceso

| Servicio | URL local | URL red local WiFi |
|---|---|---|
| Frontend (sistema) | http://localhost:5173 | http://192.168.x.x:5173 |
| API REST | http://localhost:8000/api/v1 | http://192.168.x.x:8000/api/v1 |
| Panel Django Admin | http://localhost:8000/admin | — |

> **Para tablets y otros equipos en la red WiFi:**
> Usar la IP del equipo servidor. Obtenerla con `ipconfig` en el servidor y buscar "Dirección IPv4".
> Ejemplo: `http://192.168.1.100:5173`
>
> Esa IP la asigna el router por DHCP y **puede cambiar** (reinicio del
> router, etc.), lo que rompe el acceso ya configurado en PC Caja, PC
> Depósito y tablets. Antes de dar por terminado el armado, reservarla de
> forma fija en el router — pasos concretos en
> `guia_instalacion_dispositivos.md` §2. Si igual llegara a cambiar,
> `pwa_tablet.md` tiene un checklist de recuperación de ~2 minutos por
> dispositivo.

---

## Credenciales iniciales

No hay usuario ni contraseña por defecto: `setup.bat` pide el usuario y la
contraseña del administrador de forma interactiva durante la instalación
(paso `createsuperuser`), en el momento en que se arma cada PC servidor.
Anotar lo que se cargue ahí — es la única cuenta que existe hasta que el
admin cree las demás desde **Usuarios** dentro del sistema.

*(Las credenciales `admin/demo2025` que aparecen en `guia_demo_propietarios.md`
son solo para la demo con datos de prueba — `cargar_demo.py` — no aplican
al sistema final con datos reales.)*

---

## Configuración de impresoras en Windows

### Impresora térmica FTX FTXP-80W
- Conectar por USB al equipo servidor
- Windows detecta e instala el driver automáticamente
- Si no: descargar driver desde el sitio de FTX o usar driver genérico ESC/POS
- Verificar en: Panel de control → Dispositivos e impresoras

### Impresora matricial Epson LX-350
- Conectar por USB o puerto paralelo (con adaptador USB-Paralelo si es necesario)
- Driver oficial: https://epson.com/Support/Printers/sl/s/SPT_C11C637011
- Instalar el driver Epson LX-350 para Windows

### Verificar la conexión antes de dar por armada la PC servidor
```bat
cd backend
venv\Scripts\activate
python diagnostico_impresora.py
```
Prueba la conexión con la impresora térmica configurada y avisa si Windows
no la detecta — más rápido que descubrirlo en medio de una venta real.
Fuera de Windows (o sin impresora conectada) queda en modo "simulado", sin
romper el resto del sistema.

---

## Usuarios del sistema

Crear desde el panel admin (`http://localhost:8000/admin`) o desde la API:

| Rol | Acceso |
|---|---|
| `admin` | Todo el sistema |
| `vendedor` | Showroom, productos, notas de pedido |
| `cajero` | Caja, pagos, pedidos listos |
| `deposito` | Inventario, preparación de pedidos |

---

## Solución de problemas frecuentes

**Error de conexión a PostgreSQL:**
- Verificar que el servicio esté corriendo: Inicio → Servicios → `postgresql-x64-15` → Iniciar
- O desde Símbolo del sistema como Administrador: `net start postgresql-x64-15`

**Puerto 8000 o 5173 ocupado:**
```bat
:: Ver qué proceso usa el puerto
netstat -ano | findstr :8000
:: Terminar el proceso por su PID (reemplazar 1234)
taskkill /PID 1234 /F
```

**No carga en tablets:**
- El servidor debe estar corriendo en `0.0.0.0` (ya configurado así en los scripts)
- Verificar que la tablet esté conectada a la misma red WiFi
- Abrir el firewall de Windows para los puertos 5173 y 8000:
  - Panel de control → Firewall de Windows → Configuración avanzada
  - Reglas de entrada → Nueva regla → Puerto → TCP → 5173, 8000

**Python no reconocido en la consola:**
- Reinstalar Python marcando "Add Python to PATH"
- O agregar manualmente: `C:\Users\TuUsuario\AppData\Local\Programs\Python\Python311`
