"""
Tests del cobro con cheque y su llegada al documento electrónico.

Por qué importa, en dos planos:

  · Fiscal — el grupo E630 del Manual Técnico se activa **siempre** que el
    medio de pago es cheque (E606 = 2), y sus dos campos, número y banco
    emisor, son de ocurrencia 1-1. Un cheque sin ellos vuelve rechazado.
  · Del negocio — y este rige aunque el SIFEN esté apagado: un cheque es una
    promesa de pago, no un cobro consumado como la tarjeta. Sin banco ni
    número, el local se queda con un papel que no puede cruzar contra el
    extracto.

De ahí la diferencia con la tarjeta, que estos tests fijan explícitamente:
los datos del cheque se exigen en todo cobro, no solo al facturar.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.caja import cheque as cheque_mod
from apps.caja.models import DatosCheque, Pago
from apps.caja.views import _datos_ticket
from apps.facturacion import codigos, payload
from apps.facturacion.emisor import crear_documento

from .factories import (DATOS_FISCALES_COMPLETOS, RUC_RECEPTOR, SIFEN_APAGADO,
                        SIFEN_PRENDIDO, crear_pago, crear_pedido, crear_sesion,
                        crear_usuario, crear_variante)


class ValidacionDelChequeTests(TestCase):
    """Lo que la cajera copia del papel, antes de que toque la base."""

    databases = {'default'}

    def test_sin_numero_no_hay_cheque(self):
        with self.assertRaises(cheque_mod.ErrorCheque) as caso:
            cheque_mod.validar({'banco': 'Banco Continental'})
        self.assertIn('número', str(caso.exception).lower())

    def test_completa_el_numero_con_ceros_hasta_ocho(self):
        # El manual es literal: "completar con 0 (cero) a la izquierda hasta
        # alcanzar 8 (ocho) cifras" (campo E631).
        datos = cheque_mod.validar({'numero': '12345', 'banco': 'Banco Atlas'})
        self.assertEqual(datos.numero, '00012345')

    def test_ignora_lo_que_no_sean_digitos_del_numero(self):
        datos = cheque_mod.validar({'numero': 'N° 123-456', 'banco': 'Banco Atlas'})
        self.assertEqual(datos.numero, '00123456')

    def test_un_numero_de_mas_de_ocho_digitos_no_se_acepta(self):
        # Recortarlo en silencio sería peor: quedaría guardado un cheque que
        # no es el que está en la caja.
        with self.assertRaises(cheque_mod.ErrorCheque):
            cheque_mod.validar({'numero': '123456789', 'banco': 'Banco Atlas'})

    def test_sin_banco_no_hay_cheque(self):
        with self.assertRaises(cheque_mod.ErrorCheque) as caso:
            cheque_mod.validar({'numero': '12345'})
        self.assertIn('banco', str(caso.exception).lower())

    def test_una_sigla_corta_no_pasa(self):
        # El campo E632 es de 4 a 20 caracteres: "BNF" volvería rechazado.
        with self.assertRaises(cheque_mod.ErrorCheque):
            cheque_mod.validar({'numero': '12345', 'banco': 'BNF'})

    def test_el_banco_se_recorta_al_maximo_del_sifen(self):
        datos = cheque_mod.validar({
            'numero': '1', 'banco': 'Banco Continental del Paraguay SA'})
        self.assertEqual(len(datos.banco), codigos.LARGO_MAX_BANCO)

    def test_normaliza_los_espacios_del_banco_y_del_titular(self):
        datos = cheque_mod.validar({
            'numero': '1', 'banco': '  Banco   Itaú ', 'titular': ' Juan  Pérez '})
        self.assertEqual(datos.banco, 'Banco Itaú')
        self.assertEqual(datos.titular, 'Juan Pérez')

    def test_sin_fecha_el_cheque_es_a_la_vista(self):
        datos = cheque_mod.validar({'numero': '1', 'banco': 'Banco Atlas'})
        self.assertIsNone(datos.fecha_cobro)
        self.assertFalse(datos.es_diferido)

    def test_una_fecha_futura_lo_vuelve_diferido(self):
        manana = timezone.localdate() + timedelta(days=30)
        datos = cheque_mod.validar({
            'numero': '1', 'banco': 'Banco Atlas', 'fecha_cobro': manana.isoformat()})
        self.assertEqual(datos.fecha_cobro, manana)
        self.assertTrue(datos.es_diferido)

    def test_una_fecha_que_no_se_entiende_se_avisa(self):
        # Guardar None en silencio convertiría un cheque diferido en uno a la
        # vista, que es justo el error que después nadie encuentra.
        with self.assertRaises(cheque_mod.ErrorCheque):
            cheque_mod.validar({'numero': '1', 'banco': 'Banco Atlas',
                                'fecha_cobro': '30/09/2026'})

    def test_acepta_una_fecha_ya_convertida(self):
        datos = cheque_mod.validar({'numero': '1', 'banco': 'Banco Atlas',
                                    'fecha_cobro': date(2026, 12, 1)})
        self.assertEqual(datos.fecha_cobro, date(2026, 12, 1))

    def test_sabe_que_medios_necesitan_datos_de_cheque(self):
        self.assertTrue(cheque_mod.requiere_datos_de_cheque('cheque'))
        for otro in ('efectivo', 'credito', 'debito', 'transferencia'):
            with self.subTest(medio=otro):
                self.assertFalse(cheque_mod.requiere_datos_de_cheque(otro))


class ModeloDatosChequeTests(TestCase):
    databases = {'default', 'sync'}

    def setUp(self):
        usuario = crear_usuario(username='cajero_cheque_modelo')
        variante = crear_variante(nombre='Producto cheque modelo')
        pedido = crear_pedido(usuario, [(variante, 1, 100000)])
        sesion = crear_sesion(usuario)
        self.pago = crear_pago(pedido, sesion, usuario, 100000, medio='cheque')

    def test_el_modelo_normaliza_el_numero_aunque_se_cargue_a_mano(self):
        # La validación de caja no es el único camino a la tabla: el admin y
        # los scripts escriben directo.
        datos = DatosCheque.objects.create(
            pago=self.pago, numero='7', banco='Banco Basa')
        self.assertEqual(datos.numero, '00000007')

    def test_la_descripcion_corta_sirve_para_el_ticket(self):
        datos = DatosCheque.objects.create(
            pago=self.pago, numero='45', banco='Banco Familiar',
            fecha_cobro=date(2026, 10, 15))
        self.assertIn('00000045', datos.descripcion_corta)
        self.assertIn('Banco Familiar', datos.descripcion_corta)
        self.assertIn('15/10/2026', datos.descripcion_corta)

    def test_el_ticket_lleva_el_detalle_del_cheque(self):
        DatosCheque.objects.create(
            pago=self.pago, numero='45', banco='Banco Familiar')
        self.pago.refresh_from_db()
        datos = _datos_ticket(self.pago.pedido, self.pago, self.pago.sesion_caja)
        self.assertIn('Banco Familiar', datos['detalle_pago'])

    def test_un_pago_sin_cheque_no_agrega_detalle(self):
        datos = _datos_ticket(self.pago.pedido, self.pago, self.pago.sesion_caja)
        self.assertEqual(datos['detalle_pago'], '')


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class ChequeEnElDocumentoTests(TestCase):
    """Los datos del cheque tienen que llegar al XML."""

    databases = {'default', 'sync'}
    _secuencia = 0

    def _documento(self, medio='cheque', cheque=None):
        ChequeEnElDocumentoTests._secuencia += 1
        n = ChequeEnElDocumentoTests._secuencia
        usuario = crear_usuario(username=f'cajero_cheque{n}')
        variante = crear_variante(nombre=f'Producto cheque {n}')
        pedido = crear_pedido(usuario, [(variante, 1, 100000)])
        sesion = crear_sesion(usuario)
        pago = crear_pago(pedido, sesion, usuario, 100000, medio=medio)
        if cheque is not None:
            DatosCheque.objects.create(pago=pago, **cheque)
        return crear_documento(
            pago, receptor={'ruc': RUC_RECEPTOR, 'razon_social': 'Cliente SRL'})

    def test_el_cobro_con_cheque_declara_el_medio_de_pago_dos(self):
        documento = self._documento(
            cheque={'numero': '12345', 'banco': 'Banco Continental'})
        entrega = payload.construir_data(documento)['condicion']['entregas'][0]
        self.assertEqual(entrega['tipo'], codigos.PAGO_CHEQUE)

    def test_el_pago_con_cheque_lleva_el_grupo_infoCheque(self):
        documento = self._documento(
            cheque={'numero': '12345', 'banco': 'Banco Continental'})
        entrega = payload.construir_data(documento)['condicion']['entregas'][0]

        self.assertIn('infoCheque', entrega)
        self.assertEqual(entrega['infoCheque']['numeroCheque'], '00012345')
        self.assertEqual(entrega['infoCheque']['banco'], 'Banco Continental')

    def test_el_numero_va_siempre_con_sus_ocho_cifras(self):
        # xmlgen también completa con ceros, pero el payload no depende de
        # eso: el largo lo fija el manual, no la librería.
        documento = self._documento(cheque={'numero': '7', 'banco': 'Banco Atlas'})
        entrega = payload.construir_data(documento)['condicion']['entregas'][0]
        self.assertEqual(entrega['infoCheque']['numeroCheque'], '00000007')

    def test_el_pago_en_efectivo_no_lleva_infoCheque(self):
        # El grupo se activa solo si E606 = 2. Mandarlo en otro cobro sería
        # declarar un cheque que no existió.
        documento = self._documento(medio='efectivo')
        entrega = payload.construir_data(documento)['condicion']['entregas'][0]
        self.assertNotIn('infoCheque', entrega)

    def test_un_cheque_sin_datos_no_arma_un_documento_a_medias(self):
        documento = self._documento(cheque=None)
        with self.assertRaises(payload.DatosIncompletos) as caso:
            payload.construir_data(documento)
        self.assertIn('cheque', str(caso.exception).lower())


class CobroConChequeEnCajaTests(TestCase):
    """El camino completo: la pantalla de cobro contra la API real."""

    databases = {'default', 'sync'}

    def setUp(self):
        from rest_framework.test import APIClient

        self.cajero = crear_usuario(username='cajero_cheque_api')
        self.variante = crear_variante(nombre='Producto cheque API',
                                       precio=Decimal('110000'))
        self.variante.stock.cantidad = Decimal('10')
        self.variante.stock.save(update_fields=['cantidad'])
        self.pedido = crear_pedido(self.cajero, [(self.variante, 1, '110000')])
        # El factory arma los ítems pero no toca los totales del pedido, y
        # acá el monto importa: el arqueo del cierre se hace sobre él.
        self.pedido.recalcular_totales()
        self.sesion = crear_sesion(self.cajero)
        self.client = APIClient()
        self.client.force_authenticate(self.cajero)

    def _cobrar(self, **extra):
        cuerpo = {'pedido_id': self.pedido.id, 'medio_pago': 'cheque'}
        cuerpo.update(extra)
        return self.client.post('/api/v1/caja/pagos/', cuerpo, format='json')

    @override_settings(SIFEN=SIFEN_APAGADO)
    def test_el_cheque_exige_sus_datos_aunque_sea_un_ticket(self):
        # Acá se separa del cobro con tarjeta a propósito: la tarjeta ya fue
        # autorizada por la terminal, el cheque todavía no es plata.
        resp = self._cobrar()
        self.assertEqual(resp.status_code, 400)
        self.assertIn('cheque', str(resp.data).lower())
        self.assertFalse(Pago.objects.filter(pedido=self.pedido).exists())

    @override_settings(SIFEN=SIFEN_APAGADO)
    def test_un_cobro_con_cheque_completo_entra(self):
        resp = self._cobrar(datos_cheque={
            'numero': '12345', 'banco': 'Banco Continental',
            'titular': 'JUAN PEREZ'})
        self.assertEqual(resp.status_code, 201, resp.data)

        pago = Pago.objects.get(pedido=self.pedido)
        self.assertEqual(pago.medio_pago, Pago.MEDIO_CHEQUE)
        self.assertEqual(pago.datos_cheque.numero, '00012345')
        self.assertEqual(pago.datos_cheque.banco, 'Banco Continental')
        self.assertEqual(pago.datos_cheque.titular, 'JUAN PEREZ')

    @override_settings(SIFEN=SIFEN_APAGADO)
    def test_el_banco_en_sigla_frena_el_cobro_con_el_cliente_presente(self):
        resp = self._cobrar(datos_cheque={'numero': '12345', 'banco': 'BNF'})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Pago.objects.filter(pedido=self.pedido).exists())

    @override_settings(SIFEN=SIFEN_APAGADO)
    def test_el_cheque_diferido_guarda_su_fecha(self):
        fecha = timezone.localdate() + timedelta(days=45)
        resp = self._cobrar(datos_cheque={
            'numero': '999', 'banco': 'Banco Atlas',
            'fecha_cobro': fecha.isoformat()})
        self.assertEqual(resp.status_code, 201, resp.data)

        datos = Pago.objects.get(pedido=self.pedido).datos_cheque
        self.assertEqual(datos.fecha_cobro, fecha)
        self.assertTrue(datos.es_diferido)

    @override_settings(SIFEN=SIFEN_APAGADO)
    def test_el_cheque_no_cuenta_como_efectivo_en_el_arqueo(self):
        # El arqueo compara el cajón físico contra apertura + ventas en
        # efectivo. Un cheque no entra al cajón: si contara, todo turno con
        # cheques mostraría un faltante que no existe.
        self._cobrar(datos_cheque={'numero': '5', 'banco': 'Banco Basa'})
        resp = self.client.post(
            f'/api/v1/caja/sesiones/{self.sesion.id}/cerrar/',
            {'monto_cierre': '0'}, format='json')

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['total_efectivo'], 0)
        self.assertEqual(resp.data['resumen_medios'].get('cheque'), 110000)
        self.assertEqual(resp.data['diferencia'], 0)

    @override_settings(SIFEN=SIFEN_APAGADO)
    def test_los_otros_medios_siguen_sin_pedir_nada(self):
        # El cheque no le agrega requisitos a ningún cobro que ya funcionaba.
        resp = self.client.post('/api/v1/caja/pagos/', {
            'pedido_id': self.pedido.id, 'medio_pago': 'transferencia',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
