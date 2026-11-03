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
