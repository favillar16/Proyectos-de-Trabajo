"""
Que cada edición del catálogo quede anotada, y que aplicar lo del otro nodo no
genere un rebote.
"""
from django.test import TestCase

from apps.productos.models import Categoria, Producto
from apps.productos.tests.factories import crear_producto
from apps.sync.contexto import aplicacion_remota
from apps.sync.models import CambioSync


class RegistroDeCambiosTest(TestCase):
    databases = {'default', 'sync'}

    def test_crear_un_producto_anota_un_alta(self):
        producto = crear_producto()

        cambio = CambioSync.objects.get(modelo='productos.Producto', uid=producto.uid)
        self.assertEqual(cambio.operacion, CambioSync.ALTA)
        self.assertEqual(cambio.datos['nombre'], producto.nombre)
        # La FK sale como uid del destino, nunca como el entero de esta base.
        self.assertEqual(cambio.datos['categoria'], str(producto.categoria.uid))

    def test_modificar_anota_un_cambio_aparte(self):
        producto = crear_producto()
        CambioSync.objects.all().delete()

        producto.nombre = 'Porcelanato Roma Renombrado'
        producto.save()

        cambio = CambioSync.objects.get(modelo='productos.Producto', uid=producto.uid)
        self.assertEqual(cambio.operacion, CambioSync.CAMBIO)
        self.assertEqual(cambio.datos['nombre'], 'Porcelanato Roma Renombrado')

    def test_borrar_anota_una_baja_sin_datos(self):
        producto = crear_producto()
        uid = producto.uid
        CambioSync.objects.all().delete()

        producto.delete()

        cambio = CambioSync.objects.get(modelo='productos.Producto', uid=uid)
        self.assertEqual(cambio.operacion, CambioSync.BAJA)
        # En una baja alcanza con modelo + uid: mandar la fila entera sería
        # pedirle al otro lado que la reconstruya para borrarla.
        self.assertEqual(cambio.datos, {})

    def test_aplicar_lo_del_otro_nodo_no_vuelve_a_anotarse(self):
        """
        Sin esta guarda el sync rebota para siempre: el servidor aplica lo que
        mandó la notebook, lo anota como cambio propio y se lo devuelve.
        """
        with aplicacion_remota():
            Categoria.objects.create(nombre='Aplicada de afuera', descripcion='')

        self.assertEqual(CambioSync.objects.count(), 0)

    def test_el_momento_del_cambio_es_el_de_la_fila(self):
        """El conflicto se resuelve por `actualizado_en`, así que el registro
        tiene que llevar ese valor y no la hora en que corrió el signal."""
        producto = crear_producto()
        cambio = CambioSync.objects.get(modelo='productos.Producto', uid=producto.uid)
        producto.refresh_from_db()
        self.assertEqual(cambio.momento, producto.actualizado_en)

    def test_el_stock_no_se_sincroniza(self):
        """
        `Stock` se crea solo por signal al crear una variante. No está en el
        alcance del sync —es un saldo corriente, no un valor— y no debe
        aparecer en el registro.
        """
        crear_producto()
        modelos = set(CambioSync.objects.values_list('modelo', flat=True))
        self.assertNotIn('inventario.Stock', modelos)
        self.assertNotIn('inventario.MovimientoStock', modelos)
