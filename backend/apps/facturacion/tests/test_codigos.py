"""
Tests de las tablas de códigos y del desglose de IVA.

El desglose es lo más delicado de acá: el SIFEN valida que la suma de bases
e impuestos dé EXACTAMENTE el total declarado, y en guaraníes (sin
centavos) los redondeos se notan.
"""
from decimal import Decimal

from django.test import SimpleTestCase

from apps.facturacion import codigos

from .factories import RUC_RECEPTOR as RUC_VALIDO


class TraduccionDeCodigosTests(SimpleTestCase):

    def test_cubre_todos_los_medios_de_pago_del_sistema(self):
        # Si alguien agrega un medio de pago a Pago.MEDIOS y se olvida de
        # mapearlo acá, el DE saldría declarando "efectivo" por default.
        from apps.caja.models import Pago
        for valor, _etiqueta in Pago.MEDIOS:
            with self.subTest(medio=valor):
                self.assertIn(
                    valor, codigos.MEDIO_PAGO,
                    f'El medio de pago {valor!r} existe en Pago.MEDIOS pero no '
                    f'está mapeado en codigos.MEDIO_PAGO')

    def test_medios_de_pago_conocidos(self):
        self.assertEqual(codigos.codigo_medio_pago('efectivo'), 1)
        self.assertEqual(codigos.codigo_medio_pago('cheque'), 2)
        self.assertEqual(codigos.codigo_medio_pago('credito'), 3)
        self.assertEqual(codigos.codigo_medio_pago('debito'), 4)
        self.assertEqual(codigos.codigo_medio_pago('transferencia'), 5)

    def test_medio_desconocido_cae_en_efectivo(self):
        # 'giro' y 'vale' existen en la tabla E607 del manual, pero el
        # sistema no los cobra: no están en Pago.MEDIOS ni mapeados acá.
        for entrada in ('', None, 'giro', 'vale', '  '):
            with self.subTest(entrada=entrada):
                self.assertEqual(codigos.codigo_medio_pago(entrada),
                                 codigos.PAGO_EFECTIVO)

    def test_condicion_de_venta_tolera_mayusculas_y_tilde(self):
        # La caja manda 'Contado'/'Crédito' como texto de pantalla.
        self.assertEqual(codigos.codigo_condicion_venta('Contado'), 1)
        self.assertEqual(codigos.codigo_condicion_venta('contado'), 1)
        self.assertEqual(codigos.codigo_condicion_venta('Crédito'), 2)
        self.assertEqual(codigos.codigo_condicion_venta('credito'), 2)

    def test_condicion_desconocida_cae_en_contado(self):
        self.assertEqual(codigos.codigo_condicion_venta('vaya a saber'), 1)

    def test_naturaleza_del_receptor_depende_del_ruc_no_del_tipo(self):
        # Una persona física puede tener RUC, y una venta de mostrador puede
        # no identificar a nadie.
        self.assertEqual(codigos.naturaleza_receptor(RUC_VALIDO),
                         codigos.RECEPTOR_CONTRIBUYENTE)
        for sin_ruc in ('', '   ', None):
            with self.subTest(ruc=sin_ruc):
                self.assertEqual(codigos.naturaleza_receptor(sin_ruc),
                                 codigos.RECEPTOR_NO_CONTRIBUYENTE)

    def test_una_cedula_no_convierte_al_cliente_en_contribuyente(self):
        """
        La pantalla de caja pide "RUC/CI" y acepta las dos cosas.

        Hasta el 14/09/2026 bastaba con que el campo no viniera vacío para
        declarar al cliente como contribuyente y mandar el número como
        `dRucRec`. El SIFEN valida el dígito verificador de ese campo: cada
        factura a un consumidor identificado con cédula habría vuelto
        rechazada.

        El criterio ahora es el DV. En Paraguay el RUC de una persona física
        es su cédula MÁS el dígito verificador, así que el módulo 11 separa
        los dos casos.
        """
        cedula = '4123456'
        self.assertFalse(codigos.es_ruc(cedula))
        self.assertEqual(codigos.naturaleza_receptor(cedula),
                         codigos.RECEPTOR_NO_CONTRIBUYENTE)

    def test_un_ruc_con_el_dv_mal_no_pasa_como_ruc(self):
        # Un error de tipeo en el mostrador tiene que salir acá, no como
        # rechazo del SIFEN.
        base = RUC_VALIDO.split('-')[0]
        dv_correcto = int(RUC_VALIDO.split('-')[1])
        dv_malo = (dv_correcto + 1) % 10
        self.assertFalse(codigos.es_ruc(f'{base}-{dv_malo}'))

    def test_tipo_de_operacion_acompana_a_la_naturaleza(self):
        self.assertEqual(codigos.tipo_operacion(RUC_VALIDO), codigos.OPERACION_B2B)
        self.assertEqual(codigos.tipo_operacion(''), codigos.OPERACION_B2C)
        self.assertEqual(codigos.tipo_operacion('4123456'), codigos.OPERACION_B2C)


class ContraElManualTecnicoTests(SimpleTestCase):
    """
    Las tablas del Manual Técnico V150, transcritas a mano acá.

    Es deliberadamente redundante con codigos.py: el punto es que si alguien
    "corrige" un código de memoria, el test lo frene. Cuando la DNIT publique
    una revisión, se actualizan los dos lados a la vez y el diff muestra
    exactamente qué se movió.

    Contrastado el 14/09/2026 contra el PDF que está en
    docs/Documentacion para Facturación Electrónica/.
    """

    # Campo C002 (iTiDE), sección 10.4 del manual.
    def test_tipos_de_documento_electronico(self):
        self.assertEqual(codigos.TIPO_DE_FACTURA, 1)
        self.assertEqual(codigos.TIPO_DE_AUTOFACTURA, 4)
        self.assertEqual(codigos.TIPO_DE_NOTA_CREDITO, 5)
        self.assertEqual(codigos.TIPO_DE_NOTA_DEBITO, 6)
        self.assertEqual(codigos.TIPO_DE_NOTA_REMISION, 7)

    def test_cada_tipo_de_documento_tiene_su_descripcion(self):
        # C003 (dDesTiDE) es obligatorio y el SIFEN valida que el texto
        # corresponda al código de C002.
        for codigo in (codigos.TIPO_DE_FACTURA, codigos.TIPO_DE_AUTOFACTURA,
                       codigos.TIPO_DE_NOTA_CREDITO, codigos.TIPO_DE_NOTA_DEBITO,
                       codigos.TIPO_DE_NOTA_REMISION):
            with self.subTest(tipo=codigo):
                self.assertIn(codigo, codigos.DESCRIPCION_TIPO_DE)

    # Campo B002 (iTipEmi).
    def test_tipo_de_emision(self):
        self.assertEqual(codigos.EMISION_NORMAL, 1)
        self.assertEqual(codigos.EMISION_CONTINGENCIA, 2)

    # Campo D011 (iTipTra) y D013 (iTImp).
    def test_transaccion_e_impuesto(self):
        self.assertEqual(codigos.TRANSACCION_VENTA_MERCADERIA, 1)
        self.assertEqual(codigos.IMPUESTO_IVA, 1)

    # Campo E601 (iCondOpe).
    def test_condicion_de_la_operacion(self):
        self.assertEqual(codigos.CONDICION_CONTADO, 1)
        self.assertEqual(codigos.CONDICION_CREDITO, 2)

    # Campo E606 (iTiPago).
    def test_tipos_de_pago(self):
        self.assertEqual(codigos.PAGO_EFECTIVO, 1)
        self.assertEqual(codigos.PAGO_TARJETA_CREDITO, 3)
        self.assertEqual(codigos.PAGO_TARJETA_DEBITO, 4)
        self.assertEqual(codigos.PAGO_TRANSFERENCIA, 5)

    # Campo D201 (iNatRec) y D202 (iTiOpe).
    def test_naturaleza_y_tipo_de_operacion(self):
        self.assertEqual(codigos.RECEPTOR_CONTRIBUYENTE, 1)
        self.assertEqual(codigos.RECEPTOR_NO_CONTRIBUYENTE, 2)
        self.assertEqual(codigos.OPERACION_B2B, 1)
        self.assertEqual(codigos.OPERACION_B2C, 2)
        self.assertEqual(codigos.OPERACION_B2G, 3)

    # Campo D205 (iTiContRec).
    def test_tipo_de_contribuyente_receptor(self):
        self.assertEqual(codigos.RECEPTOR_PERSONA_FISICA, 1)
        self.assertEqual(codigos.RECEPTOR_PERSONA_JURIDICA, 2)

    # Campo D208 (iTipIDRec). El pasaporte estuvo en 3 —que es la cédula
    # extranjera— hasta el 14/09/2026.
    def test_documentos_de_identidad_del_receptor(self):
        self.assertEqual(codigos.IDENTIDAD_CEDULA_PY, 1)
        self.assertEqual(codigos.IDENTIDAD_PASAPORTE, 2)
        self.assertEqual(codigos.IDENTIDAD_CEDULA_EXTRANJERA, 3)
        self.assertEqual(codigos.IDENTIDAD_CARNET_RESIDENCIA, 4)
        self.assertEqual(codigos.IDENTIDAD_INNOMINADO, 5)
        self.assertEqual(codigos.IDENTIDAD_TARJETA_DIPLOMATICA, 6)
        self.assertEqual(codigos.IDENTIDAD_OTRO, 9)

    # Tabla 6 de las Codificaciones (sección 15), campo E731 (iAfecIVA).
    def test_codigos_de_afectacion_del_iva(self):
        self.assertEqual(codigos.IVA_GRAVADO, 1)
        self.assertEqual(codigos.IVA_EXONERADO, 2)
        self.assertEqual(codigos.IVA_EXENTO, 3)
        self.assertEqual(codigos.IVA_GRAVADO_PARCIAL, 4)


class DesglosarIvaTests(SimpleTestCase):
    """En Paraguay el precio ya viene con IVA: el desglose es hacia atrás."""

    def test_casos_exactos(self):
        self.assertEqual(codigos.desglosar_iva(1_100_000, 10),
                         (Decimal('1000000'), Decimal('100000')))
        self.assertEqual(codigos.desglosar_iva(1_050_000, 5),
                         (Decimal('1000000'), Decimal('50000')))

    def test_exento_no_genera_impuesto(self):
        base, iva = codigos.desglosar_iva(500_000, 0)
        self.assertEqual(base, Decimal('500000'))
        self.assertEqual(iva, Decimal('0'))

    def test_base_mas_iva_siempre_devuelve_el_total(self):
        # La propiedad que importa: no se puede perder ni inventar un guaraní.
        for monto in range(1, 5000, 7):
            for tasa in codigos.TASAS_VALIDAS:
                with self.subTest(monto=monto, tasa=tasa):
                    base, iva = codigos.desglosar_iva(monto, tasa)
                    self.assertEqual(base + iva, Decimal(monto))

    def test_devuelve_guaranies_enteros(self):
        # El guaraní no tiene centavos; un decimal en el DE es un rechazo.
        for monto in ('333333.33', '1', '999999.99'):
            for tasa in codigos.TASAS_VALIDAS:
                with self.subTest(monto=monto, tasa=tasa):
                    base, iva = codigos.desglosar_iva(monto, tasa)
                    self.assertEqual(base, base.to_integral_value())
                    self.assertEqual(iva, iva.to_integral_value())

    def test_rechaza_tasas_que_el_sifen_no_conoce(self):
        for tasa in (7, 21, -1, 100):
            with self.subTest(tasa=tasa):
                with self.assertRaises(ValueError):
                    codigos.desglosar_iva(100_000, tasa)

    def test_monto_cero(self):
        for tasa in codigos.TASAS_VALIDAS:
            with self.subTest(tasa=tasa):
                self.assertEqual(codigos.desglosar_iva(0, tasa),
                                 (Decimal('0'), Decimal('0')))
