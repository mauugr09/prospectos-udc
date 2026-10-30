"""Obliga a cambiar la contraseña temporal antes de usar el programa."""

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse


class ReferrerEnMapas:
    """
    El programa no manda «Referer» a otros sitios (Referrer-Policy: same-origin). Las pantallas con mapa son la
    excepción: Google Maps valida la llave por la dirección de origen y OpenStreetMap exige saber quién pide.
    Solo se envía el origen (http://127.0.0.1:8000), nunca la ruta ni datos.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        from django.urls import reverse
        if request.path in (reverse('admin:index'), reverse('prospectos:mapa'), reverse('prospectos:ubicar'),
                            reverse('prospectos:configurar_mapa')):
            respuesta['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return respuesta


class CambioDeClaveObligatorio:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        u = getattr(request, 'user', None)
        if u is not None and u.is_authenticated and not request.path.startswith(('/static/', '/salud/', '/marca/')):
            from .models import Perfil
            pendiente = Perfil.objects.filter(usuario=u, debe_cambiar_clave=True)
            cambio, listo, salir = reverse('admin:password_change'), reverse('admin:password_change_done'), reverse('admin:logout')
            if request.path == listo:
                pendiente.update(debe_cambiar_clave=False)
            elif request.path not in (cambio, salir) and pendiente.exists():
                messages.info(request, 'Antes de empezar, cambia tu contraseña temporal por una tuya (12 caracteres o más).')
                return redirect(cambio)
        return self.get_response(request)


# --------------------------------------------------------------------------- acceso: intentos fallidos e inactividad
import time

from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.core.cache import cache
from django.dispatch import receiver
from django.http import JsonResponse

INTENTOS_MAXIMOS = 5          # por usuario
INTENTOS_MAXIMOS_IP = 20      # por computadora (alguien probando muchos usuarios)
BLOQUEO_SEGUNDOS = 15 * 60


def _ip(request) -> str:
    return (request.META.get('REMOTE_ADDR') or '?') if request is not None else '?'


def _llaves(usuario: str, ip: str) -> tuple[str, str]:
    return f'acceso:u:{(usuario or "").strip().lower()[:150]}', f'acceso:ip:{ip}'


def bloqueado(usuario: str, ip: str) -> bool:
    ku, kip = _llaves(usuario, ip)
    return (cache.get(ku, 0) >= INTENTOS_MAXIMOS) or (cache.get(kip, 0) >= INTENTOS_MAXIMOS_IP)


@receiver(user_login_failed)
def _fallo(sender, credentials, request=None, **kw):
    usuario = credentials.get('username', '')
    ku, kip = _llaves(usuario, _ip(request))
    for k in (ku, kip):
        cache.add(k, 0, BLOQUEO_SEGUNDOS)
        try:
            n = cache.incr(k)
        except ValueError:
            cache.set(k, 1, BLOQUEO_SEGUNDOS)
            n = 1
        if k == ku and n == INTENTOS_MAXIMOS:
            from django.contrib.auth import get_user_model
            from .servicios import auditoria
            u = get_user_model().objects.filter(username__iexact=usuario).first()
            auditoria.registrar('acceso_bloqueado', u, {'intentos': n, 'minutos': BLOQUEO_SEGUNDOS // 60}, request=request)


@receiver(user_logged_in)
def _entro(sender, request, user, **kw):
    previos = cache.get(_llaves(user.get_username(), _ip(request))[0], 0)
    cache.delete(_llaves(user.get_username(), _ip(request))[0])
    if request is not None and hasattr(request, 'session'):
        request.session['intentos_previos'] = previos  # la verificación en 2 pasos lo toma como sospecha
    if request is not None and hasattr(request, 'session'):
        request.session['ultima_actividad'] = time.time()
        request.session.pop('dos_pasos_ok', None)  # cada entrada con contraseña vuelve a pedir el código


class ProteccionDeAcceso:
    """
    - Tras 5 contraseñas equivocadas para un usuario (o 20 desde una misma computadora), el acceso se
      bloquea 15 minutos. Contra adivinar contraseñas; el costo es que alguien podría bloquear a otro a
      propósito durante 15 minutos.
    - Tras INACTIVIDAD_MINUTOS sin usar el programa (30 por omisión) la sesión se cierra: una PC de oficina
      abierta no deja los datos de los aspirantes a la vista. La campanita revisando avisos NO cuenta como uso;
      la pantalla «En vivo» de un evento sí (se proyecta durante horas).
    """
    SIN_CONTAR = ('/static/', '/salud/', '/marca/', '/admin/herramientas/avisos/contador/', '/favicon')

    def __init__(self, get_response):
        self.get_response = get_response
        self.login = '/admin/login/'

    def __call__(self, request):
        if request.method == 'POST' and request.path == self.login:
            if bloqueado(request.POST.get('username', ''), _ip(request)):
                messages.error(request, f'Demasiados intentos con contraseña equivocada. Espera {BLOQUEO_SEGUNDOS // 60} minutos '
                                        'o pide a un administrador que te restablezca la contraseña.')
                return redirect(request.get_full_path())
        u = getattr(request, 'user', None)
        minutos = int(settings.CONFIG.get('INACTIVIDAD_MINUTOS', 30) or 0)
        if minutos and u is not None and u.is_authenticated and not request.path.startswith(self.SIN_CONTAR):
            ahora = time.time()
            ultima = request.session.get('ultima_actividad', ahora)
            if ahora - ultima > minutos * 60:
                logout(request)
                if request.headers.get('x-requested-with') == 'fetch':
                    return JsonResponse({'ok': False, 'mensaje': 'La sesión se cerró por inactividad. Recarga la página.'}, status=401)
                messages.info(request, f'Se cerró tu sesión después de {minutos} minutos sin usar el programa.')
                return redirect(f'{self.login}?next={request.path}')
            request.session['ultima_actividad'] = ahora
        elif minutos and u is not None and u.is_authenticated and request.path == '/admin/herramientas/avisos/contador/':
            ultima = request.session.get('ultima_actividad', time.time())
            if time.time() - ultima > minutos * 60:
                logout(request)
                return JsonResponse({'sin_leer': 0, 'sesion': False}, status=401)
        return self.get_response(request)


# --------------------------------------------------------------------------- verificación en 2 pasos
SESION_DOS_PASOS = 'dos_pasos_ok'
INTENTOS_CODIGO = 5


class VerificacionEnDosPasos:
    """
    Con la verificación activa, después de la contraseña solo se puede ver la pantalla del código (o salir).
    A un administrador sin ella (obligatoria) se le lleva a activarla; mientras tanto puede cambiar su contraseña temporal.
    Se revisa una vez por sesión: al pasar, la sesión queda marcada con el id del usuario.
    """
    LIBRES = ('/static/', '/salud/', '/marca/', '/favicon')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        u = getattr(request, 'user', None)
        if (u is not None and u.is_authenticated and not request.path.startswith(self.LIBRES)
                and request.session.get(SESION_DOS_PASOS) != u.pk):
            from .models import Perfil
            from .servicios import dos_pasos
            perfil = Perfil.de(u)
            salir = reverse('admin:logout')
            if perfil.dos_pasos_activo and dos_pasos.motivo_para_pedir(request) is None:
                request.session[SESION_DOS_PASOS] = u.pk  # computadora de confianza y nada raro: no se pide el código
            elif perfil.dos_pasos_activo:
                verificar = reverse('prospectos:verificar')
                if request.path not in (verificar, salir):
                    if request.headers.get('x-requested-with') == 'fetch':
                        return JsonResponse({'ok': False, 'mensaje': 'Falta el código de verificación. Recarga la página.'}, status=401)
                    return redirect(f'{verificar}?next={request.get_full_path()}')
            elif dos_pasos.obligatoria(u):
                permitidas = (reverse('prospectos:dos_pasos'), salir, reverse('admin:password_change'), reverse('admin:password_change_done'))
                if request.path not in permitidas:
                    if request.headers.get('x-requested-with') == 'fetch':
                        return JsonResponse({'ok': False, 'mensaje': 'Activa la verificación en 2 pasos. Recarga la página.'}, status=401)
                    messages.info(request, 'Por seguridad, las cuentas de administrador necesitan la verificación en 2 pasos. '
                                           'Actívala para continuar (toma un minuto).')
                    return redirect(reverse('prospectos:dos_pasos'))
            else:
                request.session[SESION_DOS_PASOS] = u.pk
        return self.get_response(request)


def fallo_de_codigo(request) -> bool:
    """Cuenta un código equivocado como intento fallido de acceso. True si con eso la cuenta quedó bloqueada."""
    usuario = request.user.get_username()
    user_login_failed.send(sender=__name__, credentials={'username': usuario}, request=request)
    if bloqueado(usuario, _ip(request)):
        logout(request)
        return True
    return False
