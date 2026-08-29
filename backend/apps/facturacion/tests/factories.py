"""
Armado de datos de prueba para los tests de facturación.

No es una librería de factories: son cuatro helpers para no repetir el mismo
bloque de setUp en cada test. Se mantienen mínimos a propósito — solo los
campos que los modelos exigen — para que un cambio en un modelo ajeno rompa
un lugar y no diez.
"""
from decimal import Decimal


from apps.caja.models import Pago, SesionCaja
from apps.productos.models import Categoria, Producto, Variante
from apps.usuarios.models import Usuario
from apps.ventas.models import ItemPedido, NotaPedido

from apps.facturacion.ruc import calcular_dv

# RUC de prueba con su dígito verificador calculado, para que sea coherente
# con el validador. No es un RUC real.
BASE_RUC_EMISOR = '80012345'
RUC_EMISOR = f'{BASE_RUC_EMISOR}-{calcular_dv(BASE_RUC_EMISOR)}'

BASE_RUC_RECEPTOR = '80099887'
RUC_RECEPTOR = f'{BASE_RUC_RECEPTOR}-{calcular_dv(BASE_RUC_RECEPTOR)}'

# Configuración fiscal completa, para los tests que necesitan el SIFEN
# prendido. Se aplica con @override_settings.
DATOS_FISCALES_COMPLETOS = {
    'ruc': RUC_EMISOR,
    'razon_social': 'OGA PORA SRL',
    'direccion': 'Avda. Prueba 123',
    'telefono': '0981000000',
    'timbrado': '12345678',
    'timbrado_vto': '2027-12-31',
    'establecimiento': '001',
    'punto_expedicion': '001',
    'tipo_contribuyente': 2,
}

SIFEN_PRENDIDO = {
    'habilitado': True,
    'ambiente': 'test',
    'url_consulta_qr': 'https://ekuatia.set.gov.py/consultas/qr',
}

SIFEN_APAGADO = {
    'habilitado': False,
    'ambiente': 'test',
    'url_consulta_qr': 'https://ekuatia.set.gov.py/consultas/qr',
}


def crear_usuario(username='cajero_test', rol='cajero'):
    return Usuario.objects.create_user(
        username=username, password='clave-de-prueba', rol=rol,
        nombre_completo='Cajero De Prueba',
    )


def crear_variante(nombre='Porcelanato Prueba', precio=Decimal('100000'),
                   tasa_iva=Producto.IVA_10):
    """Una variante vendible, con su producto y categoría."""
    categoria = Categoria.objects.create(nombre=f'Cat {nombre}')
    producto = Producto.objects.create(
        nombre=nombre, categoria=categoria,
        precio_base=precio, unidad_venta=Producto.UNIDAD_M2,
        tasa_iva=tasa_iva,
    )
    return Variante.objects.create(producto=producto, color='Beige')


def crear_pedido(usuario, items=None):
    """
    Nota de pedido con ítems. `items` es una lista de
    (variante, cantidad, precio_unitario).
    """
    pedido = NotaPedido.objects.create(
        vendedor=usuario, cliente_nombre='Cliente de Prueba',
        estado=NotaPedido.ESTADO_LISTO,
    )
    for variante, cantidad, precio in (items or []):
        ItemPedido.objects.create(
            pedido=pedido, variante=variante,
            cantidad=Decimal(str(cantidad)),
            precio_unitario=Decimal(str(precio)),
        )
    return pedido


def crear_sesion(cajero):
    return SesionCaja.objects.create(
        cajero=cajero, monto_apertura=Decimal('0'),
    )


def crear_pago(pedido, sesion, cajero, monto, medio='efectivo'):
    return Pago.objects.create(
        pedido=pedido, sesion_caja=sesion, cajero=cajero,
        medio_pago=medio, monto=Decimal(str(monto)),
        estado=Pago.ESTADO_CONFIRMADO,
    )
