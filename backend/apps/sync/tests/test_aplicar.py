"""
Aplicar un lote que llegó del otro nodo: identidad, claves foráneas por uid,
orden de dependencias y resolución de conflictos.

Los tests simulan los dos equipos sobre una sola base: se serializa una fila
(lo que haría la notebook), se borra o se modifica localmente (lo que haría el
servidor mientras tanto) y se aplica el lote. Es la misma mecánica que en la
red real, sin necesidad de levantar dos Django.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.productos.models import Categoria, Producto, Variante
from apps.productos.tests.factories import crear_producto, crear_variante
from apps.sync.aplicar import aplicar_lote
from apps.sync.models import CambioSync, ConflictoSync
from apps.sync.serializacion import serializar


def cambio_de(instancia, operacion=CambioSync.CAMBIO, momento=None, nodo='NOTEBOOK'):
    """Arma el dict que viajaría por la red para esta fila."""
    return {
        'modelo':    f'{instancia._meta.app_label}.{instancia._meta.object_name}',
        'uid':       str(instancia.uid),
        'operacion': operacion,
        'datos':     {} if operacion == CambioSync.BAJA else serializar(instancia),
        'nodo':      nodo,
        'momento':   (momento or instancia.actualizado_en).isoformat(),
    }


class AplicarLoteTest(TestCase):
    databases = {'default', 'sync'}

    # ─── Alta ────────────────────────────────────────────────────────────────

    def test_un_producto_que_no_existe_se_crea_con_el_mismo_uid(self):
        producto = crear_producto(nombre='Cerámica Nueva')
        cambio = cambio_de(producto, CambioSync.ALTA)
        uid, categoria_uid = producto.uid, producto.categoria.uid
        producto.delete()

        resultado = aplicar_lote([cambio])

        self.assertEqual(resultado.aplicados, 1)
        recreado = Producto.objects.get(uid=uid)
        self.assertEqual(recreado.nombre, 'Cerámica Nueva')
        # La FK se resolvió por uid, no por el entero que traía el otro lado.
        self.assertEqual(recreado.categoria.uid, categoria_uid)

    def test_las_claves_primarias_del_otro_nodo_no_se_copian(self):
        """
        El punto de todo el diseño: los enteros no significan lo mismo en las
        dos bases, así que no pueden viajar.
        """
        producto = crear_producto()
        cambio = cambio_de(producto, CambioSync.ALTA)
        self.assertNotIn('id', cambio['datos'])

        pk_original = producto.pk
        producto.delete()
        # Otra fila se queda con ese id libre
        crear_producto(nombre='Ocupa el lugar')

        aplicar_lote([cambio])
        recreado = Producto.objects.get(uid=cambio['uid'])
        self.assertNotEqual(recreado.pk, pk_original)

    def test_los_precios_no_pierden_precision(self):
        """Decimal → str → Decimal. Si pasara por float, 150000.10 se rompe."""
        producto = crear_producto(precio=Decimal('150000.10'))
        cambio = cambio_de(producto, CambioSync.ALTA)
        producto.delete()

        aplicar_lote([cambio])

        self.assertEqual(Producto.objects.get(uid=cambio['uid']).precio_base,
                         Decimal('150000.10'))

    # ─── Orden de dependencias ───────────────────────────────────────────────

    def test_una_variante_antes_que_su_producto_igual_se_aplica(self):
        """
        El lote puede llegar en cualquier orden; el que aplica lo reordena.
        Si no lo hiciera, la variante fallaría por FK inexistente.
        """
        variante = crear_variante(color='Gris')
        producto = variante.producto
        cambios = [
            cambio_de(variante, CambioSync.ALTA),
            cambio_de(producto, CambioSync.ALTA),
            cambio_de(producto.categoria, CambioSync.ALTA),
        ]
        uid_variante = variante.uid
        variante.delete()
        producto.delete()
        producto.categoria.delete()

        resultado = aplicar_lote(cambios)

        self.assertEqual(resultado.conflictos, 0, resultado.detalle)
        self.assertEqual(resultado.aplicados, 3)
        self.assertTrue(Variante.objects.filter(uid=uid_variante).exists())

    def test_una_fila_cuya_fk_no_existe_queda_como_conflicto(self):
        variante = crear_variante(color='Verde')
        cambio = cambio_de(variante, CambioSync.ALTA)
        uid = variante.uid
        variante.delete()
        Producto.objects.all().delete()   # el producto ya no está de este lado

        resultado = aplicar_lote([cambio])

        self.assertEqual(resultado.aplicados, 0)
        self.assertEqual(resultado.conflictos, 1)
        self.assertFalse(Variante.objects.filter(uid=uid).exists())
        conflicto = ConflictoSync.objects.get()
        self.assertEqual(conflicto.motivo, ConflictoSync.NO_EXISTE)

    # ─── Conflictos ──────────────────────────────────────────────────────────

    def test_gana_el_cambio_mas_reciente(self):
        producto = crear_producto(nombre='Original')

        # La notebook lo renombró hace una hora, estando afuera del local.
        cambio = cambio_de(producto, momento=timezone.now() - timedelta(hours=1))
        cambio['datos']['nombre'] = 'Nombre viejo de la notebook'

        # Y acá alguien lo renombró recién.
        producto.nombre = 'Nombre nuevo del local'
        producto.save()

        resultado = aplicar_lote([cambio])

        self.assertEqual(resultado.conflictos, 1)
        producto.refresh_from_db()
        self.assertEqual(producto.nombre, 'Nombre nuevo del local')

    def test_el_cambio_que_pierde_queda_anotado_con_los_dos_lados(self):
        """Un rechazo silencioso es peor que una lista para revisar."""
        producto = crear_producto(nombre='Original')
        cambio = cambio_de(producto, momento=timezone.now() - timedelta(hours=1))
        cambio['datos']['nombre'] = 'Lo que puso la notebook'
        producto.nombre = 'Lo que puso el local'
        producto.save()

        aplicar_lote([cambio])

        conflicto = ConflictoSync.objects.get()
        self.assertEqual(conflicto.motivo, ConflictoSync.MAS_NUEVO_GANA)
        self.assertEqual(conflicto.datos_recibidos['nombre'], 'Lo que puso la notebook')
        self.assertEqual(conflicto.datos_locales['nombre'], 'Lo que puso el local')
        self.assertFalse(conflicto.revisado)

    def test_gana_la_notebook_si_su_cambio_es_posterior(self):
        producto = crear_producto(nombre='Original')
        cambio = cambio_de(producto, momento=timezone.now() + timedelta(minutes=5))
        cambio['datos']['nombre'] = 'Corregido en la notebook'

        resultado = aplicar_lote([cambio])

        self.assertEqual(resultado.aplicados, 1)
        self.assertEqual(resultado.conflictos, 0)
        producto.refresh_from_db()
        self.assertEqual(producto.nombre, 'Corregido en la notebook')

    # ─── Bajas ───────────────────────────────────────────────────────────────

    def test_una_baja_borra_la_fila_de_este_lado(self):
        producto = crear_producto()
        uid = producto.uid
        cambio = cambio_de(producto, CambioSync.BAJA,
                           momento=timezone.now() + timedelta(minutes=1))

        resultado = aplicar_lote([cambio])

        self.assertEqual(resultado.aplicados, 1)
        self.assertFalse(Producto.objects.filter(uid=uid).exists())

    def test_una_baja_vieja_no_pisa_una_edicion_nueva(self):
        """
        Se borró allá, pero acá se editó después. Borrar sería perder trabajo
        más reciente: queda como conflicto para que alguien decida.
        """
        producto = crear_producto()
        cambio = cambio_de(producto, CambioSync.BAJA,
                           momento=timezone.now() - timedelta(hours=1))
        producto.nombre = 'Editado después de que allá lo borraran'
        producto.save()

        resultado = aplicar_lote([cambio])

        self.assertEqual(resultado.conflictos, 1)
        self.assertTrue(Producto.objects.filter(uid=producto.uid).exists())

    def test_borrar_algo_que_ya_no_esta_no_es_un_error(self):
        producto = crear_producto()
        cambio = cambio_de(producto, CambioSync.BAJA)
        producto.delete()

        resultado = aplicar_lote([cambio])

        self.assertEqual(resultado.conflictos, 0)
        self.assertEqual(resultado.omitidos, 1)

    # ─── Alcance ─────────────────────────────────────────────────────────────

    def test_no_se_aplica_nada_fuera_del_catalogo(self):
        """
        Stock, ventas y caja tienen un solo dueño. Aunque el otro nodo los
        mande, acá no se tocan.
        """
        resultado = aplicar_lote([{
            'modelo': 'inventario.Stock',
            'uid': '00000000-0000-0000-0000-000000000001',
            'operacion': CambioSync.CAMBIO,
            'datos': {'cantidad': '9999'},
            'nodo': 'NOTEBOOK',
            'momento': timezone.now().isoformat(),
        }])

        self.assertEqual(resultado.aplicados, 0)
        self.assertEqual(resultado.omitidos, 1)

    def test_aplicar_no_genera_cambios_propios(self):
        """Si los generara, el sync rebotaría entre los dos equipos sin parar."""
        producto = crear_producto()
        cambio = cambio_de(producto, momento=timezone.now() + timedelta(minutes=1))
        cambio['datos']['nombre'] = 'Renombrado de afuera'
        CambioSync.objects.all().delete()

        aplicar_lote([cambio])

        self.assertEqual(CambioSync.objects.count(), 0)

    def test_la_hora_del_otro_nodo_se_conserva(self):
        """
        Es lo que decide el próximo conflicto. Si al aplicar se pisara con la
        hora local, la fila parecería recién editada acá y ganaría siempre.
        """
        producto = crear_producto()
        momento = timezone.now() + timedelta(minutes=3)
        cambio = cambio_de(producto, momento=momento)
        cambio['datos']['nombre'] = 'Desde la notebook'

        aplicar_lote([cambio])

        producto.refresh_from_db()
        self.assertEqual(producto.actualizado_en.replace(microsecond=0),
                         momento.replace(microsecond=0))
        self.assertEqual(producto.nodo_origen, 'NOTEBOOK')


class CategoriaSinDependenciasTest(TestCase):
    databases = {'default', 'sync'}

    def test_una_categoria_nueva_viaja_sola(self):
        categoria = Categoria.objects.create(nombre='Revestimientos', tipo='ceramico')
        cambio = cambio_de(categoria, CambioSync.ALTA)
        uid = categoria.uid
        categoria.delete()

        resultado = aplicar_lote([cambio])

        self.assertEqual(resultado.aplicados, 1)
        self.assertEqual(Categoria.objects.get(uid=uid).nombre, 'Revestimientos')
