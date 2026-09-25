"""
apps/inventario/reportes.py
Reporte imprimible del registro de ajustes de stock.

Arma la misma estructura que los reportes de caja
({'titulo', 'subtitulo', 'columnas', 'filas', 'totales'}) para renderizarse
con `apps.caja.reportes.render_pdf` / `render_xlsx`: un solo formato de hoja
para todo lo que se imprime en el local.
"""
from apps.caja.reportes import _fecha

TIPOS = {
    'entrada':    'Entrada',
    'salida':     'Salida manual',
    'ajuste':     'Cantidad exacta',
    'devolucion': 'Devolución',
}


def reporte_ajustes(movimientos, desde=None, hasta=None, buscar=''):
    """`movimientos`: queryset de MovimientoStock ya filtrado y ordenado."""
    filas = []
    sin_motivo = 0
    for m in movimientos:
        v = m.variante
        descripcion = ' — '.join(x for x in (v.producto.nombre, v.dimension_display, v.color) if x)
        if not m.observaciones:
            sin_motivo += 1
        filas.append([
            _fecha(m.fecha),
            descripcion,
            v.sku,
            TIPOS.get(m.tipo, m.get_tipo_display()),
            f'{float(m.cantidad_anterior):.2f}',
            f'{float(m.cantidad_posterior):.2f}',
            m.observaciones or 'Sin motivo cargado',
            m.usuario.nombre_completo if m.usuario_id else '',
        ])

    if desde and hasta:
        periodo = f'Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}'
    elif desde:
        periodo = f'Desde el {desde:%d/%m/%Y}'
    elif hasta:
        periodo = f'Hasta el {hasta:%d/%m/%Y}'
    else:
        periodo = 'Todos los ajustes registrados'
    if buscar:
        periodo += f' · Filtro: "{buscar}"'

    return {
        'titulo':    'Registro de Ajustes de Stock',
        'subtitulo': periodo,
        'hoja':      'Ajustes',
        'columnas':  ['Fecha', 'Producto', 'SKU', 'Movimiento', 'Antes', 'Después',
                      'Motivo', 'Usuario'],
        'cols_derecha': [4, 5],
        'filas':     filas,
        'totales': {
            'Ajustes en el reporte': len(filas),
            'Sin motivo cargado':    sin_motivo,
        },
    }
