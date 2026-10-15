"""
Tests de devoluciones y cambios.

Lo que tiene que estar bien, en orden de lo que cuesta si falla:

  · la plata: el crédito es lo que el cliente **pagó**, no el precio de
    lista, y devolver una venta entera en varias veces reintegra exactamente
    lo cobrado, ni un guaraní más;
  · la caja: un reintegro en efectivo sale del cajón, así que el arqueo y el
    cierre lo restan — y uno por transferencia no;
  · el stock: lo devuelto vuelve, salvo lo dañado, y sin comerse las
    reservas de otros pedidos;
  · que nada quede a medias cuando la devolución se rechaza.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.caja import devoluciones, reportes as rep
from apps.caja.models import Devolucion, Pago
from apps.facturacion.emisor import crear_documento
from apps.facturacion.tests.factories import (DATOS_FISCALES_COMPLETOS,
                                              RUC_RECEPTOR, SIFEN_PRENDIDO,
                                              crear_pago, crear_pedido,
                                              crear_sesion, crear_usuario,
                                              crear_variante)
from apps.inventario.models import MovimientoStock, Stock
from apps.ventas.models import NotaPedido


class BaseDevolucionTests(TestCase):
    # El alta de catálogo escribe en el registro de cambios del sync.
    databases = {'default', 'sync'}

    def setUp(self):
        self.cajero = crear_usuario('cajera_dev')
        self.sesion = crear_sesion(self.cajero)
        self.porcelanato = crear_variante('Porcelanato Roma', Decimal('150000'))
        self.ceramica = crear_variante('Cerámica Bahía', Decimal('90000'))
        for variante in (self.porcelanato, self.ceramica):
            self._stock(variante).registrar_movimiento(
                MovimientoStock.TIPO_ENTRADA, Decimal('100'), self.cajero)

    def _stock(self, variante):
        return Stock.objects.get(variante=variante)

    def _vender(self, items, monto=None, medio='efectivo'):
        """Una venta ya cobrada, con su stock descontado como en caja."""
        pedido = crear_pedido(self.cajero, items)
        pedido.reservar_stock(self.cajero)
        total = sum((Decimal(str(c)) * Decimal(str(p)) for _, c, p in items), Decimal('0'))
        pago = crear_pago(pedido, self.sesion, self.cajero,
                          monto if monto is not None else total, medio=medio)
        pedido.estado = NotaPedido.ESTADO_PAGADO
        pedido.save()
        pedido.descontar_stock(self.cajero)
        return pago

    def _pedido_listo(self, items):
        pedido = crear_pedido(self.cajero, items)
        pedido.recalcular_totales()
        pedido.reservar_stock(self.cajero)
        return pedido

    def _item(self, pago, variante):
        return pago.pedido.items.get(variante=variante)

    def _devolver(self, pago, lineas, **kwargs):
        kwargs.setdefault('motivo', Devolucion.MOTIVO_ESTADO_INADECUADO)
        return devoluciones.registrar(
            pago_original=pago, sesion=self.sesion, usuario=self.cajero,
            items=[{'item_id': self._item(pago, v).id, 'cantidad': c,
                    'reingresa_stock': r} for v, c, r in lineas],
            **kwargs,
        ).devolucion


class CreditoTests(BaseDevolucionTests):

    def test_devolucion_sin_cambio_reintegra_lo_cobrado(self):
        pago = self._vender([(self.porcelanato, '2', '150000')])
        dev = self._devolver(pago, [(self.porcelanato, '2', True)],
                             medio_pago='efectivo')

        self.assertEqual(dev.total_credito, Decimal('300000'))
        self.assertEqual(dev.monto_reintegro, Decimal('300000'))
        self.assertEqual(dev.medio_reintegro, 'efectivo')
        self.assertIsNone(dev.pago_cambio)

    def test_el_credito_sale_de_lo_cobrado_y_no_del_precio_de_lista(self):
        # Se vendió a 300.000 con un 10% de descuento en caja: el cliente
        # pagó 270.000 y eso es lo que se le devuelve.
        pago = self._vender([(self.porcelanato, '2', '150000')],
                            monto=Decimal('270000'))
        dev = self._devolver(pago, [(self.porcelanato, '1', True)],
                             medio_pago='efectivo')
        self.assertEqual(dev.total_credito, Decimal('135000'))

    def test_devolver_todo_en_partes_reintegra_exactamente_lo_cobrado(self):
        # 3 unidades cobradas 100.000 en total: 33.333,33 cada una. Devueltas
        # de a una, el redondeo tiene que cerrar en 100.000 justos.
        pago = self._vender([(self.ceramica, '3', '40000')],
                            monto=Decimal('100000'))
        total = Decimal('0')
        for _ in range(3):
            dev = self._devolver(pago, [(self.ceramica, '1', True)],
                                 medio_pago='efectivo')
            total += dev.total_credito
        self.assertEqual(total, Decimal('100000'))

    def test_el_prorrateo_entre_items_suma_lo_cobrado(self):
        pago = self._vender([(self.porcelanato, '1', '150000'),
                             (self.ceramica, '1', '90000')],
                            monto=Decimal('200000'))
        dev = self._devolver(pago, [(self.porcelanato, '1', True),
                                    (self.ceramica, '1', True)],
                             medio_pago='efectivo')
        self.assertEqual(dev.total_credito, Decimal('200000'))

    def test_no_se_devuelve_mas_de_lo_vendido(self):
        pago = self._vender([(self.porcelanato, '2', '150000')])
        self._devolver(pago, [(self.porcelanato, '1.5', True)], medio_pago='efectivo')

        with self.assertRaisesMessage(devoluciones.DevolucionInvalida, 'hasta 0,5'):
            self._devolver(pago, [(self.porcelanato, '1', True)], medio_pago='efectivo')


class StockTests(BaseDevolucionTests):

    def test_lo_devuelto_vuelve_al_stock_con_su_movimiento(self):
        pago = self._vender([(self.porcelanato, '5', '150000')])
        antes = self._stock(self.porcelanato).cantidad

        dev = self._devolver(pago, [(self.porcelanato, '2', True)], medio_pago='efectivo')

        self.assertEqual(self._stock(self.porcelanato).cantidad, antes + 2)
        mov = MovimientoStock.objects.get(tipo=MovimientoStock.TIPO_DEVOLUCION)
        self.assertEqual(mov.referencia_tipo, 'devolucion')
        self.assertEqual(mov.referencia_id, dev.pk)

    def test_lo_danado_no_vuelve_al_stock_vendible(self):
        pago = self._vender([(self.porcelanato, '5', '150000')])
        antes = self._stock(self.porcelanato).cantidad

        dev = self._devolver(pago, [(self.porcelanato, '2', False)], medio_pago='efectivo')

        self.assertEqual(self._stock(self.porcelanato).cantidad, antes)
        # Pero la plata se reintegra igual y el ítem queda registrado.
        self.assertEqual(dev.monto_reintegro, Decimal('300000'))
        self.assertFalse(dev.items.get().reingresa_stock)

    def test_la_devolucion_no_se_come_las_reservas_de_otros_pedidos(self):
        # El bug que había: TIPO_DEVOLUCION descontaba de cantidad_reservada,
        # y esa reserva era de otro pedido que todavía no se cobró.
        pago = self._vender([(self.porcelanato, '5', '150000')])
        self._pedido_listo([(self.porcelanato, '10', '150000')])
        self.assertEqual(self._stock(self.porcelanato).cantidad_reservada, Decimal('10'))

        self._devolver(pago, [(self.porcelanato, '2', True)], medio_pago='efectivo')

        self.assertEqual(self._stock(self.porcelanato).cantidad_reservada, Decimal('10'))


class CambioTests(BaseDevolucionTests):

    def test_cambio_por_algo_mas_caro_cobra_la_diferencia(self):
        pago = self._vender([(self.ceramica, '2', '90000')])          # 180.000
        nuevo = self._pedido_listo([(self.porcelanato, '2', '150000')])  # 300.000

        dev = self._devolver(pago, [(self.ceramica, '2', True)],
                             motivo=Devolucion.MOTIVO_CAMBIO, pedido_cambio=nuevo,
                             medio_pago='efectivo', monto_recibido='150000')

        self.assertEqual(dev.monto_reintegro, 0)
        self.assertEqual(dev.pago_cambio.monto, Decimal('120000'))
        self.assertEqual(dev.pago_cambio.vuelto, Decimal('30000'))
        nuevo.refresh_from_db()
        self.assertEqual(nuevo.estado, NotaPedido.ESTADO_PAGADO)
        # El pedido de cambio descontó su stock como cualquier venta.
        self.assertEqual(self._stock(self.porcelanato).cantidad, Decimal('98'))
        self.assertEqual(self._stock(self.porcelanato).cantidad_reservada, 0)

    def test_cambio_por_algo_mas_barato_reintegra_la_diferencia(self):
        pago = self._vender([(self.porcelanato, '2', '150000')])     # 300.000
        nuevo = self._pedido_listo([(self.ceramica, '2', '90000')])   # 180.000

        dev = self._devolver(pago, [(self.porcelanato, '2', True)],
                             motivo=Devolucion.MOTIVO_CAMBIO, pedido_cambio=nuevo,
                             medio_pago='transferencia')

        self.assertEqual(dev.monto_reintegro, Decimal('120000'))
        self.assertEqual(dev.medio_reintegro, 'transferencia')
        self.assertEqual(dev.pago_cambio.monto, 0)
        self.assertEqual(dev.credito_aplicado, Decimal('180000'))

    def test_devolver_lo_que_vino_en_un_cambio_reconoce_su_valor_entero(self):
        # El cambio se pagó 120.000 de bolsillo + 180.000 de crédito. Si el
        # cliente vuelve a devolverlo, vale 300.000, no 120.000.
        pago = self._vender([(self.ceramica, '2', '90000')])
        nuevo = self._pedido_listo([(self.porcelanato, '2', '150000')])
        dev = self._devolver(pago, [(self.ceramica, '2', True)],
                             motivo=Devolucion.MOTIVO_CAMBIO, pedido_cambio=nuevo,
                             medio_pago='debito')

        segunda = self._devolver(dev.pago_cambio, [(self.porcelanato, '2', True)],
                                 medio_pago='efectivo')
        self.assertEqual(segunda.total_credito, Decimal('300000'))

    def test_un_cambio_sin_pedido_nuevo_se_rechaza(self):
        pago = self._vender([(self.ceramica, '2', '90000')])
        with self.assertRaisesMessage(devoluciones.DevolucionInvalida, 'necesita el pedido'):
            self._devolver(pago, [(self.ceramica, '1', True)],
                           motivo=Devolucion.MOTIVO_CAMBIO, medio_pago='efectivo')

    def test_el_pedido_de_cambio_tiene_que_estar_listo(self):
        pago = self._vender([(self.ceramica, '2', '90000')])
        nuevo = self._pedido_listo([(self.porcelanato, '1', '150000')])
        nuevo.estado = NotaPedido.ESTADO_PENDIENTE
        nuevo.save()
        with self.assertRaisesMessage(devoluciones.DevolucionInvalida, 'Listo para cobrar'):
            self._devolver(pago, [(self.ceramica, '1', True)],
                           motivo=Devolucion.MOTIVO_CAMBIO, pedido_cambio=nuevo,
                           medio_pago='efectivo', monto_recibido='200000')

    def test_efectivo_insuficiente_no_deja_nada_a_medias(self):
        pago = self._vender([(self.ceramica, '2', '90000')])
        nuevo = self._pedido_listo([(self.porcelanato, '2', '150000')])
        stock_antes = self._stock(self.ceramica).cantidad

        with self.assertRaises(devoluciones.DevolucionInvalida):
            self._devolver(pago, [(self.ceramica, '2', True)],
                           motivo=Devolucion.MOTIVO_CAMBIO, pedido_cambio=nuevo,
                           medio_pago='efectivo', monto_recibido='50000')

        self.assertFalse(Devolucion.objects.exists())
        self.assertEqual(self._stock(self.ceramica).cantidad, stock_antes)
        nuevo.refresh_from_db()
        self.assertEqual(nuevo.estado, NotaPedido.ESTADO_LISTO)


class ValidacionTests(BaseDevolucionTests):

    def test_otro_motivo_exige_detalle(self):
        pago = self._vender([(self.ceramica, '2', '90000')])
        with self.assertRaisesMessage(devoluciones.DevolucionInvalida, 'Otro motivo'):
            self._devolver(pago, [(self.ceramica, '1', True)],
                           motivo=Devolucion.MOTIVO_OTRO, medio_pago='efectivo')

    def test_el_reintegro_necesita_un_medio(self):
        pago = self._vender([(self.ceramica, '2', '90000')])
        with self.assertRaisesMessage(devoluciones.DevolucionInvalida, 'reintegrar'):
            self._devolver(pago, [(self.ceramica, '1', True)])

    def test_no_se_reintegra_con_cheque(self):
        pago = self._vender([(self.ceramica, '2', '90000')])
        with self.assertRaises(devoluciones.DevolucionInvalida):
            self._devolver(pago, [(self.ceramica, '1', True)], medio_pago='cheque')

    @override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
    def test_una_venta_con_factura_electronica_viva_se_bloquea(self):
        # Sin nota de crédito parcial, devolver por acá dejaría al SIFEN con
        # la venta entera.
        pago = self._vender([(self.ceramica, '2', '90000')])
        crear_documento(pago, receptor={'ruc': RUC_RECEPTOR, 'razon_social': 'Cliente SRL'})

        self.assertIn('nota de crédito parcial', devoluciones.resumen(pago)['bloqueo'])
        with self.assertRaisesMessage(devoluciones.DevolucionInvalida, 'nota de crédito parcial'):
            self._devolver(pago, [(self.ceramica, '1', True)], medio_pago='efectivo')


class CajaYReportesTests(BaseDevolucionTests):

    def test_el_arqueo_resta_solo_el_reintegro_en_efectivo(self):
        self.sesion.monto_apertura = Decimal('500000')
        self.sesion.save()
        pago = self._vender([(self.porcelanato, '4', '150000')])   # 600.000 efectivo
        self._devolver(pago, [(self.porcelanato, '1', True)], medio_pago='efectivo')
        self._devolver(pago, [(self.porcelanato, '1', True)], medio_pago='transferencia')

        reporte = rep.reporte_arqueo(date.today())
        fila = next(f for f in reporte['filas']
                    if f[0].strip() == 'Efectivo que debe haber en el cajón')
        # 500.000 + 600.000 − 150.000 (el de transferencia no salió del cajón)
        self.assertEqual(fila[2], 'Gs. 950.000')

    def test_el_balance_de_ventas_da_el_neto(self):
        pago = self._vender([(self.porcelanato, '2', '150000')])
        self._devolver(pago, [(self.porcelanato, '1', True)], medio_pago='efectivo')

        reporte = rep.reporte_ventas(date.today(), date.today())
        self.assertEqual(reporte['totales']['Total de ventas'], 'Gs. 150.000')
        self.assertEqual(reporte['totales']['Cantidad de cobros'], 1)

    def test_productos_comercializados_resta_lo_devuelto(self):
        pago = self._vender([(self.porcelanato, '5', '150000')])
        self._devolver(pago, [(self.porcelanato, '2', True)], medio_pago='efectivo')

        reporte = rep.reporte_productos(date.today(), date.today())
        fila = next(f for f in reporte['filas'] if f[0] == 'Porcelanato Roma')
        self.assertEqual(fila[3], '3,00 m²')


class ApiTests(BaseDevolucionTests):

    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.cajero)

    def test_registrar_por_la_api(self):
        pago = self._vender([(self.porcelanato, '2', '150000')])
        item = self._item(pago, self.porcelanato)

        resumen = self.api.get(f'/api/v1/caja/pagos/{pago.id}/devolucion/')
        self.assertEqual(resumen.status_code, 200)
        self.assertEqual(resumen.data['items'][0]['cantidad_disponible'], Decimal('2'))

        r = self.api.post('/api/v1/caja/devoluciones/', {
            'pago_id': pago.id, 'motivo': 'estado_inadecuado',
            'items': [{'item_id': item.id, 'cantidad': 1, 'reingresa_stock': False}],
            'medio_pago': 'efectivo',
        }, format='json')

        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['comprobante']['a_reintegrar'], 150000.0)
        self.assertIn('DEVOLUCION', r.data['texto'])

        lista = self.api.get('/api/v1/caja/devoluciones/')
        self.assertEqual(len(lista.data['results']), 1)

        pagos = self.api.get('/api/v1/caja/pagos/lista/')
        self.assertEqual(pagos.data['results'][0]['devoluciones'],
                         [r.data['devolucion']['numero']])

    def test_un_error_de_validacion_vuelve_como_400(self):
        pago = self._vender([(self.porcelanato, '2', '150000')])
        r = self.api.post('/api/v1/caja/devoluciones/', {
            'pago_id': pago.id, 'motivo': 'otro', 'items': [],
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_un_vendedor_no_puede_registrar_devoluciones(self):
        vendedor = crear_usuario('vendedor_dev', rol='vendedor')
        self.api.force_authenticate(vendedor)
        r = self.api.post('/api/v1/caja/devoluciones/', {}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_el_cierre_resta_el_reintegro_en_efectivo(self):
        pago = self._vender([(self.porcelanato, '2', '150000')])
        self._devolver(pago, [(self.porcelanato, '1', True)], medio_pago='efectivo')

        r = self.api.post(f'/api/v1/caja/sesiones/{self.sesion.id}/cerrar/',
                          {'monto_cierre': 150000}, format='json')

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['total_reintegros'], 150000.0)
        self.assertEqual(r.data['total_neto'], 150000.0)
        self.assertEqual(r.data['diferencia'], 0)


class CambioDesdeCajaTests(BaseDevolucionTests):
    """
    El cambio armado en caja: la cajera marca por qué producto se cambia y el
    sistema arma el pedido, sin que el vendedor tenga que hacer uno aparte.
    """

    def _cambiar(self, pago, devuelve, lleva, **kwargs):
        kwargs.setdefault('motivo', Devolucion.MOTIVO_CAMBIO)
        return self._devolver(
            pago, devuelve,
            items_cambio=[{'variante_id': v.id, 'cantidad': c} for v, c in lleva],
            **kwargs)

    def test_cambio_por_algo_mas_caro_arma_el_pedido_y_cobra_la_diferencia(self):
        pago = self._vender([(self.ceramica, '2', '90000')])          # 180.000

        dev = self._cambiar(pago, [(self.ceramica, '2', True)],
                            [(self.porcelanato, '2')],                 # 300.000
                            medio_pago='efectivo', monto_recibido='150000')

        nuevo = dev.pedido_cambio
        self.assertEqual(nuevo.estado, NotaPedido.ESTADO_PAGADO)
        self.assertEqual(nuevo.monto_a_cobrar, Decimal('300000'))
        self.assertEqual(nuevo.cliente_nombre, pago.pedido.cliente_nombre)
        self.assertIn(pago.pedido.numero, nuevo.nota_interna)
        self.assertEqual(dev.pago_cambio.monto, Decimal('120000'))
        self.assertEqual(dev.pago_cambio.vuelto, Decimal('30000'))
        # Lo que se lleva sale del stock y no queda reservado.
        self.assertEqual(self._stock(self.porcelanato).cantidad, Decimal('98'))
        self.assertEqual(self._stock(self.porcelanato).cantidad_reservada, 0)
        # Lo que trae vuelve.
        self.assertEqual(self._stock(self.ceramica).cantidad, Decimal('100'))

    def test_cambio_por_algo_mas_barato_reintegra(self):
        pago = self._vender([(self.porcelanato, '2', '150000')])     # 300.000

        dev = self._cambiar(pago, [(self.porcelanato, '2', True)],
                            [(self.ceramica, '2')],                    # 180.000
                            medio_pago='efectivo')

        self.assertEqual(dev.monto_reintegro, Decimal('120000'))
        self.assertEqual(dev.pago_cambio.monto, 0)

    def test_cambio_por_lo_mismo_no_mueve_plata(self):
        pago = self._vender([(self.ceramica, '2', '90000')])
        dev = self._cambiar(pago, [(self.ceramica, '1', True)], [(self.ceramica, '1')])
        self.assertEqual(dev.monto_reintegro, 0)
        self.assertEqual(dev.pago_cambio.monto, 0)

    def test_el_mismo_producto_marcado_dos_veces_es_un_renglon(self):
        pago = self._vender([(self.ceramica, '4', '90000')])
        dev = self._cambiar(pago, [(self.ceramica, '4', True)],
                            [(self.porcelanato, '1'), (self.porcelanato, '1')],
                            medio_pago='transferencia')
        items = list(dev.pedido_cambio.items.all())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].cantidad, Decimal('2'))

    def test_sin_stock_para_el_cambio_no_deja_nada_a_medias(self):
        pago = self._vender([(self.ceramica, '2', '90000')])
        pedidos_antes = NotaPedido.objects.count()
        stock_ceramica = self._stock(self.ceramica).cantidad

        with self.assertRaisesMessage(devoluciones.DevolucionInvalida, 'No hay stock'):
            self._cambiar(pago, [(self.ceramica, '2', True)],
                          [(self.porcelanato, '500')], medio_pago='efectivo',
                          monto_recibido='99999999')

        self.assertEqual(NotaPedido.objects.count(), pedidos_antes)
        self.assertEqual(self._stock(self.ceramica).cantidad, stock_ceramica)
        self.assertEqual(self._stock(self.porcelanato).cantidad_reservada, 0)
        self.assertFalse(Devolucion.objects.exists())

    def test_un_error_de_la_diferencia_revierte_el_pedido_armado(self):
        # Falta el monto recibido: el pedido ya se había armado y reservado,
        # y tiene que desaparecer junto con su reserva.
        pago = self._vender([(self.ceramica, '2', '90000')])
        pedidos_antes = NotaPedido.objects.count()
        with self.assertRaisesMessage(devoluciones.DevolucionInvalida, 'monto recibido'):
            self._cambiar(pago, [(self.ceramica, '2', True)],
                          [(self.porcelanato, '2')], medio_pago='efectivo')
        self.assertEqual(NotaPedido.objects.count(), pedidos_antes)
        self.assertEqual(self._stock(self.porcelanato).cantidad_reservada, 0)

    def test_cantidad_invalida_se_rechaza(self):
        pago = self._vender([(self.ceramica, '2', '90000')])
        with self.assertRaisesMessage(devoluciones.DevolucionInvalida, 'mayor a 0'):
            self._cambiar(pago, [(self.ceramica, '1', True)], [(self.porcelanato, '0')])

    def test_no_se_mandan_pedido_y_productos_a_la_vez(self):
        pago = self._vender([(self.ceramica, '2', '90000')])
        nuevo = self._pedido_listo([(self.porcelanato, '1', '150000')])
        with self.assertRaisesMessage(devoluciones.DevolucionInvalida, 'una sola forma'):
            self._cambiar(pago, [(self.ceramica, '1', True)], [(self.porcelanato, '1')],
                          pedido_cambio=nuevo)

    def test_por_la_api(self):
        api = APIClient()
        api.force_authenticate(self.cajero)
        pago = self._vender([(self.ceramica, '2', '90000')])
        item = self._item(pago, self.ceramica)

        r = api.post('/api/v1/caja/devoluciones/', {
            'pago_id': pago.id, 'motivo': 'cambio',
            'items': [{'item_id': item.id, 'cantidad': 2, 'reingresa_stock': True}],
            'items_cambio': [{'variante_id': self.porcelanato.id, 'cantidad': 2}],
            'medio_pago': 'debito',
        }, format='json')

        self.assertEqual(r.status_code, 201, r.data)
        c = r.data['comprobante']
        self.assertEqual(c['total_credito'], 180000.0)
        self.assertEqual(c['total_nuevo'], 300000.0)
        self.assertEqual(c['a_cobrar'], 120000.0)
        self.assertEqual(len(c['llevados']), 1)


class CambiosEnReportesTests(BaseDevolucionTests):
    """Un cambio se ve como cambio en el balance, el arqueo y el tablero."""

    def _cambio(self, pago, devuelve, lleva, **kwargs):
        kwargs.setdefault('motivo', Devolucion.MOTIVO_CAMBIO)
        return self._devolver(
            pago, devuelve,
            items_cambio=[{'variante_id': v.id, 'cantidad': c} for v, c in lleva],
            **kwargs)

    def test_el_balance_nombra_el_cambio_y_no_lo_cuenta_como_cobro(self):
        pago = self._vender([(self.ceramica, '2', '90000')])           # 180.000
        dev = self._cambio(pago, [(self.ceramica, '2', True)],
                           [(self.porcelanato, '2')],                    # 300.000
                           medio_pago='transferencia')                  # cobra 120.000

        reporte = rep.reporte_ventas(date.today(), date.today())
        fila = next(f for f in reporte['filas'] if f[1] == dev.pago_cambio.numero_ticket)
        self.assertIn('Cambio', fila[2])
        self.assertIn(pago.pedido.numero, fila[2])
        t = reporte['totales']
        self.assertEqual(t['Total de ventas'], 'Gs. 300.000')          # 180.000 + 120.000
        self.assertEqual(t['Cantidad de cobros'], 1)                    # el cambio no es venta
        self.assertEqual(t['Cambios de producto'], 1)
        self.assertEqual(t['  · Diferencia cobrada en cambios'], 'Gs. 120.000')

    def test_un_cambio_sin_diferencia_no_aparece_como_cobro_en_efectivo(self):
        pago = self._vender([(self.ceramica, '2', '90000')], medio='transferencia')
        self._cambio(pago, [(self.ceramica, '1', True)], [(self.ceramica, '1')])

        balance = rep.reporte_ventas(date.today(), date.today())
        self.assertNotIn('  · Efectivo', balance['totales'])
        self.assertTrue(any(f[4] == 'Sin diferencia' for f in balance['filas']))

        arqueo = rep.reporte_arqueo(date.today())
        conceptos = [f[0].strip() for f in arqueo['filas']]
        self.assertNotIn('Cobrado en efectivo', conceptos)
        self.assertIn('Cambios de producto', conceptos)
        self.assertEqual(arqueo['totales']['Cambios de producto en el día'], 1)

    def test_el_arqueo_muestra_la_diferencia_y_el_reintegro_del_cambio(self):
        pago = self._vender([(self.porcelanato, '2', '150000')])       # 300.000
        self._cambio(pago, [(self.porcelanato, '2', True)],
                     [(self.ceramica, '2')], medio_pago='efectivo')    # reintegra 120.000

        arqueo = rep.reporte_arqueo(date.today())
        filas = {f[0].strip(): f for f in arqueo['filas']}
        self.assertIn('crédito Gs. 300.000', filas['Cambios de producto'][1])
        self.assertEqual(filas['Reintegrado (incluido abajo)'][2], '- Gs. 120.000')
        self.assertEqual(filas['Efectivo que debe haber en el cajón'][2], 'Gs. 180.000')

    def test_el_tablero_cuenta_los_cambios_aparte(self):
        admin = crear_usuario('admin_dev', rol='admin')
        api = APIClient()
        api.force_authenticate(admin)
        pago = self._vender([(self.ceramica, '2', '90000')])
        self._cambio(pago, [(self.ceramica, '2', True)], [(self.porcelanato, '2')],
                     medio_pago='debito')

        r = api.get('/api/v1/caja/kpis/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['ventas']['hoy']['cantidad'], 1)
        self.assertEqual(r.data['ventas']['hoy']['total'], 300000.0)
        self.assertEqual(r.data['cambios_mes']['cantidad'], 1)
        self.assertEqual(r.data['cambios_mes']['diferencia_cobrada'], 120000.0)
        self.assertTrue(r.data['ultimas_ventas'][0]['es_cambio'])
        self.assertIn('Cambio', r.data['ultimas_ventas'][0]['medio'])
