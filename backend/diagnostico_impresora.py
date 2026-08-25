"""
diagnostico_impresora.py
Diagnóstico de las DOS impresoras del local:

  · FTX FTXP-80W        — térmica de 80 mm, tickets y facturas de mostrador
  · Epson EcoTank L1250 — A4, etiquetas de código de barras
                          (NO imprime facturas: eso sale por su propio equipo)

Ejecutar desde la carpeta backend con el entorno virtual activado:
    python diagnostico_impresora.py

Qué hace:
  1. Lista todas las impresoras disponibles en Windows
  2. Verifica si las configuradas en el .env existen
  3. Chequea si el .pdf tiene el verbo "printto" (lo necesita el modo auto
     de la L1250)
  4. Imprime un ticket de prueba en la térmica
  5. Imprime una hoja de etiquetas de prueba en la L1250
"""
import os
import sys

# La consola de Windows arranca en cp850 (o cp1252 cuando la salida se
# redirige a un archivo) y en ninguna de las dos existen los caracteres de
# recuadro que usa este script. Sin esto, `python diagnostico_impresora.py`
# se cortaba con UnicodeEncodeError en la PRIMERA línea impresa — y peor,
# solo al redirigirlo, que es justo lo que hace alguien cuando quiere mandar
# el resultado por chat para pedir ayuda.
#
# errors='replace' mantiene la codificación real de la consola y reemplaza lo
# que no entra por '?'. Forzar utf-8 acá sería peor: escribiría bytes UTF-8
# en una consola cp850 y saldría todo con acentos rotos.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.conf import settings
from apps.caja.printer import (
    TicketBuilder, WindowsPrinter,
    ticket_a_texto, INIT, CUT_PARTIAL, FEED_LINES, LF,
)

def separador(char='═', n=55):
    print(char * n)

def listar_impresoras():
    """Lista todas las impresoras instaladas en Windows."""
    print('\n▶ Impresoras disponibles en este equipo:\n')
    try:
        import win32print
        impresoras = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
        if not impresoras:
            print('  (ninguna impresora instalada)')
        for i, p in enumerate(impresoras):
            nombre   = p[2]
            servidor = p[1] or 'local'
            default  = ' ← PREDETERMINADA' if nombre == win32print.GetDefaultPrinter() else ''
            print(f'  {i+1}. {nombre} ({servidor}){default}')
        return [p[2] for p in impresoras]
    except ImportError:
        print('  win32print no disponible — ejecutar en Windows con pywin32 instalado.')
        print('  Instalar: pip install pywin32')
        return []

def verificar_configuracion(impresoras_disponibles):
    """Verifica la configuración actual contra las impresoras disponibles."""
    cfg = settings.IMPRESORA_TERMICA
    print('\n▶ Configuración actual (desde .env):\n')

    nombre  = cfg.get('nombre_windows', '')
    puerto  = cfg.get('puerto_directo', '')
    auto    = cfg.get('auto_imprimir', True)
    copias  = cfg.get('copias', 1)
    enc     = cfg.get('encoding', 'cp850')

    print(f'  Nombre Windows:  {nombre or "(no configurado)"}')
    print(f'  Puerto directo:  {puerto or "(no configurado)"}')
    print(f'  Auto-imprimir:   {auto}')
    print(f'  Copias:          {copias}')
    print(f'  Encoding:        {enc}')

    if nombre and impresoras_disponibles:
        if nombre in impresoras_disponibles:
            print(f'\n  ✓ La impresora "{nombre}" está disponible.')
            return True
        else:
            print(f'\n  ✗ La impresora "{nombre}" NO está instalada en este equipo.')
            print(f'    Impresoras disponibles: {", ".join(impresoras_disponibles)}')
            print(f'\n  → Para corregir: en el archivo backend/.env, cambiar:')
            print(f'    IMPRESORA_TERMICA_NOMBRE=<nombre exacto de la lista>')
            return False
    elif puerto:
        print(f'\n  Usando puerto directo: {puerto}')
        return True
    else:
        print('\n  ✗ No hay impresora configurada.')
        print('    En backend/.env, configurar:')
        print('    IMPRESORA_TERMICA_NOMBRE=<nombre exacto de la impresora>')
        return False

def datos_prueba():
    """Datos ficticios para el ticket de prueba."""
    from datetime import datetime
    return {
        'negocio':        'Oga Porã',
        'ruc':            'RUC: 80012345-6',
        'numero_ticket':  'T-PRUEBA-001',
        'fecha':          datetime.now().strftime('%d/%m/%Y %H:%M'),
        'cajero':         'Test Cajero',
        'pedido_numero':  'NP-202505-0001',
        'cliente':        'Cliente de Prueba',
        'items': [
            {
                'descripcion':  'Porcelanato Roma 60x60',
                'detalle':      '60x60 cm — Beige — Mate',
                'cantidad':     4.32,
                'precio_unit':  185000,
                'subtotal':     799200,
            },
            {
                'descripcion':  'Grifería Cocina Cromo',
                'detalle':      'Cromo',
                'cantidad':     1,
                'precio_unit':  285000,
                'subtotal':     285000,
            },
        ],
        'subtotal':       1084200,
        'descuento':      84200,
        'total':          1000000,
        'medio_pago':     'Efectivo',
        'monto_recibido': 1000000,
        'vuelto':         0,
        'pie':            'Gracias por su compra — test@ceramicas.com',
    }

def imprimir_prueba(configurada):
    """Intenta imprimir un ticket de prueba."""
    datos = datos_prueba()

    print('\n▶ Ticket en texto plano (vista previa):\n')
    separador('─', 50)
    print(ticket_a_texto(datos))
    separador('─', 50)

    if not configurada:
        print('\n  (Impresión física omitida — impresora no configurada)')
        return

    respuesta = input('\n¿Imprimir ticket de prueba en la impresora física? (s/N): ').strip().lower()
    if respuesta != 's':
        print('  Impresión cancelada.')
        return

    print('\n▶ Enviando a la impresora...')
    try:
        builder = TicketBuilder(datos)
        bytes_ticket = builder.build()
        printer = WindowsPrinter()
        resultado = printer.imprimir(bytes_ticket)

        if resultado['ok']:
            print(f'  ✓ Ticket enviado correctamente ({resultado["metodo"]})')
        else:
            print(f'  ✗ Error: {resultado["error"]}')
    except Exception as e:
        print(f'  ✗ Error inesperado: {e}')

def prueba_bytes_minimos():
    """Envía el mínimo posible de bytes para verificar la comunicación."""
    respuesta = input('\n¿Enviar prueba de comunicación mínima (solo inicializar + corte)? (s/N): ').strip().lower()
    if respuesta != 's':
        return

    cfg = settings.IMPRESORA_TERMICA
    nombre = cfg.get('nombre_windows', '')
    if not nombre:
        print('  Sin nombre de impresora configurado.')
        return

    try:
        import win32print
        hprinter = win32print.OpenPrinter(nombre)
        hjob = win32print.StartDocPrinter(hprinter, 1, ('Test', None, 'RAW'))
        win32print.StartPagePrinter(hprinter)
        win32print.WritePrinter(hprinter, INIT + b'Test de comunicacion\n' + FEED_LINES(3) + CUT_PARTIAL)
        win32print.EndPagePrinter(hprinter)
        win32print.EndDocPrinter(hprinter)
        win32print.ClosePrinter(hprinter)
        print('  ✓ Prueba mínima enviada exitosamente')
    except Exception as e:
        print(f'  ✗ Error: {e}')

# ─── Epson EcoTank L1250 (A4) ─────────────────────────────────────────────────

def verificar_a4(impresoras_disponibles):
    """Verifica la configuración de la L1250 contra lo instalado en Windows."""
    from apps.caja.impresora_a4 import estado_impresora_a4

    estado = estado_impresora_a4()
    print('\n▶ Configuración actual (desde .env):\n')
    print(f'  Modelo:     {estado["modelo"]}')
    print(f'  Nombre:     {estado["nombre"] or "(sin configurar)"}')
    print(f'  Modo:       {estado["modo"]}'
          + ('  (se imprime desde el navegador)' if estado['modo'] == 'manual'
             else '  (la manda el servidor solo)'))

    if estado['disponible']:
        print('\n  OK — la impresora está instalada en este equipo.')
        return True

    print(f'\n  FALLA — {estado["error"]}')
    print('\n  Para solucionarlo:')
    print('    1. Instalá la L1250 en Panel de control -> Dispositivos e impresoras.')
    print('    2. Copiá el nombre EXACTO que aparece ahí.')
    print('    3. Pegalo en backend\\.env como IMPRESORA_A4_NOMBRE=<nombre>')
    print('    4. Reiniciá el sistema (iniciar.bat).')
    return False


def verificar_handler_pdf():
    """
    Chequea si el .pdf tiene registrado el verbo "printto" en Windows.

    Es lo que necesita IMPRESORA_A4_MODO=auto para mandar el PDF a la cola sin
    que nadie toque nada. Lo instala Adobe Acrobat Reader; el visor de PDF de
    Edge NO lo registra, y sin él el trabajo se pierde en silencio — que es
    justamente el modo de falla más difícil de diagnosticar después.
    """
    print('\n▶ Verbo "printto" para archivos .pdf:\n')
    try:
        import winreg
    except ImportError:
        print('  (no aplica fuera de Windows)')
        return False

    # Cuál es el ProgID que Windows va a usar de verdad. La elección del
    # usuario en "Abrir con" vive en HKCU y le gana a lo que diga HKCR, así
    # que se mira primero; solo si no está se cae al default de la extensión.
    progid = ''
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\CurrentVersion\Explorer'
                r'\FileExts\.pdf\UserChoice') as k:
            progid, _ = winreg.QueryValueEx(k, 'ProgId')
    except OSError:
        pass

    if not progid:
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, '.pdf') as k:
                progid, _ = winreg.QueryValueEx(k, '')
        except OSError:
            progid = ''

    if not progid:
        print('  FALLA — no hay ninguna aplicación asociada a los archivos .pdf.')
        print('    El modo auto no va a funcionar. Dejá IMPRESORA_A4_MODO=manual.')
        return False

    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                            progid + r'\shell\printto\command') as k:
            comando, _ = winreg.QueryValueEx(k, '')
        print(f'  OK — registrado por "{progid}".')
        print(f'    {comando[:100]}')
        print('    El modo auto (IMPRESORA_A4_MODO=auto) puede funcionar.')
        return True
    except OSError:
        print(f'  AVISO — "{progid}" no registra el verbo "printto".')
        print('    Pasa cuando el visor de PDF por defecto es Edge o Chrome, y')
        print('    también cuando quedó registrado un Acrobat ya desinstalado.')
        print('    Opciones:')
        print('      a) Dejar IMPRESORA_A4_MODO=manual (recomendado): se')
        print('         imprime desde el navegador y anda siempre.')
        print('      b) Instalar Adobe Acrobat Reader y ponerlo como visor')
        print('         predeterminado de PDF, y recién ahí usar modo auto.')
        return False


def prueba_a4(configurada):
    """
    Imprime una hoja A4 de prueba con etiquetas de código de barras.

    Sirve para dos cosas a la vez: confirmar que la L1250 recibe trabajos del
    sistema, y verificar con el lector en la mano que los códigos impresos se
    leen. Una etiqueta que sale bien a la vista pero no se escanea es el error
    que más tiempo hace perder.
    """
    if not configurada:
        print('\n  (se saltea la prueba: la impresora no está disponible)')
        return

    respuesta = input('\n¿Imprimir una hoja A4 de etiquetas de prueba? (s/N): ').strip().lower()
    if respuesta != 's':
        return

    from apps.caja.impresora_a4 import etiquetas_pdf, imprimir_pdf
    from apps.productos.codigo_barras import generar_ean_interno

    # Seis etiquetas de prueba: tres con EAN-13 y tres con Code128, que son
    # las dos simbologías que el sistema imprime y el FTX-LC123BH5 lee.
    etiquetas = []
    for i in range(1, 4):
        etiquetas.append({
            'codigo':  generar_ean_interno(i),
            'sku':     f'PRUEBA-EAN-{i}',
            'nombre':  'Etiqueta de prueba (EAN-13 interno)',
            'detalle': 'Escanealo para verificar el lector',
            'precio':  0,
        })
    for i in range(1, 4):
        etiquetas.append({
            'codigo':  f'PRUEBA-CODE128-{i}',
            'sku':     f'PRUEBA-C128-{i}',
            'nombre':  'Etiqueta de prueba (Code128)',
            'detalle': 'Escanealo para verificar el lector',
            'precio':  0,
        })

    pdf = etiquetas_pdf(etiquetas)
    resultado = imprimir_pdf(pdf, titulo='prueba_etiquetas')

    if resultado['ok']:
        print(f'  OK — enviado ({resultado["metodo"]}).')
        if resultado.get('archivo'):
            print(f'    PDF: {resultado["archivo"]}')
        print('    Cuando salga la hoja, pasá el lector por cada código: los')
        print('    seis tienen que leerse. Imprimí a escala 100%, sin "ajustar')
        print('    a la página" — al reescalar, los códigos dejan de leerse.')
    else:
        print(f'  FALLA — {resultado["error"]}')


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    separador()
    print('  Diagnóstico de impresoras — Oga Porã')
    separador()

    impresoras = listar_impresoras()

    print('\n' + '─' * 55)
    print('  1) Térmica FTX FTXP-80W (tickets)')
    print('─' * 55)
    configurada = verificar_configuracion(impresoras)
    imprimir_prueba(configurada)
    prueba_bytes_minimos()

    print('\n' + '─' * 55)
    print('  2) Epson EcoTank L1250 (A4: etiquetas de código de barras)')
    print('─' * 55)
    configurada_a4 = verificar_a4(impresoras)
    verificar_handler_pdf()
    prueba_a4(configurada_a4)

    separador()
    print('\n  Diagnóstico completado.')
    print()
