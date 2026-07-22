"""
Configuración principal de Django
Sistema de Gestión Comercial — Oga Porã
"""

from pathlib import Path
from decouple import config
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-cambiar-en-produccion-xK9#mP2@nQ5')

DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='localhost,127.0.0.1,0.0.0.0',
    cast=lambda v: [s.strip() for s in v.split(',')]
)

# ─── Aplicaciones ────────────────────────────────────────────────────────────

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'django_filters',
    'channels',
]

LOCAL_APPS = [
    'apps.usuarios',
    'apps.productos',
    'apps.inventario',
    'apps.ventas',
    'apps.caja',
    'apps.costos',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ─── Middleware ───────────────────────────────────────────────────────────────

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ASGI para WebSockets (sincronización en tiempo real)
ASGI_APPLICATION = 'config.asgi.application'
WSGI_APPLICATION = 'config.wsgi.application'

# ─── Base de Datos ────────────────────────────────────────────────────────────

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='ceramica_db'),
        'USER': config('DB_USER', default='ceramica_user'),
        'PASSWORD': config('DB_PASSWORD', default='ceramica_pass'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 60,
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}

# ─── Autenticación personalizada ─────────────────────────────────────────────

AUTH_USER_MODEL = 'usuarios.Usuario'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─── Django REST Framework ────────────────────────────────────────────────────

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

# ─── JWT ─────────────────────────────────────────────────────────────────────

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# ─── CORS ─────────────────────────────────────────────────────────────────────

CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000',
    cast=lambda v: [s.strip() for s in v.split(',')]
)
CORS_ALLOW_CREDENTIALS = True

# Para red local WiFi — permite todas las IPs de la subred
# ADVERTENCIA: Cambiar a False en producción y configurar CORS_ALLOWED_ORIGINS
CORS_ALLOW_ALL_ORIGINS = config('CORS_ALLOW_ALL_ORIGINS', default=True, cast=bool)

# ─── Channels (WebSocket) ─────────────────────────────────────────────────────

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
        # En producción, usar Redis:
        # 'BACKEND': 'channels_redis.core.RedisChannelLayer',
        # 'CONFIG': {'hosts': [('127.0.0.1', 6379)]},
    }
}

# ─── Archivos estáticos y media ───────────────────────────────────────────────

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Límite de tamaño de imagen por producto: 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB

# ─── Internacionalización ─────────────────────────────────────────────────────

LANGUAGE_CODE = 'es-py'
TIME_ZONE = 'America/Asuncion'
USE_I18N = True
USE_TZ = True

# ─── Configuraciones del negocio ──────────────────────────────────────────────

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── Impresoras ───────────────────────────────────────────────────────────────

IMPRESORA_TERMICA = {
    'modelo':           'FTX FTXP-80W',
    'ancho_papel_mm':   80,
    'caracteres_linea': 48,      # columnas de texto a 80mm con font A
    # Nombre del dispositivo en Windows (Panel de control → Dispositivos e impresoras)
    # Se puede sobreescribir con IMPRESORA_TERMICA_NOMBRE en el .env
    'nombre_windows':   config('IMPRESORA_TERMICA_NOMBRE', default='FTX FTXP-80W'),
    # Alternativa: ruta directa al puerto USB
    'puerto_directo':   config('IMPRESORA_TERMICA_PUERTO', default=''),
    # Codificación de texto para caracteres especiales en español
    'encoding':         'cp850',
    # Imprimir automáticamente al confirmar un pago
    'auto_imprimir':    config('IMPRESORA_AUTO', default=True, cast=bool),
    # Copias por ticket (1 = una sola copia)
    'copias':           config('IMPRESORA_COPIAS', default=1, cast=int),
}

IMPRESORA_MATRICIAL = {
    'modelo':           'Epson LX-350',
    'ancho_papel_mm':   240,
    'nombre_windows':   config('IMPRESORA_MATRICIAL_NOMBRE', default='Epson LX-350'),
}

# Datos fiscales para la emisión de facturas (se configuran en el .env)
DATOS_FISCALES = {
    'ruc':          config('FISCAL_RUC', default=''),
    'razon_social': config('FISCAL_RAZON_SOCIAL', default='Oga Porã'),
    'direccion':    config('FISCAL_DIRECCION', default=''),
    'telefono':     config('FISCAL_TELEFONO', default=''),
    'timbrado':     config('FISCAL_TIMBRADO', default=''),
    'timbrado_vto': config('FISCAL_TIMBRADO_VTO', default=''),
}
