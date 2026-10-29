from datetime import datetime, timedelta, timezone as dt_tz

import pytest
from django.contrib.auth.models import Group, User

from prospectos.models import Cuestionario, Evento, Formulario, Perfil, Pregunta, Preparatoria
from prospectos.servicios import importacion, semillas
from prospectos.servicios.fuentes import FuenteMemoria

BASE = datetime(2026, 9, 1, 15, 0, tzinfo=dt_tz.utc)


@pytest.fixture(autouse=True)
def sistema(db, settings, tmp_path):
    settings.PROSPECTOS = dict(settings.PROSPECTOS, RESPALDOS_DIR=tmp_path / 'respaldos')
    semillas.preparar()


def api(rid, valores, minutos=0, fecha=None):
    return semillas._respuesta_api(rid, fecha or (BASE + timedelta(minutes=minutos)), valores)


@pytest.fixture
def prepa():
    return Preparatoria.objects.create(nombre='Prepa Uno', municipio='Toluca', lat=19.28, lng=-99.65, alumnos_estimados=200)


@pytest.fixture
def prepa2():
    return Preparatoria.objects.create(nombre='Prepa Dos', municipio='Metepec', lat=19.25, lng=-99.60, alumnos_estimados=100)


def usuario(nombre, rol, codigo=None, **extra):
    u = User.objects.create_user(nombre, nombre, 'Clave-de-prueba-123', is_staff=True, **extra)
    u.groups.add(Group.objects.get(name=rol))
    Perfil.objects.create(usuario=u, codigo_promotor=codigo)
    return u


@pytest.fixture
def promotor():
    return usuario('promotor@x.mx', 'Promotor', 'P01')


@pytest.fixture
def evento(prepa, promotor):
    return Evento.objects.create(codigo='EV1', preparatoria=prepa, promotor=promotor, meta_registros=50)


@pytest.fixture
def evento2(prepa2, promotor):
    return Evento.objects.create(codigo='EV2', preparatoria=prepa2, promotor=promotor)


def _form(tipo, fid):
    codigos = Pregunta.objects.filter(cuestionario=tipo).values_list('codigo', flat=True)
    return Formulario.objects.create(nombre=fid, tipo=tipo, google_form_id=fid,
                                     url_publica=f'https://docs.google.com/forms/d/e/{fid}/viewform',
                                     mapeo_campos={'q_' + c: c for c in codigos},
                                     campos_prellenado={'evento': 'entry.1', 'promotor': 'entry.2', 'token_familia': 'entry.3'})


@pytest.fixture
def f_alumno():
    return _form(Cuestionario.ALUMNO, 'form-alumno')


@pytest.fixture
def f_tutor():
    return _form(Cuestionario.TUTOR, 'form-tutor')


def importar(formulario, *respuestas):
    return importacion.importar(formulario, FuenteMemoria(list(respuestas)))


def alumno(rid='a1', nombre='Ana Sofía López García', evento='EV1', minutos=0, **v):
    datos = {'consentimiento_aviso_privacidad': 'Sí', 'nombre_completo': nombre, 'correo': f'{rid}@correo.mx',
             'edad': '17', 'telefono': f'55 1111 {sum(map(ord, rid)):04d}', 'preparatoria': 'Prepa Uno',
             'plantel': 'Universidad de Cuautitlán México', 'carrera': ['Derecho'], 'modalidad': 'Semanal',
             'factor_eleccion': ['Becas y descuentos.', 'Calidad educativa.'],
             'quiere_conocer': ['Requisitos de inscripción', 'Costos y colegiaturas'],
             'recibir_informacion': 'Sí, por WhatsApp', 'evento': evento}
    datos.update(v)
    return api(rid, {k: x for k, x in datos.items() if x is not None}, minutos)


ACEPTO_TUTOR = ('He leído y acepto el aviso de privacidad. Como padre, madre o tutor legal, otorgo mi consentimiento '
                'expreso para el tratamiento de los datos del menor a mi cargo.')


def tutor(rid='t1', nombre='Ana Sofía López García', evento='EV1', minutos=30, **v):
    datos = {'consentimiento_aviso_privacidad': ACEPTO_TUTOR, 'tutor_nombre': 'María García', 'tutor_correo': f'{rid}@papas.mx',
             'tutor_telefono': f'55 9999 {sum(map(ord, rid)):04d}', 'nombre_aspirante': nombre,
             'plantel': 'Universidad de Cuautitlán México', 'carrera': ['Derecho.'], 'modalidad': 'Escolarizada',
             'tipo_universidad': 'Privada.', 'factor_eleccion': ['Calidad académica.'], 'preocupacion': 'Costos educativos.',
             'apoyo_economico': 'Becas académicas.', 'cuando_ingresa': 'En el próximo ciclo escolar.',
             'motivo_ubicacion': 'Cercanía de domicilio', 'quiere_conocer': 'Proceso de inscripcíón.',
             'recibir_informacion': 'Sí, me interesa recibir información.', 'evento': evento}
    datos.update(v)
    return api(rid, {k: x for k, x in datos.items() if x is not None}, minutos)
