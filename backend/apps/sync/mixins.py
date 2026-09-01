"""
Identidad global para las filas que viajan entre la notebook y el servidor.
"""
import uuid

from django.db import models
from django.utils import timezone


class ModeloSincronizable(models.Model):
    """
    Agrega a un modelo lo mínimo para poder sincronizarlo en dos direcciones.

    **La clave primaria sigue siendo el entero de siempre.** El `uid` es una
    identidad *aparte*, no un reemplazo: cambiar las PK a UUID obligaría a
    reescribir cada clave foránea, cada serializer, cada URL de la app y los
    tickets impresos. El `uid` solo lo usa el sync, y resuelve el problema real:
    si la notebook crea un producto estando afuera y el local crea otro, las dos
    bases le asignan el mismo entero a filas distintas, pero nunca el mismo UUID.

    `actualizado_en` se fija en `save()` y no con `auto_now` porque al aplicar
    un cambio que llega del otro nodo hay que conservar la hora del equipo que
    lo hizo — es lo que decide quién gana el conflicto. Con `auto_now` se
    pisaría con la hora local y todo cambio recién aplicado parecería el más
    nuevo del mundo.
    """

    uid = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False, db_index=True,
        help_text='Identidad de la fila entre equipos. La asigna quien la crea.',
    )

    actualizado_en = models.DateTimeField(
        default=timezone.now, db_index=True,
        help_text='Hora del equipo que hizo el último cambio. Decide conflictos.',
    )

    nodo_origen = models.CharField(
        max_length=60, blank=True, default='',
        help_text='Equipo donde se hizo el último cambio.',
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """
        Marca la fila como cambiada ahora, salvo que el cambio venga del otro
        nodo (`preservar_sync=True`), en cuyo caso los tres campos ya vienen
        puestos con los valores del equipo de origen.
        """
        if not kwargs.pop('preservar_sync', False):
            from django.conf import settings
            self.actualizado_en = timezone.now()
            self.nodo_origen = settings.NODO['nombre']
        super().save(*args, **kwargs)
