"""
Compara el catálogo de este equipo con el del servidor y, si se pide, marca
las diferencias para que el próximo empuje se las lleve.

    python manage.py sync_comparar --servidor ogapora.local
    python manage.py sync_comparar --servidor ogapora.local --marcar

**Por qué hace falta.** El registro de cambios solo tiene lo que pasó *desde
que el sync está instalado*. Todo lo que se editó en la notebook antes de eso
—por ejemplo las correcciones de precio del 25/08/2026— es invisible para el
sync, y el primer `pg_dump` desde el servidor las pisa sin avisar. Que es
exactamente lo que ya pasó una vez (`docs/traspaso_pendientes.md`).

Este comando es el puente de una sola vez entre "antes" y "después": encuentra
esas diferencias viejas comparando fila por fila, y con `--marcar` las anota en
el registro para que viajen como cualquier otro cambio.

Solo mira el catálogo. Stock, ventas y caja son del servidor y no se comparan.
"""
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.sync.cliente import ErrorDeNodo, pedir_json
from apps.sync.models import CambioSync
from apps.sync.registro import MODELOS_BIDIRECCIONALES
from apps.sync.serializacion import modelo_de, serializar

POR_PAGINA = 200

# Campos que difieren siempre y no significan nada: los genera cada base.
IGNORAR = {'slug'}


class Command(BaseCommand):
    help = 'Compara el catálogo local con el del servidor y marca las diferencias.'

    def add_arguments(self, parser):
        parser.add_argument('--servidor', required=True)
        parser.add_argument('--puerto', type=int, default=8000)
        parser.add_argument('--token', default='')
        parser.add_argument('--marcar', action='store_true',
                            help='Anota las diferencias para que se manden en el próximo empuje.')
        parser.add_argument('--modelo', default='',
                            help='Comparar solo un modelo (ej: productos.Producto).')
        parser.add_argument('--limite-detalle', type=int, default=40,
                            help='Cuántas diferencias mostrar en pantalla.')

    def handle(self, *args, **opciones):
        token = opciones['token'] or settings.SYNC['token']
        if not token:
            raise CommandError('Falta el token. Poner SYNC_TOKEN en el .env o pasar --token.')

        base = f'http://{opciones["servidor"]}:{opciones["puerto"]}/api/v1'

        try:
            identidad = pedir_json(f'{base}/salud/', token)
        except ErrorDeNodo as e:
            raise CommandError(f'No se pudo contactar al servidor: {e}')
        if identidad.get('rol') != 'servidor':
            raise CommandError(f'{opciones["servidor"]} dice ser "{identidad.get("rol")}", '
                               f'no el servidor.')

        modelos = [opciones['modelo']] if opciones['modelo'] else MODELOS_BIDIRECCIONALES
        for et in modelos:
            if et not in MODELOS_BIDIRECCIONALES:
                raise CommandError(f'"{et}" no está en el alcance del sync.')

        total_distintas = total_solo_aca = total_marcadas = 0
        mostradas = 0

        for et in modelos:
            remoto = self._traer(base, token, et)
            modelo = modelo_de(et)

            distintas, solo_aca = [], []
            for fila in modelo.objects.all().iterator(chunk_size=300):
                uid = str(fila.uid)
                if uid not in remoto:
                    solo_aca.append(fila)
                    continue
                campos = self._diferencias(serializar(fila), remoto[uid]['datos'])
                if campos:
                    distintas.append((fila, campos))

            if not distintas and not solo_aca:
                self.stdout.write(f'{et}: igual en los dos equipos.')
                continue

            self.stdout.write(self.style.MIGRATE_HEADING(
                f'\n{et}: {len(distintas)} distintas, {len(solo_aca)} solo acá'))

            for fila, campos in distintas:
                if mostradas < opciones['limite_detalle']:
                    etiqueta_fila = getattr(fila, 'codigo', None) or getattr(fila, 'sku', None) \
                        or getattr(fila, 'nombre', str(fila.uid))
                    self.stdout.write(f'  {etiqueta_fila}')
                    for campo, (aca, alla) in campos.items():
                        self.stdout.write(f'      {campo}: acá "{aca}"  ≠  servidor "{alla}"')
                    mostradas += 1

            for fila in solo_aca[:max(0, opciones['limite_detalle'] - mostradas)]:
                etiqueta_fila = getattr(fila, 'codigo', None) or getattr(fila, 'nombre', str(fila.uid))
                self.stdout.write(f'  {etiqueta_fila} — no está en el servidor')
                mostradas += 1

            total_distintas += len(distintas)
            total_solo_aca += len(solo_aca)

            if opciones['marcar']:
                total_marcadas += self._marcar(et, [f for f, _ in distintas] + solo_aca)

        self.stdout.write('')
        resumen = (f'{total_distintas} filas distintas, {total_solo_aca} que solo están acá')
        if opciones['marcar']:
            self.stdout.write(self.style.SUCCESS(
                f'{resumen}. {total_marcadas} marcadas para mandar — ahora corré:\n'
                f'  python manage.py sync_empujar --servidor {opciones["servidor"]}'))
        elif total_distintas or total_solo_aca:
            self.stdout.write(self.style.WARNING(
                f'{resumen}.\nNo se marcó nada. Si estos cambios son los buenos, repetir '
                f'con --marcar.\nSi los buenos son los del servidor, no hacer nada: el sync '
                f'los va a traer.'))
        else:
            self.stdout.write(self.style.SUCCESS('Los dos equipos tienen el mismo catálogo.'))

    # ─── Auxiliares ──────────────────────────────────────────────────────────

    def _traer(self, base, token, etiqueta_):
        """Trae el volcado del servidor para un modelo, paginado. uid → fila."""
        filas, desde = {}, 0
        while True:
            url = f'{base}/sync/catalogo/?modelo={etiqueta_}&desde={desde}&limite={POR_PAGINA}'
            try:
                pagina = pedir_json(url, token)
            except ErrorDeNodo as e:
                raise CommandError(f'Fallo trayendo {etiqueta_}: {e}')
            for fila in pagina['filas']:
                filas[fila['uid']] = fila
            desde += POR_PAGINA
            if desde >= pagina['total']:
                return filas

    def _iguales(self, a, b):
        """
        Si dos valores serializados representan lo mismo.

        Los números van por `Decimal` y no por texto: "150000" y "150000.00"
        son el mismo precio, y compararlos como cadenas inventa diferencias
        que después se marcarían y se empujarían al servidor sin motivo.
        """
        if a == b:
            return True
        if a is None or b is None:
            return False
        try:
            return Decimal(str(a)) == Decimal(str(b))
        except (InvalidOperation, ValueError):
            return str(a) == str(b)

    def _diferencias(self, aca, alla):
        """Campos con distinto valor."""
        return {
            campo: (valor, alla.get(campo))
            for campo, valor in aca.items()
            if campo not in IGNORAR and not self._iguales(valor, alla.get(campo))
        }

    def _marcar(self, etiqueta_, filas):
        """
        Anota estas filas como cambios locales pendientes.

        Se usa `actualizado_en` de la fila como momento del cambio... salvo que
        el servidor tenga una versión más nueva, en cuyo caso ganaría el
        servidor y marcar no habría servido de nada. Por eso se marca con la
        hora de ahora: es una decisión explícita de "lo de la notebook es lo
        bueno", que es justamente lo que el operador está diciendo al pasar
        --marcar.
        """
        ahora = timezone.now()
        nuevos = [
            CambioSync(
                modelo=etiqueta_,
                uid=fila.uid,
                operacion=CambioSync.CAMBIO,
                datos=serializar(fila),
                nodo=settings.NODO['nombre'],
                momento=ahora,
            )
            for fila in filas
        ]
        CambioSync.objects.bulk_create(nuevos, batch_size=200)
        return len(nuevos)
