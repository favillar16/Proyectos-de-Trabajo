"""
Tests del comando `manage.py verificar_fiscal`.

Es la herramienta con la que se va a cargar la configuración fiscal el día
del lanzamiento, así que tiene que ser confiable justo cuando todo lo demás
está a medio configurar: no puede reventar por un dato faltante, y tiene que
nombrar exactamente qué falta.
"""
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from apps.facturacion import sifen_client

from . import factories as f


def _correr(sidecar=None, **kwargs):
    """
    Corre el comando con el sidecar simulado.

    El simulacro NO es opcional: desde que el diagnóstico revisa el sidecar,
    el comando abre una conexión HTTP a 127.0.0.1:8100. Sin mockearlo, estos
    tests darían distinto según si el sidecar está levantado en la máquina que
    los corre — o sea que dejarían de probar el comando y pasarían a probar el
    estado de la PC. Por defecto se simula caído, que es el caso de hoy.

    `sidecar` puede ser un dict (respuesta de /salud) o una excepción.
    """
    if sidecar is None:
        sidecar = sifen_client.ErrorSidecar('no hay nadie escuchando')
    parche = ({'side_effect': sidecar} if isinstance(sidecar, Exception)
              else {'return_value': sidecar})

    salida = StringIO()
    with mock.patch.object(sifen_client, 'salud', **parche):
        call_command('verificar_fiscal', stdout=salida, stderr=salida, **kwargs)
    return salida.getvalue()


@override_settings(DATOS_FISCALES={}, SIFEN=f.SIFEN_APAGADO)
class SinConfigurarTests(SimpleTestCase):

    def test_no_revienta_con_todo_vacio(self):
        # El caso real del día de la instalación.
        salida = _correr()
        self.assertIn('RESUMEN', salida)

    def test_nombra_cada_clave_que_falta(self):
        salida = _correr()
        for clave in ('FISCAL_RUC', 'FISCAL_DIRECCION', 'FISCAL_TIMBRADO',
                      'FISCAL_TIMBRADO_VTO', 'FISCAL_DEPARTAMENTO',
                      'FISCAL_DISTRITO', 'FISCAL_CIUDAD',
                      'FISCAL_ACTIVIDAD_CODIGO'):
            with self.subTest(clave=clave):
                self.assertIn(clave, salida)

    def test_indica_donde_cargarlos(self):
        salida = _correr()
        self.assertIn('.env', salida)
        self.assertIn('facturacion_electronica.md', salida)

    def test_la_salida_es_ascii_puro(self):
        # La consola de la PC servidor es cp1252: un carácter de caja Unicode
        # tira UnicodeEncodeError y el comando no llega a mostrar nada.
        salida = _correr()
        try:
            salida.encode('cp1252')
        except UnicodeEncodeError as e:
            self.fail(f'La salida no se puede imprimir en la consola de '
                      f'Windows (cp1252): {e}')

    def test_con_cdc_no_revienta_sin_ruc(self):
        salida = _correr(cdc=True)
        self.assertIn('CDC DE PRUEBA', salida)


@override_settings(DATOS_FISCALES=f.DATOS_FISCALES_COMPLETOS, SIFEN=f.SIFEN_APAGADO)
class ConDatosCompletosTests(SimpleTestCase):

    def test_valida_el_digito_verificador_del_ruc(self):
        salida = _correr()
        self.assertIn('dígito verificador correcto', salida)

    def test_avisa_si_el_dv_del_ruc_no_cierra(self):
        from apps.facturacion.ruc import calcular_dv
        malo = (calcular_dv(f.BASE_RUC_EMISOR) + 1) % 10
        fiscal = dict(f.DATOS_FISCALES_COMPLETOS,
                      ruc=f'{f.BASE_RUC_EMISOR}-{malo}')
        with override_settings(DATOS_FISCALES=fiscal):
            salida = _correr()
        # Tiene que decir cuál sería el correcto, y contemplar la posibilidad
        # de que el equivocado sea nuestro algoritmo y no el RUC.
        self.assertIn(str(calcular_dv(f.BASE_RUC_EMISOR)), salida)
        self.assertIn('ruc.py', salida)

    def test_genera_un_cdc_de_prueba_descompuesto(self):
        salida = _correr(cdc=True)
        for campo in ('tipo_documento', 'ruc_emisor', 'establecimiento',
                      'punto_expedicion', 'codigo_seguridad'):
            with self.subTest(campo=campo):
                self.assertIn(campo, salida)

    def test_marca_que_el_sifen_esta_apagado(self):
        salida = _correr()
        self.assertIn('SIFEN_HABILITADO', salida)
        self.assertIn('como hasta ahora', salida)

    def test_reporta_el_certificado_faltante(self):
        salida = _correr()
        self.assertIn('SIFEN_CERT_PATH', salida)


def _salud(vence=None, **extra):
    """Respuesta de /salud con el certificado configurado."""
    certificado = {'configurado': True, 'archivo': 'C:/certs/emisor.p12',
                   'existe': True, 'vence': vence}
    certificado.update(extra)
    return {'servicio': 'sidecar-sifen', 'ok': True, 'ambiente': 'test',
            'certificado': certificado,
            'csc': {'id': '1', 'cargado': True}, 'eventos': []}


@override_settings(DATOS_FISCALES=f.DATOS_FISCALES_COMPLETOS,
                   SIFEN=f.SIFEN_APAGADO)
class SidecarTests(SimpleTestCase):
    """
    El diagnóstico del sidecar y del vencimiento del certificado.

    Lo del vencimiento es lo que más importa: un .p12 vencido frena la
    facturación entera y no avisa solo. El primer síntoma, sin este aviso,
    sería un rechazo del SIFEN a mitad de una jornada de ventas.
    """

    def test_si_el_sidecar_no_responde_avisa_pero_no_revienta(self):
        # Es el estado normal mientras la facturación electrónica esté
        # apagada: la tienda funcionó meses sin el sidecar.
        salida = _correr()
        self.assertIn('SIDECAR', salida)
        self.assertIn('no responde', salida)
        self.assertIn('npm start', salida)
        self.assertIn('RESUMEN', salida)

    def test_si_responde_lo_dice(self):
        salida = _correr(sidecar=_salud())
        self.assertIn('responde', salida)

    def test_un_certificado_vencido_sale_como_falta_no_como_aviso(self):
        from datetime import date, timedelta
        ayer = (date.today() - timedelta(days=3)).isoformat()
        salida = _correr(sidecar=_salud(vence=ayer))
        self.assertIn('VENCIDO', salida)
        self.assertIn('3', salida)

    def test_avisa_con_un_mes_de_anticipacion(self):
        from datetime import date, timedelta
        pronto = (date.today() + timedelta(days=12)).isoformat()
        salida = _correr(sidecar=_salud(vence=pronto))
        self.assertIn('vence en 12 d', salida)
        self.assertIn('renovarlo', salida)

    def test_un_vencimiento_lejano_no_alarma(self):
        from datetime import date, timedelta
        lejos = (date.today() + timedelta(days=400)).isoformat()
        salida = _correr(sidecar=_salud(vence=lejos))
        self.assertIn('faltan 400', salida)
        self.assertNotIn('VENCIDO', salida)

    def test_la_fecha_con_zona_horaria_se_entiende_igual(self):
        # getExpiration devuelve lo que trae el .p12, y el formato no está
        # garantizado. Que no se entienda no puede tirar el diagnóstico.
        from datetime import date, timedelta
        lejos = (date.today() + timedelta(days=100)).isoformat()
        salida = _correr(sidecar=_salud(vence=f'{lejos}T23:59:59Z'))
        self.assertIn('faltan 100', salida)

    def test_una_fecha_que_no_se_entiende_no_revienta(self):
        salida = _correr(sidecar=_salud(vence='algún día'))
        self.assertIn('RESUMEN', salida)

    def test_si_el_p12_no_abre_lo_reporta_como_falta(self):
        # Clave equivocada. Vale la pena descubrirlo acá y no en la primera
        # venta del día que se prenda el SIFEN.
        salida = _correr(sidecar=_salud(error='No se pudo abrir el .p12: mac verify failure'))
        self.assertIn('mac verify failure', salida)

    def test_entiende_la_forma_cruda_de_getExpiration(self):
        # `xmlsign.getExpiration()` devuelve {notBefore, notAfter}, no una
        # fecha. El sidecar lo normaliza, pero si corre una versión vieja el
        # diagnóstico tiene que seguir avisando igual — es el caso en el que
        # uno lo corre. Se descubrió probando con un .p12 real: sin
        # certificado configurado este camino nunca se ejecuta.
        from datetime import date, timedelta
        vto = (date.today() + timedelta(days=200)).isoformat()
        salida = _correr(sidecar=_salud(vence={
            'notBefore': '2026-09-16T14:02:09.000Z',
            'notAfter': f'{vto}T14:02:09.000Z',
        }))
        self.assertIn('faltan 200', salida)
