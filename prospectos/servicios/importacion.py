"""Importa respuestas de los Forms: idempotente, incremental y tolerante a fallos."""

import hashlib
import logging
import re
import threading
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .. import catalogos
from ..models import (Carrera, Cuestionario, EstadoRespuesta, Evento, Formulario, Importacion, Pregunta,
                      Preparatoria, Respuesta, RespuestaItem)
from . import texto
from .fuentes import fuente_por_defecto

log = logging.getLogger('prospectos.importador')
NUEVA, ACTUALIZADA, OMITIDA = 'nueva', 'actualizada', 'omitida'
_candados: dict[int, threading.Lock] = {}


class DatosRespuesta:
    """Valores mapeados a códigos. Los de contacto viven solo en memoria y cifrados en el prospecto."""

    def __init__(self, cuestionario: str, valores: dict[str, list[str]]):
        self.cuestionario = cuestionario
        self.valores = valores

    def uno(self, codigo: str) -> str | None:
        v = (self.valores.get(codigo) or [None])[0]
        return v.strip() if v and v.strip() else None

    def nombre_aspirante(self):
        return self.uno('nombre_completo' if self.cuestionario == Cuestionario.ALUMNO else 'nombre_aspirante')

    def token(self):
        t = self.uno('token_familia')
        return re.sub(r'\s+', '', t).upper() if t else None

    def correo(self):
        return self.uno('correo' if self.cuestionario == Cuestionario.ALUMNO else 'tutor_correo')

    def telefono(self):
        return self.uno('telefono' if self.cuestionario == Cuestionario.ALUMNO else 'tutor_telefono')

    def consiente(self) -> bool:
        return texto.si_no(self.uno('consentimiento_aviso_privacidad')) == 'si'


def hash_respuesta(formulario_id: int, response_id: str) -> str:
    return hashlib.sha256(f'{formulario_id}|{response_id}'.encode()).hexdigest()


def mapear(formulario: Formulario, cruda) -> DatosRespuesta:
    mapeo = formulario.mapeo_campos or {}
    valores: dict[str, list[str]] = {}
    for qid, lista in cruda.respuestas.items():
        codigo = mapeo.get(qid)
        if codigo:
            valores.setdefault(codigo, []).extend(lista)
    return DatosRespuesta(formulario.tipo, valores)


SIN_PREPA = {'ninguna', 'ninguno', 'no estudio', 'ya termine', 'ya sali', 'no', 'na', 'n a', 'x', 'otra', 'otro'}


def normalizar(pregunta: Pregunta, valor: str) -> str | None:
    op = pregunta.opciones
    if pregunta.tipo == 'consentimiento':
        # «Sí/No», o la casilla única «He leído y acepto el aviso…» de la encuesta de padres.
        return texto.si_no(valor) or texto.clave_opcion(valor, pregunta.textos_opciones())
    if pregunta.tipo == 'numero':
        n = texto.entero(valor, 0, 120)
        return str(n) if n is not None else None
    if op == 'carreras':
        if texto.normalizar(valor) in catalogos.TEXTOS_INDECISO:
            return catalogos.INDECISO
        c = Carrera.resolver(valor)
        return str(c.pk) if c else None  # «Otro»: se conserva lo que escribió, sin carrera del catálogo
    if op == 'preparatorias':
        n = texto.normalizar(valor)
        if len(n) < 3 or n in SIN_PREPA:
            return None
        p = Preparatoria.resolver(valor, crear=True)  # texto libre: si no existe, se da de alta «por revisar»
        return str(p.pk) if p else None
    if pregunta.tipo == 'si_no' or op == 'si_no' and not pregunta.lista_opciones():
        return texto.si_no(valor)
    opciones = pregunta.textos_opciones()
    return texto.clave_opcion(valor, opciones) if opciones else None


def procesar(formulario: Formulario, cruda) -> str:
    from .inteligencia import enlazar, recalcular

    h = hash_respuesta(formulario.pk, cruda.response_id)
    with transaction.atomic():
        existente = Respuesta.objects.filter(hash_respuesta=h).first()
        # Ya procesada y sin edición posterior, o ya purgada: no hacer nada (idempotencia).
        if existente and (existente.enviada_en >= cruda.enviada_en or existente.estado == EstadoRespuesta.DESCARTADA):
            return OMITIDA

        datos = mapear(formulario, cruda)
        from .eventos import atribuir
        evento = atribuir(formulario.tipo, datos, cruda.enviada_en)  # código del QR, o prepa + fecha del evento
        from django.contrib.auth import get_user_model
        promotor = None
        if datos.uno('promotor'):
            promotor = get_user_model().objects.filter(perfil__codigo_promotor=datos.uno('promotor').upper()).first()
        promotor = promotor or (evento.promotor if evento else None)

        r = existente or Respuesta(formulario=formulario, cuestionario=formulario.tipo,
                                   google_response_id=cruda.response_id, hash_respuesta=h)
        r.evento = evento
        r.promotor = promotor
        r.token_familia = datos.token()
        r.nombre_aspirante = datos.nombre_aspirante() or ''
        r.consentimiento_aviso_privacidad = datos.consiente()
        r.consentimiento_en = cruda.enviada_en if datos.consiente() else None
        r.enviada_en = cruda.enviada_en
        r.raw_json = {'respuesta': cruda.original, 'por_codigo': datos.valores}
        if existente:
            r.version = existente.version + 1
        r.save()

        guardar_items(r, datos)
        prospecto = recalcular(enlazar(r, datos, evento))
        if prospecto.tiene_alumno != prospecto.tiene_tutor:  # le falta una mitad: ¿ya contestó su familia / su hijo?
            from .familias import unir_o_proponer
            unir_o_proponer(prospecto)
        return ACTUALIZADA if existente else NUEVA


def guardar_items(r: Respuesta, datos: DatosRespuesta) -> None:
    r.items.all().delete()
    if hasattr(r, '_cache_items'):
        del r._cache_items
    preguntas = {p.codigo: p for p in Pregunta.objects.filter(cuestionario=r.cuestionario).prefetch_related('opciones_lista')}
    filas = []
    for codigo, lista in datos.valores.items():
        p = preguntas.get(codigo)
        if p and p.sensible:
            continue  # datos de contacto: nunca en claro en respuesta_items
        for v in lista:
            filas.append(RespuestaItem(respuesta=r, pregunta=p, codigo=codigo, valor=v[:5000],
                                       valor_normalizado=normalizar(p, v) if p else None))
    RespuestaItem.objects.bulk_create(filas)


def reprocesar(formulario: Formulario) -> int:
    """
    Vuelve a leer las respuestas YA guardadas con el mapeo actual (sin pedir nada a Google).
    Sirve cuando cambian las preguntas del Form o el catálogo: lo importado antes se reacomoda.
    """
    from .fuentes import RespuestaCruda
    from .inteligencia import recalcular
    from ..models import Prospecto
    n, tocados = 0, set()
    for r in formulario.respuestas.exclude(estado=EstadoRespuesta.DESCARTADA).iterator():
        original = (r.raw_json or {}).get('respuesta')
        if not original or not original.get('responseId'):
            continue
        with transaction.atomic():
            datos = mapear(formulario, RespuestaCruda.desde_api(original))
            datos_previos = (r.raw_json or {}).get('por_codigo') or {}
            r.raw_json = {'respuesta': original, 'por_codigo': datos.valores}
            r.nombre_aspirante = datos.nombre_aspirante() or r.nombre_aspirante
            r.consentimiento_aviso_privacidad = datos.consiente()
            r.save()
            guardar_items(r, datos)
            if datos.valores != datos_previos:
                n += 1
            if r.prospecto_id:
                tocados.add(r.prospecto_id)
    for pid in tocados:
        recalcular(Prospecto.objects.get(pk=pid))
    return n


def importar(formulario: Formulario, fuente=None) -> Importacion:
    """Importa un formulario. Nunca lanza: registra el error por formulario."""
    fuente = fuente or fuente_por_defecto()
    registro = Importacion.objects.create(formulario=formulario)
    candado = _candados.setdefault(formulario.pk, threading.Lock())
    if not candado.acquire(blocking=False):
        registro.estado, registro.mensaje, registro.terminada_en = 'omitida', 'Ya hay una importación en curso.', timezone.now()
        registro.save()
        return registro

    conteo = {NUEVA: 0, ACTUALIZADA: 0, OMITIDA: 0}
    marca = formulario.ultima_respuesta_en
    desde = marca - timedelta(minutes=settings.PROSPECTOS['TRASLAPE_MINUTOS']) if marca else None
    try:
        for cruda in fuente.respuestas(formulario, desde):
            conteo[procesar(formulario, cruda)] += 1
            if marca is None or cruda.enviada_en > marca:
                marca = cruda.enviada_en
        formulario.ultima_respuesta_en = marca
        formulario.ultima_importacion_en = timezone.now()
        formulario.ultimo_error = ''
        formulario.errores_consecutivos = 0
        formulario.save()
        registro.estado = 'ok'
    except Exception as e:  # noqa: BLE001 - se registra por formulario y se sigue
        # La marca de agua NO avanza: lo procesado es idempotente y lo pendiente se reintenta.
        msg = f'{type(e).__name__}: {e}'[:2000]
        formulario.ultimo_error = msg
        formulario.errores_consecutivos += 1
        formulario.ultima_importacion_en = timezone.now()
        formulario.save()
        registro.estado, registro.mensaje = 'error', msg
        log.error('Fallo al importar %s: %s', formulario, msg)
    finally:
        candado.release()
    registro.nuevas, registro.actualizadas, registro.omitidas = conteo[NUEVA], conteo[ACTUALIZADA], conteo[OMITIDA]
    registro.terminada_en = timezone.now()
    registro.save()
    return registro


def importar_todos(fuente=None) -> list[Importacion]:
    return [importar(f, fuente) for f in Formulario.objects.filter(activo=True)]


def proponer_mapeo(formulario: Formulario, fuente=None) -> list[dict]:
    """Propone questionId → código comparando títulos. SIEMPRE debe revisarlo una persona."""
    fuente = fuente or fuente_por_defecto()
    preguntas = list(Pregunta.objects.filter(cuestionario=formulario.tipo))
    vigentes = {p.codigo for p in preguntas}
    actual = {q: c for q, c in (formulario.mapeo_campos or {}).items() if c in vigentes}  # códigos retirados se re-proponen
    usados, propuesta = set(), []
    repetibles = catalogos.REPETIBLES
    for qid, titulo in fuente.estructura(formulario).items():
        mejor, sim = None, 0.0
        for p in preguntas:
            a, b = texto.normalizar(titulo), texto.normalizar(p.texto)
            if a == b:
                s = 1.0
            elif p.codigo in a.replace(' ', '_'):
                s = 0.95
            elif a and (a in b or b in a):
                s = 0.9
            else:
                s = texto.jaro_winkler(a, b)
            if s > sim and (p.codigo not in usados or p.codigo in repetibles):
                mejor, sim = p, s
        codigo = actual.get(qid) or (mejor.codigo if mejor and sim >= 0.75 else None)
        if codigo:
            usados.add(codigo)
        propuesta.append({'question_id': qid, 'titulo': titulo, 'codigo': codigo, 'similitud': round(sim, 2)})
    return propuesta


OCULTOS = ('evento', 'promotor', 'token_familia')


def entry_de(question_id: str) -> str | None:
    """El «entry.NNNN» del enlace prellenado es el questionId (hexadecimal) en decimal."""
    try:
        return f'entry.{int(question_id, 16)}'
    except (TypeError, ValueError):
        return None


def aplicar_mapeo(formulario: Formulario, propuesta: list[dict], entries: dict | None = None) -> dict:
    """
    Guarda el mapeo y completa los campos prellenados de la sección «uso interno».
    `entries` ({título normalizado: entry.NNNN}) sale de la página pública del Form y es lo confiable;
    sin él se usa el questionId en decimal, que NO está documentado por Google: hay que verificarlo.
    Devuelve {código: 'verificado' | 'deducido'}.
    """
    formulario.mapeo_campos = {p['question_id']: p['codigo'] for p in propuesta if p['codigo']}
    prellenado = dict(formulario.campos_prellenado or {})
    origen = {}
    for p in propuesta:
        codigo = p['codigo']
        if codigo not in OCULTOS:
            continue
        verificado = (entries or {}).get(texto.normalizar(p.get('titulo', '')))
        if verificado:
            prellenado[codigo], origen[codigo] = verificado, 'verificado'
        elif codigo not in prellenado and entry_de(p['question_id']):
            prellenado[codigo], origen[codigo] = entry_de(p['question_id']), 'deducido'
    formulario.campos_prellenado = prellenado
    formulario.save()
    return origen


def sincronizar(formulario: Formulario, fuente=None) -> dict:
    """Lee el Form en Google: título, URL pública, mapeo propuesto y campos prellenados."""
    fuente = fuente or fuente_por_defecto()
    resumen = {'titulo': None, 'url_publica': None, 'preguntas': 0, 'mapeadas': 0, 'faltan': []}
    if hasattr(fuente, 'info') and not formulario.google_form_id.startswith('demo-'):
        info = fuente.info(formulario)
        resumen['titulo'] = (info.get('info') or {}).get('title') or (info.get('info') or {}).get('documentTitle')
        if info.get('responderUri') and not formulario.url_publica:
            formulario.url_publica = info['responderUri']
            resumen['url_publica'] = info['responderUri']
    propuesta = proponer_mapeo(formulario, fuente)
    from .fuentes import entries_publicos
    entries = entries_publicos(formulario.url_publica) if not formulario.google_form_id.startswith('demo-') else {}
    resumen['prellenado'] = aplicar_mapeo(formulario, propuesta, entries)
    codigos = set(Pregunta.objects.filter(cuestionario=formulario.tipo).values_list('codigo', flat=True))
    usados = {p['codigo'] for p in propuesta if p['codigo']}
    faltan = codigos - usados
    resumen.update(preguntas=len(propuesta), mapeadas=len(usados),
                   faltan=sorted(faltan - catalogos.RECOMENDADAS), recomendadas=sorted(faltan & catalogos.RECOMENDADAS))
    resumen['reprocesadas'] = reprocesar(formulario)
    return resumen
