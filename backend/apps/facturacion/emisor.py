"""
Emisión de documentos electrónicos a partir de un cobro.

Este es el punto donde el flujo de caja que ya existe se cruza con el SIFEN.
La regla de oro: **emitir nunca puede hacer fallar un cobro**. Si algo acá
sale mal, la venta ya ocurrió, el stock ya se descontó y el cliente está en
el mostrador. Se registra el problema y se sigue; el DE se resuelve después.

Por eso emitir_para_pago() no lanza: devuelve el DE o None.
"""
import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import cdc as cdc_mod
from . import codigos
from .models import DocumentoElectronico, SecuenciaComprobante

logger = logging.getLogger(__name__)


class DatosFiscalesIncompletos(RuntimeError):
    """Falta configuración en el .env para poder emitir."""


def sifen_activo() -> bool:
    """
    True si el sistema debe emitir documentos electrónicos.

    Mientras sea False, caja funciona exactamente como hasta ahora: ticket y
    factura impresa, sin CDC y sin salir a internet. Es el interruptor que
    permite tener todo este código en producción sin que cambie nada hasta
    que estén el certificado y la habilitación.
    """
    return bool(getattr(settings, 'SIFEN', {}).get('habilitado'))


def _fiscal():
    return getattr(settings, 'DATOS_FISCALES', {})


def validar_configuracion():
    """
    Verifica que estén los datos mínimos para armar un DE.

    Se llama antes de emitir. El comando `manage.py verificar_fiscal` hace
    el mismo chequeo pero con salida legible para el día del lanzamiento.
    """
    fiscal = _fiscal()
    faltantes = [
        env for clave, env in [
            ('ruc', 'FISCAL_RUC'),
            ('razon_social', 'FISCAL_RAZON_SOCIAL'),
            ('timbrado', 'FISCAL_TIMBRADO'),
            ('establecimiento', 'FISCAL_ESTABLECIMIENTO'),
            ('punto_expedicion', 'FISCAL_PUNTO_EXPEDICION'),
        ] if not str(fiscal.get(clave) or '').strip()
    ]
    if faltantes:
        raise DatosFiscalesIncompletos(
            'Faltan datos fiscales en el .env: ' + ', '.join(faltantes) +
            '. Correr: python manage.py verificar_fiscal')


def calcular_totales_iva(pedido, total_cobrado):
    """
    Desglosa el total cobrado en base gravada e IVA, por tasa.

    El SIFEN pide el desglose por tasa, no un IVA global. Se recorre ítem
    por ítem usando Producto.tasa_iva y se prorratea el descuento: si en
    caja se cobró menos que la suma de los ítems (descuento porcentual o
    precio negociado), la diferencia se reparte proporcionalmente para que
    la suma de las bases dé exactamente el total cobrado.
    """
    total_cobrado = Decimal(str(total_cobrado))
    items = list(pedido.items.select_related('variante__producto').all())

    suma_items = sum((Decimal(str(i.subtotal)) for i in items), Decimal('0'))
    # Si no hay ítems o suman cero no hay nada que prorratear; se manda todo
    # al 10%, que es la tasa del rubro.
    factor = (total_cobrado / suma_items) if suma_items > 0 else Decimal('1')

    acumulado = {codigos.TASA_10: Decimal('0'),
                 codigos.TASA_5: Decimal('0'),
                 codigos.TASA_0: Decimal('0')}

    for item in items:
        tasa = getattr(item.variante.producto, 'tasa_iva', codigos.TASA_10)
        if tasa not in codigos.TASAS_VALIDAS:
            tasa = codigos.TASA_10
        acumulado[tasa] += Decimal(str(item.subtotal)) * factor

    if not items:
        acumulado[codigos.TASA_10] = total_cobrado

    base_10, iva_10 = codigos.desglosar_iva(acumulado[codigos.TASA_10], codigos.TASA_10)
    base_5, iva_5 = codigos.desglosar_iva(acumulado[codigos.TASA_5], codigos.TASA_5)
    exento, _ = codigos.desglosar_iva(acumulado[codigos.TASA_0], codigos.TASA_0)

    # Cuadre final. Cada tasa se redondea a guaraníes por separado, así que la
    # suma del desglose puede quedar 1 Gs por encima o por debajo del total
    # cobrado (pasa en ~6% de los casos con descuento prorrateado). El SIFEN
    # valida que el desglose sume EXACTAMENTE el total, y un peso de
    # diferencia alcanza para que rechace el documento.
    #
    # La diferencia se absorbe en la base gravada más grande, que es la que
    # menos se distorsiona en términos relativos. No se toca el IVA: ese
    # número tiene que seguir siendo la tasa aplicada sobre su base.
    suma = base_10 + iva_10 + base_5 + iva_5 + exento
    diferencia = Decimal(str(total_cobrado)).quantize(Decimal('1')) - suma
    if diferencia:
        mayor = max(
            (base_10, 'base_10'), (base_5, 'base_5'), (exento, 'exento'),
            key=lambda par: par[0])[1]
        if mayor == 'base_10':
            base_10 += diferencia
        elif mayor == 'base_5':
            base_5 += diferencia
        else:
            exento += diferencia

    return {
        'total_gravado_10': base_10,
        'iva_10': iva_10,
        'total_gravado_5': base_5,
        'iva_5': iva_5,
        'total_exento': exento,
    }


@transaction.atomic
def crear_documento(pago, *, receptor: dict, condicion_venta='contado'):
    """
    Crea el DocumentoElectronico de un pago ya confirmado.

    Corre dentro de una transacción junto con la toma del número: si algo
    falla, el correlativo vuelve atrás y no queda un salto que después haya
    que justificar ante la DNIT.

    No transmite nada. El DE queda en estado 'pendiente' y lo levanta el
    worker de la cola cuando haya internet.
    """
    validar_configuracion()
    fiscal = _fiscal()

    numero, numero_completo = SecuenciaComprobante.siguiente(
        codigos.TIPO_DE_FACTURA,
        fiscal['establecimiento'],
        fiscal['punto_expedicion'],
    )

    ahora = timezone.now()
    codigo_seguridad = cdc_mod.generar_codigo_seguridad()
    cdc = cdc_mod.generar(
        ruc_emisor=fiscal['ruc'],
        establecimiento=fiscal['establecimiento'],
        punto_expedicion=fiscal['punto_expedicion'],
        numero=numero,
        tipo_contribuyente=fiscal.get('tipo_contribuyente', 2),
        fecha_emision=ahora.date(),
        tipo_documento=codigos.TIPO_DE_FACTURA,
        codigo_seguridad=codigo_seguridad,
    )

    receptor_ruc = (receptor.get('ruc') or '').strip()
    totales = calcular_totales_iva(pago.pedido, pago.monto)

    return DocumentoElectronico.objects.create(
        pago=pago,
        cdc=cdc,
        tipo_documento=codigos.TIPO_DE_FACTURA,
        establecimiento=f"{int(fiscal['establecimiento']):03d}",
        punto_expedicion=f"{int(fiscal['punto_expedicion']):03d}",
        numero=numero,
        numero_completo=numero_completo,
        codigo_seguridad=codigo_seguridad,
        fecha_emision=ahora,

        emisor_ruc=fiscal.get('ruc', ''),
        emisor_razon_social=fiscal.get('razon_social', ''),
        emisor_direccion=fiscal.get('direccion', ''),
        emisor_telefono=fiscal.get('telefono', ''),
        emisor_timbrado=fiscal.get('timbrado', ''),
        emisor_timbrado_vto=fiscal.get('timbrado_vto', ''),

        receptor_ruc=receptor_ruc,
        receptor_razon_social=receptor.get('razon_social') or 'Consumidor Final',
        receptor_direccion=receptor.get('direccion', ''),
        receptor_telefono=receptor.get('telefono', ''),
        receptor_email=receptor.get('email', ''),
        receptor_naturaleza=codigos.naturaleza_receptor(receptor_ruc),

        condicion_venta=codigos.codigo_condicion_venta(condicion_venta),
        medio_pago=codigos.codigo_medio_pago(pago.medio_pago),
        total=pago.monto,
        **totales,

        creado_por=pago.cajero,
    )


def emitir_para_pago(pago, *, receptor: dict, condicion_venta='contado'):
    """
    Punto de entrada desde caja. Devuelve el DE creado, o None.

    Nunca lanza: un problema de facturación electrónica no puede tumbar un
    cobro que ya se hizo. Si devuelve None, la venta siguió su curso normal
    y queda registrado en el log qué pasó.
    """
    if not sifen_activo():
        return None
    try:
        documento = crear_documento(
            pago, receptor=receptor, condicion_venta=condicion_venta)
        logger.info('DE %s creado para el pago %s (CDC %s)',
                    documento.numero_completo, pago.pk, documento.cdc)
        return documento
    except Exception:
        logger.exception(
            'No se pudo emitir el documento electrónico del pago %s. '
            'El cobro se completó igual; el DE queda pendiente de resolver.',
            pago.pk)
        return None
