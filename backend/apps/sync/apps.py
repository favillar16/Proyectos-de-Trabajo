from django.apps import AppConfig


class SyncConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.sync'
    label = 'sync'
    verbose_name = 'Sincronización notebook ↔ servidor'

    def ready(self):
        # Los signals se enganchan acá y no al importar el módulo: en `ready()`
        # ya está el registro de modelos armado, así que `registro.py` puede
        # resolver "productos.Producto" a la clase real.
        from . import signals
        signals.conectar()
