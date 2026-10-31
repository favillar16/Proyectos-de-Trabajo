"""
Lo que descuenta el banco de cada cobro con tarjeta, QR o PIX.

La propietaria lo encontró al conciliar la liquidación del banco: un cobro
por QR crédito de Gs. 2.778.000 se acreditó como 2.633.291. La diferencia no
es solo la comisión:

    comisión            3 % del cobro                 83.340
    IVA s/comisión      10 % de la comisión            8.334
    retención renta     1 % del cobro                 27.780
    retención IVA       10 % del IVA del cobro (1/110) 25.255
    neto acreditado                                 2.633.291

Las tasas por medio viven en `ComisionBancaria`, con su fecha de vigencia
(ver el modelo). Este módulo hace la cuenta.

Dos decisiones del usuario (30/10/2026) que conviene no deshacer:

  · **Solo comisión + IVA de la comisión es un costo.** Las retenciones son
    impuesto adelantado: el banco lo paga a la DNIT a nombre del local, que
    lo descuenta después en su liquidación de IVA y renta. Achican lo que se
    acredita, pero no la ganancia. Por eso `ganancias.py` resta `costo` y los
    reportes muestran las retenciones aparte.
  · **Las retenciones van en todos los medios bancarios**, PIX incluido.

Cada importe se redondea a guaraníes por separado, como la liquidación del
banco (25.254,5 → 25.255).

Lo que no hace: una devolución no devuelve la comisión (el banco no la
reintegra), y un cambio paga comisión solo por la diferencia cobrada, que es
el monto de su `Pago`.
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

CIEN = Decimal('100')
IVA = Decimal('10')             # IVA de la comisión, en %
# El IVA que trae un cobro con IVA incluido al 10 %: cobro / 11.
DIVISOR_IVA_INCLUIDO = Decimal('11')


def _gs(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal('1'), rounding=ROUND_HALF_UP)


@dataclass
class Desglose:
    cobrado: Decimal
    comision: Decimal = Decimal('0')
    iva_comision: Decimal = Decimal('0')
    retencion_renta: Decimal = Decimal('0')
    retencion_iva: Decimal = Decimal('0')

    @property
    def costo(self) -> Decimal:
        """Lo que el local pierde de verdad: comisión con su IVA."""
        return self.comision + self.iva_comision

    @property
    def retenciones(self) -> Decimal:
        return self.retencion_renta + self.retencion_iva

    @property
    def descuento(self) -> Decimal:
        return self.costo + self.retenciones

    @property
    def neto(self) -> Decimal:
        """Lo que el banco acredita en la cuenta."""
        return self.cobrado - self.descuento

    def __add__(self, otro):
        return Desglose(
            cobrado=self.cobrado + otro.cobrado,
            comision=self.comision + otro.comision,
            iva_comision=self.iva_comision + otro.iva_comision,
            retencion_renta=self.retencion_renta + otro.retencion_renta,
            retencion_iva=self.retencion_iva + otro.retencion_iva,
        )


def calcular(monto, tasa) -> Desglose:
    """El desglose de un cobro de `monto` con la `ComisionBancaria` dada."""
    monto = Decimal(str(monto))
    if tasa is None or not monto:
        return Desglose(cobrado=monto)
    bruta = monto * tasa.porcentaje / CIEN
    if tasa.iva_aparte:
        comision = _gs(bruta)
        iva = _gs(comision * IVA / CIEN)
    else:
        # "1,3 %" con el IVA adentro: lo que se descuenta es 1,3 % en total;
        # se separa el IVA que trae, como lo muestra el banco.
        total = _gs(bruta)
        iva = _gs(total / DIVISOR_IVA_INCLUIDO)
        comision = total - iva
    return Desglose(
        cobrado=monto,
        comision=comision,
        iva_comision=iva,
        retencion_renta=_gs(monto * tasa.retencion_renta / CIEN),
        retencion_iva=_gs(monto / DIVISOR_IVA_INCLUIDO * tasa.retencion_iva / CIEN),
    )


class Tasas:
    """
    Las tasas vigentes en cada fecha, leídas una sola vez.

    Un reporte de un mes calcula cientos de cobros: se trae la tabla entera
    (son unas pocas filas) y se busca en memoria.
    """

    def __init__(self):
        from .models import ComisionBancaria
        self._por_medio = {}
        for t in ComisionBancaria.objects.order_by('vigente_desde'):
            self._por_medio.setdefault(t.medio, []).append(t)

    def vigente(self, medio, dia):
        """La tasa de `medio` que regía el `dia`, o None si no tiene."""
        vigente = None
        for t in self._por_medio.get(medio, []):
            if t.vigente_desde > dia:
                break
            vigente = t
        return vigente

    @property
    def medios(self):
        return list(self._por_medio)


@dataclass
class LineaComision:
    linea: object          # PagoMedio
    fecha: object          # datetime del cobro
    desglose: Desglose
    tasa: object = None


def lineas(desde, hasta, pagos=None):
    """
    Cada línea de cobro con un medio que tiene tasa, del período (o de los
    `pagos` dados), con su desglose. Las líneas en 0 —un cambio sin
    diferencia— no pasan por el banco y no se listan.
    """
    from django.utils import timezone
    from .models import Pago, PagoMedio

    tasas = Tasas()
    qs = PagoMedio.objects.filter(
        pago__estado=Pago.ESTADO_CONFIRMADO, medio__in=tasas.medios, monto__gt=0)
    if pagos is not None:
        qs = qs.filter(pago__in=pagos)
    else:
        qs = qs.filter(pago__fecha__date__gte=desde, pago__fecha__date__lte=hasta)
    for linea in qs.select_related('pago__pedido').order_by('pago__fecha', 'id'):
        dia = timezone.localdate(linea.pago.fecha)
        tasa = tasas.vigente(linea.medio, dia)
        yield LineaComision(linea=linea, fecha=linea.pago.fecha,
                            desglose=calcular(linea.monto, tasa), tasa=tasa)


def resumen(desde, hasta, pagos=None) -> dict:
    """Totales del período, en total y por medio (en el orden de Pago.MEDIOS)."""
    from .models import Pago

    total = Desglose(cobrado=Decimal('0'))
    por_medio = {}
    for l in lineas(desde, hasta, pagos=pagos):
        total = total + l.desglose
        por_medio[l.linea.medio] = por_medio.get(l.linea.medio, Desglose(cobrado=Decimal('0'))) + l.desglose
    orden = [m for m, _ in Pago.MEDIOS]
    return {
        'total': total,
        'por_medio': dict(sorted(por_medio.items(), key=lambda kv: orden.index(kv[0]))),
    }


def como_dict(d: Desglose) -> dict:
    """Para la API: números simples."""
    return {
        'cobrado':         float(d.cobrado),
        'comision':        float(d.comision),
        'iva_comision':    float(d.iva_comision),
        'retencion_renta': float(d.retencion_renta),
        'retencion_iva':   float(d.retencion_iva),
        'costo':           float(d.costo),
        'retenciones':     float(d.retenciones),
        'neto':            float(d.neto),
    }
