"""
KuDE: la representación gráfica del documento electrónico (Fase D).

Qué es y qué no. El KuDE **no es la factura**: la factura es el XML firmado
y aprobado por el SIFEN. El KuDE es el papel que se le entrega al cliente
para que pueda consultar ese documento —por el CDC escrito o leyendo el QR—
y para que le sirva de respaldo del crédito fiscal (Manual Técnico V150
§13.1). Por eso todo lo que se imprime acá sale del mismo lugar que el XML:
el manual prohíbe que el KuDE muestre información que no esté en el DE
firmado (§13.2), y la única forma seria de garantizarlo es no tener una
segunda fuente de datos. Los ítems se piden a `payload._items()`, que es
exactamente lo que viajó al SIFEN, descuentos prorrateados incluidos.

El ticket térmico de 80 mm que ya imprime la caja sigue existiendo y sirve
para el mostrador, pero no es un KuDE: le faltan el QR firmado, el timbrado
con sus vigencias y la liquidación del IVA. Son dos papeles distintos.

Del formato: la DNIT **no fija el tamaño** (§13.5 — "cualquier formato y
tamaño de papel estándar"); las gráficas 09 a 15 del manual son modelos
referenciales. Se eligió A4 vertical porque es lo que hay en la impresora de
la oficina, con la estructura de campos del §13.4, que sí es obligatoria:

  · encabezado (emisor, timbrado, datos generales, receptor);
  · ítems con precio, descuento y la afectación del IVA por columna;
  · subtotales, total de la operación y liquidación del IVA;
  · datos de consulta en el SIFEN: CDC en once grupos de cuatro;
  · QR, de 25 mm de ancho como mínimo (§13.8.1).

El QR **no se dibuja si el documento todavía no fue firmado**. El contenido
lo calcula el SIFEN a través de `qrgen` (lleva el hash de la firma y el CSC,
§13.8.2): inventar uno con la URL de consulta daría un código que escanea y
no resuelve nada, que es peor que no ponerlo. En ese caso el pie lo dice con
todas las letras.
"""
import io
import os
import re
from datetime import datetime

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

from . import cdc as cdc_mod
from . import codigos

# La marca sale de los mismos archivos que la nota de pedido: un solo logo
# para todo lo que el negocio imprime.
_ASSETS = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ventas', 'assets')
LOGO = os.path.join(_ASSETS, 'logo_oga_pora.png')

MARCA = '#B99C74'
SIDEBAR = '#453941'
BORDE = '#e8e4df'
TEXTO_SEC = '#6b6560'

# §13.8.1: 25 mm de ancho mínimo (22 de contenido + 3 de zona de silencio).
QR_LADO_MM = 30

# §13.3 — cada tipo de DE tiene su denominación, y es obligatoria.
DENOMINACION = {
    codigos.TIPO_DE_FACTURA:       'KuDE de Factura Electrónica',
    codigos.TIPO_DE_AUTOFACTURA:   'KuDE de Autofactura Electrónica',
    codigos.TIPO_DE_NOTA_CREDITO:  'KuDE de Nota de Crédito Electrónica',
    codigos.TIPO_DE_NOTA_DEBITO:   'KuDE de Nota de Débito Electrónica',
    codigos.TIPO_DE_NOTA_REMISION: 'KuDE de Nota de Remisión Electrónica',
}

# Cómo se llama el número en el encabezado, sin la palabra "KuDE".
NOMBRE_DOCUMENTO = {
    codigos.TIPO_DE_FACTURA:       'Factura Electrónica',
    codigos.TIPO_DE_AUTOFACTURA:   'Autofactura Electrónica',
    codigos.TIPO_DE_NOTA_CREDITO:  'Nota de Crédito Electrónica',
    codigos.TIPO_DE_NOTA_DEBITO:   'Nota de Débito Electrónica',
    codigos.TIPO_DE_NOTA_REMISION: 'Nota de Remisión Electrónica',
}

# El XML manda la unidad como código numérico del SIFEN (109 = m², 77 = UNI,
# 660 = ml). El KuDE lo lee una persona, así que se traduce — es el mismo
# dato del DE, escrito como se lee, que es lo que permite §13.4.2.
UNIDAD_LEGIBLE = {109: 'm²', 77: 'UNI', 660: 'ml'}


# ─── Extracción del QR del XML firmado ───────────────────────────────────────

_RE_CARQR = re.compile(r'<dCarQR>(.*?)</dCarQR>', re.DOTALL)


def enlace_qr_del_xml(xml: str) -> str:
    """
    Saca el contenido de `dCarQR` del XML que devolvió `qrgen`.

    Se lee con una expresión regular y no con un parser porque el XML llega
    firmado: parsearlo y volver a serializarlo puede cambiar espacios y
    romper la firma, y acá solo hace falta leer un campo. La entidad `&amp;`
    se desarma porque el valor real es una URL con parámetros.
    """
    if not xml:
        return ''
    coincidencia = _RE_CARQR.search(xml)
    if not coincidencia:
        return ''
    return (coincidencia.group(1).strip()
            .replace('&amp;', '&').replace('&quot;', '"'))


# ─── Formato ─────────────────────────────────────────────────────────────────

def _gs(valor) -> str:
    try:
        return f'{int(round(float(valor))):,}'.replace(',', '.')
    except (TypeError, ValueError):
        return '0'


def _num(valor, decimales=2) -> str:
    try:
        texto = f'{float(valor):,.{decimales}f}'
    except (TypeError, ValueError):
        return '0'
    return texto.replace(',', 'X').replace('.', ',').replace('X', '.')


def _fecha(momento, formato='%d/%m/%Y %H:%M') -> str:
    if momento is None:
        return ''
    if timezone.is_aware(momento):
        momento = timezone.localtime(momento)
    return momento.strftime(formato)


def _fecha_iso_a_legible(texto) -> str:
    """'2027-12-31' → '31/12/2027'. Si no tiene ese formato, lo deja igual."""
    try:
        return datetime.strptime(str(texto)[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        return str(texto or '')


# ─── Armado de los datos ─────────────────────────────────────────────────────

def construir_datos(documento) -> dict:
    """
    Todo lo que el PDF necesita, ya resuelto.

    Separado del dibujo por el mismo motivo que en `nota_pedido_doc`: se
    puede probar qué dice el documento sin tener que leer un PDF.
    """
    from . import payload as payload_mod

    fiscal = getattr(settings, 'DATOS_FISCALES', {}) or {}
    en_prueba = payload_mod.en_ambiente_de_pruebas()

    # En el ambiente de test la razón social del XML es la leyenda obligatoria
    # de la Guía de Pruebas §2. El KuDE muestra lo mismo que el XML: si acá
    # dijera el nombre real, el papel y el documento firmado no coincidirían.
    razon_social = (payload_mod.LEYENDA_AMBIENTE_PRUEBA if en_prueba
                    else documento.emisor_razon_social)

    items = []
    for item in payload_mod._items(documento):
        tasa = item['iva']
        bruto = ((float(item['precioUnitario']) - float(item['descuento']))
                 * float(item['cantidad']))
        items.append({
            'codigo': item['codigo'],
            'descripcion': item['descripcion'],
            'unidad': UNIDAD_LEGIBLE.get(item['unidadMedida'],
                                         str(item['unidadMedida'])),
            'cantidad': float(item['cantidad']),
            'precio_unitario': float(item['precioUnitario']),
            'descuento': float(item['descuento']) * float(item['cantidad']),
            # Una sola de las tres columnas lleva valor: es como el manual
            # arma la tabla (§13.4.2), una columna por afectación del IVA.
            'exentas': bruto if tasa == codigos.TASA_0 else 0,
            'iva5':    bruto if tasa == codigos.TASA_5 else 0,
            'iva10':   bruto if tasa == codigos.TASA_10 else 0,
        })

    condicion = ('Contado' if documento.condicion_venta == codigos.CONDICION_CONTADO
                 else 'Crédito')

    return {
        'denominacion': DENOMINACION.get(documento.tipo_documento, 'KuDE'),
        'nombre_documento': NOMBRE_DOCUMENTO.get(
            documento.tipo_documento, 'Documento Electrónico'),
        'en_prueba': en_prueba,

        'emisor': {
            'razon_social': razon_social,
            'ruc': documento.emisor_ruc,
            'direccion': documento.emisor_direccion,
            'telefono': documento.emisor_telefono,
            'actividad': fiscal.get('actividad_desc', ''),
            'ciudad': fiscal.get('ciudad_desc', ''),
            'timbrado': documento.emisor_timbrado,
            'timbrado_inicio': _fecha_iso_a_legible(fiscal.get('timbrado_inicio')),
            'timbrado_vto': _fecha_iso_a_legible(documento.emisor_timbrado_vto),
        },
        'numero': documento.numero_completo,
        'fecha_emision': _fecha(documento.fecha_emision, '%d/%m/%Y %H:%M:%S'),
        'condicion': condicion,
        'moneda': 'PYG — Guaraníes',

        'receptor': {
            'documento': documento.receptor_ruc or 'Sin identificar',
            'razon_social': documento.receptor_razon_social or 'Consumidor Final',
            'direccion': documento.receptor_direccion,
            'telefono': documento.receptor_telefono,
            'email': documento.receptor_email,
        },

        'items': items,
        'totales': {
            # Subtotales tal como los muestra el KuDE: lo que suma cada
            # columna de ítems, con el IVA adentro (F002/F004/F005).
            'subtotal_exentas': sum(i['exentas'] for i in items),
            'subtotal_5':  sum(i['iva5'] for i in items),
            'subtotal_10': sum(i['iva10'] for i in items),
            # Y el desglose neto que guarda el documento, para la liquidación.
            'exentas': float(documento.total_exento),
            'gravado5': float(documento.total_gravado_5),
            'gravado10': float(documento.total_gravado_10),
            'total': float(documento.total),
            'iva5': float(documento.iva_5),
            'iva10': float(documento.iva_10),
            'iva_total': float(documento.iva_5) + float(documento.iva_10),
        },

        'cdc': documento.cdc,
        'cdc_legible': cdc_mod.formatear_legible(documento.cdc),
        'enlace_qr': documento.enlace_qr,
        'url_consulta': (getattr(settings, 'SIFEN', {})
                         .get('url_consulta_qr', '')).rsplit('/qr', 1)[0],
        'estado': documento.get_estado_display(),
        'cancelado': documento.estado == documento.ESTADO_CANCELADO,
    }


# ─── Geometría del encabezado ────────────────────────────────────────────────
# El encabezado se dibuja en el callback de página (para repetirse en todas
# las hojas), pero su alto lo tiene que saber `SimpleDocTemplate` ANTES, para
# fijar el `topMargin` por debajo del cual arranca la tabla de ítems.
#
# Antes esos dos números estaban escritos a mano y no coincidían: el margen
# era 76 mm fijos y la raya separadora se dibujaba a 26 mm del tope, sin
# importar cuánto medía el bloque del emisor. Con los datos reales del local
# ese bloque mide 25,8 mm — 0,2 mm menos que la raya — así que la raya pasaba
# rozando el teléfono, cruzaba el logo y la primera línea del receptor caía
# encima de la última del emisor. Se veía en el PDF.
#
# Ahora hay una sola función que arma las líneas y las mide, y tanto el margen
# como el dibujo salen de ella. Si el emisor cambia de dirección, el papel se
# reacomoda solo.

TOPE_MM = 22.0        # dónde arranca el bloque del emisor, desde el borde
ALTO_LINEA_TITULO_MM = 4.2
ALTO_LINEA_CUERPO_MM = 3.6
HUECO_ANTES_DE_RAYA_MM = 2.4
ALTO_LINEA_RECEPTOR_MM = 4.2
HUECO_DESPUES_DE_RAYA_MM = 4.5
COLCHON_ANTES_DE_ITEMS_MM = 6.0


def _lineas_emisor(datos):
    """
    Los renglones del bloque del emisor, ya partidos.

    Devuelve una lista de `(texto, fuente, tamaño, alto_mm)`. Se arma una sola
    vez y sirve para medir y para dibujar, que es lo que garantiza que las dos
    cosas no se separen.
    """
    emisor = datos['emisor']
    lineas = []
    for texto in _cortar(emisor['razon_social'], 46)[:2]:
        lineas.append((texto, 'Helvetica-Bold', 9, ALTO_LINEA_TITULO_MM))
    for texto in (emisor['actividad'], emisor['direccion'],
                  emisor['ciudad'], emisor['telefono']):
        if not texto:
            continue
        for linea in _cortar(texto, 62)[:2]:
            lineas.append((linea, 'Helvetica', 7.5, ALTO_LINEA_CUERPO_MM))
    return lineas


def _alto_encabezado_mm(datos):
    """Alto total del encabezado, en milímetros, incluido el colchón final."""
    alto_emisor = sum(alto for _, _, _, alto in _lineas_emisor(datos))

    # El bloque del timbrado, a la derecha, compite por la misma banda: son
    # cuatro renglones más el número del documento. El encabezado mide lo que
    # mida el más alto de los dos, no lo que mida el de la izquierda.
    alto_timbrado = 5 * ALTO_LINEA_TITULO_MM

    filas_receptor = 4  # fecha/condición/moneda, RUC, razón social, dirección
    if datos['receptor'].get('email'):
        filas_receptor += 1
    if datos['en_prueba']:
        filas_receptor += 1

    return (TOPE_MM
            + max(alto_emisor, alto_timbrado)
            + HUECO_ANTES_DE_RAYA_MM
            + HUECO_DESPUES_DE_RAYA_MM
            + filas_receptor * ALTO_LINEA_RECEPTOR_MM
            + COLCHON_ANTES_DE_ITEMS_MM)


# ─── Dibujo ──────────────────────────────────────────────────────────────────

def render_pdf(documento) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    datos = construir_datos(documento)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        # El margen superior sale de medir el encabezado real, no de un
        # número fijo: ver `_alto_encabezado_mm`. El inferior deja lugar al
        # QR y al CDC, que sí son de tamaño conocido.
        topMargin=_alto_encabezado_mm(datos) * mm, bottomMargin=48 * mm,
        leftMargin=14 * mm, rightMargin=14 * mm,
        title=f'{datos["nombre_documento"]} {datos["numero"]}',
    )

    st_celda = ParagraphStyle('celda', fontName='Helvetica', fontSize=7.5,
                              leading=9.5, textColor=colors.HexColor('#1a1714'))
    st_der = ParagraphStyle('celda_der', parent=st_celda, alignment=2)
    st_th = ParagraphStyle('th', fontName='Helvetica-Bold', fontSize=7.5,
                           leading=9.5, textColor=colors.HexColor(MARCA))
    # El SKU del catálogo es una sola palabra larga y con guiones
    # ("PIS-001-18x122-ROBLE-GRIS-NATURAL"). Un Paragraph normal solo corta en
    # espacios, así que la desbordaba a lo ancho o la partía en cinco
    # renglones y estiraba toda la fila. `wordWrap='CJK'` corta donde entre.
    st_codigo = ParagraphStyle('codigo', parent=st_celda, fontSize=6.8,
                               leading=8.2, wordWrap='CJK')

    ancho = A4[0] - doc.leftMargin - doc.rightMargin

    # ── Ítems (§13.4.2) ──────────────────────────────────────────────────
    encabezados = ['Cód.', 'Descripción', 'Unidad', 'Cantidad', 'Precio unit.',
                   'Descuento', 'Exentas', '5%', '10%']
    filas = [[Paragraph(h, st_th) for h in encabezados]]
    for item in datos['items']:
        filas.append([
            Paragraph(item['codigo'], st_codigo),
            Paragraph(item['descripcion'], st_celda),
            Paragraph(item['unidad'], st_celda),
            Paragraph(_num(item['cantidad']), st_der),
            Paragraph(_gs(item['precio_unitario']), st_der),
            Paragraph(_gs(item['descuento']) if item['descuento'] else '—', st_der),
            Paragraph(_gs(item['exentas']) if item['exentas'] else '—', st_der),
            Paragraph(_gs(item['iva5']) if item['iva5'] else '—', st_der),
            Paragraph(_gs(item['iva10']) if item['iva10'] else '—', st_der),
        ])

    # Los anchos se fijaron mirando el PDF renderizado, no a ojo: con los
    # anteriores los títulos "Unidad" y "Descuento" se partían al medio
    # ("Unida/d", "Descuent/o") y el código ocupaba cinco renglones. Suman 1.
    anchos = [0.12, 0.25, 0.07, 0.09, 0.11, 0.10, 0.08, 0.08, 0.10]
    tabla = Table(filas, colWidths=[ancho * p for p in anchos], repeatRows=1)
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(SIDEBAR)),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor(BORDE)),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        # El relleno lateral por defecto de reportlab son 6 pt de cada lado:
        # 4,2 mm perdidos por columna, que en nueve columnas es la diferencia
        # entre que los títulos entren en un renglón o se partan al medio
        # ("Unida/d", "Cantida/d"). Se baja a 3 pt.
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))

    elementos = [tabla, Spacer(1, 8)]

    # ── Totales y liquidación del IVA (§13.4.3) ──────────────────────────
    # Las tres columnas del SUBTOTAL son la suma de las columnas de arriba
    # (F002/F004/F005: el total de la operación por afectación, con IVA
    # incluido). No se usa el desglose gravado/IVA del documento, que es la
    # base neta: si se mezclaran, la columna no sumaría lo que está impreso
    # justo arriba y el cliente vería un papel que no cierra.
    t = datos['totales']
    filas_resumen = [
        ['SUBTOTAL', _gs(t['subtotal_exentas']), _gs(t['subtotal_5']),
         _gs(t['subtotal_10'])],
        ['TOTAL DE LA OPERACIÓN', '', '', _gs(t['total'])],
        ['TOTAL EN GUARANÍES', '', '', _gs(t['total'])],
        [f'LIQUIDACIÓN IVA — (5%): {_gs(t["iva5"])}   (10%): {_gs(t["iva10"])}',
         'TOTAL IVA', '', _gs(t['iva_total'])],
    ]

    # ⚠️ Las tres columnas numéricas tienen que caer EXACTAMENTE debajo de
    # "Exentas", "5%" y "10%" de la tabla de arriba. No es estética: cada
    # número del SUBTOTAL es el total de su columna, y con los anchos viejos
    # (0,52 / 0,16 / 0,16 / 0,16) caían debajo de "Precio unit." y
    # "Descuento" — el papel decía que el subtotal exento era el subtotal de
    # los precios unitarios. Además las dos grillas no coincidían y se leían
    # como rayas encimadas.
    #
    # Por eso se derivan de `anchos` en vez de escribirse a mano: si alguien
    # toca la tabla de ítems, esta lo sigue.
    ancho_etiqueta = sum(anchos[:-3])
    resumen = Table(filas_resumen, colWidths=[
        ancho * ancho_etiqueta,
        ancho * anchos[-3], ancho * anchos[-2], ancho * anchos[-1]])
    resumen.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 8),
        ('FONT', (0, 1), (-1, 2), 'Helvetica-Bold', 9),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor(BORDE)),
        # Las filas de total llevan un solo valor, a la derecha. Sin el SPAN
        # quedaban dos celdas vacías con sus bordes, que es la otra fuente de
        # rayitas sueltas en el bloque.
        ('SPAN', (0, 1), (2, 1)),
        ('SPAN', (0, 2), (2, 2)),
        # "TOTAL IVA" no entra en una columna de 8% del ancho: se le dan las
        # dos, que igual están vacías en esa fila.
        ('SPAN', (1, 3), (2, 3)),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))
    elementos.append(resumen)

    if datos['cancelado']:
        elementos.append(Spacer(1, 10))
        elementos.append(Paragraph(
            '<b>DOCUMENTO CANCELADO ANTE EL SIFEN.</b> Esta representación '
            'gráfica corresponde a un documento electrónico que fue anulado '
            'por su emisor.',
            ParagraphStyle('cancelado', fontName='Helvetica-Bold', fontSize=9,
                           textColor=colors.HexColor('#9a3030'))))

    doc.build(elementos,
              onFirstPage=lambda c, d: _encabezado_y_pie(c, d, datos),
              onLaterPages=lambda c, d: _encabezado_y_pie(c, d, datos))
    return buffer.getvalue()


def _encabezado_y_pie(c, doc, datos):
    """
    Encabezado (§13.4.1) y pie con los datos de consulta (§13.4.4).

    Van en el callback de página y no como flowables para que se repitan
    igual en todas las hojas: el manual exige que el KuDE de varias páginas
    esté numerado y que el QR esté al menos en la primera (§13.3).
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    ancho_pagina, alto_pagina = A4
    izq = doc.leftMargin
    der = ancho_pagina - doc.rightMargin

    c.saveState()

    # ── Título ───────────────────────────────────────────────────────────
    c.setFont('Helvetica-Bold', 12)
    c.setFillColor(colors.HexColor(SIDEBAR))
    c.drawCentredString(ancho_pagina / 2, alto_pagina - 16 * mm,
                        datos['denominacion'].upper())

    tope = alto_pagina - TOPE_MM * mm

    lineas_emisor = _lineas_emisor(datos)
    alto_emisor = sum(alto for _, _, _, alto in lineas_emisor)
    alto_banda = max(alto_emisor, 5 * ALTO_LINEA_TITULO_MM)

    # ── Logo ─────────────────────────────────────────────────────────────
    # Se escala para que entre en la banda del emisor. Antes tenía 34 mm de
    # ancho fijos —26,6 mm de alto— y su base caía por debajo de la raya
    # separadora, que le pasaba por encima al subtítulo "ACABADOS DE
    # CONSTRUCCIÓN". Ahora la banda manda y el logo se acomoda.
    if os.path.exists(LOGO):
        proporcion = 703 / 900
        ancho_logo = min(34 * mm, (alto_banda * mm) / proporcion)
        alto_logo = ancho_logo * proporcion
        c.drawImage(LOGO, izq, tope - alto_logo + ALTO_LINEA_TITULO_MM * mm * 0.7,
                    width=ancho_logo, height=alto_logo,
                    mask='auto', preserveAspectRatio=True)

    # ── Emisor ───────────────────────────────────────────────────────────
    emisor = datos['emisor']
    x_emisor = izq + 38 * mm
    y = tope
    for texto, fuente, tamano, alto in lineas_emisor:
        c.setFont(fuente, tamano)
        c.setFillColor(colors.HexColor('#1a1714' if fuente.endswith('Bold')
                                       else TEXTO_SEC))
        c.drawString(x_emisor, y, texto)
        y -= alto * mm

    # ── Timbrado ─────────────────────────────────────────────────────────
    y = tope
    c.setFont('Helvetica', 8)
    c.setFillColor(colors.HexColor('#1a1714'))
    for etiqueta, valor in (
        ('RUC', emisor['ruc']),
        ('Timbrado N.º', emisor['timbrado']),
        ('Inicio de vigencia', emisor['timbrado_inicio']),
        ('Fin de vigencia', emisor['timbrado_vto']),
    ):
        c.drawRightString(der, y, f'{etiqueta}: {valor or "—"}')
        y -= ALTO_LINEA_TITULO_MM * mm
    c.setFont('Helvetica-Bold', 9)
    c.setFillColor(colors.HexColor(SIDEBAR))
    c.drawRightString(der, y, f'{datos["nombre_documento"]} N.º {datos["numero"]}')

    # ── Datos generales y receptor ───────────────────────────────────────
    y_linea = tope - (alto_banda + HUECO_ANTES_DE_RAYA_MM) * mm
    c.setStrokeColor(colors.HexColor(MARCA))
    c.setLineWidth(0.8)
    c.line(izq, y_linea, der, y_linea)

    c.setFont('Helvetica', 7.5)
    c.setFillColor(colors.HexColor(TEXTO_SEC))
    y = y_linea - HUECO_DESPUES_DE_RAYA_MM * mm
    c.drawString(izq, y, f'Fecha y hora de emisión: {datos["fecha_emision"]}')
    c.drawCentredString(ancho_pagina / 2, y,
                        f'Condición de venta: {datos["condicion"]}')
    c.drawRightString(der, y, f'Moneda: {datos["moneda"]}')

    receptor = datos['receptor']
    y -= ALTO_LINEA_RECEPTOR_MM * mm
    c.drawString(izq, y, f'RUC / Documento: {receptor["documento"]}')
    c.drawRightString(der, y, f'Teléfono: {receptor["telefono"] or "—"}')
    y -= ALTO_LINEA_RECEPTOR_MM * mm
    # Razón social y dirección se recortan al ancho útil: son datos del
    # cliente, de largo impredecible, y sin tope se montaban sobre el dato
    # alineado a la derecha del mismo renglón.
    c.drawString(izq, y, _cortar(
        f'Nombre o razón social: {receptor["razon_social"]}', 95)[0])
    y -= ALTO_LINEA_RECEPTOR_MM * mm
    c.drawString(izq, y, _cortar(
        f'Dirección: {receptor["direccion"] or "—"}', 95)[0])
    # El correo va en su propio renglón y no al lado de la dirección: antes
    # compartían la línea de base, uno alineado a izquierda y otro a derecha,
    # y una dirección larga se le encimaba.
    if receptor['email']:
        y -= ALTO_LINEA_RECEPTOR_MM * mm
        c.drawString(izq, y, f'Correo: {receptor["email"]}')

    if datos['en_prueba']:
        y -= ALTO_LINEA_RECEPTOR_MM * mm
        c.setFont('Helvetica-Bold', 8)
        c.setFillColor(colors.HexColor('#9a3030'))
        c.drawString(izq, y, 'DOCUMENTO EMITIDO EN AMBIENTE DE PRUEBA — '
                             'SIN VALOR COMERCIAL NI FISCAL')

    # ── Pie: consulta en el SIFEN y QR ───────────────────────────────────
    _pie_consulta(c, doc, datos)
    c.restoreState()


def _pie_consulta(c, doc, datos):
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode import qr
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    ancho_pagina, _ = A4
    izq = doc.leftMargin
    der = ancho_pagina - doc.rightMargin
    base = 12 * mm

    lado = QR_LADO_MM * mm
    if datos['enlace_qr']:
        widget = qr.QrCodeWidget(datos['enlace_qr'])
        limites = widget.getBounds()
        escala = lado / max(limites[2] - limites[0], limites[3] - limites[1])
        dibujo = Drawing(lado, lado, transform=[escala, 0, 0, escala, 0, 0])
        dibujo.add(widget)
        renderPDF.draw(dibujo, c, der - lado, base)
    else:
        # Sin firma no hay QR posible: el contenido lleva el hash de la firma
        # y el CSC (§13.8.2). Se dice, en vez de dibujar algo que no resuelve.
        c.setFont('Helvetica-Oblique', 6.5)
        c.setFillColor(colors.HexColor('#9a3030'))
        c.drawRightString(der, base + 8 * mm, 'QR pendiente: el documento')
        c.drawRightString(der, base + 5 * mm, 'todavía no fue firmado ni')
        c.drawRightString(der, base + 2 * mm, 'transmitido al SIFEN.')

    c.setFont('Helvetica', 7)
    c.setFillColor(colors.HexColor(TEXTO_SEC))
    y = base + lado - 3 * mm
    c.drawString(izq, y, 'Consulte la validez de este documento electrónico en:')
    y -= 3.6 * mm
    c.setFont('Helvetica-Bold', 7)
    c.drawString(izq, y, datos['url_consulta'] or 'https://ekuatia.set.gov.py/consultas/')
    y -= 5 * mm
    c.setFont('Helvetica', 7)
    c.drawString(izq, y, 'CDC (Código de Control):')
    y -= 3.8 * mm
    c.setFont('Courier-Bold', 7.6)
    c.setFillColor(colors.HexColor('#1a1714'))
    c.drawString(izq, y, datos['cdc_legible'])
    y -= 4.4 * mm
    c.setFont('Helvetica-Oblique', 6.5)
    c.setFillColor(colors.HexColor(TEXTO_SEC))
    c.drawString(izq, y, 'Documento tributario auxiliar. El documento válido '
                         'es el archivo electrónico aprobado por el SIFEN.')

    c.setFont('Helvetica', 6.5)
    c.drawRightString(der, base - 4 * mm, f'Página {c.getPageNumber()}')


def _cortar(texto, largo):
    """Parte un texto largo en renglones, sin cortar palabras al medio."""
    palabras, lineas, actual = str(texto or '').split(), [], ''
    for palabra in palabras:
        if len(actual) + len(palabra) + 1 > largo:
            lineas.append(actual)
            actual = palabra
        else:
            actual = f'{actual} {palabra}'.strip()
    if actual:
        lineas.append(actual)
    return lineas or ['']


# ─── Entrega ─────────────────────────────────────────────────────────────────

def responder(documento) -> HttpResponse:
    contenido = render_pdf(documento)
    respuesta = HttpResponse(contenido, content_type='application/pdf')
    nombre = f'kude_{documento.numero_completo.replace("-", "")}.pdf'
    # inline: lo normal es abrirlo para imprimirlo o mandarlo por WhatsApp,
    # no archivarlo en Descargas.
    respuesta['Content-Disposition'] = f'inline; filename="{nombre}"'
    return respuesta
