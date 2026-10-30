"""
Punto de entrada del programa: Prospectos.exe en Windows, Prospectos.app en Mac (y `python lanzador.py` en desarrollo).

Sin argumentos: prepara la base, arranca el servidor en esta computadora y abre el navegador.
Con argumentos: ejecuta un comando de administración, p. ej.
    Prospectos.exe respaldo crear                                       (Windows)
    /Applications/Prospectos.app/Contents/MacOS/Prospectos crear_admin  (Mac, en Terminal)
"""

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


def _escuchando(puerto: int) -> str | None:
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{puerto}/salud/', timeout=1.5) as r:
            return r.read().decode()
    except Exception:  # noqa: BLE001
        return None


def _puerto_libre(preferido: int) -> int:
    for p in [preferido, *range(preferido + 1, preferido + 20)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    raise SystemExit('No hay un puerto libre entre %d y %d.' % (preferido, preferido + 19))


def _no_dormir():
    """Mientras el programa está abierto, la computadora no se duerme sola (si no, se detienen la importación,
    los respaldos y el acceso de las demás computadoras). La pantalla sí puede apagarse."""
    import subprocess
    try:
        if sys.platform == 'darwin':
            # caffeinate termina solo cuando este proceso termina (-w).
            subprocess.Popen(['/usr/bin/caffeinate', '-i', '-s', '-w', str(os.getpid())],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif os.name == 'nt':
            import ctypes
            ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    except Exception:  # noqa: BLE001 - si no se puede, solo se pierde esta comodidad
        pass


def _carpeta_sincronizada(ruta: str) -> str | None:
    """OneDrive, iCloud, Dropbox o Google Drive pueden dañar la base si sincronizan con el programa abierto."""
    for marca, nombre in (('OneDrive', 'OneDrive'), ('Mobile Documents', 'iCloud Drive'), ('CloudStorage', 'una carpeta en la nube'),
                          ('Dropbox', 'Dropbox'), ('Google Drive', 'Google Drive')):
        if marca in ruta:
            return nombre
    return None


def _primera_vez():
    from django.contrib.auth import get_user_model
    from django.core.management import call_command

    if get_user_model().objects.exists():
        return
    print()
    print('=' * 70)
    print(' PRIMERA VEZ: crea el usuario ADMINISTRADOR.')
    print(' (Para capacitar sin datos reales usa OTRA carpeta: Prospectos.exe demo)')
    print('=' * 70)
    call_command('crear_admin')


def _pausa():
    if getattr(sys, 'frozen', False):
        try:
            input('\nPresiona Enter para cerrar…')
        except EOFError:
            pass


def _modo_conectado() -> bool:
    """Antes de Django: si esta computadora se conecta a la principal, solo abre el navegador allá. True si se encargó."""
    from prospectos.servicios import cliente
    pide_conectar = len(sys.argv) > 1 and sys.argv[1] == 'conectar'
    if len(sys.argv) > 1 and not pide_conectar:
        return False
    if cliente.es_principal():
        if pide_conectar:
            print('Esta computadora es la PRINCIPAL (guarda los datos en la carpeta «datos»): no se puede conectar a otra.')
            return True
        return False
    conexion = None if pide_conectar else cliente.leer()
    if conexion is None:
        if not pide_conectar:
            if not getattr(sys, 'frozen', False) and not (sys.stdin and sys.stdin.isatty()):
                return False  # desarrollo o pruebas automáticas: principal
            print()
            print('=' * 70)
            print(' PRIMERA VEZ EN ESTA COMPUTADORA. ¿Cuál es su papel?')
            print('  [P] PRINCIPAL: aquí se guardan los datos (solo UNA computadora de la oficina)')
            print('  [C] CONECTARME a la principal: ver los mismos datos, usuarios y perfiles')
            print('=' * 70)
            opcion = ''
            try:
                while opcion not in ('p', 'c'):
                    opcion = input('Elige P o C y presiona Enter: ').strip().lower()
            except EOFError:  # sin teclado (p. ej. un servicio): principal
                return False
            if opcion == 'p':
                return False
        servidor = cliente.configurar()
        if not servidor:
            _pausa()
            return True
        conexion = cliente.leer()
    if not cliente.abrir(conexion):
        _pausa()
    else:
        time.sleep(3)
    return True


def main():
    import django

    for flujo in (sys.stdout, sys.stderr):
        try:  # acentos correctos aunque la salida se redirija a un archivo
            flujo.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        except (AttributeError, ValueError):
            pass
    if _modo_conectado():
        return

    django.setup()
    from django.conf import settings
    from django.core.management import call_command

    if len(sys.argv) > 1:
        import io
        call_command('preparar', stdout=io.StringIO())
        if sys.argv[1] != 'preparar':
            call_command(*sys.argv[1:])
        else:
            print('Base de datos lista.')
        return

    print('Prospectos · Admisiones')
    print(f'Datos: {settings.DATA_DIR}')
    from prospectos.views import huella
    preferido = int(settings.CONFIG.get('PUERTO', 8000))
    for p in range(preferido, preferido + 20):
        if _escuchando(p) == f'prospectos-ok:{huella()}':
            print('Este programa ya está abierto; abriendo el navegador…')
            webbrowser.open(f'http://127.0.0.1:{p}/admin/')
            time.sleep(2)
            return

    nube = _carpeta_sincronizada(str(settings.DATA_DIR))
    if nube:
        donde = 'C:\\Prospectos' if os.name == 'nt' else 'la carpeta Aplicaciones'
        print(f'AVISO: la carpeta de datos está dentro de {nube}. La base de datos puede dañarse si se sincroniza '
              f'mientras el programa está abierto. Mueve el programa a {donde}.')

    print('Preparando la base de datos…')
    call_command('preparar')
    _primera_vez()

    from waitress import serve

    from config.wsgi import application
    from prospectos.programador import iniciar

    iniciar()
    _no_dormir()
    puerto = _puerto_libre(preferido)
    url = f'http://127.0.0.1:{puerto}/admin/'
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print()
    print(f'Listo: {url}')
    if settings.EN_RED:
        _iniciar_red(application, settings)
    print('Deja esta ventana abierta mientras usas el sistema (aquí corren la importación y los respaldos).')
    print('Para detenerlo, cierra esta ventana o presiona Ctrl+C.')
    print(f'IMPORTANTE: guarda una copia de {settings.CONFIG_FILE} fuera de esta computadora '
          '(sin sus llaves los datos cifrados se pierden).')
    # En esta computadora siempre por HTTP local: no sale de la máquina.
    serve(application, host='127.0.0.1', port=puerto, threads=8, ident='Prospectos', _quiet=True)


def _iniciar_red(application, settings):
    """HTTPS para las demás computadoras de la red (Windows o Mac, con el navegador)."""
    from prospectos.servicios import red
    try:
        srv = red.servidor_https(application, settings.DATA_DIR, settings.CONFIG)
        srv.prepare()
    except Exception as e:  # noqa: BLE001 - sin red el programa debe seguir funcionando en esta computadora
        import logging
        logging.getLogger('prospectos').exception('acceso por red')
        print(f'AVISO: no se pudo abrir el acceso por red en el puerto {red.puerto(settings.CONFIG)} '
              f'({type(e).__name__}: {e}). Las demás computadoras no podrán entrar; en esta sí funciona.')
        return
    threading.Thread(target=srv.serve, name='https-red', daemon=True).start()
    dirs = red.direcciones(settings.CONFIG)
    if not dirs:
        print('AVISO: esta computadora no tiene red local en este momento; el acceso por red queda listo para cuando la tenga.')
        return
    print('Desde otras computadoras de la red (Windows o Mac), con el navegador:')
    for d in dirs:
        print(f'   {d}')
    print(f'   La primera vez, en cada computadora: {dirs[0]}conectar/  (instalar el certificado)')
    print(f'   Código de esta computadora (para comparar al conectar otra): {red.codigo_ca(settings.DATA_DIR)}')


def _config():
    try:
        from django.conf import settings
        return settings.CONFIG_FILE
    except Exception:  # noqa: BLE001 - la configuración misma falló
        from pathlib import Path
        return Path('datos') / 'config.json'


def _explicar_error_bd(e) -> str | None:
    texto = str(e)
    if 'MariaDB' in texto and 'required' in texto:
        return ('La versión de MariaDB es demasiado vieja. Este sistema necesita MariaDB 10.11 o mayor '
                '(10.3 y 10.4 ya no tienen soporte de seguridad). Actualiza el servidor o quita BASE_DATOS '
                f'de {_config()} para seguir usando SQLite.\nDetalle: ' + texto)
    if any(x in texto for x in ("Can't connect", 'Connection refused', '2003', 'timed out')):
        return ('No se pudo conectar a MariaDB. Revisa que el servicio esté encendido y HOST/PUERTO en '
                f'{_config()} → BASE_DATOS.\nDetalle: ' + texto)
    if 'Access denied' in texto or '1045' in texto:
        return f'MariaDB rechazó el usuario o la contraseña de {_config()} → BASE_DATOS.\nDetalle: ' + texto
    if 'Unknown database' in texto or '1049' in texto:
        return 'No existe la base de datos indicada en BASE_DATOS.NOMBRE. Créala primero (ver docs\\mariadb.md).\nDetalle: ' + texto
    return None


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        from django.core.management.base import CommandError
        mensaje = _explicar_error_bd(e)
        if isinstance(e, CommandError):
            print(f'\nError: {e}')
        elif mensaje:
            print('\n' + mensaje)
        else:
            import traceback
            traceback.print_exc()
            print(f'\nOcurrió un error (detalle arriba y en {_config().parent / "prospectos.log"}).')
        if getattr(sys, 'frozen', False) and len(sys.argv) == 1:  # doble clic: que no se cierre sin leer
            try:
                input('\nPresiona Enter para cerrar…')
            except EOFError:
                pass
        sys.exit(1)
