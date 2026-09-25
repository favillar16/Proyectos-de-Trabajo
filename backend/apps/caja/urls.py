from django.urls import path
from .views import (
    SesionActualView, AbrirCajaView, CerrarCajaView,
    RegistrarPagoView, ListaPagosView,
    ReimprimirTicketView, ComprobanteView, EstadoImpresora,
    ReporteStockView, ReporteVentasView, ReporteCajaView,
    ReporteProductosView, ReporteArqueoView,
    DevolucionResumenView, DevolucionesView, ReimprimirDevolucionView,
)
from .kpis import KPIsDashboardView

urlpatterns = [
    path('sesion-actual/',                 SesionActualView.as_view(),     name='sesion-actual'),
    path('sesiones/',                      AbrirCajaView.as_view(),        name='abrir-caja'),
    path('sesiones/<int:pk>/cerrar/',      CerrarCajaView.as_view(),       name='cerrar-caja'),
    path('pagos/',                         RegistrarPagoView.as_view(),    name='registrar-pago'),
    path('pagos/lista/',                   ListaPagosView.as_view(),       name='lista-pagos'),
    path('pagos/<int:pk>/reimprimir/',     ReimprimirTicketView.as_view(), name='reimprimir-ticket'),
    # Mismo comprobante que reimprimir, pero sin mandar nada a la
    # impresora: es el que usa el ayudante de carga a e-Kuatia'i.
    path('pagos/<int:pk>/comprobante/',    ComprobanteView.as_view(),      name='comprobante-pago'),
    # Devoluciones y cambios: qué se puede devolver de una venta, registrar
    # una, y las del turno.
    path('pagos/<int:pk>/devolucion/',     DevolucionResumenView.as_view(), name='devolucion-resumen'),
    path('devoluciones/',                  DevolucionesView.as_view(),     name='devoluciones'),
    path('devoluciones/<int:pk>/reimprimir/', ReimprimirDevolucionView.as_view(), name='reimprimir-devolucion'),
    path('impresora/estado/',              EstadoImpresora.as_view(),      name='estado-impresora'),

    path('kpis/',                          KPIsDashboardView.as_view(),    name='dashboard-kpis'),
    # Reportes (PDF / Excel)
    path('reportes/stock/',                ReporteStockView.as_view(),     name='reporte-stock'),
    path('reportes/ventas/',               ReporteVentasView.as_view(),    name='reporte-ventas'),
    path('reportes/caja/',                 ReporteCajaView.as_view(),      name='reporte-caja'),
    # Qué productos se vendieron (?detalle=1 abre una fila por venta)
    path('reportes/productos/',            ReporteProductosView.as_view(), name='reporte-productos'),
    # Arqueo del día (?dia=YYYY-MM-DD)
    path('reportes/arqueo/',               ReporteArqueoView.as_view(),    name='reporte-arqueo'),
]
