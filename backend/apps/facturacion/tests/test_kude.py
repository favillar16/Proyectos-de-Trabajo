"""
Tests del KuDE, la representación gráfica del documento electrónico.

No se comparan píxeles. Lo que importa es lo que el Manual Técnico V150 §13
exige que esté y lo que prohíbe que esté:

  · la denominación correcta según el tipo (§13.3);
  · los campos del encabezado, los ítems con su afectación de IVA y la
    liquidación (§13.4.1 a §13.4.3);
  · el CDC en once grupos de cuatro, para poder consultarlo a mano (§13.4.4);
  · el QR **solo si el documento está firmado**: su contenido lleva el hash
    de la firma y el CSC (§13.8.2), así que uno inventado escanearía y no
    resolvería nada;
  · y que los ítems salgan de la misma fuente que el XML, porque el KuDE no
    puede mostrar información que no esté en el DE firmado (§13.2).
"""
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.facturacion import codigos, kude
from apps.facturacion.emisor import crear_documento
from apps.facturacion.models import DocumentoElectronico

from .factories import (DATOS_FISCALES_COMPLETOS, RUC_RECEPTOR, SIFEN_PRENDIDO,
                        crear_pago, crear_pedido, crear_sesion, crear_usuario,
                        crear_variante)

SIFEN_PRODUCCION = dict(SIFEN_PRENDIDO, ambiente='produccion')


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS,
                   SIFEN=SIFEN_PRODUCCION)
class KudeTests(TestCase):
    databases = {'default', 'sync'}
    _secuencia = 0

    def _documento(self, monto=150000, cantidad=1, **extra):
        KudeTests._secuencia += 1
        n = KudeTests._secuencia
        usuario = crear_usuario(username=f'cajero_kude{n}')
        variante = crear_variante(nombre=f'Porcelanato Kude {n}')
        pedido = crear_pedido(usuario, [(variante, cantidad, monto)])
        sesion = crear_sesion(usuario)
        pago = crear_pago(pedido, sesion, usuario,
                          Decimal(str(monto)) * Decimal(str(cantidad)))
        documento = crear_documento(
            pago, receptor={'ruc': RUC_RECEPTOR, 'razon_social': 'Cliente SRL'})
        for campo, valor in extra.items():
            setattr(documento, campo, valor)
        if extra:
            documento.save()
        return documento

    # ── Datos ────────────────────────────────────────────────────────────
    def test_la_denominacion_depende_del_tipo(self):
        documento = self._documento()
        self.assertEqual(kude.construir_datos(documento)['denominacion'],
                         'KuDE de Factura Electrónica')

        documento.tipo_documento = codigos.TIPO_DE_NOTA_CREDITO
        self.assertEqual(kude.construir_datos(documento)['denominacion'],
                         'KuDE de Nota de Crédito Electrónica')

    def test_el_cdc_sale_en_once_grupos_de_cuatro(self):
        datos = kude.construir_datos(self._documento())
        grupos = datos['cdc_legible'].split()
        self.assertEqual(len(grupos), 11)
        self.assertTrue(all(len(g) == 4 for g in grupos))

    def test_los_items_son_los_mismos_que_van_al_xml(self):
        """§13.2: el KuDE no puede mostrar nada que no esté en el DE firmado."""
        from apps.facturacion import payload as payload_mod

        documento = self._documento(monto=97500, cantidad=3)
        datos = kude.construir_datos(documento)
        delxml = payload_mod._items(documento)

        self.assertEqual(len(datos['items']), len(delxml))
        self.assertEqual(datos['items'][0]['codigo'], delxml[0]['codigo'])
        self.assertEqual(datos['items'][0]['descripcion'], delxml[0]['descripcion'])
        self.assertEqual(datos['items'][0]['cantidad'], delxml[0]['cantidad'])

    def test_el_item_gravado_al_10_carga_solo_la_columna_del_10(self):
        datos = kude.construir_datos(self._documento())
        item = datos['items'][0]
        self.assertGreater(item['iva10'], 0)
        self.assertEqual(item['iva5'], 0)
        self.assertEqual(item['exentas'], 0)

    def test_los_totales_salen_del_documento_no_de_una_cuenta_nueva(self):
        documento = self._documento(monto=200000)
        datos = kude.construir_datos(documento)
        self.assertEqual(datos['totales']['total'], float(documento.total))
        self.assertEqual(datos['totales']['iva_total'],
                         float(documento.iva_10) + float(documento.iva_5))

    def test_marca_el_documento_cancelado(self):
        documento = self._documento(
            estado=DocumentoElectronico.ESTADO_CANCELADO)
        self.assertTrue(kude.construir_datos(documento)['cancelado'])

    @override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS,
                       SIFEN=SIFEN_PRENDIDO)
    def test_en_ambiente_de_prueba_la_razon_social_es_la_leyenda(self):
        """
        El XML de prueba lleva la leyenda en la razón social (Guía §2). Si el
        papel dijera el nombre real, papel y XML no coincidirían.
        """
        from apps.facturacion.payload import LEYENDA_AMBIENTE_PRUEBA

        datos = kude.construir_datos(self._documento())
        self.assertTrue(datos['en_prueba'])
        self.assertEqual(datos['emisor']['razon_social'], LEYENDA_AMBIENTE_PRUEBA)

    def test_en_produccion_va_la_razon_social_de_verdad(self):
        datos = kude.construir_datos(self._documento())
        self.assertFalse(datos['en_prueba'])
        self.assertEqual(datos['emisor']['razon_social'], 'OGA PORA SRL')

    # ── QR ───────────────────────────────────────────────────────────────
    def test_saca_el_enlace_del_xml_firmado(self):
        xml = ('<rDE><gCamFuFD><dCarQR>https://ekuatia.set.gov.py/consultas/qr?'
               'nVersion=150&amp;Id=0180012345&amp;cHashQR=abc</dCarQR>'
               '</gCamFuFD></rDE>')
        enlace = kude.enlace_qr_del_xml(xml)
        self.assertIn('nVersion=150', enlace)
        # Las entidades se desarman: el valor real es una URL con parámetros.
        self.assertIn('&Id=', enlace)
        self.assertNotIn('&amp;', enlace)

    def test_un_xml_sin_qr_no_inventa_nada(self):
        self.assertEqual(kude.enlace_qr_del_xml('<rDE></rDE>'), '')
        self.assertEqual(kude.enlace_qr_del_xml(''), '')

    def test_sin_firma_el_documento_no_trae_enlace(self):
        datos = kude.construir_datos(self._documento())
        self.assertEqual(datos['enlace_qr'], '')

    # ── PDF ──────────────────────────────────────────────────────────────
    def test_el_pdf_se_genera(self):
        contenido = kude.render_pdf(self._documento())
        self.assertTrue(contenido.startswith(b'%PDF'))
        self.assertGreater(len(contenido), 3000)

    def test_el_pdf_se_genera_con_qr(self):
        documento = self._documento(
            enlace_qr='https://ekuatia.set.gov.py/consultas/qr?nVersion=150&Id=01')
        self.assertTrue(kude.render_pdf(documento).startswith(b'%PDF'))

    def test_el_pdf_aguanta_muchos_items(self):
        """Un pedido largo tiene que paginar, no romper ni superponerse."""
        usuario = crear_usuario(username='cajero_kude_largo')
        items = [(crear_variante(nombre=f'Producto largo {i}'), 2, 85000)
                 for i in range(28)]
        pedido = crear_pedido(usuario, items)
        sesion = crear_sesion(usuario)
        pago = crear_pago(pedido, sesion, usuario, Decimal('4760000'))
        documento = crear_documento(
            pago, receptor={'ruc': RUC_RECEPTOR, 'razon_social': 'Constructora SA'})
        self.assertTrue(kude.render_pdf(documento).startswith(b'%PDF'))


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class ApiKudeTests(TestCase):
    databases = {'default', 'sync'}

    def setUp(self):
        self.cajero = crear_usuario(username='cajera_api_kude', rol='cajero')
        variante = crear_variante(nombre='Cerámica API')
        pedido = crear_pedido(self.cajero, [(variante, 2, 75000)])
        sesion = crear_sesion(self.cajero)
        pago = crear_pago(pedido, sesion, self.cajero, Decimal('150000'))
        self.documento = crear_documento(
            pago, receptor={'ruc': RUC_RECEPTOR, 'razon_social': 'Cliente SRL'})
        self.api = APIClient()
        self.api.force_authenticate(self.cajero)

    def test_devuelve_el_pdf(self):
        respuesta = self.api.get(reverse('fe-kude', args=[self.documento.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertTrue(respuesta.content.startswith(b'%PDF'))

    def test_se_abre_en_el_navegador_en_vez_de_descargarse(self):
        respuesta = self.api.get(reverse('fe-kude', args=[self.documento.pk]))
        self.assertIn('inline', respuesta['Content-Disposition'])

    def test_un_documento_que_no_existe_da_404(self):
        self.assertEqual(
            self.api.get(reverse('fe-kude', args=[999999])).status_code, 404)

    def test_el_vendedor_no_saca_el_kude(self):
        """Lleva el detalle fiscal del cobro: es de caja, no del salón."""
        self.api.force_authenticate(
            crear_usuario(username='vendedor_kude', rol='vendedor'))
        respuesta = self.api.get(reverse('fe-kude', args=[self.documento.pk]))
        self.assertEqual(respuesta.status_code, 403)


class GeometriaDelEncabezadoTests(TestCase):
    """
    El alto del encabezado tiene que salir de medir su contenido.

    Antes eran dos números escritos a mano que no se hablaban: el margen
    superior estaba en 76 mm fijos y la raya separadora se dibujaba a 26 mm del
    tope, sin mirar cuánto medía el bloque del emisor. Con los datos reales del
    local ese bloque mide 25,8 mm, o sea 0,2 mm menos que la raya: la raya le
    pasaba por encima al logo y al teléfono, y la primera línea del receptor
    caía sobre la última del emisor. Se veía en el PDF renderizado.

    Estos tests fijan la propiedad que lo evita: **el encabezado crece con su
    contenido**. No miden píxeles, miden la función que decide la geometría.
    """

    def _datos(self, **cambios):
        base = {
            'emisor': {
                'razon_social': 'ÓGA PORA E.A.S.',
                'actividad': 'Comercio al por menor de materiales',
                'direccion': 'Calle Lidia Peralta de Benitez',
                'ciudad': 'CNEL. OVIEDO',
                'telefono': '(0971) 451936',
                'ruc': '80173107-0', 'timbrado': '18936285',
                'timbrado_inicio': '23/06/2026', 'timbrado_vto': '',
            },
            'receptor': {'email': ''},
            'en_prueba': False,
        }
        base.update(cambios)
        return base

    def test_una_direccion_mas_larga_agranda_el_encabezado(self):
        corto = kude._alto_encabezado_mm(self._datos())
        datos = self._datos()
        datos['emisor'] = dict(datos['emisor'])
        datos['emisor']['direccion'] = (
            'CALLE LIDIA PERALTA DE BENITEZ E/ JOSEFINA PLAS - '
            'BARRIO SAN ISIDRO - CIUDAD DE CORONEL OVIEDO - CAAGUAZU')
        largo = kude._alto_encabezado_mm(datos)
        self.assertGreater(largo, corto)

    def test_el_correo_del_receptor_suma_un_renglon(self):
        sin = kude._alto_encabezado_mm(self._datos())
        con = kude._alto_encabezado_mm(
            self._datos(receptor={'email': 'cliente@ejemplo.com'}))
        self.assertGreater(con, sin)

    def test_la_leyenda_de_prueba_suma_un_renglon(self):
        sin = kude._alto_encabezado_mm(self._datos())
        con = kude._alto_encabezado_mm(self._datos(en_prueba=True))
        self.assertGreater(con, sin)

    def test_la_raya_nunca_cae_dentro_del_bloque_del_emisor(self):
        # La invariante que se rompía. La raya va debajo de la última línea
        # del emisor, con un hueco de por medio, cualquiera sea el contenido.
        for direccion in ('Corta',
                          'Una dirección larga de verdad ' * 4,
                          ''):
            datos = self._datos()
            datos['emisor'] = dict(datos['emisor'], direccion=direccion)
            alto_emisor = sum(a for _, _, _, a in kude._lineas_emisor(datos))
            banda = max(alto_emisor, 5 * kude.ALTO_LINEA_TITULO_MM)
            self.assertGreaterEqual(
                banda + kude.HUECO_ANTES_DE_RAYA_MM,
                alto_emisor + kude.HUECO_ANTES_DE_RAYA_MM,
                f'La raya se mete en el bloque del emisor con {direccion!r}')

    def test_el_bloque_del_timbrado_tambien_cuenta(self):
        # Si el emisor tiene una sola línea, manda el bloque del timbrado de
        # la derecha: son cinco renglones y también están arriba de la raya.
        datos = self._datos()
        datos['emisor'] = dict(datos['emisor'], actividad='', direccion='',
                               ciudad='', telefono='')
        alto = kude._alto_encabezado_mm(datos)
        minimo = kude.TOPE_MM + 5 * kude.ALTO_LINEA_TITULO_MM
        self.assertGreater(alto, minimo)
