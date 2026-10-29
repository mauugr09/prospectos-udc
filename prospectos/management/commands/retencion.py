from django.core.management.base import BaseCommand

from ...servicios import seguridad


class Command(BaseCommand):
    help = 'Purga datos sin consentimiento (cuarentena vencida o negado) y anonimiza inactivos.'

    def handle(self, *args, **o):
        self.stdout.write(f'Sin consentimiento purgados: {seguridad.purgar_sin_consentimiento()}')
        self.stdout.write(f'Inactivos anonimizados: {seguridad.anonimizar_inactivos()}')
