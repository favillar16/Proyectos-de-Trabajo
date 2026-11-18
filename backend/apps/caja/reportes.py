"""
apps/caja/reportes.py
Generación de reportes en PDF (reportlab) y Excel (openpyxl).
Siete reportes: Stock, Balance de Ventas, Extracto de Caja, Productos
comercializados, Ganancias, Comisiones bancarias y Arqueo de Caja.

Cada función de reporte arma una estructura común:
  { 'titulo', 'subtitulo', 'columnas': [...], 'filas': [[...]], 'totales': {...} }
y, opcionales:
  'notas'        aclaraciones en castellano llano, debajo de los totales.
  'resumen'      lo que se mira primero: {'destacados': [(etiqueta, valor,
                 nota)], 'desglose': {'titulo', 'columnas', 'filas',
                 'cols_derecha'}}. En el PDF va arriba de la hoja 1, antes del
                 detalle; con 'hoja_aparte' ocupa la hoja 1 entera y el detalle
                 empieza en la 2 (Ganancias, a pedido de la propietaria).
  'solo_excel'   columnas que el PDF no imprime (SKU, cajero): sirven para
                 buscar y filtrar en la planilla, en papel solo ocupan lugar.
  'filas_titulo' índices de filas que son encabezado de sección (el arqueo).
  'titulo_detalle' el título de la tabla de detalle cuando hay resumen.
  'totales_solo_excel' el PDF no repite los totales (el arqueo: ya están en
                 el resumen y debajo de las firmas no se leerían).

Rediseño del 18/11/2026: la propietaria tenía que llegar a la última hoja
para ver los totales, las cantidades salían "3.00" sin unidad, los montos se
partían en dos renglones y el Excel traía los importes como texto, imposibles
de sumar.
"""
import io
import re
from decimal import Decimal
from datetime import datetime, date
from django.http import HttpResponse
from django.db.models import Count, Q, Sum
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


def _rango(desde, hasta):
    if desde == hasta:
        return f'Día {desde.strftime("%d/%m/%Y")}'
    return f'Del {desde.strftime("%d/%m/%Y")} al {hasta.strftime("%d/%m/%Y")}'


def _variante_txt(v):
    """
    Lo que distingue a la variante dentro del producto: "60×60 cm — Beige —
    Mate". `str(variante)` repite adelante el nombre del producto, que ya está
    en la columna de al lado, y en la hoja eso duplicaba cada renglón.
    """
    partes = [v.dimension_display, v.color, v.acabado.nombre if v.acabado_id else '']
    return ' — '.join(p for p in partes if p) or '—'


def _es_negativo(texto):
    return isinstance(texto, str) and re.match(r'^-\s?(Gs\.\s)?\d', texto) is not None


# ════════════════════════════════════════════════════════
# Render a PDF (reportlab)
# ════════════════════════════════════════════════════════
def render_pdf(reporte: dict, tamanio: str = 'a4') -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm, inch
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether,
        PageBreak,
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
    FONDO    = colors.HexColor('#fafaf9')
    TINTE    = colors.HexColor('#f3ede4')
    ROJO     = '#b3261e'

    # Las columnas que se imprimen: las de solo Excel quedan afuera.
    ocultas  = set(reporte.get('solo_excel', []))
    visibles = [i for i in range(len(reporte['columnas'])) if i not in ocultas]
    cols_der = set(reporte.get('cols_derecha', []))

    buffer = io.BytesIO()
    base_pagesize = OFICIO if tamanio == 'oficio' else A4
    pagesize = landscape(base_pagesize) if len(visibles) > 5 else base_pagesize
    doc = SimpleDocTemplate(buffer, pagesize=pagesize,
                            topMargin=16*mm, bottomMargin=18*mm,
                            leftMargin=14*mm, rightMargin=14*mm,
                            title=reporte['titulo'], author='Oga Porã')
    ancho_total = pagesize[0] - doc.leftMargin - doc.rightMargin

    styles = getSampleStyleSheet()
    st_titulo = ParagraphStyle('titulo', parent=styles['Title'],
        fontSize=18, textColor=SIDEBAR, spaceAfter=2, alignment=0)
    st_marca = ParagraphStyle('marca', parent=styles['Normal'],
        fontSize=10, textColor=GOLDDARK, spaceAfter=1)
    st_sub = ParagraphStyle('sub', parent=styles['Normal'],
        fontSize=9, textColor=TEXTSEC, spaceAfter=10)
    st_seccion = ParagraphStyle('seccion', parent=styles['Normal'],
        fontSize=11, fontName='Helvetica-Bold', textColor=SIDEBAR, spaceBefore=4, spaceAfter=6)
    st_th = ParagraphStyle('th', parent=styles['Normal'],
        fontSize=8.5, textColor=GOLD, fontName='Helvetica-Bold', leading=11)
    st_th_der = ParagraphStyle('th_der', parent=st_th, alignment=2)
    st_celda = ParagraphStyle('celda', parent=styles['Normal'],
        fontSize=8.5, textColor=TEXT, leading=10.5)
    st_celda_der = ParagraphStyle('celda_der', parent=st_celda, alignment=2)
    st_nota = ParagraphStyle('nota', parent=styles['Normal'],
        fontSize=8.5, textColor=TEXTSEC, leading=11, spaceAfter=4)
    st_notas_tit = ParagraphStyle('notas_tit', parent=styles['Normal'],
        fontSize=9.5, textColor=SIDEBAR, spaceAfter=4)

    def celda(valor, derecha=False, negrita=False):
        texto = escape(str(valor))
        if negrita:
            texto = f'<b>{texto}</b>'
        if _es_negativo(valor):
            texto = f'<font color="{ROJO}">{texto}</font>'
        return Paragraph(texto, st_celda_der if derecha else st_celda)

    def anchos(columnas, filas, derecha, disponible):
        """
        Ancho de cada columna según lo que tiene adentro. Antes las numéricas
        tenían un 9 % fijo de la hoja y en una tabla de tres columnas un
        "Gs. 1.518.000" se partía en dos renglones; las de texto se repartían
        parejo, y un SKU largo se cortaba a la mitad.
        """
        def medida(texto, negrita=False):
            fuente = 'Helvetica-Bold' if negrita else 'Helvetica'
            return stringWidth(str(texto), fuente, 8.5) + 13

        necesario = []
        for i, titulo in enumerate(columnas):
            # El encabezado puede ir en dos renglones: cuenta su palabra más larga.
            ancho = max(medida(p, True) for p in str(titulo).split() or [''])
            for fila in filas:
                if i < len(fila):
                    ancho = max(ancho, medida(fila[i]))
            # Un texto libre muy largo (observaciones, nombres) envuelve.
            necesario.append(ancho if i in derecha else min(ancho, 70 * mm))

        # No se parten: los números y todo lo corto (fechas, medios, estados).
        # Solo envuelve el texto largo, que es el que puede ir en dos renglones.
        fijas = {i for i, a in enumerate(necesario) if i in derecha or a <= 34 * mm}
        fijo = sum(a for i, a in enumerate(necesario) if i in fijas)
        texto = sum(a for i, a in enumerate(necesario) if i not in fijas)
        if fijo + texto <= disponible:
            # Sobra lugar: se lo llevan las columnas de texto (o todas, si no hay).
            extra = disponible - fijo - texto
            if texto:
                return [a if i in fijas else a + extra * a / texto
                        for i, a in enumerate(necesario)]
            return [a * disponible / fijo for a in necesario]
        if texto and fijo < disponible * 0.8:
            # Falta: lo fijo queda entero y el texto largo envuelve.
            resto = disponible - fijo
            return [a if i in fijas else a * resto / texto for i, a in enumerate(necesario)]
        return [a * disponible / (fijo + texto) for a in necesario]

    def tabla_de(columnas, filas, derecha, ancho, titulos=frozenset()):
        cols = list(range(len(columnas)))
        header = [Paragraph(escape(str(c)), st_th_der if i in derecha else st_th)
                  for i, c in enumerate(columnas)]
        cuerpo = []
        for fila in filas:
            cuerpo.append([celda(fila[i] if i < len(fila) else '', i in derecha)
                           for i in cols])
        estilo = [
            ('BACKGROUND',     (0,0), (-1,0), SIDEBAR),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, FONDO]),
            ('LINEBELOW',      (0,0), (-1,-1), 0.4, BORDER),
            ('BOX',            (0,0), (-1,-1), 0.5, BORDER),
            ('VALIGN',         (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING',     (0,0), (-1,-1), 4),
            ('BOTTOMPADDING',  (0,0), (-1,-1), 4),
            ('LEFTPADDING',    (0,0), (-1,-1), 6),
            ('RIGHTPADDING',   (0,0), (-1,-1), 6),
        ]
        for f in titulos:
            # Encabezado de sección (una caja en el arqueo): fondo y negrita.
            estilo.append(('BACKGROUND', (0, f + 1), (-1, f + 1), TINTE))
            estilo.append(('FONTNAME', (0, f + 1), (-1, f + 1), 'Helvetica-Bold'))
            cuerpo[f] = [celda(filas[f][i] if i < len(filas[f]) else '', i in derecha, True)
                         for i in cols]
        tabla = Table([header] + cuerpo, repeatRows=1,
                      colWidths=anchos(columnas, filas, derecha, ancho))
        tabla.setStyle(TableStyle(estilo))
        return tabla

    def cuenta(totales, ancho):
        """
        Los totales como una cuenta de dos columnas: lo que se suma, lo que se
        resta (-) y el resultado (=) en negrita con raya arriba. Antes eran
        renglones sueltos alineados a la derecha, difíciles de seguir.
        """
        st_c = ParagraphStyle('c', parent=styles['Normal'], fontSize=9.5, textColor=TEXT, leading=12)
        st_c_sub = ParagraphStyle('c_sub', parent=st_c, fontSize=8.5, textColor=TEXTSEC, leftIndent=10)
        st_c_der = ParagraphStyle('c_der', parent=st_c, alignment=2)
        st_c_der_sub = ParagraphStyle('c_der_sub', parent=st_c_sub, alignment=2, leftIndent=0)
        filas, estilo = [], [
            ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING',    (0,0), (-1,-1), 3.5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
            ('LEFTPADDING',   (0,0), (-1,-1), 4),
            ('RIGHTPADDING',  (0,0), (-1,-1), 4),
            ('LINEBELOW',     (0,0), (-1,-1), 0.3, BORDER),
        ]
        for i, (k, v) in enumerate(totales.items()):
            sub = str(k).startswith('  ·')
            k_txt = escape(str(k).replace('  · ', '').strip())
            v_txt = escape(str(v))
            if _es_negativo(v):
                v_txt = f'<font color="{ROJO}">{v_txt}</font>'
            if k_txt.startswith('(=)'):
                k_txt, v_txt = f'<b>{k_txt}</b>', f'<b>{v_txt}</b>'
                estilo.append(('LINEABOVE', (0,i), (-1,i), 0.8, SIDEBAR))
            if 'Ganancia neta' in k_txt:
                estilo.append(('BACKGROUND', (0,i), (-1,i), TINTE))
            filas.append([Paragraph(k_txt, st_c_sub if sub else st_c),
                          Paragraph(v_txt, st_c_der_sub if sub else st_c_der)])
        t = Table(filas, colWidths=[ancho * 0.66, ancho * 0.34])
        t.setStyle(TableStyle(estilo))
        return t

    def recuadros(destacados):
        """Las cifras que importan, grandes y en recuadros, arriba de todo."""
        st_k_lbl = ParagraphStyle('k_lbl', parent=styles['Normal'], fontSize=8,
            textColor=TEXTSEC, leading=10)
        st_k_val = ParagraphStyle('k_val', parent=styles['Normal'], fontSize=15,
            fontName='Helvetica-Bold', textColor=SIDEBAR, leading=19)
        st_k_nota = ParagraphStyle('k_nota', parent=st_k_lbl, textColor=GOLDDARK)
        celdas = []
        for etiqueta, valor, nota in destacados:
            val = escape(str(valor))
            if _es_negativo(valor):
                val = f'<font color="{ROJO}">{val}</font>'
            celdas.append([
                Paragraph(escape(etiqueta).upper(), st_k_lbl),
                Paragraph(val, st_k_val),
                Paragraph(escape(nota or ''), st_k_nota),
            ])
        n = len(celdas)
        cajas = Table([celdas], colWidths=[ancho_total / n] * n)
        cajas.setStyle(TableStyle([
            ('BOX',           (0,0), (-1,-1), 0.5, BORDER),
            ('LINEBEFORE',    (1,0), (-1,-1), 0.5, BORDER),
            ('BACKGROUND',    (0,0), (-1,-1), FONDO),
            ('VALIGN',        (0,0), (-1,-1), 'TOP'),
            ('TOPPADDING',    (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('LEFTPADDING',   (0,0), (-1,-1), 10),
        ]))
        return cajas

    notas = ([Paragraph('<b>Cómo leer este reporte</b>', st_notas_tit)]
             + [Paragraph(escape(n), st_nota) for n in reporte.get('notas', [])])

    # ── Encabezado ───────────────────────────────────────────
    elementos = []
    resumen = reporte.get('resumen')
    hoja_aparte = bool(resumen and resumen.get('hoja_aparte'))
    sub = reporte.get('subtitulo', '')
    generado = timezone.localtime().strftime('%d/%m/%Y %H:%M')
    elementos.append(Paragraph('ÓGA PORÃ — Acabados de Construcción', st_marca))
    elementos.append(Paragraph(
        resumen['titulo'] if hoja_aparte and resumen.get('titulo') else reporte['titulo'], st_titulo))
    elementos.append(Paragraph(f'{escape(sub)}  ·  Generado: {generado}', st_sub))

    # ── Detalle ──────────────────────────────────────────────
    columnas = [reporte['columnas'][i] for i in visibles]
    filas = [[f[i] if i < len(f) else '' for i in visibles] for f in reporte['filas']]
    derecha = {n for n, i in enumerate(visibles) if i in cols_der}
    titulos = set(reporte.get('filas_titulo', []))
    tabla = (tabla_de(columnas, filas, derecha, ancho_total, titulos) if filas
             else Paragraph('No hay movimientos en este período.', st_nota))

    ancho_cuenta = min(ancho_total, 125 * mm)
    totales = reporte.get('totales') or {}

    if hoja_aparte:
        # Hoja 1: el resumen, que es lo que se mira; desde la hoja 2, el
        # detalle que lo respalda. Quien quiere saber cuánto ganó no tiene
        # que pasar cuatro hojas de renglones para llegar a los totales.
        ancho_c = ancho_total * 0.55
        cuerpo = Table([[cuenta(totales, ancho_c), notas]],
                       colWidths=[ancho_c, ancho_total - ancho_c])
        cuerpo.setStyle(TableStyle([
            ('VALIGN',       (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING',  (0,0), (0,0), 0),
            ('LEFTPADDING',  (1,0), (1,0), 18),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ]))
        elementos += [recuadros(resumen['destacados']), Spacer(1, 14), cuerpo, PageBreak()]
        elementos.append(Paragraph(reporte['titulo'], ParagraphStyle(
            'titulo2', parent=st_titulo, fontSize=14)))
        elementos.append(Paragraph(f'{escape(sub)}  ·  Los totales están en la página 1', st_sub))
        elementos.append(tabla)
    else:
        # Lo importante primero: las cifras del resumen y su desglose arriba
        # de la hoja 1, el detalle debajo y la cuenta completa al final.
        if resumen:
            if resumen.get('destacados'):
                elementos += [recuadros(resumen['destacados']), Spacer(1, 12)]
            desglose = resumen.get('desglose')
            if desglose and desglose.get('filas'):
                elementos.append(Paragraph(escape(desglose['titulo']), st_seccion))
                t = tabla_de(desglose['columnas'], desglose['filas'],
                             set(desglose.get('cols_derecha', [])),
                             min(ancho_total, 170 * mm))
                t.hAlign = 'LEFT'
                elementos += [t, Spacer(1, 12)]
            elementos.append(Paragraph(reporte.get('titulo_detalle', 'Detalle'), st_seccion))
        elementos.append(tabla)

        if totales and not reporte.get('totales_solo_excel'):
            t = cuenta(totales, ancho_cuenta)
            t.hAlign = 'RIGHT'
            elementos += [Spacer(1, 10), KeepTogether([t])]

        if reporte.get('notas'):
            # Juntas en la misma hoja: una nota suelta en otra página no se lee.
            elementos.append(Spacer(1, 12))
            elementos.append(KeepTogether(notas))

    titulo_pie = reporte['titulo']

    def _pie_pagina(canvas, doc_):
        """Pie con el nombre del reporte y la página: una hoja suelta se reconoce."""
        canvas.saveState()
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(TEXTSEC)
        ancho_pagina = doc_.pagesize[0]
        canvas.drawString(doc_.leftMargin, 10*mm,
                          f'Oga Porã — {titulo_pie} — {sub} — uso interno')
        canvas.drawRightString(ancho_pagina - doc_.rightMargin, 10*mm, f'Página {doc_.page}')
        canvas.restoreState()

    doc.build(elementos, onFirstPage=_pie_pagina, onLaterPages=_pie_pagina)
    return buffer.getvalue()


# ════════════════════════════════════════════════════════
# Render a Excel (openpyxl)
# ════════════════════════════════════════════════════════
FORMATO_GS = '"Gs." #,##0;[Red]-"Gs." #,##0'
RE_GS = re.compile(r'^(-\s?)?Gs\.\s?(\d{1,3}(?:\.\d{3})*|\d+)$')
# "12,60 m²", "0,735", "3 u.": solo con las unidades de UNIDAD_CORTA, para no
# confundir con un texto como "3 cobros".
RE_CANTIDAD = re.compile(
    r'^(-?\d{1,3}(?:\.\d{3})*|-?\d+)(?:,(\d+))?(?:\s(m²|u\.|jgo\.|cajas|ml))?$')
RE_PCT = re.compile(r'^(-?\d+),(\d) %$')


def _a_numero(valor):
    """
    (número, formato de Excel) si `valor` es un importe, una cantidad o un
    porcentaje escrito como lo imprime el reporte; None si es texto.

    Los reportes arman sus celdas ya formateadas ("Gs. 1.518.000", "12,60
    m²") porque así las lee el PDF. En el Excel eso quedaba como texto: no se
    podía sumar una columna ni ordenar por monto. Se convierte acá, con el
    mismo aspecto gracias al formato de número.
    """
    if not isinstance(valor, str):
        return None
    texto = valor.strip()
    m = RE_GS.match(texto)
    if m:
        n = int(m.group(2).replace('.', ''))
        return (-n if m.group(1) else n), FORMATO_GS
    m = RE_CANTIDAD.match(texto)
    if m:
        entero, decimales, unidad = m.group(1).replace('.', ''), m.group(2), m.group(3)
        if decimales is None and unidad is None:
            return None     # un número suelto ("2026") puede ser un código
        n = float(f'{entero}.{decimales or 0}')
        formato = ('#,##0.00##' if decimales else '#,##0') + (f' "{unidad}"' if unidad else '')
        return n, formato
    m = RE_PCT.match(texto)
    if m:
        return float(f'{m.group(1)}.{m.group(2)}') / 100, '0.0 %'
    return None


def render_xlsx(reporte: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = reporte.get('hoja', 'Reporte')[:31]

    HEAD_FILL = PatternFill('solid', fgColor='453941')
    HEAD_FONT = Font(color='B99C74', bold=True, size=11)
    TINTE     = PatternFill('solid', fgColor='F3EDE4')
    borde = Border(*[Side(style='thin', color='E8E4DF')]*4)
    cols_der = set(reporte.get('cols_derecha', []))

    def escribir(fila, col, valor, **estilo):
        convertido = _a_numero(valor)
        c = ws.cell(row=fila, column=col, value=convertido[0] if convertido else valor)
        if convertido:
            c.number_format = convertido[1]
            c.alignment = Alignment(horizontal='right')
        for k, v in estilo.items():
            setattr(c, k, v)
        return c

    def encabezado(fila, columnas, derecha=()):
        for col_idx, titulo in enumerate(columnas, 1):
            c = ws.cell(row=fila, column=col_idx, value=titulo)
            c.fill = HEAD_FILL; c.font = HEAD_FONT; c.border = borde
            c.alignment = Alignment(horizontal='right' if (col_idx - 1) in derecha else 'left',
                                    vertical='center', wrap_text=True)

    # Encabezado del documento
    ws['A1'] = 'ÓGA PORÃ — Acabados de Construcción'
    ws['A1'].font = Font(color='8a7355', bold=True, size=12)
    ws['A2'] = reporte['titulo']
    ws['A2'].font = Font(color='453941', bold=True, size=14)
    ws['A3'] = (f"{reporte.get('subtitulo','')}  ·  Generado: "
                f"{timezone.localtime().strftime('%d/%m/%Y %H:%M')}")
    ws['A3'].font = Font(color='6b6560', size=9)

    fila_header = 5
    encabezado(fila_header, reporte['columnas'], cols_der)
    titulos = set(reporte.get('filas_titulo', []))
    for r_idx, fila in enumerate(reporte['filas'], fila_header + 1):
        es_titulo = (r_idx - fila_header - 1) in titulos
        for c_idx, valor in enumerate(fila, 1):
            c = escribir(r_idx, c_idx, valor, border=borde,
                         font=Font(size=10, bold=es_titulo))
            if es_titulo:
                c.fill = TINTE
            if (c_idx - 1) in cols_der:
                c.alignment = Alignment(horizontal='right')

    # El encabezado queda fijo al bajar, y cada columna se puede filtrar.
    ultima_fila = fila_header + len(reporte['filas'])
    ultima_col = get_column_letter(max(len(reporte['columnas']), 1))
    ws.freeze_panes = ws.cell(row=fila_header + 1, column=1)
    if reporte['filas'] and not titulos:
        ws.auto_filter.ref = f'A{fila_header}:{ultima_col}{ultima_fila}'

    # Anchos de columna automáticos
    for col_idx, titulo in enumerate(reporte['columnas'], 1):
        max_len = len(str(titulo))
        for fila in reporte['filas']:
            if col_idx - 1 < len(fila):
                max_len = max(max_len, len(str(fila[col_idx - 1])))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 3, 45)

    # Totales: etiqueta y valor, el valor como número.
    fila_tot = ultima_fila + 2
    if reporte.get('totales'):
        for k, v in reporte['totales'].items():
            sub = str(k).startswith('  ·')
            ws.cell(row=fila_tot, column=1, value=str(k).strip()).font = \
                Font(bold=not sub, color='6b6560' if sub else '453941')
            escribir(fila_tot, 2, v, font=Font(bold=not sub))
            fila_tot += 1
        # La etiqueta tiene que leerse entera: el valor está en la columna
        # de al lado y corta lo que desborde.
        largo = max(len(str(k)) for k in reporte['totales']) + 2
        if (ws.column_dimensions['A'].width or 0) < largo:
            ws.column_dimensions['A'].width = min(largo, 60)
        if (ws.column_dimensions['B'].width or 0) < 16:
            ws.column_dimensions['B'].width = 16

    # El desglose del resumen (por medio de pago, por ejemplo), como tabla aparte.
    desglose = (reporte.get('resumen') or {}).get('desglose')
    if desglose and desglose.get('filas'):
        fila_tot += 1
        ws.cell(row=fila_tot, column=1, value=desglose['titulo']).font = \
            Font(bold=True, color='453941', size=11)
        fila_tot += 1
        der = set(desglose.get('cols_derecha', []))
        encabezado(fila_tot, desglose['columnas'], der)
        for fila in desglose['filas']:
            fila_tot += 1
            for c_idx, valor in enumerate(fila, 1):
                escribir(fila_tot, c_idx, valor, border=borde, font=Font(size=10))
        fila_tot += 1

    # Notas: una por renglón, combinada a lo ancho de la tabla y con ajuste
    # de texto. Excel no agranda solo una celda combinada, así que el alto
    # se estima por el largo del texto.
    if reporte.get('notas'):
        n_cols = max(len(reporte['columnas']), 2)
        ancho = sum((ws.column_dimensions[get_column_letter(i)].width or 10)
                    for i in range(1, n_cols + 1))
        fila_tot += 1
        ws.cell(row=fila_tot, column=1, value='Cómo leer este reporte').font = \
            Font(bold=True, color='453941')
        for nota in reporte['notas']:
            fila_tot += 1
            ws.merge_cells(start_row=fila_tot, start_column=1, end_row=fila_tot, end_column=n_cols)
            c = ws.cell(row=fila_tot, column=1, value=nota)
            c.font = Font(size=10, color='6b6560')
            c.alignment = Alignment(wrap_text=True, vertical='top')
            ws.row_dimensions[fila_tot].height = 15 * (len(nota) // max(int(ancho * 0.9), 1) + 1)

    # Al imprimir desde Excel: apaisada si es ancha, y a lo ancho de la hoja.
    ws.page_setup.orientation = 'landscape' if len(reporte['columnas']) > 5 else 'portrait'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f'{fila_header}:{fila_header}'

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ════════════════════════════════════════════════════════
# Construcción de cada reporte
# ════════════════════════════════════════════════════════
def reporte_stock():
    from apps.inventario.models import Stock
    # Las mismas variantes y los mismos estados que la pantalla de
    # Inventario: el reporte es la versión impresa de esa pantalla.
    qs = Stock.objects.select_related(
        'variante__producto__categoria', 'variante__acabado',
    ).filter(variante__activa=True, variante__producto__activo=True)
    etiquetas = {'disponible': 'Disponible', 'bajo': 'Stock bajo',
                 'critico': 'Stock crítico', 'sin_stock': 'Sin stock'}
    # Lo que hay que reponer va arriba: quien imprime el stock lo hace para
    # saber qué falta, no para leer 130 renglones en orden alfabético.
    urgencia = {'sin_stock': 0, 'critico': 1, 'bajo': 2, 'disponible': 3}

    registros = []
    conteo = {k: 0 for k in etiquetas}
    for s in qs:
        v, p = s.variante, s.variante.producto
        unidad = UNIDAD_CORTA.get(p.unidad_venta, p.unidad_venta)
        conteo[s.estado] += 1
        registros.append(((urgencia[s.estado], p.nombre.lower(), _variante_txt(v)), [
            p.nombre,
            _variante_txt(v),
            p.categoria.nombre,
            _cantidad(s.cantidad, unidad),
            _cantidad(s.cantidad_reservada, unidad),
            _cantidad(s.cantidad_disponible, unidad),
            etiquetas[s.estado],
            v.sku,
            _cantidad(s.stock_minimo, unidad),
        ]))
    registros.sort(key=lambda r: r[0])
    filas = [f for _, f in registros]
    a_reponer = conteo['sin_stock'] + conteo['critico'] + conteo['bajo']

    return {
        'titulo':    'Reporte de Stock',
        'subtitulo': f'{len(filas)} productos y variantes · al {timezone.localdate():%d/%m/%Y}',
        'hoja':      'Stock',
        'columnas':  ['Producto', 'Variante', 'Categoría', 'En depósito', 'Reservado',
                      'Disponible', 'Estado', 'SKU', 'Mínimo'],
        'cols_derecha': [3, 4, 5, 8],
        'solo_excel': [7, 8],
        'filas':     filas,
        'resumen': {'destacados': [
            ('Con stock', conteo['disponible'], 'sin problemas'),
            ('Stock bajo', conteo['bajo'], 'queda 25 % o menos'),
            ('Stock crítico', conteo['critico'], 'queda 15 % o menos'),
            ('Sin stock', conteo['sin_stock'], 'no se puede vender'),
        ]},
        'titulo_detalle': ('Detalle — primero lo que hay que reponer' if a_reponer
                           else 'Detalle'),
        'totales': {
            'Variantes con stock':      conteo['disponible'],
            'Variantes con stock bajo': conteo['bajo'],
            'Variantes en crítico':     conteo['critico'],
            'Variantes sin stock':      conteo['sin_stock'],
            '(=) Para reponer':         a_reponer,
        },
        'notas': [
            '"En depósito" es lo que hay físicamente; "Reservado" está apartado para '
            'pedidos que todavía no se cobraron; "Disponible" es lo que se puede vender hoy.',
            'Cada producto se cuenta en su unidad: m² para pisos y revestimientos, '
            'u. (unidades) para grifería, sanitarios y accesorios, jgo. para juegos.',
        ],
    }


def _reintegros(desde: date, hasta: date):
    """Devoluciones del período que sacaron plata de la caja."""
    from apps.caja.models import Devolucion
    return Devolucion.objects.filter(
        monto_reintegro__gt=0,
        fecha__date__gte=desde,
        fecha__date__lte=hasta,
    ).select_related('pago_original__pedido', 'usuario').order_by('fecha')


def reporte_ventas(desde: date, hasta: date):
    """
    Una línea por cobro, y una en negativo por cada reintegro de devolución.

    El cobro de un cambio ya viene neto del crédito, así que con restar los
    reintegros el total es lo que efectivamente entró — sin necesidad de
    listar aparte los créditos que se usaron para pagar otro pedido. Lo que
    sí se hace es nombrarlo: el renglón dice "Cambio" con la venta original,
    y un cambio sin diferencia no se cuenta como cobro ni como medio de pago.

    El resumen "por medio de pago" suma las líneas de cada cobro, no
    `Pago.medio_pago`: un pago mixto de efectivo + cheque se reparte entre
    los dos, en vez de aparecer como un medio más llamado "Pago mixto".
    """
    from apps.caja.models import Devolucion, Pago
    from apps.caja.devoluciones import resumen_cambios

    etiquetas = dict(Pago.MEDIOS)
    pagos = Pago.objects.filter(
        estado=Pago.ESTADO_CONFIRMADO,
        fecha__date__gte=desde,
        fecha__date__lte=hasta,
    ).select_related('pedido', 'cajero',
                     'devolucion_aplicada__pago_original__pedido'
                     ).prefetch_related('medios').order_by('fecha')

    movimientos = []
    por_medio = {}          # medio → [cobros, monto]
    for p in pagos:
        cambio = getattr(p, 'devolucion_aplicada', None)
        pedido_txt = p.pedido.numero if p.pedido else '—'
        lineas = [l for l in p.medios.all() if l.monto]
        # "Cheque + Efectivo", sin repetir el medio si hubo dos cheques.
        medio_txt = (' + '.join(dict.fromkeys(etiquetas.get(l.medio, l.medio) for l in lineas))
                     or p.get_medio_pago_display())
        if cambio is not None:
            pedido_txt = (f'Cambio {pedido_txt} '
                          f'(venta {cambio.pago_original.pedido.numero})')
            if not p.monto:
                medio_txt = 'Sin diferencia'
        for l in lineas:
            r = por_medio.setdefault(l.medio, [0, 0.0])
            r[0] += 1
            r[1] += float(l.monto)
        movimientos.append((p.fecha, [
            _fecha(p.fecha),
            p.pedido.cliente_nombre if p.pedido and p.pedido.cliente_nombre else 'Consumidor Final',
            pedido_txt,
            medio_txt,
            p.numero_ticket or '—',
            p.cajero.nombre_completo,
        ], float(p.monto), cambio is not None))
    for d in _reintegros(desde, hasta):
        pedido = d.pago_original.pedido
        r = por_medio.setdefault(d.medio_reintegro, [0, 0.0])
        r[1] -= float(d.monto_reintegro)
        movimientos.append((d.fecha, [
            _fecha(d.fecha),
            pedido.cliente_nombre or 'Consumidor Final',
            (f'Cambio {pedido.numero}: reintegro' if d.pedido_cambio_id
             else f'Devolución {pedido.numero}'),
            f'Reintegro en {d.get_medio_reintegro_display().lower()}',
            d.numero,
            d.usuario.nombre_completo,
        ], -float(d.monto_reintegro), bool(d.pedido_cambio_id)))
    movimientos.sort(key=lambda m: m[0])

    filas = []
    total_general = 0
    total_cobrado = 0
    total_reintegros = 0
    cobros = 0
    cobrado_ventas = 0      # sin la diferencia de los cambios: para el promedio
    for _, fila, monto, es_cambio in movimientos:
        total_general += monto
        if monto < 0:
            total_reintegros += -monto
        else:
            total_cobrado += monto
            if not es_cambio:
                cobros += 1
                cobrado_ventas += monto
        filas.append(fila[:4] + [_gs_signo(monto)] + fila[4:])

    cambios = resumen_cambios(Devolucion.objects.filter(
        fecha__date__gte=desde, fecha__date__lte=hasta))

    totales = {'Cobrado en el período': _gs(total_cobrado)}
    if total_reintegros:
        totales['(-) Reintegros por devolución'] = f'- {_gs(total_reintegros)}'
    totales['(=) Total de ventas'] = _gs_signo(total_general)
    totales['Cantidad de cobros'] = cobros
    if cambios['cantidad']:
        totales['Cambios de producto'] = cambios['cantidad']
        totales['  · Crédito tomado de lo devuelto'] = _gs(cambios['credito'])
        totales['  · Diferencia cobrada en cambios'] = _gs(cambios['diferencia_cobrada'])
        if cambios['reintegrado']:
            totales['  · Reintegrado en cambios'] = f'- {_gs(cambios["reintegrado"])}'

    orden = [m for m, _ in Pago.MEDIOS]
    desglose = [[etiquetas.get(m, m), c or '—', _gs_signo(v)]
                for m, (c, v) in sorted(por_medio.items(),
                                        key=lambda kv: orden.index(kv[0]) if kv[0] in orden else 99)]

    destacados = [
        ('Total de ventas', _gs_signo(total_general),
         'cobrado menos reintegros' if total_reintegros else 'lo cobrado en el período'),
        ('Cobros', cobros, 'ventas cobradas'),
        ('Ticket promedio', _gs(cobrado_ventas / cobros) if cobros else '—', 'por venta'),
    ]
    if total_reintegros or cambios['cantidad']:
        destacados.append(('Devoluciones y cambios', f'- {_gs(total_reintegros)}',
                           f'{cambios["cantidad"]} cambio(s) de producto'))

    return {
        'titulo':    'Balance de Ventas',
        'subtitulo': _rango(desde, hasta),
        'hoja':      'Ventas',
        'columnas':  ['Fecha', 'Cliente', 'Pedido', 'Medio', 'Monto', 'Ticket', 'Cajero'],
        'cols_derecha': [4],
        'solo_excel': [5, 6],
        'filas':     filas,
        'totales':   totales,
        'resumen': {
            'destacados': destacados,
            'desglose': {
                'titulo': 'Por medio de pago',
                'columnas': ['Medio', 'Cobros', 'Monto'],
                'cols_derecha': [1, 2],
                'filas': desglose,
            },
        },
        'titulo_detalle': 'Detalle — un renglón por cobro',
        'notas': ([
            'Un pago mixto (por ejemplo efectivo + cheque) es un solo cobro en el detalle, '
            'pero en "Por medio de pago" cada parte suma en su medio.'
        ] + ([
            'Una devolución resta lo reintegrado al cliente. En un cambio de producto solo '
            'se cobra (o se reintegra) la diferencia, y no cuenta como una venta nueva.'
        ] if total_reintegros or cambios['cantidad'] else [])),
    }


def reporte_caja(desde: date, hasta: date):
    """Una fila por turno de caja: con cuánto abrió, qué cobró y con cuánto cerró."""
    from apps.caja.models import SesionCaja, Pago

    sesiones = SesionCaja.objects.filter(
        fecha_apertura__date__gte=desde,
        fecha_apertura__date__lte=hasta,
    ).select_related('cajero').order_by('fecha_apertura')

    filas = []
    total_ventas = 0
    total_reintegros = 0
    abiertas = 0
    for s in sesiones:
        ventas = Pago.objects.filter(
            sesion_caja=s, estado=Pago.ESTADO_CONFIRMADO
        ).aggregate(t=Sum('monto'))['t'] or 0
        reintegros = float(s.total_reintegros())
        total_ventas += float(ventas)
        total_reintegros += reintegros
        abierta = s.estado != 'cerrada'
        abiertas += abierta
        filas.append([
            s.cajero.nombre_completo,
            _fecha(s.fecha_apertura),
            _fecha(s.fecha_cierre) if s.fecha_cierre else ('Sigue abierta' if abierta else '—'),
            _gs(s.monto_apertura),
            _gs(ventas),
            f'- {_gs(reintegros)}' if reintegros else '—',
            _gs(float(ventas) - reintegros),
            _gs(s.monto_cierre) if s.monto_cierre is not None else '—',
        ])

    neto = total_ventas - total_reintegros
    return {
        'titulo':    'Extracto de Caja',
        'subtitulo': _rango(desde, hasta),
        'hoja':      'Caja',
        'columnas':  ['Cajero', 'Abrió', 'Cerró', 'Monto inicial', 'Cobrado',
                      'Reintegros', 'Neto del turno', 'Declarado al cerrar'],
        'cols_derecha': [3, 4, 5, 6, 7],
        'filas':     filas,
        'resumen': {'destacados': [
            ('Turnos de caja', len(filas),
             f'{abiertas} sigue(n) abierta(s)' if abiertas else 'todos cerrados'),
            ('Cobrado', _gs(total_ventas), 'todos los medios de pago'),
            ('Reintegros', f'- {_gs(total_reintegros)}' if total_reintegros else _gs(0),
             'por devoluciones'),
            ('Neto del período', _gs(neto), None),
        ]},
        'titulo_detalle': 'Detalle — un renglón por turno',
        'totales': {
            'Turnos de caja': len(filas),
            'Cobrado en el período': _gs(total_ventas),
            '(-) Reintegros por devolución': f'- {_gs(total_reintegros)}' if total_reintegros else _gs(0),
            '(=) Neto del período': _gs(neto),
        },
        'notas': [
            '"Declarado al cerrar" es el efectivo que contó la cajera al cerrar el turno. '
            'Para comparar contra lo que tenía que haber en el cajón, usá el Arqueo de Caja del día.',
        ],
    }


def _cantidad(valor, unidad=''):
    """
    Cantidad exacta y su unidad: "12,60 m²", "0,735 m²", "3 u.".

    Los productos que se venden por m² se piden en fracciones (media caja,
    3,15 m²), así que redondear a entero cambia el número que la propietaria
    usa para reponer. Se muestran los decimales que guarda el sistema (hasta
    cuatro, como la pantalla: tres piezas de 0,245 m² son 0,735 y no 0,74),
    con la unidad al lado para que se lea qué se está contando. Lo que se
    cuenta de a uno (grifos, juegos) sale entero cuando lo es: "3 u." y no
    "3,00 u.".
    """
    try:
        numero = Decimal(str(valor)).quantize(Decimal('0.0001'))
    except Exception:
        numero = Decimal('0')
    if unidad != 'm²' and numero == numero.to_integral_value():
        texto = f'{int(numero):,}'
    else:
        texto = f'{numero:,.4f}'.rstrip('0')
        entero, _, dec = texto.partition('.')
        texto = f'{entero}.{dec.ljust(2, "0")}'
    texto = texto.replace(',', 'X').replace('.', ',').replace('X', '.')
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


def _items_devueltos(desde: date, hasta: date):
    """
    Lo que volvió en el período, por la fecha de la devolución.

    Resta en el reporte aunque la venta sea de otro período: el reporte dice
    cuánto salió del local entre esas fechas, y lo que volvió en ellas ya no
    salió.
    """
    from apps.caja.models import ItemDevolucion
    return ItemDevolucion.objects.filter(
        devolucion__fecha__date__gte=desde,
        devolucion__fecha__date__lte=hasta,
    ).select_related(
        'devolucion__pago_original__pedido',
        'variante__producto', 'variante__acabado',
        'item_pedido',
    ).order_by('devolucion__fecha')


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
    subtitulo_rango = _rango(desde, hasta)

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
                _variante_txt(variante),
                variante.sku,
                _cantidad(item.cantidad, unidad),
                _gs(item.precio_unitario),
                _gs(subtotal),
                pago.pedido.cliente_nombre or 'Consumidor Final',
                pago.pedido.numero,
            ])

        for dev_item in _items_devueltos(desde, hasta):
            variante = dev_item.variante
            devolucion = dev_item.devolucion
            unidad = UNIDAD_CORTA.get(variante.producto.unidad_venta,
                                      variante.producto.unidad_venta)
            monto = float(dev_item.monto)
            total_ingresos -= monto
            filas.append([
                _fecha(devolucion.fecha),
                variante.producto.nombre,
                _variante_txt(variante),
                variante.sku,
                _cantidad(-dev_item.cantidad, unidad),
                _gs(dev_item.item_pedido.precio_unitario),
                f'- {_gs(monto)}',
                devolucion.pago_original.pedido.cliente_nombre or 'Consumidor Final',
                devolucion.numero,
            ])

        return {
            'titulo':    'Productos comercializados — detalle por fecha',
            'subtitulo': subtitulo_rango,
            'hoja':      'Productos por fecha',
            'columnas':  ['Fecha', 'Producto', 'Variante', 'SKU', 'Cantidad',
                          'Precio unit.', 'Total', 'Cliente', 'Pedido'],
            'cols_derecha': [4, 5, 6],
            'solo_excel': [3],
            'filas':     filas,
            'resumen': {'destacados': [
                ('Total vendido', _gs_signo(total_ingresos), 'menos lo devuelto'),
                ('Renglones de venta', len(filas), None),
            ]},
            'titulo_detalle': 'Detalle — un renglón por producto vendido',
            'totales': {
                'Líneas de venta': len(filas),
                '(=) Total vendido': _gs_signo(total_ingresos),
            },
        }

    # ── Agregado por variante ────────────────────────────────
    acumulado = {}
    for pago, item in _items_vendidos(desde, hasta):
        variante = item.variante
        registro = acumulado.setdefault(variante.id, {
            'producto': variante.producto.nombre,
            'variante': _variante_txt(variante),
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

    for dev_item in _items_devueltos(desde, hasta):
        variante = dev_item.variante
        fecha = dev_item.devolucion.fecha
        registro = acumulado.setdefault(variante.id, {
            'producto': variante.producto.nombre,
            'variante': _variante_txt(variante),
            'sku':      variante.sku,
            'unidad':   UNIDAD_CORTA.get(variante.producto.unidad_venta,
                                         variante.producto.unidad_venta),
            'cantidad': 0.0,
            'ingresos': 0.0,
            'ventas':   0,
            'primera':  fecha,
            'ultima':   fecha,
        })
        registro['cantidad'] -= float(dev_item.cantidad)
        registro['ingresos'] -= float(dev_item.monto)

    ordenados = sorted(acumulado.values(), key=lambda r: -r['ingresos'])
    for r in ordenados:
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
        'solo_excel': [2],
        'filas':     filas,
        'resumen': {'destacados': [
            ('Total vendido', _gs_signo(total_ingresos), 'menos lo devuelto'),
            ('Productos distintos', len(filas), 'variantes que se vendieron'),
            ('El que más vendió', ordenados[0]['producto'] if ordenados else '—',
             _gs(ordenados[0]['ingresos']) if ordenados else None),
        ]},
        'titulo_detalle': 'Detalle — de lo que más ingresó a lo que menos',
        'totales': {
            'Variantes distintas vendidas': len(filas),
            '(=) Total vendido': _gs_signo(total_ingresos),
        },
        'notas': [
            '"Cantidad vendida" ya descuenta lo que se devolvió en el período. '
            '"Ventas" es en cuántos cobros distintos salió el producto.',
        ],
    }


def _pct(valor):
    return '—' if valor is None else f'{float(valor):.1f} %'.replace('.', ',')


def _gs_signo(valor):
    """Gs. con signo menos adelante: una pérdida tiene que verse a simple vista."""
    if valor is None:
        return '—'
    return f'- {_gs(-valor)}' if valor < 0 else _gs(valor)


def reporte_ganancias(desde: date, hasta: date, detalle: bool = False):
    """
    Cuánto se gana con lo que se vende: precio cobrado contra costo de
    adquisición, producto por producto. La cuenta y sus decisiones están en
    apps/caja/ganancias.py.

    Igual que Productos comercializados, dos vistas: el acumulado por
    variante (qué deja más y qué deja menos) y el detalle venta por venta.
    """
    from . import ganancias

    datos = ganancias.resumen(desde, hasta, con_lineas=True)
    subtitulo = _rango(desde, hasta)
    filas = []

    def unidad(variante):
        return UNIDAD_CORTA.get(variante.producto.unidad_venta, variante.producto.unidad_venta)

    if detalle:
        for l in datos['lineas']:
            v = l.variante
            costo_u = (l.costo / l.cantidad) if (l.costo is not None and l.cantidad) else None
            filas.append([
                _fecha(l.fecha),
                v.producto.nombre + (' (devolución' + (', dañada' if l.danada else '') + ')'
                                     if l.devolucion else ''),
                _variante_txt(v),
                _cantidad(l.cantidad, unidad(v)),
                _gs(costo_u) if costo_u is not None else 'sin costo',
                _gs(l.ingreso / l.cantidad) if l.cantidad else '—',
                _gs_signo(l.ingreso),
                _gs_signo(l.costo),
                _gs_signo(l.ganancia),
                _pct(l.ganancia / l.ingreso * 100 if l.ganancia is not None and l.ingreso else None),
                l.referencia,
            ])
        columnas = ['Fecha', 'Producto', 'Variante', 'Cantidad', 'Costo unit.',
                    'Cobrado unit.', 'Cobrado', 'Costo', 'Ganancia', 'Margen', 'Pedido']
        cols_derecha = [3, 4, 5, 6, 7, 8, 9]
        titulo = 'Ganancias — detalle por venta'
    else:
        acumulado = {}
        for l in datos['lineas']:
            r = acumulado.setdefault(l.variante.id, {
                'v': l.variante, 'cantidad': Decimal('0'), 'ingreso': Decimal('0'),
                'costo': Decimal('0'), 'sin_costo': False})
            r['cantidad'] += l.cantidad
            r['ingreso'] += l.ingreso
            if l.costo is None:
                r['sin_costo'] = True
            else:
                r['costo'] += l.costo
        for r in acumulado.values():
            r['ganancia'] = None if r['sin_costo'] else r['ingreso'] - r['costo']
        orden = sorted(acumulado.values(),
                       key=lambda r: (r['ganancia'] is None, -(r['ganancia'] or 0)))
        for r in orden:
            v, cant = r['v'], r['cantidad']
            filas.append([
                v.producto.nombre,
                _variante_txt(v),
                _cantidad(cant, unidad(v)),
                'sin costo' if r['sin_costo'] else (_gs(r['costo'] / cant) if cant else '—'),
                _gs(r['ingreso'] / cant) if cant else '—',
                _gs_signo(r['ingreso']),
                '—' if r['sin_costo'] else _gs_signo(r['costo']),
                _gs_signo(r['ganancia']),
                _pct(r['ganancia'] / r['ingreso'] * 100
                     if r['ganancia'] is not None and r['ingreso'] else None),
            ])
        columnas = ['Producto', 'Variante', 'Cantidad', 'Costo unit.', 'Cobrado unit. (prom.)',
                    'Cobrado', 'Costo', 'Ganancia', 'Margen']
        cols_derecha = [2, 3, 4, 5, 6, 7, 8]
        titulo = 'Ganancias por producto'

    # Los totales se leen de arriba abajo como una cuenta: cada (-) resta del
    # renglón anterior y cada (=) es el resultado. Antes el cobrado sin costo
    # se descontaba sin mostrarse y la resta no daba a quien la hacía a mano.
    sin_costo = datos['ingresos_sin_costo']
    totales = {'Cobrado por mercadería': _gs(datos['ingresos'])}
    if sin_costo:
        totales['(-) Cobrado de productos sin costo cargado (nota 1)'] = _gs_signo(sin_costo)
        totales['(=) Cobrado de productos con costo cargado'] = _gs_signo(datos['ingresos_con_costo'])
    totales.update({
        '(-) Costo de esa mercadería': _gs(datos['costo']),
        '(=) Ganancia bruta': _gs_signo(datos['ganancia_bruta']),
        'Recargo sobre el costo (nota 2)': _pct(datos['recargo']),
        'Margen sobre lo cobrado (nota 2)': _pct(datos['margen']),
        '(-) Gastos operativos, sin pagos a proveedor (nota 3)': _gs(datos['gastos']),
        '(-) Comisiones bancarias (comisión + IVA)': _gs(datos['comisiones_bancarias']),
        '(=) Ganancia neta': _gs_signo(datos['ganancia_neta']),
    })
    if datos['pagos_proveedor']:
        totales['Pagos a proveedores del período (no restan, nota 3)'] = _gs(datos['pagos_proveedor'])
    if datos['retenciones_bancarias']:
        totales['Retenciones del banco (a cuenta de impuestos, no restan)'] = \
            _gs(datos['retenciones_bancarias'])

    notas = []
    if sin_costo:
        notas.append(
            '1. Productos sin costo cargado: se vendieron, pero en Productos no tienen '
            'precio de costo. Sin saber cuánto costaron no se puede saber cuánto dejaron, '
            'así que quedan fuera de la ganancia para no inflarla. En la tabla dicen '
            '"sin costo"; cargando su costo en Productos, las ventas siguientes ya entran.')
    notas.append(
        '2. Recargo y margen son la misma ganancia medida de dos formas. El recargo es '
        'sobre el costo: lo que se le suma al costo para poner el precio (costó 100, se '
        'vende a 132: 32 % de recargo). El margen es sobre lo cobrado: de esos 132 quedan '
        '32, o sea el 24 %. Por eso un recargo de 30 a 32 % da un margen de 23 a 24 %.')
    notas.append(
        '3. Los pagos a proveedores no restan acá porque esa plata compró mercadería: '
        'cuando la mercadería se vende, lo que costó ya está restado en "Costo de esa '
        'mercadería". Restar también el pago la contaría dos veces. Y lo que se compró '
        'pero todavía no se vendió no es pérdida: sigue en el depósito como stock.')

    return {
        'titulo':    titulo,
        'subtitulo': subtitulo + ' · precios y costos con IVA incluido',
        'hoja':      'Ganancias',
        'columnas':  columnas,
        'cols_derecha': cols_derecha,
        'filas':     filas,
        'totales':   totales,
        'notas':     notas,
        # Solo el PDF: hoja 1 con esto y los totales, el detalle desde la hoja 2.
        'resumen': {
            'hoja_aparte': True,
            'titulo': 'Resumen de ganancias',
            'destacados': [
                ('Cobrado por mercadería', _gs(datos['ingresos']), None),
                ('Costo de lo vendido', _gs(datos['costo']), None),
                ('Ganancia bruta', _gs_signo(datos['ganancia_bruta']),
                 f'{_pct(datos["recargo"])} sobre el costo · {_pct(datos["margen"])} de lo cobrado'),
                ('Ganancia neta', _gs_signo(datos['ganancia_neta']),
                 'después de gastos y comisiones bancarias'),
            ],
        },
    }


def reporte_comisiones(desde: date, hasta: date):
    """
    Lo que el banco descuenta de cada cobro con tarjeta, QR o PIX. La cuenta
    está en apps/caja/comisiones.py.

    En papel van las cuatro cifras que importan, igual que la solapa de
    Costos: cobrado, comisión + IVA, retenciones y lo que acredita el banco.
    El Excel trae además cada componente por separado (comisión, su IVA, las
    dos retenciones), que es como viene la liquidación del banco, para
    conciliarla renglón por renglón.
    """
    from . import comisiones
    from apps.caja.models import Pago

    etiquetas = dict(Pago.MEDIOS)
    filas = []
    total = comisiones.Desglose(cobrado=Decimal('0'))
    por_medio = {}
    cobros = {}
    for l in comisiones.lineas(desde, hasta):
        d, linea = l.desglose, l.linea
        total = total + d
        por_medio[linea.medio] = por_medio.get(
            linea.medio, comisiones.Desglose(cobrado=Decimal('0'))) + d
        cobros[linea.medio] = cobros.get(linea.medio, 0) + 1
        tasa = l.tasa
        filas.append([
            _fecha(l.fecha),
            linea.pago.pedido.cliente_nombre or 'Consumidor Final',
            linea.pago.numero_ticket,
            etiquetas.get(linea.medio, linea.medio),
            (f'{tasa.porcentaje.normalize()} %' + (' + IVA' if tasa.iva_aparte else ' IVA incl.'))
            if tasa else 'sin tasa',
            _gs(d.cobrado),
            f'- {_gs(d.costo)}',
            f'- {_gs(d.retenciones)}',
            _gs(d.neto),
            _gs(d.comision), _gs(d.iva_comision),
            _gs(d.retencion_renta), _gs(d.retencion_iva),
        ])

    desglose = [[etiquetas.get(m, m), cobros[m], _gs(d.cobrado), f'- {_gs(d.costo)}',
                 f'- {_gs(d.retenciones)}', _gs(d.neto)] for m, d in por_medio.items()]
    n_cobros = sum(cobros.values())
    return {
        'titulo':    'Comisiones bancarias',
        'subtitulo': _rango(desde, hasta) + ' · tarjetas, QR y PIX',
        'hoja':      'Comisiones',
        'columnas':  ['Fecha', 'Cliente', 'Ticket', 'Medio', 'Tasa', 'Cobrado',
                      'Comisión + IVA', 'Retenciones', 'Te acredita',
                      'Comisión', 'IVA s/comisión', 'Ret. renta', 'Ret. IVA'],
        'cols_derecha': [5, 6, 7, 8, 9, 10, 11, 12],
        'solo_excel': [2, 9, 10, 11, 12],
        'filas':     filas,
        'resumen': {
            'destacados': [
                ('Cobrado con tarjetas, QR y PIX', _gs(total.cobrado),
                 f'{n_cobros} cobro{"s" if n_cobros != 1 else ""}'),
                ('Comisiones + IVA', f'- {_gs(total.costo)}', 'lo que cobra el banco'),
                ('Retenciones', f'- {_gs(total.retenciones)}', 'a cuenta de impuestos'),
                ('Te acredita el banco', _gs(total.neto), None),
            ],
            'desglose': {
                'titulo': 'Por medio de pago',
                'columnas': ['Medio', 'Cobros', 'Cobrado', 'Comisión + IVA',
                             'Retenciones', 'Te acredita'],
                'cols_derecha': [1, 2, 3, 4, 5],
                'filas': desglose,
            },
        },
        'titulo_detalle': 'Detalle — un renglón por cobro',
        'totales': {
            'Cobrado con tarjetas, QR y PIX': _gs(total.cobrado),
            '(-) Comisiones + IVA (costo del local)': f'- {_gs(total.costo)}',
            '(-) Retenciones de renta e IVA': f'- {_gs(total.retenciones)}',
            '(=) Te acredita el banco': _gs(total.neto),
        },
        'notas': [
            'Esto se calcula solo con los cobros registrados en Caja: no hay que cargar nada aparte.',
            'La comisión y su IVA son el costo del local y se restan de la ganancia. Las '
            'retenciones no son una pérdida: el banco las paga a la DNIT a nombre del local '
            'y se descuentan en la liquidación de impuestos.',
        ],
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
    from apps.caja.models import SesionCaja, Pago, PagoMedio
    from apps.caja.devoluciones import resumen_cambios
    from apps.caja import comisiones

    sesiones = SesionCaja.objects.filter(
        fecha_apertura__date=dia,
    ).select_related('cajero').order_by('fecha_apertura')

    filas = []
    total_banco_dia = comisiones.Desglose(cobrado=Decimal('0'))
    total_cobrado_dia = 0.0
    total_efectivo_dia = 0.0
    diferencia_dia = 0.0
    esperado_dia = 0.0
    sin_cerrar = 0
    cambios_dia = 0

    for sesion in sesiones:
        pagos = Pago.objects.filter(sesion_caja=sesion, estado=Pago.ESTADO_CONFIRMADO)

        # Por línea del cobro: del pago mixto, solo su parte en efectivo
        # está en el cajón. `cantidad` cuenta cobros, no líneas, y no cuenta
        # las líneas en 0 — un cambio sin diferencia no es un cobro.
        lineas = PagoMedio.objects.filter(pago__in=pagos)
        por_medio = {}
        for medio, etiqueta in Pago.MEDIOS:
            agg = lineas.filter(medio=medio).aggregate(
                total=Sum('monto'),
                cantidad=Count('pago', distinct=True, filter=Q(monto__gt=0)))
            monto = float(agg['total'] or 0)
            if monto or agg['cantidad']:
                por_medio[medio] = (etiqueta, monto, int(agg['cantidad'] or 0))

        cobrado = sum(m for _, m, _ in por_medio.values())
        efectivo = por_medio.get(Pago.MEDIO_EFECTIVO, ('', 0.0, 0))[1]
        # Solo el reintegro en efectivo salió del cajón.
        reintegro_efectivo = float(sesion.total_reintegros(Pago.MEDIO_EFECTIVO))
        apertura = float(sesion.monto_apertura or 0)
        esperado = apertura + efectivo - reintegro_efectivo
        esperado_dia += esperado

        total_cobrado_dia  += cobrado
        total_efectivo_dia += efectivo - reintegro_efectivo

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

        # Lo cobrado con tarjeta, QR o PIX no llega entero: el banco descuenta
        # comisión, su IVA y retenciones (ver comisiones.py).
        banco = comisiones.resumen(dia, dia, pagos=pagos)['total']
        if banco.cobrado:
            total_banco_dia = total_banco_dia + banco
            filas.append(['   Descuento del banco (tarjetas, QR, PIX)',
                          f'comisión + IVA {_gs(banco.costo)} · retenciones {_gs(banco.retenciones)}',
                          f'- {_gs(banco.descuento)}'])
            filas.append(['   Neto que acreditan los bancos', f'de {_gs(banco.cobrado)} cobrados',
                          _gs(banco.neto)])

        # Los cambios, a la vista: si no, una diferencia cobrada se confunde
        # con una venta y un cambio sin diferencia no aparece en ningún lado.
        cambios = resumen_cambios(sesion.devoluciones.all())
        if cambios['cantidad']:
            cambios_dia += cambios['cantidad']
            plural = 's' if cambios['cantidad'] != 1 else ''
            filas.append([
                f'   Cambios de producto',
                f'{cambios["cantidad"]} cambio{plural} · crédito {_gs(cambios["credito"])}',
                '',
            ])
            filas.append(['      Diferencia cobrada (incluida arriba)', '',
                          _gs(cambios['diferencia_cobrada'])])
            if cambios['reintegrado']:
                filas.append(['      Reintegrado (incluido abajo)', '',
                              f'- {_gs(cambios["reintegrado"])}'])

        reintegros = (sesion.devoluciones.filter(monto_reintegro__gt=0)
                      .values('medio_reintegro')
                      .annotate(total=Sum('monto_reintegro'), cantidad=Count('id')))
        etiquetas = dict(Pago.MEDIOS)
        for r in reintegros:
            filas.append([
                f'   Reintegrado en {etiquetas.get(r["medio_reintegro"], r["medio_reintegro"]).lower()}',
                f'{r["cantidad"]} ' + ('devolución' if r['cantidad'] == 1 else 'devoluciones'),
                f'- {_gs(r["total"])}',
            ])

        filas.append(['   Efectivo que debe haber en el cajón',
                      ('apertura + cobros − reintegros en efectivo' if reintegro_efectivo
                       else 'apertura + cobros en efectivo'),
                      _gs(esperado)])

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
            sin_cerrar += 1
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

    if abs(diferencia_dia) < 0.005:
        leyenda_dia = 'cuadra'
    else:
        leyenda_dia = 'sobrante' if diferencia_dia > 0 else 'faltante'
    if sin_cerrar:
        nota_dif = f'{sin_cerrar} caja(s) sin cerrar todavía'
    elif not sesiones:
        nota_dif = 'no hubo cajas'
    else:
        nota_dif = 'lo contado contra lo esperado'
    titulos = [n for n, f in enumerate(filas)
               if f[0].startswith('CAJA DE ') or f[0] == 'CONTEO FÍSICO DEL EFECTIVO']

    return {
        'titulo':    'Arqueo de Caja',
        'subtitulo': f'Día {dia.strftime("%d/%m/%Y")} · {sesiones.count()} caja(s) abierta(s) ese día',
        'hoja':      'Arqueo',
        'columnas':  ['Concepto', 'Detalle', 'Monto'],
        'cols_derecha': [2],
        'filas':     filas,
        'filas_titulo': titulos,
        'resumen': {'destacados': [
            ('Cobrado en el día', _gs(total_cobrado_dia), 'todos los medios'),
            ('Efectivo esperado', _gs(esperado_dia), 'lo que tiene que haber en los cajones'),
            ('Diferencia', ('' if leyenda_dia == 'cuadra' else
                            ('- ' if leyenda_dia == 'faltante' else '+ ')) + _gs(abs(diferencia_dia)),
             f'{leyenda_dia} · {nota_dif}'),
            ('Acreditan los bancos', _gs(total_banco_dia.neto), 'tarjetas, QR y PIX, ya descontado'),
        ]},
        'titulo_detalle': 'Caja por caja',
        # En papel las cifras ya están arriba, y debajo de la planilla de
        # conteo y las firmas no se leerían.
        'totales_solo_excel': True,
        'totales': {
            'Total cobrado en el día':   _gs(total_cobrado_dia),
            'Efectivo neto (sin reintegros)': _gs(total_efectivo_dia),
            'Efectivo que debía haber en los cajones': _gs(esperado_dia),
            f'Diferencia del día ({leyenda_dia})': _gs(abs(diferencia_dia)),
            'Cambios de producto en el día': cambios_dia,
            'Descuento del banco en el día': f'- {_gs(total_banco_dia.descuento)}',
            'Neto que acreditan los bancos': _gs(total_banco_dia.neto),
        },
        'notas': [
            'Solo el efectivo se cuenta en el cajón: lo cobrado con tarjeta, QR, PIX, '
            'transferencia o cheque no está ahí, por eso no entra en la diferencia.',
            'Al final de la hoja está la planilla para contar los billetes a mano.',
        ],
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
