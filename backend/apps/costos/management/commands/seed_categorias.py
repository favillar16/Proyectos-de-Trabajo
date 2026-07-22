"""
Comando para sembrar las categorías de gasto base.
Uso: python manage.py seed_categorias
Idempotente: no duplica si ya existen.
"""
from django.core.management.base import BaseCommand
from apps.costos.models import CategoriaGasto


CATEGORIAS_BASE = [
    ('Pago a proveedor',   'proveedor', 1),
    ('Salario',            'salario',   2),
    ('Alquiler',           'servicio',  3),
    ('Servicios (luz, agua, internet)', 'servicio', 4),
    ('Impuestos',          'otro',      5),
    ('Mantenimiento',      'otro',      6),
    ('Otros gastos',       'otro',      7),
]


class Command(BaseCommand):
    help = 'Crea las categorías de gasto base si no existen'

    def handle(self, *args, **options):
        creadas = 0
        for nombre, tipo, orden in CATEGORIAS_BASE:
            obj, created = CategoriaGasto.objects.get_or_create(
                nombre=nombre,
                defaults={'tipo': tipo, 'orden': orden, 'activa': True},
            )
            if created:
                creadas += 1
                self.stdout.write(f'  + {nombre} ({tipo})')
        if creadas:
            self.stdout.write(self.style.SUCCESS(f'{creadas} categorías creadas.'))
        else:
            self.stdout.write('Todas las categorías ya existían.')