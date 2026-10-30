"""
Abrir el programa solo al iniciar sesión en la computadora principal, para que las demás no se queden sin servicio
después de un reinicio (Windows Update, un apagón).

- Windows: un archivo «Prospectos.cmd» en la carpeta Inicio del usuario (shell:startup). Arranca minimizado.
- macOS: un LaunchAgent en ~/Library/LaunchAgents.
Solo funciona con el programa empaquetado (Prospectos.exe / Prospectos.app). Ojo: arranca al INICIAR SESIÓN, no al
encender: si la computadora se queda en la pantalla de contraseña, el programa no abre.
"""

import os
import sys
from pathlib import Path

ETIQUETA_MAC = 'mx.udc.prospectos'


def disponible() -> bool:
    return bool(getattr(sys, 'frozen', False)) and (os.name == 'nt' or sys.platform == 'darwin')


def _ruta() -> Path | None:
    if os.name == 'nt':
        base = os.environ.get('APPDATA')
        return Path(base) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup' / 'Prospectos.cmd' if base else None
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'LaunchAgents' / f'{ETIQUETA_MAC}.plist'
    return None


def activo() -> bool:
    r = _ruta()
    return bool(r and r.exists())


def activar(ejecutable: str | None = None) -> Path:
    r = _ruta()
    if not r:
        raise OSError('Esta computadora no permite abrir el programa al iniciar sesión.')
    exe = ejecutable or sys.executable
    r.parent.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        carpeta = str(Path(exe).parent)
        r.write_text(f'@echo off\r\ncd /d "{carpeta}"\r\nstart "Prospectos" /min "{exe}"\r\n', encoding='utf-8')
    else:
        from xml.sax.saxutils import escape
        r.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0"><dict>'
            f'<key>Label</key><string>{ETIQUETA_MAC}</string>'
            f'<key>ProgramArguments</key><array><string>{escape(exe)}</string></array>'
            '<key>RunAtLoad</key><true/></dict></plist>\n', encoding='utf-8')
    return r


def desactivar() -> None:
    r = _ruta()
    if r and r.exists():
        r.unlink()
