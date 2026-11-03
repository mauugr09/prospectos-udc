import time

import pytest
from django.contrib.auth.models import User

from prospectos.models import Auditoria, Configuracion, DispositivoConfianza
from prospectos.servicios import dos_pasos
from prospectos.views import _coordenadas


@pytest.fixture
def jefa(client):
    u = User.objects.create_superuser('jefa@x.mx', 'jefa@x.mx', 'Clave-larga-2026!')
    client.force_login(u)
    return u


def test_la_ventana_de_salir_esta_en_cada_pantalla(client, jefa):
    html = client.get('/admin/').content.decode()
    assert 'id="sl-dialogo"' in html and 'data-minutos="30"' in html and 'salir.js' in html
    assert 'Olvidar esta computadora' not in html  # sin computadora de confianza no hay nada que olvidar


def test_salir_cierra_y_muestra_sesion_cerrada(client, jefa):
    r = client.post('/admin/herramientas/salir/')
    assert r.status_code == 302 and r.url == '/admin/herramientas/sesion-cerrada/'
    assert '_auth_user_id' not in client.session
    assert Auditoria.objects.filter(accion='cerrar_sesion').exists()
    html = client.get(r.url).content.decode()
    assert 'Sesión cerrada' in html and 'Volver a entrar' in html
    assert client.get('/admin/herramientas/salir/').status_code == 405  # solo con el botón (POST)


def test_olvidar_esta_computadora(client, jefa, rf):
    from django.http import HttpResponse
    req = rf.get('/')
    req.user = jefa
    resp = HttpResponse()
    dos_pasos.confiar(req, resp)
    client.cookies[dos_pasos.COOKIE] = resp.cookies[dos_pasos.COOKIE].value
    assert 'Olvidar esta computadora' in client.get('/admin/').content.decode()
    r = client.post('/admin/herramientas/salir/', {'olvidar': '1'})
    assert not DispositivoConfianza.objects.filter(usuario=jefa).exists()
    assert r.cookies[dos_pasos.COOKIE].value == ''


def test_sigo_aqui_renueva_la_actividad(client, jefa):
    client.get('/admin/')
    s = client.session
    s['ultima_actividad'] = antes = time.time() - 20 * 60
    s.save()
    assert client.post('/admin/herramientas/sigo-aqui/').json()['ok']
    assert client.session['ultima_actividad'] > antes
    s = client.session
    s['ultima_actividad'] = time.time() - 31 * 60
    s.save()
    assert client.post('/admin/herramientas/sigo-aqui/', HTTP_X_REQUESTED_WITH='fetch').status_code == 401


def test_sesion_cerrada_con_sesion_abierta_regresa_al_inicio(client, jefa):
    assert client.get('/admin/herramientas/sesion-cerrada/').url == '/admin/'


# --------------------------------------------------------------------------- ubicar un plantel con un clic
def test_coordenadas_de_enlaces_de_google_maps():
    assert _coordenadas('19.6512, -99.1234') == (19.6512, -99.1234)
    assert _coordenadas('https://www.google.com/maps/place/X/@19.6693,-99.1795,17z/data=!3m1') == (19.6693, -99.1795)
    assert _coordenadas('https://www.google.com/maps/place/X/@19.1,-99.1,17z/data=!3d19.6512!4d-99.1234') == (19.6512, -99.1234)
    assert _coordenadas('https://maps.google.com/?q=19.65,-99.12') == (19.65, -99.12)
    assert _coordenadas('Tultepec') is None and _coordenadas('48.85, 2.35') is None  # fuera de México


def test_ubicar_plantel_desde_el_mapa(client, jefa):
    html = client.get('/admin/herramientas/mapa/').content.decode()
    assert 'data-sede="tultepec"' in html and 'mc-colocar' in html
    r = client.post('/admin/herramientas/mapa/configurar/', {'accion': 'sede', 'clave': 'tultepec', 'lat': '19.6851', 'lng': '-99.1282'})
    assert r.json()['ok']
    assert Configuracion.obtener('mapa.sedes')['tultepec'] == {'lat': 19.6851, 'lng': -99.1282}
    assert 'data-sede="tultepec"' not in client.get('/admin/herramientas/mapa/').content.decode()
    r = client.post('/admin/herramientas/mapa/configurar/', {'accion': 'sede', 'clave': 'tultepec', 'coordenadas': 'París'})
    assert r.status_code == 400
    r = client.post('/admin/herramientas/mapa/configurar/', {'accion': 'sede', 'clave': 'otro', 'lat': '19.6', 'lng': '-99.1'})
    assert r.status_code == 400


def test_solo_administradores_ubican_planteles(client):
    from .conftest import usuario
    client.force_login(usuario('ad@x.mx', 'Admisiones'))
    assert 'data-sede=' not in client.get('/admin/herramientas/mapa/').content.decode()
    assert client.post('/admin/herramientas/mapa/configurar/', {'accion': 'sede', 'clave': 'tultepec', 'lat': '19.6',
                                                                'lng': '-99.1'}).status_code == 403


# --------------------------------------------------------------------------- formulario caducado (CSRF)
def _cliente_csrf():
    from django.test import Client
    return Client(enforce_csrf_checks=True)


def test_acceso_desde_pestana_vieja_regresa_con_aviso(db):
    User.objects.create_superuser('jefa@x.mx', 'jefa@x.mx', 'Clave-larga-2026!')
    c = _cliente_csrf()
    c.get('/admin/login/')
    c.cookies['csrftoken'] = 'x' * 32  # otra pestaña entró o salió: el código cambió
    r = c.post('/admin/login/', {'username': 'jefa@x.mx', 'password': 'Clave-larga-2026!', 'next': '/admin/herramientas/mapa/',
                                 'csrfmiddlewaretoken': 'y' * 32})
    assert r.status_code == 302 and r.url == '/admin/login/?next=/admin/herramientas/mapa/'
    html = c.get(r.url).content.decode()
    assert 'había caducado' in html and '_auth_user_id' not in c.session  # no entra solo: hay que volver a pulsar Entrar


def test_formulario_viejo_regresa_a_su_pagina(db):
    u = User.objects.create_superuser('jefa@x.mx', 'jefa@x.mx', 'Clave-larga-2026!')
    c = _cliente_csrf()
    c.force_login(u)
    c.get('/admin/')
    c.cookies['csrftoken'] = 'x' * 32
    r = c.post('/admin/herramientas/salir/', {'csrfmiddlewaretoken': 'y' * 32},
               HTTP_REFERER='http://testserver/admin/herramientas/prospectos/todos/?q=ana')
    assert r.status_code == 302 and r.url == '/admin/herramientas/prospectos/todos/?q=ana'
    assert '_auth_user_id' in c.session  # no se hizo nada
    r = c.post('/admin/herramientas/salir/', {'csrfmiddlewaretoken': 'y' * 32}, HTTP_REFERER='https://otro.sitio/x')
    assert r.url == '/admin/'


def test_sin_cookie_explica_que_hacer(db):
    c = _cliente_csrf()
    r = c.post('/admin/login/', {'username': 'a', 'password': 'b'})
    assert r.status_code == 403 and 'no guardó la cookie' in r.content.decode()
