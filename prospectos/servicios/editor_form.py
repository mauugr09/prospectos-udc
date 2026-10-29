"""
Editor de encuestas: agregar, editar, mover y quitar preguntas del Google Form desde el programa.

Cada acción se aplica en Google en ese momento (no hay un paso aparte de «publicar») y deja al programa
sabiendo qué pregunta es cuál, así que no hay que mapear nada.

Protecciones:
  - Las preguntas del sistema (nombre, edad, plantel, carrera, permiso…) se pueden reescribir, no quitar:
    las reglas de prioridad y de permiso dependen de ellas.
  - Antes de quitar una pregunta se importan las respuestas pendientes de ese Form; si no se puede, no se quita.
    Lo ya importado se conserva en el programa (Google deja de mostrar las respuestas de una pregunta borrada).
  - Cada cambio lleva la revisión del Form que se leyó: si alguien lo editó en Google mientras tanto, no se aplica.
  - Antes de cada cambio se guarda una copia del Form como estaba (datos/respaldos/forms/).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction

from .. import catalogos
from ..models import Formulario, OpcionPregunta, Pregunta
from . import auditoria, texto
from .fuentes import ErrorFuente

TIPOS = [  # (tipo del programa, tipo de Google, cómo se llama)
    ('texto', None, 'Respuesta corta'),
    ('abierta', None, 'Párrafo'),
    ('opcion', 'RADIO', 'Opción múltiple (una respuesta)'),
    ('multiple', 'CHECKBOX', 'Casillas (varias respuestas)'),
    ('lista', 'DROP_DOWN', 'Lista desplegable (una respuesta)'),
]
NOMBRE_TIPO = {t: n for t, _, n in TIPOS} | {'numero': 'Número', 'consentimiento': 'Aviso de privacidad', 'oculto': 'Uso interno (QR)',
                                              'si_no': 'Sí / No', 'catalogo': 'Respuesta corta', 'correo': 'Correo', 'telefono': 'Teléfono'}


@dataclass
class PreguntaForm:
    item_id: str
    indice: int
    titulo: str
    tipo: str              # tipo del programa
    opciones: list[dict]   # [{'value', 'isOther'?, 'goToSectionId'?}]
    requerida: bool
    pregunta: Pregunta | None
    seccion: str = ''

    @property
    def nombre_tipo(self):
        return NOMBRE_TIPO.get(self.tipo, self.tipo)

    @property
    def del_sistema(self) -> bool:
        return bool(self.pregunta and self.pregunta.de_sistema)

    @property
    def opciones_texto(self):
        return [o.get('value') for o in self.opciones if not o.get('isOther')]

    @property
    def tiene_otro(self):
        return any(o.get('isOther') for o in self.opciones)

    @property
    def opciones_de_catalogo(self) -> bool:
        """Carreras: se editan en Configuración → Carreras (cada sección muestra las de su plantel)."""
        return bool(self.pregunta and self.pregunta.opciones in ('carreras', 'preparatorias'))

    def opciones_programa(self):
        """[(OpcionPregunta | None, texto en el Form)] para editar conservando qué opción es cuál."""
        lista = self.pregunta.lista_opciones() if self.pregunta else []
        res = []
        for t in self.opciones_texto:
            o = next((o for o in lista if texto.normalizar(t) in {texto.normalizar(x) for x in [o.texto, *o.alias_lista()]}), None)
            res.append((o, t))
        return res


@dataclass
class Seccion:
    item_id: str | None
    titulo: str
    preguntas: list[PreguntaForm] = field(default_factory=list)
    fin: int = 0  # índice donde se agrega una pregunta nueva de esta sección


def _tipo_de(q: dict) -> str:
    if 'choiceQuestion' in q:
        return {'RADIO': 'opcion', 'CHECKBOX': 'multiple', 'DROP_DOWN': 'lista'}.get(q['choiceQuestion'].get('type'), 'opcion')
    if (q.get('textQuestion') or {}).get('paragraph'):
        return 'abierta'
    return 'texto'


def leer(formulario: Formulario, form: dict) -> list[Seccion]:
    """El Form como lo ve una persona: secciones y preguntas, cada una con su pregunta del programa (si la hay)."""
    mapeo = formulario.mapeo_campos or {}
    preguntas = {p.codigo: p for p in Pregunta.objects.filter(cuestionario=formulario.tipo).prefetch_related('opciones_lista')}
    secciones = [Seccion(None, '')]
    for i, item in enumerate(form.get('items', [])):
        if 'pageBreakItem' in item:
            secciones[-1].fin = i
            secciones.append(Seccion(item.get('itemId'), item.get('title', '')))
            continue
        q = (item.get('questionItem') or {}).get('question')
        if not q:
            continue
        p = preguntas.get(mapeo.get(q.get('questionId')))
        tipo = p.tipo if p and p.tipo in NOMBRE_TIPO and p.tipo not in ('opcion',) else _tipo_de(q)
        if p and p.tipo == 'opcion' and _tipo_de(q) == 'lista':
            tipo = 'lista'
        secciones[-1].preguntas.append(PreguntaForm(item['itemId'], i, item.get('title', ''), tipo,
                                                    (q.get('choiceQuestion') or {}).get('options', []),
                                                    bool(q.get('required')), p, secciones[-1].titulo))
    secciones[-1].fin = len(form.get('items', []))
    return secciones


# --------------------------------------------------------------------------- aplicar en Google
def _aplicar(formulario, fuente, form, reqs, accion, detalle, usuario):
    from .publicar import respaldar
    respaldar(formulario, form)
    r = fuente.actualizar_form(formulario.google_form_id, reqs, form.get('revisionId'))
    auditoria.registrar(accion, None, {'formulario': formulario.pk, **detalle}, usuario)
    return r or {}


def _buscar(form, item_id):
    for i, item in enumerate(form.get('items', [])):
        if item.get('itemId') == item_id:
            return i, item
    raise ErrorFuente('Esa pregunta ya no está en el Form (¿la cambió alguien en Google?). Vuelve a cargar la página.')


def _pregunta_google(tipo: str, opciones: list[str], requerida: bool, otro: bool = False) -> dict:
    q = {'required': requerida}
    google = dict((t, g) for t, g, _ in TIPOS).get(tipo)
    if google:
        lista = [{'value': o} for o in opciones] or [{'value': 'Opción 1'}]
        if otro and google != 'DROP_DOWN':
            lista.append({'isOther': True})
        q['choiceQuestion'] = {'type': google, 'options': lista}
    else:
        q['textQuestion'] = {'paragraph': tipo == 'abierta'}
    return q


def _limpias(opciones) -> list[str]:
    vistas, res = set(), []
    for o in opciones:
        o = (o or '').strip()
        if o and texto.normalizar(o) not in vistas:
            vistas.add(texto.normalizar(o))
            res.append(o[:255])
    return res


def agregar(formulario, fuente, seccion_id: str | None, texto_pregunta: str, tipo: str, opciones: list[str],
            requerida: bool, usuario=None) -> Pregunta:
    texto_pregunta = (texto_pregunta or '').strip()
    if not texto_pregunta:
        raise ValueError('Escribe la pregunta.')
    if tipo not in dict((t, n) for t, _, n in TIPOS):
        raise ValueError('Elige el tipo de respuesta.')
    opciones = _limpias(opciones)
    if tipo in ('opcion', 'multiple', 'lista') and len(opciones) < 2:
        raise ValueError('Una pregunta de opciones necesita al menos dos opciones.')
    form = fuente.info(formulario)
    seccion = next((s for s in leer(formulario, form) if s.item_id == seccion_id), None)
    indice = seccion.fin if seccion else len(form.get('items', []))
    item = {'title': texto_pregunta, 'questionItem': {'question': _pregunta_google(tipo, opciones, requerida)}}
    r = _aplicar(formulario, fuente, form, [{'createItem': {'item': item, 'location': {'index': indice}}}],
                 'encuesta_agregar', {'pregunta': texto_pregunta}, usuario)
    qid = (((r.get('replies') or [{}])[0].get('createItem') or {}).get('questionId') or [None])[0]
    with transaction.atomic():
        orden = (Pregunta.objects.filter(cuestionario=formulario.tipo).order_by('-orden').values_list('orden', flat=True).first() or 0) + 10
        p = Pregunta.objects.create(cuestionario=formulario.tipo, texto=texto_pregunta, tipo='opcion' if tipo == 'lista' else tipo,
                                    tema='otras', orden=orden, editada=True)
        for n, o in enumerate(opciones):
            OpcionPregunta.objects.create(pregunta=p, texto=o, orden=n)
        if qid:
            formulario.mapeo_campos = {**(formulario.mapeo_campos or {}), qid: p.codigo}
            formulario.save(update_fields=['mapeo_campos'])
    return p


def editar(formulario, fuente, item_id: str, texto_pregunta: str, requerida: bool, opciones: list[tuple], nuevas: list[str],
           usuario=None) -> None:
    """`opciones`: [(id de OpcionPregunta o None, texto en el Form, texto nuevo, quitar)]; `nuevas`: textos a agregar."""
    form = fuente.info(formulario)
    indice, item = _buscar(form, item_id)
    pf = next(p for s in leer(formulario, form) for p in s.preguntas if p.item_id == item_id)
    texto_pregunta = (texto_pregunta or '').strip() or pf.titulo
    nuevo = {**item, 'title': texto_pregunta}
    q = dict(nuevo['questionItem']['question'])
    q['required'] = bool(requerida)
    mascara = ['title', 'questionItem.question.required']
    cambios_opcion = []
    if 'choiceQuestion' in q and not pf.opciones_de_catalogo:
        actuales = q['choiceQuestion'].get('options', [])
        por_texto = {o.get('value'): o for o in actuales if not o.get('isOther')}
        lista = []
        for op_id, antes, despues, quitar in opciones:
            original = por_texto.get(antes)
            if original is None:
                continue
            if quitar:
                if op_id and OpcionPregunta.objects.filter(pk=op_id, fija=True).exists():
                    raise ValueError(f'«{antes}» la usan las reglas del programa: se puede renombrar, no quitar.')
                cambios_opcion.append(('quitar', op_id, antes, None))
                continue
            despues = (despues or '').strip() or antes
            lista.append({**original, 'value': despues[:255]})  # conserva «ir a la sección»
            if despues != antes:
                cambios_opcion.append(('renombrar', op_id, antes, despues))
        for t in _limpias(nuevas):
            if all(texto.normalizar(o['value']) != texto.normalizar(t) for o in lista):
                lista.append({'value': t})
                cambios_opcion.append(('agregar', None, None, t))
        if not lista:
            raise ValueError('La pregunta tiene que conservar al menos una opción.')
        q['choiceQuestion'] = {**q['choiceQuestion'], 'options': lista + [o for o in actuales if o.get('isOther')]}
        mascara.append('questionItem.question.choiceQuestion.options')
    nuevo['questionItem'] = {**nuevo['questionItem'], 'question': q}
    _aplicar(formulario, fuente, form, [{'updateItem': {'item': nuevo, 'location': {'index': indice}, 'updateMask': ','.join(mascara)}}],
             'encuesta_editar', {'pregunta': texto_pregunta}, usuario)
    p = pf.pregunta
    if not p:
        return
    with transaction.atomic():
        if p.texto != texto_pregunta:
            p.texto, p.editada = texto_pregunta, True
            p.save(update_fields=['texto', 'editada'])
        orden = (p.opciones_lista.order_by('-orden').values_list('orden', flat=True).first() or 0) + 1
        for accion, op_id, antes, despues in cambios_opcion:
            o = OpcionPregunta.objects.filter(pk=op_id, pregunta=p).first() if op_id else None
            if accion == 'renombrar':
                if o:
                    o.texto = despues
                    o.save()  # el texto anterior queda como alias: las respuestas viejas se siguen reconociendo
                else:
                    OpcionPregunta.objects.create(pregunta=p, texto=despues, alias=antes, orden=orden)
                    orden += 1
            elif accion == 'quitar' and o and not o.fija:
                o.delete()
            elif accion == 'agregar' and p.con_opciones:
                OpcionPregunta.objects.create(pregunta=p, texto=despues, orden=orden)
                orden += 1


def quitar(formulario, fuente, item_id: str, usuario=None, fuente_respuestas=None) -> None:
    from .importacion import importar
    form = fuente.info(formulario)
    indice, item = _buscar(form, item_id)
    pf = next(p for s in leer(formulario, form) for p in s.preguntas if p.item_id == item_id)
    if pf.del_sistema:
        raise ValueError('Esta pregunta la usan las reglas del programa (prioridad, permiso o unión de familias): '
                         'puedes cambiar su texto, no quitarla.')
    # Primero se traen las respuestas que falten: lo que ya llegó se queda en el programa.
    resultado = importar(formulario, fuente_respuestas)
    if resultado.estado != 'ok':
        raise ErrorFuente('No se pudieron importar las últimas respuestas de este Form; para no perderlas, no se quitó la pregunta.')
    form = fuente.info(formulario)  # releer: la importación pudo tardar
    indice, item = _buscar(form, item_id)
    _aplicar(formulario, fuente, form, [{'deleteItem': {'location': {'index': indice}}}],
             'encuesta_quitar', {'pregunta': item.get('title', '')}, usuario)
    qid = ((item.get('questionItem') or {}).get('question') or {}).get('questionId')
    mapeo = dict(formulario.mapeo_campos or {})
    codigo = mapeo.pop(qid, None)
    formulario.mapeo_campos = mapeo
    formulario.save(update_fields=['mapeo_campos'])
    if codigo and codigo not in mapeo.values():
        Pregunta.objects.filter(cuestionario=formulario.tipo, codigo=codigo, de_sistema=False).update(retirada=True)


def mover(formulario, fuente, item_id: str, direccion: str, usuario=None) -> None:
    """Sube o baja una pregunta dentro de su sección (cambiar de sección rompería la navegación del Form)."""
    form = fuente.info(formulario)
    for s in leer(formulario, form):
        for n, p in enumerate(s.preguntas):
            if p.item_id != item_id:
                continue
            vecino = n - 1 if direccion == 'arriba' else n + 1
            if not 0 <= vecino < len(s.preguntas):
                return
            destino = s.preguntas[vecino].indice
            _aplicar(formulario, fuente, form, [{'moveItem': {'originalLocation': {'index': p.indice}, 'newLocation': {'index': destino}}}],
                     'encuesta_mover', {'pregunta': p.titulo, 'direccion': direccion}, usuario)
            return
    raise ErrorFuente('Esa pregunta ya no está en el Form. Vuelve a cargar la página.')


def adoptar(formulario, fuente, item_id: str, usuario=None) -> Pregunta:
    """Una pregunta que se creó a mano en Google pasa a ser del programa (para verla en fichas y reportes)."""
    form = fuente.info(formulario)
    _, item = _buscar(form, item_id)
    q = (item.get('questionItem') or {}).get('question') or {}
    tipo = _tipo_de(q)
    orden = (Pregunta.objects.filter(cuestionario=formulario.tipo).order_by('-orden').values_list('orden', flat=True).first() or 0) + 10
    with transaction.atomic():
        p = Pregunta.objects.create(cuestionario=formulario.tipo, texto=item.get('title', 'Pregunta'),
                                    tipo='opcion' if tipo == 'lista' else tipo, tema='otras', orden=orden, editada=True)
        for n, o in enumerate(x.get('value') for x in (q.get('choiceQuestion') or {}).get('options', []) if not x.get('isOther')):
            OpcionPregunta.objects.create(pregunta=p, texto=o, orden=n)
        formulario.mapeo_campos = {**(formulario.mapeo_campos or {}), q['questionId']: p.codigo}
        formulario.save(update_fields=['mapeo_campos'])
    auditoria.registrar('encuesta_adoptar', None, {'formulario': formulario.pk, 'pregunta': p.texto}, usuario)
    from .importacion import reprocesar
    reprocesar(formulario)  # las respuestas que ya llegaron se vuelven a leer con la pregunta nueva
    return p


def es_repetible(pf: PreguntaForm) -> bool:
    return bool(pf.pregunta and pf.pregunta.codigo in catalogos.REPETIBLES)
