"""
Lectura de código de barras con el lector FTX LC123BH5.

El lector trabaja como un teclado: al disparar, "tipea" el código y manda un
Enter. Del lado del sistema todo se reduce a buscar una variante por ese texto,
así que lo que se prueba acá es esa búsqueda y la unicidad del código.
"""
from django.db.utils import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.productos.models import Variante
from apps.productos.tests.factories import crear_producto, crear_usuario, crear_variante
from apps.usuarios.models import Usuario


class CodigoDeBarrasTest(TestCase):

    def setUp(self):
        self.producto = crear_producto()

    def test_una_variante_puede_guardar_su_codigo_de_barras(self):
        variante = crear_variante(producto=self.producto, color='Beige',
                                  codigo_barras='7891234567895')

        variante.refresh_from_db()
        self.assertEqual(variante.codigo_barras, '7891234567895')

    def test_dos_variantes_no_pueden_compartir_el_codigo_de_barras(self):
        crear_variante(producto=self.producto, color='Beige',
                       codigo_barras='7891234567895')

        with self.assertRaises(IntegrityError):
            crear_variante(producto=self.producto, color='Gris',
                           codigo_barras='7891234567895')

    def test_muchas_variantes_pueden_no_tener_codigo_de_barras(self):
        """
        La mayoría de los porcelanatos vienen sin código de fábrica. Que dos
        variantes no tengan código no puede ser un conflicto.
        """
        crear_variante(producto=self.producto, color='Beige')
        crear_variante(producto=self.producto, color='Gris')
        crear_variante(producto=self.producto, color='Negro')

        self.assertEqual(
            Variante.objects.filter(codigo_barras__isnull=True).count(), 3)

    def test_un_codigo_vacio_se_guarda_como_sin_codigo(self):
        """
        Si la pantalla manda el campo vacío (el operario borró lo escaneado),
        tiene que quedar como "sin código" y no como cadena vacía, porque dos
        cadenas vacías chocarían contra la restricción de unicidad.
        """
        primera = crear_variante(producto=self.producto, color='Beige',
                                 codigo_barras='')
        segunda = crear_variante(producto=self.producto, color='Gris',
                                 codigo_barras='   ')

        self.assertIsNone(primera.codigo_barras)
        self.assertIsNone(segunda.codigo_barras)

    def test_se_le_sacan_los_espacios_al_codigo(self):
        variante = crear_variante(producto=self.producto, color='Beige',
                                  codigo_barras='  7891234567895  ')

        self.assertEqual(variante.codigo_barras, '7891234567895')


class BusquedaPorCodigoDeBarrasApiTest(TestCase):
    """El endpoint que consulta el sistema cada vez que se dispara el lector."""

    URL = '/api/v1/productos/variantes/por-codigo-barras/'

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(
            user=crear_usuario('deposito-lector', Usuario.ROL_DEPOSITO))
        self.producto = crear_producto(nombre='Porcelanato Roma')
        self.variante = crear_variante(
            producto=self.producto, color='Beige',
            codigo_barras='7891234567895',
        )

    def test_devuelve_la_variante_con_su_producto(self):
        respuesta = self.client.get(self.URL, {'codigo': '7891234567895'})

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.data['encontrado'])
        self.assertEqual(respuesta.data['variante']['id'], self.variante.id)
        self.assertEqual(respuesta.data['producto']['nombre'], 'Porcelanato Roma')

    def test_un_codigo_desconocido_no_es_un_error(self):
        """
        Al dar de alta mercadería nueva se escanea un código que todavía no
        está: la pantalla tiene que poder ofrecer cargarlo, no mostrar un error.
        """
        respuesta = self.client.get(self.URL, {'codigo': '0000000000000'})

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.data['encontrado'])
        self.assertEqual(respuesta.data['codigo'], '0000000000000')

    def test_tambien_encuentra_por_sku(self):
        """Algunas etiquetas traen impreso el SKU y no un código de fábrica."""
        respuesta = self.client.get(self.URL, {'codigo': self.variante.sku})

        self.assertTrue(respuesta.data['encontrado'])
        self.assertEqual(respuesta.data['variante']['id'], self.variante.id)

    def test_no_distingue_mayusculas_de_minusculas(self):
        respuesta = self.client.get(self.URL, {'codigo': self.variante.sku.lower()})

        self.assertTrue(respuesta.data['encontrado'])

    def test_ignora_los_espacios_que_agregue_el_lector(self):
        respuesta = self.client.get(self.URL, {'codigo': ' 7891234567895 '})

        self.assertTrue(respuesta.data['encontrado'])

    def test_sin_codigo_avisa_que_falta_el_parametro(self):
        respuesta = self.client.get(self.URL)

        self.assertEqual(respuesta.status_code, 400)

    def test_encuentra_tambien_una_variante_dada_de_baja(self):
        """
        Si el código quedó tomado por mercadería discontinuada hay que
        avisarlo, no dejar que se cargue de nuevo en otra variante.
        """
        self.variante.activa = False
        self.variante.save()

        respuesta = self.client.get(self.URL, {'codigo': '7891234567895'})

        self.assertTrue(respuesta.data['encontrado'])

    def test_todos_los_roles_pueden_usar_el_lector(self):
        for rol in (Usuario.ROL_ADMIN, Usuario.ROL_ENCARGADA_VENTAS,
                    Usuario.ROL_VENDEDOR, Usuario.ROL_CAJERO, Usuario.ROL_DEPOSITO):
            with self.subTest(rol=rol):
                self.client.force_authenticate(
                    user=crear_usuario(f'lector-{rol}', rol))
                respuesta = self.client.get(self.URL, {'codigo': '7891234567895'})
                self.assertEqual(respuesta.status_code, 200)

    def test_sin_iniciar_sesion_no_se_puede_consultar(self):
        self.client.force_authenticate(user=None)

        respuesta = self.client.get(self.URL, {'codigo': '7891234567895'})

        self.assertEqual(respuesta.status_code, 401)

    def test_el_buscador_general_tambien_encuentra_por_codigo_de_barras(self):
        respuesta = self.client.get('/api/v1/productos/', {'search': '7891234567895'})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['count'], 1)
        self.assertEqual(respuesta.data['results'][0]['nombre'], 'Porcelanato Roma')
