"""
diagnostico_impresora.py
Diagnóstico de la térmica del local:

  · FTX FTXP-80W — térmica de 80 mm, tickets y facturas de mostrador

Ejecutar desde la carpeta backend con el entorno virtual activado:
    python diagnostico_impresora.py

Qué hace:
  1. Lista todas las impresoras disponibles en Windows
  2. Verifica si la configurada en el .env existe
  3. Imprime un ticket de prueba
  4. Prueba el envío de bytes crudos ESC/POS
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
    ticket_a_texto, INIT, CUT_PARTIAL, FEED_LINES,
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
            print('\n  → Para corregir: en el archivo backend/.env, cambiar:')
            print('    IMPRESORA_TERMICA_NOMBRE=<nombre exacto de la lista>')
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
        win32print.StartDocPrinter(hprinter, 1, ('Test', None, 'RAW'))
        win32print.StartPagePrinter(hprinter)
        win32print.WritePrinter(hprinter, INIT + b'Test de comunicacion\n' + FEED_LINES(3) + CUT_PARTIAL)
        win32print.EndPagePrinter(hprinter)
        win32print.EndDocPrinter(hprinter)
        win32print.ClosePrinter(hprinter)
        print('  ✓ Prueba mínima enviada exitosamente')
    except Exception as e:
        print(f'  ✗ Error: {e}')

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    separador()
    print('  Diagnóstico de impresora — Oga Porã')
    separador()

    impresoras = listar_impresoras()

    print('\n' + '─' * 55)
    print('  Térmica FTX FTXP-80W (tickets)')
    print('─' * 55)
    configurada = verificar_configuracion(impresoras)
    imprimir_prueba(configurada)
    prueba_bytes_minimos()

    separador()
    print('\n  Diagnóstico completado.')
    print()
