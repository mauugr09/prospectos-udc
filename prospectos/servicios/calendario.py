"""
Calendario de Admisiones: en un solo lugar las visitas a prepas (Eventos), las actividades internas
(open house, exámenes, inscripciones, juntas…) y cuántas llamadas pendientes vencen cada día.

Los Eventos siguen viviendo en «Eventos y QR» (ahí están el QR, la solicitud y el reporte); aquí solo se ven y
se enlazan, para no tener dos lugares donde editar lo mismo.
"""

from __future__ import annotations

import calendar as cal
import datetime as dt
from collections import defaultdict

from django.db.models import Q
from django.utils import timezone

from ..models import Actividad, Evento, Seguimiento, TipoSeguimiento

MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
         'noviembre', 'diciembre']
DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']


def _tareas_abiertas():
    return Seguimiento.objects.filter(tipo=TipoSeguimiento.TAREA, completada_en__isnull=True, vence_en__isnull=False,
                                      prospecto__consentimiento=True, prospecto__anonimizado_en__isnull=True)


def _hora(h):
    return h.strftime('%H:%M') if h else ''


def entradas(desde: dt.date, hasta: dt.date, promotor=None) -> dict[dt.date, list[dict]]:
    """Lo que hay cada día entre dos fechas (inclusive), ya ordenado por hora."""
    dias: dict[dt.date, list[dict]] = defaultdict(list)
    eventos = Evento.objects.filter(fecha__range=(desde, hasta)).select_related('preparatoria', 'promotor')
    if promotor is not None:  # el promotor solo ve sus visitas, igual que en «Eventos y QR»
        eventos = eventos.filter(promotor=promotor)
    for e in eventos:
        dias[e.fecha].append({
            'clase': 'evento', 'estado': e.estado, 'titulo': str(e.preparatoria),
            'detalle': e.get_actividad_display(), 'estado_txt': e.get_estado_display(),
            'hora': _hora(e.hora_inicio), 'hora_fin': _hora(e.hora_fin), 'pk': e.pk,
            'quien': (e.promotor.get_full_name() or e.promotor.get_username()) if e.promotor else ''})
    actividades = Actividad.objects.filter(Q(fecha__range=(desde, hasta)) | Q(fecha__lt=desde, fecha_fin__gte=desde)) \
        .select_related('responsable')
    for a in actividades:
        for d in a.dias():
            if desde <= d <= hasta:
                dias[d].append({
                    'clase': 'actividad', 'tipo': a.tipo, 'titulo': a.titulo, 'detalle': a.get_tipo_display(),
                    'hora': _hora(a.hora_inicio), 'hora_fin': _hora(a.hora_fin), 'pk': a.pk, 'lugar': a.lugar,
                    'quien': (a.responsable.get_full_name() or a.responsable.get_username()) if a.responsable else '',
                    'varios_dias': bool(a.fecha_fin and a.fecha_fin > a.fecha), 'inicio': a.fecha, 'fin': a.fecha_fin})
    for v in dias.values():
        v.sort(key=lambda x: (x['hora'] or '99', x['titulo']))
    return dias


def tareas_por_dia(desde: dt.date, hasta: dt.date) -> dict[dt.date, int]:
    """Llamadas pendientes por día de vencimiento. Las ya vencidas se suman a hoy (si hoy está en el rango)."""
    hoy = timezone.localdate()
    res: dict[dt.date, int] = defaultdict(int)
    for v in _tareas_abiertas().values_list('vence_en', flat=True):
        d = timezone.localtime(v).date()
        if d < hoy:
            d = hoy
        if desde <= d <= hasta:
            res[d] += 1
    return res


def vencidas() -> int:
    return _tareas_abiertas().filter(vence_en__lt=timezone.now()).count()


def mes(anio: int, numero: int, promotor=None) -> dict:
    """La cuadrícula del mes (semanas de lunes a domingo, con los días de los meses vecinos para completarla)."""
    semanas = cal.Calendar(firstweekday=0).monthdatescalendar(anio, numero)
    desde, hasta = semanas[0][0], semanas[-1][-1]
    por_dia, tareas, hoy = entradas(desde, hasta, promotor), tareas_por_dia(desde, hasta), timezone.localdate()
    return {
        'nombre': f'{MESES[numero - 1].capitalize()} {anio}', 'dias_semana': DIAS,
        'semanas': [[{'fecha': d, 'del_mes': d.month == numero, 'hoy': d == hoy, 'pasado': d < hoy,
                      'cosas': por_dia.get(d, []), 'tareas': tareas.get(d, 0)} for d in s] for s in semanas],
        'anterior': (dt.date(anio, numero, 1) - dt.timedelta(days=1)).strftime('%Y-%m'),
        'siguiente': (dt.date(anio, numero, 28) + dt.timedelta(days=7)).strftime('%Y-%m'),
        'clave': f'{anio:04d}-{numero:02d}',
    }


def agenda(dias: int = 14, promotor=None) -> list[dict]:
    """Los próximos días que tienen algo, para la columna «Lo que viene»."""
    hoy = timezone.localdate()
    fin = hoy + dt.timedelta(days=dias - 1)
    por_dia, tareas = entradas(hoy, fin, promotor), tareas_por_dia(hoy, fin)
    res = []
    for i in range(dias):
        d = hoy + dt.timedelta(days=i)
        # Lo que dura varios días se anuncia una vez (el día que empieza, o hoy si ya empezó), no cada día.
        cosas = [c for c in por_dia.get(d, []) if not c.get('varios_dias') or d == max(c['inicio'], hoy)]
        if cosas or tareas.get(d):
            res.append({'fecha': d, 'hoy': i == 0, 'manana': i == 1, 'cosas': cosas, 'tareas': tareas.get(d, 0)})
    return res


# --------------------------------------------------------------------------- exportar (.ics)
def _esc(t: str) -> str:
    return (t or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\r', '').replace('\n', '\\n')


def _linea(t: str) -> str:
    """RFC 5545: líneas de máximo 75 octetos, las siguientes empiezan con un espacio."""
    b, partes = t.encode('utf-8'), []
    while len(b) > 75:
        corte = 75 if not partes else 74
        while corte and (b[corte] & 0xC0) == 0x80:  # no partir un carácter UTF-8 a la mitad
            corte -= 1
        partes.append(b[:corte].decode('utf-8'))
        b = b[corte:]
    partes.append(b.decode('utf-8'))
    return '\r\n '.join(partes)


def _momentos(fecha, inicio, fin, fecha_fin=None):
    if inicio:
        ini = dt.datetime.combine(fecha, inicio)
        ter = dt.datetime.combine(fecha_fin or fecha, fin) if fin else ini + dt.timedelta(hours=1)
        if ter <= ini:
            ter = ini + dt.timedelta(hours=1)
        f = '%Y%m%dT%H%M%S'
        return [f'DTSTART;TZID=America/Mexico_City:{ini:{f}}', f'DTEND;TZID=America/Mexico_City:{ter:{f}}']
    ultimo = (fecha_fin if fecha_fin and fecha_fin > fecha else fecha) + dt.timedelta(days=1)
    return [f'DTSTART;VALUE=DATE:{fecha:%Y%m%d}', f'DTEND;VALUE=DATE:{ultimo:%Y%m%d}']


def ics(desde: dt.date, hasta: dt.date, dominio: str = 'prospectos.udc', promotor=None) -> str:
    """Archivo .ics para importar en Google Calendar / Outlook. Es una copia: no se actualiza solo."""
    sello = timezone.now().strftime('%Y%m%dT%H%M%SZ')
    ls = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//UDC//Prospectos//ES', 'CALSCALE:GREGORIAN',
          'X-WR-CALNAME:Admisiones UDC', 'X-WR-TIMEZONE:America/Mexico_City']
    eventos = Evento.objects.filter(fecha__range=(desde, hasta)).exclude(estado='cancelado').select_related('preparatoria')
    if promotor is not None:
        eventos = eventos.filter(promotor=promotor)
    for e in eventos:
        ls += ['BEGIN:VEVENT', f'UID:evento-{e.pk}@{dominio}', f'DTSTAMP:{sello}',
               *_momentos(e.fecha, e.hora_inicio, e.hora_fin),
               f'SUMMARY:{_esc(f"{e.get_actividad_display()} · {e.preparatoria}")}',
               f'LOCATION:{_esc(str(e.preparatoria))}',
               f'DESCRIPTION:{_esc(f"Estado: {e.get_estado_display()}. {e.notas}".strip())}',
               'STATUS:' + ('CONFIRMED' if e.estado in ('confirmado', 'realizado') else 'TENTATIVE'), 'END:VEVENT']
    for a in Actividad.objects.filter(Q(fecha__range=(desde, hasta)) | Q(fecha__lt=desde, fecha_fin__gte=desde)):
        ls += ['BEGIN:VEVENT', f'UID:actividad-{a.pk}@{dominio}', f'DTSTAMP:{sello}',
               *_momentos(a.fecha, a.hora_inicio, a.hora_fin, a.fecha_fin if not a.hora_inicio else None),
               *([f'RRULE:FREQ=DAILY;COUNT={len(a.dias())}'] if a.hora_inicio and len(a.dias()) > 1 else []),
               f'SUMMARY:{_esc(a.titulo)}', f'LOCATION:{_esc(a.lugar)}', f'DESCRIPTION:{_esc(a.notas)}', 'END:VEVENT']
    ls.append('END:VCALENDAR')
    return '\r\n'.join(_linea(x) for x in ls) + '\r\n'
