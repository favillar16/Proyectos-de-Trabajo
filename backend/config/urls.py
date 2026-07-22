"""
URLs principales — Oga Porã
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

api_v1 = [
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
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include(api_v1)),
]

# Servir archivos media en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
