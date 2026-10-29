"""El Cuestionario Vocacional real: preguntas por plantel, prepa escrita a mano, mapa y permisos."""
import pytest
from django.contrib.auth.models import User

from prospectos.models import (Auditoria, Configuracion, Cuestionario, EstadoRespuesta, Formulario, Preparatoria, Prospecto,
                               Respuesta)
from prospectos.servicios import importacion, preparatorias, semillas
from prospectos.servicios.fuentes import FuenteMemoria

from .conftest import alumno, api, importar, usuario

# Títulos tal cual vienen del Form de la universidad (con sus faltas de ortografía).
ESTRUCTURA = {
    '6155f9d1': 'Nombre completo', '4e8a8f47': '¿Cuál es tu edad?', '3f2d5d55': 'Teléfono',
    '1f53f051': 'Correo electrónico', '0d8a3c6d': '¿En que preparatoria estudias?',
    '61b0b6c7': '¿En qué plantel te gustaría estudiar?',
    '69793c8f': '¿Qué carrera te gastaría estudiar?', '3aa49b47': '¿Qué modalidad de estudio prefieres?',
    '41284591': '¿Qué carrera te gastaría estudiar?', '47bb5051': '¿Qué modalidad de estudio prefieres?',
    '460fe353': '¿Qué es lo más importante para ti al elegir una universidad?',
    '20ff4652': '¿Qué te gustaría conocer sobre la Universidad?',
    '01ebd087': '¿Te gustaría recibir información sobre nuestras carreras y beneficios?',
}


class FuenteForm(FuenteMemoria):
    def estructura(self, formulario):
        return ESTRUCTURA


@pytest.fixture
def form_real():
    return Formulario.objects.create(nombre='CUESTIONARIO VOCACIONAL', tipo=Cuestionario.ALUMNO,
                                     google_form_id='demo-real', mapeo_campos={})


def test_mapeo_propuesto_con_el_form_real(form_real):
    propuesta = importacion.proponer_mapeo(form_real, FuenteForm())
    codigos = {p['question_id']: p['codigo'] for p in propuesta}
    assert codigos['69793c8f'] == codigos['41284591'] == 'carrera'  # una por plantel, mismo código
    assert codigos['3aa49b47'] == codigos['47bb5051'] == 'modalidad'
    assert codigos['0d8a3c6d'] == 'preparatoria' and codigos['61b0b6c7'] == 'plantel'
    assert codigos['3f2d5d55'] == 'telefono' and codigos['01ebd087'] == 'recibir_informacion'
    assert codigos['4e8a8f47'] == 'edad' and None not in codigos.values()


def test_respuesta_de_tultepec_con_prepa_escrita_a_mano(form_real, settings):
    importacion.aplicar_mapeo(form_real, importacion.proponer_mapeo(form_real, FuenteForm()))
    r = {'responseId': 'r1', 'createTime': '2026-10-01T15:00:00Z', 'lastSubmittedTime': '2026-10-01T15:00:00Z', 'answers': {
        q: {'questionId': q, 'textAnswers': {'answers': [{'value': v} for v in (vs if isinstance(vs, list) else [vs])]}}
        for q, vs in {'6155f9d1': 'Luis Pérez Ruiz', '4e8a8f47': '18', '3f2d5d55': '5511112222', '1f53f051': 'l@x.mx',
                      '0d8a3c6d': 'Esc. Prep. Oficial Núm. 45', '61b0b6c7': 'Universidad de Tultepec',
                      '41284591': ['Pedagogía', 'Idiomas'], '47bb5051': 'Sabatino',
                      '460fe353': ['Horarios flexibles.'], '20ff4652': ['Horarios'],
                      '01ebd087': 'Sí, por correo electrónico'}.items()}}
    importacion.importar(form_real, FuenteMemoria([r]))
    p = Prospecto.objects.get()
    assert p.plantel == 'tultepec' and p.modalidad == 'sabatino' and p.canal_informacion == 'correo'
    assert sorted(p.carreras.values_list('nombre', flat=True)) == ['Idiomas', 'Pedagogía']
    prepa = p.preparatoria
    assert prepa.por_revisar and prepa.lat is None and prepa.nombre == 'Esc. Prep. Oficial Núm. 45'
    # Otro alumno la escribe distinto: cae en la misma (clave «45»).
    assert Preparatoria.resolver('Prepa Oficial No 45') == prepa


def test_unir_preparatorias_y_las_siguientes_caen_solas(f_alumno, evento, prepa):
    importar(f_alumno, alumno('a1', preparatoria='CBT Cuautitlan Izcalli', edad='18'),
             alumno('a2', 'Luis Pérez Ruiz', preparatoria='C.B.T. de Izcalli', edad='18', evento=None))
    nuevas = list(Preparatoria.objects.filter(por_revisar=True))
    assert len(nuevas) == 2
    queda = preparatorias.unir(nuevas)
    assert Preparatoria.objects.filter(por_revisar=True).count() == 1 and len(queda.alias) == 1
    assert Prospecto.objects.filter(preparatoria=queda).count() >= 1
    importar(f_alumno, alumno('a3', 'Rosa Díaz Gil', preparatoria='C.B.T. de Izcalli', edad='18', evento=None))
    assert Prospecto.objects.get(nombre_aspirante='Rosa Díaz Gil').preparatoria == queda


def test_ubicar_preparatoria_en_el_mapa(client, f_alumno, evento):
    importar(f_alumno, alumno('a1', preparatoria='Prepa Nueva Tultepec', edad='18', evento=None))
    nueva = Preparatoria.objects.get(por_revisar=True)
    c = client
    c.force_login(usuario('ad@x.mx', 'Admisiones'))
    html = c.get('/admin/herramientas/preparatorias/ubicar/').content.decode()
    assert 'Prepa Nueva Tultepec' in html and 'mx-estados.geojson' in html
    r = c.post('/admin/herramientas/preparatorias/ubicar/', {'prepa': nueva.pk, 'lat': '40.4', 'lng': '-3.7'})
    assert r.status_code == 400 and 'fuera de México' in r.json()['error']
    r = c.post('/admin/herramientas/preparatorias/ubicar/', {'prepa': nueva.pk, 'lat': '19.685', 'lng': '-99.128', 'municipio': 'Tultepec'})
    nueva.refresh_from_db()
    assert r.json()['ok'] and float(nueva.lat) == 19.685 and not nueva.por_revisar and nueva.municipio == 'Tultepec'
    html = c.get('/admin/herramientas/mapa/?plantel=cuautitlan').content.decode()
    assert 'Prepa Nueva Tultepec' in html
    assert c.force_login(usuario('pr@x.mx', 'Promotor', 'P9')) is None
    assert c.get('/admin/herramientas/preparatorias/ubicar/').status_code == 403


def test_reprocesar_respuestas_al_cambiar_el_mapeo(f_alumno, evento):
    f_alumno.mapeo_campos = {k: v for k, v in f_alumno.mapeo_campos.items() if v != 'plantel'}
    f_alumno.save()
    importar(f_alumno, alumno('a1', edad='18'))
    assert Prospecto.objects.get().plantel == ''
    f_alumno.mapeo_campos['q_plantel'] = 'plantel'
    f_alumno.save()
    assert importacion.reprocesar(f_alumno) == 1
    assert Prospecto.objects.get().plantel == 'cuautitlan'


def test_actualizar_catalogo_quita_codigos_retirados_del_mapeo(f_alumno, evento):
    f_alumno.mapeo_campos['q_viejo'] = 'quiere_asesor'
    f_alumno.save()
    Configuracion.guardar('catalogo.version', 1)
    semillas.actualizar_por_catalogo()  # el Form no es real (sin Google): se marca el error, no truena
    assert Configuracion.obtener('catalogo.version') == semillas.VERSION_CATALOGO


def test_registrar_permiso_desde_la_respuesta(client, f_alumno, evento):
    importar(f_alumno, alumno('a1', edad='16', consentimiento_aviso_privacidad=None))
    r = Respuesta.objects.get()
    assert r.estado == EstadoRespuesta.CUARENTENA
    c = client
    c.force_login(usuario('ad@x.mx', 'Admisiones'))
    html = c.get(f'/admin/herramientas/respuestas/{r.pk}/').content.decode()
    assert 'Tiene 16 años' in html and 'Pedir el permiso del tutor' in html
    html = c.get(f'/admin/herramientas/respuestas/{r.pk}/?contacto=1').content.decode()
    assert 'Teléfono del aspirante' in html and Auditoria.objects.filter(accion='ver_contacto_para_permiso').exists()
    c.post(f'/admin/herramientas/respuestas/{r.pk}/', {'accion': 'permiso', 'tutor_nombre': 'Rosa López', 'medio': 'llamada'})
    assert Respuesta.objects.get().estado == EstadoRespuesta.CUARENTENA  # sin la casilla no cuenta
    c.post(f'/admin/herramientas/respuestas/{r.pk}/', {'accion': 'permiso', 'tutor_nombre': 'Rosa López',
                                                      'medio': 'llamada', 'confirmo': '1'})
    assert Respuesta.objects.get().estado == EstadoRespuesta.VALIDA
    assert Auditoria.objects.filter(accion='registrar_permiso_tutor').exists()


def test_solo_un_administrador_activa_el_aviso_en_el_form(client, f_alumno, evento):
    importar(f_alumno, alumno('a1', edad='19', consentimiento_aviso_privacidad=None))
    c = client
    c.force_login(usuario('ad@x.mx', 'Admisiones'))
    datos = {'accion': 'permisos', 'aviso_activo': '1', 'aviso_url': 'https://udcm.mx/aviso', 'confirmo': '1'}
    assert c.post('/admin/herramientas/scoring/', datos).status_code == 403
    c.force_login(User.objects.create_superuser('r@x.mx', 'r@x.mx', 'Clave-de-prueba-123'))
    c.post('/admin/herramientas/scoring/', dict(datos, confirmo=''))
    assert not Configuracion.obtener('permisos.aviso_en_form')  # sin confirmar no se activa
    c.post('/admin/herramientas/scoring/', datos)
    assert Configuracion.obtener('permisos.aviso_en_form')['activo'] and Prospecto.objects.get().consentimiento


def test_reporte_con_las_preguntas_reales(client, f_alumno, evento):
    importar(f_alumno, alumno('a1', edad='18'), alumno('a2', 'Luis Pérez Ruiz', edad='18', plantel='Universidad de Tultepec',
                                                         recibir_informacion='No, gracias'))
    c = client
    c.force_login(User.objects.create_superuser('r@x.mx', 'r@x.mx', 'Clave-de-prueba-123'))
    html = c.get('/admin/herramientas/reporte/?desde=2026-01-01&hasta=2026-12-31').content.decode()
    assert 'Carreras en Tultepec' in html and 'Qué quieren conocer' in html and 'Pidieron información' in html
    r = c.get('/admin/herramientas/reporte/?desde=2026-01-01&hasta=2026-12-31&excel=1')
    assert r['Content-Type'].startswith('application/vnd.openxmlformats')
    html = c.get('/admin/herramientas/cola/').content.decode()
    assert 'Ana Sofía' in html and 'Luis Pérez' not in html and 'No, gracias' in html


# ------------------------------------------------------------- encuesta para padres de familia (real)
ESTRUCTURA_TUTOR = {
    'a1': '¡AVISO DE PRIVACIDAD!', 'a2': 'Nombre completo del padre, madre o tutor ', 'a3': 'Nombre completo del aspirante ',
    'a4': 'Teléfono del padre, madre o tutor', 'a5': 'Correo electrónico del padre, madre o tutor',
    'a6': '¿Qué plantel te gustaría estudiar?',
    'c1': '¿Qué carrera le interesa estudiar a su hijo(a)? ', 'm1': '¿Qué modalidad de estudio consideran más conveniente para su hijo(a)?  ',
    'c2': '¿Qué carrera le interesa estudiar a su hijo(a)? ', 'm2': '¿Qué modalidad de estudio consideran más conveniente para su hijo(a)?  ',
    'b1': '  ¿Qué tipo de universidad están considerando para su hijo(a)?  ',
    'b2': '¿Qué aspectos consideran más importantes al elegir una universidad?  ',
    'b3': '¿Cuál es su principal preocupación respecto al ingreso de su hijo(a) a la universidad?  ',
    'b4': '¿Qué tipo de apoyo económico considera más importante para la educación de su hijo(a)?  ',
    'b5': '¿Cuándo tienen previsto que su hijo(a) ingrese a la universidad?  ',
    'b6': '¿Cuál es el principal motivo por el que prefiere esta ubicación? ',
    'b7': '¿Qué información le gustaría conocer sobre esta universidad? ',
    'b8': '¿Le gustaría recibir información personalizada sobre carreras, becas y procesos de inscripción?  ',
}


class FuenteTutor(FuenteMemoria):
    def estructura(self, formulario):
        return ESTRUCTURA_TUTOR


def test_mapeo_propuesto_con_la_encuesta_de_padres():
    f = Formulario.objects.create(nombre='ENCUESTA PARA PADRES', tipo=Cuestionario.TUTOR, google_form_id='demo-padres')
    codigos = {p['question_id']: p['codigo'] for p in importacion.proponer_mapeo(f, FuenteTutor())}
    assert codigos == {
        'a1': 'consentimiento_aviso_privacidad', 'a2': 'tutor_nombre', 'a3': 'nombre_aspirante', 'a4': 'tutor_telefono',
        'a5': 'tutor_correo', 'a6': 'plantel', 'c1': 'carrera', 'm1': 'modalidad', 'c2': 'carrera', 'm2': 'modalidad',
        'b1': 'tipo_universidad', 'b2': 'factor_eleccion', 'b3': 'preocupacion', 'b4': 'apoyo_economico',
        'b5': 'cuando_ingresa', 'b6': 'motivo_ubicacion', 'b7': 'quiere_conocer', 'b8': 'recibir_informacion'}


def test_la_familia_da_el_permiso_y_suma_lo_suyo(f_alumno, f_tutor, evento):
    from .conftest import tutor
    importar(f_alumno, alumno('a1', edad='17', consentimiento_aviso_privacidad=None, modalidad='Semanal'))
    p = Prospecto.objects.get()
    assert not p.consentimiento and p.score == 100  # sin la familia, sus reglas no cuentan
    importar(f_tutor, tutor('t1', evento=None, modalidad='Escolarizada', cuando_ingresa='Dentro de un año.',
                            apoyo_economico='Facilidades de pago.'))
    p = Prospecto.objects.get()
    assert p.consentimiento and p.origen_consentimiento == 'tutor'
    assert 'ingresa_proximo_ciclo' not in p.score_detalle and p.score < 100
    assert {'largo_plazo', 'sensible_beca'} <= set(p.segmentos)
    from prospectos.servicios import reportes
    filas = {f['codigo']: f for t in reportes.comparativo(p)['temas'] for f in t['filas']}
    assert filas['modalidad']['coinciden']  # «Semanal» (alumno) = «Escolarizada» (familia)
    assert filas['carrera']['coinciden'] and filas['cuando_ingresa']['tutor'] == ['Dentro de un año']


def test_alumno_no_quiere_pero_la_familia_si(f_alumno, f_tutor, evento):
    from .conftest import tutor
    importar(f_alumno, alumno('a1', edad='18', recibir_informacion='No, gracias'))
    assert Prospecto.objects.get().no_contactar
    importar(f_tutor, tutor('t1', evento=None))
    p = Prospecto.objects.get()
    assert not p.no_contactar and p.canal_informacion == 'si'  # se habla con la familia


# ------------------------------------------------------------- mapa: Google Maps u OpenStreetMap
LLAVE = 'AIza' + 'x' * 35


def test_configurar_google_maps_solo_admin_y_validando_la_llave(client):
    c = client
    c.force_login(usuario('co@x.mx', 'Coordinación'))
    assert c.get('/admin/herramientas/mapa/configurar/').status_code == 403
    c.force_login(User.objects.create_superuser('r@x.mx', 'r@x.mx', 'Clave-de-prueba-123'))
    html = c.get('/admin/herramientas/mapa/configurar/').content.decode()
    assert 'Places API (New)' in html and 'http://testserver/*' in html
    c.post('/admin/herramientas/mapa/configurar/', {'llave': 'mi-llave', 'tipo': 'roadmap'})
    assert not Configuracion.obtener('mapa.google')  # formato inválido: no se guarda
    c.post('/admin/herramientas/mapa/configurar/', {'llave': LLAVE, 'tipo': 'hybrid'})
    assert Configuracion.obtener('mapa.google') == {'llave': LLAVE, 'tipo': 'hybrid'}
    r = c.get('/admin/herramientas/mapa/')
    html = r.content.decode()
    assert LLAVE in html and 'Leaflet.GoogleMutant.js' in html
    assert r['Referrer-Policy'] == 'strict-origin-when-cross-origin'  # Google valida la llave por el origen
    assert c.get('/admin/prospectos/prospecto/')['Referrer-Policy'] == 'same-origin'  # el resto, igual que antes
    c.post('/admin/herramientas/mapa/configurar/', {'llave': '', 'tipo': 'roadmap'})
    assert LLAVE not in c.get('/admin/herramientas/mapa/').content.decode()


def test_sin_llave_el_mapa_es_openstreetmap(client):
    from prospectos.views import TILES
    t = TILES()
    assert t['google'] is None and 'tile.openstreetmap.org' in t['url']
