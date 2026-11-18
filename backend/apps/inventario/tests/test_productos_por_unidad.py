"""
Recorrido completo del stock de un producto que se vende por unidad.

La propietaria reportó (18/11/2026) inconsistencias en las cantidades de
grifería. Los tests del resto de la suite usan productos por m² (la fábrica
`crear_variante` los crea así), así que nada probaba de punta a punta que un
grifo se cuente de a uno. Este recorrido pasa por los endpoints reales, en el
orden en que se usan en el local: alta, pedido desde el Showroom, agregar y
quitar productos, enviar a caja, cobrar, cancelar y devolver. Después de cada
paso el stock tiene que cuadrar con su historial y con los pedidos vivos.
"""
from decimal import Decimal

from django.db.models import Sum
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.caja import devoluciones
from apps.caja.models import Devolucion, Pago
from apps.facturacion.tests.factories import crear_sesion, crear_usuario
from apps.inventario.models import MovimientoStock, Stock
from apps.productos.models import Categoria, Producto, Variante
from apps.ventas.models import ItemPedido, NotaPedido


@override_settings(SIFEN_HABILITADO=False)
class GriferiaDePuntaAPuntaTests(TestCase):
    databases = {'default', 'sync'}

    def setUp(self):
        self.admin = crear_usuario('admin_unidades', rol='admin')
        self.sesion = crear_sesion(self.admin)
        categoria = Categoria.objects.create(nombre='Grifería prueba')
        self.producto = Producto.objects.create(
            nombre='FV canilla lavatorio Clásico', categoria=categoria,
            precio_base=Decimal('250000'), unidad_venta=Producto.UNIDAD_PIEZA)
        self.grifo = Variante.objects.create(producto=self.producto, color='Cromo')
        self.stock().registrar_movimiento(
            MovimientoStock.TIPO_ENTRADA, Decimal('5'), self.admin,
            observaciones='carga inicial')
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    # ── ayudas ───────────────────────────────────────────────
    def stock(self):
        return Stock.objects.get(variante=self.grifo)

    def cuadra(self, cantidad, reservada):
        st = self.stock()
        self.assertEqual(st.cantidad, Decimal(cantidad))
        self.assertEqual(st.cantidad_reservada, Decimal(reservada))
        ultimo = MovimientoStock.objects.filter(variante=self.grifo).latest('id')
        self.assertEqual(st.cantidad, ultimo.cantidad_posterior,
                         'el stock no coincide con su último movimiento')
        vivos = (ItemPedido.objects
                 .filter(variante=self.grifo, pedido__estado__in=NotaPedido.ESTADOS_CON_RESERVA)
                 .aggregate(t=Sum('cantidad'))['t'] or Decimal('0'))
        self.assertEqual(st.cantidad_reservada, vivos,
                         'lo reservado no coincide con los pedidos vivos')

    def pedir(self, cantidad):
        r = self.api.post(reverse('pedidos-list'), {
            'cliente_nombre': 'Cliente mostrador',
            'items': [{'variante_id': self.grifo.id, 'cantidad': cantidad}],
        }, format='json')
        return r

    def cobrar(self, pedido_id):
        r = self.api.post(reverse('pedido-estado', args=[pedido_id]),
                          {'estado': 'listo'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        pedido = NotaPedido.objects.get(pk=pedido_id)
        r = self.api.post(reverse('registrar-pago'), {
            'pedido_id': pedido_id, 'medio_pago': 'efectivo',
            'monto_recibido': int(pedido.monto_a_cobrar),
        }, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        return Pago.objects.get(pedido_id=pedido_id)

    # ── el recorrido ─────────────────────────────────────────
    def test_un_grifo_se_cuenta_de_a_uno_en_todo_el_ciclo(self):
        self.cuadra(5, 0)

        # Pedido de 2 desde el Showroom: reserva 2, quedan 3 para vender.
        r = self.pedir(2)
        self.assertEqual(r.status_code, 201, r.data)
        p1 = r.data['id']
        self.cuadra(5, 2)
        self.assertEqual(self.stock().cantidad_disponible, Decimal('3'))

        # Otro vendedor no puede llevarse 4: solo quedan 3.
        self.assertEqual(self.pedir(4).status_code, 400)
        self.cuadra(5, 2)

        # El cliente suma uno más al mismo pedido: mismo renglón, reserva 3.
        r = self.api.post(reverse('pedido-agregar-items', args=[p1]),
                          {'items': [{'variante_id': self.grifo.id, 'cantidad': 1}]},
                          format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(ItemPedido.objects.filter(pedido_id=p1).count(), 1)
        self.cuadra(5, 3)

        # Un segundo pedido de 2 se arma y se cancela: libera exactamente 2.
        r = self.pedir(2)
        self.assertEqual(r.status_code, 201, r.data)
        p2 = r.data['id']
        self.cuadra(5, 5)
        r = self.api.post(reverse('pedido-estado', args=[p2]),
                          {'estado': 'cancelado'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.cuadra(5, 3)

        # Un tercero de 1, al que se le saca el ítem: libera 1.
        r = self.pedir(1)
        p3 = r.data['id']
        self.cuadra(5, 4)
        item = ItemPedido.objects.get(pedido_id=p3)
        r = self.api.delete(reverse('item-cancelar', args=[p3, item.id]))
        self.assertEqual(r.status_code, 200)
        self.cuadra(5, 3)

        # Se cobra el primero: salen 3 del depósito y no queda nada reservado.
        pago = self.cobrar(p1)
        self.cuadra(2, 0)

        # Devuelven 1 en buen estado: vuelve al stock.
        devoluciones.registrar(
            pago_original=pago, sesion=self.sesion, usuario=self.admin,
            motivo=Devolucion.MOTIVO_ESTADO_INADECUADO, medio_pago='efectivo',
            items=[{'item_id': ItemPedido.objects.get(pedido_id=p1).id,
                    'cantidad': 1, 'reingresa_stock': True}])
        self.cuadra(3, 0)

        # Un conteo de depósito fija la cantidad exacta.
        r = self.api.post(reverse('stock-ajuste'), {
            'variante_id': self.grifo.id, 'tipo': 'ajuste', 'cantidad': 3,
        }, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.cuadra(3, 0)


class CargaEnCajasSegunUnidadTests(TestCase):
    """
    "Cargar en cajas" convierte a la unidad en que se vende el producto.

    Hasta el 18/11/2026 la conversión multiplicaba siempre por los m² de la
    caja: 2 cajas de una bacha 50×40 de a 2 por caja sumaban 0,8 al stock en
    vez de 4 bachas. Las pantallas no ofrecían cajas para estos productos,
    pero el alta, el ajuste y la recepción a proveedor pasan todos por
    `Variante.convertir_a_unidad_venta`, así que la cuenta tiene que estar
    bien ahí.
    """
    databases = {'default', 'sync'}

    def setUp(self):
        self.admin = crear_usuario('admin_cajas', rol='admin')
        self.categoria = Categoria.objects.create(nombre='Cajas prueba')
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def variante(self, unidad, **datos):
        producto = Producto.objects.create(
            nombre=f'Producto {unidad} {Producto.objects.count()}', categoria=self.categoria,
            precio_base=Decimal('100000'), unidad_venta=unidad)
        return Variante.objects.create(producto=producto, color='Blanco', **datos)

    def entrada(self, variante, cantidad, unidad):
        return self.api.post(reverse('stock-ajuste'), {
            'variante_id': variante.id, 'tipo': 'entrada',
            'cantidad': cantidad, 'unidad_ingreso': unidad,
        }, format='json')

    def test_bacha_por_pieza_con_medidas_suma_piezas_y_no_m2(self):
        bacha = self.variante(Producto.UNIDAD_PIEZA, largo_cm=Decimal('50'),
                              ancho_cm=Decimal('40'), piezas_por_caja=2)
        r = self.entrada(bacha, 2, 'caja')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Stock.objects.get(variante=bacha).cantidad, Decimal('4'))
        mov = MovimientoStock.objects.filter(variante=bacha).latest('id')
        self.assertIn('2 caja(s) × 2 piezas = 4.0000 piezas', mov.observaciones)

    def test_juego_en_pallets(self):
        juego = self.variante(Producto.UNIDAD_JUEGO, piezas_por_caja=3, cajas_por_pallet=10)
        self.assertEqual(juego.convertir_a_unidad_venta(2, 'pallet'), Decimal('60'))

    def test_producto_que_se_vende_por_caja(self):
        caja = self.variante(Producto.UNIDAD_CAJA, largo_cm=Decimal('60'),
                             ancho_cm=Decimal('60'), piezas_por_caja=4, cajas_por_pallet=40)
        self.assertEqual(caja.convertir_a_unidad_venta(3, 'caja'), Decimal('3'))
        self.assertEqual(caja.convertir_a_unidad_venta(1, 'pallet'), Decimal('40'))

    def test_pieza_sin_piezas_por_caja_no_inventa_un_numero(self):
        grifo = self.variante(Producto.UNIDAD_PIEZA, largo_cm=Decimal('20'), ancho_cm=Decimal('10'))
        r = self.entrada(grifo, 2, 'caja')
        self.assertEqual(r.status_code, 400)
        self.assertIn('piezas por caja', r.data['error'])
        self.assertEqual(Stock.objects.get(variante=grifo).cantidad, Decimal('0'))

    def test_metro_lineal_se_carga_en_metros(self):
        zocalo = self.variante(Producto.UNIDAD_ML, largo_cm=Decimal('60'),
                               ancho_cm=Decimal('8'), piezas_por_caja=10)
        with self.assertRaisesMessage(ValueError, 'metros lineales'):
            zocalo.convertir_a_unidad_venta(1, 'caja')

    def test_m2_sigue_igual(self):
        piso = self.variante(Producto.UNIDAD_M2, m2_por_caja=Decimal('2.52'), cajas_por_pallet=48)
        self.assertEqual(piso.convertir_a_unidad_venta(10, 'caja'), Decimal('25.2000'))
        self.assertEqual(piso.convertir_a_unidad_venta(1, 'pallet'), Decimal('120.9600'))
        sin_dato = self.variante(Producto.UNIDAD_M2)
        with self.assertRaisesMessage(ValueError, 'no tiene m² por caja'):
            sin_dato.convertir_a_unidad_venta(1, 'caja')
