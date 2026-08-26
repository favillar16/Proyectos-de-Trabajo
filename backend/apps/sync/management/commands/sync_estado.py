"""
Diagnóstico de la sincronización.

    python manage.py sync_estado
    python manage.py sync_estado --conflictos

Es lo primero que hay que mirar cuando alguien dice "cargué algo en la notebook
y no aparece en el local".
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.sync.models import CambioSync, ConflictoSync, EstadoSync


class Command(BaseCommand):
    help = 'Muestra el estado de la sincronización de este equipo.'

    def add_arguments(self, parser):
        parser.add_argument('--conflictos', action='store_true',
                            help='Detalle de los conflictos sin revisar.')
        parser.add_argument('--limite', type=int, default=20)

    def handle(self, *args, **opciones):
        self.stdout.write(self.style.MIGRATE_HEADING('Este equipo'))
        self.stdout.write(f'  nombre : {settings.NODO["nombre"]}')
        self.stdout.write(f'  rol    : {settings.NODO["rol"]}')
        self.stdout.write(f'  token  : {"configurado" if settings.SYNC["token"] else "FALTA (sync deshabilitado)"}')

        pendientes = CambioSync.objects.filter(empujado_en__isnull=True)
        self.stdout.write(self.style.MIGRATE_HEADING('\nCambios'))
        self.stdout.write(f'  sin mandar : {pendientes.count()}')
        self.stdout.write(f'  ya mandados: {CambioSync.objects.filter(empujado_en__isnull=False).count()}')

        if pendientes.exists():
            self.stdout.write('  el más viejo sin mandar: '
                              f'{pendientes.order_by("momento").first().momento:%d/%m/%Y %H:%M}')

        sin_ver = ConflictoSync.objects.filter(revisado=False)
        estilo = self.style.WARNING if sin_ver.exists() else self.style.SUCCESS
        self.stdout.write(self.style.MIGRATE_HEADING('\nConflictos'))
        self.stdout.write(estilo(f'  sin revisar: {sin_ver.count()}'))

        nodos = EstadoSync.objects.all()
        if nodos:
            self.stdout.write(self.style.MIGRATE_HEADING('\nÚltima corrida por nodo'))
            for e in nodos:
                cuando = f'{e.ultimo_exito:%d/%m/%Y %H:%M}' if e.ultimo_exito else 'nunca'
                self.stdout.write(f'  {e.nodo}: {cuando} — {e.detalle or "sin detalle"}')

        if opciones['conflictos'] and sin_ver.exists():
            self.stdout.write(self.style.MIGRATE_HEADING('\nDetalle de conflictos'))
            for c in sin_ver.order_by('-registrado_en')[:opciones['limite']]:
                self.stdout.write(f'\n  {c.modelo} {c.uid}')
                self.stdout.write(f'    motivo : {c.get_motivo_display()}')
                self.stdout.write(f'    detalle: {c.detalle}')
                self.stdout.write(f'    de     : {c.nodo_origen}')
                for campo in ('nombre', 'precio_base', 'codigo'):
                    if campo in c.datos_recibidos or campo in c.datos_locales:
                        self.stdout.write(
                            f'    {campo}: llegó "{c.datos_recibidos.get(campo)}" / '
                            f'acá "{c.datos_locales.get(campo)}"')
