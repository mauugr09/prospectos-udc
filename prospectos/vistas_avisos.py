"""La campanita: bandeja de avisos, panel desplegable, contador y preferencias."""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import Notificacion, TipoAviso
from .servicios import avisos
from .views import _ctx

ICONOS = {TipoAviso.ASIGNADO: 'person_add', TipoAviso.VENCIDAS: 'phone_missed',
          TipoAviso.EVENTO: 'event', TipoAviso.SISTEMA: 'error'}


def _mios(request):
    return Notificacion.objects.filter(usuario=request.user)


def _hace(fecha) -> str:
    seg = (timezone.now() - fecha).total_seconds()
    if seg < 60:
        return 'Ahora'
    if seg < 3600:
        return f'Hace {int(seg // 60)} min'
    if seg < 86400:
        h = int(seg // 3600)
        return f'Hace {h} hora' + ('s' if h > 1 else '')
    local = timezone.localtime(fecha)
    if seg < 2 * 86400:
        return f'Ayer, {local:%H:%M}'
    return f'{local.day} {MESES_CORTOS[local.month - 1]}, {local:%H:%M}'


MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']


def _decorar(lista):
    for n in lista:
        n.icono = ICONOS.get(n.tipo, 'notifications')
        n.hace = _hace(n.actualizada_en)
    return lista


@staff_member_required
def bandeja(request):
    if request.method == 'POST':
        avisos.guardar_preferencias(request.user, set(request.POST.getlist('tipo')))
        messages.success(request, 'Preferencias guardadas.')
        return redirect(request.path + '#preferencias')
    filtro = request.GET.get('ver', 'nuevos')
    qs = _mios(request)
    if filtro == 'nuevos':
        qs = qs.filter(leida_en__isnull=True)
    apagados = avisos.apagados(request.user)
    tipos = [{'valor': t.value, 'nombre': t.label, 'icono': ICONOS[t], 'descripcion': avisos.DESCRIPCIONES[t],
              'encendido': t.value not in apagados, 'fijo': t in avisos.OBLIGATORIOS}
             for t in TipoAviso if t not in avisos.OBLIGATORIOS or request.user.is_superuser]
    return render(request, 'prospectos/avisos.html', _ctx(
        request, 'Avisos', avisos_lista=_decorar(list(qs[:200])), filtro=filtro, tipos=tipos,
        sin_leer=avisos.no_leidas(request.user), dias=avisos.DIAS_GUARDADOS))


@staff_member_required
def panel(request):
    """Lo que se ve al abrir la campanita (fragmento HTML)."""
    lista = list(_mios(request)[:8])
    return render(request, 'prospectos/avisos_panel.html', {'avisos_lista': _decorar(lista),
                                                           'sin_leer': avisos.no_leidas(request.user)})


@staff_member_required
def contador(request):
    """La cifra y los avisos sin leer más recientes, para la ventanita flotante (sin datos de aspirantes: solo cifras)."""
    from django.urls import reverse
    recientes = list(_mios(request).filter(leida_en__isnull=True).order_by('-actualizada_en')[:3])
    return JsonResponse({'sin_leer': avisos.no_leidas(request.user), 'recientes': [
        {'marca': int(n.actualizada_en.timestamp() * 1000), 'titulo': n.titulo, 'detalle': n.detalle,
         'icono': ICONOS.get(n.tipo, 'notifications'), 'tipo': n.tipo, 'url': reverse('prospectos:aviso_abrir', args=[n.pk])}
        for n in recientes]})


@staff_member_required
def abrir(request, pk):
    n = get_object_or_404(_mios(request), pk=pk)
    if n.leida_en is None:
        n.leida_en = timezone.now()
        n.save(update_fields=['leida_en'])
    if n.url and url_has_allowed_host_and_scheme(n.url, allowed_hosts={request.get_host()}):
        return redirect(n.url)
    return redirect('prospectos:avisos')


@staff_member_required
@require_POST
def leer_todo(request):
    _mios(request).filter(leida_en__isnull=True).update(leida_en=timezone.now())
    if request.headers.get('x-requested-with') == 'fetch':
        return JsonResponse({'sin_leer': 0})
    return redirect(request.POST.get('volver') if url_has_allowed_host_and_scheme(
        request.POST.get('volver', ''), allowed_hosts={request.get_host()}) else 'prospectos:avisos')


def contexto(request):
    """Context processor: cifra de la campanita en cada página del panel."""
    u = getattr(request, 'user', None)
    if not u or not u.is_authenticated or not u.is_staff or not request.path.startswith('/admin'):
        return {}
    from .servicios.asistente import nombre_mascota
    return {'avisos_sin_leer': avisos.no_leidas(u), 'mascota_nombre': nombre_mascota()}
