from django.urls import path
from .views import ConsultaRapidaStockView, StockListView, AjusteStockView

urlpatterns = [
    path('consulta/', ConsultaRapidaStockView.as_view(), name='stock-consulta-rapida'),
    path('stock/',    StockListView.as_view(),            name='stock-list'),
    path('ajustes/',  AjusteStockView.as_view(),          name='stock-ajuste'),
]
