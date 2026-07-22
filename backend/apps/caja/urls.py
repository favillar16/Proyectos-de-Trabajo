from django.urls import path
from .views import (
    SesionActualView, AbrirCajaView, CerrarCajaView,
    RegistrarPagoView, ListaPagosView,
    ReimprimirTicketView, EstadoImpresora,
    ReporteStockView, ReporteVentasView, ReporteCajaView,
)
from .kpis import KPIsDashboardView

urlpatterns = [
    path('sesion-actual/',                 SesionActualView.as_view(),     name='sesion-actual'),
    path('sesiones/',                      AbrirCajaView.as_view(),        name='abrir-caja'),
    path('sesiones/<int:pk>/cerrar/',      CerrarCajaView.as_view(),       name='cerrar-caja'),
    path('pagos/',                         RegistrarPagoView.as_view(),    name='registrar-pago'),
    path('pagos/lista/',                   ListaPagosView.as_view(),       name='lista-pagos'),
    path('pagos/<int:pk>/reimprimir/',     ReimprimirTicketView.as_view(), name='reimprimir-ticket'),
    path('impresora/estado/',              EstadoImpresora.as_view(),      name='estado-impresora'),
    path('kpis/',                          KPIsDashboardView.as_view(),    name='dashboard-kpis'),
    # Reportes (PDF / Excel)
    path('reportes/stock/',                ReporteStockView.as_view(),     name='reporte-stock'),
    path('reportes/ventas/',               ReporteVentasView.as_view(),    name='reporte-ventas'),
    path('reportes/caja/',                 ReporteCajaView.as_view(),      name='reporte-caja'),
]
