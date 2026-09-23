"""
Tests de la API de datos de traslado.

Es lo que faltaba para poder emitir la nota de remisión: el XML ya salía bien,
pero nadie tenía dónde cargar el motivo, el vehículo y la dirección.

Lo que más importa acá es que el endpoint **no deje guardar un traslado que
después no se pueda emitir**. Las reglas que hacen que la remisión no vuelva
rechazada viven en `DatosTraslado.clean()`, y un `ModelSerializer` de DRF no
las corre solo: si no se las llama a mano, la pantalla acepta el dato, la
persona se va tranquila, y el error aparece recién en el worker — horas más
tarde y sin nadie que se acuerde del camión.
"""
from datetime import date

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.facturacion import codigos
from apps.facturacion.models import DatosTraslado

from .factories import (DATOS_FISCALES_COMPLETOS, SIFEN_PRENDIDO,
                        crear_pedido, crear_usuario, crear_variante)

TRASLADO_VALIDO = {
    'motivo': codigos.TRASLADO_POR_VENTA,
    'responsable': codigos.RESPONSABLE_EMISOR_FACTURA,
    'fecha_inicio_traslado': '2026-09-20',
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
class ApiDatosTrasladoTests(TestCase):
    databases = {'default', 'sync'}
    _n = 0

    def setUp(self):
        ApiDatosTrasladoTests._n += 1
        n = ApiDatosTrasladoTests._n
        self.usuario = crear_usuario(username=f'dep{n}', rol='deposito')
        variante = crear_variante(nombre=f'Piso API {n}')
        self.pedido = crear_pedido(self.usuario, [(variante, 2, 50000)])
        self.client = APIClient()
        self.client.force_authenticate(self.usuario)
        self.url = f'/api/v1/facturacion/pedidos/{self.pedido.pk}/traslado/'

    # ── Lectura ──────────────────────────────────────────────────────────

    def test_un_pedido_sin_traslado_no_es_un_error(self):
        # La mayoría de los pedidos no se entregan con remisión. Devolver 404
        # obligaría a la pantalla a distinguir "no existe" de "falló", y el
        # caso normal es justamente que no exista todavía.
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.data['existe'])
        self.assertEqual(respuesta.data['pedido_numero'], self.pedido.numero)

    def test_devuelve_lo_guardado_con_las_descripciones(self):
        self.client.put(self.url, TRASLADO_VALIDO, format='json')
        respuesta = self.client.get(self.url)
        self.assertTrue(respuesta.data['existe'])
        self.assertEqual(respuesta.data['motivo_descripcion'],
                         'Traslado por venta')
        self.assertEqual(respuesta.data['modalidad_descripcion'], 'Terrestre')

    # ── Guardado ─────────────────────────────────────────────────────────

    def test_guardar_por_primera_vez_crea(self):
        respuesta = self.client.put(self.url, TRASLADO_VALIDO, format='json')
        self.assertEqual(respuesta.status_code, 201)
        traslado = DatosTraslado.objects.get(pedido=self.pedido)
        self.assertEqual(traslado.vehiculo_matricula, 'ABC123')
        self.assertEqual(traslado.creado_por, self.usuario)

    def test_guardar_de_nuevo_actualiza_y_no_duplica(self):
        # Es OneToOne: un segundo POST daría error de unicidad. Por eso el
        # endpoint es PUT y decide él si crea o actualiza — quien carga la
        # pantalla aprieta "Guardar" y no tiene por qué saber la diferencia.
        self.client.put(self.url, TRASLADO_VALIDO, format='json')
        respuesta = self.client.put(
            self.url, dict(TRASLADO_VALIDO, kilometros=30), format='json')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(DatosTraslado.objects.filter(pedido=self.pedido).count(), 1)
        self.assertEqual(
            DatosTraslado.objects.get(pedido=self.pedido).kilometros, 30)

    # ── Las reglas que evitan un rechazo del SIFEN ───────────────────────

    def test_sin_identificar_el_vehiculo_no_guarda(self):
        datos = dict(TRASLADO_VALIDO)
        datos.pop('vehiculo_matricula')
        respuesta = self.client.put(self.url, datos, format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('vehiculo_matricula', respuesta.data)
        self.assertFalse(DatosTraslado.objects.filter(pedido=self.pedido).exists())

    def test_el_numero_de_vehiculo_sirve_igual_que_la_matricula(self):
        # El SIFEN acepta cualquiera de los dos (campo E967 dice cuál es).
        datos = dict(TRASLADO_VALIDO)
        datos.pop('vehiculo_matricula')
        datos['vehiculo_numero'] = 'INT-004'
        respuesta = self.client.put(self.url, datos, format='json')
        self.assertEqual(respuesta.status_code, 201)

    def test_sin_kilometros_no_guarda(self):
        # NT 010: los volvió obligatorios. Es el tipo de dato que nadie carga
        # si el formulario lo deja pasar, y sin él el documento vuelve
        # rechazado.
        datos = dict(TRASLADO_VALIDO)
        datos.pop('kilometros')
        respuesta = self.client.put(self.url, datos, format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('kilometros', respuesta.data)

    def test_sin_direccion_de_entrega_no_guarda(self):
        datos = dict(TRASLADO_VALIDO, direccion_entrega='')
        respuesta = self.client.put(self.url, datos, format='json')
        self.assertEqual(respuesta.status_code, 400)

    def test_el_error_nombra_el_campo_para_que_el_formulario_lo_marque(self):
        # Un cartel genérico arriba de todo obliga a releer veinticinco campos.
        datos = dict(TRASLADO_VALIDO)
        datos.pop('vehiculo_matricula')
        datos.pop('kilometros')
        respuesta = self.client.put(self.url, datos, format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.assertTrue(set(respuesta.data) & {'vehiculo_matricula', 'kilometros'})

    # ── Borrado ──────────────────────────────────────────────────────────

    def test_se_puede_borrar_si_no_se_emitio_la_remision(self):
        self.client.put(self.url, TRASLADO_VALIDO, format='json')
        respuesta = self.client.delete(self.url)
        self.assertEqual(respuesta.status_code, 204)
        self.assertFalse(DatosTraslado.objects.filter(pedido=self.pedido).exists())

    def test_borrar_lo_que_no_existe_no_falla(self):
        self.assertEqual(self.client.delete(self.url).status_code, 204)

    def test_no_se_borra_si_la_remision_ya_se_emitio(self):
        # El documento existe ante el DNIT: borrar sus datos lo dejaría sin
        # respaldo. Para deshacerlo hace falta el evento de cancelación.
        from apps.facturacion.models import DocumentoElectronico
        from apps.facturacion.emisor import crear_documento
        from .factories import RUC_RECEPTOR, crear_pago, crear_sesion

        self.client.put(self.url, TRASLADO_VALIDO, format='json')
        sesion = crear_sesion(self.usuario)
        pago = crear_pago(self.pedido, sesion, self.usuario, 100000)
        documento = crear_documento(
            pago, receptor={'ruc': RUC_RECEPTOR, 'razon_social': 'Cliente SRL'})
        documento.tipo_documento = codigos.TIPO_DE_NOTA_REMISION
        documento.estado = DocumentoElectronico.ESTADO_APROBADO
        documento.save(update_fields=['tipo_documento', 'estado'])

        respuesta = self.client.delete(self.url)
        self.assertEqual(respuesta.status_code, 409)
        self.assertTrue(DatosTraslado.objects.filter(pedido=self.pedido).exists())

    # ── Permisos ─────────────────────────────────────────────────────────

    def test_deposito_puede_cargarlo(self):
        # Es quien prepara la entrega y ve el camión.
        self.assertEqual(
            self.client.put(self.url, TRASLADO_VALIDO, format='json').status_code,
            201)

    def test_el_cajero_no_carga_traslados(self):
        cajero = crear_usuario(username=f'caj{self._n}', rol='cajero')
        cliente = APIClient()
        cliente.force_authenticate(cajero)
        self.assertEqual(cliente.get(self.url).status_code, 403)

    def test_sin_autenticar_no_se_ve_nada(self):
        self.assertIn(APIClient().get(self.url).status_code, (401, 403))


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class OpcionesTrasladoTests(TestCase):
    databases = {'default', 'sync'}

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(
            crear_usuario(username='dep_opts', rol='deposito'))

    def test_sirve_las_tablas_de_la_dnit(self):
        # La pantalla no tiene su propia copia: si la DNIT cambia un código se
        # toca codigos.py y nada más. Un código geográfico o de motivo mal
        # puesto es un documento rechazado.
        respuesta = self.client.get('/api/v1/facturacion/opciones-traslado/')
        self.assertEqual(respuesta.status_code, 200)
        for clave in ('motivos', 'responsables', 'modalidades',
                      'tipos_transporte', 'responsables_flete'):
            self.assertTrue(respuesta.data[clave], f'{clave} vino vacío')

    def test_los_motivos_son_los_trece_del_manual(self):
        respuesta = self.client.get('/api/v1/facturacion/opciones-traslado/')
        self.assertEqual(len(respuesta.data['motivos']),
                         len(codigos.MOTIVOS_TRASLADO))

    def test_sugiere_el_caso_normal_del_negocio(self):
        # Entrega su propia venta con su camión. Que el formulario abra lleno
        # no es comodidad: cuanto menos haya que elegir, menos chances de
        # elegir mal un código que después rechaza el SIFEN.
        respuesta = self.client.get('/api/v1/facturacion/opciones-traslado/')
        sugeridos = respuesta.data['sugeridos']
        self.assertEqual(sugeridos['motivo'], codigos.TRASLADO_POR_VENTA)
        self.assertEqual(sugeridos['tipo_transporte'], codigos.TRANSPORTE_PROPIO)
        self.assertEqual(sugeridos['responsable_flete'],
                         codigos.FLETE_TRANSPORTE_PROPIO)
        self.assertTrue(sugeridos['direccion_salida'])
