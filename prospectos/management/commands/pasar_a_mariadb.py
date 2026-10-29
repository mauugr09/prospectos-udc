"""Copia TODOS los datos de la base SQLite (datos/prospectos.sqlite3) a MariaDB."""

import io
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from ...servicios import auditoria, semillas

MODELOS = ['auth.group', 'auth.user', 'prospectos']


class Command(BaseCommand):
    help = 'Copia los datos de SQLite a la base MariaDB configurada en config.json (BASE_DATOS). Borra lo que haya en MariaDB.'

    def add_arguments(self, parser):
        parser.add_argument('--si', action='store_true', help='No pedir confirmación')

    def handle(self, *args, si=False, **o):
        if not settings.ES_MARIADB:
            raise CommandError('Primero configura BASE_DATOS con "MOTOR": "mariadb" en datos/config.json.')
        if 'sqlite' not in settings.DATABASES:
            raise CommandError(f'No existe {settings.DATA_DIR / "prospectos.sqlite3"}: no hay nada que copiar.')
        connections['default'].ensure_connection()
        destino = settings.DATABASES['default']
        if not si and input(f"Se BORRARÁ todo lo que haya en la base MariaDB «{destino['NAME']}» y se copiarán los datos de SQLite. "
                            'Escribe COPIAR para continuar: ') != 'COPIAR':
            raise CommandError('Cancelado.')

        self.stdout.write('1/4 Preparando tablas en MariaDB…')
        call_command('migrate', database='default', interactive=False, verbosity=0)
        call_command('migrate', database='sqlite', interactive=False, verbosity=0)
        self.stdout.write('2/4 Leyendo SQLite…')
        with tempfile.TemporaryDirectory() as d:
            volcado = Path(d) / 'volcado.json'
            # UTF-8 explícito: en Windows, --output escribiría en cp1252 y loaddata (UTF-8) fallaría con acentos.
            with open(volcado, 'w', encoding='utf-8') as salida_json:
                call_command('dumpdata', *MODELOS, database='sqlite', natural_foreign=True, natural_primary=True,
                             indent=None, stdout=salida_json, verbosity=0)
            self.stdout.write('3/4 Vaciando MariaDB y cargando…')
            call_command('flush', database='default', interactive=False, verbosity=0)
            call_command('loaddata', str(volcado), database='default', verbosity=0)
        semillas.preparar()
        self.stdout.write('4/4 Comprobando…')
        from ...models import Prospecto, Respuesta
        origen = (Prospecto.objects.using('sqlite').count(), Respuesta.objects.using('sqlite').count())
        copia = (Prospecto.objects.using('default').count(), Respuesta.objects.using('default').count())
        if origen != copia:
            raise CommandError(f'Los conteos no coinciden (SQLite {origen} vs MariaDB {copia}). Revisa el log.')
        auditoria.registrar('pasar_a_mariadb', None, {'prospectos': copia[0], 'respuestas': copia[1]})
        salida = io.StringIO()
        self.stdout.write(self.style.SUCCESS(f'Listo: {copia[0]} prospectos y {copia[1]} respuestas copiados a MariaDB.'))
        self.stdout.write('El archivo SQLite se conserva intacto como respaldo. Ya puedes abrir el programa normalmente.')
        del salida
