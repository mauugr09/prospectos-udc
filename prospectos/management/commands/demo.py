from django.core.management.base import BaseCommand

from ...servicios import semillas, seguimiento


class Command(BaseCommand):
    help = 'Carga datos de DEMOSTRACIÓN ficticios (no usar con datos reales).'

    def add_arguments(self, parser):
        parser.add_argument('--familias', type=int, default=160)

    def handle(self, *args, familias, **o):
        r = semillas.cargar_demo(familias, salida=self.stdout.write)
        seguimiento.esperar_correos()
        self.stdout.write(self.style.SUCCESS(f"Usuarios: {', '.join(r['usuarios'])} · contraseña: {r['clave']}"))
