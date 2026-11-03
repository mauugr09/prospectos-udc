import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from prospectos.models import Auditoria, PosibleCoincidencia, Prospecto
from prospectos.vistas_prospectos import duplicados_pendientes

from .conftest import alumno, importar, tutor, usuario


@pytest.fixture
def datos(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1'), alumno('a2', 'Menor Sin Tutor Ruiz', edad='15'))
    importar(f_tutor, tutor('t1'))
    return Prospecto.objects.get(nombre_aspirante='Ana Sofía López García')


@pytest.fixture
def jefe(client):
    u = User.objects.create_superuser('jefe@x.mx', 'jefe@x.mx', 'Clave-larga-2026!')
    client.force_login(u)
    return client


def _dos(nombre_a='Luis Pérez Soto', nombre_b='Luis Perez Soto'):
    a = Prospecto.objects.create(nombre_aspirante=nombre_a, consentimiento=True, tiene_alumno=True,
                                 creado_en=timezone.now() - timezone.timedelta(days=3))
    b = Prospecto.objects.create(nombre_aspirante=nombre_b, consentimiento=True, tiene_alumno=True)
    return a, b


def test_una_pantalla_con_pestanas(jefe, datos):
    for url in ['/admin/herramientas/prospectos/', '/admin/herramientas/prospectos/nuevos/', '/admin/herramientas/prospectos/todos/',
                '/admin/herramientas/prospectos/permiso/', '/admin/herramientas/prospectos/forms/',
                '/admin/herramientas/prospectos/todos/?q=ana&plantel=cuautitlan&segmento=sensible_beca&estatus=registrado&mios=1&tareas=1&brecha=1',
                '/admin/herramientas/cola/', '/admin/herramientas/respuestas/?estado=valida&_todas=1&tipo=ALUMNO&q=a']:
        r = jefe.get(url)
        assert r.status_code == 200, url
        assert 'pp-pestana activa' in r.content.decode()
    html = jefe.get('/admin/herramientas/prospectos/todos/').content.decode()
    assert 'Ana Sofía' in html and 'Menor Sin Tutor' not in html  # sin permiso no se usa
    assert 'Menor Sin Tutor' in jefe.get('/admin/herramientas/prospectos/permiso/').content.decode()


def test_enlace_viejo_de_esperando_permiso_abre_la_pestana(jefe, datos):
    html = jefe.get('/admin/herramientas/respuestas/?estado=cuarentena').content.decode()
    assert 'aria-current="page"' in html and 'Esperando permiso' in html and 'Menor Sin Tutor' in html


def test_permisos_por_rol(client, datos):
    client.force_login(usuario('d@x.mx', 'Directivo'))
    assert client.get('/admin/herramientas/prospectos/').status_code == 403
    client.force_login(usuario('ad@x.mx', 'Admisiones'))
    html = client.get('/admin/herramientas/prospectos/').content.decode()
    assert 'Llamar hoy' in html and 'data-baja=' not in html.replace('data-baja="/', '')  # solo administradores dan de baja
    assert client.post(f'/admin/herramientas/prospectos/{datos.pk}/baja/', {'motivo': 'derecho_arco', 'confirmo': 'BAJA'}).status_code == 403


def test_dar_de_baja_anonimiza_y_queda_en_bitacora(jefe, datos):
    url = f'/admin/herramientas/prospectos/{datos.pk}/baja/'
    jefe.post(url, {'motivo': 'derecho_arco', 'confirmo': 'no'})
    datos.refresh_from_db()
    assert datos.anonimizado_en is None  # sin escribir BAJA no pasa nada
    jefe.post(url, {'motivo': 'otro', 'confirmo': 'BAJA'})
    datos.refresh_from_db()
    assert datos.anonimizado_en is None  # «Otro» pide el detalle
    r = jefe.post(url, {'motivo': 'registro_de_prueba', 'confirmo': 'baja', 'volver': 'https://otro.sitio/'})
    assert r['Location'] == '/admin/herramientas/prospectos/'  # no redirige fuera
    datos.refresh_from_db()
    assert datos.anonimizado_en and datos.nombre_aspirante.startswith('Anónimo') and not datos.correo
    assert Prospecto.objects.filter(pk=datos.pk).exists()  # no se borra el registro
    assert Auditoria.objects.filter(accion='dar_de_baja').exists()
    jefe.get('/admin/herramientas/prospectos/todos/')  # muestra el aviso de la baja
    assert 'Ana Sofía' not in jefe.get('/admin/herramientas/prospectos/todos/').content.decode()


def test_duplicados_un_par_aunque_haya_propuesta_en_los_dos_sentidos(jefe):
    a, b = _dos()
    PosibleCoincidencia.objects.create(prospecto=b, candidato=a, similitud=.9, motivo='Nombre similar')
    PosibleCoincidencia.objects.create(prospecto=a, candidato=b, similitud=.7, motivo='Nombre similar')
    fam = Prospecto.objects.create(nombre_aspirante='Luis Pérez', consentimiento=True, tiene_tutor=True)
    PosibleCoincidencia.objects.create(prospecto=fam, candidato=a, similitud=.8, motivo='Familia: nombre parecido (80%)')
    pares = duplicados_pendientes()
    assert len(pares) == 1 and pares[0]['queda'] == a and pares[0]['puntos'] == 90 and len(pares[0]['ids']) == 2
    html = jefe.get('/admin/herramientas/duplicados/').content.decode()
    assert html.count('class="dp-par"') == 1
    assert jefe.get('/admin/herramientas/duplicados/?nivel=baja').content.decode().count('class="dp-par"') == 0
    assert jefe.get('/admin/herramientas/duplicados/?q=luis&nivel=alta').content.decode().count('class="dp-par"') == 1


def test_duplicados_distintas_rechaza_ambos_sentidos(jefe):
    a, b = _dos()
    c1 = PosibleCoincidencia.objects.create(prospecto=b, candidato=a, similitud=.9, motivo='Nombre similar')
    c2 = PosibleCoincidencia.objects.create(prospecto=a, candidato=b, similitud=.7, motivo='Nombre similar')
    jefe.post('/admin/herramientas/duplicados/', {'accion': 'distintas', 'propuesta': [c1.pk, c2.pk]})
    assert set(PosibleCoincidencia.objects.values_list('estado', flat=True)) == {'rechazada'}
    assert duplicados_pendientes() == []


def test_duplicados_unir_conserva_el_mas_antiguo(jefe):
    a, b = _dos()
    c = PosibleCoincidencia.objects.create(prospecto=b, candidato=a, similitud=.9, motivo='Nombre similar')
    jefe.post('/admin/herramientas/duplicados/', {'accion': 'unir', 'propuesta': [c.pk]})
    b.refresh_from_db()
    assert b.fusionado_en_id == a.pk


def test_por_revisar_lleva_a_lo_que_tiene_pendientes(jefe):
    assert jefe.get('/admin/herramientas/revisar/')['Location'].endswith('/familias/')
    _a, _b = _dos()
    PosibleCoincidencia.objects.create(prospecto=_b, candidato=_a, similitud=.9, motivo='Nombre similar')
    assert jefe.get('/admin/herramientas/revisar/')['Location'].endswith('/duplicados/')
    html = jefe.get('/admin/herramientas/familias/').content.decode()
    assert 'Duplicados' in html and 'pp-pestana activa' in html


def test_historial_de_coincidencias_deja_ver_todas(jefe):
    a, b = _dos()
    PosibleCoincidencia.objects.create(prospecto=b, candidato=a, similitud=.9, motivo='Nombre similar', estado='rechazada')
    r = jefe.get('/admin/prospectos/posiblecoincidencia/')
    assert r.status_code == 200 and '0 resultados' in r.content.decode() or 'Luis' not in r.content.decode()
    r = jefe.get('/admin/prospectos/posiblecoincidencia/?estado=todas&tipo=duplicado')
    assert r.status_code == 200 and 'Luis' in r.content.decode()
