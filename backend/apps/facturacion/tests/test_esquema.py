"""
Validación del XML contra el XSD del SIFEN.

El módulo no tenía tests. Lo que hay que sostener es una sola idea, y tiene
dos caras opuestas que es fácil confundir:

  · **No poder validar nunca puede frenar una emisión.** Sin XSD, sin la
    librería, o con un XSD roto, `validar()` no hace nada. Que falte una
    herramienta de chequeo no significa que el documento esté mal.
  · **Un XSD de la versión equivocada no es "no poder validar": es peor.**
    Compila perfecto y después rechaza absolutamente todo, así que parecería
    que el sistema quedó sin poder emitir. Por eso se descarta al cargarlo.

Lo segundo no es hipotético: el archivo que la DNIT publica como
«Estructura_DE xsd» es de 2018 y no declara `targetNamespace`. Se probó el
23/09/2026 y falla ya en el elemento raíz.
"""
import os
import tempfile
import unittest

from django.test import SimpleTestCase, override_settings

from apps.facturacion import esquema

from .factories import SIFEN_PRENDIDO

try:  # pragma: no cover - depende de requirements-dev.txt
    import xmlschema  # noqa: F401
    HAY_XMLSCHEMA = True
except ImportError:  # pragma: no cover
    HAY_XMLSCHEMA = False


# Un XSD mínimo con el namespace real de los DE del SIFEN.
XSD_BUENO = """<?xml version="1.0" encoding="utf-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns="http://ekuatia.set.gov.py/sifen/xsd"
           targetNamespace="http://ekuatia.set.gov.py/sifen/xsd"
           elementFormDefault="qualified">
  <xs:element name="rDE">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="dVerFor" type="xs:integer"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""

# La forma del de 2018: sin `targetNamespace`, y con los nombres de grupo de
# entonces. Compila sin una queja; ese es justamente el problema.
XSD_VIEJO = """<?xml version="1.0" encoding="utf-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           elementFormDefault="qualified">
  <xs:element name="rDE">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="dVerFor" type="xs:decimal"/>
        <xs:element name="gCiODE" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""

XML_BIEN = ('<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">'
            '<dVerFor>150</dVerFor></rDE>')
XML_MAL = ('<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">'
           '<noExiste>1</noExiste></rDE>')


class BaseEsquema(SimpleTestCase):

    def setUp(self):
        esquema.reiniciar_cache()
        self.addCleanup(esquema.reiniciar_cache)
        self._archivos = []
        self.addCleanup(self._borrar)

    def _borrar(self):
        for ruta in self._archivos:
            try:
                os.unlink(ruta)
            except OSError:
                pass

    def _xsd(self, contenido):
        fd, ruta = tempfile.mkstemp(suffix='.xsd')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(contenido)
        self._archivos.append(ruta)
        return ruta

    def _con_xsd(self, ruta):
        return override_settings(SIFEN={**SIFEN_PRENDIDO, 'xsd_path': ruta})


class SinXsdNoSeValidaTests(BaseEsquema):
    """La validación es opcional y su ausencia nunca puede romper nada."""

    @override_settings(SIFEN={**SIFEN_PRENDIDO, 'xsd_path': ''})
    def test_sin_ruta_configurada_no_valida_y_no_se_queja(self):
        self.assertFalse(esquema.disponible())
        esquema.validar(XML_MAL)  # no lanza

    @override_settings(SIFEN={**SIFEN_PRENDIDO,
                              'xsd_path': '/no/existe/siRecepDE_v150.xsd'})
    def test_una_ruta_que_no_existe_tampoco_frena_una_emision(self):
        self.assertFalse(esquema.disponible())
        esquema.validar(XML_MAL)

    def test_un_archivo_que_no_es_un_xsd_no_frena_una_emision(self):
        ruta = self._xsd('esto no es un schema')
        with self._con_xsd(ruta):
            self.assertFalse(esquema.disponible())
            esquema.validar(XML_MAL)


@unittest.skipUnless(HAY_XMLSCHEMA,
                     'xmlschema está en requirements-dev.txt, no en el runtime')
class ElXsdEquivocadoSeDescartaTests(BaseEsquema):
    """
    El caso que motivó el guardarraíl: un XSD de otra versión del manual.

    Sin este control, apuntar `SIFEN_XSD_PATH` al «Estructura_DE xsd» que
    publica la DNIT dejaba el sistema sin poder emitir ni un documento, y el
    mensaje hablaba del XML —que estaba bien— en vez del XSD.
    """

    def test_un_xsd_sin_el_namespace_del_sifen_no_se_usa(self):
        with self._con_xsd(self._xsd(XSD_VIEJO)):
            self.assertFalse(esquema.disponible())

    def test_y_sobre_todo_no_invalida_un_xml_que_esta_bien(self):
        with self._con_xsd(self._xsd(XSD_VIEJO)):
            esquema.validar(XML_BIEN)  # no lanza
            esquema.validar(XML_MAL)   # tampoco: no hay con qué juzgarlo

    def test_el_viejo_compila_sin_error_que_es_por_lo_que_engana(self):
        # Si no compilara, alcanzaba con el `except` que ya estaba. Este test
        # existe para dejar claro por qué hizo falta mirar el namespace.
        import xmlschema as xs
        cargado = xs.XMLSchema(self._xsd(XSD_VIEJO))
        self.assertEqual(cargado.target_namespace, '')


@unittest.skipUnless(HAY_XMLSCHEMA,
                     'xmlschema está en requirements-dev.txt, no en el runtime')
class ConElXsdCorrectoSiValidaTests(BaseEsquema):

    def test_lo_acepta_si_declara_el_namespace_del_sifen(self):
        with self._con_xsd(self._xsd(XSD_BUENO)):
            self.assertTrue(esquema.disponible())

    def test_un_xml_correcto_pasa(self):
        with self._con_xsd(self._xsd(XSD_BUENO)):
            esquema.validar(XML_BIEN)

    def test_un_xml_incorrecto_lanza_y_el_mensaje_nombra_el_campo(self):
        with self._con_xsd(self._xsd(XSD_BUENO)):
            with self.assertRaises(esquema.XmlInvalido) as e:
                esquema.validar(XML_MAL)
        self.assertIn('esquema del SIFEN', str(e.exception))

    def test_un_xml_vacio_no_se_valida(self):
        with self._con_xsd(self._xsd(XSD_BUENO)):
            esquema.validar('')
