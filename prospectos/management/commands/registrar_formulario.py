"""Registra un Google Form real a partir de su URL de edición y arma el mapeo automáticamente."""

from django.core.management.base import BaseCommand, CommandError

from ...models import Cuestionario, Formulario
from ...servicios import importacion
from ...servicios.fuentes import ErrorFuente


class Command(BaseCommand):
    help = 'registrar_formulario alumno|tutor <URL de edición del Form> [--nombre "..."]'

    def add_arguments(self, parser):
        parser.add_argument('tipo', choices=['alumno', 'tutor'])
        parser.add_argument('url')
        parser.add_argument('--nombre')

    def handle(self, *args, tipo, url, nombre=None, **o):
        if '/forms/d/e/' in url:
            raise CommandError('Esa es la URL PÚBLICA (…/forms/d/e/…/viewform). Usa la de EDICIÓN: …/forms/d/<ID>/edit')
        fid = Formulario.extraer_id(url)
        f = Formulario.objects.filter(google_form_id=fid).first() or Formulario(google_form_id=fid)
        f.tipo = Cuestionario.ALUMNO if tipo == 'alumno' else Cuestionario.TUTOR
        f.nombre = nombre or f.nombre or f'Cuestionario {tipo}'
        f.save()
        try:
            r = importacion.sincronizar(f)
        except ErrorFuente as e:
            raise CommandError(f'No se pudo leer el Form: {e}') from e
        if r['titulo'] and not nombre:
            f.nombre = r['titulo']
            f.save()
        self.stdout.write(self.style.SUCCESS(f'Registrado: {f} (ID {f.google_form_id})'))
        self.stdout.write(f"Preguntas del Form: {r['preguntas']} · mapeadas: {r['mapeadas']}")
        if r['faltan']:
            self.stdout.write(self.style.WARNING('Sin pregunta en el Form: ' + ', '.join(r['faltan'])))
        self.stdout.write(f'URL pública: {f.url_publica or "— (agrégala en el panel)"}')
        self.stdout.write(f'Campos prellenados: {f.campos_prellenado}')
        self.stdout.write('Revisa el mapeo en el panel (Formularios → Revisar mapeo) antes de importar.')
