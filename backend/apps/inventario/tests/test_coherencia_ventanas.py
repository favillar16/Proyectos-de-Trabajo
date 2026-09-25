"""
Las ventanas que muestran stock tienen que dar el mismo número.

Showroom, Productos, Inventario, el tablero y el reporte de stock leían cada
uno algo distinto: el físico con reservas incluidas, solo la página visible,
un umbral propio o variantes desactivadas. Estos tests fijan que todos salen
del mismo lugar — `Stock.cantidad_disponible` y `Stock.estado` sobre
variantes activas.
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


class CoherenciaEntreVentanasTests(TestCase):
    # El alta de catálogo escribe en el registro de cambios del sync.
    databases = {'default', 'sync'}

    def setUp(self):
        self.admin = crear_usuario('admin_coherencia', rol=Usuario.ROL_ADMIN)
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

        # Piso con dos colores: Arena con 100 y 30 reservados, Gris con 50
        # todo reservado. Físico 150, vendible 70.
        self.piso = crear_producto(nombre='Piso 71220')
        self.arena = crear_variante(producto=self.piso, color='Arena')
        self.gris = crear_variante(producto=self.piso, color='Gris')
        self._entrada(self.arena, '100')
        self._entrada(self.gris, '50')
        self._reservar(self.arena, '30')
        self._reservar(self.gris, '50')

        # Una variante desactivada con stock no cuenta en ninguna ventana.
        self.vieja = crear_variante(producto=self.piso, color='Discontinuado')
        self._entrada(self.vieja, '999')
        self.vieja.activa = False
        self.vieja.save()

    def _entrada(self, variante, cantidad):
        Stock.objects.get(variante=variante).registrar_movimiento(
            tipo=MovimientoStock.TIPO_ENTRADA, cantidad=Decimal(cantidad),
            usuario=self.admin)

    def _reservar(self, variante, cantidad):
        pedido = NotaPedido.objects.create(vendedor=self.admin, cliente_nombre='Cliente')
        ItemPedido.objects.create(pedido=pedido, variante=variante,
                                  cantidad=Decimal(cantidad),
                                  precio_unitario=Decimal('1000'))
        pedido.reservar_stock(usuario=self.admin)

    def _stock_inventario(self, **params):
        respuesta = self.api.get(reverse('stock-list'), params)
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.data

    def test_producto_expone_lo_vendible_y_no_el_fisico(self):
        respuesta = self.api.get(reverse('producto-detail', args=[self.piso.id]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Decimal(respuesta.data['stock_total']), Decimal('150'))
        self.assertEqual(Decimal(respuesta.data['stock_disponible']), Decimal('70'))

    def test_showroom_suma_lo_mismo_que_inventario(self):
        showroom = self.api.get(reverse('producto-showroom'))
        self.assertEqual(showroom.status_code, 200)
        fila = next(p for p in showroom.data['results'] if p['id'] == self.piso.id)

        inventario = self._stock_inventario(search='71220')['results']
        suma_inventario = sum(Decimal(i['disponible']) for i in inventario)

        self.assertEqual(Decimal(fila['stock_disponible']), suma_inventario)

    def test_detalle_del_showroom_coincide_con_inventario(self):
        detalle = self.api.get(reverse('producto-stock', args=[self.piso.id])).data
        inventario = self._stock_inventario(search='71220')['results']
        por_sku = {i['sku']: Decimal(i['disponible']) for i in inventario}
        self.assertEqual({d['sku']: Decimal(str(d['disponible'])) for d in detalle}, por_sku)

    def test_con_stock_mira_lo_vendible(self):
        # Todo reservado: físico hay, vendible no.
        otro = crear_producto(nombre='Revestimiento Apartado')
        v = crear_variante(producto=otro, color='Blanco')
        self._entrada(v, '10')
        self._reservar(v, '10')

        ids = {p['id'] for p in
               self.api.get(reverse('producto-showroom'), {'con_stock': 'true'}).data['results']}
        self.assertIn(self.piso.id, ids)
        self.assertNotIn(otro.id, ids)

    def test_con_stock_ignora_variantes_desactivadas(self):
        otro = crear_producto(nombre='Solo Discontinuado')
        v = crear_variante(producto=otro, color='Viejo')
        self._entrada(v, '10')
        v.activa = False
        v.save()

        ids = {p['id'] for p in
               self.api.get(reverse('producto-showroom'), {'con_stock': 'true'}).data['results']}
        self.assertNotIn(otro.id, ids)

    def test_resumen_de_inventario_cuenta_todo_y_no_la_pagina(self):
        for i in range(5):
            self._entrada(crear_variante(producto=self.piso, color=f'Extra {i}'), '10')

        datos = self._stock_inventario(page_size=2)
        self.assertEqual(len(datos['results']), 2)
        self.assertEqual(datos['resumen']['total'], datos['count'])
        self.assertEqual(datos['resumen']['total'], 7)
        self.assertEqual(datos['resumen']['sin_stock'], 1)   # Gris, todo reservado

    def test_resumen_no_cambia_al_filtrar_por_estado(self):
        todo = self._stock_inventario()['resumen']
        filtrado = self._stock_inventario(estado='sin_stock')
        self.assertEqual(filtrado['resumen'], todo)
        self.assertEqual(filtrado['count'], todo['sin_stock'])

    def test_tablero_coincide_con_inventario(self):
        kpis = self.api.get(reverse('dashboard-kpis'))
        self.assertEqual(kpis.status_code, 200)
        tablero = kpis.data['stock']
        resumen = self._stock_inventario()['resumen']

        self.assertEqual(tablero['total'], resumen['total'])
        self.assertEqual(tablero['ok'], resumen['disponible'])
        self.assertEqual(tablero['bajo'], resumen['bajo'])
        self.assertEqual(tablero['critico'], resumen['critico'])
        self.assertEqual(tablero['sin_stock'], resumen['sin_stock'])
        # Gris tiene físico pero no vendible: el tablero antes lo daba "con stock".
        self.assertEqual(tablero['sin_stock'], 1)

    def test_reporte_de_stock_usa_las_mismas_variantes(self):
        from apps.caja.reportes import reporte_stock
        reporte = reporte_stock()
        skus = {f[1] for f in reporte['filas']}
        self.assertEqual(skus, {self.arena.sku, self.gris.sku})
        self.assertEqual(reporte['totales']['Variantes sin stock'], 1)
        self.assertEqual(reporte['totales']['Total unidades disponibles'], '70.00')
