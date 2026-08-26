"""
Qué se sincroniza, en qué dirección y en qué orden.

El alcance está acotado a propósito. Hay datos que **no se pueden unir con
ninguna regla** y por eso no están acá:

- `inventario.Stock` es un saldo corriente, no un valor. Si el local vendió 10
  cajas mientras la notebook estaba afuera y allá alguien tocó la cantidad, no
  existe un merge correcto: uno de los dos números está mal y no hay forma de
  saber cuál. Llega a la notebook por el `pg_dump`, de una sola dirección.
- `ventas` y `caja` mueven plata y stock reservado. `NotaPedido` usa
  `select_for_update()` justamente porque está escrito para tener un solo
  dueño; dos equipos descontando del mismo stock sin verse producen sobreventa
  irreparable.
- `facturacion.SecuenciaComprobante` numera comprobantes. Dos emisores del
  mismo número no es un problema de datos, es un problema con el DNIT.

Lo que sí está es el catálogo, que es lo que la propietaria edita en la
notebook: cargar mercadería nueva y corregir nombres y precios.
"""

# Orden de aplicación. Importa: una variante no se puede crear antes que su
# producto, ni un producto antes que su categoría. Al aplicar un lote se
# respeta este orden; para las bajas se recorre al revés.
MODELOS_BIDIRECCIONALES = [
    'productos.Categoria',
    'productos.Marca',
    'productos.Acabado',
    'productos.Producto',
    'productos.Variante',
    'productos.ImagenProducto',
    'productos.ImagenVariante',
    'ventas.Cliente',
    'costos.Proveedor',
]

# Campos que nunca viajan, por modelo. Son los que cada base calcula sola o los
# que pertenecen al equipo, no al dato.
CAMPOS_EXCLUIDOS = {
    '*': {'id', 'actualizado_en', 'nodo_origen'},
}

# Modelos cuyas filas llevan un archivo adjunto que también hay que mover.
# El campo es el `FileField`/`ImageField` con la foto.
MODELOS_CON_ARCHIVO = {
    'productos.ImagenProducto': 'imagen',
    'productos.ImagenVariante': 'imagen',
}


def es_sincronizable(etiqueta):
    return etiqueta in MODELOS_BIDIRECCIONALES


def campos_excluidos(etiqueta):
    return CAMPOS_EXCLUIDOS.get('*', set()) | CAMPOS_EXCLUIDOS.get(etiqueta, set())


def orden_de_aplicacion(etiquetas):
    """Ordena etiquetas según las dependencias de `MODELOS_BIDIRECCIONALES`."""
    posicion = {m: i for i, m in enumerate(MODELOS_BIDIRECCIONALES)}
    return sorted(etiquetas, key=lambda e: posicion.get(e, len(posicion)))
