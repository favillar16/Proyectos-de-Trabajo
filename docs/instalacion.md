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

Con los tres programas instalados, abrir una ventana de **Símbolo del sistema como Administrador** y ejecutar:

```bat
cd ceramica_system
setup.bat
```

El script realiza automáticamente:
- Verificación de Python, Node.js y PostgreSQL
- Creación de la base de datos y usuario
- Entorno virtual Python e instalación de dependencias
- Migraciones de Django
- Carga de datos iniciales (categorías, marcas, acabados)
- Creación del usuario administrador
- Generación de scripts de arranque

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
cd ceramica_system\backend

:: Entorno virtual
python -m venv venv
venv\Scripts\activate

:: Dependencias
pip install -r requirements.txt

:: Configurar variables de entorno
copy .env.example .env
:: Editar .env con el Bloc de notas si es necesario

:: Migraciones
python manage.py migrate

:: Datos iniciales
python manage.py loaddata initial_data.json

:: Crear superusuario
python manage.py createsuperuser
```

### Paso 3 — Frontend React

```bat
cd ceramica_system\frontend
npm install
```

---

## Iniciar el sistema

### Opción A — Script combinado (abre dos ventanas automáticamente)
```bat
start-all.bat
```

### Opción B — Por separado

**Ventana 1 — Backend:**
```bat
start-backend.bat
```

**Ventana 2 — Frontend:**
```bat
start-frontend.bat
```

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

---

## Credenciales iniciales

| Usuario | Contraseña | Rol |
|---|---|---|
| admin | admin123 | Administrador |

**Importante:** Cambiar la contraseña del admin en el primer acceso.

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
