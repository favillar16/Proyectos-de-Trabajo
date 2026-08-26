"""
Los endpoints que consume el agente de la notebook.
"""
import shutil
import tempfile

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.productos.models import Producto
from apps.productos.tests.factories import crear_producto
from apps.sync.models import CambioSync, EstadoSync
from apps.sync.tests.test_aplicar import cambio_de

TOKEN = 'token-de-prueba-para-el-sync'


@override_settings(SYNC={'token': TOKEN})
class RecibirCambiosTest(TestCase):
    databases = {'default', 'sync'}

    def setUp(self):
        self.client = APIClient()

    def _post(self, cuerpo, token=TOKEN):
        cabeceras = {'HTTP_X_SYNC_TOKEN': token} if token is not None else {}
        return self.client.post('/api/v1/sync/cambios/', cuerpo,
                                format='json', **cabeceras)

    def test_sin_token_no_entra(self):
        self.assertEqual(self._post({'nodo': 'X', 'cambios': []}, token=None).status_code, 403)

    def test_con_token_equivocado_no_entra(self):
        self.assertEqual(self._post({'nodo': 'X', 'cambios': []}, token='otro').status_code, 403)

    @override_settings(SYNC={'token': ''})
    def test_sin_token_configurado_los_endpoints_estan_cerrados(self):
        """Mejor que no anden a que anden abiertos."""
        self.assertEqual(self._post({'nodo': 'X', 'cambios': []}, token='').status_code, 403)

    def test_aplica_el_lote_y_devuelve_el_recuento(self):
        producto = crear_producto(nombre='Desde la notebook')
        cambio = cambio_de(producto, CambioSync.ALTA)
        uid = producto.uid
        producto.delete()

        respuesta = self._post({'nodo': 'NOTEBOOK-ANA', 'cambios': [cambio]})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['aplicados'], 1)
        self.assertTrue(Producto.objects.filter(uid=uid).exists())

    def test_deja_registrado_el_estado_del_nodo(self):
        self._post({'nodo': 'NOTEBOOK-ANA', 'cambios': []})
        estado = EstadoSync.objects.get(nodo='NOTEBOOK-ANA')
        self.assertIsNotNone(estado.ultimo_exito)

    def test_un_lote_sin_nodo_se_rechaza(self):
        """Sin saber quién manda no se puede llevar el estado de nadie."""
        self.assertEqual(self._post({'cambios': []}).status_code, 400)

    def test_un_lote_que_no_es_lista_se_rechaza(self):
        self.assertEqual(self._post({'nodo': 'X', 'cambios': 'todo'}).status_code, 400)

    def test_un_cambio_sin_uid_se_rechaza_antes_de_tocar_la_base(self):
        respuesta = self._post({
            'nodo': 'X',
            'cambios': [{'modelo': 'productos.Producto', 'operacion': 'alta'}],
        })
        self.assertEqual(respuesta.status_code, 400)

    def test_un_lote_demasiado_grande_se_rechaza(self):
        """
        El agente tiene que poder reintentar por partes: si se corta el WiFi a
        mitad de un lote de 5000, no puede quedar obligado a mandar todo de nuevo.
        """
        cambio = {'modelo': 'productos.Marca', 'uid': 'x', 'operacion': 'alta'}
        respuesta = self._post({'nodo': 'X', 'cambios': [cambio] * 501})
        self.assertEqual(respuesta.status_code, 413)


@override_settings(SYNC={'token': TOKEN})
class EstadoSyncTest(TestCase):
    databases = {'default', 'sync'}

    def test_informa_pendientes_y_conflictos(self):
        crear_producto()   # deja cambios pendientes por el signal

        respuesta = APIClient().get('/api/v1/sync/estado/', HTTP_X_SYNC_TOKEN=TOKEN)

        self.assertEqual(respuesta.status_code, 200)
        self.assertGreater(respuesta.data['cambios_pendientes'], 0)
        self.assertEqual(respuesta.data['conflictos_sin_ver'], 0)


@override_settings(SYNC={'token': TOKEN})
class SubirFotoTest(TestCase):
    databases = {'default', 'sync'}

    def setUp(self):
        # MEDIA_ROOT propio y descartable: si apuntara a la carpeta de siempre,
        # el test dejaría archivos y en la segunda corrida el endpoint
        # contestaría "ya_estaba" en vez de guardar.
        self._tmp = tempfile.mkdtemp()
        self._media = override_settings(MEDIA_ROOT=self._tmp)
        self._media.enable()

    def tearDown(self):
        self._media.disable()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_una_ruta_que_se_escapa_de_media_se_rechaza(self):
        """
        La ruta la manda el otro equipo. Sin validarla, un "../../config/
        settings.py" escribiría fuera de la carpeta de fotos.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile
        archivo = SimpleUploadedFile('x.jpg', b'contenido', content_type='image/jpeg')

        respuesta = APIClient().post(
            '/api/v1/sync/foto/',
            {'archivo': archivo, 'ruta': '../../config/settings.py'},
            format='multipart', HTTP_X_SYNC_TOKEN=TOKEN)

        self.assertEqual(respuesta.status_code, 400)

    def test_una_foto_normal_se_guarda(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        archivo = SimpleUploadedFile('foto.jpg', b'contenido', content_type='image/jpeg')

        respuesta = APIClient().post(
            '/api/v1/sync/foto/',
            {'archivo': archivo, 'ruta': 'productos/test-sync/foto.jpg'},
            format='multipart', HTTP_X_SYNC_TOKEN=TOKEN)

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data['ruta'], 'productos/test-sync/foto.jpg')
