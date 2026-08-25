"""
Genera (y opcionalmente manda a imprimir) la planilla A4 de etiquetas con
código de barras, para pegar en la mercadería.

Es la contraparte física del lector FTX-LC123BH5: sin etiqueta pegada no hay
nada que escanear. Se corre después de `asignar_codigos_barras`.

Uso:
    python manage.py imprimir_etiquetas --sin-imprimir
        Deja el PDF en backend\\media\\etiquetas\\ para revisarlo o mandarlo
        a imprimir a mano. Es lo recomendado la primera vez.

    python manage.py imprimir_etiquetas --producto POR-001
        Solo las variantes de ese producto.

    python manage.py imprimir_etiquetas --desde 7
        Saltea las primeras 7 celdas de la primera hoja, para reusar una
        planilla a la que ya se le arrancaron etiquetas.

    python manage.py imprimir_etiquetas --imprimir
        La manda directo a la Epson L1250. Requiere IMPRESORA_A4_MODO=auto y
        correrlo en la PC que tiene la impresora.
"""
import os
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.caja import impresora_a4
from apps.productos.models import Variante


class Command(BaseCommand):
    help = 'Arma la planilla A4 de etiquetas con código de barras (Epson L1250).'

    def add_arguments(self, parser):
        parser.add_argument('--producto', type=str, default='',
                            help='Código de producto a etiquetar (ej: POR-001).')
        parser.add_argument('--sku', type=str, default='',
                            help='SKU exacto de una sola variante.')
        parser.add_argument('--desde', type=int, default=0,
                            help='Celdas a saltear en la primera hoja.')
        parser.add_argument('--imprimir', action='store_true',
                            help='Mandar directo a la L1250 en vez de guardar el PDF.')
        parser.add_argument('--sin-imprimir', action='store_true',
                            help='Solo guardar el PDF (default).')

    def handle(self, *args, **opciones):
        qs = (Variante.objects
              .select_related('producto', 'acabado')
              .filter(activa=True, producto__activo=True)
              .exclude(codigo_barras__isnull=True))

        if opciones['producto']:
            qs = qs.filter(producto__codigo__iexact=opciones['producto'].strip())
        if opciones['sku']:
            qs = qs.filter(sku__iexact=opciones['sku'].strip())

        variantes = list(qs.order_by('producto__codigo', 'sku')[:500])

        if not variantes:
            self.stderr.write(self.style.ERROR(
                'Ninguna variante con código de barras coincide con el filtro.\n'
                'Si el catálogo todavía no tiene códigos, corré primero:\n'
                '    python manage.py asignar_codigos_barras'))
            return

        etiquetas = [{
            'codigo':  v.codigo_barras,
            'sku':     v.sku,
            'nombre':  v.producto.nombre,
            'detalle': ' · '.join(p for p in [v.dimension_display, v.color,
                                              v.acabado.nombre if v.acabado else ''] if p),
            'precio':  v.precio_venta,
        } for v in variantes]

        pdf = impresora_a4.etiquetas_pdf(etiquetas, desde_posicion=opciones['desde'])

        por_hoja = impresora_a4.ETIQUETAS_COLUMNAS * impresora_a4.ETIQUETAS_FILAS
        hojas = -(-(len(etiquetas) + opciones['desde']) // por_hoja)
        self.stdout.write(
            f'{len(etiquetas)} etiqueta(s) en {hojas} hoja(s) A4 '
            f'({impresora_a4.ETIQUETAS_COLUMNAS}×{impresora_a4.ETIQUETAS_FILAS} de '
            f'{impresora_a4.ETIQUETA_ANCHO_MM}×{impresora_a4.ETIQUETA_ALTO_MM} mm).')

        if opciones['imprimir'] and not opciones['sin_imprimir']:
            resultado = impresora_a4.imprimir_pdf(pdf, titulo='etiquetas')
            if resultado['ok']:
                self.stdout.write(self.style.SUCCESS(
                    f'Enviado a la impresora ({resultado["metodo"]}).'))
            else:
                self.stderr.write(self.style.ERROR(
                    f'No se pudo imprimir: {resultado["error"]}'))
            return

        carpeta = os.path.join(settings.MEDIA_ROOT, 'etiquetas')
        os.makedirs(carpeta, exist_ok=True)
        ruta = os.path.join(
            carpeta, f'etiquetas_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf')
        with open(ruta, 'wb') as f:
            f.write(pdf)

        self.stdout.write(self.style.SUCCESS(f'PDF guardado en:\n    {ruta}'))
        self.stdout.write(
            'Abrilo, revisá que la grilla coincida con la planilla '
            'autoadhesiva que compraron, e imprimí a escala 100% '
            '(NO "ajustar a la página": eso desalinea las etiquetas).')
