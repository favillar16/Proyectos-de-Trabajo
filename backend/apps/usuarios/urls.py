from django.urls import path
from .views import (
    MeView,
    UsuarioListCreateView,
    UsuarioDetailView,
    CambiarPasswordView,
)

urlpatterns = [
    path('me/',                         MeView.as_view(),               name='me'),
    path('',                            UsuarioListCreateView.as_view(), name='usuario-list'),
    path('<int:pk>/',                   UsuarioDetailView.as_view(),     name='usuario-detail'),
    path('<int:pk>/password/',          CambiarPasswordView.as_view(),   name='usuario-password'),
]
