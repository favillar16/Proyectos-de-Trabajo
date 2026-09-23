"""
Transmite al SIFEN los documentos electrónicos y los eventos en cola.

Pensado para correr como tarea programada de Windows en la PC servidor, cada
pocos minutos — igual que el sync de la notebook. También sirve a mano para
destrabar la cola después de un corte de internet.

    python manage.py sifen_transmitir
    python manage.py sifen_transmitir --limite 20
    python manage.py sifen_transmitir --listar        (no transmite nada)

Los eventos (cancelaciones e inutilizaciones) viajan en la misma corrida y
**antes** que los documentos: una cancelación tiene 48 horas de plazo desde
la aprobación del DTE, y un documento nuevo no tiene un apuro equivalente.

⚠️ Solo corre en la PC servidor. La facturación es server-authoritative,
igual que el stock y la caja: la notebook de la propietaria no emite ni
transmite (ver docs/sync_bidireccional.md).
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.facturacion import eventos as eventos_mod
from apps.facturacion import sifen_client, transmision
from apps.facturacion.emisor import sifen_activo
from apps.facturacion.models import DocumentoElectronico, EventoDocumento


class Command(BaseCommand):
    help = 'Transmite al SIFEN los documentos electrónicos pendientes.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limite', type=int, default=None,
            help='Cuántos documentos transmitir como máximo en esta corrida.')
        parser.add_argument(
            '--listar', action='store_true',
            help='Muestra la cola y sale, sin transmitir nada.')
        parser.add_argument(
            '--forzar', action='store_true',
            help='Transmite aunque SIFEN_HABILITADO esté en False. Solo para '
                 'probar contra el ambiente de test.')

    def handle(self, *args, **opciones):
        cola = list(transmision.pendientes(opciones['limite']))
        cola_eventos = list(eventos_mod.pendientes(opciones['limite']))

        if opciones['listar']:
            return self._listar(cola, cola_eventos)

        if not sifen_activo() and not opciones['forzar']:
            self.stdout.write(self.style.WARNING(
                'SIFEN_HABILITADO está en False: no se transmite nada.\n'
                'Es el estado normal mientras no estén el certificado y la '
                'habilitación de la DNIT.\n'
                'Para probar contra el ambiente de test: --forzar'))
            return

        if not cola and not cola_eventos:
            self.stdout.write('No hay documentos ni eventos pendientes de transmitir.')
            return

        # Si el sidecar no está levantado no tiene sentido recorrer la cola
        # entera sumando un intento fallido a cada documento.
        try:
            sifen_client.salud()
        except sifen_client.ErrorSidecar as e:
            raise SystemExit(self.style.ERROR(
                f'El sidecar no responde: {e}\n'
                f'No se transmitió nada — los documentos siguen en cola, sin '
                f'gastar intentos.'))

        # Los eventos van primero: son los que corren contra un plazo.
        if cola_eventos:
            self.stdout.write(f'Transmitiendo {len(cola_eventos)} evento(s)...')
            for evento in eventos_mod.transmitir_pendientes(opciones['limite']):
                estilo = (self.style.SUCCESS
                          if evento.estado == EventoDocumento.ESTADO_APROBADO
                          else self.style.ERROR
                          if evento.estado == EventoDocumento.ESTADO_RECHAZADO
                          else self.style.WARNING)
                self.stdout.write(estilo(f'  {evento}'))
            self.stdout.write('')

        if not cola:
            return

        self.stdout.write(f'Transmitiendo {len(cola)} documento(s)...\n')
        resultados = transmision.transmitir_pendientes(opciones['limite'])

        aprobados = rechazados = reintentables = 0
        for resultado in resultados:
            if resultado.ok:
                aprobados += 1
                estilo = self.style.SUCCESS
            elif resultado.reintentable:
                reintentables += 1
                estilo = self.style.WARNING
            else:
                rechazados += 1
                estilo = self.style.ERROR
            self.stdout.write(estilo(str(resultado)))

        self.stdout.write('')
        self.stdout.write(f'Aprobados: {aprobados}   '
                          f'Rechazados: {rechazados}   '
                          f'A reintentar: {reintentables}')

        if rechazados:
            self.stdout.write(self.style.ERROR(
                '\nHay documentos rechazados por el SIFEN. No se reintentan '
                'solos: hay que revisar el motivo y emitir uno corregido.'))

    def _listar(self, cola, cola_eventos=()):
        if cola_eventos:
            self.stdout.write(f'{len(cola_eventos)} evento(s) en cola:')
            for evento in cola_eventos:
                self.stdout.write(f'  {evento}  intentos {evento.intentos_envio}')
            self.stdout.write('')

        if not cola:
            self.stdout.write('La cola está vacía.')
        else:
            max_intentos = getattr(settings, 'SIFEN', {}).get('max_intentos', 10)
            self.stdout.write(f'{len(cola)} documento(s) en cola:\n')
            for documento in cola:
                self.stdout.write(
                    f'  {documento.numero_completo}  '
                    f'{documento.fecha_emision:%d/%m/%Y %H:%M}  '
                    f'{documento.get_estado_display()}  '
                    f'intentos {documento.intentos_envio}/{max_intentos}')

        # Los rechazados no están "en cola" pero son lo que alguien tiene que
        # mirar, así que conviene que aparezcan en el mismo lugar.
        rechazados = DocumentoElectronico.objects.filter(
            estado=DocumentoElectronico.ESTADO_RECHAZADO).count()
        if rechazados:
            self.stdout.write(self.style.ERROR(
                f'\nAdemás hay {rechazados} documento(s) RECHAZADOS por el '
                f'SIFEN, que no se reintentan solos.'))
