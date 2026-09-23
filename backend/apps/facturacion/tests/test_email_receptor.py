"""
El correo del receptor (campo D216 `dEmailRec`).

Es por donde el SIFEN le manda el comprobante al cliente, así que deja de ser
un dato de contacto suelto: si está mal escrito, el documento vuelve
rechazado y la venta queda sin comprobante.

El Manual V150 solo dice "A 3-80, ocurrencia 0-1". Las reglas que de verdad
se aplican salen de leer la librería de referencia de la DNIT
(`jsonDeMainValidate.service.js` y `jsonDeMain.service.js` de
facturacionelectronicapy-xmlgen), y son las que se replican acá:

  · vacío se omite del XML — la librería hace `if (data['cliente']['email'])`,
    así que un string vacío ni se escribe; mandarlo violaría el mínimo de 3;
  · sin espacios;
  · de 3 a 80 caracteres;
  · formato de correo;
  · **si vienen varios separados por coma, solo viaja el primero**, porque el
    SIFEN no acepta comas en el campo.

Esa última es la que más conviene tener cubierta: la cajera escribe dos
correos creyendo que le llega a los dos, y el comprobante sale con uno.
"""
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.caja.models import Pago
from apps.facturacion import codigos, payload
from apps.facturacion.emisor import crear_documento
from apps.inventario.models import MovimientoStock, Stock
from apps.ventas.models import NotaPedido

from .factories import (DATOS_FISCALES_COMPLETOS, RUC_RECEPTOR, SIFEN_PRENDIDO,
                        crear_pago, crear_pedido, crear_sesion, crear_usuario,
                        crear_variante)


class ValidacionDelCorreoTests(TestCase):
    """Las reglas puras, sin base de datos."""

    def test_vacio_es_valido_y_devuelve_vacio(self):
        # El campo es opcional (0-1). Vacío no es un error.
        self.assertEqual(codigos.validar_email_receptor(''), '')
        self.assertEqual(codigos.validar_email_receptor(None), '')
        self.assertEqual(codigos.validar_email_receptor('   '), '')

    def test_un_correo_normal_pasa(self):
        self.assertEqual(
            codigos.validar_email_receptor('  cliente@correo.com  '),
            'cliente@correo.com')

    def test_de_varios_separados_por_coma_queda_el_primero(self):
        # El SIFEN no acepta comas: la librería manda solo el primero. Se
        # recorta acá para que lo guardado coincida con lo transmitido.
        self.assertEqual(
            codigos.validar_email_receptor('uno@correo.com, dos@correo.com'),
            'uno@correo.com')

    def test_rechaza_espacios(self):
        with self.assertRaises(ValueError):
            codigos.validar_email_receptor('cliente @correo.com')

    def test_rechaza_lo_que_no_es_un_correo(self):
        for malo in ('cliente', 'cliente@', '@correo.com', 'cliente@correo'):
            with self.assertRaises(ValueError, msg=malo):
                codigos.validar_email_receptor(malo)

    def test_rechaza_mas_de_80_caracteres(self):
        largo = 'a' * 75 + '@correo.com'   # 86
        self.assertGreater(len(largo), codigos.LARGO_MAX_EMAIL)
        with self.assertRaises(ValueError) as ctx:
            codigos.validar_email_receptor(largo)
        self.assertIn('80', str(ctx.exception))

    def test_acepta_justo_el_maximo(self):
        relleno = 'a' * (codigos.LARGO_MAX_EMAIL - len('@correo.com'))
        correo = f'{relleno}@correo.com'
        self.assertEqual(len(correo), codigos.LARGO_MAX_EMAIL)
        self.assertEqual(codigos.validar_email_receptor(correo), correo)


@override_settings(DATOS_FISCALES=DATOS_FISCALES_COMPLETOS, SIFEN=SIFEN_PRENDIDO)
class CorreoEnElCobroTests(TestCase):
    databases = {'default', 'sync'}

    def setUp(self):
        self.cajero = crear_usuario('cajera_mail', rol='cajero')
        self.sesion = crear_sesion(self.cajero)
        variante = crear_variante(nombre='Piso MAIL')
        stock = Stock.objects.get(variante=variante)
        stock.registrar_movimiento(
            MovimientoStock.TIPO_ENTRADA, Decimal('50'), self.cajero,
            observaciones='carga inicial')

        self.pedido = crear_pedido(self.cajero, [(variante, 1, 100000)])
        self.pedido.reservar_stock(usuario=self.cajero)
        self.pedido.estado = NotaPedido.ESTADO_LISTO
        self.pedido.save(update_fields=['estado'])

        self.api = APIClient()
        self.api.force_authenticate(self.cajero)

    def _cobrar(self, **extra):
        cuerpo = {
            'pedido_id': self.pedido.pk,
            'medio_pago': 'efectivo',
            'monto_recibido': 200000,
            'tipo_comprobante': 'factura',
            'cliente_ruc': RUC_RECEPTOR,
            'cliente_razon_social': 'Constructora Sur SRL',
        }
        cuerpo.update(extra)
        return self.api.post(reverse('registrar-pago'), cuerpo, format='json')

    def test_el_correo_queda_guardado_en_el_pago(self):
        respuesta = self._cobrar(cliente_email='cliente@correo.com')
        self.assertEqual(respuesta.status_code, 201)
        pago = Pago.objects.get(pedido=self.pedido)
        self.assertEqual(pago.cliente_email, 'cliente@correo.com')

    def test_el_correo_llega_al_documento_electronico(self):
        # Lo que importa de verdad: que viaje al DE, que es lo que se
        # transmite. Guardarlo en el Pago y que no llegue acá no serviría.
        self._cobrar(cliente_email='cliente@correo.com')
        pago = Pago.objects.get(pedido=self.pedido)
        documento = pago.documento_electronico
        self.assertIsNotNone(documento)
        self.assertEqual(documento.receptor_email, 'cliente@correo.com')

    def test_un_correo_mal_escrito_frena_el_cobro(self):
        # Con el cliente todavía en el mostrador, que es cuando se puede
        # preguntar. Y sin dejar el pago a medias.
        respuesta = self._cobrar(cliente_email='cliente arroba correo')
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(Pago.objects.filter(pedido=self.pedido).exists())
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, NotaPedido.ESTADO_LISTO)

    def test_sin_correo_el_cobro_sigue_funcionando(self):
        # El campo es opcional: no se le puede agregar un requisito a la
        # cajera por algo que el SIFEN no exige.
        respuesta = self._cobrar()
        self.assertEqual(respuesta.status_code, 201)
        pago = Pago.objects.get(pedido=self.pedido)
        self.assertEqual(pago.cliente_email, '')

    def test_un_ticket_no_guarda_correo(self):
        respuesta = self._cobrar(tipo_comprobante='ticket',
                                 cliente_email='cliente@correo.com')
        self.assertEqual(respuesta.status_code, 201)
        pago = Pago.objects.get(pedido=self.pedido)
        self.assertEqual(pago.cliente_email, '')

    def test_el_correo_se_guarda_en_el_padron(self):
        from apps.ventas.models import Cliente
        self._cobrar(cliente_email='cliente@correo.com', guardar_cliente=True)
        cliente = Cliente.objects.filter(ruc=RUC_RECEPTOR).first()
        self.assertIsNotNone(cliente)
        self.assertEqual(cliente.email, 'cliente@correo.com')

    def test_el_payload_del_sifen_lo_lleva(self):
        self._cobrar(cliente_email='cliente@correo.com')
        documento = Pago.objects.get(pedido=self.pedido).documento_electronico
        datos = payload.construir_data(documento)
        self.assertEqual(datos['cliente']['email'], 'cliente@correo.com')

    def test_sin_correo_el_payload_manda_vacio_y_la_libreria_lo_omite(self):
        # La librería hace `if (data['cliente']['email'])`, así que un vacío
        # no escribe el campo. Mandar '' es seguro; mandar un `dEmailRec`
        # vacío violaría el mínimo de 3 del Manual.
        self._cobrar()
        documento = Pago.objects.get(pedido=self.pedido).documento_electronico
        datos = payload.construir_data(documento)
        self.assertEqual(datos['cliente']['email'], '')
