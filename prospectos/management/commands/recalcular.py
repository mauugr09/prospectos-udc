from django.core.management.base import BaseCommand

from ...servicios import inteligencia


class Command(BaseCommand):
    help = 'Recalcula consentimiento, score, segmentos y brechas de todos los prospectos.'

    def handle(self, *args, **o):
        self.stdout.write(f'Recalculados: {inteligencia.recalcular_todos()}')
