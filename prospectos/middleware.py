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
