"""
Cerrar sesión: ventana de confirmación (con «Olvidar esta computadora»), pantalla «Sesión cerrada» y el aviso
antes del cierre por inactividad. El cierre por inactividad lo hace el servidor (middleware.ProteccionDeAcceso);
aquí solo se evita que la pantalla siga mostrando datos cuando ya se venció, y se cuenta como uso mover el mouse
o escribir en una página abierta (sigo_aqui).
"""

from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .servicios import auditoria, dos_pasos

MOTIVOS = {'inactividad': 'Se cerró sola después de {m} minutos sin usar el programa, para que nadie vea los datos en una '
                          'computadora desatendida.'}


@require_POST
def salir(request):
    u = request.user if request.user.is_authenticated else None
    olvidar = request.POST.get('olvidar') == '1'
    motivo = request.POST.get('motivo') if request.POST.get('motivo') in MOTIVOS else ''
    if u and olvidar:
        from .models import DispositivoConfianza
        token = request.COOKIES.get(dos_pasos.COOKIE)
        if token:
            DispositivoConfianza.objects.filter(usuario=u, token_hash=dos_pasos._hash_token(token)).delete()
    if u:
        auditoria.registrar('cerrar_sesion', None, {'olvidar_pc': olvidar, 'motivo': motivo or 'manual'}, request=request)
    logout(request)
    respuesta = redirect(reverse('prospectos:sesion_cerrada') + (f'?motivo={motivo}' if motivo else ''))
    if olvidar:
        respuesta.delete_cookie(dos_pasos.COOKIE)
    return respuesta


def sesion_cerrada(request):
    from django.conf import settings
    from django.contrib import admin
    if request.user.is_authenticated:
        return redirect('admin:index')
    minutos = int(settings.CONFIG.get('INACTIVIDAD_MINUTOS', 30) or 0)
    motivo = request.GET.get('motivo')
    return render(request, 'prospectos/sesion_cerrada.html', admin.site.each_context(request) | {
        'title': 'Sesión cerrada', 'explicacion': MOTIVOS[motivo].format(m=minutos) if motivo in MOTIVOS else '',
        'inactividad': motivo == 'inactividad'})


@require_POST
def sigo_aqui(request):
    """La página sigue en uso (mouse o teclado) aunque no se haya pedido otra: el middleware renueva la actividad."""
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False}, status=401)
    return JsonResponse({'ok': True})


def csrf_fallo(request, reason=''):
    """
    CSRF_FAILURE_VIEW. Casi siempre es una pestaña vieja: al entrar o salir en otra pestaña (o al cerrarse la sesión por
    inactividad) el código de seguridad del formulario cambia y el formulario abierto ya no sirve. La protección se
    mantiene; en vez de un 403 en inglés técnico se regresa a la pantalla con un formulario nuevo. Nunca se reintenta
    el envío por la persona: hay que volver a pulsar el botón.
    """
    import logging

    from django.conf import settings
    from django.contrib import admin, messages
    from django.utils.http import url_has_allowed_host_and_scheme
    sin_cookie = settings.CSRF_COOKIE_NAME not in request.COOKIES
    logging.getLogger('prospectos.seguridad').warning(
        'CSRF rechazado: %s · %s %s · cookie=%s · origen=%s · host=%s', reason, request.method, request.path,
        'no' if sin_cookie else 'sí', request.META.get('HTTP_ORIGIN', '-'), request.get_host())
    if sin_cookie:
        texto = ('Tu navegador no guardó la cookie de seguridad de este sitio. Revisa que no estén bloqueadas las cookies '
                 'para esta dirección (o sal del modo privado) y vuelve a intentarlo.')
    elif request.path == reverse('admin:login'):
        texto = ('La página de acceso había caducado (se entró o salió en otra pestaña). '
                 'Escribe otra vez tu contraseña y pulsa Entrar.')
    else:
        texto = ('Esta página estaba abierta desde antes de entrar o salir en otra pestaña, así que su formulario caducó. '
                 'No se guardó nada: vuelve a hacerlo.')
    # De vuelta a la página donde estaba el formulario (no a la dirección que lo recibe: muchas solo aceptan POST).
    from urllib.parse import urlsplit
    ref = urlsplit(request.META.get('HTTP_REFERER', ''))
    volver = '/admin/'
    if ref.path and url_has_allowed_host_and_scheme(request.META.get('HTTP_REFERER', ''), allowed_hosts={request.get_host()}):
        volver = ref.path + (f'?{ref.query}' if ref.query else '')
    if request.path == reverse('admin:login'):
        siguiente = request.POST.get('next') or request.GET.get('next') or ''
        if siguiente and url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}):
            volver = f"{reverse('admin:login')}?next={siguiente}"
    if not sin_cookie:
        try:
            messages.warning(request, texto)
            return redirect(volver)
        except Exception:  # noqa: BLE001 - sin sesión ni mensajes: se muestra la página
            pass
    return render(request, 'prospectos/csrf_fallo.html', admin.site.each_context(request) | {
        'title': 'El formulario caducó', 'texto': texto, 'volver': volver}, status=403)
