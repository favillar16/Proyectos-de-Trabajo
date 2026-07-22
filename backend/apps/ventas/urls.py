from django.urls import path
from .views import (
    NotaPedidoListCreateView,
    NotaPedidoDetailView,
    CambioEstadoView,
    PrepararItemView,
    CancelarItemView,
    ClienteListCreateView,
    ClienteDetailView,
)

urlpatterns = [
    path('pedidos/',                                   NotaPedidoListCreateView.as_view(), name='pedidos-list'),
    path('pedidos/<int:pk>/',                          NotaPedidoDetailView.as_view(),     name='pedido-detail'),
    path('pedidos/<int:pk>/estado/',                   CambioEstadoView.as_view(),         name='pedido-estado'),
    path('pedidos/<int:pk>/items/<int:item_id>/preparar/', PrepararItemView.as_view(),     name='item-preparar'),
    path('pedidos/<int:pk>/items/<int:item_id>/',      CancelarItemView.as_view(),         name='item-cancelar'),
    # Padrón de clientes con RUC
    path('clientes/',          ClienteListCreateView.as_view(), name='clientes-list'),
    path('clientes/<int:pk>/', ClienteDetailView.as_view(),     name='cliente-detail'),
]
