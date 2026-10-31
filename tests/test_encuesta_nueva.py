"""Encuestas nuevas desde el programa, la de padres siempre visible y los escudos de los planteles en el mapa."""
import copy
import itertools

import pytest
from django.contrib.auth.models import User

from prospectos.models import Formulario
from prospectos.servicios import crear_form, reportes

from .test_publicar import google  # noqa: F401

CLAVE = 'Clave-de-prueba-123'
_ids = itertools.count(500)


class GoogleVarios:
    """Varios Forms a la vez: crear, llenar con batchUpdate, publicar."""

    def __init__(self, form):
        self.forms = {form['formId']: form}
        self.publicados, self.compartidos = [], []

    def info(self, formulario):
        return copy.deepcopy(self.forms[formulario.google_form_id])

    def estructura(self, formulario):
        return {i['questionItem']['question']['questionId']: i['title']
                for i in self.forms[formulario.google_form_id]['items'] if 'questionItem' in i}

    def respuestas(self, formulario, desde):
        return iter(())

    def crear_form(self, titulo):
        fid = f'nuevo-{next(_ids)}'
        self.forms[fid] = {'formId': fid, 'info': {'title': titulo}, 'items': [], 'responderUri': f'https://docs.google.com/forms/d/e/{fid}/viewform'}
        return {'formId': fid, 'responderUri': self.forms[fid]['responderUri']}

    def actualizar_form(self, form_id, reqs, revision):
        f = self.forms[form_id]
        for r in reqs:
            if 'updateFormInfo' in r:
                f['info'].update(r['updateFormInfo']['info'])
            elif 'createItem' in r:
                item = copy.deepcopy(r['createItem']['item'])
                assert 'itemId' not in item and 'questionId' not in (item.get('questionItem') or {}).get('question', {})
                n = next(_ids)
                item['itemId'] = f'n{n}'
                if 'questionItem' in item:
                    item['questionItem']['question']['questionId'] = f'nq{n}'
                f['items'].insert(r['createItem']['location']['index'], item)
        return {}

    def publicar_form(self, form_id):
        self.publicados.append(form_id)
        return True

    def compartir(self, form_id, correo):
        self.compartidos.append((form_id, correo))


@pytest.fixture
def varios(google):
    f, g = google
    f.para_qr = True
    f.save()
    g.form['items'].append({'itemId': 'img', 'title': 'Foto del plantel', 'imageItem': {'image': {'contentUri': 'x'}}})
    return f, GoogleVarios(g.form)


def test_copia_del_form_actual_sin_ids_ni_saltos_viejos(varios):
    origen, g = varios
    f, r = crear_form.crear('Vocacional · Feria 2027', 'ALUMNO', 'copiar', 'Gracias por contestar', g, origen=origen,
                            compartir_con='admisiones@udc.edu.mx')
    nuevo = g.forms[f.google_form_id]
    assert nuevo['info']['description'] == 'Gracias por contestar' and f.google_form_id in g.publicados
    assert r['omitidos'] == ['Foto del plantel'] and r['preguntas'] == len(nuevo['items'])
    plantel = next(i for i in nuevo['items'] if 'choiceQuestion' in i.get('questionItem', {}).get('question', {}))
    assert all('goToSectionId' not in o for o in plantel['questionItem']['question']['choiceQuestion']['options'])
    f.refresh_from_db()
    assert set(f.mapeo_campos.values()) >= {'nombre_completo', 'plantel', 'carrera', 'modalidad'}  # el mapeo sale solo
    assert not f.para_qr and reportes.formulario_activo('ALUMNO') == origen  # los QR no cambian solos
    assert g.compartidos == [(f.google_form_id, 'admisiones@udc.edu.mx')]
    crear_form.usar_para_qr(f)
    assert reportes.formulario_activo('ALUMNO') == f
    origen.refresh_from_db()
    assert not origen.para_qr


def test_con_las_preguntas_del_programa(db, monkeypatch):
    monkeypatch.setattr('prospectos.servicios.fuentes.entries_publicos', lambda *a, **k: {})
    g = GoogleVarios({'formId': 'x', 'items': []})
    f, r = crear_form.crear('Encuesta para padres · 2027', 'TUTOR', 'programa', '', g)
    items = g.forms[f.google_form_id]['items']
    assert r['preguntas'] > 5 and f.tipo == 'TUTOR'
    assert 'aviso de privacidad' in items[0]['title'].lower() or 'privacidad' in items[0]['title'].lower()  # el consentimiento primero
    with pytest.raises(ValueError):
        crear_form.crear('', 'TUTOR', 'programa', '', g)
    with pytest.raises(ValueError):
        crear_form.crear('Sin origen', 'ALUMNO', 'copiar', '', g)


def test_la_encuesta_de_padres_se_ve_aunque_google_no_responda(client, f_alumno, f_tutor):
    client.force_login(User.objects.create_superuser('r@x.mx', 'r@x.mx', CLAVE))
    html = client.get('/admin/herramientas/encuestas/').content.decode()
    assert 'Padres o tutores' in html and 'Nueva encuesta' in html
    tutor = Formulario.objects.get(tipo='TUTOR')
    html = client.get(f'/admin/herramientas/encuestas/?f={tutor.pk}').content.decode()
    assert 'Encuesta para padres o tutores' in html and 'Lo que el programa espera' in html


def test_pantalla_de_nueva_encuesta_y_permisos(client, google):
    client.force_login(User.objects.create_user('n@x.mx', 'n@x.mx', CLAVE, is_staff=True))
    assert client.get('/admin/herramientas/encuestas/nueva/').status_code == 403
    client.force_login(User.objects.create_superuser('r@x.mx', 'r@x.mx', CLAVE))
    html = client.get('/admin/herramientas/encuestas/nueva/').content.decode()
    assert 'Copia del Form actual' in html and 'No cambia los QR' in html
    r = client.post('/admin/herramientas/encuestas/nueva/', {'titulo': '', 'tipo': 'ALUMNO', 'base': 'programa'})
    assert r.status_code == 200 and 'Ponle un título' in r.content.decode()


def test_planteles_en_el_mapa_con_su_escudo(client):
    from prospectos.models import Configuracion
    from prospectos.views import sedes_udc
    sedes = sedes_udc()
    assert [s['clave'] for s in sedes] == ['cuautitlan'] and sedes[0]['escudo'].endswith('aguila.svg')  # Cuautitlán viene ubicado
    Configuracion.guardar('mapa.sedes', {'tultepec': {'lat': 19.68, 'lng': -99.13}})
    sedes = {s['clave']: s for s in sedes_udc()}
    assert sedes['tultepec']['escudo'].endswith('toro.svg') and sedes['tultepec']['universidad'] == 'Universidad de Tultepec'
    client.force_login(User.objects.create_superuser('r@x.mx', 'r@x.mx', CLAVE))
    assert 'toro.svg' in client.get('/admin/').content.decode()
