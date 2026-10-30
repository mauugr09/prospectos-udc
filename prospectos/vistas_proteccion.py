"""Configuración → Protección de datos: copia fuera de la PC, llave de recuperación y separar uniones."""

from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import Prospecto, Respaldo
from .servicios import auditoria, respaldos, uniones
from .views import _ctx


def _solo_admin(request):
    if not request.user.is_superuser:
        raise PermissionDenied


@staff_member_required
def proteccion(request):
    _solo_admin(request)
    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'carpeta':
            texto = (request.POST.get('carpeta') or '').strip().strip('"')
            from .models import Configuracion
            if not texto:
                Configuracion.guardar('respaldo.copia_carpeta', '', request.user)
                messages.warning(request, 'Se quitó la copia externa. Los respaldos quedan solo en esta computadora.')
                return redirect(request.path)
            try:
                respaldos.probar_carpeta(Path(texto))
            except respaldos.ErrorRespaldo as e:
                messages.error(request, str(e))
                return redirect(request.path)
            Configuracion.guardar('respaldo.copia_carpeta', texto, request.user)
            auditoria.registrar('copia_carpeta', None, {'configurada': True}, request=request)
            accion = 'copiar'
        if accion == 'copiar':
            try:
                nombre = respaldos.copiar_externo()
                messages.success(request, f'Copia cifrada guardada: {nombre}.' if nombre else 'Aún no hay un respaldo que copiar.')
            except respaldos.ErrorRespaldo as e:
                messages.error(request, f'No se pudo copiar: {e}')
        elif accion == 'respaldar':
            r = respaldos.crear()
            if r.estado == 'ok':
                messages.success(request, f'Respaldo hecho: {r.archivo}.')
                if respaldos.carpeta_copia():
                    try:
                        respaldos.copiar_externo(r.archivo)
                    except respaldos.ErrorRespaldo as e:
                        messages.error(request, f'El respaldo se hizo, pero la copia externa falló: {e}')
            else:
                messages.error(request, f'Falló el respaldo: {r.mensaje[:200]}')
        elif accion == 'llave':
            if not request.user.check_password(request.POST.get('clave', '')):
                messages.error(request, 'Contraseña incorrecta.')
                return redirect(request.path + '#llave')
            auditoria.registrar('descargar_llave', None, {}, request=request)
            r = HttpResponse(Path(settings.CONFIG_FILE).read_bytes(), content_type='application/json')
            r['Content-Disposition'] = 'attachment; filename="config.json"'
            r['Cache-Control'] = 'no-store'
            return r
        return redirect(request.path)

    ultimo = Respaldo.objects.filter(estado='ok').order_by('-creado_en').first()
    verificado = Respaldo.objects.filter(verificado_en__isnull=False).order_by('-verificado_en').first()
    carpeta = respaldos.carpeta_copia()
    copia = respaldos.estado_copia()
    from datetime import datetime
    copia_fecha = datetime.fromisoformat(copia['fecha']) if copia.get('fecha') else None
    return render(request, 'prospectos/proteccion.html', _ctx(
        request, 'Protección de datos', ultimo=ultimo, verificado=verificado, carpeta=carpeta or '',
        copia=copia, copia_fecha=copia_fecha, pendiente=respaldos.copia_pendiente(), uniones_lista=uniones.recientes(),
        llave_descargada=_llave_descargada()))


def _llave_descargada():
    from .models import Auditoria
    return Auditoria.objects.filter(accion='descargar_llave').order_by('-creado_en').first()


@staff_member_required
def separar(request, pk):
    if not request.user.has_perm('prospectos.resolver_coincidencias'):
        raise PermissionDenied
    sale = get_object_or_404(Prospecto, pk=pk)
    if request.method != 'POST':
        return redirect('prospectos:proteccion')
    try:
        queda, sale = uniones.separar(sale, request.user)
        messages.success(request, f'Separadas: «{queda.nombre_aspirante}» y «{sale.nombre_aspirante}» vuelven a ser dos fichas '
                                  'y no se volverán a unir solas.')
    except uniones.NoSeparable as e:
        messages.error(request, str(e))
    volver = request.POST.get('volver') or ''
    return redirect(volver if volver.startswith('/admin/') else 'prospectos:proteccion')
