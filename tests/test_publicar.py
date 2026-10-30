"""Publicar en Google: lo que se cambia en el programa llega al Form, con confirmación y sin borrar preguntas."""
import copy
import itertools

import pytest
from django.contrib.auth.models import User

from prospectos.models import Carrera, Configuracion, Formulario, OpcionPregunta, Pregunta
from prospectos.servicios import importacion, publicar
from prospectos.servicios.fuentes import ErrorFuente

_ids = itertools.count(100)


def _q(qid, titulo, choice=None, other=False):
    q = {'questionId': qid}
    if choice:
        opciones = [o if isinstance(o, dict) else {'value': o} for o in choice[1]]
        if other:
            opciones.append({'isOther': True})
        q['choiceQuestion'] = {'type': choice[0], 'options': opciones}
    else:
        q['textQuestion'] = {}
    return {'itemId': 'i' + qid, 'title': titulo, 'questionItem': {'question': q}}


class GoogleFalso:
    """Imita la Forms API: guarda el Form, aplica batchUpdate y exige la revisión vigente."""

    def __init__(self, form):
        self.form, self.revision, self.llamadas = form, 'r1', []

    def info(self, formulario):
        return copy.deepcopy({**self.form, 'revisionId': self.revision})

    def estructura(self, formulario):
        return {i['questionItem']['question']['questionId']: i['title'] for i in self.form['items'] if 'questionItem' in i}

    def respuestas(self, formulario, desde):
        return iter(())

    def actualizar_form(self, form_id, reqs, revision):
        if revision != self.revision:
            raise ErrorFuente('Alguien cambió el Form en Google mientras revisabas.')
        self.llamadas.append(reqs)
        respuestas = []
        for r in reqs:
            if 'updateItem' in r:
                self.form['items'][r['updateItem']['location']['index']] = r['updateItem']['item']
                respuestas.append({})
            elif 'deleteItem' in r:
                del self.form['items'][r['deleteItem']['location']['index']]
                respuestas.append({})
            elif 'moveItem' in r:
                item = self.form['items'].pop(r['moveItem']['originalLocation']['index'])
                self.form['items'].insert(r['moveItem']['newLocation']['index'], item)
                respuestas.append({})
            else:
                item = copy.deepcopy(r['createItem']['item'])
                n = str(next(_ids))
                item['itemId'] = 'i' + n
                item['questionItem']['question']['questionId'] = 'q' + n
                self.form['items'].insert(r['createItem']['location']['index'], item)
                respuestas.append({'createItem': {'itemId': 'i' + n, 'questionId': ['q' + n]}})
        self.revision = 'r' + str(len(self.llamadas) + 1)
        return {'replies': respuestas}


def texto_de(codigo):
    return Pregunta.objects.get(cuestionario='ALUMNO', codigo=codigo).texto


@pytest.fixture
def google(monkeypatch):
    monkeypatch.setattr('prospectos.servicios.fuentes.entries_publicos', lambda *a, **k: {})
    carrera = texto_de('carrera')
    form = {'formId': 'real-1', 'items': [
        _q('a1', texto_de('nombre_completo')),
        _q('a2', texto_de('plantel'), ('RADIO', [{'value': 'Universidad de Cuautitlán México', 'goToSectionId': 'sC'},
                                                  {'value': 'Universidad de Tultepec', 'goToSectionId': 'sT'}])),
        {'itemId': 'sC', 'title': 'Universidad de Cuautitlán México', 'pageBreakItem': {}},
        _q('a3', carrera, ('CHECKBOX', ['Derecho', 'Pedagogía', 'Filosofía', 'Aún no lo sé']), other=True),
        {'itemId': 'sT', 'title': 'Universidad de Tultepec', 'pageBreakItem': {}},
        _q('a4', carrera, ('CHECKBOX', ['Derecho', 'Pedagogía'])),
        _q('a5', texto_de('modalidad'), ('RADIO', ['Semanal', 'Sabatino', 'Dominical'])),
    ]}
    f = Formulario.objects.create(nombre='Vocacional', tipo='ALUMNO', google_form_id='real-1',
                                  mapeo_campos={'a1': 'nombre_completo', 'a2': 'plantel', 'a3': 'carrera', 'a4': 'carrera', 'a5': 'modalidad'})
    return f, GoogleFalso(form)


def _cambios(f, g):
    return {c.id: c for c in publicar.plan(f, g.info(f))}


def test_carrera_nueva_va_solo_a_la_seccion_de_su_plantel_y_la_apagada_se_propone_quitar(google):
    f, g = google
    # Lo que no está en el catálogo del programa no se toca; aquí se igualan los planteles al Form de prueba.
    for c in Carrera.objects.all():
        c.activo = c.nombre in ('Derecho', 'Pedagogía', 'Filosofía')
        c.save()
    Carrera.objects.filter(nombre='Filosofía').update(activo=False)
    Carrera.objects.create(nombre='Enfermería', planteles=['tultepec'])
    c = _cambios(f, g)
    agregar = [x for x in c.values() if x.tipo == 'agregar' and 'Enfermería' in x.detalle]
    assert len(agregar) == 1 and agregar[0].item_id == 'ia4' and agregar[0].marcado
    quitar = [x for x in c.values() if x.tipo == 'quitar']
    assert [x.datos['texto'] for x in quitar] == ['Filosofía'] and not quitar[0].marcado  # quitar: solo a propósito
    assert all(not x.marcado for x in c.values() if x.tipo == 'crear')  # preguntas nuevas: solo a propósito
    r = publicar.publicar(f, {agregar[0].id, quitar[0].id}, fuente=g)
    assert r['aplicados'] == 2 and r['respaldo']
    items = {i['itemId']: i for i in g.form['items']}
    tultepec = [o.get('value') for o in items['ia4']['questionItem']['question']['choiceQuestion']['options']]
    cuautitlan = items['ia3']['questionItem']['question']['choiceQuestion']['options']
    assert 'Enfermería' in tultepec and 'Filosofía' not in [o.get('value') for o in cuautitlan]
    assert cuautitlan[-1].get('isOther')  # «Otro» se conserva al final
    plantel = items['ia2']['questionItem']['question']['choiceQuestion']['options']
    assert plantel[0]['goToSectionId'] == 'sC'  # la navegación entre secciones no se toca
    assert not _cambios(f, g) or all(x.tipo in ('crear', 'agregar') and 'Enfermería' not in x.detalle for x in _cambios(f, g).values())


def test_renombrar_opcion_conserva_lo_importado(google):
    f, g = google
    o = OpcionPregunta.objects.get(pregunta__cuestionario='ALUMNO', pregunta__codigo='modalidad', clave='semanal')
    o.texto, o.alias = 'Escolarizada (lunes a viernes)', 'Semanal'
    o.save()
    c = [x for x in _cambios(f, g).values() if x.tipo == 'renombrar']
    assert len(c) == 1 and c[0].datos == {'de': 'Semanal', 'a': 'Escolarizada (lunes a viernes)'}
    publicar.publicar(f, {c[0].id}, fuente=g)
    modal = g.form['items'][6]['questionItem']['question']['choiceQuestion']['options']
    assert modal[0]['value'] == 'Escolarizada (lunes a viernes)'
    # Las respuestas viejas («Semanal») y las nuevas se reconocen igual.
    p = Pregunta.objects.get(cuestionario='ALUMNO', codigo='modalidad')
    assert importacion.normalizar(p, 'Semanal') == importacion.normalizar(p, 'Escolarizada (lunes a viernes)') == 'semanal'


def test_pregunta_nueva_y_texto_cambiado(google):
    f, g = google
    p = Pregunta.objects.get(cuestionario='ALUMNO', codigo='nombre_completo')
    p.texto = 'Tu nombre completo (nombre y apellidos)'
    p.save()
    c = _cambios(f, g)
    titulo = next(x for x in c.values() if x.tipo == 'titulo')
    nueva = c['nueva:consentimiento_aviso_privacidad']
    publicar.publicar(f, {titulo.id, nueva.id}, fuente=g)
    assert g.form['items'][0]['title'].startswith('He leído')  # el aviso va al inicio y es obligatorio
    assert g.form['items'][0]['questionItem']['question']['required']
    assert g.form['items'][1]['title'] == 'Tu nombre completo (nombre y apellidos)'
    f.refresh_from_db()
    assert 'consentimiento_aviso_privacidad' in f.mapeo_campos.values()  # se re-sincroniza solo
    assert not any(x.tipo == 'titulo' for x in _cambios(f, g).values())


def test_si_alguien_edita_el_form_mientras_tanto_no_se_pisa(google):
    f, g = google
    Carrera.objects.create(nombre='Enfermería', planteles=['tultepec'])

    class OtraPersonaEdita(GoogleFalso):
        def info(self, formulario):
            datos = super().info(formulario)
            self.revision = 'r-otra-persona'  # alguien guarda en Google entre la lectura y la escritura
            return datos
    ids = {x.id for x in publicar.plan(f, g.info(f)) if x.tipo == 'agregar'}
    otra = OtraPersonaEdita(copy.deepcopy(g.form))
    with pytest.raises(ErrorFuente):
        publicar.publicar(f, ids, fuente=otra)
    assert otra.llamadas == []


def test_pantalla_y_aviso_de_pendiente(client, google, monkeypatch):
    f, g = google
    monkeypatch.setattr('prospectos.servicios.fuentes.FuenteGoogle.info', lambda self, formulario: g.info(formulario))
    root = User.objects.create_superuser('p@x.mx', 'p@x.mx', 'Clave-de-prueba-123')
    client.force_login(root)
    c = Carrera.objects.get(nombre='Derecho')
    client.post(f'/admin/prospectos/carrera/{c.pk}/change/', {'nombre': 'Derecho', 'area': c.area, 'planteles': c.planteles,
                                                              'alias': '', 'activo': 'on'}, follow=True)
    assert Configuracion.obtener('publicar.pendiente.ALUMNO') is True
    Carrera.objects.create(nombre='Enfermería', planteles=['tultepec'])
    html = client.get('/admin/herramientas/encuestas/').content.decode()
    assert 'aún no está' in html and 'del programa' in html and 'Agregar «Enfermería»' in html
