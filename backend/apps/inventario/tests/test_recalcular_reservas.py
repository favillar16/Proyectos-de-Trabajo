"""
Tests de `manage.py recalcular_reservas`: la limpieza de las reservas que
quedaron trabadas antes del arreglo del 23/09/2026 (sacar un ítem de un
pedido no liberaba su reserva).
"""
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.inventario.models import MovimientoStock, Stock
from apps.productos.tests.factories import (crear_producto, crear_usuario,
                                            crear_variante)
from apps.usuarios.models import Usuario
from apps.ventas.models import ItemPedido, NotaPedido


class RecalcularReservasTests(TestCase):
    # El alta de catálogo escribe en el registro de cambios del sync.
    databases = {'default', 'sync'}

    def setUp(self):
        self.admin = crear_usuario('admin_reservas', rol=Usuario.ROL_ADMIN)
        self.variante = crear_variante(producto=crear_producto(nombre='Piso 71220'))
        self.stock = Stock.objects.get(variante=self.variante)
        self.stock.registrar_movimiento(
            tipo=MovimientoStock.TIPO_ENTRADA, cantidad=Decimal('220'), usuario=self.admin)

    def _pedido(self, cantidad):
        pedido = NotaPedido.objects.create(vendedor=self.admin)
        ItemPedido.objects.create(pedido=pedido, variante=self.variante,
                                  cantidad=Decimal(cantidad), precio_unitario=Decimal('1000'))
        pedido.reservar_stock(usuario=self.admin)
        return pedido

    def _item_borrado_sin_liberar(self, cantidad):
        """Lo que hacía la versión vieja al sacar un ítem."""
        self._pedido(cantidad).items.all().delete()

    def _correr(self, *args):
        salida = StringIO()
        call_command('recalcular_reservas', *args, stdout=salida)
        self.stock.refresh_from_db()
        return salida.getvalue()

    def test_libera_la_reserva_trabada_y_respeta_la_viva(self):
        self._pedido('46')
        self._item_borrado_sin_liberar('87')
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_disponible, Decimal('87'))

        self._correr()
        self.assertEqual(self.stock.cantidad_reservada, Decimal('46'))
        self.assertEqual(self.stock.cantidad_disponible, Decimal('174'))
        self.assertTrue(MovimientoStock.objects.filter(
            variante=self.variante, tipo=MovimientoStock.TIPO_LIBERACION,
            referencia_tipo='recalculo_reservas', cantidad=Decimal('87')).exists())

    def test_dry_run_no_toca_nada(self):
        self._item_borrado_sin_liberar('87')
        salida = self._correr('--dry-run')
        self.assertIn('corregiría', salida)
        self.assertEqual(self.stock.cantidad_reservada, Decimal('87'))

    def test_una_segunda_pasada_no_encuentra_diferencias(self):
        self._item_borrado_sin_liberar('87')
        self._correr()
        self.assertIn('0 variante(s)', self._correr())

    def test_un_pedido_cancelado_no_reserva(self):
        cancelado = self._pedido('10')
        cancelado.estado = NotaPedido.ESTADO_CANCELADO
        cancelado.save(update_fields=['estado'])
        self._correr()
        self.assertEqual(self.stock.cantidad_reservada, Decimal('0'))

    def test_repone_una_reserva_que_falta(self):
        self._pedido('30')
        self.stock.registrar_movimiento(
            tipo=MovimientoStock.TIPO_LIBERACION, cantidad=Decimal('30'), usuario=self.admin)
        self._correr()
        self.assertEqual(self.stock.cantidad_reservada, Decimal('30'))
