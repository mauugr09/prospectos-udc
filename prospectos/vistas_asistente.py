"""Asistente inteligente: conversación, confirmación de propuestas y configuración (llave, tope y gasto)."""

import json
import re

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import Configuracion
from .servicios import asistente, auditoria
from .views import _ctx

SESION_HISTORIAL = 'asistente_historial'
SESION_PROPUESTAS = 'asistente_propuestas'


def _contexto(request, datos) -> dict:
    ficha = str(datos.get('ficha') or '')
    return {'ficha': int(ficha)} if ficha.isdigit() else {}


@staff_member_required
@require_POST
def conversar(request):
    try:
        datos = json.loads(request.body or b'{}')
    except ValueError:
        datos = {}
    contexto = _contexto(request, datos)
    try:
        r = asistente.preguntar(request.user, datos.get('mensaje', ''), request.session.get(SESION_HISTORIAL, []), contexto)
    except asistente.PreguntaRechazada as e:
        return JsonResponse({'ok': False, 'mensaje': str(e), 'tipo': 'privacidad'}, status=400)
    except asistente.AsistenteNoDisponible as e:
        return JsonResponse({'ok': False, 'mensaje': str(e), 'tipo': 'no_disponible'}, status=503)
    request.session[SESION_HISTORIAL] = r['historial']
    pendientes = dict(list(request.session.get(SESION_PROPUESTAS, {}).items())[-9:])
    tarjetas = []
    for p in r['propuestas']:
        pendientes[p['id']] = p
        tarjetas.append({'id': p['id'], **asistente.detalle_propuesta(p)})
    request.session[SESION_PROPUESTAS] = pendientes
    return JsonResponse({'ok': True, 'texto': asistente.personalizar(r['texto'], request.user, contexto),
                         'propuestas': tarjetas, 'sin_ia': r.get('sin_ia', False), 'consulto': sorted(set(r['herramientas']))})


@staff_member_required
@require_POST
def confirmar(request, pid):
    pendientes = request.session.get(SESION_PROPUESTAS, {})
    p = pendientes.pop(pid, None)
    request.session[SESION_PROPUESTAS] = pendientes
    if not p:
        return JsonResponse({'ok': False, 'mensaje': 'Esa propuesta ya no está vigente. Pídela otra vez.'}, status=404)
    if request.POST.get('decision') == 'no':
        return JsonResponse({'ok': True, 'mensaje': 'Descartado. No se hizo nada.'})
    try:
        return JsonResponse({'ok': True, 'mensaje': asistente.ejecutar(request.user, p)})
    except PermissionError:
        return JsonResponse({'ok': False, 'mensaje': 'Tu rol no permite hacer eso.'}, status=403)


@staff_member_required
@require_POST
def nueva(request):
    request.session.pop(SESION_HISTORIAL, None)
    request.session.pop(SESION_PROPUESTAS, None)
    return JsonResponse({'ok': True})


@staff_member_required
def configurar(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    if request.method == 'POST':
        from .servicios.cifrado import cifrar
        llave = (request.POST.get('llave') or '').strip()
        if llave:
            if not re.fullmatch(r'sk-ant-[\w-]{20,}', llave):
                messages.error(request, 'Esa no parece una llave de Anthropic (empieza con sk-ant-).')
                return redirect(request.path)
            Configuracion.guardar('asistente.llave', cifrar(llave), request.user)
        if request.POST.get('quitar_llave'):
            Configuracion.guardar('asistente.llave', '', request.user)
        try:
            tope = max(0.0, min(float(request.POST.get('tope_usd', asistente.tope_usd())), 500.0))
        except ValueError:
            tope = asistente.tope_usd()
        Configuracion.guardar('asistente.tope_usd', tope, request.user)
        modelo = request.POST.get('modelo')
        if modelo in asistente.PRECIOS:
            Configuracion.guardar('asistente.modelo', modelo, request.user)
        Configuracion.guardar('asistente.activo', bool(request.POST.get('activo')), request.user)
        auditoria.registrar('asistente_configurar', None, {'activo': bool(request.POST.get('activo')), 'tope_usd': tope,
                                                            'llave_nueva': bool(llave), 'modelo': asistente.modelo()}, request=request)
        messages.success(request, 'Configuración del asistente guardada.')
        return redirect(request.path)
    g = asistente.gasto()
    tope = asistente.tope_usd()
    return render(request, 'prospectos/asistente_configurar.html', _ctx(
        request, 'Asistente inteligente', activo=bool(Configuracion.obtener('asistente.activo', False)),
        tiene_llave=bool(asistente.llave()), gasto=g, tope=tope, uso=min(100, round(g['usd'] / tope * 100)) if tope else 100,
        modelo=asistente.modelo(), modelos=[(m, p) for m, p in asistente.PRECIOS.items()]))
