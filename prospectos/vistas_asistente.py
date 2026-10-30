"""Kuali, el asistente: conversación, confirmación de propuestas y configuración (solo el nombre de la mascota)."""

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

SESION_MEMORIA = 'asistente_memoria'
SESION_PROPUESTAS = 'asistente_propuestas'


def _contexto(datos) -> dict:
    ficha = str(datos.get('ficha') or '')
    return {'ficha': int(ficha)} if ficha.isdigit() else {}


def _interno(url) -> bool:
    return isinstance(url, str) and url.startswith('/admin/') and '//' not in url


@staff_member_required
@require_POST
def conversar(request):
    try:
        datos = json.loads(request.body or b'{}')
    except ValueError:
        datos = {}
    contexto = _contexto(datos)
    try:
        r = asistente.preguntar(request.user, datos.get('mensaje', ''), request.session.get(SESION_MEMORIA, {}), contexto)
    except asistente.PreguntaRechazada as e:
        return JsonResponse({'ok': False, 'mensaje': str(e), 'tipo': 'vacia'}, status=400)
    request.session[SESION_MEMORIA] = r.get('memoria') or {}
    pendientes = dict(list(request.session.get(SESION_PROPUESTAS, {}).items())[-9:])
    tarjetas = []
    for p in r['propuestas']:
        pendientes[p['id']] = p
        tarjetas.append({'id': p['id'], **asistente.detalle_propuesta(p)})
    request.session[SESION_PROPUESTAS] = pendientes
    return JsonResponse({'ok': True, 'texto': r['texto'], 'propuestas': tarjetas, 'entendi': r.get('entendi', ''),
                         'siguientes': r.get('siguientes', []), 'visual': r.get('visual'),
                         'calculos': [c for c in r.get('calculos', []) if not c.get('enlace') or _interno(c['enlace'])]})


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
    request.session.pop(SESION_MEMORIA, None)
    request.session.pop(SESION_PROPUESTAS, None)
    return JsonResponse({'ok': True})


@staff_member_required
def configurar(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    if request.method == 'POST':
        nombre = re.sub(r'[^\w áéíóúñÁÉÍÓÚÑ-]', '', request.POST.get('mascota_nombre', '')).strip()[:24]
        if nombre:
            Configuracion.guardar('asistente.mascota_nombre', nombre, request.user)
            auditoria.registrar('asistente_configurar', None, {'nombre': nombre}, request=request)
            messages.success(request, f'Listo: la mascota ahora se llama {nombre}.')
        return redirect(request.path)
    return render(request, 'prospectos/asistente_configurar.html', _ctx(request, 'Asistente', mascota=asistente.nombre_mascota()))
