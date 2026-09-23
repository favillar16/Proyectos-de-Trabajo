"""
Tests de la emisión de la nota de remisión.

Lo que se prueba acá es el disparador, que era lo único que faltaba: el
payload, el CDC y el KuDE de la remisión ya tenían sus tests, pero nada
creaba el documento — el tipo 7 solo aparecía asignado a mano en los tests.

La regla de fondo que explica la forma de todo esto: la remisión respalda el
**traslado**, no la venta (Decreto 6.539/2005 art. 30), y la RG 41/2014 art. 5
exime de emitirla cuando la mercadería viaja con el comprobante de venta. Por
eso emitir es una acción explícita y no un efecto del cobro, y por eso el
primer test que importa es que cobrar NO genere una remisión sola.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.facturacion import codigos, remision
from apps.facturacion.emisor import crear_documento
from apps.facturacion.models import DatosTraslado, DocumentoElectronico

from .factories import (DATOS_FISCALES_COMPLETOS, RUC_RECEPTOR, SIFEN_PRENDIDO,
                        crear_pago, crear_pedido, crear_sesion, crear_usuario,
                        crear_variante)

TRASLADO = {
    'motivo': codigos.TRASLADO_POR_VENTA,
    'responsable': codigos.RESPONSABLE_EMISOR_FACTURA,
    'fecha_inicio_traslado': date(2026, 9, 20),
    'kilometros': 12,
    'tipo_transporte': codigos.TRANSPORTE_PROPIO,
    'modalidad': codigos.MODALIDAD_TERRESTRE,
    'responsable_flete': codigos.FLETE_TRANSPORTE_PROPIO,
    'vehiculo_tipo': 'Camion',
    'vehiculo_marca': 'Hyundai',
    'vehiculo_matricula': 'ABC123',
    'direccion_entrega': 'Avda. Mcal. Lopez 1234',
}


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class BaseEmisionRemisionTests(TestCase):
    databases = {'default', 'sync'}
    _n = 0

    def _escenario(self, *, con_traslado=True, con_factura=True,
                   ruc=RUC_RECEPTOR, **campos_traslado):
        """Un pedido cobrado, con o sin traslado y con o sin factura."""
        BaseEmisionRemisionTests._n += 1
        n = BaseEmisionRemisionTests._n

        self.usuario = crear_usuario(username=f'rem{n}', rol='deposito')
        variante = crear_variante(nombre=f'Piso REM {n}')
        self.pedido = crear_pedido(self.usuario, [(variante, 2, 50000)])
        if ruc:
            self.pedido.cliente_ruc = ruc
            self.pedido.cliente_nombre = 'Cliente SRL'
            self.pedido.save(update_fields=['cliente_ruc', 'cliente_nombre'])

        sesion = crear_sesion(self.usuario)
        self.pago = crear_pago(self.pedido, sesion, self.usuario, 100000)

        self.factura = None
        if con_factura:
            self.factura = crear_documento(
                self.pago,
                receptor={'ruc': ruc, 'razon_social': 'Cliente SRL'})

        if con_traslado:
            datos = dict(TRASLADO)
            datos.update(campos_traslado)
            DatosTraslado.objects.create(
                pedido=self.pedido, creado_por=self.usuario, **datos)

        return self.pago


class EmisionTests(BaseEmisionRemisionTests):

    def test_cobrar_no_emite_remision_sola(self):
        # El punto de toda la sección: no toda venta lleva remisión. Si el
        # cliente se lleva la mercadería con su factura, no hace falta
        # ninguna, así que el cobro no puede generarla por su cuenta.
        self._escenario()
        self.assertFalse(
            DocumentoElectronico.objects.filter(
                tipo_documento=codigos.TIPO_DE_NOTA_REMISION).exists())

    def test_emite_el_documento_del_tipo_correcto(self):
        pago = self._escenario()
        nota = remision.emitir(pago, usuario=self.usuario)

        self.assertEqual(nota.tipo_documento, codigos.TIPO_DE_NOTA_REMISION)
        self.assertEqual(nota.estado, DocumentoElectronico.ESTADO_PENDIENTE)
        # El tipo de documento viaja dentro del CDC, posiciones 0-1.
        self.assertEqual(nota.cdc[:2], '07')
        self.assertEqual(len(nota.cdc), 44)

    def test_numeracion_independiente_de_la_factura(self):
        # Cada tipo de documento tiene su propio correlativo: la primera
        # remisión es la 1 aunque ya existan facturas. Confundirlos haría
        # que el SIFEN rechace por número repetido.
        pago = self._escenario()
        self.assertEqual(self.factura.numero, 1)

        nota = remision.emitir(pago, usuario=self.usuario)
        self.assertEqual(nota.numero, 1)
        self.assertEqual(nota.numero_completo, '001-001-0000001')
        self.assertNotEqual(nota.cdc, self.factura.cdc)

    def test_referencia_el_cdc_de_su_factura(self):
        pago = self._escenario()
        nota = remision.emitir(pago, usuario=self.usuario)
        self.assertEqual(nota.documento_asociado_cdc, self.factura.cdc)

    def test_copia_el_timbrado_de_la_factura(self):
        # Mismo criterio que la nota de crédito: los documentos de una misma
        # operación declaran el mismo timbrado, aunque settings haya cambiado.
        pago = self._escenario()
        nota = remision.emitir(pago, usuario=self.usuario)
        self.assertEqual(nota.emisor_timbrado, self.factura.emisor_timbrado)
        self.assertEqual(nota.receptor_ruc, self.factura.receptor_ruc)

    def test_no_declara_iva(self):
        # El Manual V150 exceptúa al tipo 7 del valor total por ítem (E720) y
        # del grupo de IVA (E730): una remisión no liquida impuesto.
        pago = self._escenario()
        nota = remision.emitir(pago, usuario=self.usuario)
        self.assertEqual(nota.iva_10, Decimal('0'))
        self.assertEqual(nota.iva_5, Decimal('0'))
        self.assertEqual(nota.total_gravado_10, Decimal('0'))

    def test_no_mueve_stock(self):
        # La mercadería ya se descontó al confirmar el pago. Una remisión
        # describe un movimiento, no cambia existencias.
        from apps.inventario.models import MovimientoStock

        pago = self._escenario()
        antes = MovimientoStock.objects.count()
        remision.emitir(pago, usuario=self.usuario)
        self.assertEqual(MovimientoStock.objects.count(), antes)

    def test_emite_sin_factura_previa(self):
        # El campo E506 del manual ("fecha futura de emisión de la factura")
        # existe justamente porque la remisión puede salir antes que ella.
        pago = self._escenario(con_factura=False)
        nota = remision.emitir(pago, usuario=self.usuario)
        self.assertEqual(nota.documento_asociado_cdc, '')
        self.assertEqual(nota.receptor_ruc, RUC_RECEPTOR)


class ValidacionesTests(BaseEmisionRemisionTests):

    def test_sin_datos_de_traslado_no_emite(self):
        pago = self._escenario(con_traslado=False)
        with self.assertRaises(remision.RemisionInvalida) as ctx:
            remision.emitir(pago, usuario=self.usuario)
        self.assertIn('traslado', str(ctx.exception).lower())

    def test_sin_kilometros_no_emite(self):
        # NT 010: el campo E505 pasó a ser obligatorio.
        pago = self._escenario(kilometros=None)
        with self.assertRaises(remision.RemisionInvalida) as ctx:
            remision.emitir(pago, usuario=self.usuario)
        self.assertIn('kilómetros', str(ctx.exception))

    def test_receptor_innominado_no_emite(self):
        # NT 023: la remisión nunca admite receptor sin identificar.
        pago = self._escenario(con_factura=False, ruc='')
        with self.assertRaises(remision.RemisionInvalida) as ctx:
            remision.emitir(pago, usuario=self.usuario)
        self.assertIn('innominado', str(ctx.exception).lower())

    def test_no_emite_dos_veces(self):
        pago = self._escenario()
        primera = remision.emitir(pago, usuario=self.usuario)
        with self.assertRaises(remision.RemisionInvalida) as ctx:
            remision.emitir(pago, usuario=self.usuario)
        self.assertIn(primera.numero_completo, str(ctx.exception))

    def test_una_validacion_fallida_no_consume_numero(self):
        # Si el correlativo avanzara con cada intento fallido quedarían
        # huecos que hay que declarar por el evento de inutilización.
        pago = self._escenario(con_traslado=False)
        with self.assertRaises(remision.RemisionInvalida):
            remision.emitir(pago, usuario=self.usuario)

        DatosTraslado.objects.create(
            pedido=self.pedido, creado_por=self.usuario, **TRASLADO)
        nota = remision.emitir(pago, usuario=self.usuario)
        self.assertEqual(nota.numero, 1)


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class ApiRemisionTests(BaseEmisionRemisionTests):

    def setUp(self):
        self.pago = self._escenario()
        self.client = APIClient()
        self.client.force_authenticate(self.usuario)
        self.url = f'/api/v1/facturacion/pedidos/{self.pedido.pk}/remision/'

    def test_get_dice_que_todavia_no_existe(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data['existe'])

    def test_post_emite_y_get_la_encuentra(self):
        r = self.client.post(self.url, {}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.data['ok'])
        numero = r.data['remision']['numero']

        r2 = self.client.get(self.url)
        self.assertTrue(r2.data['existe'])
        self.assertEqual(r2.data['numero'], numero)

    def test_post_repetido_devuelve_400_y_no_duplica(self):
        self.client.post(self.url, {}, format='json')
        r = self.client.post(self.url, {}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            DocumentoElectronico.objects.filter(
                tipo_documento=codigos.TIPO_DE_NOTA_REMISION).count(), 1)

    def test_pedido_sin_cobro_confirmado_devuelve_400(self):
        usuario = crear_usuario(username='sincobro', rol='deposito')
        pedido = crear_pedido(usuario, [(crear_variante('Sin cobro'), 1, 1000)])
        cliente = APIClient()
        cliente.force_authenticate(usuario)
        r = cliente.post(
            f'/api/v1/facturacion/pedidos/{pedido.pk}/remision/', {},
            format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('cobro', r.data['error'].lower())

    def test_el_kude_de_la_remision_se_puede_descargar(self):
        # Es el papel que viaja con la mercadería: si esto no sale, emitir no
        # sirve de nada.
        r = self.client.post(self.url, {}, format='json')
        doc_id = r.data['remision']['id']

        admin = crear_usuario(username='admin_kude', rol='admin')
        cliente = APIClient()
        cliente.force_authenticate(admin)
        r2 = cliente.get(f'/api/v1/facturacion/documentos/{doc_id}/kude/')
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2['Content-Type'], 'application/pdf')
