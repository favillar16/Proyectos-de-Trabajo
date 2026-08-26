"""
Identidad global para el sync bidireccional notebook ↔ servidor.

En tres pasos porque `uid` es único y las filas ya existen: primero se agrega
sin la restricción, después se le da un UUID distinto a cada fila, y recién
entonces se marca único. Agregarlo único de una vez le pone el MISMO valor a
todas las filas existentes y la migración muere en el índice.
"""
import uuid

import django.utils.timezone
from django.db import migrations, models

MODELOS = [
    'Categoria',
    'Marca',
    'Acabado',
    'Producto',
    'Variante',
    'ImagenProducto',
    'ImagenVariante',
]


def asignar_uids(apps, schema_editor):
    """Un UUID propio por fila. Sin esto todas comparten el default."""
    for etiqueta in MODELOS:
        modelo = apps.get_model('productos', etiqueta)
        # .iterator() para no traer el catálogo entero a memoria de una.
        for fila in modelo.objects.filter(uid__isnull=True).iterator(chunk_size=500):
            modelo.objects.filter(pk=fila.pk).update(uid=uuid.uuid4())


def borrar_uids(apps, schema_editor):
    """Marcha atrás: los uid se van con las columnas, no hay nada que deshacer."""


class Migration(migrations.Migration):

    dependencies = [
        ('productos', '0005_variante_codigo_barras'),
    ]

    operations = (
        # 1 — las columnas, con uid todavía sin restricción de unicidad
        [
            migrations.AddField(
                model_name=m.lower(),
                name='uid',
                field=models.UUIDField(
                    null=True, editable=False, db_index=True,
                    help_text='Identidad de la fila entre equipos. La asigna quien la crea.',
                ),
            )
            for m in MODELOS
        ]
        + [
            migrations.AddField(
                model_name=m.lower(),
                name='actualizado_en',
                field=models.DateTimeField(
                    default=django.utils.timezone.now, db_index=True,
                    help_text='Hora del equipo que hizo el último cambio. Decide conflictos.',
                ),
            )
            for m in MODELOS
        ]
        + [
            migrations.AddField(
                model_name=m.lower(),
                name='nodo_origen',
                field=models.CharField(
                    max_length=60, blank=True, default='',
                    help_text='Equipo donde se hizo el último cambio.',
                ),
            )
            for m in MODELOS
        ]
        # 2 — un uid distinto por fila
        + [migrations.RunPython(asignar_uids, borrar_uids)]
        # 3 — recién ahora, único y obligatorio
        + [
            migrations.AlterField(
                model_name=m.lower(),
                name='uid',
                field=models.UUIDField(
                    default=uuid.uuid4, unique=True, editable=False, db_index=True,
                    help_text='Identidad de la fila entre equipos. La asigna quien la crea.',
                ),
            )
            for m in MODELOS
        ]
    )
