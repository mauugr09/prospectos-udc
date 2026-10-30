"""
Motor propio de Kuali: entiende preguntas en español con reglas y responde con plantillas. Sin IA externa.

Cómo funciona (de la pregunta a la respuesta):
  1. entender(): normaliza el texto (sin acentos, minúsculas) y saca
       - la intención (cifras, cruce, conversión, embudo, visitas, pendientes, ayuda, preparar llamada, proponer…),
       - las entidades: periodo, plantel, carrera, prepa, grupo, estatus, canal, quién contestó, agrupación;
     si la pregunta solo trae entidades («¿y en Tultepec?»), reutiliza la intención anterior (memoria).
  2. Llama a la consulta de analitica.py que corresponde (las cifras nunca se escriben a mano).
  3. redacta con la forma fija: cifra y periodo → comparación → hallazgos → qué haría (con enlace) → preguntas
     para seguir. Los hallazgos salen de reglas sobre los datos (el mayor cambio, la mayor parte, lo que está atorado).

Para enseñarle una forma nueva de preguntar: agrega palabras a PALABRAS_INTENCION o un sinónimo a las entidades, y
una prueba en tests/test_kuali.py. `Prospectos.exe probar_kuali` muestra cómo entiende una lista de preguntas.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from ..models import Carrera, Estatus, Preparatoria, Prospecto, etiqueta_segmento
from . import analitica as A
from . import texto

MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
DIAS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
NUMEROS = {'un': 1, 'una': 1, 'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6, 'siete': 7, 'ocho': 8,
           'nueve': 9, 'diez': 10, 'doce': 12, 'quince': 15, 'veinte': 20, 'treinta': 30}


def _n(t: str) -> str:
    return texto.normalizar(t or '')


def _tiene(q: str, *patrones: str) -> bool:
    return any(re.search(p, q) for p in patrones)


# =========================================================================== entender
PALABRAS_INTENCION = {  # raíces: «convier\w*» acepta convierte, convierten, conversión…
    'saludo': [r'^(hola|buen[oa]s? (dias|tardes|noches)|que tal|hey)\b', r'^(muchas )?gracias\b|^(ok|perfecto|listo|va)\W*$'],
    'quien_eres': [r'\b(quien eres|que eres|que puedes hacer|que sabes hacer|como te llamas|para que sirves|ayudame|en que me ayudas)\b'],
    'ficha_llamada': [r'\b(prepar\w*|guion|guia)\b.*\b(llamada|contacto)\b', r'\bllamada\b', r'\bque le (digo|pregunto)\b',
                      r'\bcomo (lo|la) (abordo|contacto|llamo)\b'],
    'ficha_mensaje': [r'\b(whats?\w*|mensaje|correo|escribel\w*|escribirle|redacta\w*)\b'],
    'ficha_diferencias': [r'\b(diferencia\w*|no coincide\w*|familia|papas|tutor)\b'],
    'asignar': [r'\b(re)?asign\w*'],
    'crear_visita': [r'\b(agend\w*|program\w*|registr\w*|crea\w*|apunt\w*)\b.*\b(visita|platica|feria|stand|taller)\b'],
    'crear_actividad': [r'\b(agreg\w*|anot\w*|pon|poner|crea\w*|registr\w*)\b.*\b(calendario|open house|junta|examen|'
                        r'inscripciones|curso|propedeutico|expo)\b'],
    'pendientes': [r'\b(urgente\w*|urge|que hago|por donde empiezo|pendiente\w*|atorad\w*|que falta|que sigue|nadie ha (llamado|contactado)|'
                   r'nunca (contactad\w*|llamad\w*)|sin contactar|lo mas importante (hoy|del dia))\b'],
    'ayuda': [r'^(como|de que forma|que pasos)\b(?!.*\b(vamos|va|van|vas|ibamos|convier\w*|rind\w*)\b)',
              r'\b(que significa|que quiere decir|que es (el|la|un|una) |para que sirve|donde (esta|veo|encuentro|se ve)|'
              r'como se (hace|usa)|no aparece|no llega|no me deja|error|explica\w*)\b'],
    'embudo': [r'\b(embudo|etapas?|se (nos )?quedan|se (nos )?(van|pierden|caen)|en que paso|pipeline)\b'],
    'conversion': [r'\b(convier\w*|conversion\w*|avanz\w*|tasa\w*|efectiv\w*|funciona\w* mejor|rind\w* mejor|mejores resultados|'
                   r'cual canal|que canal|responden mejor|se inscriben mas|mas se inscriben)'],
    'visitas': [r'\b(visitas?|eventos?|platicas?|ferias?)\b'],
    'cifras': [r'\b(cuant[oa]s?|como (vamos|va|van|ibamos)|numeros?|total\w*|llegaron|llego|registr\w*|aspirantes?|tendencia|crec\w*|'
               r'baj\w*|sub\w*|comparad\w*|contra el|vs|cifras?|piden|quieren|interesad\w*|inscrit\w*|permiso|por llamar|contactos|llamadas)'],
}

DIMENSIONES = [
    ('plantel', r'\bplantel(es)?\b'), ('carrera', r'\bcarreras?\b'), ('preparatoria', r'\b(prepas?|preparatorias?|escuelas?|bachilleratos?)\b'),
    ('municipio', r'\bmunicipios?\b'), ('canal', r'\bcanal(es)?\b'), ('modalidad', r'\bmodalidad(es)?|horarios?\b'),
    ('grupo', r'\b(grupos?|segmentos?)\b'), ('estatus', r'\b(estatus|etapas?)\b'), ('visita', r'\b(visitas?|eventos?)\b'),
    ('quien_contesto', r'\bquien contesto|alumno y familia|quien respondio\b'),
]
GRUPOS = [('listo_para_convertir', r'\blistos?( para inscribirse)?\b'), ('sensible_beca', r'\b(beca|becas|precio|costo|dinero)\b'),
          ('horario_flexible', r'\bhorario flexible|horarios? flexible|trabaja\b'), ('indeciso_carrera', r'\bindecis|no decide|sin decidir\b'),
          ('largo_plazo', r'\blargo plazo|en un ano|el proximo ano\b')]
ESTATUS = [(Estatus.INSCRITO, r'\binscrit'), (Estatus.SOLICITO, r'\bsolicit(o|aron|ud) (de )?inscripcion\b'),
           (Estatus.OPEN_HOUSE, r'\bopen house\b'), (Estatus.DESCARTADO, r'\bdescartad'), (Estatus.CONTACTADO, r'\bcontactad[oa]s\b(?! o)')]
GENERICAS_PREPA = set('preparatoria prepa bachillerato escuela colegio centro estudios instituto oficial numero de del la los las '
                      'el y en no simulado ficticia ficticio demo prueba'.split())
LUGARES = set('tultepec cuautitlan izcalli zumpango huehuetoca teoloyucan coyotepec tultitlan melchor ocampo tepotzotlan nextlalpan '
              'jaltenco tecamac ecatepec coacalco toluca metepec mexico estado'.split())
PALABRA_PREPA = r'\b(prepa|preparatoria|bachillerato|escuela|colegio|cbtis|cetis|conalep|cecyt|cobaem|epo|instituto|centro)\b'
GENERICAS_CARRERA = set('ingenieria licenciatura de en y la las los del e'.split())


def _periodo(q: str, hoy: date) -> tuple[date, date, str, bool]:
    """(desde, hasta, cómo decirlo, ¿lo dijo la persona?)."""
    def mes_completo(m, a):
        ini = date(a, m, 1)
        fin = (date(a + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
        return ini, min(fin, hoy)
    if _tiene(q, r'\bhoy\b'):
        return hoy, hoy, 'hoy', True
    if _tiene(q, r'\bayer\b'):
        return hoy - timedelta(days=1), hoy - timedelta(days=1), 'ayer', True
    if _tiene(q, r'\b(esta semana)\b'):
        return hoy - timedelta(days=hoy.weekday()), hoy, 'esta semana', True
    if _tiene(q, r'\b(la )?semana pasada\b'):
        lun = hoy - timedelta(days=hoy.weekday() + 7)
        return lun, lun + timedelta(days=6), 'la semana pasada', True
    if _tiene(q, r'\b(el )?mes (pasado|anterior)\b') and not _tiene(q, r'\bcontra el (mes )?(pasado|anterior)\b|\bvs\b'):
        a, m = (hoy.year, hoy.month - 1) if hoy.month > 1 else (hoy.year - 1, 12)
        d, h = mes_completo(m, a)
        return d, h, f'en {MESES[m - 1]}', True
    if _tiene(q, r'\b(este|en el|del) mes\b'):
        return hoy.replace(day=1), hoy, f'en lo que va de {MESES[hoy.month - 1]}', True
    if _tiene(q, r'\b(este|en el|del) ano\b|\ben lo que va del ano\b'):
        return date(hoy.year, 1, 1), hoy, f'en lo que va de {hoy.year}', True
    if _tiene(q, r'\b(el )?ano pasado\b'):
        return date(hoy.year - 1, 1, 1), date(hoy.year - 1, 12, 31), f'en {hoy.year - 1}', True
    m = re.search(r'\bultim[oa]s? (\d+|' + '|'.join(NUMEROS) + r')? ?(dias?|semanas?|mes(es)?|anos?)\b', q)
    if m:
        n = int(m.group(1)) if m.group(1) and m.group(1).isdigit() else NUMEROS.get(m.group(1) or '', 1)
        dias = {'d': 1, 's': 7, 'm': 30, 'a': 365}[m.group(2)[0]] * max(1, min(n, 1000))
        return hoy - timedelta(days=dias - 1), hoy, f'en los últimos {dias} días', True
    if _tiene(q, r'\bultimo trimestre|tres meses\b'):
        return hoy - timedelta(days=89), hoy, 'en los últimos 90 días', True
    if _tiene(q, r'\bsemestre|seis meses\b'):
        return hoy - timedelta(days=179), hoy, 'en los últimos 6 meses', True
    m = re.search(r'\b(desde|a partir de) (' + '|'.join(MESES) + r')\b', q)
    if m:
        mi = MESES.index(m.group(2)) + 1
        a = hoy.year if mi <= hoy.month else hoy.year - 1
        return date(a, mi, 1), hoy, f'desde {m.group(2)}', True
    m = re.search(r'\b(en|de|durante|del mes de) (' + '|'.join(MESES) + r')(?: (?:de )?(\d{4}))?\b', q)
    if m:
        mi = MESES.index(m.group(2)) + 1
        a = int(m.group(3)) if m.group(3) else (hoy.year if mi <= hoy.month else hoy.year - 1)
        d, h = mes_completo(mi, a)
        return d, h, f'en {m.group(2)}' + (f' de {a}' if a != hoy.year else ''), True
    return hoy - timedelta(days=29), hoy, 'en los últimos 30 días', False


def _carrera(q: str):
    mejor, puntos, empate = None, 0, False
    for c in Carrera.objects.all():
        nombres = [c.nombre, *(c.alias or [])]
        if any(_n(x) and re.search(r'\b' + re.escape(_n(x)) + r'\b', q) for x in nombres):
            return c
        claves = [t for t in _n(c.nombre).split() if len(t) >= 4 and t not in GENERICAS_CARRERA]
        p = sum(1 for t in claves if re.search(r'\b' + re.escape(t[:-1] if len(t) > 6 else t), q))
        if p > puntos:
            mejor, puntos, empate = c, p, False
        elif p == puntos and p:
            empate = True
    return mejor if puntos and not empate else None


def _prepa(q: str):
    mejor, puntos = None, 0
    for p in Preparatoria.objects.filter(activo=True):
        for nombre in [p.nombre, *(p.alias or [])]:
            completo = _n(nombre).strip()
            if len(completo) >= 5 and re.search(r'\b' + re.escape(completo) + r'\b', q):
                return p  # el nombre tal cual («Prepa Uno», «CBTIS 160»)
            claves = [t for t in _n(nombre).split() if len(t) >= 4 and t not in GENERICAS_PREPA]
            if not claves:
                continue
            encontradas = [t for t in claves if re.search(r'\b' + re.escape(t) + r'\b', q)]
            hechos = len(encontradas)
            solo_lugares = all(t in LUGARES for t in encontradas)
            if solo_lugares and not re.search(PALABRA_PREPA, q):
                continue  # «¿y en Tultepec?» habla del plantel o del lugar, no de «Colegio … Tultepec»
            if hechos and (hechos == len(claves) or hechos >= 2):
                if hechos > puntos:
                    mejor, puntos = p, hechos
    return mejor


def _usuario(q_original: str):
    """Persona del equipo mencionada (por correo o nombre). None si no hay o es ambigua."""
    m = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', q_original)
    U = get_user_model()
    if m:
        return U.objects.filter(is_active=True, is_staff=True, username__iexact=m.group(0)).first() or \
            U.objects.filter(is_active=True, is_staff=True, email__iexact=m.group(0)).first()
    q = _n(q_original)
    cands = []
    for u in U.objects.filter(is_active=True, is_staff=True):
        completo = _n(u.get_full_name())
        if completo and re.search(r'\b' + re.escape(completo) + r'\b', q):
            return u
        if u.first_name and re.search(r'\ba ' + re.escape(_n(u.first_name)) + r'\b', q):
            cands.append(u)
    return cands[0] if len(cands) == 1 else None


def _fecha_futura(q: str, hoy: date):
    if _tiene(q, r'\bpasado manana\b'):
        return hoy + timedelta(days=2)
    if _tiene(q, r'\bmanana\b'):
        return hoy + timedelta(days=1)
    m = re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b', q)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r'\b(\d{1,2})(?: de)? (' + '|'.join(MESES) + r')(?:(?: de)? (\d{4}))?\b', q)
    if m:
        mi, d = MESES.index(m.group(2)) + 1, int(m.group(1))
        try:
            if m.group(3):
                return date(int(m.group(3)), mi, d)
            f = date(hoy.year, mi, d)
            return f if f >= hoy else date(hoy.year + 1, mi, d)
        except ValueError:
            return None
    m = re.search(r'\b(el )?(proximo )?(' + '|'.join(DIAS) + r')\b', q)
    if m:
        dias = (DIAS.index(m.group(3)) - hoy.weekday()) % 7 or 7
        return hoy + timedelta(days=dias)
    m = re.search(r'\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b', q)
    if m:
        try:
            a = int(m.group(3)) if m.group(3) else hoy.year
            return date(a + 2000 if a < 100 else a, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def _hora(q: str):
    m = re.search(r'\b(?:a las |alas |@ ?)?(\d{1,2})(?::(\d{2}))? ?(am|pm|hrs|horas|de la manana|de la tarde)\b', q) or \
        re.search(r'\ba las (\d{1,2})(?::(\d{2}))?\b', q)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    sufijo = m.group(3) if m.lastindex and m.lastindex >= 3 else ''
    if sufijo in ('pm', 'de la tarde') and h < 12:
        h += 12
    return f'{h:02d}:{mi:02d}' if 0 <= h < 24 and 0 <= mi < 60 else None


def entender(mensaje: str, memoria: dict, contexto: dict) -> dict:
    q = _n(mensaje)
    hoy = timezone.localdate()
    e = {}
    if re.search(r'\btultepec\b', q):
        e['plantel'] = 'tultepec'
    elif re.search(r'\bcuautitlan\b(?! izcalli)', q):
        e['plantel'] = 'cuautitlan'
    c = _carrera(q)
    if c:
        e['carrera'] = c.nombre
    p = _prepa(q)
    if p:
        e['preparatoria'] = p.nombre
    for valor, patron in GRUPOS:
        if re.search(patron, q):
            e['grupo'] = valor
            break
    for valor, patron in ESTATUS:
        if re.search(patron, q):
            e['estatus'] = valor.value
            break
    if re.search(r'\bsolo (la )?familia|solo (los )?papas\b', q):
        e['quien_contesto'] = 'solo_familia'
    elif re.search(r'\bsolo (el )?alumno\b', q):
        e['quien_contesto'] = 'solo_alumno'
    desde, hasta, periodo_txt, explicito = _periodo(q, hoy)

    # agrupación: «por X», «mes a mes», o «qué X…» (qué carreras, de qué prepas)
    por = None
    m = re.search(r'\bpor (\w+)', q)
    if m:
        por = next((d for d, pat in DIMENSIONES if re.search(pat, m.group(1))), None)
    if not por and _tiene(q, r'\bmes a mes|cada mes|por mes|tendencia|evolucion\b'):
        por = 'mes'
    sujeto = None
    m = re.search(r'\b(que|cuales|de que|en que|cual)\s+(\w+)', q)
    if m:
        sujeto = next((d for d, pat in DIMENSIONES if re.search(pat, m.group(2))), None)
    # cruce: «qué carreras … en cada plantel», «carreras por plantel y …»
    cruce = None
    m = re.search(r'\b(en cada|por cada|segun (el|la)?|de cada)\s*(\w+)', q)
    if m:
        col = next((d for d, pat in DIMENSIONES if re.search(pat, m.group(3))), None)
        fila = sujeto or por
        if col and fila and col != fila:
            cruce = (fila, col)

    # intención
    puntajes = {}
    for nombre, patrones in PALABRAS_INTENCION.items():
        n = sum(1 for pat in patrones if re.search(pat, q))
        if n:
            puntajes[nombre] = n
    ficha = bool(contexto.get('ficha'))
    orden = ['saludo', 'quien_eres', 'asignar', 'crear_visita', 'crear_actividad']
    orden += ['ficha_llamada', 'ficha_mensaje', 'ficha_diferencias'] if ficha else []
    orden += ['pendientes', 'ayuda', 'embudo', 'conversion']
    intencion = next((i for i in orden if i in puntajes), None)
    if intencion == 'ayuda' and _tiene(q, r'\bcuant[oa]s?\b'):
        intencion = None  # «¿cuántos…?» es una cifra aunque empiece con «cómo»
    if not intencion:
        if cruce:
            intencion = 'cruce'
        elif 'visitas' in puntajes and (sujeto != 'visita' or not _tiene(q, r'\baspirantes?\b')) and \
                not _tiene(q, r'\bpor (visita|evento)\b'):
            intencion = 'visitas'
        elif 'cifras' in puntajes or sujeto or por:
            intencion = 'cifras'
    entidades_nuevas = bool(set(e) - {'grupo'} or explicito)
    seguimiento = bool(re.match(r'^\W*(y|e|tambien|ahora)\b', q)) and memoria.get('intencion') in ('cifras', 'conversion', 'embudo', 'cruce')
    if seguimiento and intencion == 'cifras' and not _tiene(q, r'\bcuant'):
        intencion = None  # «¿y por carrera?»: es la misma pregunta con otro corte
    if not intencion and memoria.get('intencion') and (entidades_nuevas or (seguimiento and por)) and len(q.split()) <= 8:
        intencion = memoria['intencion']  # «¿y en Tultepec?»: misma pregunta, otro filtro
        heredados = dict(memoria.get('args') or {})
        for k in ('plantel', 'carrera', 'preparatoria', 'grupo', 'estatus'):
            if k in e:
                heredados[k] = e[k]
        e = {**heredados, **e}
        if not explicito and memoria.get('periodo'):
            desde, hasta, periodo_txt = date.fromisoformat(memoria['periodo'][0]), date.fromisoformat(memoria['periodo'][1]), memoria['periodo'][2]
        nuevos = set(e) - set(heredados) | {k for k in ('plantel', 'carrera', 'preparatoria') if k in e and e[k] != (memoria.get('args') or {}).get(k)}
        por = por or (memoria.get('args') or {}).get('agrupar_por')
        if por in nuevos:
            por = None  # «por plantel» y luego «¿y en Tultepec?»: agrupar por plantel ya no dice nada
        e['_heredada'] = True

    if por == 'mes' and not explicito:
        desde, periodo_txt = (hoy - timedelta(days=179)).replace(day=1), 'en los últimos 6 meses'
    metrica = 'aspirantes'
    if _tiene(q, r'\binscrit'):
        metrica = 'inscritos'
        e.pop('estatus', None)
    elif _tiene(q, r'\b(esperando permiso|sin permiso|menores|esperan permiso|permiso de (la|su) familia)\b'):
        metrica = 'esperando_permiso'
    elif _tiene(q, r'\b(por llamar|se pueden llamar|llamar hoy|activos)\b'):
        metrica = 'por_llamar'
    elif _tiene(q, r'\b(cuant[oa]s (llamadas|contactos|whats?apps?|correos)|contactos (hicimos|registrados)|llamamos|contactamos)\b'):
        metrica = 'contactos'
    args = {k: v for k, v in e.items() if not k.startswith('_')}
    args.update({'desde': desde.isoformat(), 'hasta': hasta.isoformat(), 'metrica': metrica})
    if metrica in ('esperando_permiso', 'por_llamar') and not explicito:
        args['sin_periodo'] = True  # «¿cuántos menores esperan permiso?» = todos los de hoy
        periodo_txt = 'hoy'
    if intencion == 'cifras':
        args['agrupar_por'] = por or sujeto
    if intencion == 'conversion':
        args['agrupar_por'] = sujeto or por or ('canal' if _tiene(q, r'\b(canal|whats?app|correo)\b') or e.get('plantel') else 'plantel')
        if not explicito:
            args['desde'] = (hoy - timedelta(days=179)).isoformat()
            periodo_txt = 'en los últimos 6 meses'
    if intencion == 'cruce':
        args['filas'], args['columnas'] = cruce
    return {'intencion': intencion, 'args': args, 'periodo_txt': periodo_txt, 'periodo_explicito': explicito,
            'heredada': bool(e.get('_heredada')), 'q': q, 'original': mensaje, 'usuario_mencionado': _usuario(mensaje),
            'fecha': _fecha_futura(q, hoy), 'hora': _hora(q), 'cantidad': _cantidad(q)}


def _cantidad(q: str):
    m = re.search(r'\b(\d{1,3})\b(?! (de|del) )', q)
    if m:
        return int(m.group(1))
    m = re.search(r'\b(' + '|'.join(NUMEROS) + r')\b (aspirantes|primeros|de mayor|mejores|listos)', q)
    return NUMEROS[m.group(1)] if m else None


# =========================================================================== redactar
def _num(n) -> str:
    return f'{n:,}'.replace(',', ' ') if isinstance(n, int) else str(n)


def _cambio_txt(actual, previo) -> str:
    if previo is None:
        return ''
    if previo == 0:
        return ', y en el periodo anterior no hubo ninguno' if actual else ''
    d = actual - previo
    if d == 0:
        return f', igual que en el periodo anterior ({_num(previo)})'
    if previo < 5:
        return f", {_num(abs(d))} {'más' if d > 0 else 'menos'} que en el periodo anterior (antes {_num(previo)})"
    pct = round(d / previo * 100)
    return f", {_num(abs(d))} {'más' if d > 0 else 'menos'} que en el periodo anterior (**{pct:+d} %**)"


def _filtros_txt(args) -> str:
    partes = []
    if args.get('plantel'):
        partes.append(f"en {dict(A.Plantel.choices).get(args['plantel'], args['plantel'])}")
    if args.get('carrera'):
        partes.append(f"interesados en {args['carrera']}")
    if args.get('preparatoria'):
        partes.append(f"de {args['preparatoria']}")
    if args.get('grupo'):
        partes.append(f"del grupo «{etiqueta_segmento(args['grupo'])}»")
    if args.get('estatus'):
        partes.append(f"en «{dict(Estatus.choices).get(args['estatus'])}»")
    return (' ' + ' '.join(partes)) if partes else ''


def _enlace(txt, url) -> str:
    return f'[{txt}]({url})' if url else txt


SUSTANTIVO = {'aspirantes': ('aspirante nuevo', 'aspirantes nuevos'), 'inscritos': ('inscrito', 'inscritos'),
              'por_llamar': ('aspirante por llamar', 'aspirantes por llamar'),
              'esperando_permiso': ('menor esperando permiso', 'menores esperando permiso'),
              'contactos': ('contacto registrado', 'contactos registrados')}


def _plural(n, metrica):
    uno, varios = SUSTANTIVO.get(metrica, ('aspirante', 'aspirantes'))
    return uno if n == 1 else varios


def r_cifras(user, ent) -> dict:
    a = ent['args']
    r = A.cifras(user, a)
    m = a['metrica']
    total = r['total']
    per = 'hoy' if a.get('sin_periodo') or m == 'por_llamar' else ent['periodo_txt']
    lineas = [f"{per.capitalize()}: **{_num(total)} {_plural(total, m)}**{_filtros_txt(a)}"
              + (_cambio_txt(total, (r.get('periodo_anterior') or {}).get('total')) if not a.get('sin_periodo') and m != 'por_llamar' else '') + '.']
    hallazgos, siguientes = [], []
    grupos = [g for g in r.get('grupos', []) if isinstance(g['n'], int)]
    por = r.get('agrupado_por')
    if grupos:
        for g in r['grupos'][:6]:
            antes = g.get('periodo_anterior')
            lineas.append(f"- **{g['grupo']}:** {_num(g['n'])}" + (f" ({g['parte_del_total_pct']} %)" if g.get('parte_del_total_pct') is not None else '')
                          + (f", antes {antes}" if antes not in (None, '') and por != 'mes' else ''))
        if len(r['grupos']) > 6:
            lineas.append(f"- y {len(r['grupos']) - 6} más.")
        # hallazgos
        if por == 'mes' and len(grupos) >= 2:
            mejor = max(grupos, key=lambda g: g['n'])
            ultimo = grupos[-1]
            prom = sum(g['n'] for g in grupos[:-1]) / max(1, len(grupos) - 1)
            hallazgos.append(f"El mejor mes fue **{_mes_txt(mejor['grupo'])}** con {mejor['n']}.")
            if prom:
                hallazgos.append(f"{_mes_txt(ultimo['grupo']).capitalize()} va en {ultimo['n']}, "
                                 f"{'arriba' if ultimo['n'] >= prom else 'abajo'} del promedio de los meses anteriores ({round(prom)}).")
        else:
            cambios = [(g, g['n'] - g['periodo_anterior']) for g in grupos if isinstance(g.get('periodo_anterior'), int)]
            if cambios:
                sube = max(cambios, key=lambda x: x[1])
                baja = min(cambios, key=lambda x: x[1])
                if sube[1] >= 3:
                    hallazgos.append(f"Lo que más creció: **{sube[0]['grupo']}** (+{sube[1]}).")
                if baja[1] <= -3:
                    hallazgos.append(f"Lo que más bajó: **{baja[0]['grupo']}** ({baja[1]}).")
            top = next((g for g in grupos if not g['grupo'].startswith('Sin ')), grupos[0])
            if total and top['n'] / total >= .5 and len(grupos) > 1:
                hallazgos.append(f"**{top['grupo']}** concentra más de la mitad ({round(top['n'] / total * 100)} %).")
            sin = next((g for g in grupos if g['grupo'].startswith('Sin ')), None)
            if sin and total and sin['n'] / total >= .2:
                hallazgos.append(f"Ojo: {sin['n']} ({round(sin['n'] / total * 100)} %) quedan como «{sin['grupo']}»; "
                                 'conviene revisar que la pregunta del Form coincida con el catálogo.')
    if r.get('advertencia'):
        hallazgos.append(r['advertencia'])
    if hallazgos:
        lineas.append('')
        lineas += [f'- {h}' for h in hallazgos[:3]]
    # qué haría
    if m in ('aspirantes', 'por_llamar') and total:
        cola = reverse('prospectos:cola') + (f"?plantel={a['plantel']}" if a.get('plantel') else '')
        lineas.append(f"\n**Qué haría:** {_enlace('revisar la lista', r.get('enlace_a_la_lista'))} y empezar por los de mayor "
                      f"prioridad en {_enlace('A quién llamar hoy', cola)}.")
    elif m == 'esperando_permiso' and total:
        lineas.append(f"\n**Qué haría:** revisar {_enlace('Familias por unir', reverse('prospectos:familias'))}: muchos ya tienen el "
                      f"permiso de su familia pero no se han unido. A los demás, pedir el permiso desde {_enlace('Respuestas de los Forms', reverse('prospectos:respuestas'))}.")
    elif total:
        lineas.append(f"\n{_enlace('Ver la lista', r.get('enlace_a_la_lista'))}.")
    # siguientes
    lugar = f" en {dict(A.Plantel.choices)[a['plantel']]}" if a.get('plantel') else ''
    if not por:
        siguientes += ['¿Y por plantel?' if not a.get('plantel') else '¿Y por carrera?', f'¿Cómo vamos mes a mes{lugar}?']
    elif por == 'plantel':
        siguientes += ['¿Qué carreras piden en cada plantel?']
    elif por == 'carrera':
        siguientes += [f'¿De qué prepas vienen{lugar}?']
    elif por == 'mes':
        siguientes += ['¿Y por plantel?' if not a.get('plantel') else '¿Y por carrera?']
    siguientes += [f'¿Qué canal convierte mejor{lugar}?', '¿Qué es lo más urgente hoy?']
    return _salida(lineas, siguientes, r, 'consultar_cifras')


def _mes_txt(clave: str) -> str:
    try:
        a, m = clave.split('-')
        return f'{MESES[int(m) - 1]} {a}'
    except (ValueError, IndexError):
        return clave


def r_cruce(user, ent) -> dict:
    a = ent['args']
    r = A.cruce(user, a)
    if r.get('error'):
        return _salida([r['error']], ['¿Qué carreras piden en cada plantel?'], None, None)
    cols = r['columnas']
    lineas = [f"{ent['periodo_txt'].capitalize()}: **{_num(r['total'])} aspirantes nuevos**{_filtros_txt(a)}, por {r['filas']} y {r['columnas'] and a['columnas']}:"]
    for fila in r['tabla'][:8]:
        partes = ', '.join(f"{c}: {fila.get(c, 0)}" for c in cols)
        lineas.append(f"- **{fila[r['filas']]}** ({fila['total']}) — {partes}")
    # hallazgo: dónde se concentra cada columna
    hall = []
    for c in cols[:3]:
        mejores = [f for f in r['tabla'] if isinstance(f.get(c), int) and not str(f[r['filas']]).startswith('Sin ')]
        if mejores:
            top = max(mejores, key=lambda f: f[c])
            hall.append(f"En **{c}** lo que más se pide es {top[r['filas']]} ({top[c]}).")
    if hall:
        lineas.append('')
        lineas += [f'- {h}' for h in hall]
    lineas.append(f"\n{_enlace('Ver la lista', r.get('enlace_a_la_lista'))}. Las celdas con menos de 3 se ocultan.")
    sig = [f"¿Qué canal convierte mejor en {cols[0]}?" if cols else '¿Qué canal convierte mejor?', '¿Cómo vamos mes a mes?']
    return _salida(lineas, sig, r, 'cruzar', visual=None)


def r_conversion(user, ent) -> dict:
    a = ent['args']
    r = A.conversion(user, a)
    if not r['aspirantes']:
        return _salida([f"{ent['periodo_txt'].capitalize()} no hay aspirantes{_filtros_txt(a)} para calcular tasas."], ['¿Cómo vamos este mes?'], r, 'conversion')
    lineas = [f"{ent['periodo_txt'].capitalize()}, de **{_num(r['aspirantes'])} aspirantes**{_filtros_txt(a)}, el **{r['contactados_o_mas_pct']} %** "
              f"ya fue contactado o avanzó y el **{r['inscritos_pct']} %** está inscrito."]
    confiables = [g for g in r['grupos'] if g['confiable']]
    for g in sorted(r['grupos'], key=lambda g: -g['contactados_o_mas_pct'])[:6]:
        lineas.append(f"- **{g['grupo']}:** {g['contactados_o_mas_pct']} % contactados o más, {g['inscritos_pct']} % inscritos "
                      f"(de {g['aspirantes']}){'' if g['confiable'] else ' — pocos casos'}")
    accion = None
    if len(confiables) >= 2:
        mejor = max(confiables, key=lambda g: g['contactados_o_mas_pct'])
        peor = min(confiables, key=lambda g: g['contactados_o_mas_pct'])
        if mejor['contactados_o_mas_pct'] - peor['contactados_o_mas_pct'] >= 10:
            lineas.append(f"\n- La diferencia es grande: **{mejor['grupo']}** avanza {mejor['contactados_o_mas_pct'] - peor['contactados_o_mas_pct']} "
                          f"puntos más que **{peor['grupo']}**.")
        else:
            lineas.append('\n- Los grupos avanzan parecido: la diferencia es menor a 10 puntos.')
        if isinstance(peor['nunca_contactados'], int) and peor['nunca_contactados']:
            accion = f"**Qué haría:** contactar a los {peor['nunca_contactados']} de **{peor['grupo']}** que nunca han recibido una llamada."
    elif r['grupos']:
        lineas.append('\n- Hay muy pocos casos por grupo para comparar con confianza.')
    if r['inscritos_pct'] == 0 and r['aspirantes'] >= 20:
        lineas.append('- Nadie aparece como inscrito: si ya hay inscripciones, los asesores deben marcar el estatus **Inscrito** en la ficha.')
    lineas.append('\n' + (accion + ' ' if accion else '') + _enlace('Ver la lista', r.get('enlace_a_la_lista')) + '.')
    dim = r['agrupado_por']
    otra = 'preparatoria' if dim != 'preparatoria' else 'canal'
    sig = [f"¿Qué {'prepas' if otra == 'preparatoria' else 'canal'} convierten mejor?", '¿En qué etapa del embudo se nos quedan más?',
           '¿Qué es lo más urgente hoy?']
    return _salida(lineas, sig, r, 'conversion')


def r_embudo(user, ent) -> dict:
    from .asistente import h_embudo
    a = ent['args']
    r = h_embudo(user, a)
    t = r['total']
    if not t:
        return _salida([f"{ent['periodo_txt'].capitalize()} no hay aspirantes nuevos{_filtros_txt(a)}."], ['¿Y en los últimos 6 meses?'], r, 'embudo')
    ll = r['llegaron_al_menos_a']
    etapas = list(ll.items())
    lineas = [f"{ent['periodo_txt'].capitalize()} llegaron **{_num(t)} aspirantes**{_filtros_txt(a)}. Hasta dónde han avanzado:"]
    for nombre, n in etapas[1:]:
        lineas.append(f"- **{nombre}:** {n} ({round(n / t * 100)} %)")
    caidas = [(etapas[i][0], etapas[i + 1][0], etapas[i][1] - etapas[i + 1][1], etapas[i][1]) for i in range(len(etapas) - 1) if etapas[i][1]]
    if ll.get('Inscrito') == 0 and len(caidas) > 1:
        caidas = caidas[:-1]
        lineas.append('\n- Nadie aparece como **Inscrito**: si ya hay inscripciones, hay que marcarlas en la ficha; si no, todavía es pronto.')
    if caidas:
        de, a_, perdidos, base = max(caidas, key=lambda x: x[2] / x[3] if x[3] else 0)
        lineas.append(f"\n- Donde más se quedan: de **{de}** a **{a_}** ({perdidos} de {base}, {round(perdidos / base * 100)} %).")
        estatus = {e.label: e.value for e in Estatus}.get(de)
        url = r['enlace_a_la_lista'] + (f'&estatus__exact={estatus}' if estatus and '?' in r['enlace_a_la_lista'] else '')
        lineas.append(f"\n**Qué haría:** revisar a los que siguen en «{de}» ({_enlace('ver la lista', url)}).")
    sig = ['¿Qué canal convierte mejor?', '¿Qué prepas mandan aspirantes que sí avanzan?', '¿Qué es lo más urgente hoy?']
    return _salida(lineas, sig, r, 'embudo')


def r_visitas(user, ent) -> dict:
    q = ent['q']
    hoy = timezone.localdate()
    futuras = _tiene(q, r'\b(proxim|siguiente|vienen|agenda|tenemos|hay|esta semana|mes que viene|manana)\b') and \
        not _tiene(q, r'\b(rindieron|rindio|resultado|funcionaron|registros por|costo|mejor|peor)\b')
    if futuras:
        r = A.visitas(user, {'desde': hoy.isoformat(), 'hasta': (hoy + timedelta(days=30)).isoformat()})
        vs = [v for v in r['visitas'] if v['estado'] != 'Cancelado']
        if not vs:
            return _salida(['No hay visitas en los próximos 30 días.', '',
                            f"**Qué haría:** programar las siguientes desde el {_enlace('Calendario', reverse('prospectos:calendario'))}."],
                           ['¿Qué visitas rindieron más registros por costo?', '¿Qué prepas no hemos visitado en 6 meses?'], r, None)
        lineas = [f"En los próximos 30 días hay **{len(vs)} visita{'s' if len(vs) != 1 else ''}**:"]
        sin_conf = [v for v in vs if v['estado'] in ('Por solicitar', 'Solicitado')]
        for v in vs[:8]:
            d = date.fromisoformat(v['fecha'])
            lineas.append(f"- **{d.day} {MESES[d.month - 1][:3]}** · {v['preparatoria']} · {v['estado'].lower()}"
                          + (f" · {v['cartas_de_beca']} cartas de beca" if v['cartas_de_beca'] else ''))
        if sin_conf:
            lineas.append(f"\n- **Ojo:** {len(sin_conf)} todavía no {'está confirmada' if len(sin_conf) == 1 else 'están confirmadas'} por la prepa.")
        lineas.append(f"\n{_enlace('Ver el calendario', reverse('prospectos:calendario'))}.")
        return _salida(lineas, ['¿Qué visitas rindieron más registros por costo?', '¿Cómo vamos este mes?'], r, None)
    desde, hasta = date.fromisoformat(ent['args']['desde']), date.fromisoformat(ent['args']['hasta'])
    if not ent['periodo_explicito']:
        desde = hoy - timedelta(days=90)
    r = A.visitas(user, {'desde': desde.isoformat(), 'hasta': min(hasta, hoy).isoformat()})
    hechas = [v for v in r['visitas'] if date.fromisoformat(v['fecha']) <= hoy and v['estado'] != 'Cancelado']
    if not hechas:
        return _salida([f"No hubo visitas {ent['periodo_txt'] if ent['periodo_explicito'] else 'en los últimos 90 días'}."],
                       ['¿Qué visitas tenemos los próximos días?'], r, None)
    total = sum(v['registros'] for v in hechas)
    per = ent['periodo_txt'] if ent['periodo_explicito'] else 'en los últimos 90 días'
    lineas = [f"{per.capitalize()} hubo **{len(hechas)} visitas** que dejaron **{_num(total)} registros** "
              f"(promedio {round(total / len(hechas))} por visita)."]
    por_reg = sorted(hechas, key=lambda v: -v['registros'])
    for v in por_reg[:5]:
        extra = []
        if v.get('avance_meta_pct') is not None:
            extra.append(f"{v['avance_meta_pct']} % de la meta")
        if v.get('respuesta_pct') is not None:
            extra.append(f"contestó el {v['respuesta_pct']} % de los asistentes")
        if v.get('costo_por_registro') is not None:
            extra.append(f"${v['costo_por_registro']:,.0f} por registro")
        lineas.append(f"- **{v['preparatoria']}** ({v['fecha'][8:]}/{v['fecha'][5:7]}): {v['registros']} registros"
                      + (f" · {' · '.join(extra)}" if extra else ''))
    con_costo = [v for v in hechas if v.get('costo_por_registro') is not None]
    if len(con_costo) >= 2:
        barata = min(con_costo, key=lambda v: v['costo_por_registro'])
        cara = max(con_costo, key=lambda v: v['costo_por_registro'])
        lineas.append(f"\n- La más rentable: **{barata['preparatoria']}** (${barata['costo_por_registro']:,.0f} por registro); "
                      f"la más cara: **{cara['preparatoria']}** (${cara['costo_por_registro']:,.0f}).")
    bajas = [v for v in hechas if v.get('respuesta_pct') is not None and v['respuesta_pct'] < 10]
    if bajas:
        lineas.append(f"- En {len(bajas)} visita{'s' if len(bajas) > 1 else ''} contestó menos del 10 % de los asistentes: "
                      'conviene dar tiempo para escanear el QR durante la plática.')
    lineas.append(f"\n{_enlace('Ver los eventos', reverse('admin:prospectos_evento_changelist'))}.")
    return _salida(lineas, ['¿Qué visitas tenemos los próximos días?', '¿Qué prepas mandan aspirantes que sí avanzan?'], r, None)


def r_pendientes(user, ent) -> dict:
    r = A.pendientes(user, {})
    activos = [p for p in r['pendientes'] if p['n']]
    if not activos:
        return _salida(['**Nada urgente.** No hay llamadas vencidas, familias por unir ni duplicados pendientes.'],
                       ['¿Cómo vamos este mes?', '¿Qué visitas tenemos los próximos días?'], r, 'pendientes')
    primero = activos[0]
    lineas = [f"Lo más urgente: **{_num(primero['n'])} {primero['que'][0].lower() + primero['que'][1:]}**"
              + (f" — {primero['por_que_importa']}." if primero.get('por_que_importa') else '.')]
    for p in activos[1:6]:
        lineas.append(f"- {_enlace(p['que'], p['enlace'])}: **{_num(p['n'])}**" + (f" ({p['por_que_importa']})" if p.get('por_que_importa') else ''))
    lineas.append(f"\n**Qué haría:** empezar por {_enlace('esa lista', primero['enlace'])} y, antes de terminar el día, "
                  f"{_enlace('Familias por unir', reverse('prospectos:familias'))}, porque destraba permisos.")
    return _salida(lineas, ['¿Cuántos listos para inscribirse hay por plantel?', '¿Qué canal convierte mejor?'], r, 'pendientes')


PANTALLA_DE_SECCION = [  # (palabra del título del manual, ruta de la pantalla)
    ('familias', 'prospectos:familias'), ('respuestas de los forms', 'prospectos:respuestas'), ('llamar', 'prospectos:cola'),
    ('avisos', 'prospectos:avisos'), ('visitas', 'admin:prospectos_evento_changelist'), ('calendario', 'prospectos:calendario'),
    ('mapa', 'prospectos:mapa'), ('reporte', 'prospectos:reporte'), ('encuestas', 'prospectos:encuestas'),
    ('duplicados', 'admin:prospectos_posiblecoincidencia_changelist'), ('proteccion', 'prospectos:proteccion'),
]


def r_ayuda(user, ent) -> dict:
    from .asistente import buscar_ayuda
    secciones = buscar_ayuda(ent['original'], 3)
    if not secciones:
        return r_no_entendi(user, ent)
    s = secciones[0]
    titulo = re.sub(r'^\d+\.\s*', '', s['titulo'])
    cuerpo = s['texto']
    if len(cuerpo) > 1100:
        cuerpo = cuerpo[:1100].rsplit('\n', 1)[0] + '\n…'
    url = next((reverse(n) for clave, n in PANTALLA_DE_SECCION if clave in _n(titulo)), None)
    lineas = [f"**{titulo}**", cuerpo]
    if url:
        lineas.append(f"\n{_enlace('Ir a la pantalla', url)} · {_enlace('Guía completa', reverse('prospectos:ayuda'))}")
    otras = [re.sub(r'^\d+\.\s*', '', x['titulo']) for x in secciones[1:]]
    sig = [f'Explícame «{o}»' for o in otras][:2] + ['¿Qué es lo más urgente hoy?']
    return _salida(lineas, sig, None, None, calculos=[{'que': f"Del manual, sección «{titulo}».", 'enlace': None}])


# --------------------------------------------------------------------------- ficha
def _perfil(user, contexto):
    from .asistente import h_perfil
    pk = contexto.get('ficha')
    perfil = h_perfil(user, {}, contexto)
    p = Prospecto.objects.filter(pk=pk).first() if pk else None
    return perfil, p


def _primer_nombre(p) -> str:
    return (p.nombre_aspirante or '').split()[0].capitalize() if p and p.nombre_aspirante else 'el aspirante'


def _asesor(user) -> str:
    return (user.first_name or user.get_username().split('@')[0]).split()[0].capitalize()


def r_ficha_llamada(user, ent, contexto) -> dict:
    perfil, p = _perfil(user, contexto)
    if perfil.get('error'):
        return _salida([perfil['error']], [], None, None)
    nombre, asesor = _primer_nombre(p), _asesor(user)
    carreras = perfil['carreras']
    grupos = perfil['grupos']
    objetivo = {'Registrado': 'Primer contacto: presentarte y confirmar su interés.',
                'Contactado': 'Invitarlo al open house o a una visita al plantel.',
                'Asistió a open house': 'Llevarlo a la solicitud de inscripción.',
                'Solicitó inscripción': 'Ayudarle a terminar la inscripción: documentos y pago.'}.get(perfil['estatus'], 'Dar seguimiento.')
    interes = carreras[0] if carreras else None
    lineas = [f"**Objetivo:** {objetivo}",
              f"**Cómo abrir:** «Hola, {nombre}, soy {asesor} de la Universidad de Cuautitlán. Vi que te interesa "
              f"{interes if interes else 'conocer nuestras carreras'}; ¿tienes cinco minutos?»", '', '**Preguntas clave:**']
    preguntas = []
    difs = perfil['diferencias_con_la_familia']
    for d in difs[:2]:
        if 'carrera' in d.lower():
            preguntas.append('Tu familia marcó otra carrera que tú: ¿ya lo platicaron? ¿Qué te atrae más de la tuya?')
        elif 'modalidad' in d.lower():
            preguntas.append('Tú y tu familia eligieron horarios distintos: ¿cuál te acomoda de verdad?')
        elif 'paga' in d.lower() or 'econ' in d.lower():
            preguntas.append('¿Quién te va a apoyar con la colegiatura? ¿Les gustaría conocer los planes de pago?')
        else:
            preguntas.append(f'Sobre esto no coinciden con su familia: «{d}». ¿Cómo lo ven?')
    if len(carreras) > 1:
        preguntas.append(f"Marcaste {', '.join(carreras[:3])}: ¿cuál es la que más te late y por qué?")
    if 'Busca beca o precio' in grupos:
        preguntas.append('¿Qué tanto pesa el costo en tu decisión? ¿Conoces las becas que manejamos?')
    if 'Necesita horario flexible' in grupos:
        preguntas.append('¿Trabajas o tienes otra actividad entre semana? Tenemos opciones sabatinas.')
    if 'Aún no decide carrera' in grupos:
        preguntas.append('¿Qué materias disfrutas más? Te puedo contar de carreras parecidas.')
    if perfil['quien_contesto'] == 'solo el alumno':
        preguntas.append('¿Tu familia ya sabe que estás viendo la UDC? ¿Les gustaría venir al open house?')
    if not preguntas:
        preguntas.append('¿Qué es lo más importante para ti al elegir universidad?')
    lineas += [f'{i}. {x}' for i, x in enumerate(preguntas[:3], 1)]
    objeciones = []
    if 'Busca beca o precio' in grupos:
        objeciones.append('**«Está muy cara»** → pregunta qué presupuesto manejan y explica que hay becas y planes de pago; '
                          'no prometas un porcentaje: se define en Admisiones.')
    if 'Necesita horario flexible' in grupos or perfil.get('modalidad') in ('Sabatino', 'Dominical'):
        objeciones.append('**«No me da el tiempo»** → menciona la modalidad sabatina y que puede conocer el horario en el open house.')
    if 'Aún no decide carrera' in grupos:
        objeciones.append('**«No sé qué estudiar»** → ofrece la orientación vocacional o una visita a clases.')
    if 'Entraría en un año o más' in grupos:
        objeciones.append('**«Todavía no voy a entrar»** → no presiones: pide permiso para escribirle antes del siguiente ciclo.')
    if not objeciones:
        objeciones.append('**«Lo voy a pensar»** → propone una fecha concreta para el open house o una visita.')
    lineas += ['', '**Si dice…**'] + [f'- {o}' for o in objeciones[:2]]
    siguiente = {'Registrado': 'agendar su visita al open house', 'Contactado': 'confirmar su asistencia al open house',
                 'Asistió a open house': 'enviarle los requisitos de inscripción', 'Solicitó inscripción': 'revisar qué documento le falta'}
    lineas += ['', f"**Siguiente paso:** {siguiente.get(perfil['estatus'], 'registrar el contacto en la ficha')}. Al terminar, registra la llamada en esta ficha."]
    if perfil['dias_sin_contacto'] is not None and perfil['dias_sin_contacto'] > 14:
        lineas.insert(1, f"_Lleva {perfil['dias_sin_contacto']} días sin contacto._")
    return _salida(lineas, ['Escribe un WhatsApp para invitarlo al open house', '¿En qué no coincide con su familia?'], None, None,
                   calculos=[{'que': 'Armado con las respuestas de opción de esta ficha, sus grupos y su estatus.', 'enlace': None}])


def r_ficha_mensaje(user, ent, contexto) -> dict:
    perfil, p = _perfil(user, contexto)
    if perfil.get('error'):
        return _salida([perfil['error']], [], None, None)
    nombre, asesor = _primer_nombre(p), _asesor(user)
    carrera = perfil['carreras'][0] if perfil['carreras'] else None
    plantel = perfil.get('plantel')
    q = ent['q']
    motivo = 'el open house' if _tiene(q, r'open house|invit') else ('las becas' if _tiene(q, r'beca') else None)
    tema = f"de {carrera}" if carrera else 'de nuestras carreras'
    if not motivo:
        motivo = 'el open house' if perfil['estatus'] in ('Registrado', 'Contactado') else 'tu inscripción'
    becas = 'Busca beca o precio' in perfil['grupos']
    cercana = (f"¡Hola, {nombre}! Soy {asesor}, de la Universidad de Cuautitlán{f' plantel {plantel}' if plantel else ''}. "
               f"Vi que te interesa la carrera {tema} 🙂 ¿Te gustaría venir a {motivo} para conocer el plantel y resolver tus dudas"
               f"{' sobre becas' if becas else ''}?")
    formal = (f"Buen día, {nombre}. Le saluda {asesor}, de Admisiones de la Universidad de Cuautitlán. Con gusto le compartimos "
              f"información {tema}{' y de nuestros apoyos económicos' if becas else ''}. ¿Le interesaría agendar su visita a {motivo}?")
    from ..models import Perfil
    firma = Perfil.de(user).firma.strip()
    if firma:
        cercana, formal = f'{cercana}\n{firma}', f'{formal}\n{firma}'
    lineas = ['**Cercana:**', cercana, '', '**Formal:**', formal, '',
              f"_{len(cercana)} y {len(formal)} caracteres. Revísalo antes de enviarlo: no prometas porcentajes de beca._"]
    return _salida(lineas, ['Prepara la llamada con este aspirante', '¿En qué no coincide con su familia?'], None, None)


def r_ficha_diferencias(user, ent, contexto) -> dict:
    perfil, p = _perfil(user, contexto)
    if perfil.get('error'):
        return _salida([perfil['error']], [], None, None)
    if perfil['quien_contesto'] != 'alumno y familia':
        return _salida([f"Solo contestó {perfil['quien_contesto'].replace('solo ', '')}: no hay con qué comparar.",
                        "Para tener las dos versiones, comparte con la familia el QR del cuestionario de padres."],
                       ['Prepara la llamada con este aspirante'], None, None)
    filas = [f for f in perfil['respuestas_por_tema'] if f['alumno'] and f['familia']]
    distintas = [f for f in filas if not f['coinciden']]
    lineas = [f"**{len(filas) - len(distintas)} de {len(filas)}** respuestas coinciden entre {_primer_nombre(p)} y su familia."]
    for f in distintas[:5]:
        lineas.append(f"- **{f['pregunta']}:** alumno «{f['alumno']}» · familia «{f['familia']}»")
    if distintas:
        lineas.append('\n**Cómo abordarlo:** pregunta primero qué opina el alumno y después cómo lo ve su familia. '
                      'No tomes partido: ofrece que vengan juntos al open house para resolverlo con información.')
    return _salida(lineas, ['Prepara la llamada con este aspirante', 'Escribe un WhatsApp para invitarlo al open house'], None, None)


# --------------------------------------------------------------------------- propuestas
def r_asignar(user, ent) -> tuple:
    from .asistente import proponer
    u = ent['usuario_mencionado']
    if not u:
        return _salida(['¿A quién se los asigno? Escribe su correo, por ejemplo: «asigna 10 listos de Tultepec a asesora@udc.mx».'],
                       [], None, None), []
    args = {**{k: v for k, v in ent['args'].items() if k in ('plantel', 'carrera', 'preparatoria', 'grupo', 'estatus')},
            'asesor': u.username, 'maximo': ent['cantidad'] or 20,
            'solo_sin_asesor': not _tiene(ent['q'], r'\b(aunque tengan|ya asignad\w*|reasign\w*|con asesor)\b')}
    r = proponer(user, 'asignar_asesor', args)
    if r.get('error') and args['solo_sin_asesor'] and 'Ningún' in r['error']:
        con = proponer(user, 'asignar_asesor', {**args, 'solo_sin_asesor': False})
        if not con.get('error'):
            return _salida([f"Todos los que cumplen eso{_filtros_txt(args)} **ya tienen asesor**.",
                            f"Si quieres cambiárselos a {u.get_full_name() or u.username}, escribe lo mismo empezando con «reasigna»."],
                           [], None, None), []
    if r.get('error'):
        return _salida([r['error']], ['¿Cuántos listos para inscribirse hay por plantel?'], None, None), []
    n = r['para_la_ia']['aspirantes']
    quien = u.get_full_name() or u.username
    lineas = [f"Te preparé la propuesta para asignar **{n} aspirante{'s' if n != 1 else ''}** a **{quien}**{_filtros_txt(args)}, "
              'los de mayor prioridad' + (' que no tienen asesor.' if args['solo_sin_asesor'] else '.'),
              'Revisa la lista y pulsa **Confirmar**. Todavía no se cambió nada.']
    return _salida(lineas, [], None, None), [r['propuesta']]


def r_crear_visita(user, ent) -> tuple:
    from .asistente import proponer
    prepa = ent['args'].get('preparatoria')
    if not prepa:
        return _salida(['¿A qué preparatoria? Escríbela como aparece en Preparatorias, por ejemplo: «agenda visita a CBTIS 160 el 12 de noviembre».'],
                       [], None, None), []
    if not ent['fecha']:
        return _salida([f'¿Qué día sería la visita a {prepa}? Por ejemplo: «el 12 de noviembre a las 9».'], [], None, None), []
    args = {'preparatoria': prepa, 'fecha': ent['fecha'].isoformat(), 'hora_inicio': ent['hora'] or '',
            'actividad': next((a for a, pat in [('feria', 'feria'), ('stand', 'stand'), ('taller', 'taller'), ('visita', 'visita guiada')]
                               if pat in ent['q']), 'platica')}
    if ent['usuario_mencionado']:
        args['promotor'] = ent['usuario_mencionado'].username
    r = proponer(user, 'crear_visita', args)
    if r.get('error'):
        return _salida([r['error']], [], None, None), []
    return _salida([f"Te preparé la visita a **{prepa}** el **{ent['fecha'].day} de {MESES[ent['fecha'].month - 1]}**"
                    + (f" a las {ent['hora']}" if ent['hora'] else '') + '. Revisa los datos y pulsa **Confirmar**.',
                    'Después podrás generar la solicitud para la prepa y el QR desde Eventos.'], [], None, None), [r['propuesta']]


def r_crear_actividad(user, ent) -> tuple:
    from .asistente import proponer
    q = ent['q']
    tipo = next((t for t, pat in [('open_house', r'open house'), ('examen', r'examen'), ('inscripciones', r'inscripcion'),
                                  ('curso', r'curso|propedeutico'), ('junta', r'junta|reunion'), ('feria', r'feria|expo')]
                 if re.search(pat, q)), 'otro')
    titulo = {'open_house': 'Open house', 'examen': 'Examen de admisión', 'inscripciones': 'Inscripciones', 'curso': 'Curso propedéutico',
              'junta': 'Junta del equipo', 'feria': 'Feria o expo', 'otro': 'Actividad'}[tipo]
    if ent['args'].get('plantel'):
        titulo += f" · {dict(A.Plantel.choices)[ent['args']['plantel']]}"
    if not ent['fecha']:
        return _salida([f'¿Qué día es «{titulo}»? Por ejemplo: «agrega el open house al calendario el 21 de noviembre a las 10».'], [], None, None), []
    r = proponer(user, 'crear_actividad', {'titulo': titulo, 'tipo': tipo, 'fecha': ent['fecha'].isoformat(), 'hora_inicio': ent['hora'] or ''})
    if r.get('error'):
        return _salida([r['error']], [], None, None), []
    return _salida([f"Te preparé **{titulo}** para el **{ent['fecha'].day} de {MESES[ent['fecha'].month - 1]}**"
                    + (f" a las {ent['hora']}" if ent['hora'] else '') + '. Revisa y pulsa **Confirmar**.'], [], None, None), [r['propuesta']]


# --------------------------------------------------------------------------- conversación
def r_saludo(user, ent, nombre) -> dict:
    if re.search(r'gracias|perfecto|listo', ent['q']):
        return _salida(['¡Con gusto! Aquí estoy cuando me necesites.'], ['¿Qué es lo más urgente hoy?'], None, None)
    from ..models import Perfil
    return _salida([f"¡Hola, {Perfil.de(user).nombre_corto}! Soy {nombre}. Pregúntame cifras, cómo hacer algo en el programa, o pídeme preparar una "
                    'visita o asignar aspirantes.'], ['¿Qué es lo más urgente hoy?', '¿Cómo vamos este mes contra el anterior, por plantel?'],
                   None, None)


def r_quien_eres(user, ent, nombre) -> dict:
    return _salida([f"Soy **{nombre}**, el aguilucho del programa. Funciono aquí mismo, sin internet y sin inteligencia artificial "
                    'externa: entiendo preguntas con reglas y saco las cifras de los datos del programa, nunca las invento.',
                    '', '**Puedo:**', '- Contar y comparar: aspirantes, inscritos, por llamar, menores esperando permiso, contactos.',
                    '- Cruzar y analizar: carreras por plantel, qué canal o prepa convierte mejor, dónde se quedan en el embudo.',
                    '- Revisar visitas: próximas y cuánto rindieron.',
                    '- En una ficha: preparar la llamada, un WhatsApp o las diferencias con su familia.',
                    '- Preparar una visita, una actividad del calendario o asignar aspirantes (tú confirmas).',
                    '- Explicar cómo se hace algo en el programa.'],
                   ['¿Qué es lo más urgente hoy?', '¿Qué carreras piden en cada plantel?', '¿Cómo uno a una familia con su alumno?'], None, None)


EJEMPLOS = ['¿Cómo vamos este mes contra el anterior, por plantel?', '¿Qué carreras piden en cada plantel?', '¿Qué canal convierte mejor?',
            '¿En qué etapa del embudo se nos quedan más?', '¿Qué es lo más urgente hoy?', '¿Qué visitas tenemos los próximos días?',
            '¿Qué visitas rindieron más registros por costo?', '¿Cuántos menores esperan permiso?', '¿Cómo vamos mes a mes?',
            '¿De qué prepas vienen los aspirantes?', '¿Cómo uno a una familia con su alumno?', '¿Qué significa Esperando permiso?']


def r_no_entendi(user, ent) -> dict:
    palabras = set(ent['q'].split())
    parecidas = sorted(EJEMPLOS, key=lambda e: -len(palabras & set(_n(e).split())))[:3]
    return _salida(['No entendí bien esa pregunta. Todavía aprendo: sé responder sobre cifras de aspirantes, visitas, el embudo, '
                    'qué hacer hoy y cómo se usa el programa.', 'Prueba con alguna de estas, o escríbela con otras palabras:'],
                   parecidas, None, None)


def _salida(lineas, siguientes, res, herramienta, visual='auto', calculos=None) -> dict:
    from .asistente import _visual
    if calculos is None and isinstance(res, dict) and res.get('como_se_calculo'):
        calculos = [{'que': res['como_se_calculo'], 'enlace': res.get('enlace_a_la_lista')}]
    return {'texto': '\n'.join(lineas).strip(), 'siguientes': [s for s in siguientes if s][:3],
            'visual': (_visual(herramienta, res) if herramienta and res else None) if visual == 'auto' else visual,
            'calculos': calculos or []}


def _entendi_txt(ent) -> str:
    nombres = {'cifras': 'conteo', 'cruce': 'cruce', 'conversion': 'conversión', 'embudo': 'embudo', 'visitas': 'visitas',
               'pendientes': 'pendientes de hoy', 'ayuda': 'ayuda del manual', 'asignar': 'asignar aspirantes',
               'crear_visita': 'crear visita', 'crear_actividad': 'agregar al calendario', 'ficha_llamada': 'preparar llamada',
               'ficha_mensaje': 'mensaje', 'ficha_diferencias': 'diferencias con la familia'}
    i = ent['intencion']
    if i not in nombres:
        return ''
    a = ent['args']
    partes = [nombres[i]]
    if i in ('cifras', 'cruce', 'conversion', 'embudo'):
        partes.append({'aspirantes': 'aspirantes', 'inscritos': 'inscritos', 'por_llamar': 'por llamar',
                       'esperando_permiso': 'esperando permiso', 'contactos': 'contactos'}[a['metrica']] if i == 'cifras' else '')
        if i == 'cifras' and a['metrica'] == 'por_llamar':
            pass
        else:
            partes.append(ent['periodo_txt'] + ('' if ent['periodo_explicito'] or ent['heredada'] else ' (no dijiste periodo)'))
        for k in ('plantel', 'carrera', 'preparatoria'):
            if a.get(k):
                partes.append(dict(A.Plantel.choices).get(a[k], a[k]) if k == 'plantel' else a[k])
        if a.get('grupo'):
            partes.append(etiqueta_segmento(a['grupo']))
        if a.get('agrupar_por'):
            partes.append(f"por {a['agrupar_por'].replace('_', ' ')}")
        if i == 'cruce':
            partes.append(f"{a['filas']} × {a['columnas']}")
    return ' · '.join(p for p in partes if p) + (' (sigue la pregunta anterior)' if ent['heredada'] else '')


def responder(user, mensaje: str, memoria: dict, contexto: dict) -> dict:
    from .asistente import nombre_mascota
    ent = entender(mensaje, memoria, contexto)
    i = ent['intencion']
    propuestas = []
    reportes = user.has_perm('prospectos.ver_reportes')
    if i in ('cifras', 'cruce', 'conversion', 'embudo') and not reportes:
        out = _salida(['Tu rol no permite ver cifras del programa. Pide a coordinación el reporte que necesites.'], [], None, None)
    elif i == 'saludo':
        out = r_saludo(user, ent, nombre_mascota())
    elif i == 'quien_eres':
        out = r_quien_eres(user, ent, nombre_mascota())
    elif i == 'cifras':
        out = r_cifras(user, ent)
    elif i == 'cruce':
        out = r_cruce(user, ent)
    elif i == 'conversion':
        out = r_conversion(user, ent)
    elif i == 'embudo':
        out = r_embudo(user, ent)
    elif i == 'visitas':
        out = r_visitas(user, ent) if user.has_perm('prospectos.view_evento') else _salida(['Tu rol no permite ver visitas.'], [], None, None)
    elif i == 'pendientes':
        out = r_pendientes(user, ent)
    elif i == 'ayuda':
        out = r_ayuda(user, ent)
    elif i == 'ficha_llamada':
        out = r_ficha_llamada(user, ent, contexto)
    elif i == 'ficha_mensaje':
        out = r_ficha_mensaje(user, ent, contexto)
    elif i == 'ficha_diferencias':
        out = r_ficha_diferencias(user, ent, contexto)
    elif i == 'asignar':
        out, propuestas = r_asignar(user, ent)
    elif i == 'crear_visita':
        out, propuestas = r_crear_visita(user, ent)
    elif i == 'crear_actividad':
        out, propuestas = r_crear_actividad(user, ent)
    else:
        # ¿Escribió el nombre de un aspirante? Se puede buscar en la lista (todo queda en esta computadora).
        nombre = _nombre_de_aspirante(ent['q'])
        if nombre and user.has_perm('prospectos.view_prospecto'):
            url = reverse('admin:prospectos_prospecto_changelist') + f'?q={nombre.replace(" ", "+")}'
            out = _salida([f"Parece que buscas a alguien: {_enlace(f'buscar «{nombre}» en Prospectos', url)}. "
                           'Al abrir su ficha puedo prepararte la llamada.'], [], None, None)
        else:
            out = r_no_entendi(user, ent)
    nueva_memoria = memoria
    if i in ('cifras', 'cruce', 'conversion', 'embudo', 'visitas'):
        nueva_memoria = {'intencion': i, 'args': {k: v for k, v in ent['args'].items() if k not in ('desde', 'hasta')},
                         'periodo': [ent['args']['desde'], ent['args']['hasta'], ent['periodo_txt']]}
    return {**out, 'propuestas': propuestas, 'intencion': i or 'no_entendi', 'entendi': _entendi_txt(ent), 'memoria': nueva_memoria,
            'herramientas': [i] if i else []}


def _nombre_de_aspirante(q: str):
    palabras = [p for p in q.split() if len(p) >= 3]
    for a, b in zip(palabras, palabras[1:], strict=False):
        va, vb = texto._variantes(a), texto._variantes(b)
        if Prospecto.objects.filter(nombre_normalizado__contains=va).filter(nombre_normalizado__contains=vb).exists():
            return f'{a} {b}'
    return None
