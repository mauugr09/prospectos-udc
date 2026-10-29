"""Diagnóstico de la conexión con Google Forms: credenciales, acceso a cada Form, respuestas y mapeo."""

from django.core.management.base import BaseCommand

from ...models import Formulario, Pregunta
from ...servicios.fuentes import ErrorFuente, FuenteGoogle, entries_publicos, modo_google


class Command(BaseCommand):
    help = 'Comprueba credenciales y acceso a los Forms registrados (no importa nada).'

    def handle(self, *args, **o):
        ok = self.style.SUCCESS('OK')
        self.stdout.write(f'Modo de conexión: {modo_google()}')
        fuente = FuenteGoogle()
        try:
            fuente.token()
            self.stdout.write(f'1. Credenciales de Google ........ {ok}')
        except ErrorFuente as e:
            self.stdout.write(self.style.ERROR(f'1. Credenciales de Google ........ FALLA\n   {e}'))
            return
        reales = Formulario.objects.exclude(google_form_id__startswith='demo-')
        if not reales.exists():
            self.stdout.write(self.style.WARNING('2. No hay formularios reales registrados. Usa «registrar_formulario» o el panel.'))
            return
        for f in reales:
            self.stdout.write(f'\n· {f} ({f.get_tipo_display()}) — ID {f.google_form_id}')
            try:
                info = fuente.info(f)
                titulo = (info.get('info') or {}).get('title', '¿sin título?')
                self.stdout.write(f'  Acceso al Form .................. {ok} «{titulo}»')
                n = sum(1 for _ in fuente.respuestas(f, None))
                self.stdout.write(f'  Respuestas en Google ............ {n}')
                preguntas = fuente.estructura(f)
                mapeadas = [q for q in preguntas if q in (f.mapeo_campos or {})]
                codigos = set(Pregunta.objects.filter(cuestionario=f.tipo).values_list('codigo', flat=True))
                from prospectos import catalogos
                faltan = sorted(codigos - set((f.mapeo_campos or {}).values()) - catalogos.RECOMENDADAS)
                estilo = self.style.SUCCESS if not faltan else self.style.WARNING
                self.stdout.write(estilo(f'  Mapeo ........................... {len(mapeadas)}/{len(preguntas)} preguntas del Form'))
                if faltan:
                    self.stdout.write(self.style.WARNING(f'  Códigos sin pregunta: {", ".join(faltan)}'))
                if not f.url_publica:
                    self.stdout.write(self.style.WARNING('  Falta la URL pública: los QR no funcionarán.'))
                prell = f.campos_prellenado or {}
                faltan_p = [c for c in ('evento', 'promotor', 'token_familia') if c not in prell]
                if faltan_p:
                    self.stdout.write(self.style.WARNING(f'  Campos prellenados sin entry.NNNN: {", ".join(faltan_p)}'))
                publicos = set(entries_publicos(f.url_publica).values())
                if not publicos:
                    self.stdout.write(self.style.WARNING('  No se pudo leer la página pública (¿pide iniciar sesión?): '
                                                         'verifica los QR abriendo uno en el celular.'))
                else:
                    malos = [c for c, e in prell.items() if e not in publicos]
                    if malos:
                        self.stdout.write(self.style.ERROR(f'  entry.NNNN que NO existen en el Form: {", ".join(malos)} '
                                                           '→ el QR no llenará esos campos. Usa «Sincronizar con Google».'))
                    elif prell:
                        self.stdout.write(f'  Campos del QR (prellenado) ...... {ok}')
            except ErrorFuente as e:
                self.stdout.write(self.style.ERROR(f'  FALLA: {e}'))
