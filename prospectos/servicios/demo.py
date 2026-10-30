"""
Borrar los datos de demostración (los que carga la opción [D] al abrir el programa por primera vez).

Solo se borra lo que la demostración creó y que nada real usa:
  - Respuestas de los Forms «demo-…» y esos Forms.
  - Prospectos cuyas respuestas son TODAS de demostración (si uno ya tiene una respuesta real, se queda).
  - Eventos «EVDEMO…» (lo real asignado a ellos se queda sin evento); prepas ficticias de la demo sin nada real.
  - Usuarios «@demo.local» (nunca quien está borrando, y solo si queda otro administrador real).
Antes se hace un respaldo completo; si el respaldo falla, no se borra nada.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction

from ..models import Configuracion, Evento, Formulario, Preparatoria, Prospecto, Respuesta
from . import auditoria

DOMINIO = '@demo.local'


def _forms():
    return Formulario.objects.filter(google_form_id__startswith='demo-')


def _prospectos():
    """Prospectos que solo existen por la demostración."""
    demo = Respuesta.objects.filter(formulario__in=_forms())
    reales = Respuesta.objects.exclude(formulario__in=_forms())
    ids = set(Prospecto.objects.filter(pk__in=demo.values('prospecto'))
              .exclude(pk__in=reales.exclude(prospecto=None).values('prospecto')).values_list('pk', flat=True))
    # Las fichas que se unieron a otra (familias, duplicados) ya no tienen respuestas: van con la ficha que las absorbió.
    while True:
        nuevos = set(Prospecto.objects.filter(fusionado_en__in=ids, respuestas__isnull=True).exclude(pk__in=ids)
                     .values_list('pk', flat=True))
        if not nuevos:
            break
        ids |= nuevos
    return Prospecto.objects.filter(pk__in=ids)


def _prepas_demo():
    """Las prepas ficticias y las que el importador dio de alta con los nombres que «escribieron» los alumnos de la demo."""
    from .semillas import PREPAS
    from .texto import normalizar
    nombres = {normalizar(n) for p in PREPAS for n in [p[0], *p[5]]}
    ids = [pk for pk, nombre in Preparatoria.objects.values_list('pk', 'nombre') if normalizar(nombre) in nombres]
    return Preparatoria.objects.filter(pk__in=ids)


def _eventos(_=None):
    """Todos los eventos de la demo. Si una respuesta real quedó asignada a uno (por prepa y fecha), se queda sin
    evento al borrarlo: una visita ficticia no debe contar registros reales."""
    return Evento.objects.filter(codigo__startswith='EVDEMO')


def _usuarios(quien=None):
    qs = get_user_model().objects.filter(username__endswith=DOMINIO)
    return qs.exclude(pk=quien.pk) if quien else qs


def inventario(quien=None) -> dict:
    pros = _prospectos()
    return {
        'prospectos': pros.count(),
        'respuestas': Respuesta.objects.filter(formulario__in=_forms()).count(),
        'formularios': _forms().count(),
        'eventos': _eventos(pros.values('pk')).count(),
        'preparatorias': _prepas_demo().count(),
        'usuarios': _usuarios(quien).count(),
        'quien_es_demo': bool(quien and quien.username.endswith(DOMINIO)),
        'otro_admin': get_user_model().objects.filter(is_superuser=True, is_active=True).exclude(username__endswith=DOMINIO).exists(),
    }


def hay_demo() -> bool:
    return _forms().exists() or Evento.objects.filter(codigo__startswith='EVDEMO').exists() or _usuarios().exists()


def borrar(quien) -> dict:
    """Borra la demostración. Devuelve lo borrado; lanza ValueError si no es seguro hacerlo."""
    inv = inventario(quien)
    if inv['quien_es_demo']:
        raise ValueError('Entra con tu usuario real (no uno @demo.local) para borrar la demostración.')
    if not inv['otro_admin']:
        raise ValueError('Primero crea un administrador real en Configuración → Usuarios; si no, nadie podría entrar después.')
    from . import respaldos
    respaldo = respaldos.crear()
    if respaldo.estado != 'ok':
        raise RuntimeError(respaldo.mensaje or 'el respaldo no se pudo crear')
    with transaction.atomic():
        pros = list(_prospectos().values_list('pk', flat=True))
        eventos = list(_eventos(pros).values_list('pk', flat=True))
        Respuesta.objects.filter(formulario__in=_forms()).delete()
        Prospecto.objects.filter(pk__in=pros).delete()
        Evento.objects.filter(pk__in=eventos).delete()
        _forms().delete()
        # Prepas ficticias: solo si ya no tienen eventos ni prospectos.
        prepas = _prepas_demo().filter(eventos__isnull=True, prospectos__isnull=True)
        prepas.delete()
        usuarios = _usuarios(quien)
        n_us = usuarios.count()
        usuarios.delete()
        aviso = Configuracion.obtener('permisos.aviso_en_form') or {}
        if 'ejemplo.invalid' in (aviso.get('url') or ''):
            Configuracion.guardar('permisos.aviso_en_form', {}, quien)
    r = {'prospectos': len(pros), 'respuestas': inv['respuestas'], 'eventos': len(eventos), 'formularios': inv['formularios'],
         'usuarios': n_us, 'respaldo': getattr(respaldo, 'archivo', '')}
    auditoria.registrar('borrar_demo', None, r, quien)
    return r
