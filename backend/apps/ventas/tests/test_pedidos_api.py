"""
Tests de dos pedidos de la propietaria sobre la ventana de Pedidos:

  · quitar un ítem de un pedido tiene que **devolver la reserva al stock**.
    Antes no lo hacía: la mercadería quedaba reservada por un ítem que ya no
    existía y no se podía volver a vender sin un ajuste manual de inventario.
  · el buscador por nombre o CI/RUC del cliente.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.inventario.models import MovimientoStock, Stock
from apps.productos.tests.factories import (crear_producto, crear_usuario,
                                            crear_variante)
from apps.usuarios.models import Usuario
from apps.ventas.models import ItemPedido, NotaPedido


class BaseVentas(TestCase):
    # El alta de catálogo escribe en el registro de cambios del sync.
    databases = {'default', 'sync'}

    def setUp(self):
        self.vendedor = crear_usuario('vendedor_api', rol=Usuario.ROL_VENDEDOR)
        self.cliente_api = APIClient()
        self.cliente_api.force_authenticate(self.vendedor)

        producto = crear_producto(nombre='Porcelanato Siena')
        self.variante = crear_variante(producto=producto, color='Arena')
        self.stock = Stock.objects.get(variante=self.variante)
        self.stock.registrar_movimiento(
            tipo=MovimientoStock.TIPO_ENTRADA, cantidad=Decimal('50'),
            usuario=self.vendedor, observaciones='carga inicial',
        )

    def _pedido_con_reserva(self, cantidad='10', **extra):
        pedido = NotaPedido.objects.create(vendedor=self.vendedor, **extra)
        ItemPedido.objects.create(
            pedido=pedido, variante=self.variante,
            cantidad=Decimal(cantidad), precio_unitario=Decimal('150000'),
        )
        pedido.recalcular_totales()
        pedido.reservar_stock(usuario=self.vendedor)
        return pedido


class QuitarItemLiberaLaReservaTests(BaseVentas):

    def test_quitar_el_item_devuelve_el_stock_reservado(self):
        pedido = self._pedido_con_reserva('10')
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_reservada, Decimal('10'))

        item = pedido.items.first()
        respuesta = self.cliente_api.delete(
            reverse('item-cancelar', args=[pedido.id, item.id]))

        self.assertEqual(respuesta.status_code, 200)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_reservada, Decimal('0'))
        self.assertEqual(self.stock.cantidad_disponible, Decimal('50'))

    def test_deja_el_movimiento_de_liberacion_en_el_historial(self):
        """La reserva se devuelve por registrar_movimiento(), no a mano."""
        pedido = self._pedido_con_reserva('4')
        item = pedido.items.first()
        self.cliente_api.delete(reverse('item-cancelar', args=[pedido.id, item.id]))

        movimiento = MovimientoStock.objects.filter(
            variante=self.variante,
            tipo=MovimientoStock.TIPO_LIBERACION).last()
        self.assertIsNotNone(movimiento)
        self.assertEqual(movimiento.cantidad, Decimal('4'))
        self.assertIn(self.variante.sku, movimiento.observaciones)

    def test_no_toca_el_stock_fisico(self):
        pedido = self._pedido_con_reserva('7')
        item = pedido.items.first()
        self.cliente_api.delete(reverse('item-cancelar', args=[pedido.id, item.id]))
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad, Decimal('50'))

    def test_solo_libera_lo_del_item_quitado(self):
        pedido = self._pedido_con_reserva('10')
        otra = crear_variante(producto=self.variante.producto, color='Gris')
        Stock.objects.get(variante=otra).registrar_movimiento(
            tipo=MovimientoStock.TIPO_ENTRADA, cantidad=Decimal('30'),
            usuario=self.vendedor,
        )
        segundo = ItemPedido.objects.create(
            pedido=pedido, variante=otra,
            cantidad=Decimal('5'), precio_unitario=Decimal('90000'),
        )
        Stock.objects.get(variante=otra).registrar_movimiento(
            tipo=MovimientoStock.TIPO_RESERVA, cantidad=Decimal('5'),
            usuario=self.vendedor,
        )

        self.cliente_api.delete(
            reverse('item-cancelar', args=[pedido.id, segundo.id]))

        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_reservada, Decimal('10'))
        self.assertEqual(
            Stock.objects.get(variante=otra).cantidad_reservada, Decimal('0'))

    def test_un_pedido_ya_enviado_a_caja_no_deja_quitar_items(self):
        pedido = self._pedido_con_reserva('10', estado=NotaPedido.ESTADO_LISTO)
        item = pedido.items.first()
        respuesta = self.cliente_api.delete(
            reverse('item-cancelar', args=[pedido.id, item.id]))

        self.assertEqual(respuesta.status_code, 400)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_reservada, Decimal('10'))


class BuscadorDePedidosTests(BaseVentas):

    def setUp(self):
        super().setUp()
        self.admin = crear_usuario('admin_busqueda', rol=Usuario.ROL_ADMIN)
        self.cliente_api.force_authenticate(self.admin)

        self.uno = NotaPedido.objects.create(
            vendedor=self.vendedor, cliente_nombre='Rosa Mereles',
            cliente_ruc='4123456-7')
        self.dos = NotaPedido.objects.create(
            vendedor=self.vendedor, cliente_nombre='Constructora Guaraní SA',
            cliente_ruc='80012345-6')

    def _buscar(self, texto):
        respuesta = self.cliente_api.get(reverse('pedidos-list'), {'buscar': texto})
        self.assertEqual(respuesta.status_code, 200)
        return [p['numero'] for p in respuesta.data['results']]

    def test_busca_por_nombre_sin_importar_mayusculas(self):
        self.assertEqual(self._buscar('rosa'), [self.uno.numero])

    def test_busca_por_parte_del_nombre(self):
        self.assertEqual(self._buscar('Guaraní'), [self.dos.numero])

    def test_busca_por_ruc(self):
        self.assertEqual(self._buscar('80012345'), [self.dos.numero])

    def test_busca_por_cedula(self):
        self.assertEqual(self._buscar('4123456'), [self.uno.numero])

    def test_busca_por_numero_de_pedido(self):
        self.assertEqual(self._buscar(self.dos.numero), [self.dos.numero])

    def test_sin_coincidencias_devuelve_vacio(self):
        self.assertEqual(self._buscar('no-existe-este-cliente'), [])

    def test_sin_el_parametro_devuelve_todo(self):
        respuesta = self.cliente_api.get(reverse('pedidos-list'))
        self.assertEqual(len(respuesta.data['results']), 2)

    def test_el_ruc_viaja_en_el_listado(self):
        """El buscador filtra por RUC: la lista tiene que poder mostrarlo."""
        respuesta = self.cliente_api.get(reverse('pedidos-list'), {'buscar': 'Rosa'})
        self.assertEqual(respuesta.data['results'][0]['cliente_ruc'], '4123456-7')

    def test_el_vendedor_sigue_viendo_solo_los_suyos(self):
        """El buscador filtra dentro del alcance del rol, no lo amplía."""
        otro = crear_usuario('otro_vendedor', rol=Usuario.ROL_VENDEDOR)
        NotaPedido.objects.create(vendedor=otro, cliente_nombre='Rosa Distinta')

        self.cliente_api.force_authenticate(self.vendedor)
        self.assertEqual(self._buscar('Rosa'), [self.uno.numero])

    def test_el_ruc_se_puede_corregir_despues(self):
        respuesta = self.cliente_api.patch(
            reverse('pedido-detail', args=[self.uno.id]),
            {'cliente_ruc': '4123456-8'}, format='json')
        self.assertEqual(respuesta.status_code, 200)
        self.uno.refresh_from_db()
        self.assertEqual(self.uno.cliente_ruc, '4123456-8')


class DatosDelClienteEnPedidoPagadoTests(BaseVentas):
    """
    La rendija que deja corregir al cliente después de cobrar.

    No es una flexibilización general del PATCH: es lo mínimo para poder
    emitir la nota de remisión, que se emite DESPUÉS del cobro y que el SIFEN
    rechaza sin receptor identificado (NT 023). Una venta cobrada como ticket
    —donde nadie pide el RUC— quedaba sin forma de despacharse.
    """

    def setUp(self):
        super().setUp()
        self.pedido = self._pedido_con_reserva(cantidad='2')
        self.pedido.estado = NotaPedido.ESTADO_PAGADO
        self.pedido.save(update_fields=['estado'])
        self.url = reverse('pedido-detail', args=[self.pedido.id])

    def test_se_puede_cargar_el_ruc_de_un_pedido_pagado(self):
        respuesta = self.cliente_api.patch(
            self.url, {'cliente_ruc': '80099887-6',
                       'cliente_nombre': 'Constructora Sur SRL'}, format='json')
        self.assertEqual(respuesta.status_code, 200)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.cliente_ruc, '80099887-6')
        self.assertEqual(self.pedido.cliente_nombre, 'Constructora Sur SRL')

    def test_no_deja_tocar_el_monto_de_un_pedido_pagado(self):
        # Lo que la rendija NO abre. Si esto pasara, se podría reescribir el
        # precio de una venta ya cobrada y facturada.
        antes = self.pedido.total
        respuesta = self.cliente_api.patch(
            self.url, {'total_ajustado': '1'}, format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.total, antes)

    def test_mezclar_un_campo_prohibido_rechaza_todo(self):
        # Mandar el RUC junto con el monto no puede colar el monto.
        respuesta = self.cliente_api.patch(
            self.url, {'cliente_ruc': '80099887-6', 'descuento': '5000'},
            format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.cliente_ruc, '')

    def test_un_pedido_en_preparacion_sigue_cerrado(self):
        # La excepción es solo para 'pagado': en preparación el pedido está
        # en manos de depósito y no hay remisión que emitir todavía.
        self.pedido.estado = NotaPedido.ESTADO_EN_PREPARACION
        self.pedido.save(update_fields=['estado'])
        respuesta = self.cliente_api.patch(
            self.url, {'cliente_ruc': '80099887-6'}, format='json')
        self.assertEqual(respuesta.status_code, 400)

    def test_el_pedido_pendiente_sigue_editandose_como_siempre(self):
        self.pedido.estado = NotaPedido.ESTADO_PENDIENTE
        self.pedido.save(update_fields=['estado'])
        respuesta = self.cliente_api.patch(
            self.url, {'cliente_observaciones': 'Entregar por la mañana'},
            format='json')
        self.assertEqual(respuesta.status_code, 200)
