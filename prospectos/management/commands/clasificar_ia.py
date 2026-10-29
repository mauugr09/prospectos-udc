from django.core.management.base import BaseCommand

from ...servicios import seguridad


class Command(BaseCommand):
    help = 'Clasifica respuestas abiertas por tema con IA (solo si IA_HABILITADA y hay IA_API_KEY).'

    def add_arguments(self, parser):
        parser.add_argument('--limite', type=int, default=100)

    def handle(self, *args, limite, **o):
        if not seguridad.ia_habilitada():
            self.stdout.write('La clasificación con IA está desactivada (datos/config.json → IA_HABILITADA).')
            return
        self.stdout.write(f'Clasificadas: {seguridad.clasificar_pendientes(limite)}')
