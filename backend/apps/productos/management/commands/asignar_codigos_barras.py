"""
Asigna un código de barras interno a las variantes que no tienen uno.

El lector FTX-LC123BH5 sirve de poco si el catálogo no tiene códigos: la
mercadería del rubro (sanitarios, griferías, accesorios) llega en gran parte
sin EAN impreso. Este comando le da a cada variante un EAN-13 con prefijo
GS1 de uso interno, que después se imprime en etiqueta con la Epson L1250
(`python manage.py imprimir_etiquetas`).

No pisa nunca un código existente: si la caja ya trae el EAN de fábrica, ese
manda. Para reasignar hay que borrar el código a mano primero.

Uso:
    python manage.py asignar_codigos_barras --simular      # muestra qué haría
    python manage.py asignar_codigos_barras                # asigna
    python manage.py asignar_codigos_barras --producto POR-001
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.productos.models import Variante
from apps.productos.codigo_barras import generar_ean_interno, es_interno


class Command(BaseCommand):
    help = 'Asigna un EAN-13 interno a las variantes que no tienen código de barras.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--simular', action='store_true',
            help='Muestra qué códigos asignaría, sin escribir en la base.')
        parser.add_argument(
            '--producto', type=str, default='',
            help='Limita la asignación a un código de producto (ej: POR-001).')
        parser.add_argument(
            '--incluir-inactivas', action='store_true',
            help='También asigna a variantes dadas de baja.')

    def handle(self, *args, **opciones):
        simular  = opciones['simular']
        producto = (opciones['producto'] or '').strip()

        # Sin codigo la variante guarda NULL, no cadena vacia (ver
        # Variante.save()): filtrar por '' no traeria ninguna.
        qs = Variante.objects.select_related('producto').filter(
            codigo_barras__isnull=True)
        if not opciones['incluir_inactivas']:
            qs = qs.filter(activa=True, producto__activo=True)
        if producto:
            qs = qs.filter(producto__codigo__iexact=producto)
        qs = qs.order_by('producto__codigo', 'sku')

        total = qs.count()
        if total == 0:
            ya = Variante.objects.exclude(codigo_barras__isnull=True).count()
            self.stdout.write(self.style.SUCCESS(
                f'No hay variantes sin código de barras. '
                f'Ya tienen código: {ya}.'))
            return

        self.stdout.write(
            f'{total} variante(s) sin código de barras'
            + (f' (producto {producto})' if producto else '') + ':')
        self.stdout.write('')

        asignados = 0
        with transaction.atomic():
            for v in qs:
                codigo = generar_ean_interno(v.id)
                self.stdout.write(
                    f'  {codigo}  {v.sku}  —  {v.producto.nombre}')
                if not simular:
                    v.codigo_barras = codigo
                    v.save(update_fields=['codigo_barras'])
                    asignados += 1

            if simular:
                # El rollback deja la base intacta aunque más arriba se haya
                # tocado algo: es lo que hace que --simular sea confiable y no
                # dependa de que el bucle esté bien escrito.
                transaction.set_rollback(True)

        self.stdout.write('')
        if simular:
            self.stdout.write(self.style.WARNING(
                f'Simulación: no se escribió nada. '
                f'Volvé a correrlo sin --simular para asignar los {total}.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'{asignados} código(s) asignado(s).'))
            internos = sum(1 for c in Variante.objects
                           .exclude(codigo_barras__isnull=True)
                           .values_list('codigo_barras', flat=True)
                           if es_interno(c))
            self.stdout.write(
                f'Del total del catálogo, {internos} son códigos internos '
                f'(prefijo 200) y hay que imprimirles etiqueta:')
            self.stdout.write(
                '    python manage.py imprimir_etiquetas --sin-imprimir')
