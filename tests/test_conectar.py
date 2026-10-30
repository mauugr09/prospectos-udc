"""Varias computadoras: una principal con los datos y las demás conectadas (mismos datos, usuarios y perfiles)."""
import json
import threading

import pytest
from cryptography import x509
from django.contrib.auth.models import User

from prospectos.servicios import arranque, cliente, dos_pasos, red

CLAVE = 'Clave-de-prueba-123'


@pytest.fixture
def principal(tmp_path, monkeypatch, settings):
    """Un servidor HTTPS real, como el de la computadora principal."""
    monkeypatch.setattr(red, 'nombres_servidor', lambda *a: [*(a[0] if a else []), 'localhost', '127.0.0.1'])
    from config.wsgi import application
    carpeta = tmp_path / 'principal'
    settings.EN_RED, settings.DATA_DIR = True, carpeta
    srv = red.servidor_https(application, carpeta, {'PUERTO_RED': 18444}, hilos=2)
    srv.prepare()
    threading.Thread(target=srv.serve, daemon=True).start()
    yield carpeta
    srv.stop()


def _respuestas(*textos):
    pila = list(textos)
    return lambda *_: pila.pop(0)


@pytest.mark.django_db(transaction=True)
def test_conectar_compara_el_codigo_e_instala(principal, tmp_path, monkeypatch):
    instalados = []
    monkeypatch.setattr(cliente, 'instalar_certificado', lambda ruta: (instalados.append(ruta), (True, ''))[1])
    dicho = []
    carpeta = tmp_path / 'conectada'
    servidor = cliente.configurar(carpeta, _respuestas('https://127.0.0.1:18444/admin/', 's'), dicho.append, buscar_fn=lambda: [])
    assert servidor == 'https://127.0.0.1:18444/'
    assert red.codigo_ca(principal) in '\n'.join(dicho)  # el mismo código que muestra la principal
    assert cliente.leer(carpeta)['codigo'] == red.codigo_ca(principal)
    assert instalados and not (carpeta / 'config.json').exists()  # no guarda datos propios
    assert cliente.responde(servidor, carpeta / cliente.CERTIFICADO) == (True, '')
    abiertos = []
    assert cliente.abrir(cliente.leer(carpeta), carpeta, decir=lambda *_: None, abrir_navegador=abiertos.append)
    assert abiertos == ['https://127.0.0.1:18444/admin/']


@pytest.mark.django_db(transaction=True)
def test_si_el_codigo_no_coincide_no_se_conecta(principal, tmp_path, monkeypatch):
    monkeypatch.setattr(cliente, 'instalar_certificado', lambda ruta: pytest.fail('no debe instalar'))
    carpeta = tmp_path / 'conectada'
    assert cliente.configurar(carpeta, _respuestas('127.0.0.1:18444', 'n'), lambda *_: None, buscar_fn=lambda: []) is None
    assert not cliente.leer(carpeta) and not (carpeta / cliente.CERTIFICADO).exists()


@pytest.mark.django_db(transaction=True)
def test_otro_certificado_se_detecta(principal, tmp_path):
    """Si alguien se hace pasar por la principal (otra autoridad), la computadora conectada no entra."""
    carpeta = tmp_path / 'conectada'
    otra = tmp_path / 'impostor'
    red.asegurar_certificados(otra)
    cliente.guardar(carpeta, 'https://127.0.0.1:18444/', (otra / 'red' / 'ca.crt').read_bytes())
    ok, motivo = cliente.responde('https://127.0.0.1:18444/', carpeta / cliente.CERTIFICADO)
    assert not ok and 'certificado' in motivo


def test_principal_apagada_lo_explica(tmp_path):
    dicho = []
    carpeta = tmp_path / 'c'
    red.asegurar_certificados(tmp_path / 'p')
    cliente.guardar(carpeta, 'https://127.0.0.1:18999/', (tmp_path / 'p' / 'red' / 'ca.crt').read_bytes())
    assert not cliente.abrir(cliente.leer(carpeta), carpeta, decir=dicho.append, intentos=2, espera=0)
    texto = '\n'.join(dicho)
    assert 'encendida' in texto and 'VPN' in texto


def test_direcciones_validas():
    assert cliente.normalizar_servidor('10.20.1.15') == 'https://10.20.1.15:8443/'
    assert cliente.normalizar_servidor(' https://PC-Admisiones:9443/admin/ ') == 'https://pc-admisiones:9443/'
    for malo in ['', 'a b', 'http://x:99999/', '..', 'x;rm -rf']:
        assert cliente.normalizar_servidor(malo) is None, malo
    assert red.normalizar_nombre('https://10.20.1.15:8443/') == '10.20.1.15'
    assert red.normalizar_nombre('Prospectos.UDC.local') == 'prospectos.udc.local'
    assert red.normalizar_nombre('<script>') is None


def test_direccion_fija_en_el_certificado(tmp_path, monkeypatch):
    monkeypatch.setattr(red, 'ips_locales', lambda: ['192.168.1.20'])
    _, crt, _ = red.asegurar_certificados(tmp_path, ['10.20.1.15', 'prospectos.udc.local'])
    san = x509.load_pem_x509_certificate(crt.read_bytes()).extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert 'prospectos.udc.local' in san.get_values_for_type(x509.DNSName)
    assert '10.20.1.15' in [str(i) for i in san.get_values_for_type(x509.IPAddress)]
    assert red.direcciones({'NOMBRES_RED': ['10.20.1.15']})[0] == 'https://10.20.1.15:8443/'


def test_carpeta_principal_no_se_vuelve_conectada(tmp_path, monkeypatch, capsys):
    import lanzador
    monkeypatch.setattr(cliente, 'carpeta_datos', lambda: tmp_path)
    (tmp_path / 'config.json').write_text('{}')
    monkeypatch.setattr('sys.argv', ['Prospectos.exe'])
    assert lanzador._modo_conectado() is False  # principal: sigue normal
    monkeypatch.setattr('sys.argv', ['Prospectos.exe', 'conectar'])
    assert lanzador._modo_conectado() is True and 'PRINCIPAL' in capsys.readouterr().out
    assert not cliente.leer(tmp_path)


def test_pantalla_direccion_fija_y_2_pasos_para_todos(client, settings, tmp_path, promotor):
    settings.DATA_DIR = tmp_path
    settings.CONFIG_FILE = tmp_path / 'config.json'
    settings.CONFIG_FILE.write_text(json.dumps({'PUERTO': 8000}), encoding='utf-8')
    settings.CONFIG = {**settings.CONFIG}
    root = User.objects.create_superuser('red@x.mx', 'red@x.mx', CLAVE)
    client.force_login(root)
    url = '/admin/herramientas/otras-computadoras/'
    html = client.get(url).content.decode()
    assert 'Otro plantel o VPN' in html and 'No hay nada que sincronizar' in html
    client.post(url, {'accion': 'direccion', 'direccion': 'rm -rf /'})
    assert 'NOMBRES_RED' not in json.loads(settings.CONFIG_FILE.read_text())
    client.post(url, {'accion': 'direccion', 'direccion': 'https://10.20.1.15:8443/'})
    assert json.loads(settings.CONFIG_FILE.read_text())['NOMBRES_RED'] == ['10.20.1.15']
    assert not dos_pasos.obligatoria(promotor)
    client.post(url, {'accion': 'dos_pasos_todos', 'valor': '1'})
    assert json.loads(settings.CONFIG_FILE.read_text())['DOS_PASOS_TODOS'] is True and dos_pasos.obligatoria(promotor)
    demo = User.objects.create_user('p@demo.local', 'p@demo.local', CLAVE, is_staff=True)
    assert not dos_pasos.obligatoria(demo)


def test_paso_usar_desde_otras_computadoras(client, settings, tmp_path):
    root = User.objects.create_superuser('red@x.mx', 'red@x.mx', CLAVE)
    client.force_login(root)
    settings.EN_RED = False
    assert 'Usar desde otras computadoras' in client.get('/admin/').content.decode()
    client.post('/admin/herramientas/primeros-pasos/', {'accion': 'solo_esta_pc'})
    from prospectos.views import primeros_pasos
    assert next(p for p in primeros_pasos() if p['titulo'] == 'Usar desde otras computadoras')['hecho']


def test_abrir_al_iniciar_sesion(tmp_path, monkeypatch):
    destino = tmp_path / 'Startup' / 'x'
    monkeypatch.setattr(arranque, '_ruta', lambda: destino)
    assert not arranque.activo()
    arranque.activar('/Aplicaciones/Prospectos & Cía/Prospectos')
    assert arranque.activo() and '&amp;' in destino.read_text() or 'Prospectos' in destino.read_text()
    arranque.desactivar()
    assert not arranque.activo()


def test_la_principal_se_encuentra_sola_en_la_red(tmp_path):
    red.asegurar_certificados(tmp_path)
    sock = red.responder_descubrimiento({'PUERTO_RED': 18444}, tmp_path, puerto_udp=18445)
    try:
        encontradas = cliente.buscar(tiempo=1, destinos=('127.0.0.1',), puerto=18445)
    finally:
        sock.close()
    assert encontradas == [{'servidor': 'https://127.0.0.1:18444/', 'equipo': red.nombre_equipo(), 'codigo': red.codigo_ca(tmp_path)}]


@pytest.mark.django_db(transaction=True)
def test_conectar_eligiendo_la_encontrada(principal, tmp_path, monkeypatch):
    monkeypatch.setattr(cliente, 'instalar_certificado', lambda ruta: (True, ''))
    carpeta = tmp_path / 'conectada'
    encontrada = [{'servidor': 'https://127.0.0.1:18444/', 'equipo': 'PC-ADMISIONES', 'codigo': 'X'}]
    dicho = []
    assert cliente.configurar(carpeta, _respuestas('', 's'), dicho.append, buscar_fn=lambda: encontrada) == 'https://127.0.0.1:18444/'
    assert 'PC-ADMISIONES' in '\n'.join(dicho) and cliente.leer(carpeta)


def test_sin_principal_en_la_red_pide_la_direccion(tmp_path):
    dicho = []
    assert cliente.configurar(tmp_path, _respuestas(''), dicho.append, buscar_fn=lambda: []) is None
    assert any('VPN' in d for d in dicho)
