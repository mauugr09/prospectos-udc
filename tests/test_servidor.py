"""Un solo Prospectos para todos: servidor central con dirección pública, cliente que solo abre ese servidor
y un solo programador por base de datos."""
import pytest
from django.contrib.auth.models import User

from prospectos.programador import TURNO, VIGENCIA_TURNO, tomar_turno
from prospectos.servicios import publico


# --------------------------------------------------------------------------- dirección pública
@pytest.mark.parametrize('entrada, esperado', [
    ('https://prospectos.udcm.mx', 'https://prospectos.udcm.mx'),
    ('https://Prospectos.UDCM.mx/', 'https://prospectos.udcm.mx'),
    ('  https://prospectos.udcm.mx:8443 ', 'https://prospectos.udcm.mx:8443'),
    ('', None),
    (None, None),
])
def test_normaliza_la_direccion(entrada, esperado):
    assert publico.normalizar(entrada) == esperado


@pytest.mark.parametrize('mala', ['http://prospectos.udcm.mx', 'prospectos.udcm.mx', 'https://prospectos.udcm.mx/admin/',
                                  'https://', 'ftp://x.mx'])
def test_solo_https_y_solo_dominio(mala):
    with pytest.raises(publico.ErrorConfiguracion):
        publico.normalizar(mala)


def test_variables_de_entorno_mandan_sobre_config():
    cfg = {'URL_PUBLICA': 'https://de-config.mx'}
    assert publico.url_publica(cfg, {}) == 'https://de-config.mx'
    assert publico.url_publica(cfg, {'PROSPECTOS_URL_PUBLICA': 'https://de-entorno.mx'}) == 'https://de-entorno.mx'


def test_ajustes_de_seguridad_para_internet():
    a = publico.ajustes_django('https://prospectos.udcm.mx')
    assert a['ALLOWED_HOSTS'] == ['prospectos.udcm.mx']
    assert a['CSRF_TRUSTED_ORIGINS'] == ['https://prospectos.udcm.mx']
    assert a['SESSION_COOKIE_SECURE'] and a['CSRF_COOKIE_SECURE']
    assert a['SECURE_HSTS_SECONDS'] >= 30 * 24 * 3600


def test_proxy_confiable():
    assert publico.waitress_proxy(None) == {}
    w = publico.waitress_proxy('127.0.0.1')
    assert w['trusted_proxy'] == '127.0.0.1' and w['trusted_proxy_count'] == 1
    assert {'x-forwarded-for', 'x-forwarded-proto'} <= w['trusted_proxy_headers']
    assert w['clear_untrusted_proxy_headers'] is True


def test_base_de_datos_por_entorno():
    assert publico.bd_desde_entorno({}) == {}
    bd = publico.bd_desde_entorno({'PROSPECTOS_BD_MOTOR': 'mariadb', 'PROSPECTOS_BD_HOST': 'mariadb',
                                   'PROSPECTOS_BD_PUERTO': '3306', 'PROSPECTOS_BD_CLAVE': 's3creta'})
    assert bd == {'MOTOR': 'mariadb', 'HOST': 'mariadb', 'PUERTO': 3306, 'CLAVE': 's3creta'}


# --------------------------------------------------------------------------- un solo programador por base
def test_un_solo_programador_por_base():
    assert tomar_turno('a', ahora=1000)
    assert tomar_turno('a', ahora=1010)                         # renueva el suyo
    assert not tomar_turno('b', ahora=1020)                     # otro proceso espera
    assert tomar_turno('b', ahora=1010 + VIGENCIA_TURNO + 1)    # el primero dejó de renovar: toma el turno
    assert not tomar_turno('a', ahora=1010 + VIGENCIA_TURNO + 2)
    from prospectos.models import Configuracion
    assert Configuracion.obtener(TURNO)['id'] == 'b'


# --------------------------------------------------------------------------- pantallas
def test_otros_equipos_con_servidor_central(client, settings, monkeypatch):
    from prospectos.servicios import dos_pasos
    monkeypatch.setattr(dos_pasos, 'obligatoria', lambda u: False)  # aquí solo se prueba la pantalla
    settings.URL_PUBLICA = 'https://prospectos.udcm.mx'
    client.force_login(User.objects.create_superuser('c@x.mx', 'c@x.mx', 'Clave-de-prueba-123'))
    html = client.get('/admin/herramientas/otras-computadoras/').content.decode()
    assert 'Un solo Prospectos para todos' in html
    assert 'https://prospectos.udcm.mx/admin/' in html and 'data:image/svg+xml' in html
    assert 'Activar el acceso por red' not in html


def test_sin_conexion_segun_el_modo(client, settings):
    settings.URL_PUBLICA = 'https://prospectos.udcm.mx'
    assert 'internet' in client.get('/sin-conexion/').content.decode()
    settings.URL_PUBLICA = None
    assert 'Wi‑Fi de la oficina' in client.get('/sin-conexion/').content.decode()


def test_primer_admin_desde_entorno_debe_cambiar_su_clave(monkeypatch):
    from django.core.management import call_command

    from prospectos.models import Perfil
    monkeypatch.setenv('PROSPECTOS_ADMIN_CLAVE', 'Clave-Inicial-Del-Servidor-1')
    call_command('crear_admin', correo='jefa@udc.mx', clave_desde_entorno=True)
    u = User.objects.get(username='jefa@udc.mx')
    assert u.is_superuser and u.check_password('Clave-Inicial-Del-Servidor-1')
    assert Perfil.objects.get(usuario=u).debe_cambiar_clave


def test_primer_admin_rechaza_clave_debil(monkeypatch):
    from django.core.management import call_command
    from django.core.management.base import CommandError
    monkeypatch.setenv('PROSPECTOS_ADMIN_CLAVE', '123')
    with pytest.raises(CommandError):
        call_command('crear_admin', correo='otra@udc.mx', clave_desde_entorno=True)
    assert not User.objects.filter(username='otra@udc.mx').exists()


# --------------------------------------------------------------------------- «C · Conectarme» a un servidor central
@pytest.mark.parametrize('texto, esperado', [
    ('https://prospectos.udcm.mx', 'https://prospectos.udcm.mx/'),
    ('https://Prospectos.UDCM.mx/admin/', 'https://prospectos.udcm.mx/'),
    ('https://seasonal-deck-organisms-sf.trycloudflare.com/', 'https://seasonal-deck-organisms-sf.trycloudflare.com/'),
    ('https://10.20.1.15', None),          # IP: es la principal de la red local (certificado propio)
    ('https://pc-admisiones:8443', None),  # con puerto: principal de la red local
    ('10.20.1.15', None),
    ('prospectos.udcm.mx', None),          # sin https:// se trata como red local, como antes
])
def test_reconoce_un_servidor_central(texto, esperado):
    from prospectos.servicios import cliente
    assert cliente.servidor_publico(texto) == esperado


def test_conectarse_a_servidor_central_sin_codigo(tmp_path, monkeypatch):
    from prospectos.servicios import cliente
    llamadas = []
    monkeypatch.setattr(cliente, 'responde', lambda servidor, cert, tiempo=5: (llamadas.append((servidor, cert)), (True, ''))[1])
    dicho = []
    respuestas = iter(['https://prospectos.udcm.mx'])
    servidor = cliente.configurar(tmp_path, lambda *_: next(respuestas), dicho.append, buscar_fn=lambda: [])
    assert servidor == 'https://prospectos.udcm.mx/'
    assert llamadas == [('https://prospectos.udcm.mx/', None)]   # certificado HTTPS público, sin el propio
    conexion = cliente.leer(tmp_path)
    assert conexion['servidor'] == 'https://prospectos.udcm.mx/' and conexion['publico'] is True
    assert not (tmp_path / cliente.CERTIFICADO).exists() and not (tmp_path / 'config.json').exists()
    assert not any('Código' in d for d in dicho)


def test_abrir_servidor_central(tmp_path, monkeypatch):
    from prospectos.servicios import cliente
    vistos, abiertos = [], []
    monkeypatch.setattr(cliente, 'responde', lambda servidor, cert, tiempo=5: (vistos.append(cert), (True, ''))[1])
    assert cliente.abrir({'servidor': 'https://prospectos.udcm.mx/', 'publico': True}, tmp_path, lambda *_: None, abiertos.append)
    assert vistos == [None] and abiertos == ['https://prospectos.udcm.mx/admin/']


def test_en_internet_la_verificacion_en_2_pasos_es_para_todos(settings):
    from prospectos.servicios import dos_pasos
    u = User.objects.create_user('asesora@udc.mx', 'asesora@udc.mx', 'Clave-de-prueba-123', is_staff=True)
    settings.CONFIG = {**settings.CONFIG, 'DOS_PASOS_TODOS': False}
    settings.URL_PUBLICA = None
    assert not dos_pasos.obligatoria(u)
    settings.URL_PUBLICA = 'https://prospectos.udcm.mx'
    assert dos_pasos.obligatoria(u)
