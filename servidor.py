"""
Prospectos como SERVIDOR: un solo programa y una sola base de datos para todas las computadoras, celulares y
tabletas, desde cualquier lugar. Es lo que corre dentro de Docker (ver docker-compose.yml y docs/servidor.md).

    python servidor.py                  arranca: prepara la base, tareas automáticas y servidor web
    python lanzador.py <comando>        comandos de siempre (respaldo crear, crear_admin, …)

Variables de entorno:
    PROSPECTOS_URL_PUBLICA      https://prospectos.udcm.mx (la dirección con la que entra todo el mundo)
    PROSPECTOS_ESCUCHAR         dirección:puerto interno (0.0.0.0:8000)
    PROSPECTOS_PROXY_CONFIABLE  IP del proxy con HTTPS (Caddy/Cloudflare) cuyos X-Forwarded-* se creen;
                                '*' solo si el puerto del programa NO está expuesto (red interna de Docker)
    PROSPECTOS_ADMIN_CORREO / PROSPECTOS_ADMIN_CLAVE   primer administrador (solo si no hay usuarios)
    PROSPECTOS_BD_*             base de datos (ver prospectos/servicios/publico.py)
    PROSPECTOS_DATOS            carpeta de datos (config.json con las llaves, respaldos, logo…)
"""

import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


def _esperar_base(intentos: int = 30):
    """En Docker la base puede tardar unos segundos más en arrancar que el programa."""
    import time

    from django.db import connection
    from django.db.utils import OperationalError
    for i in range(intentos):
        try:
            connection.ensure_connection()
            return
        except OperationalError as e:
            if i == intentos - 1:
                raise
            print(f'Esperando la base de datos… ({e.args[-1] if e.args else e})', flush=True)
            time.sleep(2)


def _primer_admin():
    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    if get_user_model().objects.exists():
        return
    correo = os.environ.get('PROSPECTOS_ADMIN_CORREO', '').strip()
    if correo and os.environ.get('PROSPECTOS_ADMIN_CLAVE'):
        call_command('crear_admin', correo=correo, clave_desde_entorno=True)
        print('Administrador creado. Al entrar por primera vez el programa pide cambiar esa contraseña.', flush=True)
    else:
        print('AVISO: no hay usuarios. Crea el administrador con:\n'
              '   docker compose exec app python lanzador.py crear_admin\n'
              'o define PROSPECTOS_ADMIN_CORREO y PROSPECTOS_ADMIN_CLAVE.', flush=True)


def main():
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from waitress import serve

    from config.wsgi import application
    from prospectos.programador import iniciar
    from prospectos.servicios import publico

    print('Prospectos · servidor', flush=True)
    print(f'Datos: {settings.DATA_DIR} · base: {settings.BD["MOTOR"]}', flush=True)
    _esperar_base()
    call_command('preparar')
    _primer_admin()

    escuchar = os.environ.get('PROSPECTOS_ESCUCHAR', '0.0.0.0:8000')
    proxy = os.environ.get('PROSPECTOS_PROXY_CONFIABLE', '').strip() or None
    if settings.URL_PUBLICA and not proxy:
        print('AVISO: hay URL_PUBLICA pero no PROSPECTOS_PROXY_CONFIABLE: el programa no sabrá que la conexión '
              'llegó por HTTPS y no podrán iniciar sesión. Ver docs/servidor.md.', flush=True)
    if not settings.URL_PUBLICA:
        print('AVISO: falta PROSPECTOS_URL_PUBLICA (https://…). Sin ella el servidor solo acepta 127.0.0.1.', flush=True)

    iniciar()
    print(f'Listo: {settings.URL_PUBLICA or "http://" + escuchar}/admin/  (escuchando en {escuchar})', flush=True)
    serve(application, listen=escuchar, threads=int(os.environ.get('PROSPECTOS_HILOS', 16)), ident='Prospectos',
          **publico.waitress_proxy(proxy))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:  # noqa: BLE001
        try:
            from lanzador import _explicar_error_bd
            mensaje = _explicar_error_bd(e)
        except Exception:  # noqa: BLE001
            mensaje = None
        if mensaje:
            print('\n' + mensaje, file=sys.stderr)
            sys.exit(1)
        raise
