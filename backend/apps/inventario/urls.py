from django.urls import path
from .views import (
    ConsultaRapidaStockView, StockListView, AjusteStockView,
    MovimientoStockListView, EscanearCodigoView, AsignarCodigoBarrasView,
)

urlpatterns = [
    path('consulta/',    ConsultaRapidaStockView.as_view(),  name='stock-consulta-rapida'),
    path('stock/',       StockListView.as_view(),            name='stock-list'),
    path('ajustes/',     AjusteStockView.as_view(),          name='stock-ajuste'),
    path('movimientos/', MovimientoStockListView.as_view(),  name='stock-movimientos'),

    # Lector de código de barras FTX-LC123BH5
    path('escanear/',      EscanearCodigoView.as_view(),      name='escanear-codigo'),
    path('codigo-barras/', AsignarCodigoBarrasView.as_view(), name='asignar-codigo-barras'),
]
