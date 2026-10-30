"""Mi perfil y verificación en 2 pasos: el código se pide siempre, no se repite, se bloquea por intentos y la demo no queda abierta."""
import base64

import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command

from prospectos.models import Auditoria, Perfil
from prospectos.servicios import dos_pasos

CLAVE = 'Clave-de-prueba-123'
SECRETO_RFC = base64.b32encode(b'12345678901234567890').decode()


def jpeg(ancho=256, alto=256, relleno=200) -> bytes:
    sof = b'\xff\xc0\x00\x11\x08' + alto.to_bytes(2, 'big') + ancho.to_bytes(2, 'big') + b'\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01'
    return b'\xff\xd8' + sof + b'\x00' * relleno + b'\xff\xd9'


def data_url(datos: bytes, tipo='jpeg') -> str:
    return f'data:image/{tipo};base64,' + base64.b64encode(datos).decode()


@pytest.fixture(autouse=True)
def sin_bloqueos():
    from django.core.cache import cache
    cache.clear()  # los intentos fallidos viven en la caché y pasarían de una prueba a otra
    yield
    cache.clear()


@pytest.fixture
def obligatoria(settings):
    settings.CONFIG = {**settings.CONFIG, 'DOS_PASOS_ADMINS': True}


@pytest.fixture
def jefa(db):
    return User.objects.create_superuser('jefa@x.mx', 'jefa@x.mx', CLAVE, first_name='Laura')


def _entrar(client, usuario='jefa@x.mx', clave=CLAVE):
    return client.post('/admin/login/', {'username': usuario, 'password': clave, 'next': '/admin/'})


def _activar(perfil) -> list[str]:
    secreto = dos_pasos.nuevo_secreto()
    return dos_pasos.activar(perfil, secreto, dos_pasos.codigo(secreto, dos_pasos.contador_actual()))


# --------------------------------------------------------------------------- TOTP

def test_totp_coincide_con_el_rfc_6238():
    # RFC 6238, anexo B (SHA1): T=59 → 94287082; T=1111111109 → 07081804 (aquí, los últimos 6 dígitos)
    assert dos_pasos.codigo(SECRETO_RFC, 59 // 30) == '287082'
    assert dos_pasos.codigo(SECRETO_RFC, 1111111109 // 30) == '081804'


def test_ventana_de_30_segundos_y_no_se_repite():
    t = 1_000_000_000
    actual = dos_pasos.codigo(SECRETO_RFC, t // 30)
    assert dos_pasos.comprobar(SECRETO_RFC, actual, t=t) == t // 30
    assert dos_pasos.comprobar(SECRETO_RFC, actual[:3] + ' ' + actual[3:], t=t + 30)  # con espacio y 30 s después
    assert dos_pasos.comprobar(SECRETO_RFC, actual, t=t + 90) is None  # ya venció
    assert dos_pasos.comprobar(SECRETO_RFC, actual, ultimo=t // 30, t=t) is None  # ya se usó
    assert dos_pasos.comprobar(SECRETO_RFC, '12345', t=t) is None


def test_secreto_cifrado_y_codigos_solo_como_hash(jefa):
    p = Perfil.de(jefa)
    codigos = _activar(p)
    assert len(codigos) == 10 and all(len(c) == 9 for c in codigos)
    from django.db import connection
    with connection.cursor() as c:
        c.execute('SELECT dos_pasos_secreto, dos_pasos_codigos FROM prospectos_perfil WHERE id = %s', [p.pk])
        crudo_secreto, crudo_codigos = c.fetchone()
    p.refresh_from_db()
    assert p.dos_pasos_secreto not in crudo_secreto and codigos[0].replace('-', '') not in crudo_codigos


def test_codigo_de_recuperacion_sirve_una_vez(jefa):
    p = Perfil.de(jefa)
    codigos = _activar(p)
    assert dos_pasos.verificar(p, codigos[0].lower()) == 'recuperacion'
    assert dos_pasos.verificar(p, codigos[0]) is None
    assert len(p.dos_pasos_codigos) == 9


# --------------------------------------------------------------------------- entrada

def test_con_2_pasos_activa_se_pide_el_codigo_en_todo(client, jefa):
    p = Perfil.de(jefa)
    _activar(p)
    _entrar(client)
    r = client.get('/admin/prospectos/prospecto/')
    assert r.status_code == 302 and r['Location'].startswith('/admin/herramientas/verificar/')
    assert client.get('/admin/password_change/').status_code == 302  # ni cambiar la contraseña sin el código
    r = client.get('/admin/herramientas/avisos/contador/', HTTP_X_REQUESTED_WITH='fetch')
    assert r.status_code == 401
    p.refresh_from_db()
    r = client.post('/admin/herramientas/verificar/', {'codigo': dos_pasos.codigo(p.dos_pasos_secreto, dos_pasos.contador_actual() + 1),
                                                       'next': '/admin/prospectos/prospecto/'})
    assert r.status_code == 302 and r['Location'] == '/admin/prospectos/prospecto/'
    assert client.get('/admin/prospectos/prospecto/').status_code == 200
    assert Auditoria.objects.filter(accion='dos_pasos_entrada').exists()
    # al volver a entrar con contraseña, se pide otra vez
    client.post('/admin/logout/')
    _entrar(client)
    assert client.get('/admin/').status_code == 302


def test_la_redireccion_no_sale_del_programa(client, jefa):
    p = Perfil.de(jefa)
    _activar(p)
    _entrar(client)
    p.refresh_from_db()
    r = client.post('/admin/herramientas/verificar/', {'codigo': dos_pasos.codigo(p.dos_pasos_secreto, dos_pasos.contador_actual() + 1),
                                                       'next': 'https://malo.example.com/'})
    assert r['Location'] == '/admin/'


def test_cinco_codigos_equivocados_bloquean(client, jefa):
    _activar(Perfil.de(jefa))
    _entrar(client)
    for _ in range(5):
        r = client.post('/admin/herramientas/verificar/', {'codigo': '000000'})
    assert r['Location'].startswith('/admin/login/')
    r = _entrar(client)  # ni con la contraseña correcta, durante 15 minutos
    assert r.status_code == 302 and client.get('/admin/').status_code == 302
    assert Auditoria.objects.filter(accion='acceso_bloqueado').exists()


def test_administrador_debe_activarla(client, jefa, obligatoria):
    _entrar(client)
    r = client.get('/admin/')
    assert r['Location'] == '/admin/herramientas/perfil/dos-pasos/'
    assert client.get('/admin/password_change/').status_code == 200  # la contraseña temporal sí se puede cambiar
    html = client.get('/admin/herramientas/perfil/dos-pasos/').content.decode()
    assert '<svg' in html and 'Activar' in html
    secreto = client.session['dos_pasos_nuevo']
    r = client.post('/admin/herramientas/perfil/dos-pasos/', {'accion': 'activar', 'codigo': '000000'})
    assert not Perfil.de(jefa).dos_pasos_activo
    r = client.post('/admin/herramientas/perfil/dos-pasos/', {'accion': 'activar', 'codigo': dos_pasos.codigo(secreto, dos_pasos.contador_actual())})
    html = r.content.decode()
    assert Perfil.de(jefa).dos_pasos_activo and html.count('pf-lista-codigos') == 1
    assert client.get('/admin/').status_code == 200
    # no puede quitársela a sí misma
    p = Perfil.de(jefa)
    client.post('/admin/herramientas/perfil/dos-pasos/', {'accion': 'desactivar', 'clave': CLAVE,
                                                         'codigo': dos_pasos.codigo(p.dos_pasos_secreto, dos_pasos.contador_actual() + 1)})
    assert Perfil.de(jefa).dos_pasos_activo


def test_otro_administrador_la_quita_y_queda_en_la_bitacora(client, jefa):
    otro = User.objects.create_superuser('otro@x.mx', 'otro@x.mx', CLAVE)
    _activar(Perfil.de(otro))
    client.force_login(jefa)
    client.post('/admin/auth/user/', {'action': 'quitar_dos_pasos', '_selected_action': [otro.pk]})
    assert not Perfil.de(otro).dos_pasos_activo
    assert Auditoria.objects.filter(accion='dos_pasos_quitar').exists()


def test_promotor_puede_activarla_y_quitarla(client, promotor):
    promotor.set_password(CLAVE)
    promotor.save()
    client.force_login(promotor)
    assert client.get('/admin/').status_code == 200  # para ellos es opcional
    p = Perfil.de(promotor)
    _activar(p)
    p.refresh_from_db()
    client.post('/admin/herramientas/perfil/dos-pasos/', {'accion': 'desactivar', 'clave': CLAVE,
                                                         'codigo': dos_pasos.codigo(p.dos_pasos_secreto, dos_pasos.contador_actual() + 1)})
    assert not Perfil.de(promotor).dos_pasos_activo


# --------------------------------------------------------------------------- demostración

def test_cuentas_demo_no_entran_si_hay_un_administrador_real(client, obligatoria):
    demo = User.objects.create_superuser('admin@demo.local', 'admin@demo.local', CLAVE)
    _entrar(client, 'admin@demo.local')
    assert client.get('/admin/').status_code == 200  # sola, la demo funciona y no pide 2 pasos
    client.post('/admin/logout/')
    User.objects.create_superuser('real@udc.mx', 'real@udc.mx', CLAVE)
    _entrar(client, 'admin@demo.local')
    assert client.get('/admin/').status_code == 302
    assert demo.is_active


def test_demo_no_se_mezcla_con_datos_reales(jefa):
    with pytest.raises(CommandError, match='OTRA carpeta'):
        call_command('demo', familias=2)


def test_el_arranque_ya_no_ofrece_la_demo(monkeypatch, db):
    import lanzador
    llamados = []
    monkeypatch.setattr('django.core.management.call_command', lambda nombre, *a, **k: llamados.append(nombre))
    monkeypatch.setattr('builtins.input', lambda *a: pytest.fail('no debe preguntar'))
    lanzador._primera_vez()
    assert llamados == ['crear_admin']


# --------------------------------------------------------------------------- Mi perfil

def test_datos_apodo_y_firma(client, jefa, f_alumno, f_tutor, evento):
    from prospectos.servicios import kuali
    from .conftest import alumno, importar, tutor
    client.force_login(jefa)
    client.post('/admin/herramientas/perfil/', {'accion': 'datos', 'first_name': 'Laura', 'last_name': 'Hernández',
                                                'apodo': 'Lau<script>', 'telefono': '55 1234 5678', 'firma': 'Laura · Admisiones UDC'})
    p = Perfil.de(jefa)
    assert p.apodo == 'Lauscript' and p.telefono == '55 1234 5678'
    assert ', Lauscript<' in client.get('/admin/').content.decode()  # «Buenos días, Lauscript» (o tardes, o noches)
    client.post('/admin/herramientas/perfil/', {'accion': 'datos', 'telefono': '<b>'})
    assert Perfil.de(jefa).telefono == '55 1234 5678'  # no aceptó basura
    importar(f_alumno, alumno('a1', 'Valeria Quintero Salas', edad='17', tutor_correo=None, tutor_telefono=None))
    importar(f_tutor, tutor('t1', 'Valeria Quintero Salas', evento='EV1', tutor_nombre='Rosa Salas', minutos=60))
    from prospectos.models import Prospecto
    r = kuali.responder(jefa, 'Escribe un WhatsApp', {}, {'ficha': Prospecto.objects.get(fusionado_en__isnull=True).pk})
    assert 'Laura · Admisiones UDC' in r['texto']


def test_foto_se_valida_y_se_ve_en_el_avatar(client, jefa):
    client.force_login(jefa)
    url = '/admin/herramientas/perfil/'
    for malo in [data_url(b'<svg onload=alert(1)>', 'svg+xml'), data_url(b'\x89PNG....', 'png'), data_url(b'no es imagen'),
                 data_url(jpeg(4000, 4000)), data_url(jpeg(relleno=300 * 1024))]:
        client.post(url, {'accion': 'foto', 'foto': malo})
        assert not Perfil.de(jefa).foto, malo[:30]
    client.post(url, {'accion': 'foto', 'foto': data_url(jpeg())})
    p = Perfil.de(jefa)
    assert bytes(p.foto) == jpeg() and p.foto_version == 1
    r = client.get(f'/admin/herramientas/perfil/foto/{jefa.pk}/')
    assert r['Content-Type'] == 'image/jpeg' and r.content == jpeg()
    jefa.refresh_from_db()
    assert jefa.avatar_url == f'/admin/herramientas/perfil/foto/{jefa.pk}/?v=1'
    assert jefa.avatar_url in client.get('/admin/').content.decode()
    client.post(url, {'accion': 'quitar_foto'})
    assert client.get(f'/admin/herramientas/perfil/foto/{jefa.pk}/').status_code == 404


def test_foto_no_se_ve_sin_sesion(client, jefa):
    client.force_login(jefa)
    client.post('/admin/herramientas/perfil/', {'accion': 'foto', 'foto': data_url(jpeg())})
    client.logout()
    assert client.get(f'/admin/herramientas/perfil/foto/{jefa.pk}/').status_code == 302


def test_cambiar_contraseña_y_preferencias(client, jefa):
    client.force_login(jefa)
    url = '/admin/herramientas/perfil/'
    r = client.post(url, {'accion': 'clave', 'old_password': 'mala', 'new_password1': 'Otra-Clave-Larga-1', 'new_password2': 'Otra-Clave-Larga-1'})
    assert r.status_code == 200 and 'pd-error' in r.content.decode()
    client.post(url, {'accion': 'clave', 'old_password': CLAVE, 'new_password1': 'Otra-Clave-Larga-1', 'new_password2': 'Otra-Clave-Larga-1'})
    jefa.refresh_from_db()
    assert jefa.check_password('Otra-Clave-Larga-1')
    assert client.get('/admin/').status_code == 200  # la sesión sigue
    client.post(url, {'accion': 'preferencias', 'tipo': ['asignado']})
    p = Perfil.de(jefa)
    assert p.kuali_oculto and 'vencidas' in p.avisos_apagados
    assert 'data-oculto="1"' in client.get('/admin/').content.decode()
    client.post(url, {'accion': 'kuali', 'oculto': '0'}, HTTP_X_REQUESTED_WITH='fetch')
    assert not Perfil.de(jefa).kuali_oculto


def test_mi_perfil_en_el_menu(client, jefa):
    client.force_login(jefa)
    html = client.get('/admin/').content.decode()
    assert '/admin/herramientas/perfil/' in html and 'Mi perfil' in html


def test_comando_de_emergencia(jefa, capsys):
    _activar(Perfil.de(jefa))
    call_command('quitar_dos_pasos', 'JEFA@x.mx')
    assert not Perfil.de(jefa).dos_pasos_activo and 'Listo' in capsys.readouterr().out
    assert Auditoria.objects.filter(accion='dos_pasos_quitar').exists()
    with pytest.raises(CommandError):
        call_command('quitar_dos_pasos', 'nadie@x.mx')
