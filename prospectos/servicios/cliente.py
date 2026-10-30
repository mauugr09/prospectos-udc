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
PUERTO_DESCUBRIR = 8444
PREGUNTA = b'PROSPECTOS-UDC?'
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


def buscar(tiempo: float = 2.5, destinos: tuple = ('255.255.255.255',), puerto: int = PUERTO_DESCUBRIR) -> list[dict]:
    """Pregunta en la red local «¿hay una principal?». Solo encuentra las de la misma red (no a través de una VPN).
    Lo que contesta NO se cree: el código se vuelve a calcular del certificado descargado y la persona lo compara."""
    import socket
    encontradas: dict[str, dict] = {}
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.settimeout(0.3)
            for d in destinos:
                try:
                    s.sendto(PREGUNTA, (d, puerto))
                except OSError:
                    pass
            fin = time.time() + tiempo
            while time.time() < fin:
                try:
                    datos, (ip, _) = s.recvfrom(4096)
                except socket.timeout:
                    continue
                try:
                    r = json.loads(datos.decode('utf-8'))
                    servidor = normalizar_servidor(f"{ip}:{int(r.get('puerto', PUERTO_OMISION))}")
                except (ValueError, TypeError):
                    continue
                if servidor and r.get('programa') == 'prospectos-udc':
                    encontradas.setdefault(servidor, {'servidor': servidor, 'equipo': str(r.get('equipo', ''))[:40],
                                                      'codigo': str(r.get('codigo', ''))[:20]})
    except OSError:
        return []
    return list(encontradas.values())


def configurar(carpeta: Path | None = None, preguntar=input, decir=print, buscar_fn=None) -> str | None:
    """Busca la principal en la red (o pide su dirección) y la deja lista. Devuelve la dirección o None si se canceló."""
    carpeta = carpeta or carpeta_datos()
    try:
        return _configurar(carpeta, preguntar, decir, buscar_fn or buscar)
    except EOFError:
        return None


def _elegir(candidatas: list[dict], preguntar, decir) -> str | None:
    decir('')
    if len(candidatas) == 1:
        c = candidatas[0]
        decir(f"Encontré la principal: {c['equipo'] or 'sin nombre'} ({c['servidor']})")
        r = preguntar('¿Conectarme a ella? Enter = sí, o escribe otra dirección: ').strip()
        return c['servidor'] if not r or r.lower() in ('s', 'si', 'sí') else r
    decir('Encontré varias principales en esta red (¿una de pruebas?):')
    for i, c in enumerate(candidatas, 1):
        decir(f"  [{i}] {c['equipo'] or 'sin nombre'}  {c['servidor']}")
    r = preguntar('Escribe el número, o una dirección: ').strip()
    return candidatas[int(r) - 1]['servidor'] if r.isdigit() and 1 <= int(r) <= len(candidatas) else r


def _configurar(carpeta: Path, preguntar, decir, buscar_fn) -> str | None:
    decir('')
    decir('Buscando la computadora principal en esta red…')
    candidatas = buscar_fn()
    propuesta = _elegir(candidatas, preguntar, decir) if candidatas else None
    if not candidatas:
        decir('No la encontré en esta red (si estás en otro plantel o en la VPN es normal).')
    if propuesta is None or not candidatas:
        decir('Escribe su dirección: está en la principal, en Configuración → Otras computadoras')
        decir('(por ejemplo 192.168.1.20 o 10.20.1.15).')
    for _ in range(5):
        if propuesta:
            texto, propuesta = propuesta, None
        else:
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
