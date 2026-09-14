"""
Terminal POS: cobro con tarjeta.

Qué problema resuelve, concretamente: hoy un cobro con tarjeta guarda
`Pago.medio_pago = 'credito'` y nada más. El SIFEN exige bastante más — el
grupo E620 (`gPagTarCD`) del Manual Técnico **se activa obligatoriamente**
cuando el medio de pago es tarjeta, y pide como mínimo la denominación de la
tarjeta y la forma de procesamiento. Sin esos datos, ninguna venta con
tarjeta se puede facturar electrónicamente.

Así que esto no es solo comodidad para la cajera: es un requisito para que
la migración a e-Kuatia no deje afuera todas las ventas con tarjeta.

─── Las dos formas de conectar una terminal ────────────────────────────────

En Paraguay las terminales las provee la procesadora (Bancard es la más
común, también Infonet y Procard), y hay dos modos:

1. **Autónoma** — la cajera tipea el monto en la terminal, la terminal
   imprime el voucher con el código de autorización, y ese dato se carga a
   mano en el sistema. No requiere acuerdo con nadie: funciona hoy.

2. **Integrada** — el sistema le manda el monto a la terminal por USB, serie
   o red, y recibe de vuelta la autorización. Evita que la cajera tipee dos
   veces y elimina el error de tipeo. Requiere el SDK y un acuerdo comercial
   con la procesadora: es una dependencia externa, como el certificado de
   firma.

Este módulo implementa la primera y **deja lista la segunda**: caja habla
siempre con `obtener_terminal()` y nunca con una marca concreta, así que el
día que exista el acuerdo se agrega un driver y no se toca la pantalla de
cobro ni la facturación.
"""
import logging
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings

from apps.facturacion import codigos

logger = logging.getLogger(__name__)


class ErrorPOS(Exception):
    """La terminal no pudo completar el cobro."""


@dataclass
class ResultadoPOS:
    """
    Lo que devuelve un cobro con tarjeta, venga de donde venga.

    Es la misma forma tanto si la cajera copió el voucher a mano como si la
    terminal lo mandó sola. Ese es el punto de tener esta estructura: caja
    trata los dos casos igual.
    """
    aprobado: bool = True
    denominacion: int = codigos.TARJETA_OTRA
    denominacion_descripcion: str = ''
    forma_procesamiento: int = codigos.PROCESAMIENTO_POS
    codigo_autorizacion: str = ''
    titular: str = ''
    ultimos_digitos: str = ''
    procesadora_ruc: str = ''
    procesadora_razon_social: str = ''
    numero_boleta: str = ''
    mensaje: str = ''
    crudo: dict = field(default_factory=dict)

    @property
    def descripcion(self) -> str:
        """Texto del campo E622, coherente con el código E621."""
        return codigos.descripcion_tarjeta(
            self.denominacion, self.denominacion_descripcion)


class TerminalPOS:
    """
    Interfaz de una terminal. Un driver nuevo implementa `cobrar()`.

    `integrada` dice si el sistema habla electrónicamente con la terminal.
    La pantalla de caja lo usa para decidir si pide los datos del voucher o
    los espera de la terminal.
    """
    nombre = 'base'
    integrada = False

    def cobrar(self, monto: Decimal, *, medio: str, datos: dict) -> ResultadoPOS:
        raise NotImplementedError

    def disponible(self) -> bool:
        return True


class TerminalManual(TerminalPOS):
    """
    Terminal autónoma: la cajera copia los datos del voucher.

    Es el modo por defecto y el único que funciona sin acuerdo con la
    procesadora. No se comunica con ningún dispositivo: toma los datos que
    vinieron del formulario de cobro y los valida.

    Valida en serio, y no por prolijidad: la denominación de la tarjeta es
    obligatoria para el SIFEN, así que dejarla pasar vacía significa que el
    documento electrónico va a volver rechazado cuando ya no haya nadie en
    el mostrador para preguntarle al cliente con qué tarjeta pagó.
    """
    nombre = 'manual'
    integrada = False

    def cobrar(self, monto, *, medio, datos) -> ResultadoPOS:
        denominacion = datos.get('denominacion')
        try:
            denominacion = int(denominacion)
        except (TypeError, ValueError):
            raise ErrorPOS(
                'Falta indicar con qué tarjeta se pagó (Visa, Mastercard...). '
                'El SIFEN lo exige en toda venta con tarjeta.')

        valida = set(codigos.DENOMINACION_TARJETA) | {codigos.TARJETA_OTRA}
        if denominacion not in valida:
            raise ErrorPOS(
                f'La denominación de tarjeta {denominacion} no es una de las '
                f'que acepta el SIFEN.')

        ultimos = ''.join(c for c in str(datos.get('ultimos_digitos') or '')
                          if c.isdigit())[-4:]

        return ResultadoPOS(
            aprobado=True,
            denominacion=denominacion,
            denominacion_descripcion=datos.get('denominacion_descripcion', ''),
            forma_procesamiento=codigos.PROCESAMIENTO_POS,
            codigo_autorizacion=str(datos.get('codigo_autorizacion') or '').strip(),
            titular=str(datos.get('titular') or '').strip()[:30],
            ultimos_digitos=ultimos,
            procesadora_ruc=str(datos.get('procesadora_ruc') or '').strip(),
            procesadora_razon_social=str(
                datos.get('procesadora_razon_social') or '').strip()[:60],
            numero_boleta=str(datos.get('numero_boleta') or '').strip(),
        )


class TerminalSimulada(TerminalPOS):
    """
    Aprueba todo sin preguntar nada. Para la demo y para los tests.

    Nunca debe quedar configurada en la PC del local: aprobaría cobros que
    en la vida real la procesadora rechazó.
    """
    nombre = 'simulada'
    integrada = True

    def cobrar(self, monto, *, medio, datos) -> ResultadoPOS:
        logger.warning('TerminalSimulada: aprobando %s sin consultar a nadie.',
                       monto)
        return ResultadoPOS(
            aprobado=True,
            denominacion=codigos.TARJETA_VISA,
            forma_procesamiento=codigos.PROCESAMIENTO_POS,
            codigo_autorizacion='000000',
            titular='SIMULADO',
            ultimos_digitos='0000',
            mensaje='Cobro simulado — no hubo terminal.',
        )


TERMINALES = {
    'manual': TerminalManual,
    'simulada': TerminalSimulada,
}


def obtener_terminal() -> TerminalPOS:
    """
    La terminal configurada. Ante cualquier duda, la manual.

    Caer en la manual es el comportamiento seguro: pide los datos en vez de
    inventarlos. Caer en la simulada aprobaría cobros que no ocurrieron.
    """
    nombre = getattr(settings, 'POS', {}).get('terminal', 'manual')
    clase = TERMINALES.get(nombre)
    if clase is None:
        logger.warning(
            'POS_TERMINAL=%r no existe; se usa la terminal manual. '
            'Opciones: %s', nombre, ', '.join(TERMINALES))
        clase = TerminalManual
    return clase()


def requiere_datos_de_tarjeta(medio_pago: str) -> bool:
    """
    ¿Este medio de pago obliga a declarar el grupo de tarjeta del SIFEN?

    Se decide traduciendo primero al código del SIFEN, para no repetir acá la
    lista de medios que ya vive en `codigos.MEDIO_PAGO`.
    """
    return codigos.codigo_medio_pago(medio_pago) in codigos.MEDIOS_CON_TARJETA
