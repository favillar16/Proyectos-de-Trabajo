"""
Registro de cambios para la sincronización notebook ↔ servidor.

**Estas tablas NO viven en `ceramica_db`.** Van en una SQLite aparte
(`sync.sqlite3`, ver `apps/sync/routers.py`), y esa es la decisión que hace
que todo lo demás funcione: la sincronización servidor → notebook se hace con
`pg_dump` + `psql`, que borra y rehace `ceramica_db` entera. Si el registro de
cambios viviera ahí adentro, cada sync exitoso se llevaría puesto justamente
lo que la notebook todavía no alcanzó a empujar.

Ver `docs/sync_bidireccional.md`.
"""
import uuid

from django.db import models


class CambioSync(models.Model):
    """
    Un cambio hecho localmente sobre una fila sincronizable.

    Los escribe el signal de `apps/sync/signals.py`, uno por `save()` o
    `delete()`. Son inmutables: cuando el cambio se empuja al otro nodo se
    marca `empujado_en`, nunca se edita ni se borra el original — es el
    historial que permite reconstruir qué pasó estando afuera del local.
    """

    ALTA   = 'alta'
    CAMBIO = 'cambio'
    BAJA   = 'baja'
    OPERACIONES = [
        (ALTA,   'Alta'),
        (CAMBIO, 'Modificación'),
        (BAJA,   'Baja'),
    ]

    # Qué fila cambió. `modelo` es la etiqueta Django ("productos.Producto") y
    # `uid` el identificador global de la fila, que es el mismo en los dos
    # equipos — a diferencia de la clave primaria, que cada base asigna sola.
    modelo = models.CharField(max_length=80, db_index=True)
    uid    = models.UUIDField(db_index=True)

    operacion = models.CharField(max_length=10, choices=OPERACIONES)

    # Fila completa serializada, con las claves foráneas expresadas por uid.
    # En una baja va vacío: alcanza con modelo + uid.
    datos = models.JSONField(default=dict, blank=True)

    # Quién y cuándo. `momento` es la hora del equipo que hizo el cambio y es
    # lo que decide los conflictos, así que se guarda con el cambio y no se
    # recalcula al aplicarlo del otro lado.
    nodo    = models.CharField(max_length=60, db_index=True)
    momento = models.DateTimeField(db_index=True)

    # Nulo mientras está pendiente de empujar.
    empujado_en = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'sync_cambios'
        ordering = ['momento', 'id']
        indexes = [
            models.Index(fields=['empujado_en', 'momento']),
            models.Index(fields=['modelo', 'uid']),
        ]

    def __str__(self):
        return f'{self.operacion} {self.modelo} {self.uid} @{self.nodo}'


class ConflictoSync(models.Model):
    """
    Cambio que llegó del otro nodo y NO se aplicó.

    Existe para que un rechazo nunca sea silencioso. Si la propietaria corrigió
    el precio de un producto estando afuera y mientras tanto alguien lo corrigió
    en el local, gana el más reciente y el otro queda acá anotado, con los datos
    completos, para poder revisarlo en vez de descubrirlo por casualidad.
    """

    MAS_NUEVO_GANA = 'mas_nuevo'
    NO_EXISTE      = 'no_existe'
    ERROR          = 'error'
    MOTIVOS = [
        (MAS_NUEVO_GANA, 'La fila local era más nueva'),
        (NO_EXISTE,      'La fila referenciada no existe acá'),
        (ERROR,          'Error al aplicar'),
    ]

    modelo    = models.CharField(max_length=80, db_index=True)
    uid       = models.UUIDField(db_index=True)
    operacion = models.CharField(max_length=10)
    motivo    = models.CharField(max_length=20, choices=MOTIVOS)
    detalle   = models.TextField(blank=True)

    # Los dos lados del conflicto, para poder compararlos sin adivinar.
    datos_recibidos = models.JSONField(default=dict, blank=True)
    datos_locales   = models.JSONField(default=dict, blank=True)

    nodo_origen      = models.CharField(max_length=60)
    momento_recibido = models.DateTimeField(null=True, blank=True)
    momento_local    = models.DateTimeField(null=True, blank=True)

    registrado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    revisado      = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = 'sync_conflictos'
        ordering = ['-registrado_en']

    def __str__(self):
        return f'{self.modelo} {self.uid}: {self.get_motivo_display()}'


class EstadoSync(models.Model):
    """
    Resumen de la última corrida contra un nodo. Una fila por nodo.

    No es el historial (ese son los `CambioSync`), es el "cómo venimos": lo que
    mira el diagnóstico y lo que se muestra en pantalla.
    """

    nodo = models.CharField(max_length=60, unique=True)

    ultimo_intento = models.DateTimeField(null=True, blank=True)
    ultimo_exito   = models.DateTimeField(null=True, blank=True)

    cambios_enviados  = models.PositiveIntegerField(default=0)
    cambios_recibidos = models.PositiveIntegerField(default=0)
    conflictos        = models.PositiveIntegerField(default=0)

    detalle = models.TextField(blank=True)

    class Meta:
        db_table = 'sync_estado'

    def __str__(self):
        return f'{self.nodo}: {self.ultimo_exito or "nunca"}'


def nuevo_uid():
    """Default de `ModeloSincronizable.uid`. Con nombre propio para que las
    migraciones no dependan de un lambda ni de `uuid.uuid4` sin contexto."""
    return uuid.uuid4()
