"""
Vincula las fotos de la carpeta "Referencias de Productos" (raíz del repo)
con las Variantes/Productos cargados por cargar_referencias_productos.
Ver data_carga/mapeo_imagenes.csv para el emparejamiento archivo -> producto.

Uso: python manage.py vincular_imagenes_referencia
     python manage.py vincular_imagenes_referencia --dry-run

Idempotente: si el producto ya tiene una imagen con ese nombre de archivo
original, no la vuelve a subir.
"""
import re
from pathlib import Path

import csv

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from apps.productos.models import Producto, ImagenProducto

RUTA_MAPEO = Path(settings.BASE_DIR) / 'data_carga' / 'mapeo_imagenes.csv'
CARPETA_REFERENCIAS = Path(settings.BASE_DIR).parent / 'Referencias de Productos'


class Command(BaseCommand):
    help = 'Vincula las fotos de "Referencias de Productos" con sus Productos ya cargados'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        if not RUTA_MAPEO.exists():
            raise CommandError(f'No se encontró {RUTA_MAPEO}')
        if not CARPETA_REFERENCIAS.exists():
            raise CommandError(f'No se encontró la carpeta {CARPETA_REFERENCIAS}')

        dry = options['dry_run']
        vinculadas, ya_existian, faltantes = 0, 0, 0

        with open(RUTA_MAPEO, encoding='utf-8') as f:
            filas = list(csv.DictReader(f, delimiter=';'))

        # Para marcar es_principal solo en la primera imagen de cada producto
        principal_asignada = set(
            ImagenProducto.objects.filter(es_principal=True)
            .values_list('producto__codigo', flat=True)
        )

        for fila in filas:
            archivo = fila['archivo'].strip()
            codigo_prod = fila['producto_codigo'].strip()
            ruta_imagen = CARPETA_REFERENCIAS / archivo

            if not ruta_imagen.exists():
                self.stdout.write(self.style.ERROR(f'  ! no existe el archivo: {archivo}'))
                faltantes += 1
                continue

            try:
                producto = Producto.objects.get(codigo=codigo_prod)
            except Producto.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'  ! no existe el producto {codigo_prod} ({archivo})'))
                faltantes += 1
                continue

            # Django limpia paréntesis/espacios del nombre al guardar el archivo
            # (ej. "WA0062(1).jpg" -> "WA00621.jpg"), así que comparamos solo lo
            # alfanumérico para no re-subir la misma foto en una segunda corrida.
            clave = re.sub(r'[^a-zA-Z0-9]', '', Path(archivo).stem)
            ya_tiene = any(
                clave in re.sub(r'[^a-zA-Z0-9]', '', Path(img.imagen.name).stem)
                for img in ImagenProducto.objects.filter(producto=producto)
            )
            if ya_tiene:
                self.stdout.write(f'  = ya vinculada: {archivo} -> {codigo_prod}')
                ya_existian += 1
                continue

            if dry:
                self.stdout.write(f'  + vincularía: {archivo} -> {codigo_prod}')
                vinculadas += 1
                continue

            es_principal = codigo_prod not in principal_asignada
            with open(ruta_imagen, 'rb') as fh:
                imagen = ImagenProducto(
                    producto=producto,
                    es_principal=es_principal,
                    titulo=fila.get('notas', ''),
                )
                imagen.imagen.save(archivo, File(fh), save=True)

            if es_principal:
                principal_asignada.add(codigo_prod)

            self.stdout.write(self.style.SUCCESS(
                f'  + vinculada: {archivo} -> {codigo_prod} ({"principal" if es_principal else "galería"})'
            ))
            vinculadas += 1

        self.stdout.write('')
        etiqueta = 'DRY-RUN' if dry else 'Listo'
        self.stdout.write(self.style.SUCCESS(
            f'{etiqueta}: {vinculadas} vinculadas, {ya_existian} ya existían, {faltantes} con error.'
        ))
