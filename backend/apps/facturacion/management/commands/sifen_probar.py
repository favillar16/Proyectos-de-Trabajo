"""
Prueba la cadena contra el sidecar, sin transmitir nada al SIFEN.

Para qué sirve: el armado del XML es lo único de la facturación electrónica
que se puede verificar **hoy**, sin certificado y sin habilitación. `xmlgen`
no necesita la firma, así que este comando recorre payload → sidecar → XML y
deja ver el resultado. El día que llegue el .p12, lo único nuevo a probar es
firmar y transmitir.

No toca la base: arma el payload de un documento que ya existe y lo manda al
sidecar. Si no se le pasa ninguno, usa el último emitido.

    python manage.py sifen_probar --salud
    python manage.py sifen_probar --documento 3
    python manage.py sifen_probar --documento 3 --guardar salida.xml
    python manage.py sifen_probar --payload      # solo el JSON, sin sidecar

`--payload` no necesita ni el sidecar levantado: muestra lo que Django le
mandaría. Sirve para separar "el payload está mal" de "el sidecar está mal",
que es la primera pregunta cuando algo falla.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.facturacion import payload as payload_mod
from apps.facturacion import sifen_client
from apps.facturacion.models import DocumentoElectronico


class Command(BaseCommand):
    help = 'Arma el XML de un documento contra el sidecar, sin transmitirlo.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--documento', type=int, default=None,
            help='ID del DocumentoElectronico. Por defecto, el último emitido.')
        parser.add_argument(
            '--salud', action='store_true',
            help='Solo consulta /salud del sidecar y sale.')
        parser.add_argument(
            '--payload', action='store_true',
            help='Muestra el JSON que se le mandaría al sidecar, sin llamarlo.')
        parser.add_argument(
            '--guardar', metavar='ARCHIVO', default=None,
            help='Guarda el XML generado en un archivo.')
        parser.add_argument(
            '--firmar', action='store_true',
            help='Sigue la cadena: firma el XML y le agrega el QR. '
                 'Necesita certificado, pero NO transmite nada.')

    def handle(self, *args, **opciones):
        if opciones['salud']:
            return self._salud()

        documento = self._documento(opciones['documento'])
        self.stdout.write(
            f'Documento {documento.pk}: {documento.numero_completo} '
            f'({documento.get_tipo_documento_display() if hasattr(documento, "get_tipo_documento_display") else documento.tipo_documento})')

        try:
            cuerpo = payload_mod.construir(documento)
        except payload_mod.DatosIncompletos as e:
            # Es el error útil: dice qué dato falta y de dónde sale. No se
            # convierte en un traceback.
            raise CommandError(f'No se puede armar el payload:\n  {e}')

        self.stdout.write(self.style.SUCCESS('  payload armado OK'))
        self._resumen(cuerpo)

        if opciones['payload']:
            self.stdout.write('')
            self.stdout.write(json.dumps(cuerpo, indent=2, ensure_ascii=False,
                                         default=str))
            return

        try:
            xml = sifen_client.generar_xml(cuerpo['params'], cuerpo['data'])
        except sifen_client.RechazoSifen as e:
            raise CommandError(
                f'El sidecar rechazó el pedido (no se reintentaría):\n  {e}')
        except sifen_client.ErrorSidecar as e:
            raise CommandError(
                f'No se pudo hablar con el sidecar:\n  {e}\n\n'
                f'  Levantarlo con:  cd sidecar && npm start')

        self.stdout.write(self.style.SUCCESS(
            f'  XML generado OK ({len(xml)} caracteres)'))

        self._verificar_cdc(documento, xml)

        if opciones['firmar']:
            xml = self._firmar_y_qr(xml)

        if opciones['guardar']:
            with open(opciones['guardar'], 'w', encoding='utf-8') as f:
                f.write(xml)
            self.stdout.write(f'  guardado en {opciones["guardar"]}')
        else:
            self.stdout.write('')
            self.stdout.write(xml[:3000])
            if len(xml) > 3000:
                self.stdout.write(self.style.WARNING(
                    f'  ... (recortado; usar --guardar para el XML completo)'))

    # ── auxiliares ──────────────────────────────────────────────────────────

    def _firmar_y_qr(self, xml):
        """
        Firma el XML y le incorpora el QR. No transmite nada.

        Es el último eslabón que se puede probar sin estar habilitado ante el
        DNIT. Y se puede probar **antes** de tener el certificado definitivo:
        la propia Guía de Pruebas pide, como uno de sus escenarios, intentar
        con un certificado "no válido" que el contribuyente se autogenera. O
        sea que un `.p12` hecho con openssl sirve para verificar toda la
        mecánica de firma —que el archivo abra, que la clave sea la correcta,
        que el nodo firmado sea el que corresponde, que el QR se calcule con
        el CSC— y lo único que no prueba es el handshake contra el SIFEN, que
        es justamente lo que necesita el certificado de verdad.
        """
        try:
            firmado = sifen_client.firmar_xml(xml)
        except sifen_client.RechazoSifen as e:
            raise CommandError(f'No se pudo firmar:\n  {e}')
        except sifen_client.ErrorSidecar as e:
            raise CommandError(f'Error hablando con el sidecar al firmar:\n  {e}')

        if '<Signature' not in firmado and 'ds:Signature' not in firmado:
            raise CommandError(
                'El sidecar devolvió un XML sin nodo de firma. Revisar '
                'sidecar/sifen.js (signByNodeJS tiene que ir en True).')
        self.stdout.write(self.style.SUCCESS(
            f'  firmado OK ({len(firmado) - len(xml):+} caracteres de firma)'))

        try:
            con_qr = sifen_client.generar_qr(firmado)
        except sifen_client.RechazoSifen as e:
            raise CommandError(f'No se pudo generar el QR:\n  {e}')
        except sifen_client.ErrorSidecar as e:
            raise CommandError(f'Error hablando con el sidecar al generar el QR:\n  {e}')

        import re
        qr = re.search(r'<dCarQR>(.*?)</dCarQR>', con_qr, re.S)
        if not qr:
            raise CommandError('El XML volvió sin el campo dCarQR.')
        self.stdout.write(self.style.SUCCESS('  QR incorporado OK'))
        self.stdout.write(f'    {qr.group(1)[:110]}...')
        return con_qr


    def _verificar_cdc(self, documento, xml):
        """
        El CDC que calculó Django y el que calculó xmlgen tienen que ser el mismo.

        Vale la pena explicar por qué esto es la verificación más valiosa del
        comando. El CDC no se le manda al sidecar: Django le pasa los campos
        sueltos (establecimiento, punto, número, código de seguridad, fecha) y
        `xmlgen` lo arma por su cuenta, con su propia implementación del
        dígito verificador. O sea que son **dos implementaciones
        independientes** del mismo algoritmo, y acá se comparan sobre un
        documento real.

        Es exactamente el error que estuvo abierto desde agosto de 2026: el
        sistema calculaba el DV con pesos 2..9 y el SIFEN usa 2..11, así que
        todos los CDC salían con el dígito equivocado — rechazo del 100% de
        los documentos, desde el primero. Un chequeo unitario contra el
        ejemplo del manual ya existe (`test_cdc.py`); este otro corre contra
        la versión de la librería que está instalada hoy, así que además
        avisaría si una actualización de `xmlgen` cambiara el algoritmo.

        Si no coinciden no se sigue: el documento saldría con un CDC que el
        SIFEN no reconoce.
        """
        import re
        encontrado = re.search(r'<DE\s+Id="(\d{44})"', xml)
        if not encontrado:
            self.stdout.write(self.style.WARNING(
                '  no se pudo leer el CDC del XML para contrastarlo'))
            return

        del_xml = encontrado.group(1)
        if del_xml == documento.cdc:
            self.stdout.write(self.style.SUCCESS(
                f'  CDC coincide con el de la librería de la DNIT '
                f'(DV {del_xml[-1]})'))
            return

        raise CommandError(
            'El CDC no coincide con el que calcula la librería de la DNIT.\n'
            f'  Django: {documento.cdc}\n'
            f'  xmlgen: {del_xml}\n'
            '  El SIFEN recalcula con SU algoritmo, así que el que manda es\n'
            '  el de la librería. Revisar apps/facturacion/cdc.py.')

    def _documento(self, pk):
        if pk is not None:
            try:
                return DocumentoElectronico.objects.get(pk=pk)
            except DocumentoElectronico.DoesNotExist:
                raise CommandError(f'No existe el documento {pk}.')
        documento = DocumentoElectronico.objects.order_by('-fecha_emision').first()
        if documento is None:
            raise CommandError(
                'No hay ningún documento electrónico emitido todavía. '
                'Cobrar una venta con SIFEN_HABILITADO=True, o pasar --documento.')
        return documento

    def _resumen(self, cuerpo):
        """Lo que conviene mirar de un vistazo antes de leer el XML entero."""
        data = cuerpo['data']
        cliente = data.get('cliente', {})
        self.stdout.write(
            f'  emisor:   {cuerpo["params"]["ruc"]} — '
            f'timbrado {cuerpo["params"]["timbradoNumero"]} '
            f'(desde {cuerpo["params"]["timbradoFecha"]})')
        self.stdout.write(
            f'  receptor: {cliente.get("razonSocial", "?")} — '
            + (f'RUC {cliente["ruc"]}' if cliente.get('ruc')
               else f'doc tipo {cliente.get("documentoTipo")} '
                    f'nro {cliente.get("documentoNumero")}'))
        items = data.get('items', [])
        total = sum(
            (float(i['precioUnitario']) - float(i['descuento'])) * float(i['cantidad'])
            for i in items)
        self.stdout.write(f'  ítems:    {len(items)} — reconstruyen {total:,.2f} Gs'
                          .replace(',', '.'))

    def _salud(self):
        try:
            estado = sifen_client.salud()
        except sifen_client.ErrorSidecar as e:
            raise CommandError(
                f'{e}\n\n  Levantarlo con:  cd sidecar && npm start')

        self.stdout.write(self.style.SUCCESS('El sidecar responde.'))
        self.stdout.write(f'  ambiente:    {estado.get("ambiente")}')
        cert = estado.get('certificado', {})
        if not cert.get('configurado'):
            self.stdout.write(self.style.WARNING(
                '  certificado: SIN CONFIGURAR — se puede armar el XML, '
                'pero no firmar ni transmitir'))
        elif not cert.get('existe'):
            self.stdout.write(self.style.ERROR(
                f'  certificado: NO EXISTE el archivo {cert.get("archivo")}'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'  certificado: {cert.get("archivo")}'))
            if cert.get('vence'):
                self.stdout.write(f'  vence:       {cert["vence"]}')
            if cert.get('error'):
                self.stdout.write(self.style.ERROR(f'  {cert["error"]}'))
        csc = estado.get('csc', {})
        self.stdout.write(
            f'  CSC:         ' +
            (f'cargado (ID {csc.get("id")})' if csc.get('cargado')
             else 'SIN CONFIGURAR'))
