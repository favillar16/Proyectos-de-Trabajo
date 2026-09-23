"""
Los tres tipos de documento y evento que faltaban.

  · **Nota de débito** — el espejo de la de crédito: suma en vez de revertir.
    Lo que más importa probar es que nunca toque stock y que no acepte los
    motivos de devolución, que emitirían el documento al revés.
  · **Autofactura** — el único que documenta una compra, no una venta. No
    cuelga de un cobro y sus ítems se escriben a mano.
  · **Eventos del receptor** — lo que el local declara sobre un DTE ajeno,
    identificado solo por su CDC.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.facturacion import (autofactura, codigos, eventos_receptor,
                              nota_debito, payload)
from apps.facturacion.emisor import crear_documento
from apps.facturacion.models import EventoReceptor

from .factories import (DATOS_FISCALES_COMPLETOS, RUC_RECEPTOR, SIFEN_PRENDIDO,
                        crear_pago, crear_pedido, crear_sesion, crear_usuario,
                        crear_variante)

def cdc_ajeno(emitido=None) -> str:
    """
    CDC de un documento de un proveedor, con la fecha de emisión adentro.

    Las posiciones 26 a 33 no son relleno: de ahí sale la fecha con la que se
    cuenta el plazo de 45 días del receptor (Manual, Tabla J). Un CDC de
    ochos daba el año 8888 y el mes 88, o sea ninguna fecha.
    """
    emitido = emitido or date.today()
    return '01' + '8' * 23 + f'{emitido:%Y%m%d}' + '8' * 11


CDC_AJENO = cdc_ajeno()


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class NotaDebitoTests(TestCase):
    databases = {'default', 'sync'}
    _n = 0

    def setUp(self):
        NotaDebitoTests._n += 1
        n = NotaDebitoTests._n
        self.usuario = crear_usuario(username=f'adm_nd{n}', rol='admin')
        variante = crear_variante(nombre=f'Piso ND {n}')
        pedido = crear_pedido(self.usuario, [(variante, 1, 100000)])
        sesion = crear_sesion(self.usuario)
        pago = crear_pago(pedido, sesion, self.usuario, 100000)
        self.factura = crear_documento(
            pago, receptor={'ruc': RUC_RECEPTOR, 'razon_social': 'Cliente SRL'})

    def test_emite_con_numeracion_propia(self):
        nota = nota_debito.emitir(
            self.factura, motivo=codigos.MOTIVO_AJUSTE_PRECIO,
            monto=110000, usuario=self.usuario)
        self.assertEqual(nota.tipo_documento, codigos.TIPO_DE_NOTA_DEBITO)
        self.assertEqual(nota.cdc[:2], '06')
        self.assertEqual(nota.numero, 1)
        self.assertEqual(nota.documento_asociado_cdc, self.factura.cdc)

    def test_desglosa_el_iva_del_monto_nuevo(self):
        # El monto no sale de la factura: es un importe nuevo (interés,
        # flete) y su IVA hay que calcularlo desde cero.
        nota = nota_debito.emitir(
            self.factura, motivo=codigos.MOTIVO_RECUPERO_GASTO,
            monto=110000, usuario=self.usuario, tasa_iva=codigos.TASA_10)
        self.assertEqual(nota.total, Decimal('110000'))
        self.assertEqual(nota.iva_10, Decimal('10000'))
        self.assertEqual(nota.total_gravado_10, Decimal('100000'))

    def test_no_toca_stock(self):
        from apps.inventario.models import MovimientoStock
        antes = MovimientoStock.objects.count()
        nota_debito.emitir(self.factura, motivo=codigos.MOTIVO_AJUSTE_PRECIO,
                           monto=50000, usuario=self.usuario)
        self.assertEqual(MovimientoStock.objects.count(), antes)

    def test_rechaza_los_motivos_de_devolucion(self):
        # Devolver mercadería baja lo que el cliente debe, no lo sube.
        with self.assertRaises(nota_debito.NotaDebitoInvalida) as caso:
            nota_debito.emitir(self.factura, motivo=codigos.MOTIVO_DEVOLUCION,
                               monto=1000, usuario=self.usuario)
        self.assertIn('crédito', str(caso.exception))

    def test_rechaza_monto_cero_o_negativo(self):
        for monto in (0, -1000):
            with self.assertRaises(nota_debito.NotaDebitoInvalida):
                nota_debito.emitir(
                    self.factura, motivo=codigos.MOTIVO_AJUSTE_PRECIO,
                    monto=monto, usuario=self.usuario)

    def test_solo_sobre_una_factura(self):
        nota = nota_debito.emitir(
            self.factura, motivo=codigos.MOTIVO_AJUSTE_PRECIO,
            monto=1000, usuario=self.usuario)
        with self.assertRaises(nota_debito.NotaDebitoInvalida):
            nota_debito.emitir(nota, motivo=codigos.MOTIVO_AJUSTE_PRECIO,
                               monto=1000, usuario=self.usuario)

    def test_el_payload_la_arma(self):
        nota = nota_debito.emitir(
            self.factura, motivo=codigos.MOTIVO_AJUSTE_PRECIO,
            monto=110000, usuario=self.usuario)
        datos = payload.construir_data(nota)
        self.assertEqual(datos['tipoDocumento'], codigos.TIPO_DE_NOTA_DEBITO)
        self.assertEqual(datos['documentoAsociado']['cdc'], self.factura.cdc)


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class AutofacturaTests(TestCase):
    databases = {'default', 'sync'}

    VENDEDOR = {
        'numero_documento_vendedor': '1234567',
        'nombre_vendedor': 'Juan Particular',
        'direccion_vendedor': 'Calle Vieja 123',
        'departamento_vendedor': 6,
        'departamento_vendedor_desc': 'CAAGUAZU',
        'distrito_vendedor': 61,
        'distrito_vendedor_desc': 'CNEL. OVIEDO',
        'ciudad_vendedor': 2886,
        'ciudad_vendedor_desc': 'CNEL. OVIEDO',
        'lugar_transaccion': 'Local de Óga Porã',
        'departamento_transaccion': 6,
        'departamento_transaccion_desc': 'CAAGUAZU',
        'distrito_transaccion': 61,
        'distrito_transaccion_desc': 'CNEL. OVIEDO',
        'ciudad_transaccion': 2886,
        'ciudad_transaccion_desc': 'CNEL. OVIEDO',
    }
    ITEMS = [{'descripcion': 'Lote de cerámica usada', 'cantidad': '10',
              'precio_unitario': '25000'}]

    def setUp(self):
        self.admin = crear_usuario(username='adm_af', rol='admin')

    def test_emite_sin_cobro_detras(self):
        # Es el punto: una autofactura no viene de una venta.
        doc = autofactura.emitir(vendedor=self.VENDEDOR, items=self.ITEMS,
                                 usuario=self.admin)
        self.assertIsNone(doc.pago_id)
        self.assertEqual(doc.tipo_documento, codigos.TIPO_DE_AUTOFACTURA)
        self.assertEqual(doc.cdc[:2], '04')
        self.assertEqual(doc.total, Decimal('250000'))

    def test_el_receptor_es_el_propio_local(self):
        doc = autofactura.emitir(vendedor=self.VENDEDOR, items=self.ITEMS,
                                 usuario=self.admin)
        self.assertEqual(doc.receptor_ruc, doc.emisor_ruc)

    def test_guarda_el_vendedor_y_los_items(self):
        doc = autofactura.emitir(vendedor=self.VENDEDOR, items=self.ITEMS,
                                 usuario=self.admin)
        self.assertEqual(doc.datos_autofactura.nombre_vendedor,
                         'Juan Particular')
        self.assertEqual(doc.items_autofactura.count(), 1)

    def test_va_exenta_por_defecto(self):
        # Comprarle a un no contribuyente no genera crédito fiscal.
        doc = autofactura.emitir(vendedor=self.VENDEDOR, items=self.ITEMS,
                                 usuario=self.admin)
        self.assertEqual(doc.total_exento, Decimal('250000'))
        self.assertEqual(doc.iva_10, Decimal('0'))

    def test_el_payload_arma_el_grupo_del_vendedor(self):
        doc = autofactura.emitir(vendedor=self.VENDEDOR, items=self.ITEMS,
                                 usuario=self.admin)
        datos = payload.construir_data(doc)
        self.assertEqual(datos['autoFactura']['nombre'], 'Juan Particular')
        self.assertEqual(datos['autoFactura']['ubicacion']['lugar'],
                         'Local de Óga Porã')
        self.assertEqual(len(datos['items']), 1)

    def test_lista_todos_los_campos_que_faltan_de_una(self):
        # Quien carga esto lo hace de un formulario: corregir de a un campo
        # sería una ida y vuelta por campo.
        incompleto = dict(self.VENDEDOR)
        del incompleto['nombre_vendedor']
        del incompleto['lugar_transaccion']
        with self.assertRaises(autofactura.AutofacturaInvalida) as caso:
            autofactura.emitir(vendedor=incompleto, items=self.ITEMS,
                               usuario=self.admin)
        mensaje = str(caso.exception)
        self.assertIn('nombre_vendedor', mensaje)
        self.assertIn('lugar_transaccion', mensaje)

    def test_sin_items_no_emite(self):
        with self.assertRaises(autofactura.AutofacturaInvalida):
            autofactura.emitir(vendedor=self.VENDEDOR, items=[],
                               usuario=self.admin)

    def test_una_validacion_fallida_no_consume_numero(self):
        with self.assertRaises(autofactura.AutofacturaInvalida):
            autofactura.emitir(vendedor=self.VENDEDOR, items=[],
                               usuario=self.admin)
        doc = autofactura.emitir(vendedor=self.VENDEDOR, items=self.ITEMS,
                                 usuario=self.admin)
        self.assertEqual(doc.numero, 1)

    def test_no_mueve_inventario(self):
        from apps.inventario.models import MovimientoStock
        antes = MovimientoStock.objects.count()
        autofactura.emitir(vendedor=self.VENDEDOR, items=self.ITEMS,
                           usuario=self.admin)
        self.assertEqual(MovimientoStock.objects.count(), antes)


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class EventosReceptorTests(TestCase):
    databases = {'default', 'sync'}

    def setUp(self):
        self.admin = crear_usuario(username='adm_er', rol='admin')

    def test_conformidad_total(self):
        evento = eventos_receptor.registrar(
            tipo=EventoReceptor.TIPO_CONFORMIDAD, cdc=CDC_AJENO,
            usuario=self.admin,
            tipo_conformidad=EventoReceptor.CONFORMIDAD_TOTAL)
        self.assertEqual(evento.estado, EventoReceptor.ESTADO_PENDIENTE)
        self.assertTrue(evento.es_conclusivo)
        datos = eventos_receptor._datos_para_sifen(evento)
        self.assertEqual(datos, {'cdc': CDC_AJENO, 'tipoConformidad': 1})

    def test_la_conformidad_parcial_exige_fecha(self):
        with self.assertRaises(eventos_receptor.EventoReceptorInvalido):
            eventos_receptor.registrar(
                tipo=EventoReceptor.TIPO_CONFORMIDAD, cdc=CDC_AJENO,
                usuario=self.admin,
                tipo_conformidad=EventoReceptor.CONFORMIDAD_PARCIAL)

    def test_la_disconformidad_exige_motivo_largo(self):
        # El SIFEN rechaza "ok".
        with self.assertRaises(eventos_receptor.EventoReceptorInvalido):
            eventos_receptor.registrar(
                tipo=EventoReceptor.TIPO_DISCONFORMIDAD, cdc=CDC_AJENO,
                usuario=self.admin, motivo='ok')

    def test_rechaza_un_cdc_que_no_es_cdc(self):
        with self.assertRaises(eventos_receptor.EventoReceptorInvalido):
            eventos_receptor.registrar(
                tipo=EventoReceptor.TIPO_DISCONFORMIDAD, cdc='123',
                usuario=self.admin, motivo='La mercadería no llegó nunca')

    def test_no_deja_manifestarse_dos_veces_igual(self):
        eventos_receptor.registrar(
            tipo=EventoReceptor.TIPO_DISCONFORMIDAD, cdc=CDC_AJENO,
            usuario=self.admin, motivo='La mercadería no llegó nunca')
        with self.assertRaises(eventos_receptor.EventoReceptorInvalido):
            eventos_receptor.registrar(
                tipo=EventoReceptor.TIPO_DISCONFORMIDAD, cdc=CDC_AJENO,
                usuario=self.admin, motivo='La mercadería no llegó nunca')

    def test_la_notificacion_es_informativa(self):
        from django.utils import timezone
        evento = eventos_receptor.registrar(
            tipo=EventoReceptor.TIPO_NOTIFICACION, cdc=CDC_AJENO,
            usuario=self.admin,
            fecha_emision_documento=timezone.now(),
            fecha_recepcion=timezone.now(),
            total_documento=Decimal('500000'))
        self.assertFalse(evento.es_conclusivo)
        datos = eventos_receptor._datos_para_sifen(evento)
        self.assertEqual(datos['totalPYG'], 500000.0)
        # 19 caracteres exactos: la librería lo valida por largo.
        self.assertEqual(len(datos['fechaEmision']), 19)

    def test_un_tipo_que_no_existe_se_rechaza(self):
        with self.assertRaises(eventos_receptor.EventoReceptorInvalido):
            eventos_receptor.registrar(
                tipo='inventado', cdc=CDC_AJENO, usuario=self.admin)


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class ApiPantallasNuevasTests(TestCase):
    """
    Los endpoints que alimentan las dos pantallas nuevas.

    No prueban el HTML —eso no se testea acá— sino el contrato que la
    pantalla consume: que exista, que pida admin y que devuelva lo que el
    formulario necesita.
    """
    databases = {'default', 'sync'}

    def setUp(self):
        self.admin = crear_usuario(username='adm_api_pant', rol='admin')
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def test_la_autofactura_se_emite_por_la_api(self):
        r = self.api.post(
            reverse('fe-autofacturas'),
            {'vendedor': AutofacturaTests.VENDEDOR,
             'items': AutofacturaTests.ITEMS},
            format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['autofactura']['tipo_documento'],
                         codigos.TIPO_DE_AUTOFACTURA)

    def test_la_lista_de_autofacturas_trae_el_vendedor(self):
        # Es la columna que la pantalla muestra: sin eso la lista diría
        # "Consumidor Final" en todas, porque el receptor es el propio local.
        self.api.post(
            reverse('fe-autofacturas'),
            {'vendedor': AutofacturaTests.VENDEDOR,
             'items': AutofacturaTests.ITEMS},
            format='json')
        r = self.api.get(reverse('fe-autofacturas'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data[0]['vendedor'], 'Juan Particular')

    def test_un_vendedor_incompleto_no_emite(self):
        r = self.api.post(
            reverse('fe-autofacturas'),
            {'vendedor': {'nombre_vendedor': 'Solo el nombre'},
             'items': AutofacturaTests.ITEMS},
            format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('lugar_transaccion', r.data['error'])

    def test_el_evento_de_receptor_se_registra_por_la_api(self):
        r = self.api.post(
            reverse('fe-eventos-receptor'),
            {'tipo': 'disconformidad', 'cdc': CDC_AJENO,
             'motivo': 'La mercadería facturada nunca se entregó'},
            format='json')
        self.assertEqual(r.status_code, 201)
        self.assertTrue(EventoReceptor.objects.filter(cdc=CDC_AJENO).exists())

    def test_la_lista_de_eventos_dice_si_es_conclusivo(self):
        # Es lo que decide cuál usar, y no se deduce del nombre.
        self.api.post(
            reverse('fe-eventos-receptor'),
            {'tipo': 'notificacion', 'cdc': CDC_AJENO,
             'fecha_emision_documento': '2026-09-01T10:00:00',
             'fecha_recepcion': '2026-09-02T10:00:00',
             'total_documento': '500000'},
            format='json')
        r = self.api.get(reverse('fe-eventos-receptor'))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data[0]['conclusivo'])

    def test_un_cdc_invalido_devuelve_400_y_no_500(self):
        r = self.api.post(
            reverse('fe-eventos-receptor'),
            {'tipo': 'disconformidad', 'cdc': '123',
             'motivo': 'Un motivo suficientemente largo'},
            format='json')
        self.assertEqual(r.status_code, 400)

    def test_las_pantallas_nuevas_son_solo_de_admin(self):
        self.api.force_authenticate(
            crear_usuario(username='vend_pant', rol='vendedor'))
        for url in (reverse('fe-autofacturas'), reverse('fe-eventos-receptor'),
                    reverse('fe-geografia')):
            self.assertEqual(self.api.get(url).status_code, 403, url)

    def test_la_fecha_del_formulario_no_rompe_la_transmision(self):
        # El formulario manda un `datetime-local`: texto sin zona. Antes el
        # evento se registraba pero la transmisión moría con
        # "'str' object has no attribute 'utcoffset'", un error que no dice
        # nada sobre la fecha. Y guardarla naive la corría cuatro horas.
        evento = eventos_receptor.registrar(
            tipo=EventoReceptor.TIPO_NOTIFICACION, cdc=CDC_AJENO,
            usuario=self.admin,
            fecha_emision_documento='2026-09-01T10:00:00',
            fecha_recepcion='2026-09-02T10:00:00',
            total_documento=Decimal('500000'))

        from django.utils import timezone as tz
        self.assertFalse(tz.is_naive(evento.fecha_recepcion))

        datos = eventos_receptor._datos_para_sifen(evento)
        # 19 caracteres exactos: la librería lo valida por largo.
        self.assertEqual(len(datos['fechaEmision']), 19)
        self.assertTrue(datos['fechaEmision'].startswith('2026-09-01T10:00'))
