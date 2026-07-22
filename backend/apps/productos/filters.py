"""
Filtros para el endpoint de productos
Permite filtrar por categoría, marca, acabado, precio, stock, etc.
"""
import django_filters
from .models import Producto, Categoria, Marca


class ProductoFilter(django_filters.FilterSet):
    categoria = django_filters.ModelChoiceFilter(queryset=Categoria.objects.all())
    categoria_tipo = django_filters.CharFilter(field_name='categoria__tipo')
    marca = django_filters.ModelChoiceFilter(queryset=Marca.objects.all())
    precio_min = django_filters.NumberFilter(field_name='precio_base', lookup_expr='gte')
    precio_max = django_filters.NumberFilter(field_name='precio_base', lookup_expr='lte')
    destacado = django_filters.BooleanFilter()
    visible_showroom = django_filters.BooleanFilter()
    con_stock = django_filters.BooleanFilter(method='filter_con_stock')

    class Meta:
        model = Producto
        fields = ['categoria', 'categoria_tipo', 'marca', 'precio_min', 'precio_max', 'destacado']

    def filter_con_stock(self, queryset, name, value):
        if value:
            return queryset.filter(
                variantes__stock__cantidad__gt=0
            ).distinct()
        return queryset
