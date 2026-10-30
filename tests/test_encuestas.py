"""Editor de encuestas: agregar, editar, mover y quitar preguntas del Google Form desde el programa."""
import pytest
from django.contrib.auth.models import User

from prospectos.models import OpcionPregunta, Pregunta
from prospectos.servicios import editor_form, importacion
from prospectos.servicios.fuentes import ErrorFuente

from .test_publicar import google  # noqa: F401  (fixture: Form de prueba con secciones por plantel)


def _titulos(g):
    return [i.get('title') for i in g.form['items']]


def test_leer_por_secciones(google):
    f, g = google
    secciones = editor_form.leer(f, g.info(f))
    assert [s.titulo for s in secciones] == ['', 'Universidad de Cuautitlán México', 'Universidad de Tultepec']
    primera = secciones[0].preguntas
    assert primera[0].del_sistema and primera[1].opciones_texto[0] == 'Universidad de Cuautitlán México'
    assert secciones[1].preguntas[0].opciones_de_catalogo and secciones[1].preguntas[0].tiene_otro


def test_agregar_pregunta_en_una_seccion_y_el_programa_ya_la_lee(google):
    f, g = google
    tultepec = editor_form.leer(f, g.info(f))[2]
    p = editor_form.agregar(f, g, tultepec.item_id, '¿Trabajas actualmente?', 'opcion', ['Sí', 'No', 'Sí', ''], True)
    item = g.form['items'][-1]
    assert item['title'] == '¿Trabajas actualmente?' and item['questionItem']['question']['required']
    assert [o['value'] for o in item['questionItem']['question']['choiceQuestion']['options']] == ['Sí', 'No']
    f.refresh_from_db()
    assert f.mapeo_campos[item['questionItem']['question']['questionId']] == p.codigo
    assert list(p.opciones_lista.values_list('texto', flat=True)) == ['Sí', 'No']
    with pytest.raises(ValueError):
        editor_form.agregar(f, g, None, 'Elige', 'opcion', ['Solo una'], False)


def test_editar_texto_y_opciones_conserva_lo_importado(google):
    f, g = google
    pm = next(p for p in editor_form.leer(f, g.info(f))[2].preguntas if p.pregunta and p.pregunta.codigo == 'modalidad')
    ops = pm.opciones_programa()
    semanal = next(o for o, t in ops if t == 'Semanal')
    datos = [(o.pk if o else None, t, 'Escolarizada (lunes a viernes)' if t == 'Semanal' else t, t == 'Dominical' and not (o and o.fija))
             for o, t in ops]
    editor_form.editar(f, g, pm.item_id, '¿Qué modalidad prefieres?', True, datos, ['En línea'])
    q = g.form['items'][6]
    assert q['title'] == '¿Qué modalidad prefieres?' and q['questionItem']['question']['required']
    valores = [o['value'] for o in q['questionItem']['question']['choiceQuestion']['options']]
    assert valores[0] == 'Escolarizada (lunes a viernes)' and 'En línea' in valores
    semanal.refresh_from_db()
    assert semanal.texto == 'Escolarizada (lunes a viernes)' and 'Semanal' in semanal.alias_lista()
    p = Pregunta.objects.get(cuestionario='ALUMNO', codigo='modalidad')
    assert importacion.normalizar(p, 'Semanal') == 'semanal'  # las respuestas viejas siguen contando


def test_opcion_fija_no_se_quita(google):
    f, g = google
    pm = next(p for p in editor_form.leer(f, g.info(f))[2].preguntas if p.pregunta and p.pregunta.codigo == 'modalidad')
    fija = next((o, t) for o, t in pm.opciones_programa() if o and o.fija)
    with pytest.raises(ValueError):
        editor_form.editar(f, g, pm.item_id, pm.titulo, False, [(fija[0].pk, fija[1], fija[1], True)], [])


def test_quitar_solo_las_que_no_usa_el_programa_e_importa_antes(google, monkeypatch):
    f, g = google
    p = editor_form.agregar(f, g, None, '¿Cómo te enteraste de nosotros?', 'texto', [], False)
    nueva = next(x for x in editor_form.leer(f, g.info(f))[0].preguntas if x.pregunta == p)
    sistema = editor_form.leer(f, g.info(f))[0].preguntas[0]
    with pytest.raises(ValueError):
        editor_form.quitar(f, g, sistema.item_id, fuente_respuestas=g)
    importadas = []
    monkeypatch.setattr('prospectos.servicios.importacion.importar',
                        lambda formulario, fuente=None: importadas.append(1) or type('R', (), {'estado': 'ok'})())
    editor_form.quitar(f, g, nueva.item_id, fuente_respuestas=g)
    assert importadas and '¿Cómo te enteraste de nosotros?' not in _titulos(g)
    p.refresh_from_db()
    assert p.retirada and p.codigo not in f.mapeo_campos.values()
    # Si no se pudo importar, no se quita.
    p2 = editor_form.agregar(f, g, None, 'Otra', 'texto', [], False)
    x = next(x for x in editor_form.leer(f, g.info(f))[0].preguntas if x.pregunta == p2)
    monkeypatch.setattr('prospectos.servicios.importacion.importar', lambda formulario, fuente=None: type('R', (), {'estado': 'error'})())
    with pytest.raises(ErrorFuente):
        editor_form.quitar(f, g, x.item_id, fuente_respuestas=g)
    assert 'Otra' in _titulos(g)


def test_mover_dentro_de_la_seccion(google):
    f, g = google
    primera = editor_form.leer(f, g.info(f))[0].preguntas
    editor_form.mover(f, g, primera[0].item_id, 'abajo')
    assert [p.item_id for p in editor_form.leer(f, g.info(f))[0].preguntas] == [primera[1].item_id, primera[0].item_id]
    editor_form.mover(f, g, primera[0].item_id, 'abajo')  # ya es la última de su sección: no cruza a otra
    assert [p.item_id for p in editor_form.leer(f, g.info(f))[0].preguntas] == [primera[1].item_id, primera[0].item_id]


def test_adoptar_pregunta_hecha_a_mano_en_google(google):
    f, g = google
    g.form['items'].insert(1, {'itemId': 'im', 'title': '¿Tienes beca actualmente?', 'questionItem': {'question': {
        'questionId': 'qm', 'choiceQuestion': {'type': 'RADIO', 'options': [{'value': 'Sí'}, {'value': 'No'}]}}}})
    sin = next(p for p in editor_form.leer(f, g.info(f))[0].preguntas if p.item_id == 'im')
    assert sin.pregunta is None
    p = editor_form.adoptar(f, g, 'im')
    f.refresh_from_db()
    assert f.mapeo_campos['qm'] == p.codigo and p.tipo == 'opcion' and p.opciones_lista.count() == 2


def test_pantalla(client, google, monkeypatch):
    f, g = google
    monkeypatch.setattr('prospectos.servicios.fuentes.FuenteGoogle.info', lambda self, formulario: g.info(formulario))
    monkeypatch.setattr('prospectos.servicios.fuentes.FuenteGoogle.actualizar_form', lambda self, *a: g.actualizar_form(*a))
    client.force_login(User.objects.create_superuser('e@x.mx', 'e@x.mx', 'Clave-de-prueba-123'))
    html = client.get('/admin/herramientas/encuestas/').content.decode()
    assert 'Universidad de Tultepec' in html and 'Agregar pregunta' in html and 'Guardar en el Form' in html
    r = client.post('/admin/herramientas/encuestas/?tipo=ALUMNO', {'accion': 'agregar', 'texto': '¿Trabajas?', 'tipo': 'texto'}, follow=True)
    assert 'Pregunta agregada' in r.content.decode() and '¿Trabajas?' in _titulos(g)
    assert client.get('/admin/herramientas/publicar/').status_code == 302
    assert OpcionPregunta.objects.exists()


def test_pantalla_del_editor_parece_el_form(client, google, monkeypatch):
    f, g = google
    from prospectos.servicios import fuentes
    client.force_login(User.objects.create_superuser('enc@x.mx', 'enc@x.mx', 'Clave-de-prueba-123'))
    monkeypatch.setattr(fuentes.FuenteGoogle, 'info', lambda self, fo: g.info(fo))
    html = client.get(f'/admin/herramientas/encuestas/?tipo={f.tipo}').content.decode()
    assert 'Sección 1 de 3' in html and 'enc-opciones-vista' in html and 'data-tipo="multiple"' in html
    assert 'La usa el programa' in html and 'href="#sec-2"' in html
