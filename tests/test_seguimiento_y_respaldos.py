from datetime import timedelta

import pytest
from django.utils import timezone

from prospectos.models import Estatus, Prospecto, Respaldo, Seguimiento, TipoSeguimiento
from prospectos.servicios import reportes, respaldos, seguimiento

from .conftest import alumno, importar, tutor


@pytest.fixture
def prospecto(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1'))
    importar(f_tutor, tutor('t1'))
    return Prospecto.objects.get()


def test_primer_contacto_avanza_embudo_y_nota_no(prospecto):
    seguimiento.registrar(prospecto, TipoSeguimiento.NOTA, 'nota')
    assert Prospecto.objects.get().estatus == Estatus.REGISTRADO
    seguimiento.registrar(prospecto, TipoSeguimiento.LLAMADA, 'llamé')
    p = Prospecto.objects.get()
    assert p.estatus == Estatus.CONTACTADO and p.ultimo_contacto_en


def test_tareas_automaticas_sin_duplicar_y_se_cierran(prospecto):
    Prospecto.objects.update(creado_en=timezone.now() - timedelta(days=10))
    assert seguimiento.generar_tareas_sin_contacto() == 1
    assert seguimiento.generar_tareas_sin_contacto() == 0
    seguimiento.registrar(Prospecto.objects.get(), TipoSeguimiento.WHATSAPP, 'hola')
    assert not Seguimiento.objects.filter(tipo=TipoSeguimiento.TAREA, completada_en__isnull=True).exists()


def test_embudo_acumulado(prospecto):
    seguimiento.cambiar_estatus(prospecto, Estatus.SOLICITO)
    e = {x['etapa']: x['total'] for x in reportes.Metricas().embudo()}
    assert e['Registrado'] == e['Contactado'] == e['Solicitó inscripción'] == 1 and e['Inscrito'] == 0


def test_url_prellenada_y_tarjetas_mismo_token(f_alumno, f_tutor, evento):
    url = f_alumno.url_prellenada({'evento': 'EV1', 'promotor': 'P01', 'token_familia': 'FX'})
    assert 'entry.1=EV1' in url and 'entry.2=P01' in url and 'entry.3=FX' in url and 'usp=pp_url' in url
    t = reportes.tarjetas(evento, 3)
    assert len(t) == 3 and len({x['token'] for x in t}) == 3
    for x in t:
        assert f"entry.3={x['token']}" in x['alumno']['url'] and f"entry.3={x['token']}" in x['tutor']['url']
        assert x['alumno']['qr'].startswith('data:image/svg+xml')


def test_conteo_en_vivo(prospecto, evento, f_alumno):
    importar(f_alumno, alumno('a9', 'Otro Menor Gómez', edad='15'))
    c = reportes.Metricas.conteo_evento(evento)
    assert c['alumnos'] == 2 and c['tutores'] == 1


@pytest.mark.django_db(transaction=True)
def test_respaldo_crear_verificar_restaurar_rotar(prospecto):
    r = respaldos.crear()
    assert r.estado == 'ok' and r.bytes > 0
    assert respaldos.verificar()['prospectos_prospecto'] == 1
    assert Respaldo.objects.get(pk=r.pk).verificado_en

    Prospecto.objects.all().delete()
    respaldos.restaurar(r.archivo)
    assert Prospecto.objects.count() == 1 and Prospecto.objects.get().correo == 'a1@correo.mx'

    import os
    ruta = respaldos.resolver(r.archivo)
    viejo = timezone.now().timestamp() - 30 * 86400
    os.utime(ruta, (viejo, viejo))
    assert respaldos.rotar() == 1 and not ruta.exists()


def test_respaldo_danado_no_pasa_la_verificacion(tmp_path):
    import gzip
    archivo = respaldos.directorio() / 'prospectos-20260101-000000.sqlite3.gz'
    with gzip.open(archivo, 'wb') as f:
        f.write(b'esto no es una base de datos' * 100)
    with pytest.raises(respaldos.ErrorRespaldo):
        respaldos.verificar(archivo.name)
