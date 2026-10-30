"""Unir la encuesta de la familia con el cuestionario del alumno, y la CURP sin consultas externas."""
import datetime as dt

from django.db.models import Q

from django.contrib.auth.models import User

from prospectos.models import PosibleCoincidencia, Prospecto
from prospectos.servicios import curp, familias

from .conftest import alumno, importar, tutor


def curp_valida(base17='LOGA080315MMCPRNA'):
    return base17 + str(curp.digito_verificador(base17))


def test_curp_valida_y_lo_que_trae_dentro():
    c = curp_valida()
    d = curp.analizar(c.lower())
    assert d['curp'] == c and d['fecha_nacimiento'] == dt.date(2008, 3, 15) and d['entidad'] == 'Estado de México'
    assert curp.analizar(c[:-1] + str((int(c[-1]) + 1) % 10)) is None  # dígito verificador mal
    assert curp.analizar(curp_valida('LOGA081315MMCPRNA')) is None  # mes 13
    assert curp.analizar(curp_valida('LOGA950315MMCPRN0'))['fecha_nacimiento'].year == 1995  # antes de 2000: dígito
    assert curp.analizar('hola') is None
    assert curp.edad(dt.date(2008, 3, 15), dt.date(2026, 3, 14)) == 17
    assert curp.edad(dt.date(2008, 3, 15), dt.date(2026, 3, 15)) == 18
    assert curp.analizar(curp_valida('LOGA090315MMCPRNA'))['fecha_nacimiento'].year == 2009  # desde 2000: letra


def test_papa_escribe_el_nombre_incompleto_pero_en_el_mismo_evento_se_unen_solos(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', 'Juan Carlos Pérez López'))
    importar(f_tutor, tutor('t1', 'Juan Pérez', tutor_nombre='Rosa López Díaz'))
    p = Prospecto.objects.get(fusionado_en__isnull=True)
    assert p.tiene_alumno and p.tiene_tutor and p.tutor_nombre == 'Rosa López Díaz'
    assert p.consentimiento and p.origen_consentimiento == 'tutor'  # el menor ya tiene permiso de su familia


def test_el_alumno_dio_el_telefono_de_su_mama(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', 'Valeria Ramírez Soto', telefono='55 4444 1212'))
    importar(f_tutor, tutor('t1', 'Vale Ramírez', evento=None, tutor_telefono='5544441212', tutor_nombre='Laura Soto', minutos=60 * 24 * 5))
    p = Prospecto.objects.get(fusionado_en__isnull=True)
    assert p.tiene_alumno and p.tiene_tutor


def test_curp_une_con_certeza_y_da_la_edad_exacta(f_alumno, f_tutor, evento):
    c = curp_valida()
    importar(f_alumno, alumno('a1', 'Ana López García', edad=None, curp=c))
    p = Prospecto.objects.get()
    assert p.fecha_nacimiento == dt.date(2008, 3, 15) and p.edad >= 18 and p.curp == c and p.curp_bi
    importar(f_tutor, tutor('t1', 'Otra Persona Distinta', evento=None, curp_aspirante=c.lower(), plantel=None,
                            tutor_correo=None, tutor_telefono=None, minutos=60 * 24 * 30))
    p = Prospecto.objects.get(fusionado_en__isnull=True)
    assert p.tiene_alumno and p.tiene_tutor


def test_con_duda_va_a_familias_por_unir_y_se_resuelve_con_un_clic(client, f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', 'Diego Hernández Ruiz'))
    importar(f_tutor, tutor('t1', 'Diego Hernández', evento=None, tutor_correo=None, tutor_telefono=None,
                            tutor_nombre='Pedro Martínez', minutos=60 * 24 * 3))
    assert Prospecto.objects.filter(fusionado_en__isnull=True).count() == 2
    prop = familias.pendientes().get()
    assert prop.similitud >= .3 and 'nombre coincide' in prop.motivo
    client.force_login(User.objects.create_superuser('f@x.mx', 'f@x.mx', 'Clave-de-prueba-123'))
    html = client.get('/admin/herramientas/familias/').content.decode()
    assert 'data-accion="unir"' in html and 'Diego Hernández Ruiz' in html
    assert 'Familias por unir' in client.get('/admin/').content.decode()  # en el menú
    client.post('/admin/herramientas/familias/', {'accion': 'unir', 'propuesta': prop.pk})
    p = Prospecto.objects.get(fusionado_en__isnull=True)
    assert p.tiene_alumno and p.tiene_tutor and p.nombre_aspirante == 'Diego Hernández Ruiz'


def test_union_manual_y_rechazo(client, f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', 'Sofía Torres Vega'))
    importar(f_tutor, tutor('t1', 'Mi hija', evento=None, tutor_correo=None, tutor_telefono=None, tutor_nombre='Raúl Torres',
                            minutos=60 * 24 * 10))
    familia = Prospecto.objects.get(tiene_tutor=True, tiene_alumno=False)
    a = Prospecto.objects.get(tiene_alumno=True, tiene_tutor=False)
    client.force_login(User.objects.create_superuser('m@x.mx', 'm@x.mx', 'Clave-de-prueba-123'))
    html = client.get(f'/admin/herramientas/familias/alumnos/?familia={familia.pk}&q=torres').content.decode()
    assert 'Sofía Torres Vega' in html
    client.post('/admin/herramientas/familias/', {'accion': 'manual', 'familia': familia.pk, 'alumno': a.pk})
    assert Prospecto.objects.get(pk=a.pk).tiene_tutor


def test_no_une_si_hay_dos_alumnos_igual_de_probables(f_alumno, f_tutor, evento, evento2):
    importar(f_alumno, alumno('a1', 'Luis Pérez Ruiz'), alumno('a2', 'Luis Pérez Gómez', evento='EV2', correo='o@x.mx'))
    importar(f_tutor, tutor('t1', 'Luis Pérez', evento=None, tutor_correo=None, tutor_telefono=None, tutor_nombre='Ana Mora'))
    assert Prospecto.objects.filter(fusionado_en__isnull=True).count() == 3
    assert familias.pendientes().count() == 2


def test_planteles_distintos_restan(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', 'Karla Núñez Ortiz'))
    importar(f_tutor, tutor('t1', 'Karla Núñez Ortiz', evento=None, tutor_correo=None, tutor_telefono=None,
                            plantel='Universidad de Tultepec', tutor_nombre='José Ortiz'))
    assert Prospecto.objects.filter(fusionado_en__isnull=True).count() == 2


# --------------------------------------------------------------------------- pantalla agrupada por familia

def _dos_candidatos(f_alumno, f_tutor):
    importar(f_alumno, alumno('a1', 'Luis Pérez Ruiz'), alumno('a2', 'Luis Pérez Gómez', evento='EV2', correo='o@x.mx'))
    importar(f_tutor, tutor('t1', 'Luis Pérez', evento=None, tutor_correo=None, tutor_telefono=None, tutor_nombre='Ana Mora'))
    return Prospecto.objects.get(tiene_tutor=True, tiene_alumno=False)


def test_mesa_agrupa_por_familia_y_no_repite_parejas(f_alumno, f_tutor, evento, evento2):
    familia = _dos_candidatos(f_alumno, f_tutor)
    alumno1 = Prospecto.objects.get(nombre_aspirante='Luis Pérez Ruiz')
    # Misma pareja propuesta desde el otro lado (pasa con propuestas de criterios anteriores)
    PosibleCoincidencia.objects.create(prospecto=alumno1, candidato=familia, similitud=.4, motivo='Familia: viejo')
    m = familias.mesa()
    assert len(m['con']) == 1 and m['solas'] == []
    g = m['con'][0]
    assert g['familia'] == familia and len(g['candidatos']) == 2
    c1 = next(c for c in g['candidatos'] if c['alumno'] == alumno1)
    assert len(c1['propuestas']) == 2 and c1['puntos'] > 40
    assert familias.familias_pendientes() == 1  # el menú cuenta familias, no propuestas


def test_descartar_una_pareja_descarta_sus_duplicados(client, f_alumno, f_tutor, evento, evento2):
    familia = _dos_candidatos(f_alumno, f_tutor)
    alumno1 = Prospecto.objects.get(nombre_aspirante='Luis Pérez Ruiz')
    PosibleCoincidencia.objects.create(prospecto=alumno1, candidato=familia, similitud=.4, motivo='Familia: viejo')
    client.force_login(User.objects.create_superuser('d@x.mx', 'd@x.mx', 'Clave-de-prueba-123'))
    c1 = next(c for c in familias.mesa()['con'][0]['candidatos'] if c['alumno'] == alumno1)
    r = client.post('/admin/herramientas/familias/', {'accion': 'no', 'propuesta': c1['propuestas']}, HTTP_X_REQUESTED_WITH='fetch')
    assert r.json()['ok']
    assert not familias.pendientes().filter(Q(prospecto=alumno1) | Q(candidato=alumno1)).exists()
    assert len(familias.mesa()['con'][0]['candidatos']) == 1


def test_ninguno_deja_la_encuesta_sin_pareja(client, f_alumno, f_tutor, evento, evento2):
    familia = _dos_candidatos(f_alumno, f_tutor)
    client.force_login(User.objects.create_superuser('n@x.mx', 'n@x.mx', 'Clave-de-prueba-123'))
    r = client.post('/admin/herramientas/familias/', {'accion': 'ninguno', 'familia': familia.pk}, HTTP_X_REQUESTED_WITH='fetch')
    assert r.json()['ok'] and 'Se descartaron 2' in r.json()['mensaje']
    m = familias.mesa()
    assert m['con'] == [] and [g['familia'] for g in m['solas']] == [familia]


def test_unir_por_fetch_responde_json_y_resuelta_da_409(client, f_alumno, f_tutor, evento, evento2):
    familia = _dos_candidatos(f_alumno, f_tutor)
    client.force_login(User.objects.create_superuser('j@x.mx', 'j@x.mx', 'Clave-de-prueba-123'))
    c = familias.mesa()['con'][0]['candidatos'][0]
    r = client.post('/admin/herramientas/familias/', {'accion': 'unir', 'propuesta': c['propuestas']}, HTTP_X_REQUESTED_WITH='fetch')
    j = r.json()
    assert j['ok'] and j['alumno'] == c['alumno'].pk and j['familia'] == familia.pk
    assert Prospecto.objects.get(pk=c['alumno'].pk).tiene_tutor
    r = client.post('/admin/herramientas/familias/', {'accion': 'unir', 'propuesta': c['propuestas']}, HTTP_X_REQUESTED_WITH='fetch')
    assert r.status_code == 409 and not r.json()['ok']


def test_busqueda_de_alumno_tolera_acentos_y_variantes_y_da_puntos(client, f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', 'Ximena González Vázquez'), alumno('a2', 'Pedro Ruiz Soto', correo='p@x.mx'))
    importar(f_tutor, tutor('t1', 'Mi hija', evento=None, tutor_correo=None, tutor_telefono=None, tutor_nombre='Rosa Vázquez',
                            minutos=60 * 24 * 10))
    familia = Prospecto.objects.get(tiene_tutor=True, tiene_alumno=False)
    res = familias.buscar_alumnos(familia, 'jimena gonzales')
    assert [r['alumno'].nombre_aspirante for r in res] == ['Ximena González Vázquez']
    assert familias.buscar_alumnos(familia, 'z') == []  # muy corto
    client.force_login(User.objects.create_superuser('b@x.mx', 'b@x.mx', 'Clave-de-prueba-123'))
    html = client.get(f'/admin/herramientas/familias/alumnos/?familia={familia.pk}&q=ruiz').content.decode()
    assert 'Pedro Ruiz Soto' in html and 'data-confirmar' in html  # sin nada en común: pide confirmar
    html = client.get('/admin/herramientas/familias/').content.decode()
    assert 'id="fm-q"' in html and 'Busca a su hijo(a)' in html
