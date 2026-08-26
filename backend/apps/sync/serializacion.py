"""
Convertir filas a JSON y de vuelta, con las claves foráneas expresadas por uid.

Es lo único delicado del sync. Una fila serializada tiene que poder aplicarse
en la otra base sin arrastrar ni una sola clave primaria: los enteros no
significan lo mismo de los dos lados. Donde el modelo dice `producto_id = 412`,
el JSON lleva `producto: "<uuid>"` y al aplicarlo se busca el producto que
tenga ese uid en la base de destino.
"""
import datetime
import decimal
import uuid

from django.apps import apps
from django.db import models
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime, parse_time

from .registro import campos_excluidos, MODELOS_CON_ARCHIVO


class DependenciaFaltante(Exception):
    """Una FK apunta a una fila que todavía no existe en esta base."""

    def __init__(self, campo, uid_destino):
        self.campo = campo
        self.uid_destino = uid_destino
        super().__init__(f'falta {campo}={uid_destino}')


def etiqueta(modelo):
    return f'{modelo._meta.app_label}.{modelo._meta.object_name}'


def modelo_de(etiqueta_):
    app_label, nombre = etiqueta_.split('.')
    return apps.get_model(app_label, nombre)


# ─── Valores sueltos ─────────────────────────────────────────────────────────

def _a_json(valor):
    """Lleva a algo que `JSONField` acepte, sin perder precisión."""
    if isinstance(valor, decimal.Decimal):
        # str y no float: los precios son Decimal y float los redondea mal.
        return str(valor)
    if isinstance(valor, (datetime.datetime, datetime.date, datetime.time)):
        return valor.isoformat()
    if isinstance(valor, uuid.UUID):
        return str(valor)
    if isinstance(valor, models.fields.files.FieldFile):
        return valor.name or ''
    return valor


# ─── Serializar ──────────────────────────────────────────────────────────────

def serializar(instancia):
    """
    Fila → dict listo para viajar.

    Las FK salen como el uid del destino. Si el destino no es sincronizable
    (por ejemplo el usuario que subió una foto) se omite el campo: no tiene
    sentido intentar resolverlo del otro lado.
    """
    et = etiqueta(instancia.__class__)
    excluidos = campos_excluidos(et)
    datos = {}

    for campo in instancia._meta.concrete_fields:
        if campo.name in excluidos or campo.attname in excluidos:
            continue

        if isinstance(campo, models.ForeignKey):
            relacionado = getattr(instancia, campo.name, None)
            if relacionado is None:
                datos[campo.name] = None
            elif hasattr(relacionado, 'uid'):
                datos[campo.name] = str(relacionado.uid)
            else:
                # FK a algo que no se sincroniza (usuarios, por ejemplo): no
                # viaja. Del otro lado la fila queda con ese campo en su default.
                continue
        else:
            datos[campo.name] = _a_json(getattr(instancia, campo.attname))

    # El archivo adjunto viaja aparte (ver views.py); acá solo su ruta, que es
    # lo que la base guarda.
    if et in MODELOS_CON_ARCHIVO:
        campo_archivo = MODELOS_CON_ARCHIVO[et]
        archivo = getattr(instancia, campo_archivo, None)
        datos[campo_archivo] = archivo.name if archivo else ''

    return datos


# ─── Deserializar ────────────────────────────────────────────────────────────

def _resolver_fk(campo, valor_uid):
    if valor_uid in (None, ''):
        return None
    destino = campo.remote_field.model
    try:
        return destino.objects.get(uid=valor_uid)
    except destino.DoesNotExist:
        raise DependenciaFaltante(campo.name, valor_uid)
    except (ValueError, TypeError):
        raise DependenciaFaltante(campo.name, valor_uid)


def aplicar_datos(instancia, datos):
    """
    Vuelca `datos` sobre `instancia` sin guardarla.

    Levanta `DependenciaFaltante` si alguna FK apunta a una fila que todavía no
    llegó — quien llame decide si reintentar más tarde o anotar el conflicto.
    """
    et = etiqueta(instancia.__class__)
    excluidos = campos_excluidos(et)
    campo_archivo = MODELOS_CON_ARCHIVO.get(et)

    for campo in instancia._meta.concrete_fields:
        if campo.name in excluidos or campo.name not in datos:
            continue

        valor = datos[campo.name]

        if isinstance(campo, models.ForeignKey):
            setattr(instancia, campo.name, _resolver_fk(campo, valor))
            continue

        if campo.name == campo_archivo:
            # Se asigna la ruta cruda: el archivo en sí lo mueve el agente y
            # puede llegar antes o después que la fila.
            setattr(instancia, campo.attname, valor or '')
            continue

        if isinstance(campo, models.DecimalField) and valor is not None:
            valor = decimal.Decimal(str(valor))
        elif isinstance(campo, models.UUIDField) and valor:
            valor = uuid.UUID(str(valor))
        # DateTimeField antes que DateField: el primero hereda del segundo.
        elif isinstance(campo, models.DateTimeField) and valor:
            momento = parse_datetime(valor) if isinstance(valor, str) else valor
            if momento is not None and timezone.is_naive(momento):
                # Los dos equipos corren en America/Asuncion, pero si alguno
                # manda una fecha sin zona la interpretamos como local en vez
                # de dejar que Django avise y la trate como UTC.
                momento = timezone.make_aware(momento)
            valor = momento
        elif isinstance(campo, models.DateField) and valor:
            valor = parse_date(valor) if isinstance(valor, str) else valor
        elif isinstance(campo, models.TimeField) and valor:
            valor = parse_time(valor) if isinstance(valor, str) else valor

        setattr(instancia, campo.attname, valor)

    return instancia
