"""
Dos pantallas para el día a día, en lugar de cinco que mostraban a las mismas personas:

  «Prospectos» (una lista, varias pestañas)
      Llamar hoy · Nuevos · Todos · Esperando permiso · Respuestas de los Forms
      Mismos filtros arriba; en cada fila: abrir/editar la ficha y, para administradores, dar de baja.
  «Por revisar»
      Familias (encuesta de padres ↔ alumno; pantalla existente) · Duplicados (la misma persona dos veces).
      Cada par se muestra UNA vez aunque haya propuestas en los dos sentidos.

«Dar de baja» anonimiza (seguridad.anonimizar): borra nombre, contactos y texto libre y queda en la bitácora. El
prospecto pasa a la pestaña «Bajas» con su motivo y deja de contar como interesado (reportables() lo excluye). No se borra el registro (regla del proyecto y de la ley de datos personales).
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import catalogos
from .models import (ACTIVOS, Cuestionario, Estatus, EstadoRespuesta, PosibleCoincidencia, Prospecto, Segmento,
                     TipoSeguimiento, etiqueta_segmento)
from .servicios import auditoria, inteligencia, reportes

PESTANAS = [
    ('llamar', 'Llamar hoy', 'support_agent', 'Aspirantes activos que aceptan contacto, del más prioritario al más olvidado.'),
    ('nuevos', 'Nuevos', 'new_releases', 'Llegaron en los últimos 7 días.'),
    ('todos', 'Todos', 'groups', 'Todos los aspirantes con permiso, también inscritos, descartados y los que no quieren información.'),
    ('permiso', 'Esperando permiso', 'hourglass_top', 'Menores de edad sin el permiso de su familia: no se usan hasta tenerlo.'),
    ('forms', 'Respuestas de los Forms', 'inbox', 'Cada envío de los Forms tal como llegó, con su estado.'),
    ('bajas', 'Bajas', 'person_off', 'Dados de baja: sin datos personales y fuera de las cifras de interesados. Aquí tienen su propia cuenta.'),
]
MOTIVOS_BAJA = [
    ('derecho_arco', 'Pidió que se borren sus datos'),
    ('registro_de_prueba', 'Es una prueba o datos basura'),
    ('otro', 'Otro motivo (escríbelo)'),
]
POR_PAGINA = 40


def _ctx(request, titulo, **kw):
    from django.contrib import admin
    return admin.site.each_context(request) | {'title': titulo, **kw}


def puede_dar_de_baja(usuario) -> bool:
    return bool(usuario.is_superuser)


def _visibles(request):
    qs = Prospecto.objects.utilizables()
    u = request.user
    if not u.is_superuser and u.has_perm('prospectos.ver_propios'):
        qs = qs.filter(Q(promotor=u) | Q(asesor=u))
    return qs


def _respuestas_visibles(request):
    from .models import Respuesta
    qs = Respuesta.objects.select_related('prospecto__preparatoria', 'prospecto__carrera', 'evento__preparatoria', 'formulario')
    u = request.user
    if not u.is_superuser and u.has_perm('prospectos.ver_propios'):
        qs = qs.filter(Q(promotor=u) | Q(prospecto__promotor=u))
    return qs


def _bajas_visibles(request):
    qs = Prospecto.objects.bajas()
    u = request.user
    if not u.is_superuser and u.has_perm('prospectos.ver_propios'):
        qs = qs.filter(Q(promotor=u) | Q(asesor=u))
    return qs


def _filtrar_prospectos(qs, f, usuario):
    if f.get('q'):
        q = f['q'].strip()
        qs = qs.filter(Q(nombre_aspirante__icontains=q) | Q(tutor_nombre__icontains=q) | Q(preparatoria__nombre__icontains=q))
    if f.get('plantel') in catalogos.PLANTELES:
        qs = qs.filter(plantel=f['plantel'])
    if f.get('canal') in ('whatsapp', 'correo'):
        qs = qs.filter(canal_informacion=f['canal'])
    if f.get('segmento') in Segmento.values:
        qs = qs.filter(segmentos__icontains=f'"{f["segmento"]}"')
    if f.get('estatus') in Estatus.values:
        qs = qs.filter(estatus=f['estatus'])
    if f.get('mios'):
        qs = qs.filter(asesor=usuario)
    if f.get('tareas'):
        qs = qs.filter(tareas__gt=0)
    if f.get('brecha'):
        qs = qs.filter(tiene_brecha=True)
    return qs


def _con_tareas(qs):
    return qs.annotate(tareas=Count('seguimientos', filter=Q(seguimientos__tipo=TipoSeguimiento.TAREA,
                                                             seguimientos__completada_en__isnull=True)))


def _base(request, ver):
    qs = _con_tareas(_visibles(request).select_related('preparatoria', 'carrera', 'asesor'))
    if ver == 'llamar':
        return (qs.filter(estatus__in=ACTIVOS, no_contactar=False)
                .order_by('-score', F('ultimo_contacto_en').asc(nulls_first=True)))
    if ver == 'nuevos':
        return qs.filter(creado_en__gte=timezone.now() - timedelta(days=7)).order_by('-creado_en')
    return qs.order_by('-creado_en')


def _fila_prospecto(p):
    from .admin import iniciales
    todos = p.segmentos or []
    p.segmentos_det = [(s, etiqueta_segmento(s)) for s in todos[:3]]
    p.segmentos_mas = len(todos) - len(p.segmentos_det)
    p.iniciales = iniciales(p.nombre_aspirante)
    p.quien = 'Alumno y familia' if p.tiene_alumno and p.tiene_tutor else ('Solo la familia' if p.tiene_tutor else 'Solo el alumno')
    return p


def _fila_respuesta(r):
    from .admin import iniciales
    etiqueta, tono, ayuda = reportes.explicar_estado(r)
    nombre = r.nombre_aspirante or (r.prospecto.nombre_aspirante if r.prospecto else 'Sin nombre')
    prepa = (r.prospecto.preparatoria if r.prospecto else None) or (r.evento.preparatoria if r.evento else None)
    partes = [str(prepa) if prepa else 'Sin preparatoria']
    if r.prospecto and r.prospecto.carrera:
        partes.append(str(r.prospecto.carrera))
    if r.evento:
        partes.append(f'evento {r.evento.codigo}')
    return {'r': r, 'nombre': nombre, 'iniciales': iniciales(nombre), 'estado': etiqueta, 'tono': tono, 'ayuda': ayuda,
            'detalle': ' · '.join(partes)}


@staff_member_required
def bandeja(request, ver=None):
    u = request.user
    if not u.has_perm('prospectos.view_prospecto'):
        raise PermissionDenied
    f = request.GET
    claves = [p[0] for p in PESTANAS]
    ver = ver if ver in claves else (f.get('ver') if f.get('ver') in claves else None)
    # Antes «Respuestas» filtraba por estado: ?estado=cuarentena era «esperando permiso».
    if ver == 'forms' and f.get('estado') == EstadoRespuesta.CUARENTENA and not f.get('_todas'):
        ver = 'permiso'
    puede_llamar = u.has_perm('prospectos.change_prospecto')
    if not ver:
        ver = 'llamar' if puede_llamar else 'todos'
    if ver == 'llamar' and not puede_llamar:
        raise PermissionDenied

    cuentas = {
        'llamar': _base(request, 'llamar').count() if puede_llamar else None,
        'nuevos': _base(request, 'nuevos').count(),
        'permiso': _respuestas_visibles(request).filter(estado=EstadoRespuesta.CUARENTENA).count(),
        'bajas': _bajas_visibles(request).count(),
    }
    pestanas = [{'clave': c, 'titulo': t, 'icono': i, 'ayuda': a, 'n': cuentas.get(c),
                 'url': reverse('prospectos:prospectos_ver', args=[c])}
                for c, t, i, a in PESTANAS if c != 'llamar' or puede_llamar]
    actual = next(p for p in pestanas if p['clave'] == ver)

    ctx = {'ver': ver, 'pestanas': pestanas, 'actual': actual, 'f': f, 'es_respuestas': ver in ('permiso', 'forms'),
           'es_bajas': ver == 'bajas',
           'planteles': catalogos.PLANTELES_CORTO.items(), 'segmentos': [s for s in Segmento.choices],
           'estatuses': Estatus.choices, 'puede_baja': puede_dar_de_baja(u), 'motivos_baja': MOTIVOS_BAJA,
           'hay_tutor': reportes.formulario_activo(Cuestionario.TUTOR), 'puede_editar': puede_llamar,
           'filtros_activos': any(f.get(k) for k in ('q', 'plantel', 'canal', 'segmento', 'estatus', 'mios', 'tareas', 'brecha', 'tipo', 'estado'))}

    if ctx['es_bajas']:
        qs = _bajas_visibles(request).select_related('preparatoria', 'carrera').order_by('-baja_en')
        todas = qs
        if f.get('motivo') in dict(MOTIVOS_BAJA):
            qs = qs.filter(baja_motivo=f['motivo'])
        if f.get('plantel') in catalogos.PLANTELES:
            qs = qs.filter(plantel=f['plantel'])
        if f.get('q'):
            qs = qs.filter(preparatoria__nombre__icontains=f['q'].strip())
        pagina = Paginator(qs, POR_PAGINA).get_page(f.get('pagina'))
        etiquetas = {k: e.replace(' (escríbelo)', '') for k, e in MOTIVOS_BAJA}
        ctx['filas'] = [{'p': p, 'motivo': etiquetas.get(p.baja_motivo, 'Sin motivo')} for p in pagina]
        conteo = dict(todas.values_list('baja_motivo').annotate(n=Count('id')))
        inicio_mes = timezone.localdate().replace(day=1)
        ctx['resumen_bajas'] = {'total': todas.count(), 'mes': todas.filter(baja_en__date__gte=inicio_mes).count(),
                                'motivos': [(k, etiquetas[k], conteo.get(k, 0)) for k, _ in MOTIVOS_BAJA]}
        ctx['filtros_activos'] = any(f.get(k) for k in ('q', 'plantel', 'motivo'))
    elif ctx['es_respuestas']:
        qs = _respuestas_visibles(request).prefetch_related('items').order_by('-enviada_en')
        if ver == 'permiso':
            qs = qs.filter(estado=EstadoRespuesta.CUARENTENA)
        elif f.get('estado') in EstadoRespuesta.values:
            qs = qs.filter(estado=f['estado'])
        if f.get('tipo') in (Cuestionario.ALUMNO, Cuestionario.TUTOR):
            qs = qs.filter(cuestionario=f['tipo'])
        if f.get('q'):
            qs = qs.filter(Q(nombre_aspirante__icontains=f['q']) | Q(prospecto__nombre_aspirante__icontains=f['q']))
        pagina = Paginator(qs, POR_PAGINA).get_page(f.get('pagina'))
        ctx['filas'] = [_fila_respuesta(r) for r in pagina]
        if ver == 'forms':
            conteos = dict(_respuestas_visibles(request).values_list('estado').annotate(n=Count('id')))
            ctx['estados'] = [(k, *reportes.ESTADOS_LEGIBLES[k][:2], conteos.get(k, 0)) for k in
                              (EstadoRespuesta.VALIDA, EstadoRespuesta.CUARENTENA, EstadoRespuesta.SIN_CONSENTIMIENTO,
                               EstadoRespuesta.DESCARTADA)]
    else:
        qs = _filtrar_prospectos(_base(request, ver), f, u)
        pagina = Paginator(qs, POR_PAGINA).get_page(f.get('pagina'))
        ctx['filas'] = [_fila_prospecto(p) for p in pagina]
        if ver == 'llamar':
            ctx['no_quieren'] = _visibles(request).filter(estatus__in=ACTIVOS, no_contactar=True).count()
    ctx['pagina'] = pagina
    sin_pagina = f.copy()
    sin_pagina.pop('pagina', None)
    ctx['qs_sin_pagina'] = sin_pagina.urlencode()
    return render(request, 'prospectos/prospectos.html', _ctx(request, 'Prospectos', **ctx))


@staff_member_required
@require_POST
def dar_de_baja(request, pk):
    """Anonimiza a un prospecto (y sus respuestas). Irreversible: se confirma escribiendo BAJA."""
    from .servicios import seguridad
    if not puede_dar_de_baja(request.user):
        raise PermissionDenied
    p = get_object_or_404(Prospecto, pk=pk, anonimizado_en__isnull=True)
    volver = request.POST.get('volver') or reverse('prospectos:prospectos')
    if not volver.startswith('/') or volver.startswith('//'):
        volver = reverse('prospectos:prospectos')
    motivo = request.POST.get('motivo')
    nota = (request.POST.get('nota') or '').strip()[:300]
    if motivo not in dict(MOTIVOS_BAJA) or (motivo == 'otro' and not nota):
        messages.error(request, 'Elige el motivo de la baja (y escríbelo si es «Otro»).')
        return redirect(volver)
    if (request.POST.get('confirmo') or '').strip().upper() != 'BAJA':
        messages.error(request, 'Para confirmar, escribe BAJA en el cuadro.')
        return redirect(volver)
    nombre = p.nombre_aspirante
    seguridad.anonimizar(p, motivo, descartar_respuestas=True)
    Prospecto.objects.filter(pk=p.pk).update(baja_en=timezone.now(), baja_motivo=motivo)  # cifra aparte, fuera de interesados
    auditoria.registrar('dar_de_baja', p, {'motivo': motivo, 'nota': nota}, request=request)
    messages.success(request, f'{nombre} quedó dado(a) de baja: se borraron sus datos personales y pasó a la pestaña «Bajas». Ya no cuenta como interesado.')
    return redirect(volver)


# --------------------------------------------------------------------------- Por revisar
def duplicados_pendientes():
    """Propuestas de «misma persona» (no las de familia), una por par aunque existan en los dos sentidos."""
    from .servicios import familias
    qs = (PosibleCoincidencia.objects.filter(estado='pendiente', prospecto__fusionado_en__isnull=True,
                                             candidato__fusionado_en__isnull=True, prospecto__anonimizado_en__isnull=True,
                                             candidato__anonimizado_en__isnull=True)
          .exclude(motivo__startswith=familias.MOTIVO)
          .select_related('prospecto__preparatoria', 'candidato__preparatoria', 'prospecto__carrera', 'candidato__carrera')
          .order_by('-similitud', '-creado_en'))
    pares: dict[tuple[int, int], dict] = {}
    for c in qs:
        clave = tuple(sorted((c.prospecto_id, c.candidato_id)))
        if clave in pares:
            pares[clave]['ids'].append(c.pk)
            continue
        # El que queda es el más antiguo (el que ya estaba); el nuevo se integra a él.
        viejo, nuevo = sorted((c.prospecto, c.candidato), key=lambda p: (p.creado_en, p.pk))
        pares[clave] = {'ids': [c.pk], 'queda': viejo, 'sale': nuevo, 'puntos': round(c.similitud * 100),
                        'motivo': c.motivo, 'nivel': 'alta' if c.similitud >= .85 else ('media' if c.similitud >= .6 else 'baja')}
    return list(pares.values())


def contar_por_revisar(request) -> int:
    from .servicios import familias
    if not request.user.has_perm('prospectos.resolver_coincidencias'):
        return 0
    return familias.familias_pendientes() + len(duplicados_pendientes())


def badge_por_revisar(request):
    return contar_por_revisar(request) or None


def pestanas_revisar(actual: str) -> list[dict]:
    from .servicios import familias
    return [{'clave': 'familias', 'titulo': 'Familias por unir', 'icono': 'family_restroom', 'n': familias.familias_pendientes(),
             'url': reverse('prospectos:familias'), 'activa': actual == 'familias',
             'ayuda': 'Encuestas de padres que hay que unir con el cuestionario de su hijo(a).'},
            {'clave': 'duplicados', 'titulo': 'Duplicados', 'icono': 'join_inner', 'n': len(duplicados_pendientes()),
             'url': reverse('prospectos:duplicados'), 'activa': actual == 'duplicados',
             'ayuda': 'La misma persona registrada dos veces (contestó dos veces o con datos distintos).'}]


@staff_member_required
def revisar(request):
    if not request.user.has_perm('prospectos.resolver_coincidencias'):
        raise PermissionDenied
    from .servicios import familias
    if not familias.familias_pendientes() and duplicados_pendientes():
        return redirect('prospectos:duplicados')
    return redirect('prospectos:familias')


@staff_member_required
def duplicados(request):
    if not request.user.has_perm('prospectos.resolver_coincidencias'):
        raise PermissionDenied
    if request.method == 'POST':
        ids = [x for x in request.POST.getlist('propuesta') if x.isdigit()]
        props = list(PosibleCoincidencia.objects.filter(pk__in=ids, estado='pendiente').select_related('prospecto', 'candidato'))
        if not props:
            messages.error(request, 'Ese par ya se resolvió.')
        elif request.POST.get('accion') == 'unir':
            queda, sale = sorted((props[0].prospecto, props[0].candidato), key=lambda p: (p.creado_en, p.pk))
            try:
                inteligencia.fusionar(queda, sale, request.user)
                messages.success(request, f'Listo: «{sale.nombre_aspirante}» quedó dentro de la ficha de «{queda.nombre_aspirante}».')
            except inteligencia.NoFusionable as e:
                messages.error(request, str(e))
        elif request.POST.get('accion') == 'distintas':
            for c in props:
                inteligencia.rechazar(c, request.user)
            messages.success(request, 'Marcadas como personas distintas. No se volverán a proponer.')
        return redirect(request.get_full_path())

    pares = duplicados_pendientes()
    q = (request.GET.get('q') or '').strip().lower()
    nivel = request.GET.get('nivel')
    if q:
        pares = [x for x in pares if q in x['queda'].nombre_aspirante.lower() or q in x['sale'].nombre_aspirante.lower()]
    if nivel in ('alta', 'media', 'baja'):
        pares = [x for x in pares if x['nivel'] == nivel]
    for x in pares:
        for lado in ('queda', 'sale'):
            _fila_prospecto(x[lado])
    return render(request, 'prospectos/duplicados.html', _ctx(
        request, 'Por revisar', pares=pares, q=request.GET.get('q', ''), nivel=nivel or '',
        pestanas_revisar=pestanas_revisar('duplicados')))

