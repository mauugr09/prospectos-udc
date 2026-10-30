"""
Compartir por internet SIN servidor y SIN dominio: «túnel rápido» de Cloudflare (gratis, sin cuenta).

El programa sigue corriendo en ESTA computadora con su base de datos; cloudflared abre una salida segura hacia
Cloudflare y da un enlace https://<palabras-al-azar>.trycloudflare.com. Con ese enlace se entra desde cualquier
computadora, celular o tableta, en cualquier lugar, con HTTPS real (sin instalar certificados).

Seguridad: la base de datos NO se publica; solo el programa, con su inicio de sesión, bloqueo por intentos,
cierre por inactividad y bitácora. No se abre ningún puerto del módem.

Límites (para presentar el proyecto o probar, no para operar todos los días):
  - El enlace CAMBIA cada vez que se abre el programa (hay que volver a compartirlo; el QR de
    «Otras computadoras» siempre muestra el actual).
  - Funciona solo mientras esta computadora esté encendida y con el programa abierto.
  - Cloudflare lo ofrece para pruebas, sin garantía. Para uso diario: servidor central (docs/servidor.md).
"""

from __future__ import annotations

import atexit
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

# El enlace del túnel son palabras con guiones (seasonal-deck-organisms-sf.trycloudflare.com). Ojo: los mensajes de
# error mencionan https://api.trycloudflare.com, que NO es el enlace.
PATRON_URL = re.compile(r'https://(?!api\.)[a-z0-9]+(?:-[a-z0-9]+)+\.trycloudflare\.com')


class ErrorTunel(RuntimeError):
    pass


def activo(config: dict, entorno: dict | None = None) -> bool:
    entorno = os.environ if entorno is None else entorno
    return bool(config.get('COMPARTIR_EN_INTERNET')) or entorno.get('PROSPECTOS_COMPARTIR') == '1'


def buscar_cloudflared(data_dir: Path | None = None) -> str | None:
    """cloudflared en el PATH, en la carpeta de datos o donde lo dejan los instaladores de Windows y Mac."""
    if os.environ.get('PROSPECTOS_CLOUDFLARED'):
        return os.environ['PROSPECTOS_CLOUDFLARED']
    encontrado = shutil.which('cloudflared')
    if encontrado:
        return encontrado
    candidatos = []
    if data_dir:
        candidatos += [Path(data_dir) / 'cloudflared.exe', Path(data_dir) / 'cloudflared']
    candidatos += [Path(r'C:\Program Files (x86)\cloudflared\cloudflared.exe'), Path(r'C:\Program Files\cloudflared\cloudflared.exe'),
                   Path('/opt/homebrew/bin/cloudflared'), Path('/usr/local/bin/cloudflared')]
    local = os.environ.get('LOCALAPPDATA')
    if local:  # winget sin permisos de administrador
        candidatos += list(Path(local, 'Microsoft', 'WinGet', 'Packages').glob('Cloudflare.cloudflared*/cloudflared.exe'))
    for c in candidatos:
        if c.is_file():
            return str(c)
    return None


def como_instalar() -> str:
    if sys.platform == 'darwin':
        return 'En Terminal: brew install cloudflared   (o descarga «cloudflared-darwin-arm64.tgz» de github.com/cloudflare/cloudflared/releases)'
    if os.name == 'nt':
        return ('En PowerShell: winget install --id Cloudflare.cloudflared   y abre una ventana nueva de PowerShell. '
                '(O descarga «cloudflared-windows-amd64.exe» de github.com/cloudflare/cloudflared/releases, renómbralo '
                'cloudflared.exe y ponlo en la carpeta «datos».)')
    return 'Instala cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/'


def abrir(puerto: int, data_dir: Path | None = None, espera: float = 60.0, bitacora: Path | None = None) -> tuple[str, subprocess.Popen]:
    """Arranca el túnel hacia http://127.0.0.1:<puerto> y devuelve (enlace público, proceso).
    El proceso se cierra solo al salir del programa."""
    exe = buscar_cloudflared(data_dir)
    if not exe:
        raise ErrorTunel('No está instalado cloudflared. ' + como_instalar())
    opciones = {}
    if os.name == 'nt':  # que no abra otra ventana negra
        opciones['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    proc = subprocess.Popen([exe, 'tunnel', '--no-autoupdate', '--url', f'http://127.0.0.1:{puerto}'],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                            errors='replace', bufsize=1, **opciones)
    atexit.register(cerrar, proc)

    hallado: dict[str, str] = {}
    listo = threading.Event()
    lineas: list[str] = []

    def leer():  # se sigue leyendo siempre: si nadie lee, cloudflared se traba al llenar la tubería
        archivo = open(bitacora, 'a', encoding='utf-8') if bitacora else None
        try:
            for linea in proc.stdout:
                lineas.append(linea.rstrip())
                del lineas[:-30]
                if archivo:
                    archivo.write(linea)
                    archivo.flush()
                if 'url' not in hallado:
                    m = PATRON_URL.search(linea)
                    if m:
                        hallado['url'] = m.group(0)
                        listo.set()
        finally:
            listo.set()
            if archivo:
                archivo.close()

    threading.Thread(target=leer, name='tunel-cloudflared', daemon=True).start()
    limite = time.monotonic() + espera
    while time.monotonic() < limite and not listo.is_set():
        listo.wait(0.5)
        if proc.poll() is not None and 'url' not in hallado:  # cloudflared ya terminó (sin internet, bloqueado…)
            time.sleep(0.3)  # deja leer sus últimas líneas
            break
    if 'url' not in hallado:
        cerrar(proc)
        detalle = ' | '.join(lineas[-5:]) or 'sin respuesta'
        raise ErrorTunel('Cloudflare no dio un enlace (¿hay internet? ¿la red de la escuela bloquea Cloudflare?). '
                         f'Detalle: {detalle}')
    return hallado['url'], proc


def cerrar(proc: subprocess.Popen) -> None:
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()


def aplicar_a_django(settings, url: str) -> None:
    """Pone en marcha la dirección pública DESPUÉS de cargar la configuración (el enlace se conoce al arrancar).
    Debe llamarse antes de importar config.wsgi (los middlewares leen algunos ajustes al crearse)."""
    from . import publico
    url = publico.normalizar(url)
    ajustes = publico.ajustes_django(url)
    for host in ajustes.pop('ALLOWED_HOSTS'):
        if host not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS.append(host)
    origenes = list(getattr(settings, 'CSRF_TRUSTED_ORIGINS', []) or [])
    for o in ajustes.pop('CSRF_TRUSTED_ORIGINS'):
        if o not in origenes:
            origenes.append(o)
    settings.CSRF_TRUSTED_ORIGINS = origenes
    for clave, valor in ajustes.items():
        setattr(settings, clave, valor)
    settings.URL_PUBLICA = url
    settings.TUNEL_RAPIDO = True
