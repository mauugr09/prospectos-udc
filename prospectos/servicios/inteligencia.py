"""
Enlace alumno-tutor, duplicados, scoring, segmentos, brechas y fusión.

Orden del enlace de una respuesta:
  1. token_familia (tarjeta con dos QR) → enlace seguro.
  2. Contacto (índice ciego) + nombre compatible → reenvío / historial.
  3. Nombre difuso en la misma preparatoria: ≥ umbral automático y sin empate → enlace;
     ≥ umbral de revisión → prospecto nuevo + posible coincidencia para revisión manual.
  4. Si nada aplica → prospecto nuevo.
"""

import re

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .. import catalogos
from ..models import (PRIORIDAD_SEGMENTO, Carrera, Configuracion, Cuestionario, EstadoRespuesta, PosibleCoincidencia,
                      Preparatoria, Prospecto, Respuesta, Segmento, Seguimiento, TipoSeguimiento)
from . import auditoria, texto
from .cifrado import indice_correo, indice_telefono

P = settings.PROSPECTOS


# --------------------------------------------------------------------------- enlace
def _raiz(p: Prospecto) -> Prospecto:
    vistos = set()
    while p.fusionado_en_id and p.pk not in vistos:
        vistos.add(p.pk)
        p = Prospecto.objects.get(pk=p.fusionado_en_id)
    return p


def _asignar(r: Respuesta, p: Prospecto) -> Prospecto:
    r.prospecto = p
    r.save(update_fields=['prospecto'])
    return Prospecto.objects.get(pk=p.pk)


def _por_contacto(tipo: str, datos, nombre: str):
    correo_bi, tel_bi = indice_correo(datos.correo()), indice_telefono(datos.telefono())
    if not correo_bi and not tel_bi:
        return None
    col_c, col_t = ('correo_bi', 'telefono_bi') if tipo == Cuestionario.ALUMNO else ('tutor_correo_bi', 'tutor_telefono_bi')
    filtro = Q()
    if correo_bi:
        filtro |= Q(**{col_c: correo_bi})
    if tel_bi:
        filtro |= Q(**{col_t: tel_bi})
    mejores = []
    for p in Prospecto.objects.filter(fusionado_en__isnull=True, anonimizado_en__isnull=True).filter(filtro):
        s = texto.similitud_nombres(nombre, p.nombre_aspirante)
        # El correo del ALUMNO identifica a una persona; el contacto del TUTOR no (hermanos comparten tutor).
        correo_alumno = tipo == Cuestionario.ALUMNO and correo_bi and p.correo_bi == correo_bi
        if correo_alumno or s >= P['UMBRAL_REVISION']:
            mejores.append((s, p))
    return max(mejores, key=lambda x: x[0])[1] if mejores else None


def _candidatos(nombre: str, prepa_id, token):
    if not nombre.strip():
        return []
    umbral = P['UMBRAL_REVISION'] if prepa_id else P['UMBRAL_SIN_PREPARATORIA']
    qs = Prospecto.objects.filter(fusionado_en__isnull=True, anonimizado_en__isnull=True)
    if prepa_id:
        qs = qs.filter(preparatoria_id=prepa_id)
    res = []
    for p in qs.only('id', 'nombre_aspirante', 'token_familia', 'preparatoria_id'):
        if token and p.token_familia and p.token_familia != token:
            continue  # dos tokens distintos = dos familias distintas
        s = texto.similitud_nombres(nombre, p.nombre_aspirante)
        if s >= umbral:
            res.append({'prospecto': p, 'similitud': s,
                        'motivo': 'Nombre similar en la misma preparatoria' if prepa_id else 'Nombre similar (sin preparatoria conocida)'})
    return sorted(res, key=lambda c: c['similitud'], reverse=True)


def _alumno_del_tutor(datos, nombre: str, prepa_id):
    """
    La encuesta de padres no trae código de familia ni preparatoria. Se enlaza con el alumno:
      1. por el correo o teléfono DEL ASPIRANTE, si la encuesta lo pregunta (pregunta recomendada); o
      2. por el nombre completo IDÉNTICO (sin acentos ni orden), con al menos nombre y dos apellidos, cuando hay
         UN solo alumno así sin familia enlazada y el plantel no contradice. Si hay dos, va a revisión.
    """
    vivos = Prospecto.objects.filter(fusionado_en__isnull=True, anonimizado_en__isnull=True)
    contacto = datos.uno('aspirante_contacto')
    if contacto:
        filtro = Q()
        if indice_correo(contacto) and '@' in contacto:
            filtro |= Q(correo_bi=indice_correo(contacto))
        if indice_telefono(contacto):
            filtro |= Q(telefono_bi=indice_telefono(contacto))
        if filtro:
            p = vivos.filter(filtro).first()
            if p:
                return _raiz(p)
    clave = texto.clave_nombre(nombre)
    if prepa_id or len(clave.split()) < 3:
        return None
    candidatos = vivos.filter(nombre_normalizado=clave, tiene_alumno=True, tiene_tutor=False)
    plantel = texto.clave_catalogo(datos.uno('plantel'), catalogos.PLANTELES)
    if plantel:
        candidatos = candidatos.filter(Q(plantel='') | Q(plantel=plantel))
    candidatos = list(candidatos[:2])
    return candidatos[0] if len(candidatos) == 1 else None


def _familia_del_alumno(datos, nombre: str):
    """Caso inverso: la familia contestó primero. Mismo criterio: nombre idéntico, único y plantel compatible."""
    clave = texto.clave_nombre(nombre)
    if len(clave.split()) < 3:
        return None
    candidatos = Prospecto.objects.filter(fusionado_en__isnull=True, anonimizado_en__isnull=True, nombre_normalizado=clave,
                                          tiene_alumno=False, tiene_tutor=True)
    plantel = texto.clave_catalogo(datos.uno('plantel'), catalogos.PLANTELES)
    if plantel:
        candidatos = candidatos.filter(Q(plantel='') | Q(plantel=plantel))
    candidatos = list(candidatos[:2])
    return candidatos[0] if len(candidatos) == 1 else None


def _candidatos_cruzados(cuestionario, nombre: str, datos, umbral: float = 0.74, maximo: int = 3) -> list[dict]:
    if not nombre.strip():
        return []
    qs = Prospecto.objects.filter(fusionado_en__isnull=True, anonimizado_en__isnull=True)
    qs = qs.filter(tiene_alumno=True, tiene_tutor=False) if cuestionario == Cuestionario.TUTOR else qs.filter(tiene_alumno=False, tiene_tutor=True)
    plantel = texto.clave_catalogo(datos.uno('plantel'), catalogos.PLANTELES)
    if plantel:
        qs = qs.filter(Q(plantel='') | Q(plantel=plantel))
    res = []
    for p in qs.only('id', 'nombre_aspirante'):
        sim = texto.similitud_nombres(nombre, p.nombre_aspirante)
        if sim >= umbral:
            res.append({'prospecto': p, 'similitud': sim, 'motivo': 'Nombre parecido (encuesta de padres ↔ alumno, mismo plantel)'})
    return sorted(res, key=lambda c: c['similitud'], reverse=True)[:maximo]


def enlazar(r: Respuesta, datos, evento) -> Prospecto:
    if r.prospecto_id:
        return _asignar(r, _raiz(Prospecto.objects.get(pk=r.prospecto_id)))

    prepa_id = evento.preparatoria_id if evento else None
    if not prepa_id and r.cuestionario == Cuestionario.ALUMNO:
        prepa = Preparatoria.resolver(datos.uno('preparatoria'))
        prepa_id = prepa.pk if prepa else None
    nombre = datos.nombre_aspirante() or ''
    token = datos.token()

    if token:
        p = Prospecto.objects.filter(token_familia=token).first()
        if p:
            return _asignar(r, _raiz(p))

    p = _por_contacto(r.cuestionario, datos, nombre)
    if p:
        return _asignar(r, p)

    if r.cuestionario == Cuestionario.TUTOR:
        p = _alumno_del_tutor(datos, nombre, prepa_id)
        if p:
            return _asignar(r, p)
    else:
        p = _familia_del_alumno(datos, nombre)
        if p:
            return _asignar(r, p)

    cands = _candidatos(nombre, prepa_id, token)
    auto = P['UMBRAL_AUTOMATICO']
    empate = len(cands) > 1 and cands[1]['similitud'] >= auto
    if prepa_id and cands and cands[0]['similitud'] >= auto and not empate:
        return _asignar(r, cands[0]['prospecto'])
    # La pareja alumno ↔ familia (con nombres distintos) la busca familias.unir_o_proponer después de recalcular,
    # cuando la ficha ya tiene teléfonos, plantel y fecha para comparar.

    nuevo = Prospecto.objects.create(
        nombre_aspirante=nombre or 'Sin nombre', preparatoria_id=prepa_id, evento=evento, promotor=r.promotor,
        token_familia=token, ultima_actividad_en=r.enviada_en, creado_en=r.enviada_en,
    )
    for c in cands:
        PosibleCoincidencia.objects.get_or_create(prospecto=nuevo, candidato=c['prospecto'],
                                                  defaults={'similitud': c['similitud'], 'motivo': c['motivo']})
    return _asignar(r, nuevo)


# --------------------------------------------------------------------------- perfil y reglas
class Perfil:
    """Respuestas vigentes normalizadas: {codigo: [valores]} para alumno y tutor."""

    def __init__(self, alumno: Respuesta | None, tutor: Respuesta | None):
        self.alumno = self._extraer(alumno)
        self.tutor = self._extraer(tutor)

    @staticmethod
    def _extraer(r):
        d = {}
        if r:
            for i in r.items.all():
                v = i.valor_normalizado or i.valor
                if v:
                    d.setdefault(i.codigo, []).append(v)
        return d

    def a(self, c):
        return (self.alumno.get(c) or [None])[0]

    def t(self, c):
        return (self.tutor.get(c) or [None])[0]

    def x(self, c):
        """Lo del alumno y, si no contestó, lo de la familia."""
        return self.a(c) or self.t(c)


def pesos() -> dict:
    """Pesos guardados en el panel; solo las reglas que existen (se ignoran las retiradas, p. ej. semestre)."""
    guardados = Configuracion.obtener('score.pesos', {}) or {}
    return {k: guardados.get(k, v) for k, v in P['PESOS'].items()}


def umbral(clave: str):
    return Configuracion.obtener(f'segmentos.{clave}', P['SEGMENTOS'][clave])


def _ids_carrera(valores) -> list[int]:
    return [int(v) for v in valores or [] if str(v).isdigit()]


REGLAS_TUTOR = {'familia_pidio_informacion', 'ingresa_proximo_ciclo'}  # solo cuentan si la familia contestó


def quiere_informacion(perfil: Perfil) -> bool | None:
    """True si alguien (alumno o familia) pidió información; False si quien contestó dijo que no; None si nadie dijo nada."""
    a, t = perfil.a('recibir_informacion'), perfil.t('recibir_informacion')
    if a in ('whatsapp', 'correo') or t == 'si':
        return True
    if a == 'no' or t == 'no':
        return False
    return None


def calcular_score(p: Prospecto, perfil: Perfil) -> tuple[int, dict]:
    """
    Prioridad 0–100: puntos de las reglas cumplidas ÷ puntos posibles. Las reglas de la familia solo cuentan si la
    familia contestó (no se castiga a quien solo tiene la respuesta del alumno). Ordena; no predice inscripción.
    """
    w = pesos()
    x = perfil.x
    conocer = set(perfil.alumno.get('quiere_conocer', [])) | set(perfil.tutor.get('quiere_conocer', []))
    reglas = {
        'pidio_informacion': quiere_informacion(perfil) is True,
        'eligio_carrera': bool(_ids_carrera(perfil.alumno.get('carrera') or perfil.tutor.get('carrera'))),
        'pregunta_requisitos': 'requisitos' in conocer,
        'eligio_modalidad': x('modalidad') in ('semanal', 'sabatino', 'dominical'),
        'pregunta_costos': bool(conocer & {'costos', 'becas'}),
        'contacto_completo': bool(p.correo and p.telefono) or bool(p.tutor_correo and p.tutor_telefono),
        'familia_pidio_informacion': perfil.t('recibir_informacion') == 'si',
        'ingresa_proximo_ciclo': perfil.t('cuando_ingresa') == 'proximo_ciclo',
    }
    aplican = {k: v for k, v in w.items() if perfil.tutor or k not in REGLAS_TUTOR}
    total = sum(float(v) for v in aplican.values()) or 1.0
    detalle, suma = {}, 0.0
    for regla, peso in aplican.items():
        peso = float(peso)
        if reglas.get(regla) and peso > 0:
            detalle[regla] = round(peso / total * 100)
            suma += peso
    return min(100, round(suma / total * 100)), detalle


def segmentar(perfil: Perfil, score: int) -> list[str]:
    s = []
    quiere = quiere_informacion(perfil)
    if quiere is False:
        s.append(Segmento.NO_CONTACTAR)
    elif quiere and score >= int(umbral('listo_para_convertir_score')):
        s.append(Segmento.LISTO)
    factores = set(perfil.alumno.get('factor_eleccion', [])) | set(perfil.tutor.get('factor_eleccion', []))
    conocer = set(perfil.alumno.get('quiere_conocer', [])) | set(perfil.tutor.get('quiere_conocer', []))
    if (factores & {'colegiaturas', 'becas'} or conocer & {'becas', 'costos'}
            or perfil.t('apoyo_economico') in ('becas', 'descuentos', 'facilidades', 'financiamiento')
            or perfil.t('preocupacion') == 'costos'):
        s.append(Segmento.BECA)
    if ('horarios' in factores or perfil.x('modalidad') in ('sabatino', 'dominical')
            or perfil.t('modalidad') in ('sabatino', 'dominical') or perfil.t('preocupacion') == 'horarios'):
        s.append(Segmento.HORARIO)
    carreras = perfil.alumno.get('carrera') or perfil.tutor.get('carrera') or []
    if catalogos.INDECISO in carreras or not carreras or len(_ids_carrera(carreras)) >= int(umbral('indeciso_desde_carreras')):
        s.append(Segmento.INDECISO)
    if perfil.t('cuando_ingresa') in ('un_ano', 'dos_anos'):
        s.append(Segmento.LARGO_PLAZO)
    return sorted({str(x) for x in s}, key=PRIORIDAD_SEGMENTO.index)


def brechas(p: Prospecto, perfil: Perfil) -> list[dict]:
    """Diferencias entre lo que contestó el alumno y lo que contestó su familia (solo si contestaron los dos)."""
    b = []
    if not perfil.tutor or not perfil.alumno:
        return b
    ca, ct = set(_ids_carrera(perfil.alumno.get('carrera'))), set(_ids_carrera(perfil.tutor.get('carrera')))
    if ca and ct and not ca & ct:
        nombres = dict(Carrera.objects.filter(pk__in=ca | ct).values_list('pk', 'nombre'))
        b.append({'tipo': 'carrera', 'alumno': ', '.join(nombres[i] for i in ca if i in nombres),
                  'tutor': ', '.join(nombres[i] for i in ct if i in nombres),
                  'mensaje': 'El alumno y su familia eligieron carreras distintas.'})
    ma, mt = perfil.a('modalidad'), perfil.t('modalidad')
    if ma and mt and catalogos.INDECISO not in (ma, mt) and ma != mt:
        b.append({'tipo': 'modalidad', 'alumno': catalogos.MODALIDADES.get(ma, ma),
                  'tutor': catalogos.MODALIDADES_TUTOR.get(mt, mt), 'mensaje': 'Prefieren modalidades distintas.'})
    pa, pt = perfil.a('plantel'), perfil.t('plantel')
    if pa and pt and pa != pt:
        b.append({'tipo': 'plantel', 'alumno': catalogos.PLANTELES_CORTO.get(pa, pa),
                  'tutor': catalogos.PLANTELES_CORTO.get(pt, pt), 'mensaje': 'Prefieren planteles distintos.'})
    return b


def aviso_en_formulario() -> dict | None:
    """Si un administrador confirmó que el Form muestra el aviso de privacidad (consentimiento tácito de mayores)."""
    v = Configuracion.obtener('permisos.aviso_en_form')
    return v if v and v.get('activo') else None


# --------------------------------------------------------------------------- recalcular
def _primero(r: Respuesta, codigo: str):
    v = ((r.raw_json or {}).get('por_codigo', {}).get(codigo) or [None])[0]
    return texto.limpiar(v) if v and v.strip() else None


def _entero(v):
    return int(v) if v and str(v).isdigit() else None


def recalcular(p: Prospecto) -> Prospecto:
    """Reconstruye datos, consentimiento, estados, score, segmentos y brechas. Determinista."""
    resp = list(p.respuestas.exclude(estado=EstadoRespuesta.DESCARTADA).prefetch_related('items').order_by('enviada_en', 'id'))
    alumno = next((r for r in reversed(resp) if r.cuestionario == Cuestionario.ALUMNO), None)
    tutor = next((r for r in reversed(resp) if r.cuestionario == Cuestionario.TUTOR), None)

    p.tiene_alumno, p.tiene_tutor = alumno is not None, tutor is not None
    carreras = []
    if alumno:
        p.nombre_aspirante = _primero(alumno, 'nombre_completo') or p.nombre_aspirante
        p.correo = _primero(alumno, 'correo') or p.correo
        p.telefono = _primero(alumno, 'telefono') or p.telefono
        p.tutor_nombre = _primero(alumno, 'tutor_nombre') or p.tutor_nombre
        p.tutor_telefono = _primero(alumno, 'tutor_telefono') or p.tutor_telefono
        edad = _entero(alumno.valor('edad'))
        p.edad = edad if edad is not None and 10 <= edad <= 99 else p.edad
        carreras = _ids_carrera(alumno.valores('carrera'))
        p.carrera_id = carreras[0] if carreras else None
        p.modalidad = alumno.valor('modalidad') or p.modalidad
        p.plantel = alumno.valor('plantel') or p.plantel
        p.canal_informacion = alumno.valor('recibir_informacion') or p.canal_informacion
        p.preparatoria_id = p.preparatoria_id or _entero(alumno.valor('preparatoria'))
    if tutor:
        p.tutor_nombre = _primero(tutor, 'tutor_nombre') or p.tutor_nombre
        p.tutor_correo = _primero(tutor, 'tutor_correo') or p.tutor_correo
        p.tutor_telefono = _primero(tutor, 'tutor_telefono') or p.tutor_telefono
        ct = _ids_carrera(tutor.valores('carrera'))
        p.carrera_tutor_id = ct[0] if ct else p.carrera_tutor_id
        p.modalidad_tutor = tutor.valor('modalidad') or p.modalidad_tutor
        p.plantel = p.plantel or tutor.valor('plantel') or ''
        if p.canal_informacion not in ('whatsapp', 'correo'):  # el canal concreto del alumno manda
            p.canal_informacion = tutor.valor('recibir_informacion') or p.canal_informacion or ''
        if not alumno and _primero(tutor, 'nombre_aspirante'):
            p.nombre_aspirante = _primero(tutor, 'nombre_aspirante')

    # CURP (si el Form la pide): se valida y de ella sale la fecha de nacimiento → edad exacta (sin consultar a nadie).
    from . import curp as _curp
    for fuente, codigo in ((alumno, 'curp'), (tutor, 'curp_aspirante')):
        datos_curp = _curp.analizar(_primero(fuente, codigo)) if fuente else None
        if datos_curp:
            p.curp, p.fecha_nacimiento = datos_curp['curp'], datos_curp['fecha_nacimiento']
            break
    if p.fecha_nacimiento:
        p.edad = _curp.edad(p.fecha_nacimiento, timezone.localdate())

    con_evento = next((r for r in resp if r.evento_id), None)
    p.evento_id = p.evento_id or (con_evento.evento_id if con_evento else None)
    p.promotor_id = p.promotor_id or next((r.promotor_id for r in resp if r.promotor_id), None)
    if p.evento_id and not p.preparatoria_id:
        p.preparatoria_id = p.evento.preparatoria_id
    if not p.token_familia:
        tok = next((r.token_familia for r in resp if r.token_familia), None)
        if tok and not Prospecto.objects.filter(token_familia=tok).exclude(pk=p.pk).exists():
            p.token_familia = tok
    fechas = [f for f in [p.ultimo_contacto_en, p.ultima_actividad_en, *(r.enviada_en for r in resp)] if f]
    p.ultima_actividad_en = max(fechas) if fechas else timezone.now()

    # Permiso (LFPDPPP, datos de menores):
    #   tutor acepta en su cuestionario, o un asesor registró el permiso del tutor → válido;
    #   aspirante MAYOR acepta el aviso (pregunta explícita, o aviso mostrado en el Form y confirmado
    #   por un administrador = consentimiento tácito) → válido;
    #   alguien dice «No» al aviso → sin permiso; menor (o edad desconocida) sin tutor → esperando permiso.
    acepta = alumno.valor('consentimiento_aviso_privacidad') if alumno else None
    mayor = p.edad is not None and p.edad >= P['EDAD_MAYORIA']
    adulto_acepta = alumno and mayor and (acepta == 'si' or (acepta is None and aviso_en_formulario()))
    era = Prospecto.objects.filter(pk=p.pk).values_list('consentimiento', flat=True).first() or False
    p.consentimiento_negado = False
    if tutor and tutor.valor('consentimiento_aviso_privacidad') == 'si':
        p.consentimiento, p.origen_consentimiento = True, 'tutor'
        p.consentimiento_en = p.consentimiento_en or tutor.consentimiento_en or tutor.enviada_en
    elif p.permiso_registrado_por_id and acepta != 'no':
        p.consentimiento, p.origen_consentimiento = True, 'asesor'
    elif adulto_acepta:
        p.consentimiento, p.origen_consentimiento = True, 'alumno' if acepta == 'si' else 'aviso'
        p.consentimiento_en = p.consentimiento_en or alumno.consentimiento_en or alumno.enviada_en
    else:
        p.consentimiento, p.origen_consentimiento, p.consentimiento_en = False, '', None
        p.consentimiento_negado = bool(tutor and tutor.valor('consentimiento_aviso_privacidad') == 'no')

    perfil = Perfil(alumno, tutor)
    p.score, p.score_detalle = calcular_score(p, perfil)
    p.segmentos = segmentar(perfil, p.score)
    p.no_contactar = Segmento.NO_CONTACTAR in p.segmentos
    p.segmento_principal = p.segmentos[0] if p.segmentos else ''
    p.brechas = brechas(p, perfil)
    p.tiene_brecha = bool(p.brechas)
    p.save()
    if alumno:
        p.carreras.set(carreras)

    for r in resp:
        if p.consentimiento:
            estado = EstadoRespuesta.VALIDA
        elif p.consentimiento_negado or r.cuestionario == Cuestionario.TUTOR or r.valor('consentimiento_aviso_privacidad') == 'no':
            estado = EstadoRespuesta.SIN_CONSENTIMIENTO
        else:
            estado = EstadoRespuesta.CUARENTENA
        if r.estado != estado:
            Respuesta.objects.filter(pk=r.pk).update(estado=estado)

    if p.consentimiento and not era and not p.bienvenida_enviada_en and not p.no_contactar and (p.correo or p.tutor_correo):
        from .seguimiento import enviar_bienvenida
        transaction.on_commit(lambda: enviar_bienvenida(p.pk))
    return p


def recalcular_todos() -> int:
    n = 0
    for p in Prospecto.objects.filter(fusionado_en__isnull=True, anonimizado_en__isnull=True).iterator(chunk_size=200):
        recalcular(p)
        n += 1
    return n


MEDIOS_PERMISO = {'llamada': 'Por llamada', 'whatsapp': 'Por WhatsApp', 'presencial': 'En persona', 'escrito': 'Por escrito (firmado)'}


def registrar_permiso_tutor(p: Prospecto, usuario, tutor_nombre: str, medio: str, nota: str = '') -> Prospecto:
    """
    Un asesor confirma que la mamá, papá o tutor de un menor aceptó el aviso de privacidad (sin cuestionario
    del tutor). Queda quién, cuándo y cómo, en el historial y en la bitácora.
    """
    tutor_nombre = texto.limpiar(tutor_nombre or '')[:255]
    if not tutor_nombre or medio not in MEDIOS_PERMISO:
        raise ValueError('Falta el nombre del tutor o cómo dio el permiso.')
    with transaction.atomic():
        p.permiso_registrado_por = usuario
        p.permiso_nota = f'{MEDIOS_PERMISO[medio]} · {tutor_nombre}' + (f' · {texto.limpiar(nota)[:120]}' if nota else '')
        p.tutor_nombre = p.tutor_nombre or tutor_nombre
        p.consentimiento_en = timezone.now()
        p.save()
        Seguimiento.objects.create(prospecto=p, usuario=usuario, tipo=TipoSeguimiento.SISTEMA,
                                   notas=f'Permiso del tutor registrado: {p.permiso_nota}.')
        auditoria.registrar('registrar_permiso_tutor', p, {'medio': medio}, usuario)
        return recalcular(p)


# --------------------------------------------------------------------------- fusión
class NoFusionable(Exception):
    pass


def fusionar(queda: Prospecto, sale: Prospecto, usuario=None) -> Prospecto:
    if queda.pk == sale.pk:
        raise NoFusionable('No se puede fusionar un prospecto consigo mismo.')
    if queda.token_familia and sale.token_familia and queda.token_familia != sale.token_familia:
        raise NoFusionable('Tienen códigos de familia distintos: son familias diferentes.')
    with transaction.atomic():
        sale.respuestas.update(prospecto=queda)
        Seguimiento.objects.filter(prospecto=sale).update(prospecto=queda)
        queda.etiquetas.add(*sale.etiquetas.all())
        for campo in ('token_familia', 'preparatoria_id', 'evento_id', 'promotor_id', 'asesor_id'):
            if not getattr(queda, campo) and getattr(sale, campo):
                valor = getattr(sale, campo)
                if campo == 'token_familia':
                    Prospecto.objects.filter(pk=sale.pk).update(token_familia=None)
                setattr(queda, campo, valor)
        if sale.posicion_embudo > queda.posicion_embudo:
            queda.estatus = sale.estatus
        queda.save()
        Prospecto.objects.filter(pk=sale.pk).update(fusionado_en=queda, token_familia=None)
        PosibleCoincidencia.objects.filter(
            Q(prospecto__in=[queda, sale], candidato__in=[queda, sale])
        ).update(estado='fusionada', revisado_por=usuario, revisado_en=timezone.now())
        PosibleCoincidencia.objects.filter(prospecto=sale, estado='pendiente').update(estado='rechazada', revisado_en=timezone.now())
        Seguimiento.objects.create(prospecto=queda, usuario=usuario, tipo=TipoSeguimiento.SISTEMA,
                                   notas=f'Fusionado con el prospecto #{sale.pk}.')
        auditoria.registrar('fusionar', queda, {'absorbido_id': sale.pk}, usuario)
        return recalcular(Prospecto.objects.get(pk=queda.pk))


def rechazar(c: PosibleCoincidencia, usuario=None) -> None:
    c.estado, c.revisado_por, c.revisado_en = 'rechazada', usuario, timezone.now()
    c.save()
    auditoria.registrar('rechazar_coincidencia', c.prospecto, {'candidato_id': c.candidato_id}, usuario)
