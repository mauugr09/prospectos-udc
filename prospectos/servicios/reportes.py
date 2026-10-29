"""
Métricas agregadas, comparativo alumno/tutor y generador de QR.
Ninguna métrica devuelve datos personales; solo cuentan prospectos con consentimiento y sin fusionar.
"""

import secrets
from collections import Counter
from datetime import datetime, time, timedelta

import segno
from django.db.models import Count, F, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .. import catalogos
from ..models import (EMBUDO, Carrera, Cuestionario, EstadoRespuesta, Estatus, Evento, Formulario, Pregunta,
                      Preparatoria, Prospecto, Respuesta, RespuestaItem)


def _inicio(d):
    return timezone.make_aware(datetime.combine(d, time.min)) if d else None


def _fin(d):
    return timezone.make_aware(datetime.combine(d, time.max)) if d else None


class Metricas:
    def __init__(self, desde=None, hasta=None):
        self.desde, self.hasta = _inicio(desde), _fin(hasta)

    def base(self):
        qs = Prospecto.objects.reportables()
        if self.desde:
            qs = qs.filter(creado_en__gte=self.desde)
        if self.hasta:
            qs = qs.filter(creado_en__lte=self.hasta)
        return qs

    def _items(self):
        qs = RespuestaItem.objects.filter(respuesta__estado=EstadoRespuesta.VALIDA)
        if self.desde:
            qs = qs.filter(respuesta__enviada_en__gte=self.desde)
        if self.hasta:
            qs = qs.filter(respuesta__enviada_en__lte=self.hasta)
        return qs

    @staticmethod
    def _lista(qs, campo, defecto, limite):
        return [{'etiqueta': r['e'] or defecto, 'total': r['total']}
                for r in qs.values(e=F(campo)).annotate(total=Count('id')).order_by('-total')[:limite]]

    def total(self) -> int:
        return self.base().count()

    def por_preparatoria(self, limite=15):
        return self._lista(self.base(), 'preparatoria__nombre', 'Sin preparatoria', limite)

    def por_promotor(self, limite=15):
        filas = (self.base().values('promotor__first_name', 'promotor__last_name', 'promotor__username')
                 .annotate(total=Count('id')).order_by('-total')[:limite])
        return [{'etiqueta': ('Sin promotor' if not r['promotor__username'] else
                              f"{r['promotor__first_name'] or ''} {r['promotor__last_name'] or ''}".strip() or r['promotor__username']),
                 'total': r['total']} for r in filas]

    def carreras(self, limite=10, plantel=None):
        """Cada carrera marcada cuenta (el Form permite elegir varias)."""
        base = self.base()
        if plantel:
            base = base.filter(plantel=plantel)
        filas = (Carrera.objects.filter(interesados__in=base).values('nombre')
                 .annotate(total=Count('interesados', distinct=True)).order_by('-total')[:limite])
        return [{'etiqueta': r['nombre'], 'total': r['total']} for r in filas]

    def por_plantel(self):
        por = dict(self.base().values_list('plantel').annotate(n=Count('id')))
        return [{'clave': k, 'etiqueta': v, 'total': por.get(k, 0)} for k, v in catalogos.PLANTELES_CORTO.items()] + (
            [{'clave': '', 'etiqueta': 'Sin plantel', 'total': por['']}] if por.get('') else [])

    def canales(self):
        """Cómo quieren recibir información (whatsapp / correo / no)."""
        por = dict(self.base().values_list('canal_informacion').annotate(n=Count('id')))
        total = sum(por.values()) or 1
        opciones = {**catalogos.CANAL_INFORMACION, 'si': 'Sí (lo pidió la familia)'}
        filas = [{'clave': k, 'etiqueta': v, 'total': por.get(k, 0), 'pct': round(100 * por.get(k, 0) / total, 1)}
                 for k, v in opciones.items() if k != 'si' or por.get(k)]
        return filas

    def indecisos(self) -> float:
        total = self.base().count()
        n = self.base().filter(segmentos__icontains='"indeciso_carrera"').count()
        return round(100 * n / total, 1) if total else 0.0

    def por_semana(self, semanas=12):
        """Agrupa en Python (hora local): no depende de las tablas de zonas horarias del servidor."""
        desde = timezone.now() - timedelta(weeks=semanas)
        c = Counter()
        for f in self.base().filter(creado_en__gte=desde).values_list('creado_en', flat=True):
            d = timezone.localtime(f).date()
            c[d - timedelta(days=d.weekday())] += 1
        return [{'etiqueta': lunes.strftime('%d/%m'), 'total': n} for lunes, n in sorted(c.items())]

    def por_segmento(self):
        c = Counter()
        for segs in self.base().values_list('segmentos', flat=True):
            c.update(segs or [])
        from ..models import Segmento
        return [{'etiqueta': Segmento(k).label, 'clave': k, 'total': c.get(k, 0)} for k in Segmento.values]

    def por_preparatoria_plantel(self, limite=20):
        """Preparatorias de donde vienen, separadas por plantel elegido."""
        filas = (self.base().values(e=F('preparatoria__nombre'))
                 .annotate(total=Count('id'), cuautitlan=Count('id', filter=Q(plantel='cuautitlan')),
                           tultepec=Count('id', filter=Q(plantel='tultepec'))).order_by('-total')[:limite])
        return [dict(r, etiqueta=r['e'] or 'Sin preparatoria') for r in filas]

    def frecuencia(self, codigo: str, cuestionario: str, catalogo=None):
        p = Pregunta.objects.filter(cuestionario=cuestionario, codigo=codigo).prefetch_related('opciones_lista').first()
        etiquetas = p.etiquetas_opciones() if p else {}
        if p and p.tipo in ('si_no', 'consentimiento') and not etiquetas:
            etiquetas = {'si': 'Sí', 'no': 'No'}
        filas = (self._items().filter(respuesta__cuestionario=cuestionario, codigo=codigo, valor_normalizado__isnull=False)
                 .values('valor_normalizado').annotate(total=Count('id')).order_by('-total'))
        return [{'etiqueta': etiquetas.get(r['valor_normalizado'], r['valor_normalizado']), 'total': r['total']} for r in filas]

    def tasa_respuesta(self):
        filtro = Q(prospectos__consentimiento=True, prospectos__fusionado_en__isnull=True)
        filas = (Preparatoria.objects.filter(alumnos_estimados__gt=0)
                 .annotate(total=Count('prospectos', filter=filtro)).order_by('-total'))
        return [{'etiqueta': p.nombre, 'total': p.total, 'estimados': p.alumnos_estimados,
                 'tasa': round(100 * p.total / max(1, p.alumnos_estimados), 1)} for p in filas]

    def parejas(self):
        total = self.base().count()
        parejas = self.base().filter(tiene_alumno=True, tiene_tutor=True).count()
        return {'total': total, 'parejas': parejas, 'porcentaje': round(100 * parejas / total, 1) if total else 0.0}

    def pide_informacion(self) -> float:
        """% que pidió información por WhatsApp o correo."""
        return round(sum(c['pct'] for c in self.canales() if c['clave'] in ('whatsapp', 'correo', 'si')), 1)

    def preguntas_agregadas(self):
        """Frecuencias de las preguntas de opción agregadas desde el panel (no son del sistema)."""
        res = []
        for p in Pregunta.objects.filter(de_sistema=False, sensible=False, tipo__in=['opcion', 'multiple', 'si_no']).order_by('orden'):
            filas = self.frecuencia(p.codigo, p.cuestionario)
            if filas:
                res.append({'titulo': p.etiqueta or p.texto, 'cuestionario': p.get_cuestionario_display(), 'filas': filas})
        return res

    def temas_duda(self, limite=10):
        c = Counter()
        for e in self._items().filter(etiqueta_ia__isnull=False).values_list('etiqueta_ia', flat=True):
            c.update((e or {}).get('temas', []))
        return [{'etiqueta': t.capitalize(), 'total': n} for t, n in c.most_common(limite)]

    def embudo(self):
        por = dict(self.base().values_list('estatus').annotate(n=Count('id')))
        res, acumulado = [], 0
        for etapa in reversed(EMBUDO):
            acumulado += por.get(etapa, 0)
            res.append({'etapa': Estatus(etapa).label, 'total': acumulado})
        return list(reversed(res))

    def costo_por_prospecto(self):
        qs = Evento.objects.exclude(costo=None)
        if self.desde:
            qs = qs.filter(fecha__gte=self.desde.date())
        if self.hasta:
            qs = qs.filter(fecha__lte=self.hasta.date())
        qs = qs.annotate(n=Count('prospectos', filter=Q(prospectos__consentimiento=True, prospectos__fusionado_en__isnull=True)))
        costo = float(qs.aggregate(s=Sum('costo'))['s'] or 0)
        n = sum(e.n for e in qs)
        return {'costo_total': costo, 'prospectos': n, 'costo_por_prospecto': round(costo / n, 2) if n else None}

    @staticmethod
    def conteo_evento(evento: Evento):
        qs = Respuesta.objects.filter(evento=evento).exclude(estado=EstadoRespuesta.DESCARTADA)
        return {'alumnos': qs.filter(cuestionario=Cuestionario.ALUMNO).count(),
                'tutores': qs.filter(cuestionario=Cuestionario.TUTOR).count(),
                'ultima': qs.aggregate(m=Max('enviada_en'))['m']}

    @staticmethod
    def ranking_promotores(desde, hasta):
        filas = (Respuesta.objects.exclude(estado=EstadoRespuesta.DESCARTADA).exclude(promotor=None)
                 .filter(enviada_en__range=(desde, hasta))
                 .values('promotor__first_name', 'promotor__last_name', 'promotor__username')
                 .annotate(total=Count('id')).order_by('-total'))
        return [{'etiqueta': f"{r['promotor__first_name']} {r['promotor__last_name']}".strip() or r['promotor__username'],
                 'total': r['total']} for r in filas]

    @staticmethod
    def cobertura(base=None):
        filtro = Q(prospectos__consentimiento=True, prospectos__fusionado_en__isnull=True)
        if base is not None:
            filtro &= Q(prospectos__in=base)
        qs = (Preparatoria.objects.exclude(lat=None).exclude(lng=None)
              .annotate(total=Count('prospectos', filter=filtro),
                        cuautitlan=Count('prospectos', filter=filtro & Q(prospectos__plantel='cuautitlan')),
                        tultepec=Count('prospectos', filter=filtro & Q(prospectos__plantel='tultepec'))))
        return [{'id': p.pk, 'nombre': p.nombre, 'municipio': p.municipio, 'lat': float(p.lat), 'lng': float(p.lng),
                 'estimados': p.alumnos_estimados, 'total': p.total, 'cuautitlan': p.cuautitlan, 'tultepec': p.tultepec}
                for p in qs]

    @staticmethod
    def sin_ubicar():
        """Preparatorias sin coordenadas, con cuántos aspirantes tiene cada una (las que más importan primero)."""
        filtro = Q(prospectos__fusionado_en__isnull=True)
        return (Preparatoria.objects.filter(Q(lat=None) | Q(lng=None), activo=True)
                .annotate(total=Count('prospectos', filter=filtro)).order_by('-total', 'nombre'))


# --------------------------------------------------------------------------- respuestas legibles
OCULTOS = {'evento', 'promotor', 'token_familia', 'nombre_completo', 'nombre_aspirante', 'tutor_nombre'}

# Preguntas agrupadas por tema, con un nombre corto y claro (el texto completo queda como ayuda).
TEMAS = [
    ('interes', 'Lo que quiere estudiar', 'school', [
        ('plantel', 'Plantel'), ('carrera', 'Carreras que le interesan'), ('modalidad', 'Modalidad')]),
    ('ideal', 'Su universidad ideal', 'star', [
        ('factor_eleccion', 'Lo más importante al elegir'), ('quiere_conocer', 'Quiere conocer')]),
    ('contacto', 'Cómo quiere que lo contactemos', 'chat', [
        ('recibir_informacion', 'Recibir información')]),
    ('generales', 'Datos generales', 'badge', [
        ('edad', 'Edad'), ('preparatoria', 'Preparatoria'), ('consentimiento_aviso_privacidad', 'Aceptó el aviso de privacidad')]),
]
ABIERTAS: set[str] = set()


def _valores(r, pregunta, carreras, prepas) -> list[str]:
    if not r or not pregunta:
        return []
    vals = []
    for i in r._items():
        if i.codigo != pregunta.codigo:
            continue
        n, op = i.valor_normalizado, pregunta.opciones
        if n is None:
            vals.append(f'Otra: {i.valor}' if op == 'carreras' else i.valor)
        elif op == 'carreras':
            vals.append('Aún no lo sabe' if n == catalogos.INDECISO else carreras.get(int(n), i.valor))
        elif op == 'preparatorias':
            vals.append(prepas.get(int(n), i.valor))
        elif pregunta.tipo in ('si_no', 'consentimiento') and not pregunta.lista_opciones():
            vals.append({'si': 'Sí', 'no': 'No'}.get(n, i.valor))
        else:
            vals.append(pregunta.etiquetas_opciones().get(n, i.valor))
    return [v for v in vals if v]


def _texto(r, pregunta, carreras, prepas):
    return ', '.join(_valores(r, pregunta, carreras, prepas)) or None


def _contexto_preguntas():
    preguntas = {}
    for q in Pregunta.objects.filter(sensible=False).prefetch_related('opciones_lista').order_by('orden', 'id'):
        preguntas.setdefault(q.cuestionario, {})[q.codigo] = q
    return preguntas, dict(Carrera.objects.values_list('id', 'nombre')), dict(Preparatoria.objects.values_list('id', 'nombre'))


def _claves(r, codigo) -> list[str]:
    """Valores internos (no el texto que se ve): «Semanal» del alumno y «Escolarizada» del tutor son la misma clave."""
    from . import texto
    return [i.valor_normalizado or texto.normalizar(i.valor) for i in r._items() if i.codigo == codigo] if r else []


def _coinciden(codigo, va, vt) -> bool:
    # Carreras: el Form deja marcar varias; basta con que compartan una.
    return bool(set(va) & set(vt)) if codigo == 'carrera' else sorted(va) == sorted(vt)


ICONOS_TEMA = {'interes': 'school', 'ideal': 'star', 'expectativas': 'family_restroom', 'contacto': 'chat',
               'generales': 'badge', 'otras': 'list'}


def _temas(alumno, tutor) -> list[dict]:
    """Respuestas agrupadas por tema (el tema y el nombre corto de cada pregunta se editan en el panel)."""
    from ..models import TEMAS_PREGUNTA
    preguntas, carreras, prepas = _contexto_preguntas()
    codigos = list(dict.fromkeys([*preguntas.get('ALUMNO', {}), *preguntas.get('TUTOR', {})]))
    temas = []
    for clave, titulo in TEMAS_PREGUNTA:
        renglones = []
        for codigo in codigos:
            pa, pt = preguntas.get('ALUMNO', {}).get(codigo), preguntas.get('TUTOR', {}).get(codigo)
            base = pa or pt
            if base.tema != clave or codigo in OCULTOS:
                continue
            va = _valores(alumno, pa, carreras, prepas)
            vt = _valores(tutor, pt, carreras, prepas)
            comparable = bool(pa and pt and alumno and tutor) and codigo in catalogos.COMPARABLES
            if not va and not vt and (codigo in catalogos.RECOMENDADAS or (not (alumno and pa) and not (tutor and pt))):
                continue  # pregunta que el Form no tiene: no se muestra vacía
            renglones.append({
                'codigo': codigo, 'etiqueta': base.etiqueta or base.texto, 'pregunta': base.texto,
                'abierta': base.tipo == 'abierta',
                'alumno': va, 'tutor': vt, 'aplica_alumno': bool(pa), 'aplica_tutor': bool(pt),
                'comparable': comparable,
                'coinciden': comparable and va and vt and _coinciden(codigo, _claves(alumno, codigo), _claves(tutor, codigo)),
                'diferente': comparable and va and vt and not _coinciden(codigo, _claves(alumno, codigo), _claves(tutor, codigo)),
            })
        if renglones:
            temas.append({'clave': clave, 'titulo': titulo, 'icono': ICONOS_TEMA.get(clave, 'list'), 'filas': renglones,
                          'diferencias': sum(1 for r in renglones if r['diferente'])})
    return temas


def comparativo(p: Prospecto) -> dict:
    """Respuestas del alumno y del tutor por tema, lado a lado. Sin datos de contacto."""
    resp = list(p.respuestas.exclude(estado=EstadoRespuesta.DESCARTADA).prefetch_related('items').order_by('-enviada_en'))
    alumno = next((r for r in resp if r.cuestionario == Cuestionario.ALUMNO), None)
    tutor = next((r for r in resp if r.cuestionario == Cuestionario.TUTOR), None)
    temas = _temas(alumno, tutor)
    filas = [f for t in temas for f in t['filas']]
    comparables = [f for f in filas if f['comparable'] and f['alumno'] and f['tutor']]
    return {'alumno': alumno, 'tutor': tutor, 'temas': temas,
            'filas': filas,  # compatibilidad
            'comparables': len(comparables), 'coinciden': sum(1 for f in comparables if f['coinciden']),
            'diferencias': sum(1 for f in comparables if f['diferente'])}


def detalle_respuesta(r) -> list[dict]:
    """Una sola respuesta, agrupada por tema."""
    return _temas(r, None) if r.cuestionario == Cuestionario.ALUMNO else _temas(None, r)


ESTADOS_LEGIBLES = {
    EstadoRespuesta.VALIDA: ('Lista para usar', 'verde', 'Tiene permiso (aviso de privacidad aceptado): cuenta en la cola y en los reportes.'),
    EstadoRespuesta.CUARENTENA: ('Esperando permiso', 'ambar',
                                 'Es de un menor y aún no llega la autorización del tutor. No se usa hasta que llegue; '
                                 'si no llega en 30 días, se borra.'),
    EstadoRespuesta.SIN_CONSENTIMIENTO: ('Sin permiso', 'rojo', 'No se aceptó el aviso de privacidad: no se usa y se borra.'),
    EstadoRespuesta.DESCARTADA: ('Borrada', 'gris', 'Sus datos personales ya se eliminaron; solo queda para estadísticas.'),
}


def explicar_estado(r: Respuesta) -> tuple[str, str, str]:
    """(estado, color, por qué) en palabras simples; para «Esperando permiso» dice exactamente qué falta."""
    etiqueta, tono, ayuda = ESTADOS_LEGIBLES.get(r.estado, (r.estado, 'gris', ''))
    if r.estado != EstadoRespuesta.CUARENTENA:
        return etiqueta, tono, ayuda
    from django.conf import settings
    from . import texto
    from .inteligencia import aviso_en_formulario
    mayoria = settings.PROSPECTOS['EDAD_MAYORIA']
    dias = settings.PROSPECTOS['CUARENTENA_DIAS']
    edad_txt = r.valor('edad', normalizado=False)
    edad = texto.entero(edad_txt, 10, 99)
    if edad is None:
        motivo = (f'No sabemos su edad (escribió «{edad_txt}»).' if edad_txt else 'No contestó su edad.') + \
            ' Se trata como menor hasta confirmarla.'
    elif edad < mayoria:
        motivo = f'Tiene {edad} años: falta el permiso de su mamá, papá o tutor.'
    elif r.valor('consentimiento_aviso_privacidad') is None and not aviso_en_formulario():
        motivo = (f'Tiene {edad} años, pero el Form no le pidió aceptar el aviso de privacidad. Agrega esa pregunta al Form '
                  'o, si el aviso ya se muestra en el Form, márcalo en «Reglas de permiso».')
    else:
        motivo = 'Falta el permiso.'
    return etiqueta, tono, f'{motivo} No se usa hasta tenerlo; si no llega en {dias} días, se borra.'


# --------------------------------------------------------------------------- QR
ALFABETO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # sin 0/O ni 1/I


def qr_svg(contenido: str) -> str:
    """QR como data URI SVG (sin servicios externos)."""
    return segno.make(contenido, error='l').svg_data_uri(scale=4, border=2)


def formulario_activo(tipo: str):
    return Formulario.objects.filter(tipo=tipo, activo=True).order_by('-id').first()


def _codigo_promotor(evento):
    perfil = getattr(evento.promotor, 'perfil', None) if evento.promotor_id else None
    return perfil.codigo_promotor if perfil else None


def qr_general(evento: Evento, tipo: str) -> dict:
    f = formulario_activo(tipo)
    url = f.url_prellenada({'evento': evento.codigo, 'promotor': _codigo_promotor(evento)}) if f else None
    return {'url': url, 'qr': qr_svg(url) if url else None}


def qr_permanente(prepa: Preparatoria, tipo: str) -> dict:
    """QR que no cambia: sirve para carteles y para todas las visitas a esa prepa."""
    f = formulario_activo(tipo)
    url = f.url_prellenada({'evento': prepa.codigo_qr}) if f else None
    return {'url': url, 'qr': qr_svg(url) if url else None,
            'con_codigo': bool(f and (f.campos_prellenado or {}).get('evento'))}


def token_familia() -> str:
    return 'F' + ''.join(secrets.choice(ALFABETO) for _ in range(7))


def tarjetas(evento: Evento, cantidad: int) -> list[dict]:
    fa, ft = formulario_activo(Cuestionario.ALUMNO), formulario_activo(Cuestionario.TUTOR)
    promotor = _codigo_promotor(evento)
    res = []
    for _ in range(max(1, min(200, cantidad))):
        t = token_familia()
        v = {'evento': evento.codigo, 'promotor': promotor, 'token_familia': t}
        ua = fa.url_prellenada(v) if fa else None
        ut = ft.url_prellenada(v) if ft else None
        res.append({'token': t, 'alumno': {'url': ua, 'qr': qr_svg(ua) if ua else None},
                    'tutor': {'url': ut, 'qr': qr_svg(ut) if ut else None}})
    return res
