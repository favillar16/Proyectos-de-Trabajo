"""
Comando para sembrar las subcategorías de sanitarios/accesorios definidas en
docs/Listado de Productos.docx (bachas, piletas, grifería, duchas, etc.).
Uso: python manage.py seed_categorias_producto
Idempotente: no duplica si ya existen (busca por 'tipo').
"""
from django.core.management.base import BaseCommand
from apps.productos.models import Categoria


# (nombre visible, tipo, orden)
CATEGORIAS_BASE = [
    ('Bachas',                        'bacha',           10),
    ('Piletas para cocina',           'pileta_cocina',   11),
    ('Piletas para ropa',             'pileta_ropa',     12),
    ('Grifería',                      'griferia',        13),
    ('Duchas',                        'ducha',           14),
    ('Inodoros',                      'inodoro',         15),
    ('Migitorios',                    'migitorio',       16),
    ('Bidés',                         'bide',            17),
    ('Duchas higiénicas',             'ducha_higienica', 18),
    ('Cisternas',                     'cisterna',        19),
    ('Tapas para inodoro',            'tapa_inodoro',    20),
    ('Nichos para baño',              'nicho_bano',      21),
    ('Espejos',                       'espejo',          22),
    ('Adhesivos',                     'adhesivo',        23),
    ('Pastinas',                      'pastina',         24),
    ('Plomería',                      'plomeria',        25),
    ('Tiras de fondo con tarugo',     'tira_fondo',      26),
]


class Command(BaseCommand):
    help = 'Crea las subcategorías de productos (sanitarios/accesorios) si no existen'

    def handle(self, *args, **options):
        creadas = 0
        for nombre, tipo, orden in CATEGORIAS_BASE:
            obj, created = Categoria.objects.get_or_create(
                tipo=tipo,
                defaults={'nombre': nombre, 'orden': orden, 'activa': True},
            )
            if created:
                creadas += 1
                self.stdout.write(f'  + {nombre} ({tipo})')
        if creadas:
            self.stdout.write(self.style.SUCCESS(f'{creadas} categorías creadas.'))
        else:
            self.stdout.write('Todas las categorías ya existían.')
