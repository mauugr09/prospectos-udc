from django.core.management.base import BaseCommand

from ...servicios import seguridad


class Command(BaseCommand):
    help = 'Clasifica por tema las respuestas abiertas pendientes (reglas propias, sin IA externa).'

    def add_arguments(self, parser):
        parser.add_argument('--limite', type=int, default=500)

    def handle(self, *args, limite, **o):
        self.stdout.write(f'Clasificadas: {seguridad.clasificar_pendientes(limite)}')
