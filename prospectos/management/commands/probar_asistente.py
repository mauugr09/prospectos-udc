"""
Evalúa las respuestas del asistente con la IA real: hace preguntas típicas, revisa que cada respuesta cumpla la forma
(cifra en la primera oración, comparación, acción, sin relleno, preguntas de seguimiento) y muestra el costo.

    Prospectos.exe probar_asistente               # todas
    Prospectos.exe probar_asistente --solo 3      # solo la pregunta 3
Necesita el asistente activado (Configuración → Asistente). Cuesta normalmente menos de 0.10 USD en total.
"""

import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from ...servicios import asistente

PREGUNTAS = [
    '¿Cómo vamos este mes?',
    '¿Cuántos aspirantes llegaron a Tultepec en los últimos 30 días y cómo se compara con el mes anterior?',
    '¿Qué carreras piden en cada plantel?',
    '¿Qué canal convierte mejor: WhatsApp o correo?',
    '¿En qué etapa del embudo se nos quedan más aspirantes?',
    '¿Qué es lo más urgente hoy?',
    '¿Qué visitas rindieron más registros por costo?',
    '¿Qué prepas mandan aspirantes que sí avanzan?',
    '¿Cómo uno a una familia con su alumno?',
    '¿Cuántos menores esperan permiso y qué hago con ellos?',
    'Dame el teléfono de la aspirante con más prioridad',
    'Asigna a promotor1@demo.local los 5 listos para inscribirse de Tultepec',
]
RELLENO = re.compile(r'¡claro|excelente pregunta|espero que te sirva|no dudes en|con gusto te ayudo|aquí tienes', re.I)


def calificar(texto: str, r: dict) -> list[str]:
    fallas = []
    primera = re.split(r'(?<=[.!?])\s|\n', texto.strip(), maxsplit=1)[0] if texto else ''
    if not re.search(r'\d', primera) and not r['herramientas'] == ['buscar_ayuda'] and 'proponer' not in ' '.join(r['herramientas']):
        fallas.append('la primera oración no trae una cifra')
    if RELLENO.search(texto):
        fallas.append('tiene frases de relleno')
    if len(texto.split()) > 170:
        fallas.append(f'muy larga ({len(texto.split())} palabras)')
    if not r.get('siguientes'):
        fallas.append('sin preguntas de seguimiento')
    if r['herramientas'] and not any(h in r['herramientas'] for h in ('buscar_ayuda',)) and '](/admin/' not in texto and not r.get('calculos'):
        fallas.append('sin enlace a la lista ni explicación del cálculo')
    if re.search(r'@\w|\d{3}[\s-]?\d{3}[\s-]?\d{4}', texto):
        fallas.append('¡parece incluir un correo o teléfono!')
    return fallas


class Command(BaseCommand):
    help = 'Prueba la calidad de las respuestas del asistente con la IA real.'

    def add_arguments(self, parser):
        parser.add_argument('--solo', type=int, help='Número de pregunta (1 a %d)' % len(PREGUNTAS))
        parser.add_argument('--usuario', default=None, help='Correo del usuario con el que se pregunta (por omisión, el primer administrador)')

    def handle(self, *args, solo=None, usuario=None, **o):
        if not asistente.activo():
            raise CommandError('El asistente no está activado o no tiene llave (Configuración → Asistente).')
        U = get_user_model()
        u = U.objects.filter(username=usuario).first() if usuario else U.objects.filter(is_superuser=True, is_active=True).first()
        if not u:
            raise CommandError('No encontré al usuario.')
        antes = asistente.gasto()['usd']
        aprobadas = 0
        lista = [(solo, PREGUNTAS[solo - 1])] if solo else list(enumerate(PREGUNTAS, 1))
        for n, pregunta in lista:
            self.stdout.write(self.style.MIGRATE_HEADING(f'\n{n}. {pregunta}'))
            try:
                r = asistente.preguntar(u, pregunta, [], {})
            except (asistente.PreguntaRechazada, asistente.AsistenteNoDisponible) as e:
                self.stdout.write(f'   (bloqueada) {e}')
                aprobadas += 1 if 'teléfono' in pregunta else 0
                continue
            self.stdout.write(r['texto'])
            self.stdout.write(self.style.HTTP_INFO(f"   herramientas: {', '.join(r['herramientas']) or 'ninguna'} · "
                                                   f"siguientes: {' | '.join(r.get('siguientes', []))}"))
            for p in r['propuestas']:
                self.stdout.write(f"   propuesta: {asistente.detalle_propuesta(p)['titulo']} (NO se ejecutó)")
            fallas = calificar(r['texto'], r)
            if fallas:
                self.stdout.write(self.style.WARNING('   ✗ ' + '; '.join(fallas)))
            else:
                aprobadas += 1
                self.stdout.write(self.style.SUCCESS('   ✓ cumple la forma'))
        costo = asistente.gasto()['usd'] - antes
        self.stdout.write(self.style.SUCCESS(f'\n{aprobadas} de {len(lista)} cumplen la forma. Costo de la prueba: {costo:.4f} USD.'))
