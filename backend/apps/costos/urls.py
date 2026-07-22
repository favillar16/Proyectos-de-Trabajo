from django.urls import path
from .views import (
    CategoriaGastoListView,
    ProveedorListCreateView, ProveedorDetailView,
    EmpleadoListCreateView, EmpleadoDetailView,
    GastoListCreateView, GastoDetailView,
    PedidoProveedorListCreateView, PedidoProveedorDetailView,
    AlertasCostosView, ResumenCostosView,
)

urlpatterns = [
    path('categorias/',        CategoriaGastoListView.as_view(),     name='categorias-gasto'),
    path('proveedores/',       ProveedorListCreateView.as_view(),    name='proveedores-list'),
    path('proveedores/<int:pk>/', ProveedorDetailView.as_view(),     name='proveedor-detail'),
    path('empleados/',         EmpleadoListCreateView.as_view(),      name='empleados-list'),
    path('empleados/<int:pk>/',EmpleadoDetailView.as_view(),          name='empleado-detail'),
    path('gastos/',            GastoListCreateView.as_view(),         name='gastos-list'),
    path('gastos/<int:pk>/',   GastoDetailView.as_view(),             name='gasto-detail'),
    path('pedidos-proveedor/', PedidoProveedorListCreateView.as_view(), name='pedidos-prov-list'),
    path('pedidos-proveedor/<int:pk>/', PedidoProveedorDetailView.as_view(), name='pedido-prov-detail'),
    path('alertas/',           AlertasCostosView.as_view(),           name='costos-alertas'),
    path('resumen/',           ResumenCostosView.as_view(),            name='costos-resumen'),
]
