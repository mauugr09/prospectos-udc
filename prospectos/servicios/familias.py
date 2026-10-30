"""
Unir la encuesta de la familia (mamá, papá o tutor) con el cuestionario del alumno.

El problema real: la encuesta de padres no trae código de familia ni preparatoria, y los papás escriben el
nombre del hijo distinto («Juan Pérez» contra «Juan Carlos Pérez López»). Exigir el nombre idéntico casi nunca
unía a nadie. Ahora se suman indicios y cada uno vale puntos:

  CURP del aspirante igual ............................. seguro (100)
  correo/teléfono del aspirante que dio la familia ...... seguro (100)
  teléfono o correo del tutor = el que dio el alumno .... +40 (muchos alumnos dan el de su mamá)
  nombre del aspirante idéntico ......................... +50
  nombre de la familia contenido en el del alumno ....... +35 (le faltan apellidos o el segundo nombre)
  nombre parecido (errores de dedo) ..................... +30 / +15
  un apellido del tutor aparece en el del alumno ........ +10
  mismo evento +20, mismo día +12, mismo plantel +5, misma carrera +5
  plantel distinto ...................................... −30

Se unen solos con 70 puntos o más SI el segundo candidato queda al menos 20 puntos abajo (si no, hay duda).
Desde 30 puntos van a «Familias por unir» para confirmarlos con un clic. Nunca se une a quien ya tiene su mitad.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db.models import Q
from django.utils import timezone

from ..models import Cuestionario, EstadoRespuesta, PosibleCoincidencia, Prospecto
from . import texto
from .cifrado import indice_correo, indice_curp, indice_telefono

AUTOMATICO = 70
VENTAJA = 20
REVISION = 30
MOTIVO = 'Familia'  # prefijo del motivo en PosibleCoincidencia: así se distinguen de los duplicados


@dataclass
class Lado:
    p: Prospecto
    tokens: list[str]
    apellidos_tutor: set[str] = field(default_factory=set)
    contacto_aspirante: set[str] = field(default_factory=set)   # índices ciegos que dio la familia
    curp_aspirante: str | None = None
    fecha = None
    carreras: set[int] = field(default_factory=set)


def _tokens(nombre: str | None) -> list[str]:
    return [t for t in texto.clave_nombre(nombre).split(' ') if t]


def _respuesta(p: Prospecto, cuestionario):
    return (p.respuestas.filter(cuestionario=cuestionario).exclude(estado=EstadoRespuesta.DESCARTADA)
            .order_by('-enviada_en').first())


def _primero(r, codigo):
    v = ((r.raw_json or {}).get('por_codigo', {}).get(codigo) or [None])[0] if r else None
    return v.strip() if v and v.strip() else None


def _lado(p: Prospecto) -> Lado:
    lado = Lado(p=p, tokens=_tokens(p.nombre_aspirante))
    lado.apellidos_tutor = set(_tokens(p.tutor_nombre))
    r = _respuesta(p, Cuestionario.TUTOR if p.tiene_tutor and not p.tiene_alumno else Cuestionario.ALUMNO)
    lado.fecha = timezone.localtime(r.enviada_en).date() if r else None
    if p.tiene_tutor and not p.tiene_alumno:
        c = _primero(r, 'aspirante_contacto')
        if c:
            lado.contacto_aspirante = {x for x in (indice_correo(c) if '@' in c else None, indice_telefono(c)) if x}
        lado.curp_aspirante = indice_curp(_primero(r, 'curp_aspirante'))
        lado.carreras = {p.carrera_tutor_id} if p.carrera_tutor_id else set()
    else:
        lado.carreras = set(p.carreras.values_list('id', flat=True))
    return lado


def _contenido(corto: list[str], largo: list[str]) -> bool:
    """Todos los tokens del nombre corto están en el largo (tolerando errores de dedo). Mínimo nombre y un apellido."""
    if len(corto) < 2 or len(corto) > len(largo):
        return False
    libres = list(largo)
    for t in corto:
        mejor = max(libres, key=lambda x: texto.jaro_winkler(t, x), default=None)
        if mejor is None or texto.jaro_winkler(t, mejor) < 0.92:
            return False
        libres.remove(mejor)
    return True


def _otro_sexo(n1: str | None, n2: str | None) -> bool:
    """El primer nombre es la versión del otro sexo: Fernanda/Fernando, Daniela/Daniel, Andrea/Andrés no; Luisa/Luis sí."""
    a, b = (texto.normalizar(n1).split(' ') or [''])[0], (texto.normalizar(n2).split(' ') or [''])[0]
    if not a or not b or a == b or len(a) < 3 or len(b) < 3:
        return False
    corto, largo = sorted((a, b), key=len)
    if len(largo) - len(corto) == 1 and largo.startswith(corto) and largo[-1] == 'a':
        return True  # Luis/Luisa, Daniel/Daniela, Manuel/Manuela
    return len(a) == len(b) and a[:-1] == b[:-1] and {a[-1], b[-1]} == {'a', 'o'}  # Fernando/Fernanda, Mario/Maria


def puntuar(familia: Lado, alumno: Lado) -> tuple[int, list[str]]:
    """Puntos e indicios de que `familia` (encuesta de padres) habla de `alumno`."""
    f, a = familia.p, alumno.p
    if familia.curp_aspirante and familia.curp_aspirante == a.curp_bi:
        return 100, ['misma CURP']
    if familia.contacto_aspirante & {x for x in (a.correo_bi, a.telefono_bi) if x}:
        return 100, ['la familia dio el correo o teléfono del alumno']
    puntos, razones = 0, []
    if _otro_sexo(f.nombre_aspirante, a.nombre_aspirante):
        return 0, []  # Fernanda/Fernando, Daniela/Daniel: el apellido y el día no bastan para unirlos
    contactos_alumno = {x for x in (a.telefono_bi, a.correo_bi, a.tutor_telefono_bi, a.tutor_correo_bi) if x}
    if {x for x in (f.tutor_telefono_bi, f.tutor_correo_bi) if x} & contactos_alumno:
        puntos += 40
        razones.append('el alumno dio el teléfono o correo de su familia')
    if familia.tokens and familia.tokens == alumno.tokens:
        puntos += 50
        razones.append('mismo nombre')
    elif _contenido(familia.tokens, alumno.tokens) or _contenido(alumno.tokens, familia.tokens):
        puntos += 35
        razones.append('el nombre coincide (a uno le faltan apellidos o segundo nombre)')
    else:
        s = texto.similitud_nombres(f.nombre_aspirante, a.nombre_aspirante)
        if s >= 0.85:
            puntos += 30
            razones.append(f'nombre muy parecido ({s:.0%})')
        elif s >= 0.74:
            puntos += 15
            razones.append(f'nombre parecido ({s:.0%})')
    if not razones:  # sin nombre ni contacto en común, apellido + día + carrera son pura coincidencia
        return 0, []
    if familia.apellidos_tutor:
        if familia.apellidos_tutor & set(alumno.tokens):
            puntos += 10
            razones.append('comparten apellido')
    if f.evento_id and f.evento_id == a.evento_id:
        puntos += 20
        razones.append('mismo evento')
    elif familia.fecha and familia.fecha == alumno.fecha:
        puntos += 12
        razones.append('contestaron el mismo día')
    if f.plantel and a.plantel:
        if f.plantel == a.plantel:
            puntos += 5
        else:
            puntos -= 30
            razones.append('eligieron planteles distintos')
    if familia.carreras & alumno.carreras:
        puntos += 5
        razones.append('misma carrera')
    return max(0, min(puntos, 99)), razones


def _vivos():
    return Prospecto.objects.filter(fusionado_en__isnull=True, anonimizado_en__isnull=True)


def descartados(p: Prospecto) -> set[int]:
    """Con quién ya se dijo «No son» (o se separó): no se vuelve a proponer ni a unir solo."""
    filas = PosibleCoincidencia.objects.filter(Q(prospecto=p) | Q(candidato=p), estado='rechazada').values_list('prospecto_id', 'candidato_id')
    return {x for par in filas for x in par} - {p.pk}


def candidatos(p: Prospecto, minimo: int = REVISION, maximo: int = 5) -> list[dict]:
    """Posibles parejas de un prospecto al que le falta una mitad (solo familia o solo alumno)."""
    if p.tiene_alumno == p.tiene_tutor:
        return []
    yo = _lado(p)
    soy_familia = p.tiene_tutor
    otros = (_vivos().exclude(pk=p.pk).filter(tiene_alumno=soy_familia, tiene_tutor=not soy_familia)
             .exclude(pk__in=descartados(p)))
    if p.token_familia:
        otros = otros.filter(Q(token_familia__isnull=True) | Q(token_familia=p.token_familia))
    res = []
    for o in otros.prefetch_related('carreras'):
        otro = _lado(o)
        puntos, razones = puntuar(yo, otro) if soy_familia else puntuar(otro, yo)
        if puntos >= minimo:
            res.append({'prospecto': o, 'puntos': puntos, 'razones': razones})
    return sorted(res, key=lambda c: c['puntos'], reverse=True)[:maximo]


def unir_o_proponer(p: Prospecto) -> Prospecto:
    """Tras importar: une sola la familia con su alumno si no hay duda; si la hay, la deja para revisión."""
    from .inteligencia import NoFusionable, fusionar
    cands = candidatos(p)
    if not cands:
        return p
    mejor = cands[0]
    segundo = cands[1]['puntos'] if len(cands) > 1 else 0
    if mejor['puntos'] >= AUTOMATICO and mejor['puntos'] - segundo >= VENTAJA:
        alumno, familia = (mejor['prospecto'], p) if p.tiene_tutor else (p, mejor['prospecto'])
        try:
            return fusionar(alumno, familia)
        except NoFusionable:
            pass
    for c in cands[:3]:
        PosibleCoincidencia.objects.get_or_create(
            prospecto=p, candidato=c['prospecto'],
            defaults={'similitud': c['puntos'] / 100, 'motivo': f"{MOTIVO}: {', '.join(c['razones']) or 'indicios débiles'}"})
    return p


def pendientes():
    """Familias por unir: propuestas pendientes entre una encuesta de padres y un alumno."""
    return (PosibleCoincidencia.objects.filter(estado='pendiente', motivo__startswith=MOTIVO,
                                               prospecto__fusionado_en__isnull=True, candidato__fusionado_en__isnull=True)
            .select_related('prospecto', 'candidato', 'prospecto__preparatoria', 'candidato__preparatoria'))


def familias_pendientes() -> int:
    """Cuántas encuestas de familia tienen al menos una propuesta (lo que cuenta el menú; no las propuestas sueltas)."""
    ids = set()
    for p_id, p_es_alumno, c_id in pendientes().values_list('prospecto_id', 'prospecto__tiene_alumno', 'candidato_id'):
        ids.add(c_id if p_es_alumno else p_id)
    return len(ids)


def buscar_para_todos() -> dict:
    """Vuelve a buscar pareja para todas las fichas a medias (útil tras mejorar el criterio o importar mucho)."""
    unidas = propuestas = 0
    for p in list(_vivos().filter(Q(tiene_alumno=True, tiene_tutor=False) | Q(tiene_alumno=False, tiene_tutor=True))):
        p.refresh_from_db()
        if p.fusionado_en_id or p.tiene_alumno == p.tiene_tutor:
            continue
        antes = PosibleCoincidencia.objects.filter(prospecto=p).count()
        r = unir_o_proponer(p)
        if r.pk != p.pk or (r.tiene_alumno and r.tiene_tutor):
            unidas += 1
        else:
            propuestas += PosibleCoincidencia.objects.filter(prospecto=p).count() - antes
    return {'unidas': unidas, 'propuestas': propuestas}


# --------------------------------------------------------------------------- pantalla «Familias por unir»

def nivel(puntos: int | None) -> str:
    if puntos is None:
        return 'sin'
    return 'alta' if puntos >= 60 else 'media' if puntos >= 45 else 'baja'


def _soy_familia(p: Prospecto) -> bool:
    return p.tiene_tutor and not p.tiene_alumno


def mesa(limite_solas: int = 500) -> dict:
    """
    Agrupa por encuesta de familia: cada una con sus alumnos candidatos (mejor primero).
    Una misma pareja puede tener dos propuestas (una creada desde cada lado, o con criterios viejos):
    se muestra una sola, con el puntaje más alto, y al rechazarla se rechazan todas.
    """
    grupos: dict[int, dict] = {}
    for c in pendientes().prefetch_related('prospecto__carreras', 'candidato__carreras'):
        f, a = (c.prospecto, c.candidato) if _soy_familia(c.prospecto) else (c.candidato, c.prospecto)
        if not _soy_familia(f) or not (a.tiene_alumno and not a.tiene_tutor):
            continue  # alguna de las dos ya se completó por otro lado
        g = grupos.setdefault(f.pk, {'familia': f, 'candidatos': {}})
        puntos = round(c.similitud * 100)
        previo = g['candidatos'].get(a.pk)
        if previo:
            previo['propuestas'].append(c.pk)
            if puntos <= previo['puntos']:
                continue
        g['candidatos'][a.pk] = {'alumno': a, 'puntos': puntos, 'nivel': nivel(puntos),
                                 'razones': [r for r in c.motivo.split(': ', 1)[-1].split(', ') if r and r != 'indicios débiles'],
                                 'propuestas': (previo or {}).get('propuestas', []) + ([] if previo else [c.pk])}
    con = []
    for g in grupos.values():
        g['candidatos'] = sorted(g['candidatos'].values(), key=lambda x: -x['puntos'])
        g['mejor'] = g['candidatos'][0]['puntos']
        g['nivel'] = nivel(g['mejor'])
        con.append(g)
    con.sort(key=lambda g: (-g['mejor'], g['familia'].nombre_aspirante))
    solas_qs = (_vivos().filter(tiene_tutor=True, tiene_alumno=False).exclude(pk__in=grupos)
                .select_related('carrera_tutor').order_by('-creado_en'))
    solas = [{'familia': f, 'candidatos': [], 'mejor': None, 'nivel': 'sin'} for f in solas_qs[:limite_solas]]
    return {'con': con, 'solas': solas, 'total_solas': solas_qs.count(),
            'alumnos_solos': _vivos().filter(tiene_alumno=True, tiene_tutor=False).count()}


def buscar_alumnos(familia: Prospecto, q: str, maximo: int = 15) -> list[dict]:
    """Alumnos sin familia cuyo nombre contiene todas las palabras de `q`, con los puntos que tendrían."""
    # Mismas reglas que nombre_normalizado (Ximena→jimena, z→s, h muda…), para que «Gonzalez» encuentre «González».
    palabras = [texto._variantes(t) for t in texto.normalizar(q).split(' ') if len(t) >= 2 and t not in texto.PARTICULAS]
    palabras = [t for t in palabras if t]
    if not palabras:
        return []
    qs = _vivos().filter(tiene_alumno=True, tiene_tutor=False).select_related('preparatoria')
    for t in palabras:
        qs = qs.filter(nombre_normalizado__icontains=t)
    if familia.token_familia:
        qs = qs.filter(Q(token_familia__isnull=True) | Q(token_familia=familia.token_familia))
    yo = _lado(familia)
    res = []
    for a in qs.prefetch_related('carreras')[:60]:
        puntos, razones = puntuar(yo, _lado(a))
        res.append({'alumno': a, 'puntos': puntos, 'nivel': nivel(puntos) if puntos else 'sin', 'razones': razones})
    res.sort(key=lambda r: (-r['puntos'], r['alumno'].nombre_aspirante))
    return res[:maximo]
