"""
¿Está cifrado el disco donde viven los datos? (BitLocker en Windows, FileVault en Mac).

El programa ya cifra correos, teléfonos, CURP y la respuesta completa de cada Form, pero los nombres y las
cifras tienen que quedar legibles para buscar y unir familias, y las llaves están en datos/config.json. Si alguien
se lleva la computadora o el disco, lo único que protege TODO junto es cifrar el disco: eso revisa este módulo.
No necesita permisos de administrador. Si no se puede saber, dice «desconocido» (nunca afirma que sí).
"""

import os
import subprocess
import sys
import time
from pathlib import Path

_CACHE: dict[str, tuple[float, dict]] = {}
VIGENCIA = 3600

# Shell.Application → System.Volume.BitLockerProtection (no requiere administrador)
_PS = ("$v = (New-Object -ComObject Shell.Application).NameSpace('{unidad}').Self.ExtendedProperty("
       "'System.Volume.BitLockerProtection'); if ($v -eq $null) {{ 'x' }} else {{ $v }}")
_BITLOCKER = {'1': 'si', '3': 'si', '6': 'si', '2': 'no', '4': 'no', '5': 'suspendido', '0': 'no'}


def _windows(ruta: Path) -> str:
    unidad = (Path(ruta).resolve().drive or 'C:') + '\\'
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', _PS.format(unidad=unidad)],
                           capture_output=True, text=True, timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError):
        return 'desconocido'
    return _BITLOCKER.get((r.stdout or '').strip(), 'desconocido')


def _mac() -> str:
    try:
        r = subprocess.run(['fdesetup', 'status'], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return 'desconocido'
    salida = r.stdout or ''
    return 'si' if 'FileVault is On' in salida else 'no' if 'FileVault is Off' in salida else 'desconocido'


def estado(ruta: Path, refrescar: bool = False) -> dict:
    clave = str(ruta)
    if not refrescar and clave in _CACHE and time.time() - _CACHE[clave][0] < VIGENCIA:
        return _CACHE[clave][1]
    if os.name == 'nt':
        valor, nombre = _windows(ruta), 'BitLocker'
        como = ('Inicio → «Administrar BitLocker» → Activar BitLocker en la unidad del programa (en Windows Home: '
                'Configuración → Privacidad y seguridad → Cifrado del dispositivo). Guarda la clave de recuperación lejos de la PC.')
    elif sys.platform == 'darwin':
        valor, nombre = _mac(), 'FileVault'
        como = 'Configuración del Sistema → Privacidad y seguridad → FileVault → Activar.'
    else:
        valor, nombre, como = 'desconocido', 'cifrado de disco', 'Usa el cifrado de disco del sistema (LUKS).'
    r = {'estado': valor, 'nombre': nombre, 'como': como}
    _CACHE[clave] = (time.time(), r)
    return r
