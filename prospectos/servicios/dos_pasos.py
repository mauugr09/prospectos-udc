"""
Verificación en 2 pasos con códigos de 6 dígitos (TOTP, RFC 6238): Google Authenticator, Microsoft Authenticator,
Authy o cualquier app compatible. Sin dependencias ni internet: el código se calcula con la hora de la PC.

- El secreto se guarda cifrado (CampoCifrado). Los 10 códigos de recuperación, solo como sha256: no se pueden volver a ver.
- Se acepta el código del intervalo actual y el de ±30 s (relojes un poco desfasados). Un código no sirve dos veces.
- Obligatoria para administradores (CONFIG['DOS_PASOS_ADMINS'], True por omisión), salvo cuentas de demostración.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone

INTERVALO = 30
DIGITOS = 6
VENTANA = 1
EMISOR = 'Prospectos UDC'


def nuevo_secreto() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode('ascii')


def codigo(secreto: str, contador: int) -> str:
    llave = base64.b32decode(secreto.upper() + '=' * (-len(secreto) % 8))
    h = hmac.new(llave, struct.pack('>Q', contador), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    n = (struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** DIGITOS
    return str(n).zfill(DIGITOS)


def contador_actual(t: float | None = None) -> int:
    return int((time.time() if t is None else t) // INTERVALO)


def _limpio(texto: str) -> str:
    return ''.join(c for c in (texto or '') if c.isalnum()).upper()


def comprobar(secreto: str, texto: str, ultimo: int = 0, t: float | None = None) -> int | None:
    """Devuelve el contador que coincidió (para no aceptarlo otra vez) o None."""
    texto = _limpio(texto)
    if not secreto or len(texto) != DIGITOS or not texto.isdigit():
        return None
    ahora = contador_actual(t)
    for c in range(ahora - VENTANA, ahora + VENTANA + 1):
        if c > ultimo and hmac.compare_digest(codigo(secreto, c), texto):
            return c
    return None


def uri(secreto: str, cuenta: str) -> str:
    return (f'otpauth://totp/{quote(EMISOR)}:{quote(cuenta)}?secret={secreto}&issuer={quote(EMISOR)}'
            f'&algorithm=SHA1&digits={DIGITOS}&period={INTERVALO}')


def qr_svg(texto: str) -> str:
    import io

    import segno
    salida = io.BytesIO()
    segno.make(texto, error='m').save(salida, kind='svg', scale=5, border=2, dark='#111827', light='#ffffff',
                                     xmldecl=False, svgns=True, nl=False)
    return salida.getvalue().decode('utf-8')


def _hash(c: str) -> str:
    return hashlib.sha256(f'{settings.SECRET_KEY}|2p|{_limpio(c)}'.encode()).hexdigest()


def nuevos_codigos_recuperacion(perfil) -> list[str]:
    alfabeto = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # sin 0/O ni 1/I
    codigos = [''.join(secrets.choice(alfabeto) for _ in range(8)) for _ in range(10)]
    perfil.dos_pasos_codigos = [_hash(c) for c in codigos]
    perfil.save(update_fields=['dos_pasos_codigos'])
    return [f'{c[:4]}-{c[4:]}' for c in codigos]


def usar_codigo_recuperacion(perfil, texto: str) -> bool:
    h = _hash(texto)
    if len(_limpio(texto)) != 8 or h not in (perfil.dos_pasos_codigos or []):
        return False
    perfil.dos_pasos_codigos = [x for x in perfil.dos_pasos_codigos if x != h]
    perfil.save(update_fields=['dos_pasos_codigos'])
    return True


def verificar(perfil, texto: str) -> str | None:
    """'codigo' o 'recuperacion' si es válido; None si no."""
    c = comprobar(perfil.dos_pasos_secreto, texto, perfil.dos_pasos_ultimo)
    if c is not None:
        perfil.dos_pasos_ultimo = c
        perfil.save(update_fields=['dos_pasos_ultimo'])
        return 'codigo'
    if usar_codigo_recuperacion(perfil, texto):
        return 'recuperacion'
    return None


def activar(perfil, secreto: str, texto: str) -> list[str] | None:
    """Activa si el código de la app coincide con el secreto propuesto. Devuelve los códigos de recuperación."""
    c = comprobar(secreto, texto)
    if c is None:
        return None
    perfil.dos_pasos_secreto, perfil.dos_pasos_activo, perfil.dos_pasos_ultimo = secreto, True, c
    perfil.dos_pasos_desde = timezone.now()
    perfil.save(update_fields=['dos_pasos_secreto', 'dos_pasos_activo', 'dos_pasos_ultimo', 'dos_pasos_desde'])
    return nuevos_codigos_recuperacion(perfil)


def desactivar(perfil) -> None:
    olvidar_dispositivos(perfil.usuario)
    perfil.dos_pasos_secreto, perfil.dos_pasos_activo, perfil.dos_pasos_codigos = None, False, []
    perfil.dos_pasos_ultimo, perfil.dos_pasos_desde = 0, None
    perfil.save(update_fields=['dos_pasos_secreto', 'dos_pasos_activo', 'dos_pasos_codigos', 'dos_pasos_ultimo', 'dos_pasos_desde'])


def es_demo(usuario) -> bool:
    return usuario.get_username().lower().endswith('@demo.local')


def obligatoria(usuario) -> bool:
    """Administradores siempre (salvo que se apague en config.json); todos, si se pidió en Otras computadoras."""
    if es_demo(usuario):
        return False
    if settings.CONFIG.get('DOS_PASOS_TODOS'):
        return True
    return bool(usuario.is_superuser and settings.CONFIG.get('DOS_PASOS_ADMINS', True))


# --------------------------------------------------------------------------- computadoras de confianza
# Pedir el código en cada entrada cansa y la gente termina apagándolo. Se pide solo cuando hay motivo:
#   - computadora o navegador nuevo (sin la cookie), o la cookie venció (DIAS_CONFIANZA);
#   - la entrada viene de otra red (otra /24 en IPv4) que la de la última vez;
#   - hubo contraseñas equivocadas para esa cuenta justo antes de entrar;
#   - la contraseña cambió desde que se confió en esa computadora.
# En una PC compartida, «confiar» significa que quien sepa la contraseña entra desde ESA PC sin código.
COOKIE = 'prospectos_confianza'
DIAS_CONFIANZA = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256(f'{settings.SECRET_KEY}|confianza|{token}'.encode()).hexdigest()


def _huella_clave(usuario) -> str:
    return hashlib.sha256(f'{settings.SECRET_KEY}|{usuario.password}'.encode()).hexdigest()[:16]


def red_de(ip: str) -> str:
    import ipaddress
    try:
        d = ipaddress.ip_address((ip or '').strip())
    except ValueError:
        return ''
    if d.is_loopback:
        return 'local'
    if d.version == 4:
        return str(ipaddress.ip_network(f'{d}/24', strict=False))
    return str(ipaddress.ip_network(f'{d}/64', strict=False))


def _nombre_navegador(agente: str) -> str:
    a = agente or ''
    nav = next((n for k, n in (('Edg/', 'Edge'), ('OPR/', 'Opera'), ('Firefox/', 'Firefox'), ('Chrome/', 'Chrome'), ('Safari/', 'Safari')) if k in a), 'Navegador')
    so = next((n for k, n in (('Windows', 'Windows'), ('Mac OS', 'Mac'), ('Android', 'Android'), ('iPhone', 'iPhone'), ('iPad', 'iPad'), ('Linux', 'Linux')) if k in a), '')
    return f'{nav} en {so}' if so else nav


def confiar(request, respuesta) -> None:
    """Recuerda esta computadora DIAS_CONFIANZA días (cookie HttpOnly con un token; en la base solo su hash)."""
    from datetime import timedelta

    from ..models import DispositivoConfianza
    token = secrets.token_urlsafe(32)
    ahora = timezone.now()
    DispositivoConfianza.objects.create(
        usuario=request.user, token_hash=_hash_token(token), nombre=_nombre_navegador(request.META.get('HTTP_USER_AGENT', ''))[:80],
        red=red_de(request.META.get('REMOTE_ADDR', '')), clave_huella=_huella_clave(request.user), vence_en=ahora + timedelta(days=DIAS_CONFIANZA))
    respuesta.set_cookie(COOKIE, token, max_age=DIAS_CONFIANZA * 86400, httponly=True, samesite='Lax', secure=request.is_secure())


def motivo_para_pedir(request) -> str | None:
    """None si esta computadora es de confianza y nada se ve raro; si no, por qué se pide el código."""
    from ..models import DispositivoConfianza
    token = request.COOKIES.get(COOKIE)
    if not token:
        return 'nueva'
    d = DispositivoConfianza.objects.filter(usuario=request.user, token_hash=_hash_token(token)).first()
    if not d or d.vence_en <= timezone.now():
        return 'nueva'
    if d.clave_huella != _huella_clave(request.user):
        return 'contraseña cambiada'
    if request.session.get('intentos_previos', 0) >= 3:
        return 'intentos fallidos'
    red = red_de(request.META.get('REMOTE_ADDR', ''))
    if d.red and red and red != d.red:
        return 'otra red'
    d.usado_en = timezone.now()
    d.save(update_fields=['usado_en'])
    return None


def olvidar_dispositivos(usuario) -> int:
    from ..models import DispositivoConfianza
    return DispositivoConfianza.objects.filter(usuario=usuario).delete()[0]
