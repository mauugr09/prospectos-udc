"""
Eventos en preparatorias: a qué evento pertenece cada respuesta, QR permanentes y el reporte final.

¿Por qué los QR «no registraban»? El QR lleva el código del evento en un campo prellenado del Form
(«Código de evento»). Si el Form no tiene esa pregunta, el código se pierde y la respuesta llega sin evento.
Ahora, además del código, cada respuesta se asigna al evento por preparatoria y fecha:

  1. Código del evento en la respuesta (QR del evento o tarjeta familiar) → ese evento.
  2. Código permanente de una prepa (QR permanente, «P0012») → el evento de esa prepa ese día, si lo hay.
  3. Alumno cuya preparatoria (la que escribió) tiene un evento ese día → ese evento.
  4. Encuesta de padres (no pregunta prepa) el día de un evento → ese evento, solo si fue el ÚNICO evento del día.
  5. Alumno que no escribió una prepa reconocible → el único evento del día, solo si contestó durante su horario.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter

from django.db import transaction
from django.utils import timezone

from ..models import Cuestionario, EstadoRespuesta, Evento, Preparatoria, Respuesta

ACTIVOS = ('por_solicitar', 'solicitado', 'confirmado', 'realizado')


def _del_dia(fecha):
    return Evento.objects.select_related('promotor', 'preparatoria').filter(fecha=fecha, estado__in=ACTIVOS)


def _en_horario(e: Evento, momento) -> bool:
    if not e.hora_inicio:
        return False
    hora = timezone.localtime(momento).time()
    inicio = (dt.datetime.combine(e.fecha, e.hora_inicio) - dt.timedelta(minutes=30)).time()
    fin = (dt.datetime.combine(e.fecha, e.hora_fin or e.hora_inicio) + dt.timedelta(hours=2)).time()
    return inicio <= hora <= fin


def atribuir(cuestionario: str, datos, enviada_en) -> Evento | None:
    """El evento al que pertenece una respuesta (ver orden arriba)."""
    codigo = (datos.uno('evento') or '').strip().upper()
    if codigo:
        e = Evento.objects.select_related('promotor').filter(codigo=codigo).first()
        if e:
            return e
    fecha = timezone.localtime(enviada_en).date()
    del_dia = list(_del_dia(fecha))
    if not del_dia:
        return None
    prepa_qr = Preparatoria.por_codigo_qr(codigo)
    if prepa_qr:
        return next((e for e in del_dia if e.preparatoria_id == prepa_qr.pk), None)
    if cuestionario == Cuestionario.ALUMNO:
        prepa = Preparatoria.resolver(datos.uno('preparatoria'))
        if prepa:
            return next((e for e in del_dia if e.preparatoria_id == prepa.pk), None)
        return del_dia[0] if len(del_dia) == 1 and _en_horario(del_dia[0], enviada_en) else None
    return del_dia[0] if len(del_dia) == 1 else None


def reatribuir(desde=None) -> int:
    """Asigna evento a las respuestas guardadas que no lo tienen (las que llegaron antes de este cambio)."""
    from .importacion import DatosRespuesta
    from .inteligencia import recalcular
    qs = Respuesta.objects.filter(evento__isnull=True).exclude(estado=EstadoRespuesta.DESCARTADA).select_related('prospecto')
    if desde:
        qs = qs.filter(enviada_en__date__gte=desde)
    n, tocados = 0, set()
    for r in qs.iterator():
        datos = DatosRespuesta(r.cuestionario, (r.raw_json or {}).get('por_codigo') or {})
        e = atribuir(r.cuestionario, datos, r.enviada_en)
        if e:
            with transaction.atomic():
                Respuesta.objects.filter(pk=r.pk).update(evento=e, promotor=r.promotor or e.promotor)
                if r.prospecto_id:
                    tocados.add(r.prospecto_id)
            n += 1
    from ..models import Prospecto
    for p in Prospecto.objects.filter(pk__in=tocados, fusionado_en__isnull=True):
        recalcular(p)
    return n


# --------------------------------------------------------------------------- reporte final
def reporte(e: Evento, con_nombres: bool = False) -> dict:
    from ..models import Carrera, Prospecto
    resp = Respuesta.objects.filter(evento=e).exclude(estado=EstadoRespuesta.DESCARTADA)
    alumnos = resp.filter(cuestionario=Cuestionario.ALUMNO)
    familias = resp.filter(cuestionario=Cuestionario.TUTOR)
    ids = set(resp.exclude(prospecto=None).values_list('prospecto_id', flat=True))
    pros = Prospecto.objects.filter(pk__in=ids, fusionado_en__isnull=True).select_related('carrera')
    n_alumnos, n_familias, n_pros = alumnos.count(), familias.count(), pros.count()
    con_permiso = pros.filter(consentimiento=True)
    unidas = pros.filter(tiene_alumno=True, tiene_tutor=True).count()
    piden = con_permiso.filter(canal_informacion__in=['whatsapp', 'correo', 'si']).count()

    carreras = Counter()
    for ids_c in (p.carreras.values_list('id', flat=True) for p in con_permiso.prefetch_related('carreras')):
        carreras.update(ids_c)
    nombres = dict(Carrera.objects.filter(pk__in=carreras).values_list('pk', 'nombre'))
    top = [{'etiqueta': nombres.get(k, '—'), 'total': v} for k, v in carreras.most_common(8)]
    tope = max([c['total'] for c in top] or [1])
    for c in top:
        c['pct'] = round(100 * c['total'] / tope)

    modalidades = Counter(con_permiso.exclude(modalidad='').values_list('modalidad', flat=True))
    etiquetas_mod = dict(Prospecto._meta.get_field('modalidad').choices)
    planteles = Counter(con_permiso.exclude(plantel='').values_list('plantel', flat=True))
    from .. import catalogos

    por_hora = Counter(timezone.localtime(f).strftime('%H:00') for f in alumnos.values_list('enviada_en', flat=True))
    primero = alumnos.order_by('enviada_en').values_list('enviada_en', flat=True).first()
    ultimo = alumnos.order_by('-enviada_en').values_list('enviada_en', flat=True).first()

    promotores = Counter()
    for r in resp.select_related('promotor'):
        if r.promotor_id:
            promotores[r.promotor.get_full_name() or r.promotor.get_username()] += 1

    asistentes = e.alumnos_asistentes or None
    costo = float(e.costo) if e.costo else None
    return {
        'alumnos': n_alumnos, 'familias': n_familias, 'prospectos': n_pros, 'con_permiso': con_permiso.count(),
        'esperando': pros.filter(consentimiento=False, consentimiento_negado=False).count(),
        'unidas': unidas, 'piden_info': piden,
        'pct_piden': round(100 * piden / con_permiso.count()) if con_permiso.count() else None,
        'tasa': round(100 * n_alumnos / asistentes) if asistentes else None,
        'meta_pct': round(100 * n_alumnos / e.meta_registros) if e.meta_registros else None,
        'costo': costo, 'costo_por_registro': round(costo / n_alumnos, 2) if costo and n_alumnos else None,
        'costo_txt': f'${costo:,.2f}' if costo else '—',  # formato de México: $2,000.00
        'costo_registro_txt': f'${costo / n_alumnos:,.2f}' if costo and n_alumnos else '—',
        'carreras': top,
        'modalidades': [{'etiqueta': etiquetas_mod.get(k, k), 'total': v} for k, v in modalidades.most_common()],
        'planteles': [{'etiqueta': catalogos.PLANTELES_CORTO.get(k, k), 'total': v} for k, v in planteles.most_common()],
        'por_hora': sorted(por_hora.items()), 'primero': primero, 'ultimo': ultimo,
        'promotores': promotores.most_common(),
        'nombres': list(con_permiso.order_by('-score', 'nombre_aspirante')) if con_nombres else [],
    }
