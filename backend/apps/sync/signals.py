"""
Anotar cada cambio local sobre un modelo sincronizable.

Se enganchan a `post_save`/`post_delete` de los modelos de `registro.py`. Es
deliberadamente automático: si dependiera de que cada vista se acuerde de
registrar el cambio, el primer endpoint nuevo que alguien agregue rompería el
sync en silencio.
"""
import logging

from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from .contexto import aplicando_remoto
from .models import CambioSync
from .registro import MODELOS_BIDIRECCIONALES
from .serializacion import etiqueta, modelo_de, serializar

logger = logging.getLogger(__name__)


def _anotar(instancia, operacion):
    if aplicando_remoto():
        # Viene del otro nodo: ya está en su registro, no en el nuestro.
        return

    et = etiqueta(instancia.__class__)
    try:
        datos = {} if operacion == CambioSync.BAJA else serializar(instancia)
        CambioSync.objects.create(
            modelo=et,
            uid=instancia.uid,
            operacion=operacion,
            datos=datos,
            nodo=settings.NODO['nombre'],
            momento=getattr(instancia, 'actualizado_en', None) or timezone.now(),
        )
    except Exception:
        # Un fallo acá no puede tumbar la venta o la carga que lo disparó. Se
        # pierde el cambio en el sync (se recupera en el próximo dump completo
        # servidor → notebook), pero la operación del usuario sigue.
        logger.exception('No se pudo anotar el cambio de sync para %s %s', et, instancia.pk)


def conectar():
    """Engancha los signals. La llama `SyncConfig.ready()`."""
    for et in MODELOS_BIDIRECCIONALES:
        modelo = modelo_de(et)

        @receiver(post_save, sender=modelo, weak=False,
                  dispatch_uid=f'sync_guardar_{et}')
        def _guardado(sender, instance, created, **kwargs):
            _anotar(instance, CambioSync.ALTA if created else CambioSync.CAMBIO)

        @receiver(post_delete, sender=modelo, weak=False,
                  dispatch_uid=f'sync_borrar_{et}')
        def _borrado(sender, instance, **kwargs):
            _anotar(instance, CambioSync.BAJA)
