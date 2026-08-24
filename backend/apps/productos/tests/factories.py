"""
Armado de datos de prueba para los tests de productos.

Mismo criterio que apps/facturacion/tests/factories.py: no es una librería de
factories, son helpers mínimos para no repetir el setUp en cada test.
"""
from decimal import Decimal

from apps.productos.models import Categoria, Producto, Variante
from apps.usuarios.models import Usuario


def crear_usuario(username='tester', rol=Usuario.ROL_ADMIN):
    return Usuario.objects.create_user(
        username=username, password='clave-de-prueba', rol=rol,
        nombre_completo=f'Usuario {username}',
    )


def crear_producto(nombre='Porcelanato Roma', tipo='porcelanato',
                   precio=Decimal('150000')):
    categoria = Categoria.objects.create(nombre=f'Cat {nombre}', tipo=tipo)
    return Producto.objects.create(
        nombre=nombre, categoria=categoria,
        precio_base=precio, unidad_venta=Producto.UNIDAD_M2,
    )


def crear_variante(producto=None, color='Beige', **extra):
    return Variante.objects.create(
        producto=producto or crear_producto(),
        color=color,
        **extra,
    )
