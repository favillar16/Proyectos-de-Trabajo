"""
apps/caja/impresora_a4.py
Impresión en hoja A4 con la Epson EcoTank L1250.

Alcance — leer antes de agregar nada acá
────────────────────────────────────────
**La L1250 NO es la impresora de facturas.** El comprobante fiscal sale por
otro equipo (la térmica FTX FTXP-80W hoy, y el modelo que se conecte para
facturar cuando esté). Este módulo existe para lo que sí necesita una hoja A4
común:

- **Etiquetas de código de barras**, que es lo que hace usable al lector
  FTX-LC123BH5 con la mercadería que viene sin EAN de fábrica: se genera un
  código interno (apps/productos/codigo_barras.py), se imprime la planilla y
  se pega en la caja.
- Cualquier PDF que haya que sacar en hoja: `imprimir_pdf()` es genérico y
  también sirve para los reportes de `reportes.py`.

Por qué no se le puede mandar lo mismo que a la térmica
───────────────────────────────────────────────────────
`printer.py` habla ESC/POS: bytes crudos a la térmica, que imprime texto de
48 columnas en un rollo de 80 mm. La L1250 es una inyección de tinta con
driver GDI: no entiende ESC/POS y mandarle esos bytes en RAW saca páginas de
basura. Todo lo que salga por acá tiene que ser una página ya compuesta — un
PDF armado con reportlab.

Cómo llega el PDF a la impresora
────────────────────────────────
Dos modos, configurables con IMPRESORA_A4_MODO en el .env:

- **manual** (default) — el backend devuelve el PDF y el navegador lo abre en
  el diálogo de impresión. Anda siempre, sin depender de qué visor de PDF
  esté instalado en el servidor.
- **auto** — el servidor manda el PDF a la cola de Windows por su cuenta, sin
  intervención. Necesita que el .pdf tenga registrado el verbo "printto", que
  es lo que trae Adobe Acrobat Reader y NO trae el visor de Edge. Por eso no
  es el default: si no está el handler, el trabajo se pierde en silencio.
  `python diagnostico_impresora.py` dice si está o no.
"""
import io
import logging
import os
import tempfile
from datetime import datetime

from django.conf import settings

logger = logging.getLogger(__name__)


# ─── Helpers de formato ───────────────────────────────────────────────────────

def _gs(v):
    """Guaraníes con separador de miles. El guaraní no tiene centavos."""
    try:
        return f'Gs. {int(round(float(v))):,}'.replace(',', '.')
    except (TypeError, ValueError):
        return 'Gs. 0'


def _cfg():
    return getattr(settings, 'IMPRESORA_A4', {})


# ─── Envío a la impresora (Windows) ───────────────────────────────────────────

def imprimir_pdf(pdf_bytes: bytes, titulo: str = 'Documento',
                 nombre_impresora: str = '', copias: int = 0) -> dict:
    """
    Manda un PDF ya armado a la L1250 usando el verbo "printto" de Windows.

    Retorna {'ok', 'error', 'metodo'} con la misma forma que
    printer.WindowsPrinter.imprimir(), para que las views traten a las dos
    impresoras igual.

    El archivo temporal NO se borra al terminar: ShellExecute es asincrónico y
    el visor de PDF puede tardar segundos en leerlo. Borrarlo enseguida deja
    la hoja en blanco. Se limpian los viejos en la llamada siguiente.
    """
    cfg = _cfg()
    nombre = nombre_impresora or cfg.get('nombre_windows', '')
    copias = copias or cfg.get('copias', 1)

    if not nombre:
        return {'ok': False, 'metodo': 'ninguno',
                'error': 'No hay impresora A4 configurada (IMPRESORA_A4_NOMBRE en el .env).'}

    carpeta = os.path.join(tempfile.gettempdir(), 'oga_pora_impresion')
    os.makedirs(carpeta, exist_ok=True)
    _limpiar_temporales(carpeta)

    seguro = ''.join(c for c in titulo if c.isalnum() or c in '-_')[:40] or 'documento'
    ruta = os.path.join(
        carpeta, f'{seguro}_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}.pdf')
    with open(ruta, 'wb') as f:
        f.write(pdf_bytes)

    try:
        import win32api
    except ImportError:
        # Fuera de Windows (desarrollo) se comporta como printer.py: no falla,
        # deja el PDF en disco y avisa por dónde salió.
        logger.warning('win32api no disponible — impresión A4 simulada en %s', ruta)
        return {'ok': True, 'error': None, 'metodo': 'simulado', 'archivo': ruta}

    try:
        for _ in range(copias):
            # El nombre de la impresora va entre comillas: "EPSON L1250 Series"
            # tiene espacios y sin comillas Windows lo parte en el primero.
            win32api.ShellExecute(0, 'printto', ruta, f'"{nombre}"', '.', 0)
        return {'ok': True, 'error': None, 'metodo': 'printto',
                'impresora': nombre, 'archivo': ruta}
    except Exception as e:
        logger.error('Error al imprimir el PDF en %s: %s', nombre, e)
        return {
            'ok': False, 'metodo': 'printto', 'archivo': ruta,
            'error': (
                f'{e}. Suele ser que el .pdf no tiene registrado el verbo '
                f'"printto" (lo instala Adobe Acrobat Reader; el visor de Edge '
                f'no lo trae). Corré diagnostico_impresora.py para confirmarlo, '
                f'o dejá IMPRESORA_A4_MODO=manual e imprimí desde el navegador.'
            ),
        }


def _limpiar_temporales(carpeta, horas=24):
    """Borra los PDF temporales de más de `horas`. Nunca falla hacia afuera."""
    try:
        limite = datetime.now().timestamp() - horas * 3600
        for nombre in os.listdir(carpeta):
            ruta = os.path.join(carpeta, nombre)
            if os.path.isfile(ruta) and os.path.getmtime(ruta) < limite:
                os.remove(ruta)
    except OSError:
        pass


def estado_impresora_a4() -> dict:
    """
    Diagnóstico de la L1250, con la misma forma que EstadoImpresora usa para
    la térmica. No imprime nada.
    """
    cfg = _cfg()
    nombre = cfg.get('nombre_windows', '')
    resultado = {
        'modelo':        cfg.get('modelo', 'Epson EcoTank L1250'),
        'nombre':        nombre,
        'modo':          cfg.get('modo', 'manual'),
        'configurada':   bool(nombre),
        'disponible':    False,
        'error':         None,
    }
    if not nombre:
        resultado['error'] = 'No hay impresora A4 configurada en el .env (IMPRESORA_A4_NOMBRE).'
        return resultado

    try:
        import win32print
        impresoras = [p[2] for p in win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )]
        resultado['impresoras_disponibles'] = impresoras
        resultado['disponible'] = nombre in impresoras
        if not resultado['disponible']:
            # Match parcial: el driver de Epson a veces registra la cola como
            # "EPSON L1250 Series" y en el .env quedó "L1250" o al revés.
            parecidas = [i for i in impresoras
                         if 'l1250' in i.lower().replace(' ', '')]
            sugerencia = f' ¿Será "{parecidas[0]}"?' if parecidas else ''
            resultado['error'] = (
                f'La impresora "{nombre}" no está instalada en esta PC.{sugerencia} '
                f'Instaladas: {", ".join(impresoras) or "ninguna"}.'
            )
    except ImportError:
        resultado['disponible'] = True
        resultado['error'] = 'win32print no disponible (entorno no-Windows).'
    except Exception as e:
        resultado['error'] = str(e)

    return resultado


# ─── Planilla de etiquetas de código de barras ────────────────────────────────

# Grilla de la planilla. Son etiquetas autoadhesivas A4 de 70×37 mm (3×8), el
# formato más común de librería en Paraguay. Si se compra otro formato, se
# cambian estas cuatro constantes y el resto se acomoda solo.
ETIQUETAS_COLUMNAS = 3
ETIQUETAS_FILAS    = 8
ETIQUETA_ANCHO_MM  = 70
ETIQUETA_ALTO_MM   = 37


def etiquetas_pdf(etiquetas, desde_posicion=0) -> bytes:
    """
    Planilla A4 de etiquetas con código de barras, para pegar en la mercadería.

    `etiquetas` es una lista de dicts:
        {'codigo', 'sku', 'nombre', 'detalle', 'precio'}

    `desde_posicion` saltea las primeras N celdas de la primera hoja. Sirve
    para reusar una planilla a la que ya se le arrancaron etiquetas, que es lo
    que pasa siempre en la práctica: si no, cada impresión desperdicia una hoja
    entera.

    El código se dibuja como EAN-13 cuando el valor lo permite y como Code128
    en cualquier otro caso. El FTX-LC123BH5 lee las dos simbologías de fábrica,
    sin configurarle nada.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as pdfcanvas
    from reportlab.graphics.barcode import createBarcodeDrawing
    from reportlab.graphics import renderPDF

    from apps.productos.codigo_barras import es_ean_valido

    ANCHO, ALTO = A4
    et_ancho = ETIQUETA_ANCHO_MM * mm
    et_alto  = ETIQUETA_ALTO_MM * mm
    por_hoja = ETIQUETAS_COLUMNAS * ETIQUETAS_FILAS

    # Centrar la grilla en la hoja: las planillas comerciales tienen márgenes
    # laterales mínimos y esto los reparte parejo.
    margen_x = (ANCHO - ETIQUETAS_COLUMNAS * et_ancho) / 2
    margen_y = (ALTO - ETIQUETAS_FILAS * et_alto) / 2

    buffer = io.BytesIO()
    c = pdfcanvas.Canvas(buffer, pagesize=A4)
    c.setTitle('Etiquetas de código de barras')

    posicion = desde_posicion % por_hoja
    # Las celdas salteadas de la primera hoja quedan en blanco a propósito.
    for etiqueta in etiquetas:
        if posicion >= por_hoja:
            c.showPage()
            posicion = 0

        col = posicion % ETIQUETAS_COLUMNAS
        fila = posicion // ETIQUETAS_COLUMNAS
        cx = margen_x + col * et_ancho
        cy = ALTO - margen_y - (fila + 1) * et_alto

        _dibujar_etiqueta(c, etiqueta, cx, cy, et_ancho, et_alto, mm,
                          colors, createBarcodeDrawing, renderPDF, es_ean_valido)
        posicion += 1

    c.showPage()
    c.save()
    return buffer.getvalue()


def _dibujar_etiqueta(c, e, x, y, ancho, alto, mm, colors,
                      createBarcodeDrawing, renderPDF, es_ean_valido):
    """Una celda de la planilla: nombre, código de barras, SKU y precio."""
    pad = 3 * mm
    codigo = str(e.get('codigo', '') or '')

    # Marco tenue: guía para el corte cuando se imprime en hoja común en vez
    # de en planilla troquelada.
    c.setStrokeColor(colors.HexColor('#e8e4df'))
    c.setLineWidth(0.3)
    c.rect(x, y, ancho, alto)

    # Nombre del producto, hasta dos líneas
    c.setFillColor(colors.HexColor('#1a1714'))
    c.setFont('Helvetica-Bold', 7.5)
    texto = str(e.get('nombre', ''))[:60]
    corte = _partir(texto, 40)
    ty = y + alto - pad - 2.5 * mm
    for linea in corte[:2]:
        c.drawString(x + pad, ty, linea)
        ty -= 3.2 * mm

    detalle = str(e.get('detalle', '') or '')
    if detalle:
        c.setFillColor(colors.HexColor('#6b6560'))
        c.setFont('Helvetica', 6.5)
        c.drawString(x + pad, ty, detalle[:44])
        ty -= 3.2 * mm

    # Código de barras
    if codigo:
        try:
            if es_ean_valido(codigo) and len(codigo) == 13:
                dibujo = createBarcodeDrawing(
                    'EAN13', value=codigo, barHeight=11 * mm,
                    humanReadable=True, fontSize=6)
            else:
                dibujo = createBarcodeDrawing(
                    'Code128', value=codigo, barHeight=11 * mm,
                    humanReadable=True, fontSize=6, barWidth=0.42 * mm)
            # Escalar si no entra: un código más ancho que la etiqueta se
            # imprime cortado y no lo lee nadie.
            disponible = ancho - 2 * pad
            escala = min(1.0, disponible / dibujo.width) if dibujo.width else 1.0
            dibujo.scale(escala, escala)
            dibujo.width *= escala
            dibujo.height *= escala
            renderPDF.draw(dibujo, c,
                           x + (ancho - dibujo.width) / 2,
                           y + pad + 3.5 * mm)
        except Exception as exc:      # noqa: BLE001 — una etiqueta rota no
            # puede tumbar la planilla entera: se imprime el código en texto y
            # se sigue con las demás.
            logger.warning('No se pudo dibujar el código %s: %s', codigo, exc)
            c.setFont('Courier-Bold', 9)
            c.setFillColor(colors.HexColor('#9a3030'))
            c.drawCentredString(x + ancho / 2, y + alto / 2, codigo)

    # Pie: SKU a la izquierda, precio a la derecha
    c.setFont('Courier', 6)
    c.setFillColor(colors.HexColor('#6b6560'))
    c.drawString(x + pad, y + pad, str(e.get('sku', ''))[:26])
    if e.get('precio'):
        c.setFont('Helvetica-Bold', 8)
        c.setFillColor(colors.HexColor('#8a7355'))
        c.drawRightString(x + ancho - pad, y + pad, _gs(e['precio']))


def _partir(texto, ancho):
    """Parte un texto en líneas de a lo sumo `ancho` caracteres, por palabra."""
    palabras = texto.split()
    lineas, actual = [], ''
    for palabra in palabras:
        candidata = f'{actual} {palabra}'.strip()
        if len(candidata) <= ancho:
            actual = candidata
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas or ['']
