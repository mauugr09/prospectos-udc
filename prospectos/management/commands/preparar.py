from django.core.management import call_command
from django.core.management.base import BaseCommand

from ...servicios import semillas


def _respaldar_antes_de_actualizar(salida) -> None:
    """
    Si esta versión trae cambios a la base (migraciones pendientes) y ya hay datos, guarda una copia
    ANTES de tocarla. Si la actualización sale mal, se restaura con «respaldo restaurar <archivo>».
    """
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    try:
        tablas = connection.introspection.table_names()
    except Exception:  # noqa: BLE001 - base nueva o inaccesible: migrate dará el error claro
        return
    if 'prospectos_prospecto' not in tablas or connection.in_atomic_block:
        return  # instalación nueva (o dentro de una transacción, donde SQLite no puede copiarse)
    plan = MigrationExecutor(connection).migration_plan(MigrationExecutor(connection).loader.graph.leaf_nodes())
    if not plan:
        return
    import gzip
    import shutil
    import sqlite3
    from pathlib import Path

    from django.utils import timezone

    from ...servicios import respaldos
    if respaldos.es_mariadb():
        destino = respaldos.directorio() / f'prospectos-antes-de-actualizar-{timezone.localtime():%Y%m%d-%H%M%S}.sql.gz'
        respaldos._crear_mariadb(destino)
    else:
        destino = respaldos.directorio() / f'prospectos-antes-de-actualizar-{timezone.localtime():%Y%m%d-%H%M%S}.sqlite3.gz'
        tmp = Path(str(destino).removesuffix('.gz'))
        connection.ensure_connection()
        copia = sqlite3.connect(tmp)
        with copia:
            connection.connection.backup(copia)
        copia.close()
        with open(tmp, 'rb') as fin, gzip.open(destino, 'wb', compresslevel=6) as fout:
            shutil.copyfileobj(fin, fout, 1 << 20)
        tmp.unlink(missing_ok=True)
    salida.write(f'Actualización: {len(plan)} cambios a la base. Copia previa: {destino.name}')


class Command(BaseCommand):
    help = 'Crea/actualiza tablas, preguntas, carreras y roles. Seguro de repetir. Respalda antes de actualizar.'

    def handle(self, *args, **o):
        _respaldar_antes_de_actualizar(self.stdout)
        call_command('migrate', verbosity=0, interactive=False)
        semillas.preparar()
        self.stdout.write(self.style.SUCCESS('Base de datos lista.'))
