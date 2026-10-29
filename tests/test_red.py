"""Acceso desde otras computadoras: solo por HTTPS con certificado propio."""
import json
import ssl
import threading
import urllib.request

import pytest
from cryptography import x509
from django.contrib.auth.models import User

from prospectos.servicios import red


def test_activa_y_compatibilidad():
    assert not red.activa({})
    assert red.activa({'EN_RED': True})
    assert red.activa({'ESCUCHAR_EN': '0.0.0.0'})  # configuración vieja: ahora significa HTTPS en red
    assert not red.activa({'ESCUCHAR_EN': '127.0.0.1'})


def test_certificados_validos_para_navegadores(tmp_path, monkeypatch):
    monkeypatch.setattr(red, 'nombres_servidor', lambda: ['admisiones', 'admisiones.local', 'localhost', '192.168.1.20', '127.0.0.1'])
    ca, crt, key = red.asegurar_certificados(tmp_path)
    c = x509.load_pem_x509_certificate(crt.read_bytes())
    autoridad = x509.load_pem_x509_certificate(ca.read_bytes())
    assert (c.not_valid_after_utc - c.not_valid_before_utc).days <= 398  # límite de Safari/Chrome
    san = c.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert 'admisiones.local' in san.get_values_for_type(x509.DNSName)
    assert '192.168.1.20' in [str(i) for i in san.get_values_for_type(x509.IPAddress)]
    assert c.issuer == autoridad.subject
    assert autoridad.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    # Se reutiliza mientras no cambie la IP; con IP nueva se renueva con la MISMA autoridad (no hay que reinstalar).
    antes = crt.read_bytes()
    assert red.asegurar_certificados(tmp_path)[1].read_bytes() == antes
    monkeypatch.setattr(red, 'nombres_servidor', lambda: ['admisiones', '192.168.1.99', '127.0.0.1'])
    red.asegurar_certificados(tmp_path)
    assert crt.read_bytes() != antes and ca.read_bytes() == autoridad.public_bytes(__import__('cryptography').hazmat.primitives.serialization.Encoding.PEM)
    assert len(red.huella_ca(tmp_path).replace(' ', '')) == 64
    assert (tmp_path / 'red' / 'ca.key').stat().st_mode & 0o077 == 0  # llave privada solo para el dueño


@pytest.mark.django_db(transaction=True)
def test_servidor_https_atiende_y_el_certificado_se_valida(tmp_path, monkeypatch, settings):
    monkeypatch.setattr(red, 'nombres_servidor', lambda: ['localhost', '127.0.0.1'])
    from config.wsgi import application
    cfg = {'PUERTO_RED': 18443}
    srv = red.servidor_https(application, tmp_path, cfg, hilos=2)
    srv.prepare()
    hilo = threading.Thread(target=srv.serve, daemon=True)
    hilo.start()
    try:
        ctx = ssl.create_default_context(cafile=str(tmp_path / 'red' / 'ca.crt'))  # como un navegador que ya confía en la CA
        with urllib.request.urlopen('https://127.0.0.1:18443/salud/', context=ctx, timeout=10) as r:
            assert r.read().decode().startswith('prospectos-ok:')
        with pytest.raises(urllib.error.URLError):  # sin instalar la CA, el navegador no confía
            urllib.request.urlopen('https://127.0.0.1:18443/salud/', context=ssl.create_default_context(), timeout=10)
    finally:
        srv.stop()


def test_pagina_de_otras_computadoras_y_conectar(client, settings, tmp_path):
    settings.DATA_DIR = tmp_path
    settings.CONFIG_FILE = tmp_path / 'config.json'
    settings.CONFIG_FILE.write_text(json.dumps({'PUERTO': 8000}), encoding='utf-8')
    root = User.objects.create_superuser('red@x.mx', 'red@x.mx', 'Clave-de-prueba-123')
    client.force_login(root)
    html = client.get('/admin/herramientas/otras-computadoras/').content.decode()
    assert 'Activar el acceso por red' in html
    client.post('/admin/herramientas/otras-computadoras/', {'accion': 'activar'})
    assert json.loads(settings.CONFIG_FILE.read_text())['EN_RED'] is True
    assert (tmp_path / 'red' / 'ca.crt').exists()
    assert 'vuélvelo a abrir' in client.get('/admin/herramientas/otras-computadoras/').content.decode()
    # «conectar» y el certificado solo existen con el acceso por red ya activo (tras reiniciar).
    client.logout()
    settings.EN_RED = False
    assert client.get('/conectar/').status_code == 404
    settings.EN_RED = True
    r = client.get('/conectar/', HTTP_USER_AGENT='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605')
    assert r.status_code == 200 and 'Confiar siempre' in r.content.decode()
    r = client.get('/conectar/Prospectos-UDC.crt')
    assert r.status_code == 200 and b'BEGIN CERTIFICATE' in b''.join(r.streaming_content)
    assert b'PRIVATE' not in (tmp_path / 'red' / 'ca.crt').read_bytes()


def test_solo_el_administrador_cambia_el_acceso_por_red(client):
    u = User.objects.create_user('n@x.mx', 'n@x.mx', 'Clave-de-prueba-123', is_staff=True)
    client.force_login(u)
    assert client.get('/admin/herramientas/otras-computadoras/').status_code == 403


def test_nombre_de_mac_largo(tmp_path, monkeypatch):
    largo = 'MacBook-Pro-de-Maria-Guadalupe-Hernandez-Admisiones-Universidad-Cuautitlan'
    monkeypatch.setattr(red, 'nombre_equipo', lambda: largo)
    monkeypatch.setattr(red, 'nombres_servidor', lambda: [largo, f'{largo}.local', '192.168.1.5', '127.0.0.1'])
    _, crt, _ = red.asegurar_certificados(tmp_path)
    san = x509.load_pem_x509_certificate(crt.read_bytes()).extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert f'{largo}.local' in san.get_values_for_type(x509.DNSName)
