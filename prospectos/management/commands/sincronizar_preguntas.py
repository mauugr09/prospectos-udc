from django.core.management.base import BaseCommand, CommandError

from ...models import Formulario
from ...servicios import importacion


class Command(BaseCommand):
    help = 'Muestra el mapeo propuesto (pregunta del Form → código). Con --aplicar lo guarda.'

    def add_arguments(self, parser):
        parser.add_argument('formulario', type=int)
        parser.add_argument('--aplicar', action='store_true')

    def handle(self, *args, formulario, aplicar, **o):
        f = Formulario.objects.filter(pk=formulario).first()
        if not f:
            raise CommandError('No existe ese formulario.')
        propuesta = importacion.proponer_mapeo(f)
        for p in propuesta:
            self.stdout.write(f"{p['question_id']:>12}  {p['similitud']:.2f}  {p['codigo'] or '— sin asignar —':<35} {p['titulo'][:70]}")
        if aplicar:
            importacion.aplicar_mapeo(f, propuesta)
            self.stdout.write(self.style.SUCCESS('Mapeo guardado. Revísalo en el panel: Formularios → Revisar mapeo.'))
