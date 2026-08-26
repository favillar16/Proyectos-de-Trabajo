"""
El puente entre "antes" y "después" del sync.

El registro de cambios solo tiene lo que pasó desde que el sync está
instalado. Lo editado en la notebook antes de eso es invisible, y el primer
`pg_dump` desde el servidor se lo lleva puesto — pasó de verdad con las
correcciones de precio del 25/08/2026. `sync_comparar` encuentra esas
diferencias viejas y las marca para que viajen.

El servidor se simula reemplazando la única función que habla por red
(`pedir_json`), así el test ejercita la comparación real sin levantar un
segundo Django.
"""
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.productos.models import Producto
from apps.productos.tests.factories import crear_producto
from apps.sync.models import CambioSync
from apps.sync.serializacion import serializar

TOKEN = 'token-de-prueba-para-el-sync'


@override_settings(SYNC={'token': TOKEN})
class CatalogoEndpointTest(TestCase):
    databases = {'default', 'sync'}

    def test_devuelve_las_filas_serializadas(self):
        producto = crear_producto(nombre='Para comparar')

        r = APIClient().get('/api/v1/sync/catalogo/?modelo=productos.Producto',
                            HTTP_X_SYNC_TOKEN=TOKEN)

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['total'], 1)
        fila = r.data['filas'][0]
        self.assertEqual(fila['uid'], str(producto.uid))
        self.assertEqual(fila['datos']['nombre'], 'Para comparar')

    def test_un_modelo_fuera_del_alcance_se_rechaza(self):
        r = APIClient().get('/api/v1/sync/catalogo/?modelo=inventario.Stock',
                            HTTP_X_SYNC_TOKEN=TOKEN)
        self.assertEqual(r.status_code, 400)

    def test_sin_token_no_entra(self):
        r = APIClient().get('/api/v1/sync/catalogo/?modelo=productos.Producto')
        self.assertEqual(r.status_code, 403)

    def test_pagina_con_orden_estable(self):
        """
        Sin un orden fijo, dos páginas pueden repetir u omitir filas y la
        comparación acusaría diferencias que no existen.
        """
        for i in range(5):
            crear_producto(nombre=f'Producto {i}')

        vistos = []
        for desde in (0, 2, 4):
            r = APIClient().get(
                f'/api/v1/sync/catalogo/?modelo=productos.Producto&desde={desde}&limite=2',
                HTTP_X_SYNC_TOKEN=TOKEN)
            vistos += [f['uid'] for f in r.data['filas']]

        self.assertEqual(len(vistos), 5)
        self.assertEqual(len(set(vistos)), 5)


@override_settings(SYNC={'token': TOKEN}, NODO={'rol': 'notebook', 'nombre': 'NOTEBOOK',
                                                'red_wifi': 'OGA PORA'})
class CompararTest(TestCase):
    databases = {'default', 'sync'}

    def _correr(self, servidor_dice, *args):
        """
        Corre el comando con un servidor simulado.

        `servidor_dice` es {uid: datos} — lo que tendría el servidor.
        """
        def falso_pedir_json(url, token):
            if '/salud/' in url:
                return {'sistema': 'oga-pora', 'rol': 'servidor', 'nombre': 'OGAPORA'}
            return {
                'modelo': 'productos.Producto',
                'total': len(servidor_dice),
                'desde': 0,
                'filas': [
                    {'uid': uid, 'actualizado_en': '2026-08-20T10:00:00-03:00', 'datos': datos}
                    for uid, datos in servidor_dice.items()
                ],
            }

        salida = StringIO()
        with patch('apps.sync.management.commands.sync_comparar.pedir_json', falso_pedir_json):
            call_command('sync_comparar', '--servidor', 'ogapora.local',
                         '--modelo', 'productos.Producto', *args, stdout=salida)
        return salida.getvalue()

    def test_encuentra_un_precio_distinto(self):
        """El caso real: la notebook tiene el precio corregido, el servidor no."""
        producto = crear_producto(precio=Decimal('126262'))
        del_servidor = serializar(producto)
        del_servidor['precio_base'] = '99000'      # el valor viejo, equivocado

        salida = self._correr({str(producto.uid): del_servidor})

        self.assertIn('precio_base', salida)
        self.assertIn('126262', salida)
        self.assertIn('99000', salida)
        # Sin --marcar no se anota nada de más: queda solo el alta del producto
        # (crear_producto además crea su categoría, que se cuenta aparte).
        self.assertEqual(
            CambioSync.objects.filter(modelo='productos.Producto').count(), 1)

    def test_marcar_deja_el_cambio_listo_para_empujar(self):
        producto = crear_producto(precio=Decimal('126262'))
        del_servidor = serializar(producto)
        del_servidor['precio_base'] = '99000'
        CambioSync.objects.all().delete()

        self._correr({str(producto.uid): del_servidor}, '--marcar')

        cambio = CambioSync.objects.get(modelo='productos.Producto', uid=producto.uid)
        self.assertEqual(cambio.operacion, CambioSync.CAMBIO)
        self.assertEqual(cambio.datos['precio_base'], '126262.00')
        self.assertIsNone(cambio.empujado_en)

    def test_una_fila_que_el_servidor_no_tiene_tambien_se_marca(self):
        producto = crear_producto(nombre='Solo en la notebook')
        CambioSync.objects.all().delete()

        salida = self._correr({}, '--marcar')

        self.assertIn('no está en el servidor', salida)
        self.assertTrue(
            CambioSync.objects.filter(modelo='productos.Producto', uid=producto.uid).exists())

    def test_si_todo_coincide_no_marca_nada(self):
        producto = crear_producto()
        CambioSync.objects.all().delete()

        salida = self._correr({str(producto.uid): serializar(producto)}, '--marcar')

        self.assertIn('igual en los dos equipos', salida)
        self.assertEqual(CambioSync.objects.count(), 0)

    def test_el_slug_no_cuenta_como_diferencia(self):
        """Lo genera cada base por su cuenta; no significa nada."""
        producto = crear_producto()
        del_servidor = serializar(producto)
        del_servidor['slug'] = 'otro-slug-distinto'
        CambioSync.objects.all().delete()

        salida = self._correr({str(producto.uid): del_servidor}, '--marcar')

        self.assertIn('igual en los dos equipos', salida)
        self.assertEqual(CambioSync.objects.count(), 0)

    def test_no_compara_contra_algo_que_no_es_el_servidor(self):
        crear_producto()

        def dice_notebook(url, token):
            return {'sistema': 'oga-pora', 'rol': 'notebook', 'nombre': 'OTRA'}

        from django.core.management.base import CommandError
        with patch('apps.sync.management.commands.sync_comparar.pedir_json', dice_notebook):
            with self.assertRaises(CommandError):
                call_command('sync_comparar', '--servidor', 'x', stdout=StringIO())
