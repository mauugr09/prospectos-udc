"""Lo que se agregó para el lanzamiento: Forms de la UDC, avisos flotantes, computadoras de confianza, disco y conexión de un clic."""
import json
import subprocess
import time

import pytest
from django.contrib.auth.models import User

from prospectos.models import DispositivoConfianza, Formulario, Perfil
from prospectos.servicios import disco, dos_pasos, instalador, red, semillas

CLAVE = 'Clave-de-prueba-123'


@pytest.fixture(autouse=True)
def sin_bloqueos():
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


# --------------------------------------------------------------------------- Forms de la UDC
def test_forms_de_la_udc_se_registran_una_vez(db):
    assert semillas.forms_predeterminados() == 2
    alumno = Formulario.objects.get(tipo='ALUMNO')
    assert alumno.google_form_id == '15yKpCaIUBX98tBvfdVcd7uqPXEppT6jfOjc9BSM2XgU' and 'viewform' in alumno.url_publica
    Formulario.objects.all().delete()
    assert semillas.forms_predeterminados() == 0  # si los quitaron, no vuelven


def test_no_se_agregan_si_ya_hay_forms(db, f_alumno):
    assert semillas.forms_predeterminados() == 0


def test_tipo_se_corrige_con_el_titulo(db):
    assert semillas.tipo_por_titulo('ENCUESTA PARA PADRES DE FAMILIA') == 'TUTOR'
    assert semillas.tipo_por_titulo('CUESTIONARIO VOCACIONAL') == 'ALUMNO'
    assert semillas.tipo_por_titulo('') is None


# --------------------------------------------------------------------------- avisos
def test_contador_trae_los_recientes_para_la_ventanita(client):
    from prospectos.servicios import avisos
    u = User.objects.create_superuser('a@x.mx', 'a@x.mx', CLAVE)
    client.force_login(u)
    avisos.avisar(u, 'asignado', 'k1', 'Te asignaron 3 aspirantes', 'De Tultepec', '/admin/')
    j = client.get('/admin/herramientas/avisos/contador/').json()
    assert j['sin_leer'] == 1 and j['recientes'][0]['titulo'] == 'Te asignaron 3 aspirantes' and j['recientes'][0]['marca'] > 0
    html = client.get('/admin/').content.decode()
    assert 'data-sonido="1"' in html and 'data-usuario=' in html
    client.post('/admin/herramientas/perfil/', {'accion': 'preferencias', 'kuali_visible': '1'})
    assert not Perfil.de(u).avisos_sonido and 'data-sonido="0"' in client.get('/admin/').content.decode()


# --------------------------------------------------------------------------- 2 pasos solo con sospecha
def _con_2_pasos(u):
    p = Perfil.de(u)
    s = dos_pasos.nuevo_secreto()
    dos_pasos.activar(p, s, dos_pasos.codigo(s, dos_pasos.contador_actual()))
    p.refresh_from_db()
    return p


def _entrar(client, ip='192.168.1.20'):
    return client.post('/admin/login/', {'username': 'jefa@x.mx', 'password': CLAVE}, REMOTE_ADDR=ip)


def _codigo(client, p, confiar=True, ip='192.168.1.20'):
    p.refresh_from_db()
    datos = {'codigo': dos_pasos.codigo(p.dos_pasos_secreto, dos_pasos.contador_actual() + 1)}
    if confiar:
        datos['confiar'] = '1'
    return client.post('/admin/herramientas/verificar/', datos, REMOTE_ADDR=ip)


def test_computadora_de_confianza_no_pide_el_codigo(client):
    u = User.objects.create_superuser('jefa@x.mx', 'jefa@x.mx', CLAVE)
    p = _con_2_pasos(u)
    _entrar(client)
    assert client.get('/admin/', REMOTE_ADDR='192.168.1.20').status_code == 302  # computadora nueva: pide el código
    r = _codigo(client, p)
    assert dos_pasos.COOKIE in r.cookies and r.cookies[dos_pasos.COOKIE]['httponly']
    d = DispositivoConfianza.objects.get()
    assert d.token_hash != r.cookies[dos_pasos.COOKIE].value and d.red == '192.168.1.0/24'  # solo el hash en la base
    client.post('/admin/logout/')
    _entrar(client)
    assert client.get('/admin/', REMOTE_ADDR='192.168.1.20').status_code == 200  # la misma computadora: ya no pide


def test_sospecha_vuelve_a_pedir_el_codigo(client):
    u = User.objects.create_superuser('jefa@x.mx', 'jefa@x.mx', CLAVE)
    p = _con_2_pasos(u)
    _entrar(client)
    _codigo(client, p)
    client.post('/admin/logout/')
    _entrar(client, ip='10.20.5.9')  # otra red
    r = client.get('/admin/', REMOTE_ADDR='10.20.5.9')
    assert r.status_code == 302 and 'verificar' in r['Location']
    assert 'red distinta' in client.get(r['Location'], REMOTE_ADDR='10.20.5.9').content.decode()
    client.post('/admin/logout/')
    for _ in range(3):  # contraseñas equivocadas antes de entrar
        client.post('/admin/login/', {'username': 'jefa@x.mx', 'password': 'mala-mala-mala'}, REMOTE_ADDR='192.168.1.20')
    _entrar(client)
    assert client.get('/admin/', REMOTE_ADDR='192.168.1.20').status_code == 302


def test_contraseña_cambiada_y_olvidar(client):
    u = User.objects.create_superuser('jefa@x.mx', 'jefa@x.mx', CLAVE)
    p = _con_2_pasos(u)
    _entrar(client)
    _codigo(client, p)
    u.set_password('Otra-Clave-Larga-99')
    u.save()
    client.post('/admin/logout/')
    client.post('/admin/login/', {'username': 'jefa@x.mx', 'password': 'Otra-Clave-Larga-99'}, REMOTE_ADDR='192.168.1.20')
    assert client.get('/admin/', REMOTE_ADDR='192.168.1.20').status_code == 302
    Perfil.objects.filter(pk=p.pk).update(dos_pasos_ultimo=0)  # el código anterior ya se usó: otro intervalo
    _codigo(client, p)
    assert 'Olvidar' in client.get('/admin/herramientas/perfil/', REMOTE_ADDR='192.168.1.20').content.decode()
    client.post('/admin/herramientas/perfil/', {'accion': 'olvidar'}, REMOTE_ADDR='192.168.1.20')
    assert not DispositivoConfianza.objects.exists()


def test_sin_marcar_confiar_se_pide_siempre(client):
    u = User.objects.create_superuser('jefa@x.mx', 'jefa@x.mx', CLAVE)
    p = _con_2_pasos(u)
    _entrar(client)
    r = _codigo(client, p, confiar=False)
    assert dos_pasos.COOKIE not in r.cookies and not DispositivoConfianza.objects.exists()


def test_quitar_2_pasos_olvida_las_computadoras(client):
    u = User.objects.create_superuser('jefa@x.mx', 'jefa@x.mx', CLAVE)
    p = _con_2_pasos(u)
    _entrar(client)
    _codigo(client, p)
    dos_pasos.desactivar(Perfil.de(u))
    assert not DispositivoConfianza.objects.exists()


def test_red_de():
    assert dos_pasos.red_de('192.168.1.77') == '192.168.1.0/24'
    assert dos_pasos.red_de('127.0.0.1') == 'local' and dos_pasos.red_de('basura') == ''


# --------------------------------------------------------------------------- disco cifrado
def test_estado_del_disco_nunca_afirma_sin_saber(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(disco, 'os', SimpleNamespace(name='nt'))

    class R:
        stdout = '1\n'
    monkeypatch.setattr(disco.subprocess, 'run', lambda *a, **k: R())
    assert disco.estado(tmp_path, refrescar=True)['estado'] == 'si'
    R.stdout = '2'
    assert disco.estado(tmp_path, refrescar=True)['estado'] == 'no'
    R.stdout = 'x'
    assert disco.estado(tmp_path, refrescar=True)['estado'] == 'desconocido'

    def falla(*a, **k):
        raise OSError('sin powershell')
    monkeypatch.setattr(disco.subprocess, 'run', falla)
    assert disco.estado(tmp_path, refrescar=True)['estado'] == 'desconocido'


def test_pantalla_de_proteccion_muestra_el_disco(client):
    client.force_login(User.objects.create_superuser('r@x.mx', 'r@x.mx', CLAVE))
    html = client.get('/admin/herramientas/proteccion/').content.decode()
    assert 'Disco cifrado' in html and 'id="disco"' in html


# --------------------------------------------------------------------------- conexión de un clic
def test_instalador_lleva_la_huella_completa(tmp_path):
    red.asegurar_certificados(tmp_path)
    ca = tmp_path / 'red' / 'ca.crt'
    t = instalador.generar(['https://10.20.1.15:8443/', 'https://192.168.1.20:8443/'], ca, red.codigo_ca(tmp_path))
    assert t.isascii() and t.startswith('@echo off\r\n') and '#POWERSHELL#' in t
    assert instalador.huella_completa(ca) in t and len(instalador.huella_completa(ca)) == 64
    assert "'https://10.20.1.15:8443/', 'https://192.168.1.20:8443/'" in t
    with pytest.raises(ValueError):
        instalador.generar(["https://x'; Remove-Item C:\\ -Recurse; '"], ca, '')
    with pytest.raises(ValueError):
        instalador.generar([], ca, '')


def test_descarga_solo_para_administradores_y_con_red(client, settings, tmp_path):
    settings.DATA_DIR, settings.EN_RED = tmp_path, True
    settings.CONFIG_FILE = tmp_path / 'config.json'
    settings.CONFIG_FILE.write_text(json.dumps({'EN_RED': True, 'NOMBRES_RED': ['10.20.1.15']}))
    settings.CONFIG = {**settings.CONFIG, 'NOMBRES_RED': ['10.20.1.15']}
    red.asegurar_certificados(tmp_path)
    u = User.objects.create_user('n@x.mx', 'n@x.mx', CLAVE, is_staff=True)
    client.force_login(u)
    assert client.post('/admin/herramientas/otras-computadoras/', {'accion': 'instalador'}).status_code == 403
    client.force_login(User.objects.create_superuser('r@x.mx', 'r@x.mx', CLAVE))
    r = client.post('/admin/herramientas/otras-computadoras/', {'accion': 'instalador'})
    assert r['Content-Disposition'] == 'attachment; filename="Conectar a Prospectos.cmd"'
    assert b'https://10.20.1.15:8443/' in r.content


@pytest.mark.django_db(transaction=True)
def test_instalador_con_powershell_real(tmp_path, monkeypatch, settings):
    """Si hay PowerShell en esta computadora, se prueba el script de verdad contra un servidor HTTPS."""
    import shutil
    import threading
    pwsh = shutil.which('pwsh') or shutil.which('powershell') or ('/tmp/claude-0/pwsh/pwsh' if __import__('os').path.exists('/tmp/claude-0/pwsh/pwsh') else None)
    if not pwsh:
        pytest.skip('sin PowerShell')
    from config.wsgi import application
    monkeypatch.setattr(red, 'nombres_servidor', lambda *a: ['localhost', '127.0.0.1'])
    settings.EN_RED, settings.DATA_DIR = True, tmp_path
    srv = red.servidor_https(application, tmp_path, {'PUERTO_RED': 18446}, hilos=2)
    srv.prepare()
    threading.Thread(target=srv.serve, daemon=True).start()
    try:
        t = instalador.generar(['https://127.0.0.1:18446/'], tmp_path / 'red' / 'ca.crt', red.codigo_ca(tmp_path))
        ps = tmp_path / 'c.ps1'
        ps.write_text(t[t.index('#POWERSHELL#') + 12:])
        entorno = {k: v for k, v in __import__('os').environ.items() if 'proxy' not in k.lower()}
        r = subprocess.run([pwsh, '-NoProfile', '-File', str(ps)], capture_output=True, text=True, timeout=120,
                           env={**entorno, 'PROSPECTOS_SIN_INSTALAR': '1'})
        assert r.returncode == 0 and 'Certificado comprobado' in r.stdout, r.stdout + r.stderr
        ps.write_text(t[t.index('#POWERSHELL#') + 12:].replace("$huella = '", "$huella = '00", 1))
        r = subprocess.run([pwsh, '-NoProfile', '-File', str(ps)], capture_output=True, text=True, timeout=120,
                           env={**entorno, 'PROSPECTOS_SIN_INSTALAR': '1'})
        assert r.returncode == 3 and 'ALTO' in r.stdout
    finally:
        srv.stop()
        time.sleep(0.2)


# --------------------------------------------------------------------------- escudos
def test_escudos_en_el_acceso_y_en_el_menu(client):
    html = client.get('/admin/login/').content.decode()
    assert 'escudo-aguila' in html and 'escudo-toro' in html and 'Universidad de' in html and 'Tultepec' in html
    client.force_login(User.objects.create_superuser('r@x.mx', 'r@x.mx', CLAVE))
    html = client.get('/admin/').content.decode()
    assert 'escudos.svg' in html and 'escudos-oscuro.svg' in html
