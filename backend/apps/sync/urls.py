from django.urls import path

from . import views

urlpatterns = [
    path('cambios/', views.recibir_cambios, name='sync_recibir_cambios'),
    path('estado/',  views.estado_sync,     name='sync_estado'),
    path('catalogo/', views.catalogo,       name='sync_catalogo'),
    path('foto/',    views.subir_foto,      name='sync_subir_foto'),
]
