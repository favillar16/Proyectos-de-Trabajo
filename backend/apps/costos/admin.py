from django.contrib import admin
from .models import (
    CategoriaGasto, Empleado, GastoOperativo,
    Proveedor, PedidoProveedor,
)

@admin.register(CategoriaGasto)
class CategoriaGastoAdmin(admin.ModelAdmin):
    list_display = ['nombre','tipo','activa','orden']
    list_editable = ['activa','orden']
    list_filter = ['tipo','activa']

@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ['nombre','rubro','contacto','telefono','activo']
    list_filter = ['activo']
    search_fields = ['nombre','ruc','rubro']

@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    list_display = ['nombre_completo','cargo','salario_base','activo']
    list_filter = ['activo']
    search_fields = ['nombre_completo','cargo']

@admin.register(GastoOperativo)
class GastoAdmin(admin.ModelAdmin):
    list_display = ['descripcion','categoria','proveedor','monto','metodo_pago','mes','anio','estado']
    list_filter = ['estado','categoria','metodo_pago','anio','mes']
    search_fields = ['descripcion','comprobante','cheque_numero']
    date_hierarchy = 'fecha_creacion'

@admin.register(PedidoProveedor)
class PedidoProveedorAdmin(admin.ModelAdmin):
    list_display = ['proveedor','descripcion','fecha_entrega_estimada','estado']
    list_filter = ['estado']
    search_fields = ['descripcion','proveedor__nombre']
    date_hierarchy = 'fecha_pedido'
