"""
Manda al servidor lo que se editó en este equipo.

Es la mitad del sync que antes no existía. La otra mitad —traer lo del
servidor— la sigue haciendo `pg_dump` + `psql` desde `sync_notebook.ps1`, que
arrastra también el stock, las ventas y la caja, que van en una sola dirección.

    python manage.py sync_empujar --servidor ogapora.local
    python manage.py sync_empujar --servidor ogapora.local --simular

El agente lo llama ANTES del restore. El orden importa: el restore borra
`ceramica_db` entera, y si se empujara después, lo que la notebook editó
estando afuera ya no estaría para mandar.
"""
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.sync.cliente import ErrorDeNodo, enviar_archivo, enviar_json, pedir_json
from apps.sync.models import CambioSync, EstadoSync
from apps.sync.registro import MODELOS_CON_ARCHIVO

# Igual que MAX_POR_LOTE del receptor. Si se corta el WiFi a mitad de camino,
# lo ya confirmado queda marcado y el próximo intento sigue desde ahí.
POR_LOTE = 500


class Command(BaseCommand):
    help = 'Empuja al servidor los cambios de catálogo hechos en este equipo.'

    def add_arguments(self, parser):
        parser.add_argument('--servidor', required=True,
                            help='Nombre o IP del servidor (ej: ogapora.local)')
        parser.add_argument('--puerto', type=int, default=8000)
        parser.add_argument('--token', default='',
                            help='X-Sync-Token. Por defecto, el SYNC_TOKEN del .env.')
        parser.add_argument('--simular', action='store_true',
                            help='Muestra qué se mandaría, sin mandar nada.')
        parser.add_argument('--sin-fotos', action='store_true',
                            help='No sube los archivos de las fotos nuevas.')

    def handle(self, *args, **opciones):
        token = opciones['token'] or settings.SYNC['token']
        if not token:
            raise CommandError(
                'Falta el token de sincronización. Poner SYNC_TOKEN en el .env '
                'de este equipo (el mismo que el del servidor) o pasar --token.')

        base = f'http://{opciones["servidor"]}:{opciones["puerto"]}/api/v1'
        nodo = settings.NODO['nombre']

        pendientes = list(
            CambioSync.objects.filter(empujado_en__isnull=True).order_by('momento', 'id')
        )
        if not pendientes:
            self.stdout.write('No hay cambios para mandar.')
            return

        self.stdout.write(f'{len(pendientes)} cambios pendientes en {nodo}.')

        if opciones['simular']:
            self._mostrar(pendientes)
            return

        # Verificar de entrada con quién estamos hablando: mandarle el catálogo
        # a un equipo equivocado es peor que no mandarlo.
        try:
            identidad = pedir_json(f'{base}/salud/', token)
        except ErrorDeNodo as e:
            raise CommandError(f'No se pudo contactar al servidor: {e}')
        if identidad.get('rol') != 'servidor':
            raise CommandError(
                f'{opciones["servidor"]} dice ser "{identidad.get("rol")}", no el '
                f'servidor. No se manda nada.')

        enviados = aplicados = conflictos = 0
        for desde in range(0, len(pendientes), POR_LOTE):
            lote = pendientes[desde:desde + POR_LOTE]
            cuerpo = {'nodo': nodo, 'cambios': [self._serializar(c) for c in lote]}

            try:
                respuesta = enviar_json(f'{base}/sync/cambios/', token, cuerpo)
            except ErrorDeNodo as e:
                # Lo ya confirmado queda marcado; el resto se reintenta solo en
                # la próxima corrida.
                self._registrar_estado(enviados, conflictos, f'Cortado: {e}')
                raise CommandError(f'Falló el envío del lote: {e}')

            aplicados += respuesta.get('aplicados', 0)
            conflictos += respuesta.get('conflictos', 0)
            enviados += len(lote)

            for aviso in respuesta.get('detalle', []):
                for ajuste in aviso.get('ajustes', []):
                    self.stdout.write(self.style.WARNING(
                        f'  {aviso["modelo"]} {aviso["uid"]}: {ajuste}'))

            ahora = timezone.now()
            CambioSync.objects.filter(pk__in=[c.pk for c in lote]).update(empujado_en=ahora)
            self.stdout.write(f'  lote de {len(lote)}: {respuesta.get("aplicados", 0)} aplicados, '
                              f'{respuesta.get("conflictos", 0)} en conflicto')

        if not opciones['sin_fotos']:
            self._subir_fotos(base, token, pendientes)

        self._registrar_estado(enviados, conflictos,
                               f'{aplicados} aplicados en el servidor')

        resumen = f'Listo: {enviados} cambios enviados, {aplicados} aplicados'
        if conflictos:
            resumen += f', {conflictos} en conflicto (revisar en el servidor)'
            self.stdout.write(self.style.WARNING(resumen))
        else:
            self.stdout.write(self.style.SUCCESS(resumen))

    # ─── Auxiliares ──────────────────────────────────────────────────────────

    def _serializar(self, cambio):
        return {
            'modelo':    cambio.modelo,
            'uid':       str(cambio.uid),
            'operacion': cambio.operacion,
            'datos':     cambio.datos,
            'nodo':      cambio.nodo,
            'momento':   cambio.momento.isoformat(),
        }

    def _subir_fotos(self, base, token, cambios):
        """
        Sube los archivos de las fotos cargadas acá.

        Van aparte del lote porque una foto pesa cientos de KB: metida en el
        JSON, un corte de WiFi obligaría a reenviar todo el catálogo de nuevo.
        """
        rutas = set()
        for cambio in cambios:
            campo = MODELOS_CON_ARCHIVO.get(cambio.modelo)
            if not campo or cambio.operacion == CambioSync.BAJA:
                continue
            ruta = (cambio.datos or {}).get(campo)
            if ruta:
                rutas.add(ruta)

        if not rutas:
            return

        subidas = faltantes = 0
        for ruta in sorted(rutas):
            completa = os.path.join(settings.MEDIA_ROOT, ruta.replace('/', os.sep))
            if not os.path.exists(completa):
                faltantes += 1
                continue
            try:
                with open(completa, 'rb') as f:
                    contenido = f.read()
                enviar_archivo(f'{base}/sync/foto/', token, ruta, contenido,
                               os.path.basename(completa))
                subidas += 1
            except (OSError, ErrorDeNodo) as e:
                # Una foto que no sube no invalida el catálogo: el producto ya
                # llegó, le falta la imagen. Se avisa y se sigue.
                self.stdout.write(self.style.WARNING(f'  foto {ruta}: {e}'))

        self.stdout.write(f'Fotos: {subidas} subidas de {len(rutas)}'
                          + (f', {faltantes} sin archivo en disco' if faltantes else ''))

    def _registrar_estado(self, enviados, conflictos, detalle):
        estado, _ = EstadoSync.objects.get_or_create(nodo='servidor')
        estado.ultimo_intento = timezone.now()
        if enviados:
            estado.ultimo_exito = estado.ultimo_intento
        estado.cambios_enviados += enviados
        estado.conflictos += conflictos
        estado.detalle = detalle
        estado.save()

    def _mostrar(self, pendientes):
        por_modelo = {}
        for c in pendientes:
            por_modelo.setdefault(c.modelo, {}).setdefault(c.operacion, 0)
            por_modelo[c.modelo][c.operacion] += 1
        for modelo, ops in sorted(por_modelo.items()):
            detalle = ', '.join(f'{n} {op}' for op, n in sorted(ops.items()))
            self.stdout.write(f'  {modelo}: {detalle}')
