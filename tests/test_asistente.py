"""Kuali, el asistente propio: entiende con reglas, no sale a internet, no inventa cifras y solo propone acciones."""
import json
import socket

import pytest
from django.contrib.auth.models import User

from prospectos.models import Actividad, Auditoria, Evento, Notificacion, Prospecto
from prospectos.servicios import asistente, kuali

from .conftest import alumno, importar, tutor

URL = '/admin/herramientas/asistente/'
CLAVE = 'Clave-de-prueba-123'


@pytest.fixture
def jefa(client):
    u = User.objects.create_superuser('jefa@x.mx', 'jefa@x.mx', CLAVE, first_name='Laura')
    client.force_login(u)
    return u


@pytest.fixture
def datos(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', 'Valeria Quintero Salas', edad='18', carrera=['Derecho']),
             alumno('a2', 'Mateo Quintero Ruiz', edad='19', minutos=3), alumno('a3', 'Ana Paz Ríos', edad='20', minutos=5))
    return Prospecto.objects.filter(fusionado_en__isnull=True)


@pytest.fixture
def sin_internet(monkeypatch):
    """Cualquier intento de conexión hace fallar la prueba: Kuali funciona sin red."""
    def prohibido(*a, **k):
        raise AssertionError('Kuali intentó conectarse a la red')
    monkeypatch.setattr(socket.socket, 'connect', prohibido)


def _preguntar(client, mensaje, **extra):
    return client.post(URL, json.dumps({'mensaje': mensaje, **extra}), content_type='application/json', HTTP_X_REQUESTED_WITH='fetch')


# --------------------------------------------------------------------------- entender

@pytest.mark.parametrize('pregunta, intencion', [
    ('hola', 'saludo'), ('¿qué puedes hacer?', 'quien_eres'),
    ('¿Cómo vamos este mes?', 'cifras'), ('¿Cuántos aspirantes llegaron en septiembre por carrera?', 'cifras'),
    ('¿Qué carreras piden en cada plantel?', 'cruce'),
    ('¿Qué canal convierte mejor?', 'conversion'), ('¿Qué prepas convierten mejor?', 'conversion'),
    ('¿En qué etapa del embudo se nos quedan más?', 'embudo'),
    ('¿Qué es lo más urgente hoy?', 'pendientes'), ('¿Qué visitas tenemos los próximos días?', 'visitas'),
    ('¿Cómo uno a una familia con su alumno?', 'ayuda'), ('¿Qué significa esperando permiso?', 'ayuda'),
    ('asigna 5 listos de Tultepec a pepe@x.mx', 'asignar'),
    ('agrega el open house al calendario el 21 de noviembre a las 10', 'crear_actividad'),
    ('qué opinas del clima', 'no_entendi'),
])
def test_entiende_la_intencion(jefa, pregunta, intencion):
    assert (kuali.entender(pregunta, {}, {})['intencion'] or 'no_entendi') == intencion


def test_periodo_plantel_y_carrera(jefa):
    e = kuali.entender('¿Cuántos aspirantes llegaron en septiembre en Tultepec para Derecho?', {}, {})
    assert e['periodo_explicito'] and 'septiembre' in e['periodo_txt']
    assert e['args'].get('plantel') == 'tultepec' and e['args'].get('carrera') == 'Derecho'


def test_la_pregunta_de_seguimiento_reusa_la_anterior(jefa, prepa):
    r = kuali.responder(jefa, '¿Cuántos aspirantes llegaron en septiembre?', {}, {})
    e = kuali.entender('¿y en Tultepec?', r['memoria'], {})
    assert e['intencion'] == 'cifras' and e['heredada'] and 'septiembre' in e['periodo_txt']
    assert e['args'].get('plantel') == 'tultepec'


def test_el_nombre_del_plantel_no_es_una_prepa(jefa):
    from prospectos.models import Preparatoria
    Preparatoria.objects.create(nombre='Colegio de Prueba Tultepec')
    e = kuali.entender('¿y en Tultepec?', {'intencion': 'cifras', 'args': {}}, {})
    assert e['args'].get('plantel') == 'tultepec' and not e['args'].get('preparatoria')
    e = kuali.entender('¿Cuántos llegaron del Colegio de Prueba Tultepec?', {}, {})
    assert e['args'].get('preparatoria')


def test_mes_a_mes_sin_periodo_son_seis_meses(jefa):
    e = kuali.entender('¿Cómo vamos mes a mes?', {}, {})
    assert e['args'].get('agrupar_por') == 'mes' and '6 meses' in e['periodo_txt']


def test_permiso_sin_periodo_cuenta_todos_los_de_hoy(jefa, f_alumno, evento):
    importar(f_alumno, alumno('a1', 'Menor Uno', edad='16'))
    Prospecto.objects.update(creado_en='2020-01-01T00:00:00Z')  # llegó hace mucho y sigue esperando
    r = kuali.responder(jefa, '¿Cuántos menores esperan permiso?', {}, {})
    assert r['texto'].startswith('Hoy: **1 menor') or '**1 ' in r['texto']


# --------------------------------------------------------------------------- responder

def test_cifras_comprobables_con_grafica_calculo_y_siguientes(client, jefa, datos, sin_internet):
    r = _preguntar(client, '¿Cuántos aspirantes llegaron este año por plantel?').json()
    assert r['ok'] and '**3 aspirantes' in r['texto'] and r['entendi'].startswith('conteo')
    assert r['visual']['tipo'] == 'barras' and r['visual']['total'] == 3
    assert r['calculos'] and r['calculos'][0]['enlace'].startswith('/admin/prospectos/prospecto/?')
    assert len(r['siguientes']) >= 2
    assert Auditoria.objects.filter(accion='asistente').exists()


def test_grupos_chicos_se_ocultan(jefa, datos):
    r = kuali.responder(jefa, '¿Cuántos aspirantes llegaron este año por carrera?', {}, {})
    assert 'Valeria' not in r['texto'] and ('menos de 3' in json.dumps(r['visual'], ensure_ascii=False) or r['visual']['filas'])


def test_no_entendi_sugiere_preguntas_que_si_sabe(client, jefa, sin_internet):
    r = _preguntar(client, 'qué opinas del clima').json()
    assert r['ok'] and r['siguientes'] and 'No entendí' in r['texto'] or 'no sé' in r['texto'].lower()


def test_ayuda_sale_del_manual(client, jefa, sin_internet):
    r = _preguntar(client, '¿Cómo uno a una familia con su alumno?').json()
    assert r['ok'] and 'Familias por unir' in r['texto']
    assert all(s.startswith('Explícame') or s.startswith('¿') for s in r['siguientes'])


def test_mensaje_vacio_se_rechaza(client, jefa):
    assert _preguntar(client, '   ').status_code == 400


# --------------------------------------------------------------------------- ficha

def test_mensaje_para_la_ficha_con_su_nombre(client, jefa, f_alumno, f_tutor, evento, sin_internet):
    importar(f_alumno, alumno('a1', 'Valeria Quintero Salas', edad='17', tutor_correo=None, tutor_telefono=None))
    importar(f_tutor, tutor('t1', 'Valeria Quintero Salas', evento='EV1', tutor_nombre='Rosa Salas', minutos=60))
    p = Prospecto.objects.get(fusionado_en__isnull=True)
    r = _preguntar(client, 'Escribe un WhatsApp para este aspirante', ficha=p.pk).json()
    assert 'Valeria' in r['texto'] and 'Laura' in r['texto']  # local: puede usar los nombres reales
    r = _preguntar(client, 'Prepara la llamada', ficha=p.pk).json()
    assert r['ok'] and r['texto']


def test_perfil_no_disponible_sin_permiso_de_la_familia(jefa, f_alumno, evento):
    importar(f_alumno, alumno('a1', 'Menor Sin Permiso', edad='16'))
    p = Prospecto.objects.get()
    assert 'no tiene permiso' in asistente.h_perfil(jefa, {}, {'ficha': p.pk})['error']


# --------------------------------------------------------------------------- acciones: solo propone

def test_asignar_solo_propone_y_se_confirma(client, jefa, datos, sin_internet):
    asesor = User.objects.create_user('pepe@x.mx', 'pepe@x.mx', CLAVE, first_name='Pepe', last_name='Luna', is_staff=True)
    r = _preguntar(client, 'Asigna 2 aspirantes a Pepe Luna').json()
    assert r['ok'] and len(r['propuestas']) == 1
    tarjeta = r['propuestas'][0]
    assert tarjeta['titulo'] == 'Asignar 2 aspirantes a Pepe Luna'
    assert not Prospecto.objects.filter(asesor=asesor).exists()  # todavía no cambió nada
    j = client.post(f'{URL}propuesta/{tarjeta["id"]}/', {'decision': 'si'}).json()
    assert j['ok'] and Prospecto.objects.filter(asesor=asesor).count() == 2
    assert Auditoria.objects.filter(accion='asistente_asignar').exists()
    assert Notificacion.objects.filter(usuario=asesor, tipo='asignado').exists()
    assert client.post(f'{URL}propuesta/{tarjeta["id"]}/', {'decision': 'si'}).status_code == 404  # no se repite


def test_si_ya_tienen_asesor_lo_explica(client, jefa, datos):
    pepe = User.objects.create_user('pepe@x.mx', 'pepe@x.mx', CLAVE, first_name='Pepe', last_name='Luna', is_staff=True)
    Prospecto.objects.update(asesor=jefa)
    r = _preguntar(client, 'Asigna 2 aspirantes a Pepe Luna').json()
    assert 'ya tienen asesor' in r['texto'] and not r['propuestas'] and not Prospecto.objects.filter(asesor=pepe).exists()


def test_crear_visita_y_actividad_se_descartan_sin_efecto(client, jefa, prepa, sin_internet):
    r = _preguntar(client, 'agenda una visita a Prepa Uno el 10 de marzo de 2099 a las 9').json()
    assert r['propuestas'] and r['propuestas'][0]['titulo'] == 'Crear visita'
    client.post(f'{URL}propuesta/{r["propuestas"][0]["id"]}/', {'decision': 'no'})
    assert not Evento.objects.exists()
    r = _preguntar(client, 'agrega el open house al calendario el 20 de marzo de 2099').json()
    assert r['propuestas']
    client.post(f'{URL}propuesta/{r["propuestas"][0]["id"]}/', {'decision': 'si'})
    assert 'open house' in Actividad.objects.get().titulo.lower()


def test_promotor_no_asigna(promotor, datos):
    assert asistente.proponer(promotor, 'asignar_asesor', {'asesor': 'x'})['error']


# --------------------------------------------------------------------------- pantalla y mascota

def test_boton_en_todas_las_paginas_y_en_la_ficha(client, jefa, datos):
    p = datos.first()
    html = client.get(f'/admin/prospectos/prospecto/{p.pk}/change/').content.decode()
    assert 'id="as-abrir"' in html and 'Preparar llamada' in html


def test_configurar_solo_el_nombre(client, jefa):
    html = client.get(URL + 'configurar/').content.decode()
    assert 'Propio, en esta PC' in html and 'Gratis' in html
    client.post(URL + 'configurar/', {'mascota_nombre': 'Cuauhti<script>'})
    assert asistente.nombre_mascota() == 'Cuauhtiscript'  # sin < >
    assert 'data-nombre="Cuauhtiscript"' in client.get('/admin/').content.decode()
    assert kuali.responder(jefa, '¿cómo te llamas?', {}, {})['texto'].count('Cuauhtiscript')


def test_sin_sesion_no_hay_mascota(client):
    assert 'id="km"' not in client.get('/admin/login/').content.decode()


def test_no_hay_rastros_de_ia_externa():
    from django.conf import settings
    import prospectos.servicios.asistente as mod
    fuente = open(mod.__file__, encoding='utf-8').read() + open(kuali.__file__, encoding='utf-8').read()
    assert 'requests' not in fuente and 'anthropic' not in fuente.lower()
    assert not hasattr(settings, 'IA_API_KEY')


# --------------------------------------------------------------------------- analítica (sin datos personales)

def test_herramientas_de_analisis_no_filtran_datos_personales(jefa, datos, f_alumno):
    from prospectos.servicios import analitica
    todo = json.dumps([analitica.cifras(jefa, {'agrupar_por': 'preparatoria', 'desde': '2000-01-01'}),
                       analitica.cruce(jefa, {'filas': 'carrera', 'columnas': 'plantel', 'desde': '2000-01-01'}),
                       analitica.conversion(jefa, {'agrupar_por': 'preparatoria', 'desde': '2000-01-01'}),
                       analitica.pendientes(jefa, {}), analitica.visitas(jefa, {})], ensure_ascii=False, default=str)
    for p in datos:
        for parte in p.nombre_aspirante.split():
            assert parte not in todo
    assert 'menos de 3' in todo  # grupos chicos ocultos


def test_conversion_marca_tasas_con_pocos_casos(jefa, datos):
    from prospectos.servicios import analitica
    r = analitica.conversion(jefa, {'agrupar_por': 'plantel', 'desde': '2000-01-01'})
    assert r['grupos'] and all(g['confiable'] is False for g in r['grupos'])


def test_enlaces_de_las_herramientas_abren_la_lista_filtrada(client, jefa, datos):
    from prospectos.servicios import analitica
    r = analitica.cifras(jefa, {'plantel': 'cuautitlan', 'carrera': 'Derecho', 'desde': '2000-01-01'})
    html = client.get(r['enlace_a_la_lista']).content.decode()
    assert r['total'] == 3 and all(n in html for n in ('Valeria Quintero', 'Mateo Quintero', 'Ana Paz'))
    otra = analitica.cifras(jefa, {'plantel': 'tultepec', 'desde': '2000-01-01'})
    assert otra['total'] == 0 and 'Valeria Quintero' not in client.get(otra['enlace_a_la_lista']).content.decode()


def test_probar_kuali_corre(jefa, capsys):
    from django.core.management import call_command
    call_command('probar_kuali', 'hola', '¿Cómo vamos este mes?', '--breve')
    assert 'Entendió 2 de 2' in capsys.readouterr().out


def test_seguimiento_cambia_el_corte_sin_perder_filtros(jefa):
    m = kuali.responder(jefa, '¿Cómo vamos este mes por plantel?', {}, {})['memoria']
    r = kuali.responder(jefa, '¿y en Tultepec?', m, {})
    e = kuali.entender('¿y en Tultepec?', m, {})
    assert e['args'].get('plantel') == 'tultepec' and not e['args'].get('agrupar_por')  # por plantel ya no dice nada
    e = kuali.entender('¿y por carrera?', r['memoria'], {})
    assert e['args'].get('plantel') == 'tultepec' and e['args'].get('agrupar_por') == 'carrera' and e['heredada']
