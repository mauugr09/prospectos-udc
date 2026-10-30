"""
Un solo Prospectos para todos, desde cualquier lugar: el programa corre en UN servidor con UNA base de datos
y cada computadora, celular o tableta entra por una dirección pública con HTTPS real
(por ejemplo https://prospectos.udcm.mx). Ver docs/servidor.md.

Tres formas de tenerlo, el mismo código:
  1. Servidor en la nube o de la universidad: Docker (app + MariaDB + Caddy, que saca el certificado solo).
  2. Una PC de la oficina siempre encendida + Cloudflare Tunnel (sin abrir puertos del router).
  3. En las demás computadoras, Prospectos.exe → «C · Conectarme» con la dirección https://… solo abre el
     servidor central (servicios/cliente.py): no crea una base propia, así no hay datos separados.

Este módulo no usa Django (se llama desde config/settings.py antes de que Django arranque).
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit


class ErrorConfiguracion(ValueError):
    pass


def _limpiar(url: str | None) -> str | None:
    url = (url or '').strip().rstrip('/')
    return url or None


def normalizar(url: str | None, que: str = 'URL_PUBLICA') -> str | None:
    """'https://prospectos.udcm.mx/' → 'https://prospectos.udcm.mx'. Solo HTTPS: por internet, sin HTTPS las
    contraseñas y los datos de los aspirantes viajarían legibles."""
    url = _limpiar(url)
    if not url:
        return None
    partes = urlsplit(url)
    if partes.scheme != 'https' or not partes.hostname:
        raise ErrorConfiguracion(f'{que} debe empezar con https:// y llevar un dominio (por ejemplo https://prospectos.udcm.mx). '
                                 f'Se recibió: {url!r}')
    if partes.path not in ('', '/') or partes.query or partes.fragment:
        raise ErrorConfiguracion(f'{que} es solo el dominio, sin rutas (https://prospectos.udcm.mx, no …/admin/). Se recibió: {url!r}')
    return f'https://{partes.netloc.lower()}'


def url_publica(config: dict, entorno: dict | None = None) -> str | None:
    """La dirección pública de ESTE servidor: variable PROSPECTOS_URL_PUBLICA o "URL_PUBLICA" en config.json."""
    entorno = os.environ if entorno is None else entorno
    return normalizar(entorno.get('PROSPECTOS_URL_PUBLICA') or config.get('URL_PUBLICA'))


def ajustes_django(url: str) -> dict:
    """Ajustes de seguridad para atender por internet detrás de un proxy con HTTPS (Caddy o Cloudflare).

    El proxy le dice al programa que la conexión original fue HTTPS y desde qué IP: eso lo resuelve waitress
    (trusted_proxy, ver `waitress_proxy`), así `request.is_secure()` y `REMOTE_ADDR` son los reales y el
    bloqueo por intentos fallidos cuenta por persona y no por el proxy.
    """
    host = urlsplit(url).hostname
    return {
        'ALLOWED_HOSTS': [host],
        'CSRF_TRUSTED_ORIGINS': [url],
        'SESSION_COOKIE_SECURE': True,
        'CSRF_COOKIE_SECURE': True,
        # El navegador recuerda 30 días que este dominio es solo HTTPS (subir a un año cuando todo esté estable).
        'SECURE_HSTS_SECONDS': 30 * 24 * 3600,
        'SECURE_HSTS_INCLUDE_SUBDOMAINS': False,
        'SECURE_HSTS_PRELOAD': False,
        'SECURE_CROSS_ORIGIN_OPENER_POLICY': 'same-origin',
    }


def waitress_proxy(confiable: str | None) -> dict:
    """Parámetros de waitress para confiar en los encabezados X-Forwarded-* SOLO del proxy indicado.
    `confiable`: IP del proxy ('127.0.0.1' para Cloudflare Tunnel en la misma PC) o '*' cuando el puerto del
    programa no está expuesto y el único que llega es el proxy (red interna de Docker)."""
    if not confiable:
        return {}
    return {
        'trusted_proxy': confiable,
        'trusted_proxy_count': 1,
        'trusted_proxy_headers': {'x-forwarded-for', 'x-forwarded-proto', 'x-forwarded-host'},
        'clear_untrusted_proxy_headers': True,
    }


def bd_desde_entorno(entorno: dict | None = None) -> dict:
    """Base de datos por variables de entorno (Docker), sin escribir la contraseña en config.json."""
    entorno = os.environ if entorno is None else entorno
    claves = {'MOTOR': 'PROSPECTOS_BD_MOTOR', 'HOST': 'PROSPECTOS_BD_HOST', 'PUERTO': 'PROSPECTOS_BD_PUERTO',
              'NOMBRE': 'PROSPECTOS_BD_NOMBRE', 'USUARIO': 'PROSPECTOS_BD_USUARIO', 'CLAVE': 'PROSPECTOS_BD_CLAVE',
              'BIN': 'PROSPECTOS_BD_BIN'}
    salida = {k: entorno[v] for k, v in claves.items() if entorno.get(v)}
    if 'PUERTO' in salida:
        salida['PUERTO'] = int(salida['PUERTO'])
    return salida
