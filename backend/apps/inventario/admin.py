from django.contrib import admin
from django.utils.html import format_html
from .models import Stock, MovimientoStock


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display  = [
        'variante', 'cantidad', 'cantidad_reservada',
        'disponible_display', 'stock_minimo', 'estado_display', 'ubicacion'
    ]
    list_filter   = ['variante__producto__categoria']
    search_fields = ['variante__sku', 'variante__producto__nombre', 'ubicacion']
    readonly_fields = ['cantidad_disponible_ro', 'estado_ro', 'fecha_actualizacion']

    def disponible_display(self, obj):
        disponible = obj.cantidad_disponible
        color = '#c00' if obj.sin_stock else ('#e68a00' if obj.en_stock_critico else '#3a9960')
        return format_html('<strong style="color:{}">{}</strong>', color, disponible)
    disponible_display.short_description = 'Disponible'

    def estado_display(self, obj):
        colores = {'sin_stock': '#c00', 'critico': '#e68a00', 'disponible': '#3a9960'}
        labels  = {'sin_stock': 'Sin stock', 'critico': 'Stock crítico', 'disponible': 'OK'}
        estado  = obj.estado
        return format_html(
            '<span style="color:{};font-weight:500">{}</span>',
            colores[estado], labels[estado]
        )
    estado_display.short_description = 'Estado'

    def cantidad_disponible_ro(self, obj):
        return obj.cantidad_disponible
    cantidad_disponible_ro.short_description = 'Cantidad disponible'

    def estado_ro(self, obj):
        return obj.estado
    estado_ro.short_description = 'Estado'


@admin.register(MovimientoStock)
class MovimientoStockAdmin(admin.ModelAdmin):
    list_display  = [
        'fecha', 'variante', 'tipo_display', 'cantidad',
        'cantidad_anterior', 'cantidad_posterior', 'usuario', 'referencia_tipo'
    ]
    list_filter   = ['tipo', 'referencia_tipo', 'usuario']
    search_fields = ['variante__sku', 'variante__producto__nombre', 'observaciones']
    readonly_fields = [
        'variante', 'tipo', 'cantidad', 'cantidad_anterior', 'cantidad_posterior',
        'referencia_tipo', 'referencia_id', 'usuario', 'observaciones', 'fecha'
    ]
    date_hierarchy = 'fecha'

    def tipo_display(self, obj):
        colores = {
            'entrada':    '#3a9960',
            'salida':     '#c00',
            'ajuste':     '#4a8ecf',
            'reserva':    '#e68a00',
            'liberacion': '#8a6ecf',
            'devolucion': '#6b6560',
        }
        return format_html(
            '<span style="color:{};font-weight:500">{}</span>',
            colores.get(obj.tipo, '#333'), obj.get_tipo_display()
        )
    tipo_display.short_description = 'Tipo'

    def has_add_permission(self, request):
        return False   # Los movimientos solo se crean por código, nunca manualmente

    def has_change_permission(self, request, obj=None):
        return False   # Registro de auditoría: inmutable

    def has_delete_permission(self, request, obj=None):
        return False
