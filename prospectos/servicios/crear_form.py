"""
Encuestas nuevas: crea un Google Form desde el programa, lo publica, lo registra y lo deja listo para importar.

Dos puntos de partida:
  - «copiar»: una copia del Form actual de ese tipo (secciones, preguntas, opciones, textos). Las imágenes y videos
    no se pueden copiar con la API: se avisa cuáles faltan.
  - «programa»: solo las preguntas del programa (Configuración → Preguntas), en su orden.
Como las preguntas se llaman igual, el mapeo sale solo y las respuestas llegan a las fichas como las de siempre.
El Form nuevo NO cambia los QR de las visitas hasta que se elija «Usar para los QR» (Formulario.para_qr).
"""

import copy

from django.db import transaction

from ..models import Formulario, Pregunta
from . import auditoria, importacion, publicar

BASES = [('copiar', 'Copia del Form actual'), ('programa', 'Solo las preguntas del programa')]
_NO_COPIABLES = ('imageItem', 'videoItem')


def _limpiar_pregunta(q: dict) -> dict:
    q = {k: v for k, v in q.items() if k != 'questionId'}
    for o in (q.get('choiceQuestion') or {}).get('options', []):
        o.pop('goToSectionId', None)  # apunta a secciones del Form viejo
        o.pop('image', None)
    q.pop('image', None)
    return q


def items_copiados(form: dict) -> tuple[list[dict], list[str]]:
    """Los items del Form de origen, sin identificadores (Google asigna nuevos). Devuelve (items, títulos omitidos)."""
    items, omitidos = [], []
    for item in form.get('items', []):
        if any(k in item for k in _NO_COPIABLES):
            omitidos.append(item.get('title') or 'Imagen o video sin título')
            continue
        nuevo = {k: copy.deepcopy(v) for k, v in item.items() if k != 'itemId'}
        if 'questionItem' in nuevo:
            nuevo['questionItem'] = {'question': _limpiar_pregunta(nuevo['questionItem'].get('question', {}))}
        if 'questionGroupItem' in nuevo:
            g = nuevo['questionGroupItem']
            g['questions'] = [_limpiar_pregunta(q) for q in g.get('questions', [])]
            g.pop('image', None)
        items.append(nuevo)
    return items, omitidos


def items_del_programa(tipo: str) -> list[dict]:
    preguntas = list(Pregunta.objects.filter(cuestionario=tipo, retirada=False).prefetch_related('opciones_lista').order_by('orden'))
    preguntas.sort(key=lambda p: (p.tipo != 'consentimiento', p.orden))  # el aviso de privacidad, primero
    return [publicar._item_pregunta_nueva(p) for p in preguntas]


def crear(titulo: str, tipo: str, base: str, descripcion: str, fuente, usuario=None, origen: Formulario | None = None,
          compartir_con: str | None = None) -> tuple[Formulario, dict]:
    titulo = (titulo or '').strip()[:200]
    if not titulo:
        raise ValueError('Ponle un título a la encuesta.')
    if tipo not in ('ALUMNO', 'TUTOR'):
        raise ValueError('Elige para quién es la encuesta.')
    omitidos: list[str] = []
    if base == 'copiar':
        if not origen:
            raise ValueError('No hay un Form de ese tipo para copiar. Elige «Solo las preguntas del programa».')
        items, omitidos = items_copiados(fuente.info(origen))
    else:
        items = items_del_programa(tipo)
    if not items:
        raise ValueError('No hay preguntas que poner en la encuesta.')

    nuevo = fuente.crear_form(titulo)
    form_id = nuevo['formId']
    reqs = []
    if descripcion:
        reqs.append({'updateFormInfo': {'info': {'description': descripcion.strip()[:4000]}, 'updateMask': 'description'}})
    reqs += [{'createItem': {'item': it, 'location': {'index': i}}} for i, it in enumerate(items)]
    fuente.actualizar_form(form_id, reqs, None)
    publicado = fuente.publicar_form(form_id)
    compartido = None
    if compartir_con:
        try:
            fuente.compartir(form_id, compartir_con)
            compartido = compartir_con
        except Exception as e:  # noqa: BLE001 - el Form ya existe; solo no se pudo compartir
            compartido = f'error: {e}'[:200]
    with transaction.atomic():
        f = Formulario.objects.create(nombre=titulo, tipo=tipo, google_form_id=form_id, url_publica=nuevo.get('responderUri') or '',
                                      activo=True, para_qr=False)
    resumen = importacion.sincronizar(f, fuente)
    auditoria.registrar('encuesta_crear', f, {'tipo': tipo, 'base': base, 'preguntas': len(items), 'omitidas': len(omitidos)},
                        usuario=usuario)
    return f, {'preguntas': len(items), 'omitidos': omitidos, 'publicado': publicado, 'compartido': compartido, 'mapeo': resumen}


def usar_para_qr(formulario: Formulario, usuario=None) -> None:
    with transaction.atomic():
        Formulario.objects.filter(tipo=formulario.tipo).update(para_qr=False)
        Formulario.objects.filter(pk=formulario.pk).update(para_qr=True)
    auditoria.registrar('encuesta_qr', formulario, {'tipo': formulario.tipo}, usuario=usuario)
