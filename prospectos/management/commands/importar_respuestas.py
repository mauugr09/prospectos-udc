from django.core.management.base import BaseCommand

from ...models import Formulario
from ...servicios import importacion, seguimiento


class Command(BaseCommand):
    help = 'Importa las respuestas nuevas o editadas de los formularios activos.'

    def add_arguments(self, parser):
        parser.add_argument('--formulario', type=int, help='ID de un formulario en particular')

    def handle(self, *args, formulario=None, **o):
        qs = Formulario.objects.filter(activo=True)
        if formulario:
            qs = qs.filter(pk=formulario)
        for f in qs:
            r = importacion.importar(f)
            estilo = self.style.SUCCESS if r.estado == 'ok' else self.style.ERROR
            self.stdout.write(estilo(f'{f}: {r.estado} · nuevas {r.nuevas} · actualizadas {r.actualizadas} · omitidas {r.omitidas}'
                                     + (f' · {r.mensaje}' if r.mensaje else '')))
        seguimiento.esperar_correos()
