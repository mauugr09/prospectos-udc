from django.core.management.base import BaseCommand

from ...servicios import semillas, seguimiento


class Command(BaseCommand):
    help = 'Carga datos de DEMOSTRACIÓN ficticios (no usar con datos reales).'

    def add_arguments(self, parser):
        parser.add_argument('--familias', type=int, default=160)

    def handle(self, *args, familias, **o):
        from django.contrib.auth import get_user_model
        from django.core.management.base import CommandError
        from ...models import Respuesta
        from ...servicios import demo
        reales = get_user_model().objects.exclude(username__iendswith=demo.DOMINIO)
        if reales.exists() or Respuesta.objects.exclude(formulario__in=demo._forms()).exists():
            raise CommandError('Esta carpeta ya tiene usuarios o aspirantes reales: la demostración se mezclaría con ellos. '
                               'Para capacitar, copia el programa a OTRA carpeta (sin «datos») y corre ahí «Prospectos.exe demo».')
        r = semillas.cargar_demo(familias, salida=self.stdout.write)
        seguimiento.esperar_correos()
        self.stdout.write(self.style.SUCCESS(f"Usuarios: {', '.join(r['usuarios'])} · contraseña: {r['clave']}"))
