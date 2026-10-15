"""
Runner de tests que nunca deja imprimir en la térmica.

settings.py ya vacía la impresora mirando sys.argv, y settings_test.py también.
Este runner es la última barrera: la vacía al preparar el entorno de tests,
sin depender de cómo se lanzó la corrida ni de qué settings se usen. Cada
ticket de una corrida de tests es papel gastado en la PC del local.
"""
from django.conf import settings
from django.test.runner import DiscoverRunner


class RunnerSinImpresora(DiscoverRunner):

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        settings.IMPRESORA_TERMICA = {
            **settings.IMPRESORA_TERMICA,
            'nombre_windows': '',
            'puerto_directo': '',
        }
