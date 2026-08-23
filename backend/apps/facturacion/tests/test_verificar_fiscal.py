"""
Tests del comando `manage.py verificar_fiscal`.

Es la herramienta con la que se va a cargar la configuración fiscal el día
del lanzamiento, así que tiene que ser confiable justo cuando todo lo demás
está a medio configurar: no puede reventar por un dato faltante, y tiene que
nombrar exactamente qué falta.
"""
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from . import factories as f


def _correr(**kwargs):
    salida = StringIO()
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
