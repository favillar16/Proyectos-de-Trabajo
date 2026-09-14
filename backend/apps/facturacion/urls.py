"""Rutas de facturación electrónica."""
from django.urls import path

from .views import ColaDocumentosView, EmitirNotaCreditoView, MotivosNotaView

urlpatterns = [
    path('documentos/', ColaDocumentosView.as_view(), name='fe-documentos'),
    path('documentos/<int:pk>/nota-credito/', EmitirNotaCreditoView.as_view(),
         name='fe-nota-credito'),
    path('motivos-nota/', MotivosNotaView.as_view(), name='fe-motivos-nota'),
]
