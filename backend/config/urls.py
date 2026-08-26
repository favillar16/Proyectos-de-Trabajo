"""
URLs principales — Oga Porã
"""
from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve as servir_estatico
from .salud import salud
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

api_v1 = [
    # Identidad del nodo — sonda de descubrimiento, pública y sin auth.
    # Es lo que permite que tablets/notebook encuentren al servidor por
    # nombre en vez de por IP (ver config/salud.py).
    path('salud/', salud, name='salud'),

    # Autenticación JWT
    path('auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/verify/', TokenVerifyView.as_view(), name='token_verify'),

    # Apps
    path('usuarios/', include('apps.usuarios.urls')),
    path('productos/', include('apps.productos.urls')),
    path('inventario/', include('apps.inventario.urls')),
    path('ventas/', include('apps.ventas.urls')),
    path('caja/', include('apps.caja.urls')),
    path('costos/', include('apps.costos.urls')),
    path('sync/', include('apps.sync.urls')),
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include(api_v1)),
]

# Fotos de productos: servir siempre, sin depender de DEBUG. Este sistema es
# un appliance LAN-only sin servidor web separado (ver CLAUDE.md) — si no se
# sirve acá, no se sirve en ningún lado. No se usa el helper static() de
# Django porque internamente ignora todo si DEBUG=False, sin excepción.
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', servir_estatico, {'document_root': settings.MEDIA_ROOT}),
]

# Estáticos de Django (admin, DRF browsable API): solo hace falta en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
