"""
La marca obligatoria del ambiente de pruebas de la DNIT.

De dónde sale: `Guia de Pruebas para e-kuatia.pdf` §2, "Set de Pruebas". Pide
un texto literal en dos lugares —la razón social del emisor y la descripción
del primer ítem— para que un documento de prueba no pueda pasar por uno real.
El resto de los datos tienen que ser los verdaderos, los de Marangatú.

Por qué hay tests de esto y no se confía en la librería: se revisó `xmlgen` y
su opción `config.test` **no marca el documento de ninguna manera**. Es
andamiaje que quedó de la implementación de la NT 013 en 2023, cuando una
fórmula del IVA entró a regir en test un mes antes que en producción; las dos
fechas ya pasaron y hoy los dos caminos calculan igual. Sin el bloque de
`payload._marcar_como_prueba()` los documentos de la habilitación saldrían sin
la leyenda, y la DNIT los devolvería.
"""
from django.test import TestCase, override_settings

from apps.facturacion import payload

from .factories import (DATOS_FISCALES_COMPLETOS, RUC_RECEPTOR, SIFEN_PRENDIDO,
                        crear_pago, crear_pedido, crear_sesion, crear_usuario,
                        crear_variante)
from apps.facturacion.emisor import crear_documento

SIFEN_PRODUCCION = dict(SIFEN_PRENDIDO, ambiente='produccion')

# Literal de la Guía de Pruebas §2. Se escribe entero acá, aparte de la
# constante del código: si alguien la edita por accidente, este test falla.
LEYENDA = ('DOCUMENTO ELECTRÓNICO SIN VALOR COMERCIAL NI FISCAL - '
           'GENERADO EN AMBIENTE DE PRUEBA')


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class AmbienteDePruebasTests(TestCase):

    databases = {'default', 'sync'}

    _n = 0

    def _documento(self, cantidad_items=1):
        AmbienteDePruebasTests._n += 1
        usuario = crear_usuario(username=f'cajero_amb{AmbienteDePruebasTests._n}')
        items = [(crear_variante(), 1, 100000) for _ in range(cantidad_items)]
        pedido = crear_pedido(usuario, items)
        sesion = crear_sesion(usuario)
        pago = crear_pago(pedido, sesion, usuario, 100000 * cantidad_items)
        return crear_documento(pago, receptor={
            'ruc': RUC_RECEPTOR, 'razon_social': 'Cliente SRL'})

    def test_la_leyenda_es_exactamente_la_de_la_guia(self):
        self.assertEqual(payload.LEYENDA_AMBIENTE_PRUEBA, LEYENDA)

    def test_en_test_la_razon_social_del_emisor_lleva_la_leyenda(self):
        cuerpo = payload.construir(self._documento())
        self.assertEqual(cuerpo['params']['razonSocial'], LEYENDA)
        self.assertEqual(cuerpo['params']['nombreFantasia'], LEYENDA)

    def test_en_test_el_primer_item_lleva_la_leyenda(self):
        cuerpo = payload.construir(self._documento(cantidad_items=3))
        self.assertEqual(cuerpo['data']['items'][0]['descripcion'], LEYENDA)

    def test_solo_el_primer_item_se_marca(self):
        # La guía dice "el primer ítem de mercadería". Marcar todos borraría
        # el detalle de la venta y dejaría el documento sin nada que revisar.
        cuerpo = payload.construir(self._documento(cantidad_items=3))
        descripciones = [i['descripcion'] for i in cuerpo['data']['items']]
        self.assertEqual(descripciones[0], LEYENDA)
        for otra in descripciones[1:]:
            self.assertNotEqual(otra, LEYENDA)

    def test_la_marca_no_toca_los_importes(self):
        # Es solo texto: si cambiara un monto, el documento no cuadraría y el
        # SIFEN lo rechazaría por una razón que no tiene nada que ver.
        documento = self._documento(cantidad_items=2)
        sin_marcar = payload.construir_data(documento)
        marcado = payload.construir(documento)['data']
        for antes, despues in zip(sin_marcar['items'], marcado['items']):
            self.assertEqual(antes['precioUnitario'], despues['precioUnitario'])
            self.assertEqual(antes['cantidad'], despues['cantidad'])
            self.assertEqual(antes['descuento'], despues['descuento'])

    def test_los_datos_reales_del_emisor_se_conservan(self):
        # La guía es explícita: salvo la razón social, todo lo del emisor tiene
        # que ser el dato real registrado en Marangatú.
        cuerpo = payload.construir(self._documento())
        self.assertEqual(cuerpo['params']['ruc'], DATOS_FISCALES_COMPLETOS['ruc'])
        self.assertEqual(cuerpo['params']['timbradoNumero'],
                         str(DATOS_FISCALES_COMPLETOS['timbrado']))

    @override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS,
                       SIFEN=SIFEN_PRODUCCION)
    def test_en_produccion_NO_se_marca_nada(self):
        # Lo importante del par de tests. Una factura real que saliera con la
        # leyenda de prueba sería un problema tributario, no un detalle.
        documento = self._documento()
        cuerpo = payload.construir(documento)
        self.assertEqual(cuerpo['params']['razonSocial'],
                         DATOS_FISCALES_COMPLETOS['razon_social'])
        self.assertNotEqual(cuerpo['data']['items'][0]['descripcion'], LEYENDA)

    @override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS,
                       SIFEN=SIFEN_PRODUCCION)
    def test_en_ambiente_de_pruebas_responde_segun_el_ambiente(self):
        self.assertFalse(payload.en_ambiente_de_pruebas())

    def test_en_ambiente_de_pruebas_por_defecto_es_true(self):
        # El default es 'test' a propósito: si alguien se olvida de declarar el
        # ambiente, el sistema se comporta como si fuera prueba. Equivocarse
        # hacia "producción" sería mucho peor.
        self.assertTrue(payload.en_ambiente_de_pruebas())
