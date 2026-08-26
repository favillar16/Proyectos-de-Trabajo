"""
Configuración para correr las pruebas automáticas sin depender de PostgreSQL.

    python manage.py test --settings=config.settings_test

Los tests también corren contra la configuración normal
(`python manage.py test apps.facturacion`), que es lo que se usa en la PC del
negocio. Esta configuración alternativa existe para poder correrlos en
cualquier máquina —una notebook de desarrollo, por ejemplo— sin tener
PostgreSQL levantado ni conocer su contraseña.

La base es SQLite en memoria: arranca vacía, se descarta al terminar y no toca
en ningún momento los datos del negocio.

IMPORTANTE — un test falla acá y está bien que falle:

    apps.facturacion.tests.test_numeracion.ConcurrenciaTests
    .test_varias_cajas_simultaneas_no_duplican_ni_saltan

Ese test levanta varios hilos cobrando al mismo tiempo para verificar que la
numeración de comprobantes no se duplique. Necesita bloqueo por fila, que es de
PostgreSQL; SQLite bloquea la tabla entera y el test muere con "database table
is locked". **No es un problema del sistema.** Contra PostgreSQL pasa:

    python manage.py test apps.facturacion

Lo mismo vale, en general, para todo lo que dependa de `select_for_update`
(las reservas de stock, por ejemplo): acá esa protección no se ejercita.

Tampoco se cubren, y hay que seguir probándolos a mano
(ver docs/checklist_entrega.md): la impresora térmica y los avisos en tiempo
real por WebSocket.
"""
from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    },
    # El registro de cambios del sync vive en su propia base también acá (ver
    # apps/sync/routers.py). Los tests que la tocan tienen que declararla:
    #     databases = {'default', 'sync'}
    'sync': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    },
}

# Hash de contraseñas rápido: los tests crean muchos usuarios y el hash real
# (PBKDF2) es lento a propósito. Solo aplica a las pruebas.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

CHANNEL_LAYERS = {
    'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}
}

STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# Las imágenes de prueba van a una carpeta descartable, no a las fotos reales
# de los productos.
MEDIA_ROOT = BASE_DIR / 'media_test'  # noqa: F405

DEBUG = False
