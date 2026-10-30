"""Teléfonos y tabletas: Android, iPhone y iPad (app instalable, contacto con un toque, página para conectarse)."""
import json

import pytest
from django.contrib.auth.models import User

from prospectos.servicios import movil, red

UA = {
    'android': 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36',
    'iphone': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1',
    'ipad_viejo': 'Mozilla/5.0 (iPad; CPU OS 12_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.1 Mobile/15E148 Safari/604.1',
    'mac': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15',
    'windows': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36',
}


def test_reconoce_el_sistema():
    assert movil.sistema(UA['android']) == 'android'
    assert movil.sistema(UA['iphone']) == 'ios'
    assert movil.sistema(UA['ipad_viejo']) == 'ios'
    assert movil.sistema(UA['mac']) == 'mac'  # iPadOS 13+ también dice Macintosh: lo corrige la página en el navegador
    assert movil.sistema(UA['windows']) == 'windows'
    assert movil.sistema('') == 'windows'


@pytest.mark.parametrize('entrada, esperado', [
    ('55 1234 5678', '525512345678'),
    ('(55) 1234-5678', '525512345678'),
    ('+52 55 1234 5678', '525512345678'),
    ('044 55 1234 5678', '525512345678'),
    ('+52 1 55 1234 5678', '525512345678'),  # celular con el «1» de antes
    ('+1 415 555 0100', '14155550100'),
    ('12345', None),
    ('', None),
    (None, None),
])
def test_numero_internacional(entrada, esperado):
    assert movil.internacional(entrada) == esperado


def test_acciones_de_contacto():
    acciones = movil.acciones_contacto(telefono='55 1234 5678', correo='ana.lopez@correo.mx')
    assert [a[1] for a in acciones] == ['Llamar', 'WhatsApp', 'Correo']
    assert acciones[0][2] == 'tel:+525512345678'
    assert acciones[1][2] == 'https://wa.me/525512345678'
    assert acciones[2][2] == 'mailto:ana.lopez@correo.mx'
    assert movil.acciones_contacto(telefono='123', correo='sin-arroba') == []
    assert movil.acciones_contacto() == []


def test_manifiesto_para_instalar(client):
    r = client.get('/manifest.webmanifest')
    assert r.status_code == 200 and r['Content-Type'].startswith('application/manifest+json')
    m = json.loads(r.content)
    assert m['start_url'] == '/admin/' and m['scope'] == '/' and m['display'] == 'standalone'
    tamanos = {(i['sizes'], i.get('purpose')) for i in m['icons']}
    assert ('192x192', 'any') in tamanos and ('512x512', 'any') in tamanos and ('512x512', 'maskable') in tamanos


def test_service_worker_no_guarda_datos(client):
    r = client.get('/sw.js')
    assert r.status_code == 200 and 'javascript' in r['Content-Type']
    assert r['Service-Worker-Allowed'] == '/'
    js = r.content.decode()
    # Solo guarda la pantalla «sin conexión» y un icono; las páginas del programa van siempre a la red.
    assert "'/sin-conexion/'" in js and 'caches.match(OFFLINE)' in js
    assert 'cache.put' not in js and '.put(' not in js


def test_pagina_sin_conexion_es_publica_y_sin_datos(client):
    r = client.get('/sin-conexion/')
    assert r.status_code == 200 and 'Sin conexión con Prospectos' in r.content.decode()


def test_las_paginas_traen_lo_necesario_para_instalarse(client):
    html = client.get('/admin/login/').content.decode()
    assert 'rel="manifest" href="/manifest.webmanifest"' in html
    assert 'apple-touch-icon' in html and 'icono-180.png' in html
    assert 'prospectos/js/movil.js' in html
    assert html.count('name="viewport"') == 1


def test_pedidos_del_telefono_no_cuentan_como_uso_ni_piden_cambiar_clave(client, settings):
    u = User.objects.create_user('p@x.mx', 'p@x.mx', 'Clave-de-prueba-123', is_staff=True)
    from prospectos.models import Perfil
    Perfil.objects.update_or_create(usuario=u, defaults={'debe_cambiar_clave': True})
    client.force_login(u)
    for ruta in ('/sw.js', '/manifest.webmanifest', '/sin-conexion/'):
        assert client.get(ruta).status_code == 200, ruta  # sin redirigir a «cambia tu contraseña»


def _red_activa(settings, tmp_path):
    settings.DATA_DIR = tmp_path
    settings.EN_RED = True
    red.asegurar_certificados(tmp_path)


@pytest.mark.parametrize('ua, titulo, texto', [
    ('android', 'Instálalo en Android', 'Certificado de CA'),
    ('iphone', 'Instálalo en iPhone o iPad', 'Ajustes de confianza de certificados'),
])
def test_conectar_desde_telefono(client, settings, tmp_path, ua, titulo, texto):
    _red_activa(settings, tmp_path)
    html = client.get('/conectar/', HTTP_USER_AGENT=UA[ua]).content.decode()
    assert titulo in html and texto in html
    assert 'no está contemplado' not in html
    assert 'Ponlo en la pantalla de inicio' in html
    # La sección de su sistema se ve; la de Windows queda oculta.
    seccion = html.split(f'<h2>2. {titulo}</h2>')[0].rsplit('<section', 1)[1]
    assert 'hidden' not in seccion


def test_qr_para_conectar_el_telefono(client, settings, tmp_path, monkeypatch):
    settings.DATA_DIR = tmp_path
    settings.CONFIG_FILE = tmp_path / 'config.json'
    settings.CONFIG_FILE.write_text(json.dumps({'EN_RED': True}), encoding='utf-8')
    settings.EN_RED = True
    monkeypatch.setattr(red, 'ips_locales', lambda: ['192.168.1.20'])
    red.asegurar_certificados(tmp_path)
    client.force_login(User.objects.create_superuser('qr@x.mx', 'qr@x.mx', 'Clave-de-prueba-123'))
    html = client.get('/admin/herramientas/otras-computadoras/').content.decode()
    assert 'Desde un teléfono o tableta' in html
    assert 'https://192.168.1.20:8443/conectar/' in html and 'data:image/svg+xml' in html


def test_lo_que_pide_el_telefono_no_espera_la_verificacion_en_2_pasos(client, settings):
    settings.CONFIG = {**settings.CONFIG, 'DOS_PASOS_TODOS': True}
    u = User.objects.create_user('promo@udc.mx', 'promo@udc.mx', 'Clave-de-prueba-123', is_staff=True)
    client.force_login(u)
    assert client.get('/admin/').status_code == 302  # todavía no activa sus 2 pasos
    for ruta in ('/sw.js', '/manifest.webmanifest', '/sin-conexion/'):
        assert client.get(ruta).status_code == 200, ruta
