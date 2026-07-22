from django.contrib import admin
from .models import NotaPedido, ItemPedido, Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ['razon_social', 'ruc', 'tipo', 'condicion_venta', 'permite_ajuste_precio', 'activo']
    list_filter  = ['tipo', 'condicion_venta', 'permite_ajuste_precio', 'activo']
    search_fields = ['razon_social', 'ruc', 'telefono']


class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 0


@admin.register(NotaPedido)
class NotaPedidoAdmin(admin.ModelAdmin):
    list_display = ['numero', 'estado', 'cliente_nombre', 'total', 'total_ajustado', 'fecha_creacion']
    list_filter  = ['estado', 'fecha_creacion']
    search_fields = ['numero', 'cliente_nombre', 'cliente_ruc']
    inlines = [ItemPedidoInline]
    date_hierarchy = 'fecha_creacion'
