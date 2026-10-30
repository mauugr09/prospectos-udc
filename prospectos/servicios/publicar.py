"""
Publicar en Google: lo que se cambia en el programa (textos de preguntas, opciones, carreras) se aplica al Google Form.

Por qué así y no hospedar la encuesta nosotros: el programa vive en una computadora de la oficina y los alumnos
contestan desde su celular en la prepa; Google sigue hospedando el Form (gratis, siempre en línea) y el programa
pasa a ser el lugar donde se administran las preguntas.

Reglas de seguridad:
  - Nunca se cambia nada sin que una persona vea la lista de cambios y la confirme.
  - Antes de publicar se guarda una copia del Form tal como estaba (datos/respaldos/forms/).
  - Google rechaza el cambio si alguien editó el Form mientras tanto (writeControl.requiredRevisionId).
  - Quitar opciones o agregar preguntas viene desmarcado: hay que marcarlo a propósito.
  - Este módulo nunca borra preguntas; quitar una se hace en el editor (editor_form.quitar), que importa antes lo pendiente.
  - La API de Google no permite configurar validaciones (p. ej. «número entre 12 y 99»): esas siguen a mano.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field

from django.conf import settings
from django.utils import timezone

from .. import catalogos
from ..models import Carrera, Formulario, Pregunta
from . import auditoria, texto


@dataclass
class Cambio:
    id: str                    # identificador estable para el formulario de confirmación
    tipo: str                  # titulo | renombrar | agregar | quitar | crear
    pregunta: str              # cómo se llama la pregunta (para la persona)
    detalle: str               # qué va a pasar, en palabras
    marcado: bool = True       # propuesto por omisión
    item_id: str | None = None
    datos: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- lectura del Form
def _items_con_seccion(form: dict) -> list[tuple[int, dict, str]]:
    """(índice, item, título de la sección en que está). Las secciones son los «pageBreakItem»."""
    seccion, res = '', []
    for i, item in enumerate(form.get('items', [])):
        if 'pageBreakItem' in item:
            seccion = item.get('title', '')
        res.append((i, item, seccion))
    return res


def _plantel_de(seccion: str) -> str | None:
    n = texto.normalizar(seccion)
    for clave, nombre in catalogos.PLANTELES_CORTO.items():
        if texto.normalizar(nombre) in n:
            return clave
    return None


def _pregunta(item: dict) -> dict:
    return (item.get('questionItem') or {}).get('question') or {}


def _opciones(item: dict) -> list[dict]:
    return (_pregunta(item).get('choiceQuestion') or {}).get('options', [])


# --------------------------------------------------------------------------- qué debería decir cada pregunta
def _deseadas_carrera(plantel: str | None) -> list[Carrera]:
    qs = Carrera.objects.filter(activo=True).order_by('nombre')
    return [c for c in qs if not plantel or not c.planteles or plantel in c.planteles]


def _cambios_opciones(p: Pregunta, item: dict, plantel: str | None) -> list[Cambio]:
    actuales = [o for o in _opciones(item) if not o.get('isOther')]
    textos = [o.get('value', '') for o in actuales]
    cambios = []
    base = f'{item["itemId"]}'
    nombre = p.etiqueta or p.texto[:60]
    if p.opciones == 'carreras':
        deseadas = _deseadas_carrera(plantel)
        ids_deseados = {c.pk for c in deseadas}
        vistos = set()
        for t in textos:
            c = Carrera.resolver(t)
            if c and c.pk in ids_deseados:
                vistos.add(c.pk)
            elif c and texto.normalizar(t) not in catalogos.TEXTOS_INDECISO:
                motivo = 'ya no se ofrece' if not c.activo else 'no se ofrece en este plantel'
                cambios.append(Cambio(f'{base}:q:{texto.normalizar(t)}', 'quitar', nombre, f'Quitar «{t}» ({motivo})',
                                      marcado=False, item_id=item['itemId'], datos={'texto': t}))
        for c in deseadas:
            if c.pk not in vistos:
                donde = f' (plantel {catalogos.PLANTELES_CORTO.get(plantel, plantel)})' if plantel else ''
                cambios.append(Cambio(f'{base}:a:{c.pk}', 'agregar', nombre, f'Agregar «{c.nombre}»{donde}',
                                      item_id=item['itemId'], datos={'texto': c.nombre}))
        return cambios
    if not p.lista_opciones():
        return []
    usados = set()
    for o in p.lista_opciones():
        reconoce = {texto.normalizar(x) for x in [o.texto, *o.alias_lista()]}
        actual = next((t for t in textos if texto.normalizar(t) in reconoce and t not in usados), None)
        if actual is None:
            cambios.append(Cambio(f'{base}:a:{o.clave}', 'agregar', nombre, f'Agregar «{o.texto}»',
                                  item_id=item['itemId'], datos={'texto': o.texto}))
        else:
            usados.add(actual)
            if actual.strip() != o.texto.strip():
                cambios.append(Cambio(f'{base}:r:{o.clave}', 'renombrar', nombre, f'Cambiar «{actual}» por «{o.texto}»',
                                      item_id=item['itemId'], datos={'de': actual, 'a': o.texto}))
    for t in textos:
        if t not in usados:
            cambios.append(Cambio(f'{base}:q:{texto.normalizar(t)}', 'quitar', nombre,
                                  f'Quitar «{t}» (ya no está en el programa)', marcado=False, item_id=item['itemId'], datos={'texto': t}))
    return cambios


TIPO_GOOGLE = {'opcion': 'RADIO', 'multiple': 'CHECKBOX', 'consentimiento': 'RADIO', 'si_no': 'RADIO'}


def plan(formulario: Formulario, form: dict) -> list[Cambio]:
    """Lista de cambios para que el Form diga lo mismo que el programa."""
    mapeo = formulario.mapeo_campos or {}
    preguntas = {p.codigo: p for p in Pregunta.objects.filter(cuestionario=formulario.tipo, retirada=False).prefetch_related('opciones_lista')}
    cambios, presentes = [], set()
    for _i, item, seccion in _items_con_seccion(form):
        q = _pregunta(item)
        codigo = mapeo.get(q.get('questionId'))
        p = preguntas.get(codigo)
        if not p:
            continue
        presentes.add(codigo)
        titulo = item.get('title', '')
        # Las preguntas repetidas (una por plantel) conservan su título; el resto se iguala al del programa.
        if codigo not in catalogos.REPETIBLES and titulo.strip() != p.texto.strip():
            cambios.append(Cambio(f'{item["itemId"]}:t', 'titulo', p.etiqueta or titulo[:60], f'Cambiar el texto a «{p.texto}»',
                                  item_id=item['itemId'], datos={'a': p.texto}))
        if 'choiceQuestion' in q:
            cambios += _cambios_opciones(p, item, _plantel_de(seccion))
    faltan = [p for c, p in preguntas.items() if c not in presentes]
    for p in sorted(faltan, key=lambda x: x.orden):
        donde = 'al inicio' if p.tipo == 'consentimiento' else 'al final'
        cambios.append(Cambio(f'nueva:{p.codigo}', 'crear', p.etiqueta or p.texto[:60],
                              f'Agregar la pregunta «{p.texto}» {donde} del Form', marcado=False, datos={'codigo': p.codigo}))
    return cambios


# --------------------------------------------------------------------------- aplicar
def _item_pregunta_nueva(p: Pregunta) -> dict:
    pregunta = {'required': p.tipo == 'consentimiento'}
    if p.con_opciones or p.tipo == 'consentimiento':
        textos = list(p.etiquetas_opciones().values())
        if p.opciones == 'carreras':
            textos = [c.nombre for c in _deseadas_carrera(None)]
        pregunta['choiceQuestion'] = {'type': TIPO_GOOGLE.get(p.tipo, 'RADIO'), 'options': [{'value': t} for t in textos or ['Sí', 'No']]}
    else:
        pregunta['textQuestion'] = {'paragraph': p.tipo == 'abierta'}
    item = {'title': p.texto, 'questionItem': {'question': pregunta}}
    if p.tipo == 'oculto':
        item['description'] = 'Uso interno: se llena sola con el QR. No la modifiques.'
    return item


def solicitudes(form: dict, cambios: list[Cambio], elegidos: set[str], tipo: str) -> list[dict]:
    """Traduce los cambios elegidos a peticiones de forms.batchUpdate."""
    por_item: dict[str, list[Cambio]] = {}
    nuevas = []
    for c in cambios:
        if c.id not in elegidos:
            continue
        if c.tipo == 'crear':
            nuevas.append(c)
        else:
            por_item.setdefault(c.item_id, []).append(c)
    reqs = []
    for i, item in enumerate(form.get('items', [])):
        lista = por_item.get(item.get('itemId'))
        if not lista:
            continue
        nuevo = copy.deepcopy(item)
        mascara = []
        for c in lista:
            if c.tipo == 'titulo':
                nuevo['title'] = c.datos['a']
                if 'title' not in mascara:
                    mascara.append('title')
        opciones_cambian = [c for c in lista if c.tipo in ('renombrar', 'agregar', 'quitar')]
        if opciones_cambian:
            opciones = (nuevo['questionItem']['question'].get('choiceQuestion') or {}).get('options', [])
            otras = [o for o in opciones if o.get('isOther')]
            normales = [o for o in opciones if not o.get('isOther')]
            for c in opciones_cambian:
                if c.tipo == 'renombrar':  # conserva la posición y el «ir a la sección» de la opción
                    for o in normales:
                        if o.get('value') == c.datos['de']:
                            o['value'] = c.datos['a']
                elif c.tipo == 'quitar':
                    normales = [o for o in normales if o.get('value') != c.datos['texto']]
                elif c.tipo == 'agregar' and all(texto.normalizar(o.get('value')) != texto.normalizar(c.datos['texto']) for o in normales):
                    normales.append({'value': c.datos['texto']})
            nuevo['questionItem']['question']['choiceQuestion']['options'] = normales + otras
            mascara.append('questionItem.question.choiceQuestion.options')
        reqs.append({'updateItem': {'item': nuevo, 'location': {'index': i}, 'updateMask': ','.join(mascara)}})
    total = len(form.get('items', []))
    for c in nuevas:
        p = Pregunta.objects.get(cuestionario=tipo, codigo=c.datos['codigo'])
        indice = 0 if p.tipo == 'consentimiento' else total
        reqs.append({'createItem': {'item': _item_pregunta_nueva(p), 'location': {'index': indice}}})
        total += 1
    return reqs


def respaldar(formulario: Formulario, form: dict) -> str:
    carpeta = settings.DATA_DIR / 'respaldos' / 'forms'
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f'{formulario.google_form_id}-{timezone.localtime():%Y%m%d-%H%M%S}.json'
    ruta.write_text(json.dumps(form, ensure_ascii=False, indent=1), encoding='utf-8')
    return str(ruta)


def publicar(formulario: Formulario, elegidos: set[str], usuario=None, fuente=None) -> dict:
    """Vuelve a leer el Form, aplica los cambios elegidos y re-sincroniza el mapeo. Devuelve un resumen."""
    from .fuentes import FuenteGoogle
    from .importacion import sincronizar
    fuente = fuente or FuenteGoogle(edicion=True)
    form = fuente.info(formulario)
    cambios = plan(formulario, form)
    reqs = solicitudes(form, cambios, elegidos, formulario.tipo)
    if not reqs:
        return {'aplicados': 0, 'respaldo': None}
    # Las preguntas nuevas se crean con su código: así el mapeo las reconoce solas al re-sincronizar.
    respaldo = respaldar(formulario, form)
    fuente.actualizar_form(formulario.google_form_id, reqs, form.get('revisionId'))
    aplicados = [c for c in cambios if c.id in elegidos]
    auditoria.registrar('publicar_form', None, {'formulario': formulario.pk, 'cambios': [c.detalle for c in aplicados][:100]}, usuario)
    from ..models import Configuracion
    Configuracion.guardar(f'publicar.pendiente.{formulario.tipo}', False, usuario)
    sincronizar(formulario, fuente)
    return {'aplicados': len(aplicados), 'respaldo': respaldo}
