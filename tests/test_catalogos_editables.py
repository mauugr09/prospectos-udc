"""Carreras, preguntas, opciones y usuarios editables desde el panel, sin que el programa los pise."""
import re

import pytest
from django.contrib.auth.models import Group, User

from prospectos.models import Carrera, Configuracion, OpcionPregunta, Perfil, Pregunta, Prospecto, Respuesta
from prospectos.servicios import semillas

from .conftest import alumno, importar, usuario


@pytest.fixture
def admin_c(client):
    client.force_login(User.objects.create_superuser('root@x.mx', 'root@x.mx', 'Clave-de-prueba-123'))
    return client


def _inline(prefijo, filas, iniciales=0):
    d = {f'{prefijo}-TOTAL_FORMS': len(filas), f'{prefijo}-INITIAL_FORMS': iniciales,
         f'{prefijo}-MIN_NUM_FORMS': 0, f'{prefijo}-MAX_NUM_FORMS': 1000}
    for i, f in enumerate(filas):
        d.update({f'{prefijo}-{i}-{k}': v for k, v in f.items()})
    return d


def test_carrera_nueva_sobrevive_al_reinicio_y_se_reconoce_por_alias(admin_c, f_alumno, evento):
    r = admin_c.post('/admin/prospectos/carrera/add/', {'nombre': 'Psicología', 'area': 'Salud', 'planteles': ['cuautitlan'],
                                                       'alias': 'Psicologia clinica\nPsico', 'activo': 'on'})
    assert r.status_code == 302
    semillas.preparar()
    Configuracion.guardar('catalogo.version', 0)
    semillas.preparar()  # incluso con una actualización del programa
    c = Carrera.objects.get(nombre='Psicología')
    assert c.activo and c.editada and c.planteles == ['cuautitlan'] and c.alias == ['Psicologia clinica', 'Psico']
    importar(f_alumno, alumno('a1', edad='18', carrera=['Psico']))
    assert Prospecto.objects.get().carrera == c


def test_apagar_carrera_vieja_no_se_revierte(admin_c):
    c = Carrera.objects.get(nombre='Filosofía')
    admin_c.post(f'/admin/prospectos/carrera/{c.pk}/change/', {'nombre': 'Filosofía', 'area': c.area, 'planteles': ['cuautitlan']})
    Configuracion.guardar('catalogo.version', 0)
    semillas.preparar()
    assert not Carrera.objects.get(pk=c.pk).activo


def test_texto_de_pregunta_editado_se_respeta(admin_c):
    p = Pregunta.objects.get(cuestionario='ALUMNO', codigo='edad')
    datos = {'texto': '¿Cuántos años tienes?', 'etiqueta': 'Años', 'tema': 'generales', 'orden': 20}
    r = admin_c.post(f'/admin/prospectos/pregunta/{p.pk}/change/', datos)
    assert r.status_code == 302, r.content.decode()[:500]
    Configuracion.guardar('catalogo.version', 0)
    semillas.preparar()
    p.refresh_from_db()
    assert p.texto == '¿Cuántos años tienes?' and p.etiqueta == 'Años' and p.tipo == 'numero' and p.de_sistema


def test_agregar_pregunta_con_opciones_y_verla_en_ficha_y_reporte(admin_c, f_alumno, evento):
    datos = {'cuestionario': 'ALUMNO', 'texto': '¿Trabajas actualmente?', 'etiqueta': 'Trabaja', 'tema': 'ideal',
             'tipo': 'opcion', 'orden': 200, 'codigo': ''}
    datos.update(_inline('opciones_lista', [{'texto': 'Sí, tiempo completo', 'orden': 1}, {'texto': 'Sí, medio tiempo', 'orden': 2},
                                            {'texto': 'No', 'orden': 3}]))
    r = admin_c.post('/admin/prospectos/pregunta/add/', datos)
    assert r.status_code == 302, r.content.decode()[:800]
    p = Pregunta.objects.get(etiqueta='Trabaja')
    assert p.codigo == 'trabaja' and not p.de_sistema and p.opciones_lista.count() == 3
    f_alumno.mapeo_campos['q_trabaja'] = 'trabaja'
    f_alumno.save()
    importar(f_alumno, alumno('a1', edad='18', trabaja='Sí, medio tiempo'))
    pr = Prospecto.objects.get()
    html = admin_c.get(f'/admin/prospectos/prospecto/{pr.pk}/change/').content.decode()
    assert 'Trabaja' in html and 'Sí, medio tiempo' in html
    html = admin_c.get('/admin/herramientas/reporte/?desde=2026-01-01&hasta=2026-12-31').content.decode()
    assert 'Trabaja' in html


def test_renombrar_opcion_no_pierde_respuestas_viejas(admin_c, f_alumno, evento):
    importar(f_alumno, alumno('a1', edad='18'))  # factor_eleccion «Becas y descuentos.»
    p = Pregunta.objects.get(cuestionario='ALUMNO', codigo='factor_eleccion')
    o = p.opciones_lista.get(clave='becas')
    o.texto = 'Becas, descuentos y apoyos'
    o.save()
    assert 'Becas y descuentos' in o.alias_lista()
    from prospectos.servicios import importacion
    importacion.reprocesar(f_alumno)
    assert 'becas' in Respuesta.objects.get().valores('factor_eleccion')


def test_no_se_borran_opciones_ni_preguntas_que_usan_las_reglas(admin_c):
    p = Pregunta.objects.get(cuestionario='ALUMNO', codigo='recibir_informacion')
    ops = list(p.opciones_lista.all())
    filas = [{'id': o.pk, 'pregunta': p.pk, 'texto': o.texto, 'orden': o.orden, 'alias': ''} for o in ops]
    filas[2]['DELETE'] = 'on'  # «No, gracias»
    datos = {'texto': p.texto, 'etiqueta': p.etiqueta, 'tema': p.tema, 'orden': p.orden}
    datos.update(_inline('opciones_lista', filas, iniciales=len(ops)))
    r = admin_c.post(f'/admin/prospectos/pregunta/{p.pk}/change/', datos)
    assert r.status_code == 200 and 'la usan las reglas' in r.content.decode()
    assert OpcionPregunta.objects.filter(pregunta=p).count() == 3
    assert admin_c.get(f'/admin/prospectos/pregunta/{p.pk}/delete/').status_code == 403


def test_alta_de_usuario_en_un_paso_y_cambio_de_clave_obligatorio(admin_c, client):
    r = admin_c.post('/admin/auth/user/add/', {'email': 'Laura@UDC.mx', 'first_name': 'Laura', 'last_name': 'Ruiz',
                                               'rol': Group.objects.get(name='Admisiones').pk, 'codigo_promotor': '',
                                               'clave': ''}, follow=True)
    html = r.content.decode()
    u = User.objects.get(username='laura@udc.mx')
    assert u.groups.get().name == 'Admisiones' and u.is_staff and Perfil.objects.get(usuario=u).debe_cambiar_clave
    clave = re.search(r'<code[^>]*>([^<]+)</code>', html).group(1)
    assert u.check_password(clave)
    client.logout()
    assert client.login(username='laura@udc.mx', password=clave)
    r = client.get('/admin/')
    assert r.status_code == 302 and 'password_change' in r['Location']
    r = client.post('/admin/password_change/', {'old_password': clave, 'new_password1': 'Mi-Clave-Nueva-2026',
                                                'new_password2': 'Mi-Clave-Nueva-2026'}, follow=True)
    assert not Perfil.objects.get(usuario=u).debe_cambiar_clave
    assert client.get('/admin/').status_code == 200


def test_coordinacion_edita_catalogos_y_usuarios_pero_no_puede_escalar(client):
    jefe = User.objects.create_superuser('jefe@x.mx', 'jefe@x.mx', 'Clave-de-prueba-123')
    c = client
    c.force_login(usuario('coord@x.mx', 'Coordinación'))
    assert c.get('/admin/prospectos/pregunta/add/').status_code == 200
    assert c.get('/admin/prospectos/carrera/add/').status_code == 200
    assert c.get('/admin/herramientas/scoring/').status_code == 200
    html = c.get('/admin/auth/user/').content.decode()
    assert 'jefe@x.mx' not in html  # no ve administradores
    assert c.get(f'/admin/auth/user/{jefe.pk}/change/').status_code in (302, 404)
    html = c.get('/admin/auth/user/add/').content.decode()
    assert '>Administrador<' not in html and '>Admisiones<' in html
    assert c.get('/admin/auth/group/').status_code == 403
    adm = Group.objects.get(name='Administrador')
    c.post('/admin/auth/user/add/', {'email': 'x@x.mx', 'first_name': 'X', 'rol': adm.pk})
    assert not User.objects.filter(username='x@x.mx').exists()


def test_usuarios_no_se_borran_se_desactivan(admin_c):
    u = usuario('p@x.mx', 'Promotor', 'P7')
    assert admin_c.get(f'/admin/auth/user/{u.pk}/delete/').status_code == 403
    admin_c.post('/admin/auth/user/', {'action': 'desactivar', '_selected_action': [u.pk]})
    assert not User.objects.get(pk=u.pk).is_active
