"""
Tests del endpoint que resuelve un escaneo del lector FTX-LC123BH5.

Lo que importa acá no es que "encuentre algo", sino que encuentre UNA sola
cosa. El lector existe para que la vendedora no elija: si un escaneo devuelve
una lista, no sirvió de nada. Por eso los tests se concentran en la
exactitud de la resolución y en el orden de precedencia.
"""
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.inventario.models import Stock
from apps.productos.models import Categoria, Producto, Variante
from apps.usuarios.models import Usuario

EAN_A = '7501031311309'
EAN_B = '5449000000996'


class EscaneoTestBase(APITestCase):

    def setUp(self):
        self.categoria = Categoria.objects.create(nombre='Porcelanatos')
        self.producto = Producto.objects.create(
            nombre='Porcelanato Roma', categoria=self.categoria,
            precio_base=Decimal('185000'),
        )
        self.beige = Variante.objects.create(
            producto=self.producto, color='Beige', codigo_barras=EAN_A)
        self.gris = Variante.objects.create(
            producto=self.producto, color='Gris')

        # El Stock lo crea un post_save de Variante; se le pone cantidad para
        # que la consulta lo devuelva como disponible.
        for variante in (self.beige, self.gris):
            stock = Stock.objects.get(variante=variante)
            stock.cantidad = Decimal('50')
            stock.save(update_fields=['cantidad'])

        self.vendedor = Usuario.objects.create_user(
            username='vendedor_escaneo', password='x', rol='vendedor',
            nombre_completo='Vendedor Prueba')
        self.deposito = Usuario.objects.create_user(
            username='deposito_escaneo', password='x', rol='deposito',
            nombre_completo='Deposito Prueba')

    def escanear(self, codigo, usuario=None):
        self.client.force_authenticate(usuario or self.vendedor)
        return self.client.get(reverse('escanear-codigo'), {'codigo': codigo})


class ResolucionTests(EscaneoTestBase):

    def test_encuentra_la_variante_por_su_ean(self):
        r = self.escanear(EAN_A)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.data['encontrado'])
        self.assertFalse(r.data['ambiguo'])
        self.assertEqual(r.data['coincidencia'], 'codigo_barras')
        self.assertEqual(r.data['resultado']['variante_id'], self.beige.id)

    def test_ignora_el_enter_que_manda_el_lector(self):
        """
        El lector tiene configurado un Enter como sufijo. Si ese \\r\\n llega
        al backend sin limpiar, la búsqueda exacta no matchea y el escaneo
        parece "no encontrado" aunque el código esté cargado.
        """
        r = self.escanear(EAN_A + '\r\n')
        self.assertTrue(r.data['encontrado'])
        self.assertEqual(r.data['resultado']['variante_id'], self.beige.id)

    def test_tambien_resuelve_por_sku(self):
        r = self.escanear(self.gris.sku)
        self.assertTrue(r.data['encontrado'])
        self.assertEqual(r.data['coincidencia'], 'sku')
        self.assertEqual(r.data['resultado']['variante_id'], self.gris.id)

    def test_el_codigo_de_barras_le_gana_al_sku(self):
        """
        Si un SKU coincide con el código de barras de OTRA variante, manda el
        código de barras: es lo que efectivamente está pegado en la caja.
        """
        self.gris.sku = EAN_A
        self.gris.save(update_fields=['sku'])
        r = self.escanear(EAN_A)
        self.assertEqual(r.data['resultado']['variante_id'], self.beige.id)

    def test_el_codigo_de_producto_con_varias_variantes_es_ambiguo(self):
        r = self.escanear(self.producto.codigo)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.data['encontrado'])
        self.assertTrue(r.data['ambiguo'])
        self.assertEqual(r.data['total'], 2)

    def test_codigo_desconocido_da_404_con_mensaje_util(self):
        r = self.escanear('2000000000428')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(r.data['encontrado'])
        self.assertIn('2000000000428', r.data['mensaje'])

    def test_codigo_vacio_es_400(self):
        r = self.escanear('')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_devuelve_variantes_dadas_de_baja(self):
        self.beige.activa = False
        self.beige.save(update_fields=['activa'])
        r = self.escanear(EAN_A)
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_exige_estar_autenticado(self):
        self.client.force_authenticate(None)
        r = self.client.get(reverse('escanear-codigo'), {'codigo': EAN_A})
        self.assertIn(r.status_code, (status.HTTP_401_UNAUTHORIZED,
                                      status.HTTP_403_FORBIDDEN))


class AsignacionTests(EscaneoTestBase):

    def asignar(self, variante, codigo, usuario=None):
        self.client.force_authenticate(usuario or self.deposito)
        return self.client.post(reverse('asignar-codigo-barras'),
                                {'variante_id': variante.id, 'codigo': codigo},
                                format='json')

    def test_el_deposito_puede_asignar_un_codigo(self):
        r = self.asignar(self.gris, EAN_B)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.gris.refresh_from_db()
        self.assertEqual(self.gris.codigo_barras, EAN_B)

    def test_asignado_queda_escaneable_enseguida(self):
        self.asignar(self.gris, EAN_B)
        r = self.escanear(EAN_B)
        self.assertEqual(r.data['resultado']['variante_id'], self.gris.id)

    def test_codigo_vacio_borra_la_asociacion(self):
        r = self.asignar(self.beige, '')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.beige.refresh_from_db()
        self.assertEqual(self.beige.codigo_barras, '')

    def test_un_codigo_ya_usado_da_409_y_dice_de_quien_es(self):
        r = self.asignar(self.gris, EAN_A)
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('Porcelanato Roma', r.data['error'])
        self.gris.refresh_from_db()
        self.assertEqual(self.gris.codigo_barras, '')

    def test_un_ean_con_el_dv_mal_se_rechaza(self):
        r = self.asignar(self.gris, '7501031311300')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.gris.refresh_from_db()
        self.assertEqual(self.gris.codigo_barras, '')

    def test_el_vendedor_no_puede_asignar(self):
        """
        Asignar mal un código hace que la caja cobre otro producto. Es una
        operación de depósito, no de showroom.
        """
        r = self.asignar(self.gris, EAN_B, usuario=self.vendedor)
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_variante_inexistente_da_404(self):
        self.client.force_authenticate(self.deposito)
        r = self.client.post(reverse('asignar-codigo-barras'),
                             {'variante_id': 999999, 'codigo': EAN_B},
                             format='json')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class ConsultaRapidaConCodigoTests(EscaneoTestBase):
    """La consulta rápida (la que usa el buscador) también acepta el escaneo."""

    def test_encuentra_por_codigo_de_barras(self):
        self.client.force_authenticate(self.vendedor)
        r = self.client.get(reverse('stock-consulta-rapida'), {'q': EAN_A})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['total'], 1)
        self.assertEqual(r.data['resultados'][0]['variante_id'], self.beige.id)

    def test_el_resultado_incluye_el_codigo_de_barras(self):
        self.client.force_authenticate(self.vendedor)
        r = self.client.get(reverse('stock-consulta-rapida'), {'q': 'Roma'})
        codigos = {x['sku']: x['codigo_barras'] for x in r.data['resultados']}
        self.assertEqual(codigos[self.beige.sku], EAN_A)
        self.assertEqual(codigos[self.gris.sku], '')
