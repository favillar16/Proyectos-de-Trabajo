from django.contrib import admin
from .models import (
    Categoria, Marca, Acabado, TipoInstalacion,
    Producto, Variante, ImagenProducto, ImagenVariante
)


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'tipo', 'activa', 'orden']
    list_editable = ['activa', 'orden']
    list_filter = ['tipo', 'activa']


@admin.register(Marca)
class MarcaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'pais_origen', 'activa']
    list_editable = ['activa']


@admin.register(Acabado)
class AcabadoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'descripcion']


@admin.register(TipoInstalacion)
class TipoInstalacionAdmin(admin.ModelAdmin):
    list_display = ['nombre']


class ImagenProductoInline(admin.TabularInline):
    model = ImagenProducto
    extra = 1
    fields = ['imagen', 'es_principal', 'titulo', 'orden']


class VarianteInline(admin.TabularInline):
    model = Variante
    extra = 1
    fields = ['sku', 'color', 'calidad', 'acabado', 'largo_cm', 'ancho_cm', 'precio_diferencial', 'activa']
    show_change_link = True


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'nombre', 'categoria', 'marca', 'precio_base', 'unidad_venta', 'destacado', 'activo']
    list_filter = ['categoria', 'marca', 'activo', 'destacado', 'visible_showroom']
    search_fields = ['codigo', 'nombre', 'descripcion']
    list_editable = ['destacado', 'activo']
    inlines = [ImagenProductoInline, VarianteInline]
    prepopulated_fields = {'slug': ('nombre',)}


@admin.register(Variante)
class VarianteAdmin(admin.ModelAdmin):
    list_display = ['sku', 'producto', 'color', 'calidad', 'acabado', 'largo_cm', 'ancho_cm', 'precio_venta', 'activa']
    list_filter = ['activa', 'acabado']
    search_fields = ['sku', 'producto__nombre', 'color']
