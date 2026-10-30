"""
Uso desde teléfonos y tabletas (Android, iPhone, iPad).

El programa es el mismo para todos los equipos: el panel web se acomoda solo al tamaño de la pantalla y,
desde un teléfono o tableta, se puede «instalar» en la pantalla de inicio como una app (PWA). No hay una app
aparte en Play Store ni App Store: así no hay que publicar, firmar ni actualizar dos programas más, y los datos
nunca salen de la computadora de Admisiones.

Aquí viven:
  - el sistema del visitante (para dar los pasos correctos en /conectar/),
  - los enlaces para llamar, escribir por WhatsApp o mandar correo desde la ficha,
  - el manifiesto de la app y el «service worker» (solo muestra una pantalla de «sin conexión»;
    NUNCA guarda páginas con datos de aspirantes en el teléfono).
"""

from __future__ import annotations

import re
from urllib.parse import quote

# --------------------------------------------------------------------------- sistema del visitante
SISTEMAS = ('windows', 'mac', 'android', 'ios')


def sistema(agente: str) -> str:
    """'android', 'ios', 'mac' o 'windows' según el User-Agent.

    Desde iPadOS 13 Safari se presenta como «Macintosh»; el iPad se distingue porque tiene pantalla táctil,
    cosa que el servidor no puede saber: la página /conectar/ lo corrige en el navegador (navigator.maxTouchPoints).
    """
    a = agente or ''
    if 'Android' in a:
        return 'android'
    if re.search(r'iPhone|iPad|iPod', a):
        return 'ios'
    if 'Macintosh' in a:
        return 'mac'
    return 'windows'


# --------------------------------------------------------------------------- llamar / WhatsApp / correo
LADA_PAIS = '52'  # México


def solo_digitos(telefono: str | None) -> str:
    return re.sub(r'\D+', '', telefono or '')


def internacional(telefono: str | None) -> str | None:
    """Número en formato internacional sin «+» (5215512345678 → 525512345678). None si no parece válido.

    - 10 dígitos: número mexicano → se antepone 52.
    - 044/045 o 1 de los celulares viejos (13 dígitos con 521): se quita.
    - Más de 10 dígitos que ya empiezan con 52: se respeta.
    """
    d = solo_digitos(telefono)
    if d.startswith(('044', '045')) and len(d) == 13:
        d = d[3:]
    if d.startswith('521') and len(d) == 13:
        d = '52' + d[3:]
    if len(d) == 10:
        return LADA_PAIS + d
    if 11 <= len(d) <= 15:
        return d
    return None


def acciones_contacto(telefono: str | None = None, correo: str | None = None) -> list[tuple[str, str, str]]:
    """Botones (icono, texto, enlace) para la ficha. En el teléfono abren el marcador, WhatsApp o el correo;
    en la computadora, lo que tenga configurado (Teléfono de Windows/Mac, WhatsApp Web, Outlook/Mail)."""
    salida = []
    if telefono:
        num = internacional(telefono)
        if num:
            salida.append(('call', 'Llamar', f'tel:+{num}'))
            salida.append(('chat', 'WhatsApp', f'https://wa.me/{num}'))
    if correo and '@' in correo:
        salida.append(('mail', 'Correo', f'mailto:{quote(correo.strip(), safe="@.+-_")}'))
    return salida


# --------------------------------------------------------------------------- app instalable (PWA)
def manifiesto(static) -> dict:
    """Manifiesto web: nombre, iconos y colores con los que se instala en Android, iPhone y iPad."""
    return {
        'id': '/admin/',
        'name': 'Prospectos UDC',
        'short_name': 'Prospectos',
        'description': 'Admisiones de la Universidad de Cuautitlán: a quién llamar hoy, prospectos y visitas a preparatorias.',
        'lang': 'es-MX',
        'dir': 'ltr',
        'start_url': '/admin/',
        'scope': '/',
        'display': 'standalone',
        'display_override': ['standalone', 'minimal-ui'],
        'orientation': 'any',
        'background_color': '#f2f2f7',
        'theme_color': '#172852',
        'categories': ['business', 'education', 'productivity'],
        'icons': [
            {'src': static('prospectos/marca/icono-192.png'), 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
            {'src': static('prospectos/marca/icono-512.png'), 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
            {'src': static('prospectos/marca/icono-maskable-512.png'), 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
            {'src': static('prospectos/marca/favicon.svg'), 'sizes': 'any', 'type': 'image/svg+xml', 'purpose': 'any'},
        ],
        'shortcuts': [
            {'name': 'A quién llamar hoy', 'short_name': 'Llamar', 'url': '/admin/herramientas/cola/',
             'icons': [{'src': static('prospectos/marca/icono-192.png'), 'sizes': '192x192', 'type': 'image/png'}]},
            {'name': 'Calendario de visitas', 'short_name': 'Calendario', 'url': '/admin/herramientas/calendario/',
             'icons': [{'src': static('prospectos/marca/icono-192.png'), 'sizes': '192x192', 'type': 'image/png'}]},
        ],
    }


# Versión del service worker: cambiarla obliga a los teléfonos a tomar el nuevo.
VERSION_SW = '2'


def service_worker(pagina_sin_conexion: str, icono: str) -> str:
    """
    Service worker mínimo y a propósito «tonto»:
      - Todo va siempre a la red (el programa es la fuente de verdad; nada se sirve viejo).
      - Si no hay red al abrir una página, muestra «Sin conexión con Prospectos» (lo único que se guarda).
      - No guarda ninguna respuesta del programa: ni fichas, ni listas, ni reportes. Si el teléfono se pierde,
        no lleva datos de aspirantes dentro (LFPDPPP).
    """
    return f"""/* Prospectos UDC · service worker v{VERSION_SW}. Ver prospectos/servicios/movil.py */
const CACHE = 'prospectos-sin-conexion-v{VERSION_SW}';
const OFFLINE = {pagina_sin_conexion!r};
const ARCHIVOS = [OFFLINE, {icono!r}];

self.addEventListener('install', (e) => {{
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ARCHIVOS)).then(() => self.skipWaiting()));
}});

self.addEventListener('activate', (e) => {{
  e.waitUntil(caches.keys()
    .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
}});

self.addEventListener('fetch', (e) => {{
  const r = e.request;
  if (r.method !== 'GET' || r.mode !== 'navigate') return;  // todo lo demás: directo a la red, sin tocarlo
  e.respondWith(fetch(r).catch(() => caches.match(OFFLINE)));
}});
"""
