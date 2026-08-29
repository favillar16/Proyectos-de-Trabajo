"""
Diagnóstico de la configuración fiscal.

    python manage.py verificar_fiscal

Existe para que el día del lanzamiento no haya que ir campo por campo
adivinando qué falta. Revisa el .env, valida el dígito verificador del RUC
real contra el algoritmo, prueba que el CDC se arme, y lista lo que queda
pendiente en un orden accionable.

No modifica nada: se puede correr las veces que haga falta.
"""
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.facturacion import cdc as cdc_mod
from apps.facturacion import codigos
from apps.facturacion.ruc import RucInvalido, calcular_dv, separar

OK = 'OK  '
FALTA = 'FALTA'
AVISO = 'AVISO'


class Command(BaseCommand):
    help = 'Verifica que los datos fiscales estén completos para poder facturar.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cdc', action='store_true',
            help='Además, genera un CDC de prueba con los datos configurados.')

    def handle(self, *args, **opciones):
        fiscal = getattr(settings, 'DATOS_FISCALES', {})
        sifen = getattr(settings, 'SIFEN', {})
        problemas = []
        transmision = []

        self._titulo('DATOS FISCALES DEL EMISOR (.env)')

        # ── RUC: el único que se puede verificar de verdad ────────────────
        ruc = (fiscal.get('ruc') or '').strip()
        if not ruc:
            self._linea(FALTA, 'FISCAL_RUC', 'sin definir — la factura sale sin RUC')
            problemas.append('FISCAL_RUC')
        else:
            try:
                base, dv = separar(ruc)
                esperado = calcular_dv(base)
                if esperado == dv:
                    self._linea(OK, 'FISCAL_RUC', f'{base}-{dv} (dígito verificador correcto)')
                else:
                    self._linea(
                        FALTA, 'FISCAL_RUC',
                        f'{ruc} — el DV no cierra: debería terminar en {esperado}. '
                        f'Si el RUC en la cédula tributaria SÍ termina en {dv}, '
                        f'entonces el algoritmo del módulo 11 no coincide con el '
                        f'de la DNIT y hay que corregir apps/facturacion/ruc.py.')
                    problemas.append('FISCAL_RUC')
            except RucInvalido as e:
                self._linea(FALTA, 'FISCAL_RUC', str(e))
                problemas.append('FISCAL_RUC')

        # ── El resto: solo se puede chequear presencia ─────────────────────
        obligatorios = [
            ('razon_social', 'FISCAL_RAZON_SOCIAL', 'nombre que va impreso en la factura'),
            ('direccion', 'FISCAL_DIRECCION', 'la que figura en el timbrado'),
            ('telefono', 'FISCAL_TELEFONO', ''),
            ('timbrado', 'FISCAL_TIMBRADO', 'número que otorga la DNIT'),
        ]
        for clave, env, nota in obligatorios:
            valor = (fiscal.get(clave) or '').strip()
            if valor and not (clave == 'razon_social' and valor == 'Oga Porã'):
                self._linea(OK, env, valor)
            elif clave == 'razon_social':
                self._linea(AVISO, env, 'usando el default "Oga Porã" — confirmar '
                                        'que sea la razón social exacta del RUC')
            else:
                self._linea(FALTA, env, nota or 'sin definir')
                problemas.append(env)

        # El vencimiento no bloquea: los timbrados electrónicos no vencen como
        # los de talonario, y la habilitación no imprime fecha de fin.
        vto = (fiscal.get('timbrado_vto') or '').strip()
        self._linea(
            OK if vto else AVISO, 'FISCAL_TIMBRADO_VTO',
            vto or 'sin definir — normal en timbrado electrónico; confirmar en Marangatú')

        self._titulo('PUNTO DE EXPEDICIÓN (compone el CDC)')
        for clave, env in [('establecimiento', 'FISCAL_ESTABLECIMIENTO'),
                           ('punto_expedicion', 'FISCAL_PUNTO_EXPEDICION')]:
            valor = str(fiscal.get(clave) or '').strip()
            usando_default = valor in ('001', '')
            self._linea(
                AVISO if usando_default else OK, env,
                f'{valor or "sin definir"}'
                + (' — es el default, confirmar contra lo habilitado en el RUC'
                   if usando_default else ''))
        tipo_c = fiscal.get('tipo_contribuyente')
        self._linea(
            OK if tipo_c in (1, 2) else FALTA, 'FISCAL_TIPO_CONTRIBUYENTE',
            {1: '1 (persona física)', 2: '2 (persona jurídica)'}.get(
                tipo_c, f'valor inválido: {tipo_c!r} — debe ser 1 o 2'))

        self._titulo('DOMICILIO CODIFICADO (lo exige el DE, no el ticket)')
        for clave, env in [('departamento', 'FISCAL_DEPARTAMENTO'),
                           ('distrito', 'FISCAL_DISTRITO'),
                           ('ciudad', 'FISCAL_CIUDAD'),
                           ('actividad_economica', 'FISCAL_ACTIVIDAD_CODIGO')]:
            valor = str(fiscal.get(clave) or '').strip()
            self._linea(OK if valor else AVISO, env,
                        valor or 'sin definir — código de la tabla de la DNIT')
            if not valor:
                transmision.append(env)

        self._titulo('SIFEN / e-Kuatia')
        habilitado = sifen.get('habilitado')
        self._linea(
            OK if not habilitado else AVISO, 'SIFEN_HABILITADO',
            'False — el sistema factura como hasta ahora, sin emitir DEs'
            if not habilitado else
            'True — el sistema va a intentar emitir documentos electrónicos')
        self._linea(OK, 'SIFEN_AMBIENTE', str(sifen.get('ambiente')))
        cert = (sifen.get('certificado_path') or '').strip()
        if cert:
            import os
            existe = os.path.exists(cert)
            self._linea(OK if existe else FALTA, 'SIFEN_CERT_PATH',
                        cert if existe else f'{cert} — el archivo no existe')
        else:
            self._linea(AVISO, 'SIFEN_CERT_PATH',
                        'sin definir — certificado cualificado de firma '
                        '(confirmar quién lo emite y si tiene costo)')
            transmision.append('SIFEN_CERT_PATH')

        csc = (sifen.get('csc') or '').strip()
        csc_id = str(sifen.get('csc_id') or '').strip()
        if csc and csc_id:
            self._linea(OK, 'SIFEN_CSC', f'cargado (ID {csc_id})')
        else:
            self._linea(AVISO, 'SIFEN_CSC',
                        'sin definir — figura en el PDF de la habilitación; '
                        'firma el QR del KuDE')
            transmision.append('SIFEN_CSC')

        # ── CDC de prueba ─────────────────────────────────────────────────
        if opciones['cdc']:
            self._titulo('CDC DE PRUEBA')
            try:
                prueba = cdc_mod.generar(
                    ruc_emisor=ruc,
                    establecimiento=fiscal.get('establecimiento') or '1',
                    punto_expedicion=fiscal.get('punto_expedicion') or '1',
                    numero='1',
                    tipo_contribuyente=fiscal.get('tipo_contribuyente') or 2,
                    fecha_emision=date.today(),
                    tipo_documento=codigos.TIPO_DE_FACTURA,
                )
                self.stdout.write(f'  {cdc_mod.formatear_legible(prueba)}')
                for campo, valor in cdc_mod.descomponer(prueba).items():
                    self.stdout.write(f'    {campo:20} {valor}')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  No se pudo armar: {e}'))

        # ── Resumen ───────────────────────────────────────────────────────
        self._titulo('RESUMEN')

        # Dos listas distintas a propósito. Emitir es local: numerar, calcular
        # el CDC y encolar el documento no necesita internet ni certificado.
        # Transmitir al SIFEN es el paso siguiente y pide otras cosas. Mezclar
        # las dos hacía que el comando marcara como bloqueante algo que no
        # impide facturar.
        if problemas:
            self.stdout.write(self.style.ERROR(
                f'  EMITIR: faltan {len(problemas)} datos, el sistema no puede '
                f'numerar comprobantes:\n'
                f'  {", ".join(dict.fromkeys(problemas))}\n'))
            self.stdout.write(
                '  Se cargan en backend\\.env y se reinicia el sistema.\n'
                '  De dónde sale cada uno: docs/facturacion_electronica.md\n'
                '  y docs/carga_final/datos_fiscales.md\n')
        else:
            self.stdout.write(self.style.SUCCESS(
                '  EMITIR: listo. El sistema puede numerar comprobantes\n'
                '  (001-001-NNNNNNN), calcular el CDC y encolar el documento.\n'
                '  Todo eso es local: no necesita internet.\n'))

        if transmision:
            self.stdout.write(self.style.WARNING(
                f'\n  TRANSMITIR al SIFEN: faltan {len(transmision)}.\n'
                f'  {", ".join(dict.fromkeys(transmision))}\n'))
            self.stdout.write(
                '  No impiden facturar. Hacen falta para armar y firmar el XML,\n'
                '  y solo aplican si se emite con solución propia. Con la\n'
                '  solución gratuita del DNIT la factura se carga en el portal.\n'
                '  Ver docs/carga_final/datos_fiscales.md\n')
        else:
            self.stdout.write(self.style.SUCCESS(
                '\n  TRANSMITIR: los datos están. Falta la parte no\n'
                '  automatizable: sidecar, worker y pruebas en ambiente test.\n'))

    # ── helpers de salida ────────────────────────────────────────────────
    def _titulo(self, texto):
        # Solo ASCII en la salida: la consola de la PC servidor es cp1252 y
        # revienta con UnicodeEncodeError ante los caracteres de caja.
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO(f'-- {texto} '.ljust(76, '-')))

    def _linea(self, estado, clave, detalle):
        estilo = {
            OK: self.style.SUCCESS,
            FALTA: self.style.ERROR,
            AVISO: self.style.WARNING,
        }[estado]
        self.stdout.write(f'  {estilo(estado)}  {clave:28} {detalle}')
