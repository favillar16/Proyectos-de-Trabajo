"""
Carga cantidades de stock sobre variantes identificadas por su `uid` de sync.

Por qué por `uid` y no por SKU: cuando una variante viaja de un nodo al otro,
`apps/sync/conciliacion.py` le **regenera** el SKU si el que traía ya estaba en
uso del lado que la recibe (está en `CAMPOS_REGENERABLES`). Así que después de
un empuje el SKU de acá y el de allá no coinciden, y el único identificador
estable entre los dos equipos es el `uid`.

De dónde sale el archivo: lo genera la notebook con las cantidades que cargó a
mano antes de que el sync existiera. El stock no viaja por el sync —es del
servidor por diseño, ver docs/sync_bidireccional.md— así que esas cantidades
necesitan este puente de una sola vez.

    python manage.py cargar_stock_por_uid --archivo data_carga/stock_31_notebook.csv --dry-run
    python manage.py cargar_stock_por_uid --archivo data_carga/stock_31_notebook.csv

Idempotente: si la variante ya tiene stock distinto de cero, la fila se informa
y se saltea. Repetir el comando no infla las cantidades.

Formato del CSV (separador ';'):
    uid_variante;codigo_producto;nombre_producto;sku_notebook;cantidad
"""
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.inventario.models import MovimientoStock, Stock
from apps.productos.models import Variante
from apps.usuarios.models import Usuario

RUTA_DEFAULT = Path(settings.BASE_DIR) / 'data_carga' / 'stock_31_notebook.csv'


class Command(BaseCommand):
    help = 'Carga stock sobre variantes identificadas por uid (puente notebook → servidor)'

    def add_arguments(self, parser):
        parser.add_argument('--archivo', default=str(RUTA_DEFAULT))
        parser.add_argument(
            '--usuario', default='',
            help='Username que queda como responsable del movimiento. '
                 'Por defecto, el primer admin activo.')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opciones):
        ruta = Path(opciones['archivo'])
        if not ruta.is_absolute():
            ruta = Path(settings.BASE_DIR) / ruta
        if not ruta.exists():
            raise CommandError(f'No se encontró {ruta}')

        dry = opciones['dry_run']

        if opciones['usuario']:
            usuario = Usuario.objects.filter(username=opciones['usuario']).first()
            if usuario is None:
                raise CommandError(f'No existe el usuario {opciones["usuario"]!r}')
        else:
            usuario = Usuario.objects.filter(rol='admin', activo=True).order_by('id').first()
            if usuario is None:
                raise CommandError('No hay ningún admin activo; pasar --usuario.')

        self.stdout.write(f'Responsable del movimiento: {usuario.username}')

        with open(ruta, encoding='utf-8-sig') as f:
            filas = list(csv.DictReader(f, delimiter=';'))

        cargadas = salteadas = faltantes = 0

        with transaction.atomic():
            for n, fila in enumerate(filas, start=2):
                uid = (fila.get('uid_variante') or '').strip()
                etiqueta = '%s %s' % (fila.get('codigo_producto', '?'),
                                      (fila.get('nombre_producto') or '')[:40])

                try:
                    cantidad = Decimal(str(fila.get('cantidad', '')).strip())
                except (InvalidOperation, TypeError):
                    self.stdout.write(self.style.ERROR(
                        f'  ! línea {n}: cantidad inválida — {etiqueta}'))
                    faltantes += 1
                    continue

                if cantidad <= 0:
                    self.stdout.write(f'  = línea {n}: cantidad 0, se saltea — {etiqueta}')
                    salteadas += 1
                    continue

                variante = Variante.objects.filter(uid=uid).first()
                if variante is None:
                    self.stdout.write(self.style.ERROR(
                        f'  ! no existe acá la variante {uid} — {etiqueta}'))
                    faltantes += 1
                    continue

                stock = Stock.objects.filter(variante=variante).first()
                if stock is None:
                    self.stdout.write(self.style.ERROR(
                        f'  ! la variante {variante.sku} no tiene fila de stock — {etiqueta}'))
                    faltantes += 1
                    continue

                if stock.cantidad:
                    self.stdout.write(
                        f'  = ya tiene {stock.cantidad}, se saltea — {variante.sku} {etiqueta}')
                    salteadas += 1
                    continue

                if dry:
                    self.stdout.write(
                        f'  + cargaría {cantidad} a {variante.sku} — {etiqueta}')
                    cargadas += 1
                    continue

                stock.registrar_movimiento(
                    tipo=MovimientoStock.TIPO_ENTRADA,
                    cantidad=cantidad,
                    usuario=usuario,
                    referencia_tipo='carga_inicial_notebook',
                    observaciones='Cantidad cargada a mano en la notebook antes del sync.',
                )
                self.stdout.write(self.style.SUCCESS(
                    f'  + {cantidad} → {variante.sku} — {etiqueta}'))
                cargadas += 1

            if dry:
                transaction.set_rollback(True)

        etiqueta_final = 'DRY-RUN' if dry else 'Listo'
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'{etiqueta_final}: {cargadas} cargadas, {salteadas} salteadas, '
            f'{faltantes} con error.'))
