"""
apps/caja/reportes.py
Generación de reportes en PDF (reportlab) y Excel (openpyxl).
Cinco reportes: Stock, Balance de Ventas, Extracto de Caja, Productos
comercializados y Arqueo de Caja.

Cada función de reporte arma una estructura común:
  { 'titulo', 'subtitulo', 'columnas': [...], 'filas': [[...]], 'totales': {...} }
y luego se renderiza a PDF o XLSX con los helpers de abajo.
"""
import io
from datetime import datetime, date
from django.http import HttpResponse
from django.db.models import Sum, Count
from django.utils import timezone


# ════════════════════════════════════════════════════════
# Helpers de formato
# ════════════════════════════════════════════════════════
def _gs(v):
    try:
        return f'Gs. {int(v):,}'.replace(',', '.')
    except (ValueError, TypeError):
        return 'Gs. 0'


def _fecha(momento, formato='%d/%m/%Y %H:%M'):
    """
    Fecha y hora en la hora de Asunción.

    La base guarda los datetime en UTC (USE_TZ=True), así que llamar a
    strftime() sobre el campo tal cual imprime la hora corrida: una venta de
    las 10 de la mañana salía "14:00" en el reporte. Todo lo que se imprima
    para leer en el local pasa por acá.
    """
    if momento is None:
        return ''
    if timezone.is_aware(momento):
        momento = timezone.localtime(momento)
    return momento.strftime(formato)


# ════════════════════════════════════════════════════════
# Render a PDF (reportlab)
# ════════════════════════════════════════════════════════
def render_pdf(reporte: dict, tamanio: str = 'a4') -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm, inch
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    )
    from xml.sax.saxutils import escape

    # "Oficio" — tamaño de hoja de uso administrativo habitual en Paraguay
    # (8.5 × 13 pulgadas). Distinto del A4 (210 × 297 mm) y no incluido en
    # reportlab.lib.pagesizes (que solo trae LEGAL = 8.5 × 14").
    OFICIO = (8.5 * inch, 13 * inch)

    GOLD     = colors.HexColor('#B99C74')
    GOLDDARK = colors.HexColor('#8a7355')
    SIDEBAR  = colors.HexColor('#453941')
    BORDER   = colors.HexColor('#e8e4df')
    TEXTSEC  = colors.HexColor('#6b6560')
    TEXT     = colors.HexColor('#1a1714')

    buffer = io.BytesIO()
    muchas_cols = len(reporte['columnas']) > 5
    base_pagesize = OFICIO if tamanio == 'oficio' else A4
    pagesize = landscape(base_pagesize) if muchas_cols else base_pagesize
    doc = SimpleDocTemplate(buffer, pagesize=pagesize,
                            topMargin=18*mm, bottomMargin=20*mm,
                            leftMargin=14*mm, rightMargin=14*mm)

    styles = getSampleStyleSheet()
    st_titulo = ParagraphStyle('titulo', parent=styles['Title'],
        fontSize=18, textColor=SIDEBAR, spaceAfter=2, alignment=0)
    st_marca = ParagraphStyle('marca', parent=styles['Normal'],
        fontSize=10, textColor=GOLDDARK, spaceAfter=1)
    st_sub = ParagraphStyle('sub', parent=styles['Normal'],
        fontSize=9, textColor=TEXTSEC, spaceAfter=12)
    st_th = ParagraphStyle('th', parent=styles['Normal'],
        fontSize=8.5, textColor=GOLD, fontName='Helvetica-Bold', leading=11)
    st_celda = ParagraphStyle('celda', parent=styles['Normal'],
        fontSize=8, textColor=TEXT, leading=10)
    st_celda_der = ParagraphStyle('celda_der', parent=st_celda, alignment=2)

    elementos = []
    elementos.append(Paragraph('ÓGA PORÃ — Acabados de Construcción', st_marca))
    elementos.append(Paragraph(reporte['titulo'], st_titulo))
    sub = reporte.get('subtitulo', '')
    generado = datetime.now().strftime('%d/%m/%Y %H:%M')
    elementos.append(Paragraph(f'{sub}  ·  Generado: {generado}', st_sub))

    # ── Tabla ────────────────────────────────────────────────
    # colWidths explícitos: sin esto reportlab no envuelve el texto y da
    # a cada columna su ancho "natural", desbordando la hoja apenas hay
    # nombres largos de producto o cliente. Las celdas van en Paragraph
    # (en vez de strings planos) para que sí hagan wrap dentro del ancho
    # asignado, y escapadas porque son texto libre cargado por el usuario.
    columnas    = reporte['columnas']
    cols_der    = set(reporte.get('cols_derecha', []))
    n_cols      = len(columnas)
    ancho_total = pagesize[0] - doc.leftMargin - doc.rightMargin

    ancho_num   = ancho_total * 0.09
    n_texto     = max(n_cols - len(cols_der), 1)
    ancho_texto = (ancho_total - ancho_num * len(cols_der)) / n_texto
    col_widths  = [ancho_num if i in cols_der else ancho_texto for i in range(n_cols)]

    header = [Paragraph(escape(str(c)), st_th) for c in columnas]
    filas_pdf = []
    for fila in reporte['filas']:
        fila_pdf = []
        for i, valor in enumerate(fila):
            estilo_celda = st_celda_der if i in cols_der else st_celda
            fila_pdf.append(Paragraph(escape(str(valor)), estilo_celda))
        filas_pdf.append(fila_pdf)

    tabla = Table([header] + filas_pdf, repeatRows=1, colWidths=col_widths)
    tabla.setStyle(TableStyle([
        ('BACKGROUND',     (0,0), (-1,0), SIDEBAR),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#fafaf9')]),
        ('GRID',           (0,0), (-1,-1), 0.5, BORDER),
        ('VALIGN',         (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',     (0,0), (-1,-1), 5),
        ('BOTTOMPADDING',  (0,0), (-1,-1), 5),
        ('LEFTPADDING',    (0,0), (-1,-1), 6),
        ('RIGHTPADDING',   (0,0), (-1,-1), 6),
    ]))
    elementos.append(tabla)

    # Totales
    if reporte.get('totales'):
        elementos.append(Spacer(1, 10))
        for k, v in reporte['totales'].items():
            elementos.append(Paragraph(
                f'<b>{escape(str(k))}:</b> {escape(str(v))}',
                ParagraphStyle('tot', parent=styles['Normal'],
                    fontSize=10, textColor=SIDEBAR, alignment=2, spaceAfter=2)))

    def _pie_pagina(canvas, doc_):
        """Pie con marca y número de página — evita hojas sueltas sin identificar."""
        canvas.saveState()
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(TEXTSEC)
        ancho_pagina = doc_.pagesize[0]
        canvas.drawString(doc_.leftMargin, 10*mm, 'Oga Porã — Documento de uso interno')
        canvas.drawRightString(ancho_pagina - doc_.rightMargin, 10*mm, f'Página {doc_.page}')
        canvas.restoreState()

    doc.build(elementos, onFirstPage=_pie_pagina, onLaterPages=_pie_pagina)
    return buffer.getvalue()


# ════════════════════════════════════════════════════════
# Render a Excel (openpyxl)
# ════════════════════════════════════════════════════════
def render_xlsx(reporte: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = Workbook()
    ws = wb.active
    ws.title = reporte.get('hoja', 'Reporte')[:31]

    GOLD_FILL = PatternFill('solid', fgColor='453941')
    GOLD_FONT = Font(color='B99C74', bold=True, size=11)
    borde = Border(*[Side(style='thin', color='E8E4DF')]*4)

    # Encabezado del documento
    ws['A1'] = 'ÓGA PORÃ — Acabados de Construcción'
    ws['A1'].font = Font(color='8a7355', bold=True, size=12)
    ws['A2'] = reporte['titulo']
    ws['A2'].font = Font(color='453941', bold=True, size=14)
    ws['A3'] = f"{reporte.get('subtitulo','')}  ·  Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws['A3'].font = Font(color='6b6560', size=9)

    fila_header = 5
    # Cabecera de columnas
    for col_idx, titulo in enumerate(reporte['columnas'], 1):
        c = ws.cell(row=fila_header, column=col_idx, value=titulo)
        c.fill = GOLD_FILL; c.font = GOLD_FONT
        c.alignment = Alignment(horizontal='left', vertical='center')
        c.border = borde

    # Filas de datos
    for r_idx, fila in enumerate(reporte['filas'], fila_header+1):
        for c_idx, valor in enumerate(fila, 1):
            c = ws.cell(row=r_idx, column=c_idx, value=valor)
            c.border = borde
            c.font = Font(size=10)
            if (c_idx-1) in reporte.get('cols_derecha', []):
                c.alignment = Alignment(horizontal='right')

    # Anchos de columna automáticos
    for col_idx, titulo in enumerate(reporte['columnas'], 1):
        max_len = len(str(titulo))
        for fila in reporte['filas']:
            if col_idx-1 < len(fila):
                max_len = max(max_len, len(str(fila[col_idx-1])))
        ws.column_dimensions[ws.cell(row=fila_header, column=col_idx).column_letter].width = min(max_len+3, 45)

    # Totales
    if reporte.get('totales'):
        fila_tot = fila_header + len(reporte['filas']) + 2
        for k, v in reporte['totales'].items():
            ws.cell(row=fila_tot, column=1, value=k).font = Font(bold=True, color='453941')
            ws.cell(row=fila_tot, column=2, value=v).font = Font(bold=True)
            fila_tot += 1

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ════════════════════════════════════════════════════════
# Construcción de cada reporte
# ════════════════════════════════════════════════════════
def reporte_stock():
    from apps.inventario.models import Stock
    qs = Stock.objects.select_related('variante__producto').all()

    filas = []
    total_unidades = 0
    sin_stock = 0
    criticos = 0
    for s in qs:
        disp = float(s.cantidad_disponible)
        total_unidades += disp
        if s.sin_stock: sin_stock += 1
        elif s.en_stock_critico: criticos += 1
        estado = 'Sin stock' if s.sin_stock else ('Crítico' if s.en_stock_critico else 'Disponible')
        filas.append([
            s.variante.producto.nombre,
            s.variante.sku,
            str(s.variante),
            f'{float(s.cantidad):.2f}',
            f'{float(s.cantidad_reservada):.2f}',
            f'{disp:.2f}',
            f'{float(s.stock_minimo):.2f}',
            estado,
        ])
    filas.sort(key=lambda f: f[0])

    return {
        'titulo':    'Reporte de Stock',
        'subtitulo': f'{qs.count()} variantes registradas',
        'hoja':      'Stock',
        'columnas':  ['Producto','SKU','Variante','Stock','Reservado','Disponible','Mínimo','Estado'],
        'cols_derecha': [3,4,5,6],
        'filas':     filas,
        'totales': {
            'Variantes sin stock':  sin_stock,
            'Variantes en crítico': criticos,
            'Total unidades disponibles': f'{total_unidades:.2f}',
        },
    }


def reporte_ventas(desde: date, hasta: date):
    from apps.caja.models import Pago

    pagos = Pago.objects.filter(
        estado=Pago.ESTADO_CONFIRMADO,
        fecha__date__gte=desde,
        fecha__date__lte=hasta,
    ).select_related('pedido', 'cajero').order_by('fecha')

    filas = []
    total_general = 0
    por_medio = {}
    for p in pagos:
        monto = float(p.monto)
        total_general += monto
        medio = p.get_medio_pago_display()
        por_medio[medio] = por_medio.get(medio, 0) + monto
        filas.append([
            _fecha(p.fecha),
            p.numero_ticket or '—',
            p.pedido.numero if p.pedido else '—',
            p.pedido.cliente_nombre if p.pedido and p.pedido.cliente_nombre else 'Consumidor Final',
            medio,
            p.cajero.nombre_completo,
            _gs(monto),
        ])

    totales = {'Total de ventas': _gs(total_general),
               'Cantidad de cobros': len(filas)}
    for medio, m in por_medio.items():
        totales[f'  · {medio}'] = _gs(m)

    return {
        'titulo':    'Balance de Ventas',
        'subtitulo': f'Del {desde.strftime("%d/%m/%Y")} al {hasta.strftime("%d/%m/%Y")}',
        'hoja':      'Ventas',
        'columnas':  ['Fecha','Ticket','Pedido','Cliente','Medio','Cajero','Monto'],
        'cols_derecha': [6],
        'filas':     filas,
        'totales':   totales,
    }


def reporte_caja(desde: date, hasta: date):
    from apps.caja.models import SesionCaja, Pago

    sesiones = SesionCaja.objects.filter(
        fecha_apertura__date__gte=desde,
        fecha_apertura__date__lte=hasta,
    ).select_related('cajero').order_by('fecha_apertura')

    filas = []
    total_ventas = 0
    for s in sesiones:
        ventas = Pago.objects.filter(
            sesion_caja=s, estado=Pago.ESTADO_CONFIRMADO
        ).aggregate(t=Sum('monto'))['t'] or 0
        total_ventas += float(ventas)
        filas.append([
            _fecha(s.fecha_apertura),
            _fecha(s.fecha_cierre) if s.fecha_cierre else 'Abierta',
            s.cajero.nombre_completo,
            _gs(s.monto_apertura),
            _gs(s.monto_cierre) if s.monto_cierre is not None else '—',
            _gs(ventas),
            'Cerrada' if s.estado == 'cerrada' else 'Abierta',
        ])

    return {
        'titulo':    'Extracto de Caja',
        'subtitulo': f'Del {desde.strftime("%d/%m/%Y")} al {hasta.strftime("%d/%m/%Y")}',
        'hoja':      'Caja',
        'columnas':  ['Apertura','Cierre','Cajero','M. Apertura','M. Cierre','Ventas','Estado'],
        'cols_derecha': [3,4,5],
        'filas':     filas,
        'totales': {
            'Sesiones': len(filas),
            'Total ventas del período': _gs(total_ventas),
        },
    }


def _cantidad(valor, unidad=''):
    """
    Cantidad con dos decimales y su unidad.

    Los productos que se venden por m² se piden en fracciones (media caja,
    3,15 m²), así que redondear a entero cambia el número que la propietaria
    usa para reponer. Se muestra el valor exacto, con la unidad al lado para
    que se lea qué se está contando.
    """
    try:
        texto = f'{float(valor):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    except (ValueError, TypeError):
        texto = '0,00'
    return f'{texto} {unidad}'.strip()


UNIDAD_CORTA = {
    'm2': 'm²', 'pieza': 'u.', 'juego': 'jgo.', 'caja': 'cajas', 'ml': 'ml',
}


def _items_vendidos(desde: date, hasta: date):
    """
    Ítems efectivamente comercializados en el período, con la fecha del cobro.

    La fecha que importa para "qué se vendió y cuándo" es la del cobro
    confirmado, no la de creación del pedido: un presupuesto armado el lunes
    y cobrado el jueves se vendió el jueves. Por eso se entra por Pago y no
    por NotaPedido.
    """
    from apps.caja.models import Pago

    pagos = Pago.objects.filter(
        estado=Pago.ESTADO_CONFIRMADO,
        fecha__date__gte=desde,
        fecha__date__lte=hasta,
    ).select_related('pedido').prefetch_related(
        'pedido__items__variante__producto',
        'pedido__items__variante__acabado',
    ).order_by('fecha')

    for pago in pagos:
        if not pago.pedido:
            continue
        for item in pago.pedido.items.all():
            yield pago, item


def reporte_productos(desde: date, hasta: date, detalle: bool = False):
    """
    Qué productos se vendieron en el período.

    Dos vistas del mismo dato, porque responden preguntas distintas:
      · agregado (default) — cuánto se vendió de cada variante. Es el que
        sirve para reponer: dice qué comprar y en qué cantidad.
      · detalle  — una fila por venta, con la fecha. Es el que sirve para
        rastrear una venta puntual o ver el ritmo de salida de un producto.

    El Balance de Ventas sigue existiendo y no cambia: ahí una venta es una
    línea con el número de pedido. Acá se abre en los productos que la
    componen, que es justamente lo que ese reporte no muestra.
    """
    filas = []
    total_ingresos = 0.0
    subtitulo_rango = f'Del {desde.strftime("%d/%m/%Y")} al {hasta.strftime("%d/%m/%Y")}'

    if detalle:
        for pago, item in _items_vendidos(desde, hasta):
            variante = item.variante
            unidad = UNIDAD_CORTA.get(variante.producto.unidad_venta,
                                      variante.producto.unidad_venta)
            subtotal = float(item.subtotal)
            total_ingresos += subtotal
            filas.append([
                _fecha(pago.fecha),
                variante.producto.nombre,
                str(variante),
                variante.sku,
                _cantidad(item.cantidad, unidad),
                _gs(item.precio_unitario),
                _gs(subtotal),
                pago.pedido.cliente_nombre or 'Consumidor Final',
                pago.pedido.numero,
            ])

        return {
            'titulo':    'Productos comercializados — detalle por fecha',
            'subtitulo': subtitulo_rango,
            'hoja':      'Productos por fecha',
            'columnas':  ['Fecha', 'Producto', 'Variante', 'SKU', 'Cantidad',
                          'Precio unit.', 'Total', 'Cliente', 'Pedido'],
            'cols_derecha': [4, 5, 6],
            'filas':     filas,
            'totales': {
                'Líneas de venta': len(filas),
                'Total facturado': _gs(total_ingresos),
            },
        }

    # ── Agregado por variante ────────────────────────────────
    acumulado = {}
    for pago, item in _items_vendidos(desde, hasta):
        variante = item.variante
        registro = acumulado.setdefault(variante.id, {
            'producto': variante.producto.nombre,
            'variante': str(variante),
            'sku':      variante.sku,
            'unidad':   UNIDAD_CORTA.get(variante.producto.unidad_venta,
                                         variante.producto.unidad_venta),
            'cantidad': 0.0,
            'ingresos': 0.0,
            'ventas':   0,
            'primera':  pago.fecha,
            'ultima':   pago.fecha,
        })
        registro['cantidad'] += float(item.cantidad)
        registro['ingresos'] += float(item.subtotal)
        registro['ventas']   += 1
        registro['primera'] = min(registro['primera'], pago.fecha)
        registro['ultima']  = max(registro['ultima'],  pago.fecha)

    for r in sorted(acumulado.values(), key=lambda r: -r['ingresos']):
        total_ingresos += r['ingresos']
        filas.append([
            r['producto'],
            r['variante'],
            r['sku'],
            _cantidad(r['cantidad'], r['unidad']),
            r['ventas'],
            _fecha(r['primera'], '%d/%m/%Y'),
            _fecha(r['ultima'], '%d/%m/%Y'),
            _gs(r['ingresos']),
        ])

    return {
        'titulo':    'Productos comercializados',
        'subtitulo': subtitulo_rango,
        'hoja':      'Productos',
        'columnas':  ['Producto', 'Variante', 'SKU', 'Cantidad vendida',
                      'Ventas', 'Primera venta', 'Última venta', 'Ingresos'],
        'cols_derecha': [3, 4, 7],
        'filas':     filas,
        'totales': {
            'Variantes distintas vendidas': len(filas),
            'Total facturado': _gs(total_ingresos),
        },
    }


# Denominaciones del guaraní, para la planilla de conteo físico.
# Se imprimen en blanco: las completa a mano quien cuenta la caja.
DENOMINACIONES = [100000, 50000, 20000, 10000, 5000, 2000, 1000, 500, 100, 50]


def reporte_arqueo(dia: date):
    """
    Arqueo de caja de un día: lo que el sistema dice que tiene que haber,
    contra lo que se cuenta a mano.

    Se arma como lista de conceptos y no como tabla de sesiones porque es una
    planilla para completar en el mostrador, no un listado para leer: va
    sesión por sesión, con el detalle de cobros por medio de pago, el efectivo
    esperado, lo declarado al cierre y la diferencia. Al final lleva la
    grilla de denominaciones en blanco para el conteo físico.

    Solo el efectivo entra en la diferencia. Una tarjeta o una transferencia
    no están en el cajón: confirmarlas contra el extracto es otra tarea, y
    mezclarlas acá haría que un arqueo correcto parezca descuadrado.
    """
    from apps.caja.models import SesionCaja, Pago

    sesiones = SesionCaja.objects.filter(
        fecha_apertura__date=dia,
    ).select_related('cajero').order_by('fecha_apertura')

    filas = []
    total_cobrado_dia = 0.0
    total_efectivo_dia = 0.0
    diferencia_dia = 0.0

    for sesion in sesiones:
        pagos = Pago.objects.filter(sesion_caja=sesion, estado=Pago.ESTADO_CONFIRMADO)

        por_medio = {}
        for medio, etiqueta in Pago.MEDIOS:
            agg = pagos.filter(medio_pago=medio).aggregate(
                total=Sum('monto'), cantidad=Count('id'))
            monto = float(agg['total'] or 0)
            if monto or agg['cantidad']:
                por_medio[medio] = (etiqueta, monto, int(agg['cantidad'] or 0))

        cobrado = sum(m for _, m, _ in por_medio.values())
        efectivo = por_medio.get(Pago.MEDIO_EFECTIVO, ('', 0.0, 0))[1]
        apertura = float(sesion.monto_apertura or 0)
        esperado = apertura + efectivo

        total_cobrado_dia  += cobrado
        total_efectivo_dia += efectivo

        cierre_txt = (_fecha(sesion.fecha_cierre, '%H:%M')
                      if sesion.fecha_cierre else 'todavía abierta')
        filas.append([
            f'CAJA DE {sesion.cajero.nombre_completo.upper()}',
            f'{_fecha(sesion.fecha_apertura, "%H:%M")} a {cierre_txt}',
            '',
        ])
        filas.append(['   Monto de apertura', '', _gs(apertura)])

        for etiqueta, monto, cantidad in por_medio.values():
            plural = 's' if cantidad != 1 else ''
            filas.append([
                f'   Cobrado en {etiqueta.lower()}',
                f'{cantidad} cobro{plural}',
                _gs(monto),
            ])
        if not por_medio:
            filas.append(['   Sin cobros registrados', '', _gs(0)])

        filas.append(['   Total cobrado en el turno', '', _gs(cobrado)])
        filas.append(['   Efectivo que debe haber en el cajón',
                      'apertura + cobros en efectivo', _gs(esperado)])

        if sesion.monto_cierre is not None:
            declarado = float(sesion.monto_cierre)
            diferencia = declarado - esperado
            diferencia_dia += diferencia
            if abs(diferencia) < 0.005:
                leyenda = 'cuadra'
            else:
                leyenda = 'sobrante' if diferencia > 0 else 'faltante'
            filas.append(['   Declarado al cerrar', '', _gs(declarado)])
            filas.append(['   Diferencia', leyenda, _gs(abs(diferencia))])
        else:
            filas.append(['   Declarado al cerrar', 'la caja sigue abierta', '________'])
            filas.append(['   Diferencia', 'se calcula al cerrar', '________'])

        if sesion.observaciones_cierre:
            filas.append(['   Observaciones del cierre', sesion.observaciones_cierre, ''])
        filas.append(['', '', ''])

    if not filas:
        filas.append(['No hubo sesiones de caja este día', '', ''])
        filas.append(['', '', ''])

    # ── Conteo físico, para completar a mano ─────────────────
    filas.append(['CONTEO FÍSICO DEL EFECTIVO', 'cantidad', 'importe'])
    for valor in DENOMINACIONES:
        filas.append([f'   {_gs(valor)}', '__________', '__________'])
    filas.append(['   TOTAL CONTADO', '', '__________'])
    filas.append(['', '', ''])
    filas.append(['Cuenta el efectivo', 'firma', '__________________'])
    filas.append(['Controla', 'firma', '__________________'])

    return {
        'titulo':    'Arqueo de Caja',
        'subtitulo': f'Día {dia.strftime("%d/%m/%Y")} · {sesiones.count()} sesión(es)',
        'hoja':      'Arqueo',
        'columnas':  ['Concepto', 'Detalle', 'Monto'],
        'cols_derecha': [2],
        'filas':     filas,
        'totales': {
            'Total cobrado en el día':   _gs(total_cobrado_dia),
            'De eso, en efectivo':       _gs(total_efectivo_dia),
            'Diferencia acumulada':      _gs(diferencia_dia),
        },
    }


# ════════════════════════════════════════════════════════
# Entrega como HttpResponse
# ════════════════════════════════════════════════════════
def responder_reporte(reporte: dict, formato: str, nombre_base: str, tamanio: str = 'a4') -> HttpResponse:
    hoy = date.today().strftime('%Y%m%d')
    if formato == 'pdf':
        contenido = render_pdf(reporte, tamanio=tamanio)
        resp = HttpResponse(contenido, content_type='application/pdf')
        resp['Content-Disposition'] = f'attachment; filename="{nombre_base}_{hoy}.pdf"'
        return resp
    else:  # xlsx
        contenido = render_xlsx(reporte)
        resp = HttpResponse(
            contenido,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp['Content-Disposition'] = f'attachment; filename="{nombre_base}_{hoy}.xlsx"'
        return resp
