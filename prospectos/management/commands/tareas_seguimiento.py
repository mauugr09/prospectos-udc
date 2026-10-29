from django.core.management.base import BaseCommand

from ...servicios import seguimiento


class Command(BaseCommand):
    help = 'Crea tareas para prospectos activos que llevan X días sin contacto.'

    def handle(self, *args, **o):
        self.stdout.write(f'Tareas creadas: {seguimiento.generar_tareas_sin_contacto()}')
