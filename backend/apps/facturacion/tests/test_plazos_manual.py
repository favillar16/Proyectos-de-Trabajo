"""
Los plazos y la cadena de cancelación que fija el Manual V150 y que el
sistema no aplicaba.

Salieron de releer el Manual el 23/09/2026. Cada uno viene de un lugar
distinto y **no todos se comportan igual**, que es lo que más importa acá:

  · **45 días del receptor** (Tabla J, filas 10 a 13) — bloquea. Se cuenta
    desde la fecha de emisión del documento del proveedor, que viaja adentro
    del CDC.
  · **15 días para corregir un evento del receptor** (Tabla K) — todavía no
    hay evento de corrección que emitir, así que por ahora solo se calcula.
  · **15 primeros días del mes siguiente, inutilización** (Tabla J, fila 2) —
    **avisa pero no impide**: un hueco sin declarar no tiene otro camino.
  · **Vigencia del timbrado** (misma fila, «plazo del sistema») — bloquea,
    porque ese lo hace cumplir el SIFEN.
  · **Cancelación en cadena** (Tabla J, fila 1) — bloquea: primero se cancela
    el último DTE asociado y se va hacia atrás.
"""
from datetime import date, datetime, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.facturacion import codigos, eventos, eventos_receptor
from apps.facturacion.cdc import fecha_de_emision
from apps.facturacion.cdc import generar as cdc_generar
from apps.facturacion.emisor import crear_documento
from apps.facturacion.models import DocumentoElectronico, EventoReceptor

from .factories import (DATOS_FISCALES_COMPLETOS, RUC_RECEPTOR, SIFEN_PRENDIDO,
                        crear_pago, crear_pedido, crear_sesion, crear_usuario,
                        crear_variante)


def cdc_emitido_el(dia):
    """Un CDC de 44 dígitos que lleva esa fecha en las posiciones 26 a 33."""
    return '01' + '8' * 23 + f'{dia:%Y%m%d}' + '8' * 11


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class BasePlazos(TestCase):
    databases = {'default', 'sync'}
    _secuencia = 0

    @classmethod
    def _nuevo(cls):
        cls._secuencia += 1
        return cls._secuencia

    def setUp(self):
        self.admin = crear_usuario(
            username=f'admin_pl{self._nuevo()}', rol='admin')

    def _documento(self, aprobado=True, tipo=codigos.TIPO_DE_FACTURA):
        n = self._nuevo()
        usuario = crear_usuario(username=f'cajero_pl{n}')
        variante = crear_variante(nombre=f'Producto pl{n}')
        pedido = crear_pedido(usuario, [(variante, 1, 100000)])
        sesion = crear_sesion(usuario)
        pago = crear_pago(pedido, sesion, usuario, 100000)
        documento = crear_documento(
            pago, receptor={'ruc': RUC_RECEPTOR, 'razon_social': 'Cliente SRL'})
        documento.tipo_documento = tipo
        if aprobado:
            documento.estado = DocumentoElectronico.ESTADO_APROBADO
            documento.fecha_aprobacion = timezone.now()
        documento.save()
        return documento


# ─── 45 días del receptor ────────────────────────────────────────────────────

class PlazoDelReceptorTests(BasePlazos):

    def _registrar(self, cdc):
        return eventos_receptor.registrar(
            tipo=EventoReceptor.TIPO_CONFORMIDAD, cdc=cdc, usuario=self.admin,
            tipo_conformidad=EventoReceptor.CONFORMIDAD_TOTAL)

    def test_la_fecha_sale_del_cdc_y_no_hay_que_preguntarla(self):
        self.assertEqual(fecha_de_emision(cdc_emitido_el(date(2026, 3, 14))),
                         date(2026, 3, 14))

    def test_lee_bien_un_cdc_armado_de_verdad_y_no_solo_el_de_prueba(self):
        # `cdc_emitido_el()` corta en las mismas posiciones que la función
        # que se está probando, así que por sí solo no demuestra nada: si el
        # rango estuviera corrido, los dos estarían corridos igual. Esta es
        # la prueba que rompe esa circularidad — el CDC lo arma `generar()`,
        # que compone los 44 dígitos campo por campo.
        emitido = date(2026, 3, 14)
        armado = cdc_generar(
            ruc_emisor=RUC_RECEPTOR, establecimiento='001',
            punto_expedicion='001', numero='0000123',
            tipo_contribuyente=2, fecha_emision=emitido)
        self.assertEqual(fecha_de_emision(armado), emitido)

    def test_un_documento_de_ayer_se_puede_manifestar(self):
        cdc = cdc_emitido_el(timezone.localdate() - timedelta(days=1))
        self.assertEqual(self._registrar(cdc).cdc, cdc)

    def test_el_dia_45_todavia_entra(self):
        cdc = cdc_emitido_el(timezone.localdate() - timedelta(days=45))
        self.assertEqual(eventos_receptor.dias_restantes_para_registrar(cdc), 0)
        self.assertEqual(
            eventos_receptor.motivo_por_el_que_no_se_puede_registrar(cdc), '')

    def test_el_dia_46_ya_no(self):
        cdc = cdc_emitido_el(timezone.localdate() - timedelta(days=46))
        with self.assertRaises(eventos_receptor.EventoReceptorInvalido) as e:
            self._registrar(cdc)
        self.assertIn('45', str(e.exception))
        self.assertFalse(EventoReceptor.objects.filter(cdc=cdc).exists())

    def test_el_mensaje_dice_por_cuanto_se_paso(self):
        cdc = cdc_emitido_el(timezone.localdate() - timedelta(days=50))
        self.assertIn(
            '5 día(s)',
            eventos_receptor.motivo_por_el_que_no_se_puede_registrar(cdc))

    def test_un_cdc_sin_fecha_valida_no_se_registra_a_ciegas(self):
        # El año 8888 y el mes 88 no son una fecha. Antes esto pasaba
        # derecho, porque del CDC solo se miraba el largo.
        cdc = '01' + '8' * 42
        self.assertIsNone(eventos_receptor.dias_restantes_para_registrar(cdc))
        with self.assertRaises(eventos_receptor.EventoReceptorInvalido):
            self._registrar(cdc)

    def test_el_plazo_se_revisa_antes_que_los_campos_de_cada_tipo(self):
        # Una conformidad que no dice si es total o parcial también es
        # inválida, pero si además está fuera de plazo lo que corresponde
        # decir es lo del plazo: no tiene sentido mandar a completar un
        # formulario que no se va a poder guardar igual.
        cdc = cdc_emitido_el(timezone.localdate() - timedelta(days=90))
        with self.assertRaises(eventos_receptor.EventoReceptorInvalido) as e:
            eventos_receptor.registrar(
                tipo=EventoReceptor.TIPO_CONFORMIDAD, cdc=cdc,
                usuario=self.admin)
        self.assertIn('Venció el plazo', str(e.exception))


# ─── 15 días para corregir (Tabla K) ─────────────────────────────────────────

class VentanaDeCorreccionTests(BasePlazos):

    def _evento(self, dias_atras=0, estado=EventoReceptor.ESTADO_APROBADO):
        evento = eventos_receptor.registrar(
            tipo=EventoReceptor.TIPO_CONFORMIDAD,
            cdc=cdc_emitido_el(timezone.localdate()), usuario=self.admin,
            tipo_conformidad=EventoReceptor.CONFORMIDAD_TOTAL)
        evento.estado = estado
        evento.save(update_fields=['estado'])
        # `fecha_creacion` es auto_now_add: para moverla hay que pasar por un
        # update, que no la vuelve a escribir.
        EventoReceptor.objects.filter(pk=evento.pk).update(
            fecha_creacion=timezone.now() - timedelta(days=dias_atras))
        evento.refresh_from_db()
        return evento

    def test_recien_registrado_quedan_15_dias(self):
        self.assertEqual(
            eventos_receptor.dias_restantes_para_corregir(self._evento()), 15)

    def test_el_dia_15_todavia_se_corrige(self):
        self.assertTrue(
            eventos_receptor.se_puede_corregir(self._evento(dias_atras=15)))

    def test_el_dia_16_ya_no(self):
        self.assertFalse(
            eventos_receptor.se_puede_corregir(self._evento(dias_atras=16)))

    def test_un_evento_rechazado_no_se_corrige_se_vuelve_a_registrar(self):
        self.assertFalse(eventos_receptor.se_puede_corregir(
            self._evento(estado=EventoReceptor.ESTADO_RECHAZADO)))

    def test_un_evento_que_el_sifen_no_contesto_todavia_no_se_corrige(self):
        self.assertFalse(eventos_receptor.se_puede_corregir(
            self._evento(estado=EventoReceptor.ESTADO_PENDIENTE)))


# ─── Plazo de la inutilización ───────────────────────────────────────────────

class FechaLimiteDeInutilizacionTests(TestCase):

    def test_es_el_15_del_mes_siguiente(self):
        self.assertEqual(eventos.fecha_limite_inutilizacion(date(2026, 9, 20)),
                         date(2026, 10, 15))

    def test_diciembre_cae_en_enero_del_ano_siguiente(self):
        self.assertEqual(eventos.fecha_limite_inutilizacion(date(2026, 12, 3)),
                         date(2027, 1, 15))

    def test_el_primero_del_mes_tambien_vence_el_15_del_siguiente(self):
        self.assertEqual(eventos.fecha_limite_inutilizacion(date(2026, 2, 1)),
                         date(2026, 3, 15))


class AvisoDeInutilizacionFueraDePlazoTests(BasePlazos):

    TIPO = codigos.TIPO_DE_FACTURA

    def _documento_numero(self, numero, emitido):
        documento = self._documento()
        documento.numero = numero
        documento.numero_completo = f'001-001-{numero:07d}'
        documento.fecha_emision = timezone.make_aware(
            datetime(emitido.year, emitido.month, emitido.day, 10, 0))
        documento.save()
        return documento

    def test_sin_documento_posterior_no_hay_hecho_que_fechar(self):
        # Números que la secuencia reservó pero todavía no pasó de largo: el
        # salto no se consumó, así que no hay plazo corriendo.
        self.assertIsNone(
            eventos.fecha_del_hecho(self.TIPO, '001', '001', hasta=900))
        self.assertEqual(
            eventos.advertencia_de_plazo_inutilizacion(
                self.TIPO, '001', '001', hasta=900), '')

    def test_el_hecho_es_la_fecha_del_documento_que_siguio_de_largo(self):
        self._documento_numero(900, timezone.localdate() - timedelta(days=10))
        self.assertEqual(
            eventos.fecha_del_hecho(self.TIPO, '001', '001', hasta=899),
            timezone.localdate() - timedelta(days=10))

    def test_un_salto_reciente_no_genera_aviso(self):
        self._documento_numero(901, timezone.localdate())
        self.assertEqual(
            eventos.advertencia_de_plazo_inutilizacion(
                self.TIPO, '001', '001', hasta=900), '')

    def test_un_salto_viejo_avisa_y_dice_las_dos_fechas(self):
        hecho = timezone.localdate() - timedelta(days=120)
        self._documento_numero(902, hecho)
        aviso = eventos.advertencia_de_plazo_inutilizacion(
            self.TIPO, '001', '001', hasta=901)
        self.assertIn(f'{hecho:%d/%m/%Y}', aviso)
        self.assertIn(
            f'{eventos.fecha_limite_inutilizacion(hecho):%d/%m/%Y}', aviso)

    def test_fuera_de_plazo_igual_deja_declarar(self):
        # Es la decisión que separa este plazo del de cancelación: un hueco
        # sin declarar no tiene camino alternativo, así que avisar es lo
        # correcto e impedir sería dejar el correlativo roto para siempre.
        self._documento_numero(903, timezone.localdate() - timedelta(days=200))
        evento = eventos.registrar_inutilizacion(
            tipo_documento=self.TIPO, establecimiento='001',
            punto_expedicion='001', desde=880, hasta=882,
            motivo='Salto de numeración detectado tarde', usuario=self.admin)
        self.assertEqual(evento.numero_desde, 880)


class TimbradoVencidoTests(BasePlazos):

    def test_con_el_timbrado_vigente_no_molesta(self):
        self.assertEqual(eventos.timbrado_vencido(), '')

    @override_settings(DATOS_FISCALES={**DATOS_FISCALES_COMPLETOS,
                                       'timbrado_vto': '2020-01-31'})
    def test_un_timbrado_vencido_impide_inutilizar(self):
        with self.assertRaises(eventos.EventoNoPermitido) as e:
            eventos.registrar_inutilizacion(
                tipo_documento=codigos.TIPO_DE_FACTURA, establecimiento='001',
                punto_expedicion='001', desde=800, hasta=801,
                motivo='Salto de numeración', usuario=self.admin)
        self.assertIn('31/01/2020', str(e.exception))

    @override_settings(DATOS_FISCALES={**DATOS_FISCALES_COMPLETOS,
                                       'timbrado_vto': ''})
    def test_sin_fecha_cargada_no_bloquea(self):
        self.assertEqual(eventos.timbrado_vencido(), '')

    @override_settings(DATOS_FISCALES={**DATOS_FISCALES_COMPLETOS,
                                       'timbrado_vto': 'el año que viene'})
    def test_una_fecha_ilegible_en_el_env_no_frena_una_declaracion(self):
        self.assertEqual(eventos.timbrado_vencido(), '')


# ─── Cancelación en cadena (Tabla J, fila 1) ─────────────────────────────────

class CancelacionEnCadenaTests(BasePlazos):

    def _asociar(self, hijo, padre, estado=DocumentoElectronico.ESTADO_APROBADO,
                 tipo=codigos.TIPO_DE_NOTA_CREDITO):
        hijo.documento_asociado_cdc = padre.cdc
        hijo.tipo_documento = tipo
        hijo.estado = estado
        hijo.save()
        return hijo

    def test_una_factura_sin_nada_colgado_se_cancela(self):
        self.assertEqual(eventos.motivo_por_el_que_no_se_puede_cancelar(
            self._documento()), '')

    def test_una_factura_con_nota_de_credito_viva_no_se_cancela_primero(self):
        factura = self._documento()
        nota = self._asociar(self._documento(), factura)
        motivo = eventos.motivo_por_el_que_no_se_puede_cancelar(factura)
        self.assertIn(nota.numero_completo, motivo)
        self.assertIn('último', motivo)

    def test_la_nota_si_se_puede_cancelar_porque_es_la_punta_de_la_cadena(self):
        factura = self._documento()
        nota = self._asociar(self._documento(), factura)
        self.assertEqual(
            eventos.motivo_por_el_que_no_se_puede_cancelar(nota), '')

    def test_una_nota_ya_cancelada_deja_libre_a_la_factura(self):
        factura = self._documento()
        self._asociar(self._documento(), factura,
                      estado=DocumentoElectronico.ESTADO_CANCELADO)
        self.assertEqual(
            eventos.motivo_por_el_que_no_se_puede_cancelar(factura), '')

    def test_una_nota_rechazada_no_cuenta_porque_nunca_fue_dte(self):
        factura = self._documento()
        self._asociar(self._documento(), factura,
                      estado=DocumentoElectronico.ESTADO_RECHAZADO)
        self.assertEqual(
            eventos.motivo_por_el_que_no_se_puede_cancelar(factura), '')

    def test_una_nota_todavia_en_la_cola_tambien_frena(self):
        # Está pendiente de transmitir: va a ser un DTE en minutos. Cancelar
        # la factura ahora invertiría el orden que pide el manual.
        factura = self._documento()
        self._asociar(self._documento(), factura,
                      estado=DocumentoElectronico.ESTADO_PENDIENTE)
        self.assertIn('asociado', eventos.motivo_por_el_que_no_se_puede_cancelar(
            factura))

    def test_una_remision_asociada_frena_igual_que_una_nota(self):
        # No son solo las notas: `remision.emitir()` también referencia la
        # factura por su CDC.
        factura = self._documento()
        self._asociar(self._documento(), factura,
                      tipo=codigos.TIPO_DE_NOTA_REMISION)
        self.assertIn('asociado', eventos.motivo_por_el_que_no_se_puede_cancelar(
            factura))

    def test_no_se_confunde_con_documentos_de_otra_factura(self):
        factura = self._documento()
        otra = self._documento()
        self._asociar(self._documento(), otra)
        self.assertEqual(
            eventos.motivo_por_el_que_no_se_puede_cancelar(factura), '')


# ─── Lo que ve quien está del otro lado de la pantalla ───────────────────────

class PlazosPorLaApiTests(BasePlazos):
    """
    Que las reglas nuevas lleguen como un 400 con texto legible y no como un
    500, y que el aviso de la inutilización no se quede solo en el log.
    """

    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def test_un_evento_fuera_de_plazo_devuelve_400_y_lo_explica(self):
        cdc = cdc_emitido_el(timezone.localdate() - timedelta(days=60))
        r = self.api.post(
            reverse('fe-eventos-receptor'),
            {'tipo': 'disconformidad', 'cdc': cdc,
             'motivo': 'La mercadería facturada nunca se entregó'},
            format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('45', r.data['error'])
        self.assertFalse(EventoReceptor.objects.filter(cdc=cdc).exists())

    def test_dentro_de_plazo_se_registra_igual_que_siempre(self):
        cdc = cdc_emitido_el(timezone.localdate() - timedelta(days=3))
        r = self.api.post(
            reverse('fe-eventos-receptor'),
            {'tipo': 'disconformidad', 'cdc': cdc,
             'motivo': 'La mercadería facturada nunca se entregó'},
            format='json')
        self.assertEqual(r.status_code, 201)

    def test_la_inutilizacion_tardia_devuelve_el_aviso_en_el_cuerpo(self):
        documento = self._documento()
        documento.numero = 950
        documento.numero_completo = '001-001-0000950'
        documento.fecha_emision = timezone.now() - timedelta(days=200)
        documento.save()

        r = self.api.post(
            reverse('fe-inutilizaciones'),
            {'tipo_documento': codigos.TIPO_DE_FACTURA,
             'establecimiento': '001', 'punto_expedicion': '001',
             'desde': 940, 'hasta': 942,
             'motivo': 'Salto de numeración detectado tarde'},
            format='json')
        self.assertEqual(r.status_code, 201)
        self.assertIn('fuera de plazo', r.data['advertencia'])

    def test_una_inutilizacion_en_plazo_no_trae_advertencia(self):
        documento = self._documento()
        documento.numero = 960
        documento.numero_completo = '001-001-0000960'
        documento.save()

        r = self.api.post(
            reverse('fe-inutilizaciones'),
            {'tipo_documento': codigos.TIPO_DE_FACTURA,
             'establecimiento': '001', 'punto_expedicion': '001',
             'desde': 955, 'hasta': 956,
             'motivo': 'Salto de numeración del día'},
            format='json')
        self.assertEqual(r.status_code, 201)
        self.assertNotIn('advertencia', r.data)
