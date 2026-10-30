"""
Modo «esta computadora se conecta a la principal».

Una sola computadora guarda los datos (la principal). En las demás, el mismo Prospectos.exe puede quedar como acceso
directo: la primera vez pregunta la dirección de la principal, descarga su certificado, muestra un código para
compararlo con el de la principal (Configuración → Otras computadoras), lo instala y guarda «conexion.json».
Desde entonces, abrirlo comprueba que la principal responde y abre el navegador ahí.

No usa Django: corre antes de preparar cualquier base de datos (una computadora conectada no tiene base propia).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ARCHIVO = 'conexion.json'
CERTIFICADO = 'principal.crt'
PUERTO_OMISION = 8443


def _abrir_url(url: str, contexto: ssl.SSLContext, tiempo: float):
    """Directo, sin el proxy de la oficina: la principal está en la red local o la VPN, y un proxy podría ver
    (o interceptar) el tráfico."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=contexto))
    return opener.open(url, timeout=tiempo)


def carpeta_datos() -> Path:
    """Misma regla que config/settings.py (que la usa): junto al .exe en Windows, Application Support en Mac."""
    if os.environ.get('PROSPECTOS_DATOS'):
        return Path(os.environ['PROSPECTOS_DATOS'])
    congelado = bool(getattr(sys, 'frozen', False))
    if congelado and sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'Prospectos UDC'
    if congelado:
        return Path(sys.executable).resolve().parent / 'datos'
    return Path(__file__).resolve().parent.parent.parent / 'datos'


def es_principal(carpeta: Path | None = None) -> bool:
    return ((carpeta or carpeta_datos()) / 'config.json').exists()


def leer(carpeta: Path | None = None) -> dict | None:
    ruta = (carpeta or carpeta_datos()) / ARCHIVO
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
        return datos if datos.get('servidor') else None
    except (OSError, ValueError):
        return None


def normalizar_servidor(texto: str) -> str | None:
    """«10.20.1.15», «pc-admisiones:8443», «https://10.20.1.15:8443/admin/» → «https://10.20.1.15:8443/»."""
    t = (texto or '').strip()
    t = re.sub(r'^[a-zA-Z]+://', '', t).split('/')[0].strip()
    m = re.fullmatch(r'([A-Za-z0-9.-]+)(?::(\d{2,5}))?', t)
    if not m or '..' in m.group(1) or m.group(1).startswith(('.', '-')):
        return None
    puerto = int(m.group(2) or PUERTO_OMISION)
    if not 1 <= puerto <= 65535:
        return None
    return f'https://{m.group(1).lower()}:{puerto}/'


def codigo(pem: bytes) -> str:
    """Igual que red.codigo_ca: primeros 12 caracteres del SHA-256 del certificado (en DER)."""
    der = ssl.PEM_cert_to_DER_cert(pem.decode('ascii'))
    h = hashlib.sha256(der).hexdigest().upper()
    return f'{h[0:4]}-{h[4:8]}-{h[8:12]}'


def descargar_certificado(servidor: str, tiempo: float = 8) -> bytes:
    """Sin verificar (todavía no se confía en nadie): por eso después se compara el código a ojo."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with _abrir_url(servidor + 'conectar/Prospectos-UDC.crt', ctx, tiempo) as r:
        pem = r.read(64 * 1024)
    if b'BEGIN CERTIFICATE' not in pem:
        raise ValueError('La respuesta no es un certificado: ¿es la dirección del programa?')
    return pem


def responde(servidor: str, certificado: Path, tiempo: float = 5) -> tuple[bool, str]:
    """¿La principal contesta, con un certificado firmado por la autoridad que se aceptó? (True, '') o (False, motivo)."""
    try:
        ctx = ssl.create_default_context(cafile=str(certificado))
        try:
            with _abrir_url(servidor + 'salud/', ctx, tiempo) as r:
                texto = r.read(200).decode(errors='replace')
        except urllib.error.URLError as e:  # urllib envuelve el error del certificado
            if isinstance(e.reason, ssl.SSLCertVerificationError):
                raise e.reason from e
            raise
        return (True, '') if texto.startswith('prospectos-ok') else (False, 'contestó otro programa')
    except ssl.SSLCertVerificationError as e:
        if 'hostname' in str(e).lower() or 'match' in str(e).lower():
            return False, ('el certificado de la principal no incluye esta dirección; en la principal escríbela en '
                           'Otras computadoras → «Otro plantel o VPN», o usa otra de las direcciones que muestra')
        return False, 'el certificado de la principal cambió; vuelve a conectar esta computadora (Prospectos.exe conectar)'
    except (urllib.error.URLError, OSError) as e:
        return False, f'no responde ({getattr(e, "reason", e)})'


def instalar_certificado(ruta: Path) -> tuple[bool, str]:
    """Lo agrega a los certificados de confianza DEL USUARIO (no necesita ser administrador)."""
    try:
        if os.name == 'nt':
            r = subprocess.run(['certutil', '-user', '-addstore', 'Root', str(ruta)], capture_output=True, text=True, timeout=180)
        elif sys.platform == 'darwin':
            llavero = Path.home() / 'Library' / 'Keychains' / 'login.keychain-db'
            r = subprocess.run(['security', 'add-trusted-cert', '-r', 'trustRoot', '-k', str(llavero), str(ruta)],
                               capture_output=True, text=True, timeout=180)
        else:
            return False, 'en esta computadora instala el certificado a mano (ver la página conectar/)'
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    return (r.returncode == 0, (r.stdout + r.stderr).strip()[-300:])


def guardar(carpeta: Path, servidor: str, pem: bytes) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / CERTIFICADO).write_bytes(pem)
    (carpeta / ARCHIVO).write_text(json.dumps({'servidor': servidor, 'codigo': codigo(pem),
                                               'conectada_en': time.strftime('%Y-%m-%d %H:%M')}, indent=2), encoding='utf-8')


def configurar(carpeta: Path | None = None, preguntar=input, decir=print) -> str | None:
    """Pregunta la dirección de la principal y la deja lista. Devuelve la dirección o None si se canceló."""
    carpeta = carpeta or carpeta_datos()
    decir('')
    decir('Escribe la dirección de la computadora principal. Está en esa computadora, en')
    decir('Configuración → Otras computadoras (por ejemplo 192.168.1.20 o 10.20.1.15).')
    try:
        return _configurar(carpeta, preguntar, decir)
    except EOFError:
        return None


def _configurar(carpeta: Path, preguntar, decir) -> str | None:
    for _ in range(5):
        texto = preguntar('Dirección (o Enter para cancelar): ').strip()
        if not texto:
            return None
        servidor = normalizar_servidor(texto)
        if not servidor:
            decir('Esa dirección no es válida. Escribe solo la IP o el nombre, por ejemplo 192.168.1.20')
            continue
        decir(f'Conectando con {servidor} …')
        try:
            pem = descargar_certificado(servidor)
        except (urllib.error.URLError, OSError, ValueError) as e:
            decir(f'No se pudo: {getattr(e, "reason", e)}.')
            decir('Revisa que la principal esté encendida, con el programa abierto y el acceso por red ACTIVO,')
            decir('y que esta computadora esté en la misma red (o en la VPN).')
            continue
        decir('')
        decir(f'   Código de la principal:   {codigo(pem)}')
        decir('')
        decir('Compáralo con el que aparece en la principal (Configuración → Otras computadoras).')
        if preguntar('¿Es exactamente el mismo? Escribe S para sí o N para no: ').strip().lower() not in ('s', 'si', 'sí'):
            decir('No se conectó. Si el código es distinto, avisa a quien administra el programa: '
                  'alguien podría estar haciéndose pasar por él.')
            return None
        guardar(carpeta, servidor, pem)
        ok, motivo = responde(servidor, carpeta / CERTIFICADO)
        if not ok:
            decir(f'Aviso: {motivo}.')
        decir('Instalando el certificado (Windows o macOS pueden pedirte que lo confirmes: acepta)…')
        instalado, detalle = instalar_certificado(carpeta / CERTIFICADO)
        if not instalado:
            decir('No se pudo instalar solo el certificado. El navegador mostrará un aviso de seguridad: abre')
            decir(f'{servidor}conectar/ y sigue los pasos para instalarlo a mano.')
        decir('')
        decir('Listo: esta computadora queda conectada a la principal. No guarda datos propios.')
        return servidor
    return None


def abrir(conexion: dict, carpeta: Path | None = None, decir=print, abrir_navegador=None, intentos: int = 12, espera: float = 10) -> bool:
    """Espera a que la principal responda (hasta 2 minutos) y abre el navegador ahí."""
    import webbrowser
    carpeta = carpeta or carpeta_datos()
    servidor = conexion['servidor']
    decir(f'Esta computadora se conecta a la principal: {servidor}')
    for i in range(intentos):
        ok, motivo = responde(servidor, carpeta / CERTIFICADO)
        if ok:
            (abrir_navegador or webbrowser.open)(servidor + 'admin/')
            decir('Abriendo el navegador… (puedes cerrar esta ventana)')
            return True
        if 'certificado' in motivo:
            decir(f'No se puede entrar: {motivo}.')
            return False
        if i == 0:
            decir(f'La principal {motivo}.')
            decir('¿Está encendida, con el programa abierto? Si estás en otro plantel o en casa, ¿estás conectado a la VPN?')
            decir('Reintentando cada 10 segundos (cierra esta ventana para dejar de intentar)…')
        time.sleep(espera)
    decir('La principal sigue sin responder. Pide a quien la administra que la encienda y abra el programa.')
    return False
