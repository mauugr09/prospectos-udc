"""Protección: separar uniones, copia externa cifrada, respaldo antes de actualizar, bloqueo de acceso e inactividad."""
import gzip
import time

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache

from prospectos.models import Auditoria, Configuracion, PosibleCoincidencia, Prospecto, Respaldo
from prospectos.servicios import familias, respaldos, uniones
from prospectos.servicios.inteligencia import fusionar

from .conftest import alumno, importar, tutor

CLAVE = 'Clave-de-prueba-123'


@pytest.fixture(autouse=True)
def _limpia_cache():
    cache.clear()
    yield
    cache.clear()


def _admin(client=None):
    u = User.objects.create_superuser('jefa@x.mx', 'jefa@x.mx', CLAVE)
    if client:
        client.force_login(u)
    return u


def _pareja(f_alumno, f_tutor):
    importar(f_alumno, alumno('a1', 'Sofía Torres Vega', edad='16', tutor_correo=None, tutor_telefono=None))
    importar(f_tutor, tutor('t1', 'Otro Niño Distinto', evento=None, tutor_correo='mama@x.mx', tutor_telefono=None,
                            tutor_nombre='Raúl Torres', minutos=60 * 24 * 10))
    a = Prospecto.objects.get(tiene_alumno=True, tiene_tutor=False)
    f = Prospecto.objects.get(tiene_tutor=True, tiene_alumno=False)
    return a, f


# --------------------------------------------------------------------------- separar

def test_separar_regresa_todo_y_no_se_vuelven_a_unir(f_alumno, f_tutor, evento):
    a, f = _pareja(f_alumno, f_tutor)
    jefa = _admin()
    fusionar(a, f, jefa)
    a.refresh_from_db()
    assert a.tiene_tutor and a.consentimiento and a.tutor_correo == 'mama@x.mx'  # el permiso venía de la familia
    reg = Auditoria.objects.get(accion='fusionar')
    assert reg.detalle['absorbido_id'] == f.pk and reg.detalle['respuestas']
    assert [u['sale'] for u in uniones.recientes()] == [Prospecto.objects.get(pk=f.pk)]

    queda, sale = uniones.separar(Prospecto.objects.get(pk=f.pk), jefa)
    assert queda.pk == a.pk and sale.pk == f.pk and sale.fusionado_en_id is None
    assert queda.tiene_alumno and not queda.tiene_tutor
    assert not queda.consentimiento and queda.tutor_correo in (None, '')  # ya no tiene el permiso ni el correo de la otra familia
    assert sale.tiene_tutor and not sale.tiene_alumno and sale.tutor_correo == 'mama@x.mx'
    assert Auditoria.objects.filter(accion='separar').exists()
    assert uniones.recientes() == []
    # «Volver a buscar» no los vuelve a proponer ni a unir
    assert f.pk in familias.descartados(queda)
    familias.buscar_para_todos()
    assert Prospecto.objects.get(pk=f.pk).fusionado_en_id is None
    assert not familias.pendientes().exists()


def test_union_vieja_sin_registro_se_separa_por_tipo(f_alumno, f_tutor, evento):
    a, f = _pareja(f_alumno, f_tutor)
    fusionar(a, f)
    reg = Auditoria.objects.get(accion='fusionar')
    Auditoria.objects.filter(pk=reg.pk).update(detalle={'absorbido_id': f.pk})
    queda, sale = uniones.separar(Prospecto.objects.get(pk=f.pk))
    assert queda.tiene_alumno and not queda.tiene_tutor and sale.tiene_tutor and not sale.tiene_alumno


def test_no_separa_lo_que_no_esta_unido(f_alumno, f_tutor, evento):
    a, f = _pareja(f_alumno, f_tutor)
    with pytest.raises(uniones.NoSeparable):
        uniones.separar(f)


def test_boton_separar_en_la_ficha_y_en_proteccion(client, f_alumno, f_tutor, evento):
    a, f = _pareja(f_alumno, f_tutor)
    _admin(client)
    fusionar(a, f)
    html = client.get(f'/admin/prospectos/prospecto/{a.pk}/change/').content.decode()
    assert 'No es la misma persona: separar' in html
    html = client.get('/admin/herramientas/proteccion/').content.decode()
    assert 'Uniones de los últimos 90 días' in html and 'Sofía Torres Vega' in html
    r = client.post(f'/admin/herramientas/separar/{f.pk}/', {'volver': f'/admin/prospectos/prospecto/{a.pk}/change/'})
    assert r.status_code == 302 and Prospecto.objects.get(pk=f.pk).fusionado_en_id is None


def test_separar_requiere_permiso(client, f_alumno, f_tutor, evento, promotor):
    a, f = _pareja(f_alumno, f_tutor)
    fusionar(a, f)
    client.force_login(promotor)
    assert client.post(f'/admin/herramientas/separar/{f.pk}/').status_code == 403
    assert client.get('/admin/herramientas/proteccion/').status_code == 403


# --------------------------------------------------------------------------- copia externa

@pytest.mark.django_db(transaction=True)
def test_copia_externa_cifrada_y_restaurable(tmp_path, settings):
    usb = tmp_path / 'usb'
    usb.mkdir()
    Configuracion.guardar('respaldo.copia_carpeta', str(usb))
    r = respaldos.crear()
    assert r.estado == 'ok'
    nombre = respaldos.copiar_externo(r.archivo)
    copia = usb / nombre
    assert copia.is_file() and nombre.endswith('.cifrado')
    with pytest.raises(OSError):
        gzip.decompress(copia.read_bytes())  # no es legible sin la llave
    assert not respaldos.copia_pendiente() and respaldos.estado_copia()['ok']
    fuera = tmp_path / 'recuperado'
    fuera.mkdir()
    gz = respaldos.descifrar_copia(copia, fuera)
    assert gz.read_bytes() == (respaldos.directorio() / r.archivo).read_bytes()


def test_copia_externa_rechaza_carpetas_inutiles(tmp_path, settings):
    with pytest.raises(respaldos.ErrorRespaldo, match='ruta completa'):
        respaldos.probar_carpeta(type(tmp_path)('relativa'))
    with pytest.raises(respaldos.ErrorRespaldo, match='No encuentro'):
        respaldos.probar_carpeta(tmp_path / 'no-existe')
    with pytest.raises(respaldos.ErrorRespaldo, match='dentro de los datos'):
        respaldos.probar_carpeta(respaldos.directorio())


@pytest.mark.django_db(transaction=True)
def test_memoria_desconectada_queda_pendiente(tmp_path):
    usb = tmp_path / 'usb'
    Configuracion.guardar('respaldo.copia_carpeta', str(usb))  # no existe: «memoria no conectada»
    r = respaldos.crear()
    with pytest.raises(respaldos.ErrorRespaldo):
        respaldos.copiar_externo(r.archivo)
    assert respaldos.copia_pendiente() and respaldos.estado_copia()['ok'] is False
    usb.mkdir()
    assert respaldos.copiar_externo() and not respaldos.copia_pendiente()


@pytest.mark.django_db(transaction=True)
def test_pantalla_proteccion_configura_y_descarga_llave(client, tmp_path):
    jefa = _admin(client)
    usb = tmp_path / 'usb'
    usb.mkdir()
    respaldos.crear()
    client.post('/admin/herramientas/proteccion/', {'accion': 'carpeta', 'carpeta': str(usb)})
    assert list(usb.glob('*.cifrado'))
    r = client.post('/admin/herramientas/proteccion/', {'accion': 'llave', 'clave': 'mala'})
    assert r.status_code == 302 and not Auditoria.objects.filter(accion='descargar_llave').exists()
    r = client.post('/admin/herramientas/proteccion/', {'accion': 'llave', 'clave': CLAVE})
    assert r['Content-Disposition'].endswith('"config.json"') and b'CLAVE_CIFRADO' in r.content
    assert Auditoria.objects.filter(accion='descargar_llave', usuario=jefa).exists()


# --------------------------------------------------------------------------- respaldo antes de actualizar

@pytest.mark.django_db(transaction=True)
def test_preparar_respalda_si_hay_migraciones_pendientes(monkeypatch):
    from io import StringIO

    from django.db.migrations.executor import MigrationExecutor

    from prospectos.management.commands import preparar
    monkeypatch.setattr(MigrationExecutor, 'migration_plan', lambda self, objetivos: ['cambio'])
    salida = StringIO()
    preparar._respaldar_antes_de_actualizar(salida)
    assert 'Copia previa: prospectos-antes-de-actualizar-' in salida.getvalue()
    assert any(f.name.startswith('prospectos-antes-de-actualizar-') for f in respaldos.archivos())


def test_preparar_no_respalda_sin_cambios():
    from io import StringIO

    from prospectos.management.commands import preparar
    salida = StringIO()
    preparar._respaldar_antes_de_actualizar(salida)
    assert salida.getvalue() == ''


# --------------------------------------------------------------------------- acceso

def test_bloqueo_tras_cinco_intentos(client):
    _admin()
    for _ in range(5):
        client.post('/admin/login/', {'username': 'jefa@x.mx', 'password': 'mal'})
    r = client.post('/admin/login/', {'username': 'jefa@x.mx', 'password': CLAVE}, follow=True)
    assert 'Demasiados intentos' in r.content.decode()
    assert '_auth_user_id' not in client.session
    assert Auditoria.objects.filter(accion='acceso_bloqueado').count() == 1
    cache.clear()  # pasan los 15 minutos
    client.post('/admin/login/', {'username': 'jefa@x.mx', 'password': CLAVE})
    assert '_auth_user_id' in client.session


def test_inactividad_cierra_la_sesion(client, settings):
    _admin(client)
    assert client.get('/admin/').status_code == 200
    s = client.session
    s['ultima_actividad'] = time.time() - 31 * 60
    s.save()
    assert client.get('/admin/herramientas/avisos/contador/').status_code == 401
    assert '_auth_user_id' not in client.session


def test_la_campanita_no_cuenta_como_uso(client):
    _admin(client)
    client.get('/admin/')
    s = client.session
    s['ultima_actividad'] = antes = time.time() - 10 * 60
    s.save()
    client.get('/admin/herramientas/avisos/contador/')
    assert client.session['ultima_actividad'] == antes
    client.get('/admin/')
    r = client.get('/admin/')
    assert r.status_code == 200 and client.session['ultima_actividad'] > antes


def test_inactividad_redirige_al_acceso(client):
    _admin(client)
    client.get('/admin/')
    s = client.session
    s['ultima_actividad'] = time.time() - 3600
    s.save()
    r = client.get('/admin/herramientas/familias/')
    assert r.status_code == 302 and r.url.startswith('/admin/login/')
