"""Escribe «Conectar a Prospectos.cmd» (ver servicios/instalador.py). Lo mismo que el botón de Otras computadoras."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ...servicios import instalador, red


class Command(BaseCommand):
    help = 'Genera el archivo de un clic para conectar otra computadora Windows a esta principal.'

    def add_arguments(self, parser):
        parser.add_argument('--salida', default='Conectar a Prospectos.cmd')
        parser.add_argument('--direccion', action='append', help='Dirección a probar (se puede repetir); por omisión, las de esta PC')

    def handle(self, *args, salida, direccion=None, **o):
        ca = settings.DATA_DIR / 'red' / 'ca.crt'
        if not ca.exists():
            raise CommandError('Esta computadora no tiene el acceso por red activo (Configuración → Otras computadoras).')
        direcciones = direccion or red.direcciones(settings.CONFIG)
        try:
            contenido = instalador.generar(direcciones, ca, red.codigo_ca(settings.DATA_DIR))
        except ValueError as e:
            raise CommandError(str(e)) from e
        with open(salida, 'w', encoding='ascii', newline='') as f:
            f.write(contenido)
        self.stdout.write(self.style.SUCCESS(f'Listo: {salida} ({len(direcciones)} direcciones).'))
