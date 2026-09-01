"""
Tests de la numeración de comprobantes.

Lo que se prueba acá son las tres reglas que impone la DNIT y que el sistema
no cumplía antes (numeraba con `T-<timestamp>-<pedido_id>`):

  · formato fijo EEE-PPP-NNNNNNN
  · correlativo sin saltos
  · sin duplicados, ni con dos cajas cobrando en el mismo segundo

Un salto o un duplicado hay que justificarlo ante la DNIT, así que estas
garantías son de las pocas del sistema que valen una prueba de concurrencia
de verdad.
"""
import threading

from django.db import connection, transaction
from django.test import SimpleTestCase, TransactionTestCase, skipUnlessDBFeature

from apps.facturacion import numeracion
from apps.facturacion.models import SecuenciaComprobante
from apps.facturacion.numeracion import NumeracionInvalida

TIPO_FACTURA = 1


class FormatoTests(SimpleTestCase):

    def test_rellena_con_ceros(self):
        self.assertEqual(numeracion.formatear(1, 1, 1), '001-001-0000001')
        self.assertEqual(numeracion.formatear('7', '3', 123456), '007-003-0123456')

    def test_acepta_el_maximo(self):
        self.assertEqual(numeracion.formatear(999, 999, numeracion.NUMERO_MAXIMO),
                         '999-999-9999999')

    def test_rechaza_fuera_de_rango(self):
        for numero in (0, -1, numeracion.NUMERO_MAXIMO + 1):
            with self.subTest(numero=numero):
                with self.assertRaises(NumeracionInvalida):
                    numeracion.formatear(1, 1, numero)

    def test_ida_y_vuelta(self):
        for est, punto, num in [(1, 1, 1), (7, 3, 123456), (999, 999, 9999999)]:
            with self.subTest(est=est, punto=punto, num=num):
                texto = numeracion.formatear(est, punto, num)
                self.assertEqual(numeracion.descomponer(texto),
                                 (f'{est:03d}', f'{punto:03d}', num))

    def test_el_formato_viejo_no_es_valido(self):
        # Es el número que el sistema usaba antes. Tiene que quedar claro que
        # no sirve como comprobante.
        self.assertFalse(numeracion.es_valido('T-20260823210357-14'))

    def test_rechaza_formatos_parecidos_pero_mal(self):
        for malo in ('1-1-1', '001-001-000001', '001-001-00000001',
                     '0011-001-0000001', '001_001_0000001', '', None):
            with self.subTest(malo=malo):
                self.assertFalse(numeracion.es_valido(malo))
                with self.assertRaises(NumeracionInvalida):
                    numeracion.descomponer(malo)


class SecuenciaTests(TransactionTestCase):
    """
    TransactionTestCase y no TestCase: estos tests necesitan transacciones
    reales (select_for_update, rollback), no el rollback automático que
    TestCase envuelve alrededor de cada test.
    """
    # El catálogo dispara el registro de cambios del sync, que vive en su
    # propia base (ver apps/sync/routers.py). Sin declararla, Django la
    # bloquea y el signal falla en silencio.
    databases = {'default', 'sync'}

    reset_sequences = True

    def test_arranca_en_uno_y_avanza_de_a_uno(self):
        obtenidos = [SecuenciaComprobante.siguiente(TIPO_FACTURA, '001', '001')[1]
                     for _ in range(5)]
        self.assertEqual(obtenidos, [
            '001-001-0000001', '001-001-0000002', '001-001-0000003',
            '001-001-0000004', '001-001-0000005',
        ])

    def test_cada_punto_de_expedicion_lleva_su_propia_cuenta(self):
        SecuenciaComprobante.siguiente(TIPO_FACTURA, '001', '001')
        SecuenciaComprobante.siguiente(TIPO_FACTURA, '001', '001')
        _, primero_del_otro = SecuenciaComprobante.siguiente(TIPO_FACTURA, '001', '002')
        self.assertEqual(primero_del_otro, '001-002-0000001')

    def test_un_rollback_no_deja_hueco(self):
        # Si el cobro falla después de tomar el número, ese número tiene que
        # volver a estar disponible: un salto hay que justificarlo ante la DNIT.
        SecuenciaComprobante.siguiente(TIPO_FACTURA, '001', '001')
        antes = SecuenciaComprobante.objects.get(punto_expedicion='001').ultimo_numero

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                SecuenciaComprobante.siguiente(TIPO_FACTURA, '001', '001')
                raise RuntimeError('simula que el cobro falla')

        despues = SecuenciaComprobante.objects.get(punto_expedicion='001').ultimo_numero
        self.assertEqual(antes, despues)
        _, siguiente = SecuenciaComprobante.siguiente(TIPO_FACTURA, '001', '001')
        self.assertEqual(siguiente, '001-001-0000002')

    def test_avisa_antes_de_agotar_el_rango_autorizado(self):
        SecuenciaComprobante.objects.create(
            tipo_documento=TIPO_FACTURA, establecimiento='001',
            punto_expedicion='005', numero_desde=1, numero_hasta=2)
        SecuenciaComprobante.siguiente(TIPO_FACTURA, '001', '005')
        SecuenciaComprobante.siguiente(TIPO_FACTURA, '001', '005')
        with self.assertRaises(ValueError) as ctx:
            SecuenciaComprobante.siguiente(TIPO_FACTURA, '001', '005')
        self.assertIn('timbrado', str(ctx.exception).lower())

    def test_respeta_numero_desde(self):
        # Un timbrado puede autorizar desde un número que no sea el 1.
        SecuenciaComprobante.objects.create(
            tipo_documento=TIPO_FACTURA, establecimiento='001',
            punto_expedicion='006', numero_desde=500, numero_hasta=999)
        _, primero = SecuenciaComprobante.siguiente(TIPO_FACTURA, '001', '006')
        self.assertEqual(primero, '001-006-0000500')

    def test_una_secuencia_desactivada_no_entrega_numeros(self):
        SecuenciaComprobante.objects.create(
            tipo_documento=TIPO_FACTURA, establecimiento='001',
            punto_expedicion='007', activa=False)
        with self.assertRaises(ValueError):
            SecuenciaComprobante.siguiente(TIPO_FACTURA, '001', '007')

    def test_numeros_restantes(self):
        secuencia = SecuenciaComprobante.objects.create(
            tipo_documento=TIPO_FACTURA, establecimiento='001',
            punto_expedicion='008', numero_hasta=10)
        self.assertEqual(secuencia.numeros_restantes, 10)
        SecuenciaComprobante.siguiente(TIPO_FACTURA, '001', '008')
        secuencia.refresh_from_db()
        self.assertEqual(secuencia.numeros_restantes, 9)


@skipUnlessDBFeature('has_select_for_update')
class ConcurrenciaTests(TransactionTestCase):
    """
    La garantía que la DNIT no perdona: dos cajas cobrando a la vez no pueden
    sacar el mismo número de factura.

    Solo corre contra PostgreSQL, que es lo que usa el negocio. Con SQLite
    (`--settings=config.settings_test`, la corrida sin Postgres) se saltea:
    SQLite no tiene bloqueo por fila, bloquea la tabla entera y el test moría
    con "database table is locked" — un falso positivo que hacía que
    `probar.bat` avisara de una falla inexistente.
    """
    # El catálogo dispara el registro de cambios del sync, que vive en su
    # propia base (ver apps/sync/routers.py). Sin declararla, Django la
    # bloquea y el signal falla en silencio.
    databases = {'default', 'sync'}

    reset_sequences = True

    def test_varias_cajas_simultaneas_no_duplican_ni_saltan(self):
        N_CAJAS, POR_CAJA = 6, 12
        obtenidos, errores = [], []
        lock = threading.Lock()

        def cobrar():
            try:
                for _ in range(POR_CAJA):
                    with transaction.atomic():
                        _, texto = SecuenciaComprobante.siguiente(
                            TIPO_FACTURA, '001', '001')
                    with lock:
                        obtenidos.append(texto)
            except Exception as e:          # pragma: no cover - solo si falla
                with lock:
                    errores.append(repr(e))
            finally:
                # Cada hilo abre su propia conexión; si no se cierra, el
                # runner no puede destruir la base de test al terminar.
                connection.close()

        hilos = [threading.Thread(target=cobrar) for _ in range(N_CAJAS)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        self.assertEqual(errores, [], f'Hubo errores en los hilos: {errores}')
        self.assertEqual(len(obtenidos), N_CAJAS * POR_CAJA)
        self.assertEqual(len(set(obtenidos)), len(obtenidos),
                         'Se entregaron números de factura duplicados')

        numeros = sorted(int(t.split('-')[-1]) for t in obtenidos)
        self.assertEqual(numeros, list(range(1, len(numeros) + 1)),
                         'El correlativo quedó con huecos')
