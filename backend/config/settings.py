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

# '*' por defecto: la tablet llama a la API directo por su IP LAN (variable
# según el local), no solo por localhost. Ver nota en .env.
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='*',
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
    'apps.facturacion',
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

    # ── Agregados para facturación electrónica ───────────────────────────
    # Los tres de abajo componen el CDC y el número de comprobante, así que
    # tienen que coincidir EXACTAMENTE con lo que la DNIT habilitó en el RUC.
    # e-Kuatia'i además exige un único establecimiento y un único punto de
    # expedición: si el negocio necesita más de uno, no califica para
    # e-Kuatia'i y hay que ir a e-Kuatia completo.
    'establecimiento':    config('FISCAL_ESTABLECIMIENTO', default='001'),
    'punto_expedicion':   config('FISCAL_PUNTO_EXPEDICION', default='001'),
    # 1 = persona física, 2 = persona jurídica. Va en el dígito 25 del CDC.
    'tipo_contribuyente': config('FISCAL_TIPO_CONTRIBUYENTE', default=2, cast=int),

    # Domicilio fiscal desglosado: el SIFEN no acepta la dirección como un
    # texto libre, la pide por campos con códigos de departamento/distrito.
    'departamento':        config('FISCAL_DEPARTAMENTO', default=''),
    'departamento_desc':   config('FISCAL_DEPARTAMENTO_DESC', default=''),
    'distrito':            config('FISCAL_DISTRITO', default=''),
    'distrito_desc':       config('FISCAL_DISTRITO_DESC', default=''),
    'ciudad':              config('FISCAL_CIUDAD', default=''),
    'ciudad_desc':         config('FISCAL_CIUDAD_DESC', default=''),
    'actividad_economica': config('FISCAL_ACTIVIDAD_CODIGO', default=''),
    'actividad_desc':      config('FISCAL_ACTIVIDAD_DESC', default=''),
}

# ─── SIFEN / e-Kuatia ─────────────────────────────────────────────────────────
# Transmisión de documentos electrónicos a la DNIT.
#
# Ojo con el contexto: este sistema es un appliance de red local pensado para
# funcionar sin internet (ver CLAUDE.md), y el SIFEN necesita internet. Por eso
# la emisión NO es sincrónica — el DE se encola y se transmite aparte. El cobro
# en caja nunca espera a la red. Ver apps/facturacion/models.py.
#
# Mientras SIFEN_HABILITADO sea False el sistema sigue funcionando exactamente
# como hoy: no genera DEs, no numera comprobantes electrónicos y no intenta
# salir a internet. Se prende recién cuando estén el certificado y la
# habilitación de la DNIT.
SIFEN = {
    'habilitado':  config('SIFEN_HABILITADO', default=False, cast=bool),
    # 'test' mientras se hacen las pruebas de habilitación, 'produccion' después.
    'ambiente':    config('SIFEN_AMBIENTE', default='test'),

    # Certificado cualificado de firma electrónica (.p12 / .pfx). Lo entrega la
    # DNIT sin costo. NUNCA versionar este archivo ni su clave.
    'certificado_path':     config('SIFEN_CERT_PATH', default=''),
    'certificado_password': config('SIFEN_CERT_PASSWORD', default=''),

    # Sidecar Node con la suite facturacionelectronicapy-* (xmlgen, xmlsign,
    # qrgen, setapi, kude), que es la librería que la DNIT publica como
    # referencia. Se eligió Node porque la PC servidor ya lo tiene instalado
    # para el frontend — ver docs/facturacion_electronica.md.
    'sidecar_url': config('SIFEN_SIDECAR_URL', default='http://127.0.0.1:8100'),
    'timeout_seg': config('SIFEN_TIMEOUT', default=30, cast=int),

    # Reintentos de la cola. La DNIT da una ventana para transmitir un DE ya
    # emitido, así que un corte de internet de unas horas no invalida la venta.
    'max_intentos':        config('SIFEN_MAX_INTENTOS', default=10, cast=int),
    'minutos_entre_envios': config('SIFEN_MINUTOS_REINTENTO', default=5, cast=int),

    'url_consulta_qr': config(
        'SIFEN_URL_CONSULTA_QR',
        default='https://ekuatia.set.gov.py/consultas/qr'),
}
