"""
Kuali, el asistente: motor PROPIO, sin inteligencia artificial externa (ver decisiones 51 a 54).

Todo corre en la computadora del sistema, es gratis y funciona sin internet:
  - kuali.py entiende la pregunta con reglas (qué se pregunta, periodo, plantel, carrera, prepa, agrupación…),
    recuerda el contexto de la conversación y redacta la respuesta con plantillas;
  - analitica.py calcula las cifras (con el periodo anterior, partes del total, tasas y enlaces);
  - este módulo tiene lo común: ayuda desde el manual, perfil de la ficha y las propuestas de acción.

Kuali nunca inventa una cifra: todo número sale de una consulta. Y no cambia nada solo: crear una visita, una
actividad o asignar asesor se PROPONE y la persona confirma viendo el detalle; lo confirmado queda en la bitácora.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone

from ..models import (ACTIVOS, Actividad, Carrera, Configuracion, Estatus, Evento, Plantel, Preparatoria, Prospecto,
                      Segmento, Seguimiento, TipoSeguimiento, etiqueta_segmento)
from . import auditoria, texto

log = logging.getLogger('prospectos.asistente')
MINIMO_GRUPO = 3
SIN_ENVIAR = {'preparatoria', 'consentimiento_aviso_privacidad', 'evento', 'promotor', 'token_familia', 'edad'}
_VACIAS = set('que cual cuales como donde cuando para por con los las del una uno unos unas este esta estos hago hace puedo '
              'quiero dame dime significa sirve tengo hay'.split())


class PreguntaRechazada(Exception):
    pass


def _aware(d: date, fin=False):
    return timezone.make_aware(datetime.combine(d, time.max if fin else time.min))


def preguntar(user, mensaje: str, memoria: dict | None = None, contexto: dict | None = None) -> dict:
    """Una vuelta de conversación con el motor propio. Ver kuali.responder."""
    from . import kuali
    mensaje = (mensaje or '').strip()[:1500]
    if not mensaje:
        raise PreguntaRechazada('Escribe una pregunta.')
    r = kuali.responder(user, mensaje, memoria or {}, contexto or {})
    auditoria.registrar('asistente', None, {'entendi': r['intencion'], 'propuestas': len(r['propuestas']),
                                            'ficha': bool((contexto or {}).get('ficha'))}, user)
    return r


NOMBRE_OMISION = 'Kuali'  # «bueno» en náhuatl; se cambia en Configuración → Asistente


def nombre_mascota() -> str:
    return (Configuracion.obtener('asistente.mascota_nombre') or NOMBRE_OMISION)[:24]


def _fecha(v, defecto: date) -> date:
    try:
        return date.fromisoformat(str(v)[:10]) if v else defecto
    except ValueError:
        return defecto


def _rango(args) -> tuple[date, date]:
    hoy = timezone.localdate()
    return _fecha(args.get('desde'), hoy - timedelta(days=29)), _fecha(args.get('hasta'), hoy)


def h_embudo(user, args) -> dict:
    from . import analitica as A
    desde, hasta = A.periodo(args)
    qs, desc, params = A.filtrar(A.base(user).filter(creado_en__range=(A._aware(desde), A._aware(hasta, True))), args)
    conteo = dict(qs.values_list('estatus').annotate(n=Count('id')).order_by())
    total = qs.count()
    etapas, acumulado = [], total
    for e in Estatus:
        n = conteo.get(e.value, 0)
        etapas.append({'estatus': e.label, 'n': A._oculto(n) if n else 0, 'pct': round(n / total * 100) if total else None})
    llegaron = {e.label: sum(conteo.get(x.value, 0) for x in list(Estatus)[i:5]) for i, e in enumerate(list(Estatus)[:5])}
    return {'periodo': A._rango_txt(desde, hasta), 'filtros': desc or 'ninguno', 'total': total, 'embudo': etapas,
            'llegaron_al_menos_a': llegaron,
            'como_se_calculo': f'Aspirantes con permiso registrados {A._rango_txt(desde, hasta)}, según la etapa en que están hoy. '
                               '«Llegaron al menos a» suma esa etapa y las siguientes (sin descartados).',
            'enlace_a_la_lista': A.enlace(params, desde, hasta)}


def _secciones_manual() -> list[tuple[str, str]]:
    secciones = []
    for nombre in ('manual-usuario.md', 'manual-instalacion-operacion.md'):
        ruta = Path(settings.BASE_DIR) / 'docs' / nombre
        if not ruta.is_file():
            continue
        actual, cuerpo = None, []
        for linea in ruta.read_text(encoding='utf-8').splitlines():
            if linea.startswith(('## ', '### ')):
                if actual:
                    secciones.append((actual, '\n'.join(cuerpo)))
                actual, cuerpo = linea.lstrip('# ').strip(), []
            elif actual and not linea.startswith('!['):
                cuerpo.append(linea)
        if actual:
            secciones.append((actual, '\n'.join(cuerpo)))
    return [(t, _desenvolver(c)) for t, c in secciones]


def _desenvolver(md: str) -> str:
    """Une los renglones partidos del markdown (párrafos y viñetas) y quita *cursivas* y tablas."""
    salida = []
    encabezado_tabla = True
    for linea in md.splitlines():
        l = linea.rstrip()
        if l.strip().startswith('|'):
            celdas = [c.strip() for c in l.strip().strip('|').split('|')]
            if all(re.fullmatch(r':?-{2,}:?', c) for c in celdas if c):
                continue
            if encabezado_tabla:
                encabezado_tabla = False
                continue  # la fila de títulos de la tabla
            l = f'- {celdas[0]}: ' + ' — '.join(c for c in celdas[1:] if c)
        else:
            encabezado_tabla = True
        nuevo_bloque = not l.strip() or re.match(r'\s*([-*•>|#]|\d+[.)])\s', l + ' ')
        if salida and not nuevo_bloque and salida[-1].strip():
            salida[-1] += ' ' + l.strip()
        else:
            salida.append(l)
    texto_plano = '\n'.join(salida)
    texto_plano = re.sub(r'(?<!\*)\*(?!\*)([^*\n]+)(?<!\*)\*(?!\*)', r'\1', texto_plano)
    return re.sub(r'\n{3,}', '\n\n', texto_plano).strip()


def buscar_ayuda(tema: str, maximo: int = 3) -> list[dict]:
    palabras = {texto._variantes(p) for p in texto.normalizar(tema).split() if len(p) >= 3 and p not in _VACIAS}
    palabras |= {p[:-1] for p in palabras if len(p) > 5 and p.endswith('s')}  # plurales
    puntuadas = []
    for titulo, cuerpo in _secciones_manual():
        t, c = texto.normalizar(titulo), texto.normalizar(cuerpo)
        puntos = sum(3 * (p in t) + c.count(p) for p in palabras)
        if puntos:
            puntuadas.append((puntos, titulo, cuerpo.strip()[:2500]))
    puntuadas.sort(key=lambda x: -x[0])
    return [{'titulo': t, 'texto': c} for _, t, c in puntuadas[:maximo]]


def h_perfil(user, args, contexto) -> dict:
    """Solo categorías del catálogo del aspirante abierto en pantalla. Nada que lo identifique."""
    pk = (contexto or {}).get('ficha')
    if not pk:
        return {'error': 'No hay una ficha abierta. Pide a la persona que abra la ficha del aspirante.'}
    if not user.has_perm('prospectos.view_prospecto'):
        return {'error': 'Tu rol no permite ver fichas.'}
    qs = Prospecto.objects.filter(pk=pk, fusionado_en__isnull=True, anonimizado_en__isnull=True)
    if user.has_perm('prospectos.ver_propios') and not user.is_superuser:
        qs = qs.filter(promotor=user)
    p = qs.prefetch_related('carreras').first()
    if not p:
        return {'error': 'No se encontró la ficha.'}
    if not p.consentimiento:
        return {'error': 'Este aspirante no tiene permiso todavía: no se le debe contactar.'}
    if p.no_contactar:
        return {'error': 'Este aspirante pidió no recibir información: no se le debe contactar.'}
    dias = (timezone.now() - p.ultimo_contacto_en).days if p.ultimo_contacto_en else None
    from .reportes import comparativo
    temas = []
    from ..models import Pregunta
    # Solo preguntas con opciones del catálogo: nunca texto libre (ahí puede haber nombres, la prepa o instrucciones).
    cerradas = set(Pregunta.objects.filter(tipo__in=['opcion', 'multiple', 'si_no']).values_list('codigo', flat=True)) - SIN_ENVIAR
    try:
        for tema in comparativo(p).get('temas', []):
            for f in tema.get('filas', []):
                if f.get('codigo') in cerradas and not f.get('abierta'):
                    temas.append({'pregunta': str(f.get('etiqueta', ''))[:60], 'alumno': ', '.join(map(str, f.get('alumno') or []))[:120],
                                  'familia': ', '.join(map(str, f.get('tutor') or []))[:120], 'coinciden': bool(f.get('coinciden'))})
    except Exception:  # noqa: BLE001 - el perfil sirve aunque falle el comparativo
        log.exception('Perfil sin comparativo')
        temas = []
    return {
                'quien_contesto': 'alumno y familia' if p.tiene_alumno and p.tiene_tutor else 'solo el alumno' if p.tiene_alumno else 'solo la familia',
        'carreras': [c.nombre for c in p.carreras.all()][:3], 'modalidad': p.get_modalidad_display() if p.modalidad else None,
        'plantel': p.get_plantel_display() if p.plantel else None, 'prefiere': p.get_canal_informacion_display() if p.canal_informacion else None,
        'grupos': [etiqueta_segmento(s) for s in p.segmentos], 'prioridad': p.score, 'estatus': p.get_estatus_display(),
        'diferencias_con_la_familia': [b.get('mensaje', '')[:120] for b in (p.brechas or [])][:4],
        'dias_sin_contacto': dias, 'contactos_previos': p.seguimientos.filter(tipo__in=[TipoSeguimiento.LLAMADA, TipoSeguimiento.WHATSAPP,
                                                                                         TipoSeguimiento.CORREO, TipoSeguimiento.VISITA]).count(),
        'respuestas_por_tema': [t for t in temas if t['alumno'] or t['familia']][:20],
    }


# --- acciones: solo se proponen; se ejecutan al confirmar


def _usuario_por_nombre(valor: str):
    v = (valor or '').strip()
    if not v:
        return None
    U = get_user_model()
    exacto = U.objects.filter(is_active=True, is_staff=True).filter(Q(username__iexact=v) | Q(email__iexact=v)).first()
    if exacto:
        return exacto
    n = texto.normalizar(v)
    cands = [u for u in U.objects.filter(is_active=True, is_staff=True)
             if n and (n in texto.normalizar(u.get_full_name()) or n == texto.normalizar(u.first_name))]
    return cands[0] if len(cands) == 1 else None


def _hora(v):
    try:
        return time.fromisoformat(str(v)) if v else None
    except ValueError:
        return None


def proponer(user, tipo: str, args) -> dict:
    """Valida y guarda la propuesta; devuelve lo que la IA puede saber (sin nombres de aspirantes)."""
    hoy = timezone.localdate()
    if tipo == 'crear_visita':
        if not user.has_perm('prospectos.add_evento'):
            return {'error': 'Tu rol no permite crear visitas.'}
        prepa = Preparatoria.resolver(args.get('preparatoria'))
        if not prepa:
            return {'error': 'No encontré esa preparatoria. Pide el nombre como aparece en Preparatorias.'}
        fecha = _fecha(args.get('fecha'), None)
        if not fecha or fecha < hoy:
            return {'error': 'Falta la fecha (AAAA-MM-DD) y debe ser de hoy en adelante.'}
        promotor = _usuario_por_nombre(args.get('promotor')) if args.get('promotor') else None
        if args.get('promotor') and not promotor:
            return {'error': 'No encontré a ese promotor (o hay varios con ese nombre). Pide su correo.'}
        actividad = args.get('actividad') if args.get('actividad') in dict(Evento._meta.get_field('actividad').choices) else 'platica'
        datos = {'preparatoria': prepa.pk, 'fecha': str(fecha), 'hora_inicio': str(_hora(args.get('hora_inicio')) or ''),
                 'actividad': actividad, 'promotor': promotor.pk if promotor else None}
        resumen = {'preparatoria': prepa.nombre, 'fecha': str(fecha), 'actividad': actividad}
    elif tipo == 'crear_actividad':
        if not user.has_perm('prospectos.add_actividad'):
            return {'error': 'Tu rol no permite crear actividades del calendario.'}
        fecha = _fecha(args.get('fecha'), None)
        titulo = (args.get('titulo') or '').strip()[:150]
        if not fecha or not titulo:
            return {'error': 'Falta el título o la fecha (AAAA-MM-DD).'}
        tipo_act = args.get('tipo') if args.get('tipo') in dict(Actividad.TIPOS) else 'otro'
        datos = {'titulo': titulo, 'tipo': tipo_act, 'fecha': str(fecha), 'hora_inicio': str(_hora(args.get('hora_inicio')) or ''),
                 'lugar': (args.get('lugar') or '')[:150]}
        resumen = {'titulo': titulo, 'fecha': str(fecha), 'tipo': tipo_act}
    elif tipo == 'asignar_asesor':
        if not user.has_perm('prospectos.change_prospecto'):
            return {'error': 'Tu rol no permite asignar asesores.'}
        asesor = _usuario_por_nombre(args.get('asesor'))
        if not asesor:
            return {'error': 'No encontré a ese asesor (o hay varios con ese nombre). Pide su correo.'}
        maximo = max(1, min(int(args.get('maximo') or 20), 50))
        qs = Prospecto.objects.utilizables().filter(estatus__in=ACTIVOS, no_contactar=False)
        if args.get('solo_sin_asesor', True):
            qs = qs.filter(asesor__isnull=True)
        from . import analitica as A
        qs = A.filtrar(qs, args)[0].order_by('-score', 'creado_en')
        ids = list(qs.values_list('pk', flat=True)[:maximo])
        if not ids:
            return {'error': 'Ningún aspirante cumple esos filtros.'}
        datos = {'asesor': asesor.pk, 'ids': ids}
        resumen = {'asesor': asesor.get_full_name() or asesor.get_username(), 'aspirantes': len(ids)}
    else:
        return {'error': 'Acción no permitida.'}
    return {'propuesta': {'id': uuid.uuid4().hex[:12], 'tipo': tipo, 'datos': datos}, 'para_la_ia': {
        'estado': 'propuesta lista; la persona debe revisarla y pulsar Confirmar. Todavía NO se hizo.', **resumen}}


def detalle_propuesta(p: dict) -> dict:
    """Lo que se muestra en la tarjeta de confirmación (se arma en la computadora, con nombres; no va a la IA)."""
    d = p['datos']
    if p['tipo'] == 'crear_visita':
        prepa = Preparatoria.objects.get(pk=d['preparatoria'])
        U = get_user_model()
        prom = U.objects.filter(pk=d['promotor']).first() if d['promotor'] else None
        return {'titulo': 'Crear visita', 'icono': 'event', 'lineas': [
            f'Preparatoria: {prepa.nombre}', f"Fecha: {d['fecha']}" + (f" a las {d['hora_inicio'][:5]}" if d['hora_inicio'] else ''),
            f"Actividad: {dict(Evento._meta.get_field('actividad').choices)[d['actividad']]}",
            f"Promotor: {prom.get_full_name() or prom.get_username()}" if prom else 'Promotor: sin asignar']}
    if p['tipo'] == 'crear_actividad':
        return {'titulo': 'Agregar al calendario', 'icono': 'calendar_add_on', 'lineas': [
            d['titulo'], f"Tipo: {dict(Actividad.TIPOS)[d['tipo']]}",
            f"Fecha: {d['fecha']}" + (f" a las {d['hora_inicio'][:5]}" if d['hora_inicio'] else ''), *([f"Lugar: {d['lugar']}"] if d['lugar'] else [])]}
    U = get_user_model()
    a = U.objects.get(pk=d['asesor'])
    nombres = list(Prospecto.objects.filter(pk__in=d['ids']).order_by('-score').values_list('nombre_aspirante', 'score'))
    return {'titulo': f"Asignar {len(nombres)} aspirantes a {a.get_full_name() or a.get_username()}", 'icono': 'assignment_ind',
            'lineas': [f'{n} · prioridad {s}' for n, s in nombres]}


def ejecutar(user, p: dict) -> str:
    d = p['datos']
    if p['tipo'] == 'crear_visita':
        if not user.has_perm('prospectos.add_evento'):
            raise PermissionError
        ev = Evento.objects.create(preparatoria_id=d['preparatoria'], fecha=date.fromisoformat(d['fecha']),
                                   hora_inicio=_hora(d['hora_inicio']), actividad=d['actividad'], promotor_id=d['promotor'])
        auditoria.registrar('asistente_crear_visita', ev, {'propuesta': p['id']}, user)
        return f'Visita creada: {ev}.'
    if p['tipo'] == 'crear_actividad':
        if not user.has_perm('prospectos.add_actividad'):
            raise PermissionError
        act = Actividad.objects.create(titulo=d['titulo'], tipo=d['tipo'], fecha=date.fromisoformat(d['fecha']),
                                       hora_inicio=_hora(d['hora_inicio']), lugar=d['lugar'], creado_por=user)
        auditoria.registrar('asistente_crear_actividad', act, {'propuesta': p['id']}, user)
        return f'Agregado al calendario: {act.titulo} ({act.fecha:%d/%m/%Y}).'
    if p['tipo'] == 'asignar_asesor':
        if not user.has_perm('prospectos.change_prospecto'):
            raise PermissionError
        a = get_user_model().objects.get(pk=d['asesor'])
        n = Prospecto.objects.filter(pk__in=d['ids']).update(asesor=a)
        auditoria.registrar('asistente_asignar', None, {'propuesta': p['id'], 'asesor_id': a.pk, 'prospectos': d['ids']}, user)
        from . import avisos
        if a.pk != user.pk and n:
            hoy = timezone.localdate().isoformat()
            from django.urls import reverse
            avisos.avisar(a, 'asignado', f'asignado:{hoy}', f'Te asignaron {n} aspirantes', 'Revisa tu lista y haz el primer contacto.',
                          reverse('admin:prospectos_prospecto_changelist') + f'?asesor__id__exact={a.pk}', cantidad=n, acumular=True)
        return f'Se asignaron {n} aspirantes a {a.get_full_name() or a.get_username()}.'
    raise ValueError('Acción desconocida')


# --------------------------------------------------------------------------- la conversación


def _visual(herramienta: str, res) -> dict | None:
    """Datos para la gráfica de la burbuja: salen del sistema, no del texto de la IA."""
    if not isinstance(res, dict):
        return None
    if herramienta == 'consultar_cifras' and res.get('grupos'):
        filas = [{'etiqueta': g['grupo'], 'valor': g['n'] if isinstance(g['n'], int) else None,
                  'antes': g.get('periodo_anterior') if isinstance(g.get('periodo_anterior'), int) else None}
                 for g in res['grupos'][:8]]
        return {'tipo': 'barras', 'titulo': f"{res['que_se_conto'].capitalize()} · {res['periodo']}", 'filas': filas,
                'total': res['total'], 'enlace': res.get('enlace_a_la_lista'),
                'anterior': (res.get('periodo_anterior') or {}).get('total')}
    if herramienta == 'conversion' and res.get('grupos'):
        return {'tipo': 'porcentajes', 'titulo': f"Contactados o más · {res['periodo']}", 'enlace': res.get('enlace_a_la_lista'),
                'filas': [{'etiqueta': g['grupo'], 'valor': g['contactados_o_mas_pct'], 'n': g['aspirantes'], 'confiable': g['confiable']}
                          for g in res['grupos'][:8]]}
    if herramienta == 'embudo' and res.get('embudo'):
        return {'tipo': 'barras', 'titulo': f"Embudo · {res['periodo'] if 'periodo' in res else ''}".strip(' ·'),
                'filas': [{'etiqueta': e['estatus'], 'valor': e['n']} for e in res['embudo']], 'total': res.get('total')}
    if herramienta == 'pendientes':
        return {'tipo': 'pendientes', 'titulo': 'Pendientes de hoy',
                'filas': [{'etiqueta': x['que'], 'valor': x['n'], 'enlace': x['enlace']} for x in res['pendientes'] if x['n']]}
    return None
