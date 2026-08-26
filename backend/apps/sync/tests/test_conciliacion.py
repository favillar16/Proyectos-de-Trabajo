"""
Choques de unicidad entre dos equipos que trabajaron sin verse.

Es el caso que rompe cualquier sync ingenuo. `Producto.codigo` se genera
buscando el primer correlativo libre, así que la notebook offline y el local
sacan POR-004 los dos, y el `uid` —que resuelve la identidad— no evita que el
INSERT muera contra el índice único de `codigo`.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.productos.models import Acabado, Marca, Producto, Variante
from apps.productos.tests.factories import crear_producto, crear_variante
from apps.sync.aplicar import aplicar_lote
from apps.sync.models import CambioSync
from apps.sync.tests.test_aplicar import cambio_de


class CodigosGeneradosTest(TestCase):
    databases = {'default', 'sync'}

    def test_dos_productos_distintos_con_el_mismo_codigo_conviven(self):
        """
        Cargados sin verse, los dos sacaron el mismo código. Son productos
        distintos: entran los dos y el que llega se lleva un código nuevo.
        """
        de_afuera = crear_producto(nombre='Cargado en la notebook')
        cambio = cambio_de(de_afuera, CambioSync.ALTA)
        codigo_repetido = de_afuera.codigo
        uid_afuera = de_afuera.uid
        de_afuera.delete()

        # El local carga otro producto y le toca el mismo correlativo.
        del_local = crear_producto(nombre='Cargado en el local')
        del_local.codigo = codigo_repetido
        del_local.save()

        resultado = aplicar_lote([cambio])

        self.assertEqual(resultado.aplicados, 1)
        self.assertEqual(resultado.conflictos, 0)

        # Están los dos, con códigos distintos.
        recibido = Producto.objects.get(uid=uid_afuera)
        del_local.refresh_from_db()
        self.assertEqual(recibido.nombre, 'Cargado en la notebook')
        self.assertNotEqual(recibido.codigo, del_local.codigo)
        self.assertEqual(del_local.codigo, codigo_repetido)

    def test_el_cambio_de_codigo_se_informa(self):
        """Que un producto haya entrado con otro código no puede ser invisible."""
        de_afuera = crear_producto(nombre='De la notebook')
        cambio = cambio_de(de_afuera, CambioSync.ALTA)
        codigo_repetido = de_afuera.codigo
        de_afuera.delete()
        del_local = crear_producto(nombre='Del local')
        del_local.codigo = codigo_repetido
        del_local.save()

        resultado = aplicar_lote([cambio])

        self.assertEqual(len(resultado.detalle), 1)
        texto = ' '.join(resultado.detalle[0]['ajustes'])
        self.assertIn('codigo', texto)
        self.assertIn(codigo_repetido, texto)

    def test_un_sku_repetido_tampoco_frena_a_la_variante(self):
        variante = crear_variante(color='Arena')
        cambio = cambio_de(variante, CambioSync.ALTA)
        sku_repetido = variante.sku
        uid = variante.uid
        producto = variante.producto
        variante.delete()

        otra = crear_variante(producto=producto, color='Otro Color')
        otra.sku = sku_repetido
        otra.save()

        resultado = aplicar_lote([cambio])

        self.assertEqual(resultado.aplicados, 1)
        recibida = Variante.objects.get(uid=uid)
        self.assertNotEqual(recibida.sku, sku_repetido)


class FusionPorClaveNaturalTest(TestCase):
    databases = {'default', 'sync'}

    def test_la_misma_marca_cargada_dos_veces_no_se_duplica(self):
        """
        "KLAUKOL" en la notebook y "KLAUKOL" en el local no son dos marcas.
        Se fusionan en una, y los dos equipos quedan usando el mismo uid.
        """
        marca_afuera = Marca.objects.create(nombre='KLAUKOL')
        cambio = cambio_de(marca_afuera, CambioSync.ALTA,
                           momento=timezone.now() + timedelta(minutes=1))
        uid_afuera = marca_afuera.uid
        marca_afuera.delete()

        marca_local = Marca.objects.create(nombre='KLAUKOL')
        uid_local = marca_local.uid
        self.assertNotEqual(uid_local, uid_afuera)

        resultado = aplicar_lote([cambio])

        self.assertEqual(resultado.aplicados, 1)
        self.assertEqual(Marca.objects.filter(nombre='KLAUKOL').count(), 1)
        # La fila local sobrevive pero adopta el uid que vino: de acá en más
        # los dos equipos hablan de la misma.
        marca_local.refresh_from_db()
        self.assertEqual(marca_local.uid, uid_afuera)

    def test_lo_mismo_con_los_acabados(self):
        acabado_afuera = Acabado.objects.create(nombre='Mate')
        cambio = cambio_de(acabado_afuera, CambioSync.ALTA,
                           momento=timezone.now() + timedelta(minutes=1))
        acabado_afuera.delete()
        Acabado.objects.create(nombre='Mate')

        aplicar_lote([cambio])

        self.assertEqual(Acabado.objects.filter(nombre='Mate').count(), 1)

    def test_la_misma_variante_del_mismo_producto_se_fusiona(self):
        """
        La clave natural de una variante son sus atributos: mismo producto,
        mismo color, mismo acabado y misma medida es la misma variante.
        """
        producto = crear_producto()
        variante_afuera = crear_variante(producto=producto, color='Beige')
        cambio = cambio_de(variante_afuera, CambioSync.ALTA,
                           momento=timezone.now() + timedelta(minutes=1))
        uid_afuera = variante_afuera.uid
        variante_afuera.delete()

        variante_local = crear_variante(producto=producto, color='Beige')

        resultado = aplicar_lote([cambio])

        self.assertEqual(resultado.conflictos, 0)
        self.assertEqual(
            Variante.objects.filter(producto=producto, color='Beige').count(), 1)
        variante_local.refresh_from_db()
        self.assertEqual(variante_local.uid, uid_afuera)


class CodigoDeBarrasTest(TestCase):
    databases = {'default', 'sync'}

    def test_un_ean_repetido_entra_vacio_y_no_pisa_al_que_ya_estaba(self):
        """
        El código de barras es el EAN impreso en la caja. Si dos variantes
        distintas dicen tener el mismo, hay un error de carga que ningún
        automatismo puede resolver: entra sin código, para no romper el lector
        de la que ya estaba bien.
        """
        producto = crear_producto()
        de_afuera = crear_variante(producto=producto, color='Gris',
                                   codigo_barras='7891234567895')
        cambio = cambio_de(de_afuera, CambioSync.ALTA)
        uid = de_afuera.uid
        de_afuera.delete()

        del_local = crear_variante(producto=producto, color='Negro',
                                   codigo_barras='7891234567895')

        resultado = aplicar_lote([cambio])

        self.assertEqual(resultado.aplicados, 1)
        recibida = Variante.objects.get(uid=uid)
        self.assertIsNone(recibida.codigo_barras)
        del_local.refresh_from_db()
        self.assertEqual(del_local.codigo_barras, '7891234567895')

    def test_un_ean_libre_viaja_normal(self):
        variante = crear_variante(color='Blanco', codigo_barras='7790001112224')
        cambio = cambio_de(variante, CambioSync.ALTA)
        uid = variante.uid
        variante.delete()

        aplicar_lote([cambio])

        self.assertEqual(Variante.objects.get(uid=uid).codigo_barras, '7790001112224')
