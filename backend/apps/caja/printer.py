"""
apps/caja/printer.py
Módulo de impresión ESC/POS para la impresora térmica FTX FTXP-80W en Windows.

Arquitectura:
  TicketBuilder   — construye los bytes ESC/POS del ticket
  WindowsPrinter  — envía los bytes a la impresora vía win32print
  imprimir_ticket — función de alto nivel para llamar desde las views
  imprimir_cierre — ticket de cierre de sesión

ESC/POS Reference:
  https://escpos.readthedocs.io/
  Comandos básicos que usa este módulo:
    ESC @   — inicializar impresora
    ESC a N — alineación: 0=izq, 1=centro, 2=der
    ESC E N — negrita: 1=on, 0=off
    ESC !   — seleccionar modo de impresión
    GS V    — corte de papel
    LF      — avance de línea
"""
import logging
from datetime import datetime

from django.conf import settings

logger = logging.getLogger(__name__)

# ─── Constantes ESC/POS ───────────────────────────────────────────────────────

ESC = b'\x1b'
GS  = b'\x1d'
LF  = b'\x0a'
CR  = b'\x0d'

# Inicializar
INIT            = ESC + b'@'
# Alineación
ALIGN_LEFT      = ESC + b'a\x00'
ALIGN_CENTER    = ESC + b'a\x01'
ALIGN_RIGHT     = ESC + b'a\x02'
# Negrita
BOLD_ON         = ESC + b'E\x01'
BOLD_OFF        = ESC + b'E\x00'
# Doble ancho + alto (para totales)
DOUBLE_ON       = ESC + b'!\x38'   # double width + height + bold
DOUBLE_OFF      = ESC + b'!\x00'
# Fuente pequeña (font B — más caracteres por línea)
FONT_A          = ESC + b'M\x00'   # 12×24 dots — 48 char/línea @80mm
FONT_B          = ESC + b'M\x01'   # 9×17  dots — 64 char/línea @80mm
# Corte de papel
CUT_FULL        = GS  + b'V\x00'
CUT_PARTIAL     = GS  + b'V\x01'   # Recomendado para rollo continuo
# Avances extra antes del corte
FEED_LINES      = lambda n: ESC + b'd' + bytes([n])


# ─── Helpers de formato ───────────────────────────────────────────────────────

COLS = 48  # caracteres por línea con font A a 80mm

def _enc(texto: str, encoding='cp850') -> bytes:
    """Codifica texto al encoding de la impresora, reemplazando chars no soportados."""
    return texto.encode(encoding, errors='replace')

def _linea(texto: str, encoding='cp850') -> bytes:
    """Línea de texto con salto de línea."""
    return _enc(texto, encoding) + LF

def _separador(char='-') -> bytes:
    return _enc(char * COLS) + LF

def _dos_columnas(izq: str, der: str, cols=COLS) -> bytes:
    """
    Texto en dos columnas: izquierda y derecha alineada.
    Ej: 'Subtotal           Gs. 185.000'
    """
    espacio = cols - len(izq) - len(der)
    if espacio < 1:
        # Si no cabe, truncar la izquierda
        izq = izq[:cols - len(der) - 1]
        espacio = 1
    return _enc(izq + ' ' * espacio + der) + LF

def _centrado(texto: str, cols=COLS) -> bytes:
    padding = max(0, (cols - len(texto)) // 2)
    return _enc(' ' * padding + texto) + LF

def _formatGs(valor) -> str:
    return f'Gs. {int(valor):,}'.replace(',', '.')


# ─── Builder de ticket de venta ───────────────────────────────────────────────

class TicketBuilder:
    """
    Construye la secuencia de bytes ESC/POS de un ticket de venta.
    No tiene dependencias de impresora — solo genera bytes.
    """

    def __init__(self, datos: dict):
        self.datos    = datos
        self.encoding = settings.IMPRESORA_TERMICA.get('encoding', 'cp850')
        self.cols     = settings.IMPRESORA_TERMICA.get('caracteres_linea', 48)

    def _e(self, texto):
        return _enc(texto, self.encoding)

    def _l(self, texto=''):
        return self._e(texto) + LF

    def _sep(self, char='-'):
        return self._e(char * self.cols) + LF

    def _2col(self, izq, der):
        return _dos_columnas(izq, der, self.cols)

    def build(self) -> bytes:
        d = self.datos
        buf = bytearray()

        # ── Inicializar ──────────────────────────────────────
        buf += INIT
        buf += FONT_A

        # ── Cabecera del negocio ─────────────────────────────
        buf += ALIGN_CENTER
        buf += BOLD_ON
        buf += self._l(d.get('negocio', 'Oga Porã'))
        buf += BOLD_OFF
        buf += self._l(d.get('ruc', ''))
        buf += self._l(d.get('direccion', ''))
        buf += self._l(d.get('telefono', ''))
        buf += LF

        # ── Datos del comprobante ────────────────────────────
        buf += ALIGN_CENTER
        buf += BOLD_ON
        buf += self._l('- TICKET DE VENTA -')
        buf += BOLD_OFF
        buf += self._e('Comprobante no fiscal') + LF
        buf += ALIGN_LEFT
        buf += self._sep('-')
        buf += self._2col('Ticket:', d.get('numero_ticket', ''))
        buf += self._2col('Fecha:', d.get('fecha', ''))
        buf += self._2col('Cajero:', d.get('cajero', ''))
        buf += self._2col('Pedido:', d.get('pedido_numero', ''))
        buf += self._2col('Cliente:', d.get('cliente', 'Consumidor Final'))
        buf += self._sep('-')

        # ── Ítems ────────────────────────────────────────────
        buf += BOLD_ON
        buf += self._2col('PRODUCTO', 'SUBTOTAL')
        buf += BOLD_OFF
        buf += self._sep()

        for item in d.get('items', []):
            nombre     = str(item.get('descripcion', ''))[:self.cols]
            detalle    = str(item.get('detalle', ''))
            cant       = item.get('cantidad', 0)
            precio     = item.get('precio_unit', 0)
            subtotal   = item.get('subtotal', 0)

            # Línea 1: nombre del producto
            buf += self._l(nombre)
            # Línea 2: detalle + cantidad × precio = subtotal
            cant_str  = f'{cant:.2f}'.rstrip('0').rstrip('.')
            linea2    = f'  {detalle[:22]}' if detalle and detalle != nombre else ''
            buf += self._2col(
                f'  {cant_str} x {_formatGs(precio)}',
                _formatGs(subtotal)
            )
            if linea2:
                buf += self._l(linea2)

        buf += self._sep()

        # ── Totales ──────────────────────────────────────────
        if float(d.get('descuento', 0)) > 0:
            buf += self._2col('Subtotal:', _formatGs(d['subtotal']))
            buf += self._2col('Descuento:', '- ' + _formatGs(d['descuento']))
            buf += self._sep()

        # Total en doble tamaño
        buf += ALIGN_CENTER
        buf += DOUBLE_ON
        total_str = _formatGs(d.get('total', 0))
        buf += self._l(f'TOTAL: {total_str}')
        buf += DOUBLE_OFF
        buf += LF

        # ── Forma de pago ────────────────────────────────────
        buf += ALIGN_LEFT
        buf += self._2col('Medio de pago:', str(d.get('medio_pago', '')))

        if d.get('monto_recibido'):
            buf += self._2col('Recibido:', _formatGs(d['monto_recibido']))
        if float(d.get('vuelto', 0)) > 0:
            buf += BOLD_ON
            buf += self._2col('VUELTO:', _formatGs(d['vuelto']))
            buf += BOLD_OFF

        buf += self._sep('=')

        # ── Pie ──────────────────────────────────────────────
        buf += ALIGN_CENTER
        buf += self._l(d.get('pie', 'Gracias por su compra'))
        buf += self._l('Oga Porã — Acabados de Construcción')
        buf += LF

        # ── Corte ────────────────────────────────────────────
        buf += FEED_LINES(4)
        buf += CUT_PARTIAL

        return bytes(buf)


class FacturaBuilder:
    """
    Construye los bytes ESC/POS de una FACTURA (comprobante legal).
    A diferencia del ticket, incluye: timbrado, RUC del cliente,
    condición de venta y desglose de IVA (régimen paraguayo: 10% / 5% / exento).
    """

    def __init__(self, datos: dict):
        self.datos    = datos
        self.encoding = settings.IMPRESORA_TERMICA.get('encoding', 'cp850')
        self.cols     = settings.IMPRESORA_TERMICA.get('caracteres_linea', 48)

    def _e(self, texto):  return _enc(texto, self.encoding)
    def _l(self, texto=''): return self._e(texto) + LF
    def _sep(self, char='-'): return self._e(char * self.cols) + LF
    def _2col(self, izq, der): return _dos_columnas(izq, der, self.cols)

    def build(self) -> bytes:
        d = self.datos
        buf = bytearray()
        buf += INIT
        buf += FONT_A

        # ── Cabecera del negocio ─────────────────────────────
        buf += ALIGN_CENTER
        buf += BOLD_ON
        buf += self._l(d.get('negocio', 'Oga Porã'))
        buf += BOLD_OFF
        buf += self._l(d.get('direccion', ''))
        buf += self._l('Tel: ' + str(d.get('telefono', '')))
        buf += self._l('RUC: ' + str(d.get('ruc_negocio', '')))
        buf += LF

        # ── Datos del comprobante fiscal ─────────────────────
        buf += ALIGN_CENTER
        buf += DOUBLE_ON
        buf += self._l('FACTURA')
        buf += DOUBLE_OFF
        buf += self._e('* COMPROBANTE LEGAL *') + LF
        buf += ALIGN_LEFT
        buf += self._sep('=')
        if d.get('timbrado'):
            buf += self._2col('Timbrado N:', str(d.get('timbrado', '')))
            buf += self._2col('Vto. timbrado:', str(d.get('timbrado_vto', '')))
        buf += self._2col('Factura Nro:', d.get('factura_numero', d.get('numero_ticket', '')))
        buf += self._2col('Fecha:', d.get('fecha', ''))
        buf += self._2col('Condicion:', d.get('condicion_venta', 'Contado'))
        buf += self._sep('-')

        # ── Datos del cliente (obligatorio en factura) ───────
        buf += BOLD_ON
        buf += self._l('DATOS DEL CLIENTE')
        buf += BOLD_OFF
        buf += self._2col('Razon social:', d.get('cliente_razon_social', d.get('cliente', 'Consumidor Final')))
        buf += self._2col('RUC/CI:', str(d.get('cliente_ruc', 'Sin especificar')))
        if d.get('cliente_telefono'):
            buf += self._2col('Telefono:', str(d.get('cliente_telefono', '')))
        if d.get('cliente_direccion'):
            buf += self._l('Direccion: ' + str(d.get('cliente_direccion', '')))
        buf += self._sep('=')

        # ── Ítems ────────────────────────────────────────────
        buf += BOLD_ON
        buf += self._2col('DESCRIPCION', 'VALOR')
        buf += BOLD_OFF
        buf += self._sep()
        for item in d.get('items', []):
            nombre   = str(item.get('descripcion', ''))[:self.cols]
            cant     = item.get('cantidad', 0)
            precio   = item.get('precio_unit', 0)
            subtotal = item.get('subtotal', 0)
            cant_str = f'{cant:.2f}'.rstrip('0').rstrip('.')
            buf += self._l(nombre)
            buf += self._2col(f'  {cant_str} x {_formatGs(precio)}', _formatGs(subtotal))
        buf += self._sep()

        # ── Totales con IVA ──────────────────────────────────
        if float(d.get('descuento', 0)) > 0:
            buf += self._2col('Subtotal:', _formatGs(d.get('subtotal', 0)))
            buf += self._2col('Descuento:', '- ' + _formatGs(d.get('descuento', 0)))

        # Desglose IVA (en Paraguay el IVA viene incluido en el precio)
        iva_10 = d.get('iva_10', 0)
        iva_5  = d.get('iva_5', 0)
        exento = d.get('exento', 0)
        if iva_10:   buf += self._2col('IVA 10% incluido:', _formatGs(iva_10))
        if iva_5:    buf += self._2col('IVA 5% incluido:', _formatGs(iva_5))
        if exento:   buf += self._2col('Exento:', _formatGs(exento))
        buf += self._sep()

        buf += ALIGN_CENTER
        buf += DOUBLE_ON
        buf += self._l(f'TOTAL: {_formatGs(d.get("total", 0))}')
        buf += DOUBLE_OFF
        buf += LF

        # ── Forma de pago ────────────────────────────────────
        buf += ALIGN_LEFT
        buf += self._2col('Medio de pago:', str(d.get('medio_pago', '')))
        if d.get('monto_recibido'):
            buf += self._2col('Recibido:', _formatGs(d['monto_recibido']))
        if float(d.get('vuelto', 0)) > 0:
            buf += self._2col('Vuelto:', _formatGs(d['vuelto']))
        buf += self._sep('=')

        # ── Pie legal ────────────────────────────────────────
        buf += ALIGN_CENTER

        # Con documento electrónico el comprobante es un KuDE: la
        # representación gráfica del DE. Lleva el CDC impreso, que es lo que
        # permite consultarlo en el portal del DNIT. Sin DE se mantiene la
        # leyenda de siempre.
        cdc = str(d.get('cdc', '') or '')
        if cdc:
            buf += self._l('Consulte este documento en:')
            buf += self._l('ekuatia.set.gov.py')
            buf += LF
            buf += self._l('CDC:')
            # Se imprime agrupado de a 4 y partido en dos lineas: son 44
            # digitos y no entran de una en papel de 80mm.
            legible = str(d.get('cdc_legible', '') or cdc)
            mitad = len(legible) // 2
            corte = legible.rfind(' ', 0, mitad + 3)
            if corte == -1:
                buf += self._l(legible)
            else:
                buf += self._l(legible[:corte])
                buf += self._l(legible[corte + 1:])
            buf += LF
            # TODO: el QR del KuDE necesita la firma del DE y sale del
            # sidecar Node (facturacionelectronicapy-qrgen). Ver
            # docs/facturacion_electronica.md §5.4.
        else:
            buf += self._l('Documento no válido como')
            buf += self._l('comprobante fiscal sin timbrado')

        buf += self._l('Oga Porã — Acabados de Construcción')
        buf += FEED_LINES(4)
        buf += CUT_PARTIAL
        return bytes(buf)


class TicketCierreBuilder:
    """Ticket de cierre de sesión de caja."""

    def __init__(self, sesion, resumen: dict):
        self.sesion   = sesion
        self.resumen  = resumen
        self.encoding = settings.IMPRESORA_TERMICA.get('encoding', 'cp850')
        self.cols     = settings.IMPRESORA_TERMICA.get('caracteres_linea', 48)

    def _e(self, t): return _enc(t, self.encoding)
    def _l(self, t=''): return self._e(t) + LF
    def _sep(self, c='-'): return self._e(c * self.cols) + LF
    def _2col(self, i, d): return _dos_columnas(i, d, self.cols)

    def build(self) -> bytes:
        buf = bytearray()
        buf += INIT + FONT_A

        buf += ALIGN_CENTER
        buf += BOLD_ON
        buf += self._l('CIERRE DE CAJA')
        buf += BOLD_OFF
        buf += self._l(settings.IMPRESORA_TERMICA.get('nombre_negocio', 'Oga Porã'))
        buf += LF

        buf += ALIGN_LEFT
        buf += self._sep('=')
        ahora = datetime.now().strftime('%d/%m/%Y %H:%M')
        buf += self._2col('Fecha cierre:', ahora)
        buf += self._2col('Cajero:', self.sesion.cajero.nombre_completo)
        apertura = self.sesion.fecha_apertura.strftime('%d/%m/%Y %H:%M')
        buf += self._2col('Apertura:', apertura)
        buf += self._sep('=')

        buf += BOLD_ON
        buf += self._l('RESUMEN POR MEDIO DE PAGO')
        buf += BOLD_OFF
        buf += self._sep()

        for medio, monto in self.resumen.get('resumen_medios', {}).items():
            buf += self._2col(f'  {medio}:', _formatGs(monto))

        buf += self._sep()
        buf += self._2col('Total pagos:', str(self.resumen.get('total_pagos', 0)))
        buf += self._2col('Apertura con:', _formatGs(self.sesion.monto_apertura))

        buf += self._sep('=')
        buf += DOUBLE_ON
        buf += ALIGN_CENTER
        total_str = _formatGs(self.resumen.get('total_ventas', 0))
        buf += self._l(f'TOTAL: {total_str}')
        buf += DOUBLE_OFF
        buf += LF

        if self.sesion.monto_cierre:
            buf += ALIGN_LEFT
            buf += self._2col('En caja al cierre:', _formatGs(self.sesion.monto_cierre))
            diferencia = float(self.sesion.monto_cierre) - float(self.sesion.monto_apertura) - float(self.resumen.get('total_efectivo', 0))
            dif_str = ('+' if diferencia >= 0 else '') + _formatGs(abs(diferencia))
            buf += self._2col('Diferencia:', dif_str)

        if self.sesion.observaciones_cierre:
            buf += self._sep()
            buf += self._l('Observaciones:')
            for linea in self.sesion.observaciones_cierre.split('\n'):
                buf += self._l(linea[:self.cols])

        buf += self._sep('=')
        buf += ALIGN_CENTER
        buf += self._l('Firma: ____________________')
        buf += LF
        buf += FEED_LINES(4)
        buf += CUT_PARTIAL

        return bytes(buf)


# ─── Driver de impresora para Windows ────────────────────────────────────────

class WindowsPrinter:
    """
    Envía bytes ESC/POS a la impresora en Windows usando win32print.

    Dos estrategias según configuración:
    A) nombre_windows: usa la cola de impresión de Windows (recomendado)
       — La impresora debe estar instalada en Panel de control
       — Compatible con impresora compartida en red
    B) puerto_directo: escribe directamente al puerto USB/COM
       — Más rápido pero requiere conocer el puerto exacto
    """

    def __init__(self):
        cfg = settings.IMPRESORA_TERMICA
        self.nombre  = cfg.get('nombre_windows', '')
        self.puerto  = cfg.get('puerto_directo', '')
        self.copias  = cfg.get('copias', 1)

    def imprimir(self, datos_bytes: bytes) -> dict:
        """
        Envía los bytes a la impresora.
        Retorna {'ok': bool, 'error': str | None, 'metodo': str}
        """
        if self.puerto:
            return self._por_puerto(datos_bytes)
        elif self.nombre:
            return self._por_cola_windows(datos_bytes)
        else:
            return {'ok': False, 'error': 'No hay impresora configurada.', 'metodo': 'ninguno'}

    def _por_cola_windows(self, datos_bytes: bytes) -> dict:
        """
        Método A: Cola de impresión de Windows via win32print.
        Requiere: pip install pywin32
        """
        try:
            import win32print

            # Obtener handle de la impresora
            nombre = self.nombre or win32print.GetDefaultPrinter()
            hprinter = win32print.OpenPrinter(nombre)

            try:
                # Iniciar trabajo de impresión
                win32print.StartDocPrinter(
                    hprinter, 1,
                    ('Ticket', None, 'RAW')   # RAW = bytes directos, sin driver de conversión
                )
                try:
                    win32print.StartPagePrinter(hprinter)

                    for _ in range(self.copias):
                        win32print.WritePrinter(hprinter, datos_bytes)

                    win32print.EndPagePrinter(hprinter)
                finally:
                    win32print.EndDocPrinter(hprinter)
            finally:
                win32print.ClosePrinter(hprinter)

            return {'ok': True, 'error': None, 'metodo': 'win32print', 'impresora': nombre}

        except ImportError:
            # En desarrollo (no Windows), simular éxito y loggear
            logger.warning('win32print no disponible — impresión simulada')
            return {'ok': True, 'error': None, 'metodo': 'simulado'}

        except Exception as e:
            logger.error(f'Error de impresión via win32print: {e}')
            return {'ok': False, 'error': str(e), 'metodo': 'win32print'}

    def _por_puerto(self, datos_bytes: bytes) -> dict:
        """
        Método B: Puerto directo (USB/COM).
        Útil cuando la impresora no está en la cola de Windows.
        Ejemplo de puerto: 'USB001', 'COM3', '\\\\.\\USB#...'
        """
        try:
            # En Windows, se puede abrir el puerto como un archivo
            with open(self.puerto, 'wb') as f:
                f.write(datos_bytes)
            return {'ok': True, 'error': None, 'metodo': 'puerto_directo', 'puerto': self.puerto}

        except Exception as e:
            logger.error(f'Error de impresión por puerto {self.puerto}: {e}')
            return {'ok': False, 'error': str(e), 'metodo': 'puerto_directo'}


# ─── Funciones de alto nivel ──────────────────────────────────────────────────

def imprimir_ticket(datos_ticket: dict) -> dict:
    """
    Función principal. Construye y envía el ticket de venta.
    Llamar desde RegistrarPagoView después de confirmar el pago.

    Args:
        datos_ticket: dict retornado por _datos_ticket()

    Returns:
        {'ok': bool, 'error': str|None, 'metodo': str}
    """
    cfg = settings.IMPRESORA_TERMICA
    if not cfg.get('auto_imprimir', True):
        return {'ok': True, 'error': None, 'metodo': 'desactivado'}

    try:
        builder = TicketBuilder(datos_ticket)
        datos_bytes = builder.build()

        printer = WindowsPrinter()
        resultado = printer.imprimir(datos_bytes)

        if not resultado['ok']:
            logger.error(f"Fallo al imprimir ticket {datos_ticket.get('numero_ticket')}: {resultado['error']}")

        return resultado

    except Exception as e:
        logger.exception(f"Error inesperado en imprimir_ticket: {e}")
        return {'ok': False, 'error': str(e), 'metodo': 'error_interno'}


def imprimir_factura(datos_factura: dict) -> dict:
    """
    Construye y envía una FACTURA. Mismo flujo que imprimir_ticket
    pero usando FacturaBuilder (incluye timbrado, RUC e IVA).
    """
    cfg = settings.IMPRESORA_TERMICA
    if not cfg.get('auto_imprimir', True):
        return {'ok': True, 'error': None, 'metodo': 'desactivado'}
    try:
        builder = FacturaBuilder(datos_factura)
        datos_bytes = builder.build()
        printer = WindowsPrinter()
        resultado = printer.imprimir(datos_bytes)
        if not resultado['ok']:
            logger.error(f"Fallo al imprimir factura {datos_factura.get('factura_numero')}: {resultado['error']}")
        return resultado
    except Exception as e:
        logger.exception(f"Error inesperado en imprimir_factura: {e}")
        return {'ok': False, 'error': str(e), 'metodo': 'error_interno'}


def imprimir_cierre(sesion, resumen: dict) -> dict:
    """
    Imprime el ticket de cierre de sesión de caja.
    Llamar desde CerrarCajaView.
    """
    try:
        builder = TicketCierreBuilder(sesion, resumen)
        datos_bytes = builder.build()

        printer = WindowsPrinter()
        return printer.imprimir(datos_bytes)

    except Exception as e:
        logger.exception(f"Error al imprimir cierre de caja: {e}")
        return {'ok': False, 'error': str(e), 'metodo': 'error_interno'}


def ticket_a_texto(datos_ticket: dict) -> str:
    """
    Versión de texto plano del ticket (sin ESC/POS).
    Útil para guardar en BD, mostrar en pantalla, o enviar por WhatsApp.
    """
    d    = datos_ticket
    cols = settings.IMPRESORA_TERMICA.get('caracteres_linea', 48)
    sep  = '-' * cols

    def g(v): return f'Gs. {int(v):,}'.replace(',', '.')
    def r(i, d_): espacio = cols-len(i)-len(d_); return i + ' '*max(1,espacio) + d_

    lineas = [
        '=' * cols,
        d.get('negocio', '').center(cols),
        '=' * cols,
        r('Ticket:', d.get('numero_ticket', '')),
        r('Fecha:', d.get('fecha', '')),
        r('Cajero:', d.get('cajero', '')),
        r('Pedido:', d.get('pedido_numero', '')),
        r('Cliente:', d.get('cliente', 'Consumidor Final')),
        sep,
        r('PRODUCTO', 'SUBTOTAL'),
        sep,
    ]

    for item in d.get('items', []):
        cant = f"{item['cantidad']:.2f}".rstrip('0').rstrip('.')
        lineas.append(item['descripcion'][:cols])
        lineas.append(r(
            f"  {cant} x {g(item['precio_unit'])}",
            g(item['subtotal'])
        ))

    lineas.append(sep)

    if float(d.get('descuento', 0)) > 0:
        lineas.append(r('Subtotal:', g(d['subtotal'])))
        lineas.append(r('Descuento:', '- ' + g(d['descuento'])))
        lineas.append(sep)

    total_str = f'TOTAL: {g(d.get("total", 0))}'
    lineas.append(total_str.center(cols))
    lineas.append(sep)
    lineas.append(r('Medio de pago:', str(d.get('medio_pago', ''))))

    if d.get('monto_recibido'):
        lineas.append(r('Recibido:', g(d['monto_recibido'])))
    if float(d.get('vuelto', 0)) > 0:
        lineas.append(r('VUELTO:', g(d['vuelto'])))

    lineas += ['=' * cols, d.get('pie', 'Gracias por su compra').center(cols), '']
    return '\n'.join(lineas)
