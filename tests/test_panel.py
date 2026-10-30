import pytest
from django.contrib.auth.models import User

from prospectos.models import Auditoria, Configuracion, Evento, Prospecto
from prospectos.servicios import semillas

from .conftest import alumno, importar, tutor, usuario


@pytest.fixture
def datos(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1'), alumno('a2', 'Menor Sin Tutor Ruiz', edad='15'))
    importar(f_tutor, tutor('t1'))
    return Prospecto.objects.get(nombre_aspirante='Ana Sofía López García')


def cliente(client, u):
    client.force_login(u)
    return client


def test_exige_sesion(client):
    r = client.get('/admin/prospectos/prospecto/')
    assert r.status_code == 302 and '/admin/login/' in r['Location']


def test_usuario_inactivo_o_sin_staff_no_entra(client):
    u = User.objects.create_user('x@x.mx', 'x@x.mx', 'Clave-de-prueba-123', is_staff=False)
    assert cliente(client, u).get('/admin/').status_code == 302


def test_directivo_solo_reportes(client, datos):
    c = cliente(client, usuario('d@x.mx', 'Directivo'))
    assert c.get('/admin/herramientas/reporte/').status_code == 200
    assert c.get('/admin/prospectos/prospecto/').status_code == 403
    assert c.get(f'/admin/prospectos/prospecto/{datos.pk}/change/').status_code == 403
    assert c.get('/admin/herramientas/cola/').status_code == 403


def test_admisiones_trabaja_prospectos_sin_usuarios_ni_auditoria(client, datos):
    c = cliente(client, usuario('ad@x.mx', 'Admisiones'))
    assert c.get('/admin/prospectos/prospecto/').status_code == 200
    assert c.get('/admin/herramientas/cola/').status_code == 200
    assert c.get('/admin/auth/user/').status_code == 403
    assert c.get('/admin/prospectos/auditoria/').status_code == 403


def test_promotor_solo_lo_suyo_y_enmascarado(client, datos, promotor):
    otro = usuario('p2@x.mx', 'Promotor', 'P02')
    c = cliente(client, otro)
    assert c.get(f'/admin/prospectos/prospecto/{datos.pk}/change/').status_code == 302  # no existe para él
    c = cliente(client, promotor)
    r = c.get(f'/admin/prospectos/prospecto/{datos.pk}/change/?contacto=1')
    assert r.status_code == 200 and 'a1@correo.mx' not in r.content.decode() and 'Mostrar datos' not in r.content.decode()


def test_nadie_ve_sin_consentimiento_por_defecto(client, datos):
    c = cliente(client, usuario('ad@x.mx', 'Admisiones'))
    html = c.get('/admin/prospectos/prospecto/').content.decode()
    assert 'Ana Sofía' in html and 'Menor Sin Tutor' not in html


def test_auditoria_al_abrir_ficha_y_ver_contacto(client, datos):
    c = cliente(client, usuario('ad@x.mx', 'Admisiones'))
    html = c.get(f'/admin/prospectos/prospecto/{datos.pk}/change/').content.decode()
    assert 'a1@correo.mx' not in html
    html = c.get(f'/admin/prospectos/prospecto/{datos.pk}/change/?contacto=1').content.decode()
    assert 'a1@correo.mx' in html
    acciones = list(Auditoria.objects.values_list('accion', flat=True))
    assert acciones.count('ver') == 2 and 'ver_datos_personales' in acciones


def test_exportar_con_permiso_y_bitacora(client, datos):
    c = cliente(client, usuario('ad@x.mx', 'Admisiones'))
    r = c.post('/admin/prospectos/prospecto/', {'action': 'exportar_excel_contacto', '_selected_action': [datos.pk]})
    assert r['Content-Type'].startswith('application/vnd.openxmlformats') and Auditoria.objects.filter(accion='exportar_con_contacto').exists()
    from io import BytesIO
    from openpyxl import load_workbook
    filas = list(load_workbook(BytesIO(b''.join(r.streaming_content) if r.streaming else r.content)).active.values)
    assert len(filas[0]) == len(filas[1])  # cada encabezado con su dato (no quedan columnas corridas)
    assert dict(zip(filas[0], filas[1], strict=True))['Prioridad'] == datos.score
    c = cliente(client, usuario('p9@x.mx', 'Promotor'))
    html = c.get('/admin/prospectos/prospecto/').content.decode()
    assert 'exportar_excel' not in html


def test_promotor_no_imprime_tarjetas_ajenas(client, evento):
    c = cliente(client, usuario('p2@x.mx', 'Promotor', 'P02'))
    assert c.get(f'/admin/herramientas/evento/{evento.pk}/tarjetas/?cantidad=2').status_code == 403


def test_en_vivo_json_sin_datos_personales(client, datos, evento):
    c = cliente(client, usuario('ad@x.mx', 'Admisiones'))
    d = c.get(f'/admin/herramientas/evento/{evento.pk}/en-vivo/datos/').json()
    assert d['alumnos'] == 2 and d['tutores'] == 1 and 'Ana' not in str(d)


def test_scoring_guarda_y_recalcula(client, datos):
    admin = User.objects.create_superuser('root@x.mx', 'root@x.mx', 'Clave-de-prueba-123')
    c = cliente(client, admin)
    pesos = {f'peso_{k}': 0 for k in ['pidio_informacion', 'eligio_carrera', 'pregunta_requisitos', 'eligio_modalidad',
                                      'pregunta_costos']}
    pesos.update({'peso_contacto_completo': 10, 'umbral_listo_para_convertir_score': 70, 'umbral_indeciso_desde_carreras': 3})
    c.post('/admin/herramientas/scoring/', pesos)
    assert Configuracion.obtener('score.pesos')['contacto_completo'] == 10
    assert Prospecto.objects.get(pk=datos.pk).score == 100
    assert cliente(client, usuario('p3@x.mx', 'Promotor')).get('/admin/herramientas/scoring/').status_code == 403


def test_estatus_desde_el_panel_deja_bitacora(client, datos):
    from prospectos.models import Seguimiento
    c = cliente(client, usuario('ad@x.mx', 'Admisiones'))
    r = c.post(f'/admin/prospectos/prospecto/{datos.pk}/change/', {
        'estatus': 'solicito_inscripcion', 'asesor': '',
        'seguimientos-TOTAL_FORMS': 1, 'seguimientos-INITIAL_FORMS': 0, 'seguimientos-MIN_NUM_FORMS': 0, 'seguimientos-MAX_NUM_FORMS': 1000,
        'seguimientos-0-tipo': 'llamada', 'seguimientos-0-fecha_0': '27/10/2026', 'seguimientos-0-fecha_1': '10:00:00',
        'seguimientos-0-notas': 'Llamé', 'seguimientos-0-vence_en_0': '', 'seguimientos-0-vence_en_1': '',
        'seguimientos-2-TOTAL_FORMS': 0, 'seguimientos-2-INITIAL_FORMS': 0, 'seguimientos-2-MIN_NUM_FORMS': 0, 'seguimientos-2-MAX_NUM_FORMS': 0,
    })
    assert r.status_code == 302, r.content.decode()[:3000]
    p = Prospecto.objects.get(pk=datos.pk)
    assert p.estatus == 'solicito_inscripcion' and p.ultimo_contacto_en
    assert Seguimiento.objects.filter(prospecto=p, tipo='cambio_estatus', estatus_nuevo='solicito_inscripcion').exists()
    assert Seguimiento.objects.filter(prospecto=p, tipo='llamada', notas='Llamé').exists()


@pytest.mark.django_db(transaction=True)
def test_demo_completa_y_todas_las_pantallas_cargan(client, settings, tmp_path):
    settings.DATA_DIR = tmp_path
    semillas.cargar_demo(40, salida=lambda *_: None)
    assert Prospecto.objects.utilizables().count() > 10
    e = Evento.objects.get(codigo='EVDEMOHOY')
    p = Prospecto.objects.utilizables().first()
    from prospectos.models import Formulario
    fid = Formulario.objects.order_by('pk').first().pk
    for u in ['admin@demo.local', 'admisiones@demo.local', 'directivo@demo.local', 'promotor1@demo.local']:
        c = cliente(client, User.objects.get(username=u))
        for url in ['/admin/', '/admin/herramientas/cola/', '/admin/herramientas/mapa/', '/admin/herramientas/reporte/',
                    '/admin/herramientas/reporte/?excel=1', '/admin/herramientas/scoring/', f'/admin/herramientas/evento/{e.pk}/en-vivo/',
                    f'/admin/herramientas/evento/{e.pk}/tarjetas/?cantidad=2', '/admin/prospectos/prospecto/',
                    f'/admin/prospectos/prospecto/{p.pk}/change/', '/admin/prospectos/posiblecoincidencia/?estado__exact=pendiente',
                    '/admin/prospectos/respaldo/', f'/admin/prospectos/formulario/{fid}/change/', f'/admin/herramientas/formulario/{fid}/mapeo/',
                    '/admin/?dias=7', '/admin/?dias=365', '/admin/herramientas/respuestas/',
                    '/admin/herramientas/respuestas/?estado=cuarentena&tipo=TUTOR&q=a', '/admin/herramientas/ayuda/']:
            assert c.get(url).status_code in (200, 302, 403), (u, url)


def test_anonimizar_arco_pide_confirmacion(client, datos):
    c = cliente(client, usuario('ad@x.mx', 'Admisiones'))
    r = c.post('/admin/prospectos/prospecto/', {'action': 'anonimizar_arco', '_selected_action': [datos.pk]})
    assert r.status_code == 200 and 'ANONIMIZAR' in r.content.decode()
    assert not Prospecto.objects.get(pk=datos.pk).anonimizado_en
    c.post('/admin/prospectos/prospecto/', {'action': 'anonimizar_arco', '_selected_action': [datos.pk], 'confirmar': 'ANONIMIZAR'})
    p = Prospecto.objects.get(pk=datos.pk)
    assert p.anonimizado_en and p.correo is None


def test_login_lleva_al_tablero_con_la_identidad_udc(client):
    User.objects.create_superuser('root@x.mx', 'root@x.mx', 'Clave-de-prueba-123')
    html = client.get('/admin/login/').content.decode()
    assert 'ac-tarjeta' in html and 'udc-edificio.jpg' in html and 'Universidad de Cuautitlán' in html
    assert 'sign up' not in html.lower() and 'name="password"' in html  # sin registro público
    r = client.post('/admin/login/', {'username': 'root@x.mx', 'password': 'Clave-de-prueba-123'})
    assert r.status_code == 302 and r['Location'] == '/admin/'
    html = client.get('/admin/').content.decode()
    assert 'titulo-grande' in html and 'Universidad de Cuautitlán' in html and 'prospectos/css/udc.css' in html


def test_logo_opcional(client, settings, tmp_path):
    assert client.get('/marca/logo.png').status_code == 404
    settings.LOGO_ARCHIVO = tmp_path / 'logo.png'
    settings.LOGO_ARCHIVO.write_bytes(b'\x89PNG\r\n\x1a\n')
    assert client.get('/marca/logo.png')['Content-Type'] == 'image/png'


def test_tablero_avisa_si_fallo_el_respaldo(client):
    from prospectos.models import Respaldo
    c = cliente(client, User.objects.create_superuser('root@x.mx', 'root@x.mx', 'Clave-de-prueba-123'))
    Respaldo.objects.create(archivo='x.sql.gz', estado='error', mensaje='No se encontró mariadb-dump.exe')
    assert 'El último respaldo falló' in c.get('/admin/').content.decode()


def test_respuestas_explican_por_que_no_aparece(client, datos):
    """El menor sin tutor está en la bandeja como «Esperando permiso», no perdido."""
    from prospectos.models import Respuesta
    c = cliente(client, usuario('ad2@x.mx', 'Admisiones'))
    html = c.get('/admin/herramientas/respuestas/?estado=cuarentena').content.decode()
    assert 'Menor Sin Tutor Ruiz' in html and 'Esperando permiso' in html
    assert 'Ana Sofía' not in html  # filtrado por estado
    r = Respuesta.objects.get(nombre_aspirante='Menor Sin Tutor Ruiz')
    html = c.get(f'/admin/herramientas/respuestas/{r.pk}/').content.decode()
    assert 'rs-tema' in html and 'permiso' in html.lower()
    assert Auditoria.objects.filter(accion='ver_respuesta', objeto_id=str(r.pk)).exists()


def test_promotor_solo_ve_sus_respuestas(client, datos):
    from prospectos.models import Respuesta
    otro = usuario('p9@x.mx', 'Promotor', 'P9')
    c = cliente(client, otro)
    r = Respuesta.objects.first()
    assert c.get(f'/admin/herramientas/respuestas/{r.pk}/').status_code == 404
    assert 'rs-item' not in c.get('/admin/herramientas/respuestas/').content.decode()


def test_ficha_compara_alumno_y_tutor_por_tema(client, datos):
    c = cliente(client, usuario('ad3@x.mx', 'Admisiones'))
    html = c.get(f'/admin/prospectos/prospecto/{datos.pk}/change/').content.decode()
    assert 'rs-temas' in html and 'rs-cabeza' in html  # columnas Alumno | Tutor


def test_ayuda_y_primeros_pasos(client, f_alumno):
    root = User.objects.create_superuser('root2@x.mx', 'root2@x.mx', 'Clave-de-prueba-123')
    c = cliente(client, root)
    html = c.get('/admin/herramientas/ayuda/').content.decode()
    assert 'Esperando permiso' in html and 'Para empezar con datos reales' in html
    html = c.get('/admin/').content.decode()
    assert 'Primeros pasos' in html and 'Recibir la primera respuesta' in html
    c.post('/admin/herramientas/primeros-pasos/', {'accion': 'config_copiado'})
    assert Configuracion.obtener('pasos.config_copiado') is True
    c.post('/admin/herramientas/primeros-pasos/', {'accion': 'ocultar'})
    assert 'Primeros pasos' not in c.get('/admin/').content.decode()


def test_primeros_pasos_no_los_cambia_cualquiera(client):
    c = cliente(client, usuario('d2@x.mx', 'Directivo'))
    c.post('/admin/herramientas/primeros-pasos/', {'accion': 'ocultar'})
    assert not Configuracion.obtener('pasos.ocultos', False)


def test_llave_google_con_doble_extension(settings, tmp_path):
    from prospectos.servicios import fuentes
    settings.CONFIG = {**settings.CONFIG, 'GOOGLE_CUENTA_SERVICIO': str(tmp_path / 'google-service-account.json')}
    assert not fuentes.credenciales_listas()
    (tmp_path / 'google-service-account.json.json').write_text('{}')
    assert fuentes.ruta_cuenta_servicio().name == 'google-service-account.json.json'
    assert fuentes.credenciales_listas()


def test_tema_claro_u_oscuro_lo_elige_cada_quien(client):
    c = cliente(client, User.objects.create_superuser('t@x.mx', 't@x.mx', 'Clave-de-prueba-123'))
    html = c.get('/admin/').content.decode()
    assert "theme('dark')" not in html  # ya no se fuerza el oscuro: sistema / claro / oscuro
    assert 'prospectos/js/animaciones.js' in html and 'switchTheme' in html
    assert 'Claro' in html and 'Oscuro' in html and 'Sistema' in html


def test_inicio_empieza_por_a_quien_llamar(client):
    c = cliente(client, User.objects.create_superuser('i@x.mx', 'i@x.mx', 'Clave-de-prueba-123'))
    html = c.get('/admin/').content.decode()
    assert html.index('A quién llamar hoy') < html.index('Pendientes')
    assert any(sal in html for sal in ('Buenos días', 'Buenas tardes', 'Buenas noches'))  # saludo según la hora (decisión 45)
