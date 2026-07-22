from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoriaViewSet, MarcaViewSet, AcabadoViewSet, TipoInstalacionViewSet, ProductoViewSet, VarianteViewSet

router = DefaultRouter()
router.register('categorias', CategoriaViewSet, basename='categoria')
router.register('marcas', MarcaViewSet, basename='marca')
router.register('acabados', AcabadoViewSet, basename='acabado')
router.register('tipos-instalacion', TipoInstalacionViewSet, basename='tipo-instalacion')
router.register('variantes', VarianteViewSet, basename='variante')
router.register('', ProductoViewSet, basename='producto')

urlpatterns = [
    path('', include(router.urls)),
]
