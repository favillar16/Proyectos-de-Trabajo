from django.apps import AppConfig

class InventarioConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.inventario'
    verbose_name = 'Inventario'

    def ready(self):
        # Registrar señales al iniciar la app
        import apps.inventario.models  # noqa: F401
