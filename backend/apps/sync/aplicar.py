"""
Aplicar un lote de cambios que llegó del otro nodo.

Regla de conflicto: **gana el cambio más reciente**, comparando el
`actualizado_en` que trae el cambio contra el que tiene la fila local. En un
empate gana el servidor, porque es el equipo donde trabaja todo el mundo y el
que tiene el stock y las ventas atadas al catálogo.

Lo que pierde no se tira: queda en `ConflictoSync` con los dos lados completos.
Un rechazo silencioso es peor que una lista para revisar — la propietaria
corrigió un precio estando afuera y tiene derecho a enterarse de que no quedó.
"""
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .conciliacion import buscar_equivalente, resolver_choques_unicos
from .contexto import aplicacion_remota
from .models import CambioSync, ConflictoSync
from .registro import orden_de_aplicacion, es_sincronizable
from .serializacion import (
    DependenciaFaltante, aplicar_datos, modelo_de, serializar,
)

logger = logging.getLogger(__name__)

# Cuántas veces se reintenta un cambio cuya FK todavía no llegó. Con el orden
# de `registro.py` alcanza una vuelta; la segunda cubre el caso raro de dos
# lotes cruzados.
MAX_VUELTAS = 3


class Resultado:
    def __init__(self):
        self.aplicados = 0
        self.conflictos = 0
        self.omitidos = 0
        self.detalle = []

    def como_dict(self):
        return {
            'aplicados': self.aplicados,
            'conflictos': self.conflictos,
            'omitidos': self.omitidos,
            'detalle': self.detalle,
        }


def _momento(valor):
    if valor is None:
        return None
    if isinstance(valor, str):
        momento = parse_datetime(valor)
    else:
        momento = valor
    if momento is not None and timezone.is_naive(momento):
        momento = timezone.make_aware(momento)
    return momento


def _anotar_conflicto(cambio, motivo, detalle, local=None, momento_local=None):
    ConflictoSync.objects.create(
        modelo=cambio['modelo'],
        uid=cambio['uid'],
        operacion=cambio['operacion'],
        motivo=motivo,
        detalle=detalle,
        datos_recibidos=cambio.get('datos') or {},
        datos_locales=serializar(local) if local is not None else {},
        nodo_origen=cambio.get('nodo', ''),
        momento_recibido=_momento(cambio.get('momento')),
        momento_local=momento_local,
    )


def _aplicar_uno(cambio):
    """
    Aplica un cambio. Devuelve 'aplicado', 'conflicto' u 'omitido'.
    Levanta `DependenciaFaltante` si hay que reintentarlo más tarde.
    """
    et = cambio['modelo']
    if not es_sincronizable(et):
        # Alguien mandó algo fuera del alcance acordado. No es un error del
        # otro nodo necesariamente (puede ser una versión más nueva), pero acá
        # no se toca: stock, ventas y caja tienen un solo dueño.
        return 'omitido'

    modelo = modelo_de(et)
    recibido = _momento(cambio.get('momento')) or timezone.now()
    local = modelo.objects.filter(uid=cambio['uid']).first()

    # ── Baja ──────────────────────────────────────────────────────────────
    if cambio['operacion'] == CambioSync.BAJA:
        if local is None:
            return 'omitido'           # ya no estaba: el resultado es el mismo
        if local.actualizado_en > recibido:
            _anotar_conflicto(
                cambio, ConflictoSync.MAS_NUEVO_GANA,
                'La fila se modificó acá después de que allá se la borrara.',
                local=local, momento_local=local.actualizado_en)
            return 'conflicto'
        local.delete()
        return 'aplicado'

    # ── Alta / modificación ───────────────────────────────────────────────
    if local is None:
        # Puede existir igual con otro uid: los dos equipos cargaron la misma
        # marca, o la misma variante del mismo producto. Para saberlo hay que
        # armar primero la fila, porque la clave natural incluye claves
        # foráneas que sólo se resuelven una vez aplicados los datos.
        tentativa = aplicar_datos(modelo(uid=cambio['uid']), cambio.get('datos') or {})
        local = buscar_equivalente(modelo, et, tentativa, cambio['uid'])
        if local is not None:
            # Es la misma cosa cargada dos veces: se adopta la fila de acá y se
            # le pone el uid que viene, para que los dos nodos converjan en una.
            logger.info('Sync — %s %s se fusiona con la fila local %s',
                        et, cambio['uid'], local.pk)

    if local is not None:
        if local.actualizado_en > recibido:
            _anotar_conflicto(
                cambio, ConflictoSync.MAS_NUEVO_GANA,
                'La versión local es más nueva; se conservó.',
                local=local, momento_local=local.actualizado_en)
            return 'conflicto'
        if local.actualizado_en == recibido and settings.NODO['rol'] == 'servidor':
            # Empate: manda el servidor. Sin esto, dos relojes sincronizados
            # producirían resultados distintos según quién sincronice primero.
            return 'omitido'
        instancia = local
    else:
        instancia = modelo(uid=cambio['uid'])

    aplicar_datos(instancia, cambio.get('datos') or {})
    instancia.uid = cambio['uid']
    instancia.actualizado_en = recibido
    instancia.nodo_origen = cambio.get('nodo', '')

    # Códigos y SKU los genera cada base por su cuenta y llegan al mismo valor
    # si los dos equipos cargaron mercadería sin verse.
    ajustes = resolver_choques_unicos(modelo, et, instancia, cambio['uid'])

    instancia.save(preservar_sync=True)
    return ('aplicado', ajustes) if ajustes else 'aplicado'


@transaction.atomic
def aplicar_lote(cambios):
    """
    Aplica una lista de cambios (dicts como los serializa `CambioSync`).

    Todo o nada: si algo revienta a mitad de camino, la base queda como estaba
    y el agente reintenta. Un catálogo a medio aplicar es peor que uno viejo.
    """
    resultado = Resultado()

    # Por modelo, respetando dependencias: la categoría antes que el producto,
    # el producto antes que la variante.
    orden = {et: i for i, et in enumerate(orden_de_aplicacion({c['modelo'] for c in cambios}))}
    pendientes = sorted(
        cambios,
        key=lambda c: (orden.get(c['modelo'], 999), _momento(c.get('momento')) or timezone.now()),
    )

    with aplicacion_remota():
        for vuelta in range(MAX_VUELTAS):
            faltantes = []
            for cambio in pendientes:
                try:
                    estado = _aplicar_uno(cambio)
                except DependenciaFaltante as e:
                    faltantes.append((cambio, e))
                    continue
                except Exception as e:
                    logger.exception('Error aplicando %s %s', cambio.get('modelo'), cambio.get('uid'))
                    _anotar_conflicto(cambio, ConflictoSync.ERROR, str(e))
                    resultado.conflictos += 1
                    continue

                if isinstance(estado, tuple):
                    estado, ajustes = estado
                    resultado.detalle.append({
                        'modelo': cambio['modelo'], 'uid': cambio['uid'],
                        'ajustes': ajustes,
                    })

                if estado == 'aplicado':
                    resultado.aplicados += 1
                elif estado == 'conflicto':
                    resultado.conflictos += 1
                else:
                    resultado.omitidos += 1

            if not faltantes:
                break
            # Si en toda una vuelta no se resolvió nada, no va a resolverse:
            # la fila referenciada no existe de este lado.
            if len(faltantes) == len(pendientes):
                for cambio, e in faltantes:
                    _anotar_conflicto(
                        cambio, ConflictoSync.NO_EXISTE,
                        f'No existe acá la fila referenciada por "{e.campo}" ({e.uid_destino}).')
                    resultado.conflictos += 1
                break
            pendientes = [c for c, _ in faltantes]
        else:
            for cambio in pendientes:
                _anotar_conflicto(cambio, ConflictoSync.NO_EXISTE,
                                  'Quedó sin resolver tras varias vueltas.')
                resultado.conflictos += 1

    return resultado
