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


def puntuar(familia: Lado, alumno: Lado) -> tuple[int, list[str]]:
    """Puntos e indicios de que `familia` (encuesta de padres) habla de `alumno`."""
    f, a = familia.p, alumno.p
    if familia.curp_aspirante and familia.curp_aspirante == a.curp_bi:
        return 100, ['misma CURP']
    if familia.contacto_aspirante & {x for x in (a.correo_bi, a.telefono_bi) if x}:
        return 100, ['la familia dio el correo o teléfono del alumno']
    puntos, razones = 0, []
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


def candidatos(p: Prospecto, minimo: int = REVISION, maximo: int = 5) -> list[dict]:
    """Posibles parejas de un prospecto al que le falta una mitad (solo familia o solo alumno)."""
    if p.tiene_alumno == p.tiene_tutor:
        return []
    yo = _lado(p)
    soy_familia = p.tiene_tutor
    otros = _vivos().exclude(pk=p.pk).filter(tiene_alumno=soy_familia, tiene_tutor=not soy_familia)
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
