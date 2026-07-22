# Sistema de Gestión Comercial — Cerámicas & Sanitarios

Versión 1.0 · Mayo 2025  
Stack: Django 4.2 · React 18 · PostgreSQL 15 · WebSocket (Django Channels)

---

## Resumen del sistema

Sistema de gestión comercial integral para negocio de pisos, porcelanatos, cerámicas, sanitarios y accesorios en Paraguay. Funciona en red local WiFi sin conexión a internet.

### Módulos implementados

| Módulo | Estado | Roles con acceso |
|--------|--------|-----------------|
| Showroom digital | ✓ Completo | Todos |
| Catálogo de productos | ✓ Completo | Admin, Vendedor |
| Consulta rápida de stock | ✓ Completo | Todos |
| Notas de pedido | ✓ Completo | Admin, Vendedor, Depósito |
| Módulo de caja | ✓ Completo | Admin, Cajero |
| Impresora térmica ESC/POS | ✓ Completo | Cajero (automático) |
| Control de stock automático | ✓ Completo | Sistema |
| Inventario y ajustes | ✓ Completo | Admin, Depósito |
| Dashboard con KPIs | ✓ Completo | Admin |
| Gestión de usuarios y roles | ✓ Completo | Admin |
| WebSocket tiempo real | ✓ Completo | Todos los módulos |

### Estadísticas del código

- **40** archivos Python (backend)
- **21** archivos JavaScript/JSX (frontend)  
- **15** tablas en la base de datos
- **20** endpoints REST en la API
- **2** canales WebSocket (por pedido + por rol)
- **4** roles de usuario con permisos granulares

---

## Arquitectura

```
ceramica_final/
├── backend/                  Django 4.2
│   ├── apps/
│   │   ├── usuarios/         Modelo de usuario + roles + permisos
│   │   ├── productos/        Catálogo completo con variantes e imágenes
│   │   ├── inventario/       Stock, movimientos y alertas
│   │   ├── ventas/           Notas de pedido + WebSocket
│   │   └── caja/             Sesiones, pagos, impresión, KPIs
│   ├── config/               settings.py, urls.py, asgi.py
│   └── manage.py
├── frontend/                 React 18 + Vite
│   └── src/
│       ├── pages/            8 páginas (una por módulo)
│       ├── components/       5 componentes reutilizables
│       ├── hooks/            4 hooks (useDevice, useShowroom, useProductoForm, usePedidoSocket)
│       └── services/api.js   51 funciones de API
├── docs/
│   ├── manual_usuario.docx   Manual para el cliente (este archivo)
│   ├── checklist_entrega.md  59 pruebas funcionales
│   ├── instalacion.md        Guía de instalación paso a paso
│   └── guia_demo.md          Script de presentación
└── iniciar_demo.bat          Arranque de la demo con un doble clic
```

---

## Instalación rápida

Ver `docs/instalacion.md` para la guía completa.

```cmd
# 1. Prerequisitos instalados: Python 3.11, Node.js 20, PostgreSQL 15, Redis 7

# 2. Base de datos
psql -U postgres -c "CREATE DATABASE ceramica_db;"
psql -U postgres -c "CREATE USER ceramica_user WITH PASSWORD 'ceramica_pass_2025';"
psql -U postgres -c "GRANT ALL ON DATABASE ceramica_db TO ceramica_user;"

# 3. Backend
cd backend
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # editar con datos reales

python manage.py makemigrations usuarios productos inventario ventas caja
python manage.py migrate
python manage.py loaddata initial_data.json
python cargar_demo.py

# 4. Frontend
cd ..\frontend
npm install

# 5. Iniciar
iniciar_demo.bat
```

---

## Variables de entorno críticas

```env
SECRET_KEY=<generar con get_random_secret_key()>
DEBUG=False                          # False en producción
DB_PASSWORD=<contraseña segura>
IMPRESORA_TERMICA_NOMBRE=FTX FTXP-80W
CORS_ALLOW_ALL_ORIGINS=False         # False en producción
CORS_ALLOWED_ORIGINS=http://<IP>:5173
```

---

## Flujo de venta completo

```
Vendedor crea pedido → reserva stock automáticamente
    ↓ WebSocket
Depósito recibe notificación → marca ítems preparados → marca "Listo"
    ↓ WebSocket
Cajero recibe notificación → cobra → confirma pago
    ↓
Stock descontado automáticamente → ticket impreso → pedido cerrado
    ↓ WebSocket
Vendedor y admin ven el pedido como "Pagado"
```

---

## Diagnóstico de impresora

```cmd
cd backend
python diagnostico_impresora.py
```

---

## Usuarios de demo

| username | password | rol |
|----------|----------|-----|
| admin | demo2025 | Administrador |
| vendedor | demo2025 | María González |
| cajero | demo2025 | Carlos Benítez |
| deposito | demo2025 | Roberto Villalba |

**Cambiar todas las contraseñas antes de la entrega al cliente.**

---

## Documentación adicional

- `docs/manual_usuario.docx` — Manual completo para usuarios finales
- `docs/checklist_entrega.md` — Lista de 59 pruebas funcionales
- `docs/instalacion.md` — Guía técnica de instalación
- `docs/guia_demo_propietarios.md` — Script de presentación (25-35 min)
