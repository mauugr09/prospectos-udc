from django.core.management import call_command
from django.core.management.base import BaseCommand

from ...servicios import semillas


class Command(BaseCommand):
    help = 'Crea/actualiza tablas, preguntas, carreras y roles. Seguro de repetir.'

    def handle(self, *args, **o):
        call_command('migrate', verbosity=0, interactive=False)
        semillas.preparar()
        self.stdout.write(self.style.SUCCESS('Base de datos lista.'))
