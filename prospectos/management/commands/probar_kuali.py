"""
Muestra cómo entiende Kuali una lista de preguntas (y su respuesta). Sirve para enseñarle formas nuevas de preguntar.

    Prospectos.exe probar_kuali                       # las preguntas de ejemplo
    Prospectos.exe probar_kuali "¿y en tultepec?"     # una pregunta propia
    Prospectos.exe probar_kuali --archivo preguntas.txt --breve
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from ...servicios import kuali

PREGUNTAS = [
    'hola', '¿qué puedes hacer?', '¿Cómo vamos este mes?', '¿y en Tultepec?', '¿Cuántos aspirantes llegaron en septiembre por carrera?',
    '¿Qué carreras piden en cada plantel?', '¿Qué canal convierte mejor?', '¿Qué prepas convierten mejor?',
    '¿En qué etapa del embudo se nos quedan más?', '¿Qué es lo más urgente hoy?', '¿Qué visitas tenemos los próximos días?',
    '¿Qué visitas rindieron más registros por costo?', '¿Cuántos menores esperan permiso?', '¿Cómo vamos mes a mes?',
    '¿Cuántos inscritos llevamos este año?', '¿Cómo uno a una familia con su alumno?', '¿Qué significa esperando permiso?',
    'asigna 5 listos de Tultepec a promotor1@demo.local', 'agrega el open house al calendario el 21 de noviembre a las 10',
    'qué opinas del clima',
]


class Command(BaseCommand):
    help = 'Muestra cómo entiende Kuali una lista de preguntas.'

    def add_arguments(self, parser):
        parser.add_argument('preguntas', nargs='*')
        parser.add_argument('--archivo', help='Un archivo de texto con una pregunta por renglón')
        parser.add_argument('--breve', action='store_true', help='Solo lo que entendió, sin la respuesta')

    def handle(self, *args, preguntas=None, archivo=None, breve=False, **o):
        u = get_user_model().objects.filter(is_superuser=True, is_active=True).first()
        if not u:
            raise CommandError('Hace falta un usuario administrador.')
        if archivo:
            with open(archivo, encoding='utf-8') as f:
                preguntas = [x.strip() for x in f if x.strip()]
        memoria, no = {}, 0
        for pregunta in preguntas or PREGUNTAS:
            r = kuali.responder(u, pregunta, memoria, {})
            memoria = r['memoria']
            no += r['intencion'] == 'no_entendi'
            self.stdout.write(self.style.MIGRATE_HEADING(f'\n» {pregunta}'))
            self.stdout.write(self.style.HTTP_INFO(f"  intención: {r['intencion']}   entendí: {r['entendi'] or '—'}"))
            if not breve:
                self.stdout.write('  ' + r['texto'].replace('\n', '\n  '))
                if r['siguientes']:
                    self.stdout.write(self.style.HTTP_INFO('  siguientes: ' + ' | '.join(r['siguientes'])))
        total = len(preguntas or PREGUNTAS)
        self.stdout.write(self.style.SUCCESS(f'\nEntendió {total - no} de {total}.'))
