"""
Carga el catálogo real transcripto desde las facturas de compra y fotos de
referencia de la carpeta "Referencias de Productos" (ver
data_carga/referencias_productos.csv).

Uso: python manage.py cargar_referencias_productos
     python manage.py cargar_referencias_productos --archivo otra_ruta.csv
     python manage.py cargar_referencias_productos --dry-run

Cada fila del CSV se convierte en un Producto + una Variante (la variante
lleva el color/dimensión propios de esa fila; no se agrupan varios colores
bajo un mismo Producto porque el proveedor ya factura cada color como un
código de compra distinto).

Idempotente: no duplica si el Producto (por nombre) ya existe. Filas sin
precio_base se listan pero no se cargan (el modelo exige precio_base > 0);
quedan marcadas "PENDIENTE" en el CSV para completar antes de reintentar.

Las imágenes de la carpeta "Referencias de Productos" NO se asocian acá:
el código del proveedor está sobreimpreso en el píxel de la foto, no en el
nombre de archivo, así que emparejar cada foto con su Variante requiere un
vistazo humano (rápido de hacer desde la pantalla de Productos, subiendo
la imagen a la variante correspondiente).
"""
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.productos.models import Categoria, Marca, Producto, Variante
from apps.inventario.models import Stock, MovimientoStock
from apps.usuarios.models import Usuario

RUTA_DEFAULT = Path(settings.BASE_DIR) / 'data_carga' / 'referencias_productos.csv'

NOMBRE_CATEGORIA = {
    'piso': 'Pisos',
    'porcelanato': 'Porcelanatos',
    'ceramica': 'Cerámicas',
    'sanitario': 'Sanitarios',
    'accesorio_bano': 'Accesorios de Baño',
    'cocina': 'Artículos de Cocina',
    'otro': 'Otros',
}


def _dec(valor):
    valor = (valor or '').strip()
    if not valor:
        return None
    try:
        return Decimal(valor)
    except InvalidOperation:
        return None


class Command(BaseCommand):
    help = 'Carga el catálogo transcripto de facturas/fotos en data_carga/referencias_productos.csv'

    def add_arguments(self, parser):
        parser.add_argument('--archivo', default=str(RUTA_DEFAULT),
                             help='Ruta del CSV a cargar (default: data_carga/referencias_productos.csv)')
        parser.add_argument('--dry-run', action='store_true',
                             help='Solo muestra qué haría, no escribe nada en la base')

    def handle(self, *args, **options):
        ruta = Path(options['archivo'])
        if not ruta.exists():
            raise CommandError(f'No se encontró el archivo {ruta}')

        usuario = Usuario.objects.filter(rol=Usuario.ROL_ADMIN, activo=True).first()
        if not usuario:
            raise CommandError(
                'No hay ningún usuario admin activo para registrar el movimiento de stock inicial. '
                'Crear uno con createsuperuser antes de correr este comando.'
            )

        dry = options['dry_run']
        creados, omitidos, existentes = 0, 0, 0

        with open(ruta, encoding='utf-8') as f:
            filas = list(csv.DictReader(f, delimiter=';'))

        for fila in filas:
            nombre = fila['nombre'].strip()
            precio_costo = _dec(fila.get('precio_costo'))
            precio_base = _dec(fila.get('precio_base'))

            if not precio_base:
                self.stdout.write(self.style.WARNING(
                    f'  – omitido (sin precio_base): [{fila["codigo_prov"]}] {nombre}'
                ))
                omitidos += 1
                continue

            if Producto.objects.filter(nombre=nombre).exists():
                self.stdout.write(f'  = ya existe: {nombre}')
                existentes += 1
                continue

            if dry:
                self.stdout.write(f'  + crearía: [{fila["codigo_prov"]}] {nombre}')
                creados += 1
                continue

            with transaction.atomic():
                categoria, _ = Categoria.objects.get_or_create(
                    tipo=fila['categoria_tipo'],
                    defaults={'nombre': NOMBRE_CATEGORIA.get(fila['categoria_tipo'], fila['categoria_tipo'].title())},
                )

                marca = None
                nombre_marca = (fila.get('marca') or '').strip()
                if nombre_marca:
                    marca, _ = Marca.objects.get_or_create(nombre=nombre_marca)

                unidad = fila['unidad_venta'].strip() or Producto.UNIDAD_PIEZA

                producto = Producto.objects.create(
                    nombre=nombre,
                    categoria=categoria,
                    marca=marca,
                    precio_base=precio_base,
                    precio_costo=precio_costo,
                    unidad_venta=unidad,
                    notas_internas=(
                        f"Factura/origen: {fila.get('factura','')} · código proveedor: {fila.get('codigo_prov','')}. "
                        f"{fila.get('notas','')}"
                    ).strip(),
                )

                variante = Variante.objects.create(
                    producto=producto,
                    color=(fila.get('color') or '').strip(),
                    largo_cm=_dec(fila.get('largo_cm')),
                    ancho_cm=_dec(fila.get('ancho_cm')),
                    m2_por_caja=_dec(fila.get('m2_por_caja')),
                )

                cantidad = _dec(fila.get('cantidad'))
                if cantidad and cantidad > 0:
                    stock = Stock.objects.get(variante=variante)
                    stock.registrar_movimiento(
                        tipo=MovimientoStock.TIPO_ENTRADA,
                        cantidad=cantidad,
                        usuario=usuario,
                        referencia_tipo='carga_inicial',
                        observaciones=f"Carga inicial — factura {fila.get('factura','')} — código {fila.get('codigo_prov','')}",
                    )

                self.stdout.write(self.style.SUCCESS(
                    f'  + creado: [{producto.codigo}] {nombre} — SKU {variante.sku} — stock {cantidad or 0}'
                ))
                creados += 1

        self.stdout.write('')
        if dry:
            self.stdout.write(self.style.WARNING(f'DRY-RUN: {creados} se crearían, {existentes} ya existen, {omitidos} omitidos por falta de precio.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'{creados} productos creados, {existentes} ya existían, {omitidos} omitidos por falta de precio_base.'))
            self.stdout.write(
                'Recordatorio: las fotos de "Referencias de Productos" todavía no están vinculadas '
                'a estas variantes — subirlas manualmente desde la pantalla de Productos, comparando '
                'el código/tamaño impreso en cada foto con el código de proveedor guardado en "notas internas".'
            )
