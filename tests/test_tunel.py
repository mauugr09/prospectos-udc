"""Compartir por internet con el túnel rápido de Cloudflare (sin servidor ni dominio)."""
import json
import sys
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User

from prospectos.servicios import tunel

LINEAS_OK = [
    'INF Requesting new quick Tunnel on trycloudflare.com...',
    'INF Retrying https://api.trycloudflare.com/tunnel',
    'INF |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |',
    'INF |  https://seasonal-deck-organisms-sf.trycloudflare.com                                       |',
]


def test_el_enlace_no_es_el_de_la_api():
    assert not tunel.PATRON_URL.search('failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel"')
    m = tunel.PATRON_URL.search(LINEAS_OK[-1])
    assert m and m.group(0) == 'https://seasonal-deck-organisms-sf.trycloudflare.com'


def test_activo_por_config_o_entorno():
    assert not tunel.activo({}, {})
    assert tunel.activo({'COMPARTIR_EN_INTERNET': True}, {})
    assert tunel.activo({}, {'PROSPECTOS_COMPARTIR': '1'})


def _falso(tmp_path, lineas, quedarse=True):
    """Un «cloudflared» de mentira que imprime lo que imprime el real."""
    ruta = tmp_path / 'cloudflared-falso.py'
    cuerpo = ''.join(f'print({linea!r}, flush=True)\n' for linea in lineas)
    if quedarse:
        cuerpo += 'import time\nwhile True: time.sleep(1)\n'
    ruta.write_text(cuerpo, encoding='utf-8')
    lanzador = tmp_path / 'cloudflared'
    lanzador.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{ruta}" "$@"\n', encoding='utf-8')
    lanzador.chmod(0o755)
    return str(lanzador)


@pytest.mark.skipif(sys.platform == 'win32', reason='el cloudflared falso es un script de shell')
def test_abre_el_tunel_y_lo_cierra(tmp_path, monkeypatch):
    monkeypatch.setenv('PROSPECTOS_CLOUDFLARED', _falso(tmp_path, LINEAS_OK))
    url, proc = tunel.abrir(8000, tmp_path, espera=15, bitacora=tmp_path / 'cloudflared.log')
    try:
        assert url == 'https://seasonal-deck-organisms-sf.trycloudflare.com'
        assert proc.poll() is None
    finally:
        tunel.cerrar(proc)
    assert proc.poll() is not None
    assert 'seasonal-deck' in (tmp_path / 'cloudflared.log').read_text(encoding='utf-8')


@pytest.mark.skipif(sys.platform == 'win32', reason='el cloudflared falso es un script de shell')
def test_sin_internet_falla_rapido_y_con_explicacion(tmp_path, monkeypatch):
    malas = ['INF Requesting new quick Tunnel on trycloudflare.com...',
             'failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel": no such host']
    monkeypatch.setenv('PROSPECTOS_CLOUDFLARED', _falso(tmp_path, malas, quedarse=False))
    with pytest.raises(tunel.ErrorTunel, match='no such host'):
        tunel.abrir(8000, tmp_path, espera=15)


def test_sin_cloudflared_dice_como_instalarlo(tmp_path, monkeypatch):
    monkeypatch.delenv('PROSPECTOS_CLOUDFLARED', raising=False)
    monkeypatch.setattr(tunel, 'buscar_cloudflared', lambda d=None: None)
    with pytest.raises(tunel.ErrorTunel, match='cloudflared'):
        tunel.abrir(8000, tmp_path)


def test_aplica_la_direccion_publica_al_arrancar():
    s = SimpleNamespace(ALLOWED_HOSTS=['127.0.0.1'], CSRF_TRUSTED_ORIGINS=[], URL_PUBLICA=None, TUNEL_RAPIDO=False)
    tunel.aplicar_a_django(s, 'https://seasonal-deck-organisms-sf.trycloudflare.com')
    assert 'seasonal-deck-organisms-sf.trycloudflare.com' in s.ALLOWED_HOSTS and '127.0.0.1' in s.ALLOWED_HOSTS
    assert s.CSRF_TRUSTED_ORIGINS == ['https://seasonal-deck-organisms-sf.trycloudflare.com']
    assert s.SESSION_COOKIE_SECURE and s.URL_PUBLICA.endswith('trycloudflare.com') and s.TUNEL_RAPIDO


def test_boton_compartir_por_internet(client, settings, tmp_path):
    settings.CONFIG = dict(settings.CONFIG)  # la vista activa 2 pasos para todos en settings.CONFIG: que no pase a otras pruebas
    settings.CONFIG_FILE = tmp_path / 'config.json'
    settings.CONFIG_FILE.write_text(json.dumps({'PUERTO': 8000}), encoding='utf-8')
    settings.DATA_DIR = tmp_path
    client.force_login(User.objects.create_superuser('t@x.mx', 't@x.mx', 'Clave-de-prueba-123'))
    html = client.get('/admin/herramientas/otras-computadoras/').content.decode()
    assert 'Compartir por internet' in html
    client.post('/admin/herramientas/otras-computadoras/', {'accion': 'internet_activar'})
    guardado = json.loads(settings.CONFIG_FILE.read_text())
    assert guardado['COMPARTIR_EN_INTERNET'] is True
    assert guardado['DOS_PASOS_TODOS'] is True   # en internet, 2 pasos para todos
    client.post('/admin/herramientas/otras-computadoras/', {'accion': 'internet_apagar'})
    assert json.loads(settings.CONFIG_FILE.read_text())['COMPARTIR_EN_INTERNET'] is False


def test_pantalla_con_enlace_temporal(client, settings, monkeypatch):
    from prospectos.servicios import dos_pasos
    monkeypatch.setattr(dos_pasos, 'obligatoria', lambda u: False)  # aquí solo se prueba la pantalla
    settings.URL_PUBLICA = 'https://seasonal-deck-organisms-sf.trycloudflare.com'
    settings.TUNEL_RAPIDO = True
    client.force_login(User.objects.create_superuser('u@x.mx', 'u@x.mx', 'Clave-de-prueba-123'))
    html = client.get('/admin/herramientas/otras-computadoras/').content.decode()
    assert 'Compartido por internet' in html and 'Enlace temporal' in html
    assert 'Dejar de compartir por internet' in html
