"""Asistente: nunca envía datos personales, no inventa cifras, solo propone acciones y respeta el tope de gasto."""
import json

import pytest
from django.contrib.auth.models import User

from prospectos.models import Actividad, Auditoria, Configuracion, Evento, Notificacion, Prospecto
from prospectos.servicios import asistente
from prospectos.servicios.cifrado import cifrar

from .conftest import alumno, importar, tutor

URL = '/admin/herramientas/asistente/'
CLAVE = 'Clave-de-prueba-123'


class FalsaAPI:
    """Imita la API de Anthropic: devuelve las respuestas en orden y guarda lo que se le mandó."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.enviado = []

    def __call__(self, url, timeout=None, json=None, headers=None):
        self.enviado.append(__import__('copy').deepcopy(json))
        cuerpo = self.respuestas.pop(0)

        class R:
            status_code = 200

            @staticmethod
            def json():
                return cuerpo
        return R()

    def todo(self) -> str:
        return __import__('json').dumps(self.enviado, ensure_ascii=False)


def usa(nombre, entrada, id_='t1'):
    return {'stop_reason': 'tool_use', 'usage': {'input_tokens': 1000, 'output_tokens': 50},
            'content': [{'type': 'tool_use', 'id': id_, 'name': nombre, 'input': entrada}]}


def responde(texto):
    return {'stop_reason': 'end_turn', 'usage': {'input_tokens': 1200, 'output_tokens': 200}, 'content': [{'type': 'text', 'text': texto}]}


@pytest.fixture
def jefa(client):
    u = User.objects.create_superuser('jefa@x.mx', 'jefa@x.mx', CLAVE, first_name='Laura')
    client.force_login(u)
    return u


@pytest.fixture
def activo():
    Configuracion.guardar('asistente.llave', cifrar('sk-ant-prueba-' + 'x' * 30))
    Configuracion.guardar('asistente.activo', True)


@pytest.fixture
def datos(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', 'Valeria Quintero Salas', edad='18', carrera=['Derecho']),
             alumno('a2', 'Mateo Quintero Ruiz', edad='19', minutos=3), alumno('a3', 'Ana Paz Ríos', edad='20', minutos=5))
    return Prospecto.objects.filter(fusionado_en__isnull=True)


def _preguntar(client, mensaje, **extra):
    return client.post(URL, json.dumps({'mensaje': mensaje, **extra}), content_type='application/json', HTTP_X_REQUESTED_WITH='fetch')


def test_sin_ia_responde_con_el_manual(client, jefa, monkeypatch):
    llamado = []
    monkeypatch.setattr(asistente.requests, 'post', lambda *a, **k: llamado.append(1))
    r = _preguntar(client, '¿Cómo uno a una familia con su alumno?').json()
    assert r['ok'] and r['sin_ia'] and 'Familias por unir' in r['texto'] and not llamado


def test_no_envia_nombres_telefonos_ni_correos(client, jefa, activo, datos, monkeypatch):
    llamado = []
    monkeypatch.setattr(asistente.requests, 'post', lambda *a, **k: llamado.append(1))
    for texto in ['Prepara la llamada para Valeria Quintero', 'Escríbele a valeria@correo.mx', 'Llama al 55 1234 5678',
                  'CURP LOGA080315MMCPRNA1']:
        r = _preguntar(client, texto)
        assert r.status_code == 400 and r.json()['tipo'] == 'privacidad', texto
    assert not llamado


def test_un_compañero_del_equipo_si_se_puede_nombrar(jefa, datos):
    User.objects.create_user('v@x.mx', 'v@x.mx', CLAVE, first_name='Valeria', last_name='Quintero', is_staff=True)
    asistente.revisar_pregunta('Asigna 10 aspirantes a Valeria Quintero')  # no lanza


def test_cifras_salen_del_sistema_y_ocultan_grupos_chicos(client, jefa, activo, datos, monkeypatch):
    api = FalsaAPI(usa('consultar_cifras', {'metrica': 'aspirantes', 'agrupar_por': 'carrera', 'desde': '2026-01-01', 'hasta': '2026-12-31'}),
                   responde('Hay **3** aspirantes en el periodo.'))
    monkeypatch.setattr(asistente.requests, 'post', api)
    r = _preguntar(client, '¿Cuántos aspirantes hay por carrera?').json()
    assert r['ok'] and 'Hay 3' in r['texto'].replace('**', '') and r['consulto'] == ['consultar_cifras']
    resultado = json.loads(api.enviado[1]['messages'][-1]['content'][0]['content'])
    assert resultado['total'] == 3 and all(g['n'] == 'menos de 3' or g['n'] >= 3 for g in resultado['grupos'])
    for p in datos:
        assert p.nombre_aspirante.split()[0] not in api.todo()
    assert Auditoria.objects.filter(accion='asistente').exists()
    g = asistente.gasto()
    assert g['consultas'] == 1 and g['entrada'] == 2200 and g['usd'] > 0


def test_perfil_de_la_ficha_sin_nombre_y_borrador_personalizado(client, jefa, activo, f_alumno, f_tutor, evento, monkeypatch):
    importar(f_alumno, alumno('a1', 'Valeria Quintero Salas', edad='17', tutor_correo=None, tutor_telefono=None))
    importar(f_tutor, tutor('t1', 'Valeria Quintero Salas', evento='EV1', tutor_nombre='Rosa Salas', minutos=60))
    p = Prospecto.objects.get(fusionado_en__isnull=True)
    assert p.consentimiento
    api = FalsaAPI(usa('perfil_del_aspirante', {}), responde('Hola [NOMBRE], soy [ASESOR] de la UDC. ¿Te cuento de Derecho?'))
    monkeypatch.setattr(asistente.requests, 'post', api)
    r = _preguntar(client, 'Escribe un WhatsApp para este aspirante', ficha=p.pk).json()
    assert r['texto'].startswith('Hola Valeria, soy Laura de la UDC')
    enviado = api.todo()
    for prohibido in ['Valeria', 'Quintero', 'Rosa', 'Prepa Uno', 'Salas', '@correo', '1111']:
        assert prohibido not in enviado, prohibido
    assert 'perfil_del_aspirante' in enviado and 'Derecho' in enviado


def test_perfil_no_disponible_sin_permiso_de_la_familia(jefa, f_alumno, evento):
    importar(f_alumno, alumno('a1', 'Menor Sin Permiso', edad='16'))
    p = Prospecto.objects.get()
    assert 'no tiene permiso' in asistente.h_perfil(jefa, {}, {'ficha': p.pk})['error']


def test_asignar_asesor_solo_propone_y_se_confirma(client, jefa, activo, datos, monkeypatch):
    asesor = User.objects.create_user('pepe@x.mx', 'pepe@x.mx', CLAVE, first_name='Pepe', last_name='Luna', is_staff=True)
    api = FalsaAPI(usa('proponer_asignar_asesor', {'asesor': 'pepe@x.mx', 'maximo': 2}),
                   responde('Te dejé la propuesta para asignar 2 aspirantes a Pepe. Revísala y confirma.'))
    monkeypatch.setattr(asistente.requests, 'post', api)
    r = _preguntar(client, 'Asigna los 2 de mayor prioridad a pepe@x.mx'.replace('pepe@x.mx', 'Pepe Luna')).json()
    assert r['ok'] and len(r['propuestas']) == 1
    tarjeta = r['propuestas'][0]
    assert 'Asignar 2 aspirantes a Pepe Luna' == tarjeta['titulo'] and len(tarjeta['lineas']) == 2
    assert not Prospecto.objects.filter(asesor=asesor).exists()  # todavía no cambió nada
    for p in datos:
        assert p.nombre_aspirante not in api.todo()  # los nombres solo están en la tarjeta local
    j = client.post(f'{URL}propuesta/{tarjeta["id"]}/', {'decision': 'si'}).json()
    assert j['ok'] and Prospecto.objects.filter(asesor=asesor).count() == 2
    assert Auditoria.objects.filter(accion='asistente_asignar').exists()
    assert Notificacion.objects.filter(usuario=asesor, tipo='asignado').exists()
    assert client.post(f'{URL}propuesta/{tarjeta["id"]}/', {'decision': 'si'}).status_code == 404  # no se repite


def test_crear_visita_y_actividad_se_descartan_sin_efecto(client, jefa, activo, prepa, monkeypatch):
    api = FalsaAPI({'stop_reason': 'tool_use', 'usage': {'input_tokens': 10, 'output_tokens': 10}, 'content': [
        {'type': 'tool_use', 'id': 'a', 'name': 'proponer_crear_visita', 'input': {'preparatoria': 'Prepa Uno', 'fecha': '2099-03-10', 'hora_inicio': '09:00'}},
        {'type': 'tool_use', 'id': 'b', 'name': 'proponer_crear_actividad', 'input': {'titulo': 'Open house', 'tipo': 'open_house', 'fecha': '2099-03-20'}}]},
        responde('Listo para confirmar.'))
    monkeypatch.setattr(asistente.requests, 'post', api)
    r = _preguntar(client, 'Agenda visita a Prepa Uno el 10 de marzo y el open house el 20').json()
    visita, act = r['propuestas']
    assert visita['titulo'] == 'Crear visita' and 'Preparatoria: Prepa Uno' in visita['lineas']
    client.post(f'{URL}propuesta/{visita["id"]}/', {'decision': 'no'})
    assert not Evento.objects.exists()
    client.post(f'{URL}propuesta/{act["id"]}/', {'decision': 'si'})
    assert Actividad.objects.get().titulo == 'Open house'


def test_promotor_solo_cuenta_lo_suyo_y_no_asigna(promotor, datos):
    nombres = {t['name'] for t in asistente.herramientas(promotor, {})}
    assert 'proponer_asignar_asesor' not in nombres
    assert asistente.proponer(promotor, 'asignar_asesor', {'asesor': 'x'})['error']
    otro = User.objects.create_user('otro@x.mx', 'otro@x.mx', CLAVE, is_staff=True)
    Prospecto.objects.update(promotor=otro)
    if 'consultar_cifras' in nombres:
        assert asistente.h_cifras(promotor, {'desde': '2000-01-01'})['total'] == 0


def test_tope_de_gasto_detiene_al_asistente(client, jefa, activo, monkeypatch):
    llamado = []
    monkeypatch.setattr(asistente.requests, 'post', lambda *a, **k: llamado.append(1))
    Configuracion.guardar('asistente.tope_usd', 1.0)
    Configuracion.guardar(f'asistente.gasto.{asistente._mes()}', {'usd': 1.01, 'entrada': 0, 'salida': 0, 'consultas': 5})
    r = _preguntar(client, '¿Cuántos aspirantes hay?')
    assert r.status_code == 503 and 'tope' in r.json()['mensaje'] and not llamado


def test_las_ordenes_dentro_de_datos_no_ejecutan_nada(client, jefa, activo, prepa, monkeypatch):
    """Aunque la IA «obedezca» algo raro, solo puede proponer: nada cambia sin confirmar."""
    api = FalsaAPI(usa('proponer_asignar_asesor', {'asesor': 'jefa@x.mx', 'maximo': 50, 'solo_sin_asesor': False}), responde('Hecho.'))
    monkeypatch.setattr(asistente.requests, 'post', api)
    _preguntar(client, '¿Qué prepas hay?')
    assert not Prospecto.objects.filter(asesor__isnull=False).exists()


def test_configuracion_guarda_la_llave_cifrada(client, jefa):
    url = URL + 'configurar/'
    assert 'Qué recibe la IA y qué no' in client.get(url).content.decode()
    client.post(url, {'llave': 'no-es-llave', 'activo': '1', 'tope_usd': '5'})
    assert not asistente.llave()
    llave = 'sk-ant-api03-' + 'a' * 40
    client.post(url, {'llave': llave, 'activo': '1', 'tope_usd': '5', 'modelo': 'claude-haiku-5-5'})
    assert asistente.llave() == llave and asistente.activo() and asistente.tope_usd() == 5
    assert llave not in json.dumps(Configuracion.obtener('asistente.llave'))
    assert Auditoria.objects.filter(accion='asistente_configurar').exists()


def test_boton_en_todas_las_paginas_y_en_la_ficha(client, jefa, datos):
    p = datos.first()
    html = client.get(f'/admin/prospectos/prospecto/{p.pk}/change/').content.decode()
    assert 'id="as-abrir"' in html and 'Preparar llamada' in html


def test_error_de_conexion_se_explica(client, jefa, activo, monkeypatch):
    def caida(*a, **k):
        raise asistente.requests.ConnectionError()
    monkeypatch.setattr(asistente.requests, 'post', caida)
    r = _preguntar(client, '¿Cuántos aspirantes hay este mes?')
    assert r.status_code == 503 and 'internet' in r.json()['mensaje']


def test_kuali_en_el_menu_con_su_nombre_y_en_las_instrucciones(client, jefa):
    html = client.get('/admin/').content.decode()
    assert 'id="km"' in html and 'data-nombre="Kuali"' in html and 'class="kuali' in html
    client.post(URL + 'configurar/', {'mascota_nombre': 'Cuauhti<script>', 'tope_usd': '10'})
    assert asistente.nombre_mascota() == 'Cuauhtiscript'  # sin < >
    html = client.get('/admin/').content.decode()
    assert 'data-nombre="Cuauhtiscript"' in html
    sistema = asistente._sistema(jefa, {})
    assert 'Eres Cuauhtiscript, un aguilucho' in sistema and 'nunca hagas bromas' in sistema


def test_sin_sesion_no_hay_mascota(client):
    assert 'id="km"' not in client.get('/admin/login/').content.decode()
