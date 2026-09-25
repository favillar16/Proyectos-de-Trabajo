from django.urls import path
from .views import (
    ConsultaRapidaStockView, StockListView, AjusteStockView,
    MovimientoStockListView, ReservasVigentesView,
)

urlpatterns = [
    path('consulta/',    ConsultaRapidaStockView.as_view(),  name='stock-consulta-rapida'),
    path('stock/',       StockListView.as_view(),            name='stock-list'),
    path('ajustes/',     AjusteStockView.as_view(),          name='stock-ajuste'),
    path('movimientos/', MovimientoStockListView.as_view(),  name='stock-movimientos'),
    path('reservas/',    ReservasVigentesView.as_view(),     name='stock-reservas'),
]
