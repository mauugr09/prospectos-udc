"""
Consultas de análisis para el asistente. Devuelven cifras agregadas CON CONTEXTO (contra el periodo anterior, qué parte
del total es cada grupo, tasas de avance), cómo se calculó cada una en palabras y un enlace a la lista exacta en el
programa. Nunca devuelven datos que identifiquen a una persona: los grupos pequeños se ocultan y las tasas con muy pocos
casos se marcan como poco confiables.
"""

from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import urlencode

from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from ..models import (ACTIVOS, Carrera, Estatus, Evento, PosibleCoincidencia, Preparatoria, Prospecto, Seguimiento,
                      TipoSeguimiento, etiqueta_segmento, Plantel)
from . import texto

MINIMO_GRUPO = 3     # menos de esto se muestra como «menos de 3»
MINIMO_TASA = 8      # con menos casos, una tasa no dice nada: se marca
CONTACTOS = [TipoSeguimiento.LLAMADA, TipoSeguimiento.WHATSAPP, TipoSeguimiento.CORREO, TipoSeguimiento.VISITA]
AVANZO = [Estatus.CONTACTADO, Estatus.OPEN_HOUSE, Estatus.SOLICITO, Estatus.INSCRITO]
METRICAS = {
    'aspirantes': 'aspirantes nuevos con permiso',
    'inscritos': 'aspirantes nuevos que ya están marcados como inscritos',
    'por_llamar': 'aspirantes activos que se pueden llamar hoy',
    'esperando_permiso': 'menores esperando el permiso de su familia',
    'contactos': 'contactos registrados (llamadas, WhatsApp, correos, visitas)',
}

# dimensión → (campo en la base, cómo se lee, parámetro de la lista del programa)
DIMENSIONES = {
    'plantel': ('plantel', lambda v: dict(Plantel.choices).get(v, 'Sin plantel'), 'plantel__exact'),
    'carrera': ('carrera__nombre', lambda v: v or 'Sin carrera', None),
    'preparatoria': ('preparatoria__nombre', lambda v: v or 'Sin preparatoria', None),
    'municipio': ('preparatoria__municipio', lambda v: v or 'Sin municipio', None),
    'estatus': ('estatus', lambda v: dict(Estatus.choices).get(v, v), 'estatus__exact'),
    'grupo': ('segmento_principal', lambda v: etiqueta_segmento(v) if v else 'Sin grupo', None),
    'canal': ('canal_informacion', lambda v: {'whatsapp': 'WhatsApp', 'correo': 'Correo', 'si': 'Familia: sí',
                                              'no': 'No quiere información'}.get(v, 'Sin dato'), 'canal_informacion__exact'),
    'modalidad': ('modalidad', lambda v: {'semanal': 'Semanal', 'sabatino': 'Sabatino', 'dominical': 'Dominical',
                                          'indeciso': 'Aún no decide'}.get(v, 'Sin dato'), None),
    'visita': ('evento__preparatoria__nombre', lambda v: v or 'Sin visita (llegó por otro medio)', None),
    'quien_contesto': (None, None, None),
    'mes': (None, None, None),
}


# --------------------------------------------------------------------------- utilidades

def _fecha(v, defecto):
    try:
        return date.fromisoformat(str(v)[:10]) if v else defecto
    except ValueError:
        return defecto


def periodo(args) -> tuple[date, date]:
    hoy = timezone.localdate()
    desde = _fecha(args.get('desde'), hoy - timedelta(days=29))
    hasta = _fecha(args.get('hasta'), hoy)
    return (desde, hasta) if desde <= hasta else (hasta, desde)


def anterior(desde: date, hasta: date) -> tuple[date, date]:
    dias = (hasta - desde).days + 1
    return desde - timedelta(days=dias), desde - timedelta(days=1)


def _aware(d, fin=False):
    from datetime import datetime, time
    return timezone.make_aware(datetime.combine(d, time.max if fin else time.min))


def _rango_txt(desde, hasta) -> str:
    meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
    return f'del {desde.day} {meses[desde.month - 1]} al {hasta.day} {meses[hasta.month - 1]} {hasta.year}'


def solo_propios(user) -> bool:
    return user.has_perm('prospectos.ver_propios') and not user.is_superuser


def base(user, metrica='aspirantes'):
    if metrica == 'esperando_permiso':
        qs = Prospecto.objects.filter(consentimiento=False, consentimiento_negado=False, anonimizado_en__isnull=True,
                                      fusionado_en__isnull=True)
    else:
        qs = Prospecto.objects.reportables()
        if metrica == 'inscritos':
            qs = qs.filter(estatus=Estatus.INSCRITO)
        elif metrica == 'por_llamar':
            qs = qs.filter(estatus__in=ACTIVOS, no_contactar=False, anonimizado_en__isnull=True)
    if solo_propios(user):
        qs = qs.filter(promotor=user)
    return qs


def filtrar(qs, args) -> tuple:
    """Aplica filtros; devuelve (qs, descripción en palabras, parámetros para el enlace)."""
    desc, params = [], {}
    if args.get('plantel'):
        v = texto.normalizar(args['plantel']).replace(' ', '')
        qs = qs.filter(plantel=v)
        desc.append(f"plantel {dict(Plantel.choices).get(v, v)}")
        params['plantel__exact'] = v
    if args.get('carrera'):
        c = Carrera.resolver(args['carrera'])
        qs = qs.filter(carreras=c) if c else qs.none()
        desc.append(f"interesados en {c.nombre if c else args['carrera'] + ' (no existe)'}")
        if c:
            params['carreras__id__exact'] = c.pk
    if args.get('preparatoria'):
        p = Preparatoria.resolver(args['preparatoria'])
        qs = qs.filter(preparatoria=p) if p else qs.filter(preparatoria__nombre_normalizado__contains=texto.normalizar(args['preparatoria']))
        desc.append(f"de {p.nombre if p else args['preparatoria']}")
        if p:
            params['preparatoria__id__exact'] = p.pk
    if args.get('estatus'):
        qs = qs.filter(estatus=args['estatus'])
        desc.append(f"en «{dict(Estatus.choices).get(args['estatus'], args['estatus'])}»")
        params['estatus__exact'] = args['estatus']
    if args.get('grupo'):
        qs = qs.filter(segmentos__icontains=f'"{args["grupo"]}"')
        desc.append(f"del grupo «{etiqueta_segmento(args['grupo'])}»")
        params['segmento'] = args['grupo']
    if args.get('quien_contesto') in ('ambos', 'solo_alumno', 'solo_familia'):
        q = {'ambos': Q(tiene_alumno=True, tiene_tutor=True), 'solo_alumno': Q(tiene_alumno=True, tiene_tutor=False),
             'solo_familia': Q(tiene_alumno=False, tiene_tutor=True)}[args['quien_contesto']]
        qs = qs.filter(q)
        desc.append({'ambos': 'que contestaron alumno y familia', 'solo_alumno': 'que contestó solo el alumno',
                     'solo_familia': 'que contestó solo la familia'}[args['quien_contesto']])
    return qs, desc, params


def enlace(params: dict, desde=None, hasta=None) -> str:
    p = dict(params)
    if desde:
        p['creado_en__gte'] = desde.isoformat()
    if hasta:
        p['creado_en__lt'] = (hasta + timedelta(days=1)).isoformat()
    return reverse('admin:prospectos_prospecto_changelist') + ('?' + urlencode(p) if p else '')


def _contar(qs, dim) -> dict[str, int]:
    campo, leer, _ = DIMENSIONES[dim]
    if dim == 'mes':
        conteo = {}
        for d in qs.values_list('creado_en', flat=True):
            k = timezone.localtime(d).strftime('%Y-%m')
            conteo[k] = conteo.get(k, 0) + 1
        return dict(sorted(conteo.items()))
    if dim == 'quien_contesto':
        filas = qs.values('tiene_alumno', 'tiene_tutor').annotate(n=Count('id')).order_by()
        etiquetas = {(True, True): 'Alumno y familia', (True, False): 'Solo el alumno', (False, True): 'Solo la familia'}
        return {etiquetas.get((f['tiene_alumno'], f['tiene_tutor']), 'Sin respuesta'): f['n'] for f in filas}
    conteo = {}
    for f in qs.values(campo).annotate(n=Count('id', distinct=True)).order_by():
        k = str(leer(f[campo]))[:80]
        conteo[k] = conteo.get(k, 0) + f['n']
    return dict(sorted(conteo.items(), key=lambda x: -x[1]))


def _oculto(n):
    return n if n >= MINIMO_GRUPO else f'menos de {MINIMO_GRUPO}'


def _cambio(actual, previo):
    if not previo:
        return None if not actual else 'nuevo (antes 0)'
    return round((actual - previo) / previo * 100)


# --------------------------------------------------------------------------- herramientas

def cifras(user, args) -> dict:
    metrica = args.get('metrica') if args.get('metrica') in METRICAS else 'aspirantes'
    desde, hasta = periodo(args)
    pdesde, phasta = anterior(desde, hasta)
    if metrica == 'contactos':
        def qs_contactos(d, h):
            q = Seguimiento.objects.filter(tipo__in=CONTACTOS, fecha__range=(_aware(d), _aware(h, True)))
            return q.filter(prospecto__promotor=user) if solo_propios(user) else q
        actual, previo = qs_contactos(desde, hasta), qs_contactos(pdesde, phasta)
        etiqueta = dict(TipoSeguimiento.choices)
        grupos_a = {etiqueta.get(f['tipo'], f['tipo']): f['n'] for f in actual.values('tipo').annotate(n=Count('id')).order_by()}
        grupos_p = {etiqueta.get(f['tipo'], f['tipo']): f['n'] for f in previo.values('tipo').annotate(n=Count('id')).order_by()}
        return _armar(METRICAS[metrica], desde, hasta, actual.count(), previo.count(), grupos_a, grupos_p, [], 'por tipo de contacto',
                      reverse('prospectos:cola'), f'Se contaron los contactos registrados en las fichas {_rango_txt(desde, hasta)}.')
    qs = base(user, metrica)
    qs, desc, params = filtrar(qs, args)
    por_fecha = metrica != 'por_llamar'
    actual = qs.filter(creado_en__range=(_aware(desde), _aware(hasta, True))) if por_fecha else qs
    previo = qs.filter(creado_en__range=(_aware(pdesde), _aware(phasta, True))) if por_fecha else None
    dim = args.get('agrupar_por') if args.get('agrupar_por') in DIMENSIONES else None
    grupos_a = _contar(actual, dim) if dim else {}
    grupos_p = _contar(previo, dim) if dim and previo is not None and dim != 'mes' else {}
    como = (f"Se contaron los {METRICAS[metrica]}" + (f" registrados {_rango_txt(desde, hasta)}" if por_fecha else ' (hoy)')
            + (', ' + ', '.join(desc) if desc else '') + (f', agrupados por {dim.replace("_", " ")}' if dim else '') + '.'
            + (' «Aspirantes» cuenta solo a quienes tienen permiso (los menores sin permiso no se cuentan).' if metrica == 'aspirantes' else '')
            + (' Por carrera se usa la que eligieron primero.' if dim == 'carrera' else ''))
    return _armar(METRICAS[metrica], desde if por_fecha else None, hasta if por_fecha else None, actual.count(),
                  previo.count() if previo is not None else None, grupos_a, grupos_p, desc, dim,
                  enlace({**params, **({'vista': 'cuarentena'} if metrica == 'esperando_permiso' else {})},
                         desde if por_fecha else None, hasta if por_fecha else None), como)


def _armar(etiqueta, desde, hasta, total, total_previo, grupos_a, grupos_p, desc, dim, link, como) -> dict:
    r = {'que_se_conto': etiqueta, 'periodo': _rango_txt(desde, hasta) if desde else 'hoy', 'filtros': desc or 'ninguno',
         'total': total, 'como_se_calculo': como, 'enlace_a_la_lista': link}
    if total_previo is not None:
        pd, ph = anterior(desde, hasta)
        r['periodo_anterior'] = {'periodo': _rango_txt(pd, ph), 'total': total_previo, 'cambio_porcentual': _cambio(total, total_previo)}
    if grupos_a:
        filas = []
        for g, n in list(grupos_a.items())[:20]:
            fila = {'grupo': g, 'n': _oculto(n), 'parte_del_total_pct': round(n / total * 100) if total and n >= MINIMO_GRUPO else None}
            if grupos_p:
                fila['periodo_anterior'] = _oculto(grupos_p.get(g, 0)) if grupos_p.get(g, 0) else 0
            filas.append(fila)
        r['agrupado_por'] = dim
        r['grupos'] = filas
        if len(grupos_a) > 20:
            r['nota'] = f'Se muestran los 20 grupos más grandes de {len(grupos_a)}.'
    if total and total < MINIMO_TASA:
        r['advertencia'] = 'Son muy pocos casos: no saques conclusiones de porcentajes con tan poco.'
    return r


def cruce(user, args) -> dict:
    """Tabla de dos dimensiones (p. ej. carrera × plantel)."""
    filas_dim, cols_dim = args.get('filas'), args.get('columnas')
    if filas_dim not in DIMENSIONES or cols_dim not in DIMENSIONES or 'mes' in (filas_dim, cols_dim) or filas_dim == cols_dim:
        return {'error': 'Elige dos dimensiones distintas (no «mes»).'}
    desde, hasta = periodo(args)
    qs, desc, params = filtrar(base(user).filter(creado_en__range=(_aware(desde), _aware(hasta, True))), args)
    total = qs.count()
    columnas = list(_contar(qs, cols_dim))[:6]
    tabla = []
    for f in list(_contar(qs, filas_dim))[:12]:
        sub = _filtrar_por_valor(qs, filas_dim, f)
        cont = _contar(sub, cols_dim)
        tabla.append({filas_dim: f, **{c: _oculto(cont.get(c, 0)) if cont.get(c, 0) else 0 for c in columnas}, 'total': _oculto(sub.count())})
    return {'que_se_conto': 'aspirantes nuevos con permiso', 'periodo': _rango_txt(desde, hasta), 'filtros': desc or 'ninguno',
            'total': total, 'filas': filas_dim, 'columnas': columnas, 'tabla': tabla,
            'como_se_calculo': f'Se cruzaron los aspirantes nuevos {_rango_txt(desde, hasta)} por {filas_dim} y {cols_dim}; '
                               f'se muestran los 12 y 6 valores más frecuentes. Celdas con menos de {MINIMO_GRUPO} se ocultan.',
            'enlace_a_la_lista': enlace(params, desde, hasta)}


def _filtrar_por_valor(qs, dim, etiqueta):
    """Filtra por el valor legible de una dimensión (inverso de _contar)."""
    if dim == 'quien_contesto':
        return qs.filter(**{'Alumno y familia': {'tiene_alumno': True, 'tiene_tutor': True},
                            'Solo el alumno': {'tiene_alumno': True, 'tiene_tutor': False},
                            'Solo la familia': {'tiene_alumno': False, 'tiene_tutor': True}}.get(etiqueta, {'pk': -1}))
    campo, leer, _ = DIMENSIONES[dim]
    valores = [v for v in qs.values_list(campo, flat=True).distinct() if str(leer(v))[:80] == etiqueta]
    q = Q(**{f'{campo}__in': [v for v in valores if v is not None]})
    if None in valores:
        q |= Q(**{f'{campo}__isnull': True})
    if '' in valores:
        q |= Q(**{campo: ''})
    return qs.filter(q)


def conversion(user, args) -> dict:
    """Qué parte de los aspirantes avanzó (contactado o más) y qué parte se inscribió, por grupo."""
    dim = args.get('agrupar_por') if args.get('agrupar_por') in DIMENSIONES and args.get('agrupar_por') != 'mes' else 'plantel'
    hoy = timezone.localdate()
    desde = _fecha(args.get('desde'), hoy - timedelta(days=179))
    hasta = _fecha(args.get('hasta'), hoy)
    qs, desc, params = filtrar(base(user).filter(creado_en__range=(_aware(desde), _aware(hasta, True))), args)
    filas = []
    for g in list(_contar(qs, dim))[:15]:
        sub = _filtrar_por_valor(qs, dim, g)
        n = sub.count()
        if n < MINIMO_GRUPO:
            continue
        avanzo = sub.filter(estatus__in=AVANZO).count()
        inscritos = sub.filter(estatus=Estatus.INSCRITO).count()
        sin_contacto = sub.filter(ultimo_contacto_en__isnull=True, estatus__in=ACTIVOS).count()
        filas.append({'grupo': g, 'aspirantes': n, 'contactados_o_mas_pct': round(avanzo / n * 100),
                      'inscritos_pct': round(inscritos / n * 100), 'nunca_contactados': _oculto(sin_contacto) if sin_contacto else 0,
                      'confiable': n >= MINIMO_TASA})
    n_total = qs.count()
    return {'periodo': _rango_txt(desde, hasta), 'filtros': desc or 'ninguno', 'agrupado_por': dim, 'aspirantes': n_total,
            'contactados_o_mas_pct': round(qs.filter(estatus__in=AVANZO).count() / n_total * 100) if n_total else None,
            'inscritos_pct': round(qs.filter(estatus=Estatus.INSCRITO).count() / n_total * 100) if n_total else None,
            'grupos': filas,
            'como_se_calculo': f'De los aspirantes con permiso registrados {_rango_txt(desde, hasta)}: qué porcentaje ya pasó a '
                               'Contactado o una etapa posterior, y qué porcentaje está marcado como Inscrito. «Inscrito» lo marca '
                               f'un asesor a mano. Grupos con menos de {MINIMO_TASA} aspirantes se marcan como no confiables.',
            'enlace_a_la_lista': enlace(params, desde, hasta)}


def visitas(user, args) -> dict:
    """Rendimiento de cada visita: registros contra la meta y la asistencia, costo por registro y avance de esos aspirantes."""
    hoy = timezone.localdate()
    desde = _fecha(args.get('desde'), hoy - timedelta(days=90))
    hasta = _fecha(args.get('hasta'), hoy + timedelta(days=60))
    qs = Evento.objects.filter(fecha__range=(desde, hasta)).select_related('preparatoria', 'promotor').order_by('fecha')
    if user.has_perm('prospectos.ver_eventos_propios') and not user.is_superuser:
        qs = qs.filter(promotor=user)
    if args.get('estado'):
        qs = qs.filter(estado=args['estado'])
    filas = []
    for e in qs[:40]:
        regs = Prospecto.objects.filter(evento=e, fusionado_en__isnull=True)
        n = regs.count()
        con_permiso = regs.filter(consentimiento=True).count()
        fila = {'preparatoria': e.preparatoria.nombre[:80], 'fecha': str(e.fecha), 'estado': e.get_estado_display(),
                'actividad': e.get_actividad_display(), 'registros': n, 'con_permiso': con_permiso,
                'meta': e.meta_registros, 'alumnos_asistentes': e.alumnos_asistentes,
                'cartas_de_beca': e.beca_hojas if e.beca_carta else 0,
                'enlace': reverse('admin:prospectos_prospecto_changelist') + f'?evento__id__exact={e.pk}&vista=todos'}
        if e.meta_registros:
            fila['avance_meta_pct'] = round(n / e.meta_registros * 100)
        if e.alumnos_asistentes:
            fila['respuesta_pct'] = round(n / e.alumnos_asistentes * 100)
        if e.costo and n:
            fila['costo_por_registro'] = round(float(e.costo) / n, 2)
        if e.fecha < hoy and con_permiso >= MINIMO_TASA:
            fila['contactados_o_mas_pct'] = round(regs.filter(consentimiento=True, estatus__in=AVANZO).count() / con_permiso * 100)
        filas.append(fila)
    return {'periodo': _rango_txt(desde, hasta), 'visitas': filas,
            'como_se_calculo': 'Registros = aspirantes que llegaron con el QR de esa visita (incluye menores aún sin permiso). '
                               'Avance a la meta = registros ÷ meta. Respuesta = registros ÷ alumnos que asistieron (si se capturó). '
                               'Costo por registro = costo capturado ÷ registros.'}


def pendientes(user, args) -> dict:
    """Lo que está atorado hoy, con el enlace a cada lista."""
    hoy = timezone.now()
    base_u = base(user, 'por_llamar')
    nunca = base_u.filter(ultimo_contacto_en__isnull=True)
    frio = base_u.filter(ultimo_contacto_en__lt=hoy - timedelta(days=14))
    vencidas = Seguimiento.objects.filter(tipo=TipoSeguimiento.TAREA, completada_en__isnull=True, vence_en__lt=hoy,
                                          prospecto__consentimiento=True, prospecto__anonimizado_en__isnull=True)
    if solo_propios(user):
        vencidas = vencidas.filter(prospecto__promotor=user)
    listos_sin = base_u.filter(segmentos__icontains='"listo_para_convertir"', ultimo_contacto_en__isnull=True)
    from .familias import familias_pendientes
    return {'como_se_calculo': 'Conteos de hoy sobre aspirantes activos con permiso.', 'pendientes': [
        {'que': 'Listos para inscribirse que nunca han sido contactados', 'n': listos_sin.count(),
         'enlace': reverse('prospectos:cola') + '?segmento=listo_para_convertir', 'por_que_importa': 'son los de mayor probabilidad y se enfrían'},
        {'que': 'Aspirantes activos nunca contactados', 'n': nunca.count(), 'enlace': reverse('prospectos:cola')},
        {'que': 'Sin contacto en más de 14 días', 'n': frio.count(), 'enlace': reverse('prospectos:cola')},
        {'que': 'Llamadas pendientes ya vencidas', 'n': vencidas.count(), 'enlace': reverse('prospectos:calendario')},
        {'que': 'Menores esperando el permiso de su familia', 'n': base(user, 'esperando_permiso').count(),
         'enlace': reverse('prospectos:respuestas'), 'por_que_importa': 'si en 30 días no llega el permiso, se borran'},
        {'que': 'Encuestas de familias por unir con su alumno', 'n': familias_pendientes(),
         'enlace': reverse('prospectos:familias'), 'por_que_importa': 'sin unirlas, el permiso de la familia no llega al menor'},
        {'que': 'Posibles duplicados por revisar', 'n': PosibleCoincidencia.objects.filter(estado='pendiente').exclude(motivo__startswith='Familia').count(),
         'enlace': reverse('admin:prospectos_posiblecoincidencia_changelist')},
    ]}
