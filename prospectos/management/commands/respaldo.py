from django.core.management.base import BaseCommand, CommandError

from ...servicios import auditoria, respaldos


class Command(BaseCommand):
    help = 'Respaldos: crear | verificar [archivo] | restaurar <archivo> | listar'

    def add_arguments(self, parser):
        parser.add_argument('accion', choices=['crear', 'verificar', 'restaurar', 'listar'])
        parser.add_argument('archivo', nargs='?')
        parser.add_argument('--si', action='store_true', help='No pedir confirmación al restaurar')

    def handle(self, *args, accion, archivo=None, si=False, **o):
        try:
            if accion == 'crear':
                r = respaldos.crear()
                self.stdout.write(f'{r.archivo}: {r.estado} {r.mensaje}')
                self.stdout.write(f'Rotados: {respaldos.rotar()}')
            elif accion == 'listar':
                for f in respaldos.archivos():
                    self.stdout.write(f'{f.name}  {f.stat().st_size / 1_048_576:.1f} MB')
            elif accion == 'verificar':
                c = respaldos.verificar(archivo)
                self.stdout.write(self.style.SUCCESS('Respaldo íntegro: ' + ', '.join(f'{k}={v}' for k, v in c.items())))
            else:
                if not archivo:
                    raise CommandError('Indica el archivo a restaurar (usa «respaldo listar»).')
                ruta = respaldos.resolver(archivo)
                from django.conf import settings
                from urllib.request import urlopen
                from prospectos.views import huella
                for puerto in range(int(settings.CONFIG.get('PUERTO', 8000)), int(settings.CONFIG.get('PUERTO', 8000)) + 20):
                    try:
                        with urlopen(f'http://127.0.0.1:{puerto}/salud/', timeout=1) as r:
                            if r.read().decode() == f'prospectos-ok:{huella()}':
                                raise CommandError('El programa está abierto. Ciérralo (cierra su ventana) y vuelve a ejecutar la restauración.')
                    except OSError:
                        pass
                if not si and input(f'Esto REEMPLAZA la base actual con {ruta.name}. Escribe RESTAURAR para continuar: ') != 'RESTAURAR':
                    raise CommandError('Cancelado.')
                previo = respaldos.crear()
                self.stdout.write(f'Respaldo previo: {previo.archivo} ({previo.estado})')
                if previo.estado != 'ok':
                    raise CommandError('No se pudo crear el respaldo previo; no se restaura.')
                respaldos.restaurar(str(ruta))
                auditoria.registrar('respaldo_restaurar', None, {'archivo': ruta.name, 'previo': previo.archivo})
                self.stdout.write(self.style.SUCCESS('Restaurado. Reinicia el programa.'))
        except respaldos.ErrorRespaldo as e:
            raise CommandError(str(e)) from e
