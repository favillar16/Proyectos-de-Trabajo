"""
Tests de los datos de traslado y de la nota de remisión.

La remisión es el documento más distinto de los cinco: no describe un cobro
sino un movimiento de mercadería, así que sus datos cuelgan del pedido y se
cargan al preparar la entrega, no al facturar.
"""
from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.facturacion import codigos, payload
from apps.facturacion.emisor import crear_documento
from apps.facturacion.models import DatosTraslado

from .factories import (DATOS_FISCALES_COMPLETOS, RUC_RECEPTOR, SIFEN_PRENDIDO,
                        crear_pago, crear_pedido, crear_sesion, crear_usuario,
                        crear_variante)


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class BaseRemisionTests(TestCase):
    databases = {'default', 'sync'}
    _secuencia = 0

    TRASLADO_MINIMO = {
        'motivo': codigos.TRASLADO_POR_VENTA,
        'fecha_inicio_traslado': date(2026, 9, 15),
        'vehiculo_tipo': 'Camion',
        'vehiculo_marca': 'Hyundai',
        'vehiculo_matricula': 'ABC123',
        'direccion_entrega': 'Avda. Mcal. Lopez 1234',
        # Obligatorio desde la NT 010.
        'kilometros': 12,
    }

    def _documento_remision(self, traslado=None):
        BaseRemisionTests._secuencia += 1
        n = BaseRemisionTests._secuencia
        self.usuario = crear_usuario(username=f'user_nr{n}')
        variante = crear_variante(nombre=f'Piso NR {n}')
        self.pedido = crear_pedido(self.usuario, [(variante, 2, 50000)])
        sesion = crear_sesion(self.usuario)
        pago = crear_pago(self.pedido, sesion, self.usuario, 100000)
        documento = crear_documento(
            pago, receptor={'ruc': RUC_RECEPTOR, 'razon_social': 'Cliente SRL'})

        if traslado is not None:
            DatosTraslado.objects.create(
                pedido=self.pedido, creado_por=self.usuario, **traslado)

        documento.tipo_documento = codigos.TIPO_DE_NOTA_REMISION
        documento.save(update_fields=['tipo_documento'])
        return documento


class ValidacionDelTrasladoTests(BaseRemisionTests):

    def _traslado_suelto(self, sufijo, **campos):
        usuario = crear_usuario(username=f'user_val{sufijo}')
        pedido = crear_pedido(usuario, [(crear_variante(f'V{sufijo}'), 1, 1000)])
        return DatosTraslado(pedido=pedido, creado_por=usuario, **campos)

    def test_exige_identificar_el_vehiculo(self):
        # El SIFEN pide o la matrícula o el número: un traslado sin vehículo
        # identificable vuelve rechazado.
        traslado = self._traslado_suelto(
            'veh', motivo=codigos.TRASLADO_POR_VENTA,
            fecha_inicio_traslado=date(2026, 9, 15),
            kilometros=12, direccion_entrega='Alguna calle')
        with self.assertRaises(ValidationError) as caso:
            traslado.clean()
        self.assertIn('vehiculo_matricula', caso.exception.message_dict)

    def test_exige_la_direccion_de_entrega(self):
        traslado = self._traslado_suelto(
            'dir', fecha_inicio_traslado=date(2026, 9, 15), kilometros=12,
            vehiculo_matricula='ABC123', direccion_entrega='   ')
        with self.assertRaises(ValidationError) as caso:
            traslado.clean()
        self.assertIn('direccion_entrega', caso.exception.message_dict)

    def test_deduce_como_se_identifica_el_vehiculo(self):
        con_chapa = self._traslado_suelto('chapa', vehiculo_matricula='ABC123')
        sin_chapa = self._traslado_suelto('num', vehiculo_numero='CHASIS-99')
        self.assertEqual(con_chapa.tipo_identificacion_vehiculo,
                         codigos.VEHICULO_POR_MATRICULA)
        self.assertEqual(sin_chapa.tipo_identificacion_vehiculo,
                         codigos.VEHICULO_POR_NUMERO)


class PayloadDeLaRemisionTests(BaseRemisionTests):

    def test_sin_datos_de_traslado_avisa_que_faltan(self):
        documento = self._documento_remision(traslado=None)
        with self.assertRaises(payload.DatosIncompletos) as caso:
            payload.construir_data(documento)
        self.assertIn('traslado', str(caso.exception).lower())

    def test_arma_el_motivo_y_el_responsable(self):
        documento = self._documento_remision(traslado=self.TRASLADO_MINIMO)
        data = payload.construir_data(documento)
        self.assertEqual(data['remision']['motivo'], codigos.TRASLADO_POR_VENTA)
        self.assertEqual(data['remision']['tipoResponsable'],
                         codigos.RESPONSABLE_EMISOR_FACTURA)

    def test_declara_el_vehiculo_por_matricula(self):
        documento = self._documento_remision(traslado=self.TRASLADO_MINIMO)
        vehiculo = payload.construir_data(documento)['transporte']['vehiculos'][0]
        self.assertEqual(vehiculo['numeroMatricula'], 'ABC123')
        self.assertEqual(vehiculo['tipoIdentificacion'],
                         codigos.VEHICULO_POR_MATRICULA)
        self.assertNotIn('numeroVehiculo', vehiculo)

    def test_declara_el_vehiculo_por_numero_cuando_no_hay_chapa(self):
        traslado = dict(self.TRASLADO_MINIMO)
        traslado.pop('vehiculo_matricula')
        traslado['vehiculo_numero'] = 'CHASIS-99'
        documento = self._documento_remision(traslado=traslado)
        vehiculo = payload.construir_data(documento)['transporte']['vehiculos'][0]
        self.assertEqual(vehiculo['numeroVehiculo'], 'CHASIS-99')
        self.assertNotIn('numeroMatricula', vehiculo)

    def test_sin_transportista_no_manda_el_grupo(self):
        # El manual lo hace opcional cuando el transporte es propio. Mandarlo
        # vacío sería peor que omitirlo.
        documento = self._documento_remision(traslado=self.TRASLADO_MINIMO)
        self.assertNotIn('transportista',
                         payload.construir_data(documento)['transporte'])

    def test_un_transportista_con_ruc_va_como_contribuyente(self):
        traslado = dict(self.TRASLADO_MINIMO,
                        transportista_nombre='Fletes del Este SRL',
                        transportista_ruc=RUC_RECEPTOR,
                        conductor_nombre='Pedro Gimenez',
                        conductor_documento='1234567')
        documento = self._documento_remision(traslado=traslado)
        transportista = (payload.construir_data(documento)
                         ['transporte']['transportista'])
        self.assertTrue(transportista['contribuyente'])
        self.assertEqual(transportista['ruc'], RUC_RECEPTOR)
        self.assertEqual(transportista['chofer']['nombre'], 'Pedro Gimenez')

    def test_un_transportista_con_cedula_no_va_como_contribuyente(self):
        # Mismo criterio que con el receptor: una cédula no es un RUC.
        traslado = dict(self.TRASLADO_MINIMO,
                        transportista_nombre='Juan Fletero',
                        transportista_documento='4123456')
        documento = self._documento_remision(traslado=traslado)
        transportista = (payload.construir_data(documento)
                         ['transporte']['transportista'])
        self.assertFalse(transportista['contribuyente'])
        self.assertNotIn('ruc', transportista)
        self.assertEqual(transportista['documentoNumero'], '4123456')

    def test_la_entrega_cae_en_el_domicilio_del_local_si_faltan_codigos(self):
        # Preferible declarar un domicilio real y validable que mandar el
        # grupo incompleto.
        documento = self._documento_remision(traslado=self.TRASLADO_MINIMO)
        entrega = payload.construir_data(documento)['transporte']['entrega']
        self.assertEqual(entrega['direccion'], 'Avda. Mcal. Lopez 1234')
        self.assertEqual(entrega['departamento'],
                         DATOS_FISCALES_COMPLETOS['departamento'])

    def test_usa_los_codigos_de_entrega_cuando_estan_cargados(self):
        traslado = dict(self.TRASLADO_MINIMO,
                        entrega_departamento=11,
                        entrega_departamento_desc='ALTO PARANA',
                        entrega_distrito=145,
                        entrega_distrito_desc='CIUDAD DEL ESTE',
                        entrega_ciudad=3432, entrega_ciudad_desc='CDE')
        documento = self._documento_remision(traslado=traslado)
        entrega = payload.construir_data(documento)['transporte']['entrega']
        self.assertEqual(entrega['departamento'], 11)
        self.assertEqual(entrega['ciudadDescripcion'], 'CDE')

    def test_la_remision_no_declara_los_grupos_de_los_otros_tipos(self):
        documento = self._documento_remision(traslado=self.TRASLADO_MINIMO)
        data = payload.construir_data(documento)
        self.assertNotIn('factura', data)
        self.assertNotIn('notaCreditoDebito', data)


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class CamposQueExigeXmlgenTests(BaseRemisionTests):
    """
    Los campos de la remisión que el validador de `xmlgen` reclamó.

    De dónde salen estos tests: el 16/09/2026 se armó la primera nota de
    remisión de verdad contra el sidecar y la librería la rechazó con **diez**
    errores de golpe. El bloque de la remisión era el único de los tres tipos
    construidos que nunca se había probado contra `xmlgen` — se había escrito
    leyendo el manual, y el manual no alcanza.

    Cada test de acá es uno de esos diez. No son hipótesis sobre lo que el
    SIFEN podría pedir: son cosas que la implementación de referencia de la
    DNIT rechazó explícitamente.
    """

    def _data(self, **campos):
        documento = self._documento_remision(
            dict(self.TRASLADO_MINIMO, **campos))
        return payload.construir_data(documento)

    def test_la_fecha_de_inicio_usa_el_nombre_que_espera_la_libreria(self):
        # La clave es `inicioEstimadoTranslado`, con "Transl". Parece un error
        # de tipeo de la librería y lo es, pero es el nombre real: escribirlo
        # "bien" hace que xmlgen no vea el campo y rechace el documento por
        # obligatorio. Verificado en jsonDeMain.service.js.
        transporte = self._data()['transporte']
        self.assertIn('inicioEstimadoTranslado', transporte)
        self.assertNotIn('inicioEstimadoTraslado', transporte)

    def test_la_fecha_de_fin_siempre_va(self):
        # Las dos fechas son obligatorias. El sistema solo captura la de
        # inicio porque la entrega es el mismo día; cuando no hay fecha de fin
        # se declara la de inicio antes que omitir el campo.
        transporte = self._data()['transporte']
        self.assertEqual(transporte['finEstimadoTranslado'],
                         transporte['inicioEstimadoTranslado'])

    def test_la_fecha_de_fin_cargada_gana(self):
        transporte = self._data(
            fecha_fin_traslado=date(2026, 9, 18))['transporte']
        self.assertEqual(transporte['finEstimadoTranslado'], '2026-09-18')

    def test_el_local_de_salida_lleva_ciudad_y_numero_de_casa(self):
        # xmlgen los exige por separado: la dirección sola no le alcanza.
        salida = self._data()['transporte']['salida']
        self.assertTrue(salida['ciudad'])
        self.assertTrue(salida['numeroCasa'])
        self.assertTrue(salida['direccion'])

    def test_el_receptor_de_una_remision_lleva_direccion_y_domicilio_completo(self):
        # Declarar la calle activa el grupo entero: sin ciudad, distrito y
        # departamento el SIFEN rechaza.
        cliente = self._data()['cliente']
        self.assertTrue(cliente['direccion'])
        for campo in ('numeroCasa', 'ciudad', 'distrito', 'departamento'):
            self.assertTrue(cliente[campo], f'falta {campo} en el receptor')

    def test_si_el_receptor_no_tiene_direccion_se_usa_la_de_entrega(self):
        cliente = self._data()['cliente']
        self.assertEqual(cliente['direccion'], 'Avda. Mcal. Lopez 1234')

    def test_el_transportista_lleva_documento_y_direccion(self):
        transportista = self._data(
            transportista_nombre='Fletes del Este')['transporte']['transportista']
        self.assertTrue(transportista['direccion'])
        self.assertTrue(transportista.get('ruc')
                        or transportista.get('documentoNumero'))
        if not transportista.get('ruc'):
            self.assertIn('documentoTipo', transportista)

    def test_el_chofer_lleva_numero_de_documento_y_direccion(self):
        transportista = self._data(
            transportista_nombre='Fletes del Este',
            conductor_nombre='Juan Perez',
            conductor_documento='1234567')['transporte']['transportista']
        chofer = transportista['chofer']
        self.assertEqual(chofer['documentoNumero'], '1234567')
        self.assertTrue(chofer['direccion'])

    def test_las_direcciones_del_transporte_se_recortan_a_60(self):
        # El límite es de 4 a 60 caracteres y la dirección real del local
        # tiene 78: sin recortar, el documento vuelve rechazado por un campo
        # accesorio. Se descubrió así, con la dirección verdadera.
        largo = 'Calle muy larga que supera holgadamente el limite de sesenta caracteres del manual'
        self.assertGreater(len(largo), 60)
        transportista = self._data(
            transportista_nombre='Fletes del Este',
            transportista_direccion=largo,
            conductor_nombre='Juan Perez',
            conductor_documento='1234567')['transporte']['transportista']
        self.assertLessEqual(len(transportista['direccion']), 60)
        self.assertLessEqual(len(transportista['chofer']['direccion']), 60)

    def test_sin_traslado_el_error_habla_del_traslado_y_no_de_la_direccion(self):
        # El orden de los errores importa. `_cliente()` corre antes que el
        # bloque de la remisión, así que si no se tuviera cuidado el mensaje
        # sería "falta la dirección del receptor" — que es una consecuencia,
        # no la causa, y manda a buscar el problema al lugar equivocado.
        documento = self._documento_remision(None)
        with self.assertRaises(payload.DatosIncompletos) as caso:
            payload.construir_data(documento)
        self.assertIn('traslado', str(caso.exception).lower())
