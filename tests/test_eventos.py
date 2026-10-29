"""Eventos: cada respuesta llega a su evento aunque el Form no tenga «Código de evento»; solicitud y reporte."""
import datetime as dt

import pytest

from django.contrib.auth.models import User

from prospectos.models import Evento, Preparatoria, Respuesta
from prospectos.servicios import eventos

from .conftest import BASE, alumno, importar, tutor

DIA = BASE.date()


def _evento(prepa, **kw):
    kw.setdefault('estado', 'confirmado')
    return Evento.objects.create(preparatoria=prepa, fecha=DIA, **kw)


def test_sin_codigo_se_asigna_por_prepa_y_fecha(f_alumno, f_tutor, prepa, prepa2):
    e1, _ = _evento(prepa), _evento(prepa2)
    importar(f_alumno, alumno('a1', 'Ana López García', evento=None, preparatoria='prepa uno'))
    assert Respuesta.objects.get().evento == e1
    # Encuesta de padres sin prepa con DOS eventos ese día: no se adivina.
    importar(f_tutor, tutor('t1', 'Ana López García', evento=None))
    assert Respuesta.objects.get(cuestionario='TUTOR').evento is None


def test_familia_el_dia_del_unico_evento(f_tutor, prepa):
    e = _evento(prepa)
    importar(f_tutor, tutor('t1', 'Luis Mora Díaz', evento=None))
    assert Respuesta.objects.get().evento == e


def test_otro_dia_no_cuenta_para_el_evento(f_alumno, prepa):
    Evento.objects.create(preparatoria=prepa, fecha=DIA + dt.timedelta(days=1), estado='confirmado')
    importar(f_alumno, alumno('a1', evento=None))
    assert Respuesta.objects.get().evento is None


def test_qr_permanente_de_la_prepa(f_alumno, prepa, prepa2):
    e = _evento(prepa)
    # El alumno escribió otra prepa, pero escaneó el QR permanente de la Prepa Uno: manda el QR.
    importar(f_alumno, alumno('a1', evento=prepa.codigo_qr, preparatoria='Prepa Dos'))
    assert Respuesta.objects.get().evento == e
    assert Preparatoria.por_codigo_qr(prepa.codigo_qr) == prepa and Preparatoria.por_codigo_qr('EV1') is None


def test_cancelado_no_recibe_respuestas(f_alumno, prepa):
    _evento(prepa).delete()
    Evento.objects.create(preparatoria=prepa, fecha=DIA, estado='cancelado')
    importar(f_alumno, alumno('a1', evento=None))
    assert Respuesta.objects.get().evento is None


def test_reasignar_lo_que_llego_antes(f_alumno, prepa):
    importar(f_alumno, alumno('a1', evento=None))
    assert Respuesta.objects.get().evento is None
    e = _evento(prepa)  # el evento se capturó después de que llegaran las respuestas
    assert eventos.reatribuir() == 1
    r = Respuesta.objects.get()
    assert r.evento == e and r.prospecto.evento == e


def test_solicitud_reporte_y_qr_permanente(client, f_alumno, f_tutor, prepa, promotor):
    e = _evento(prepa, estado='por_solicitar', promotor=promotor, hora_inicio=dt.time(10), hora_fin=dt.time(12), dirigido_a='Mtra. Laura Ríos',
                grupos='6.° semestre', requerimientos='Un salón con proyector\nAcceso a los grupos', alumnos_asistentes=40,
                meta_registros=20, costo=500)
    importar(f_alumno, alumno('a1', 'Juan Carlos Pérez López', evento=None), alumno('a2', 'Sara Ruiz Gil', evento=None))
    importar(f_tutor, tutor('t1', 'Juan Pérez', evento=None, tutor_nombre='Rosa López'))
    client.force_login(User.objects.create_superuser('e@x.mx', 'e@x.mx', 'Clave-de-prueba-123'))
    html = client.get(f'/admin/herramientas/evento/{e.pk}/solicitud/').content.decode()
    assert 'Mtra. Laura Ríos' in html and 'Un salón con proyector' in html and 'Difusión educativa' in html
    assert 'hoja-membretada.jpg' in html and 'Ing. César Hernández López' in html  # formato oficial de la UDC
    assert 'menores de edad' in html  # la carta avisa cómo se tratan los datos de menores
    client.post(f'/admin/herramientas/evento/{e.pk}/solicitud/', {'accion': 'firma', 'nombre': 'Lic. Mario Paz', 'cargo': 'Coordinador'})
    client.post(f'/admin/herramientas/evento/{e.pk}/solicitud/', {'accion': 'solicitado'})
    e.refresh_from_db()
    assert e.estado == 'solicitado' and 'Lic. Mario Paz' in client.get(f'/admin/herramientas/evento/{e.pk}/solicitud/').content.decode()
    d = eventos.reporte(e)
    assert d['alumnos'] == 2 and d['familias'] == 1 and d['unidas'] == 1 and d['tasa'] == 5 and d['costo_por_registro'] == 250
    html = client.get(f'/admin/herramientas/evento/{e.pk}/reporte/').content.decode()
    assert 'Reporte final del evento' in html and 'Juan Carlos Pérez López' not in html  # sin nombres por omisión
    assert 'Juan Carlos Pérez López' in client.get(f'/admin/herramientas/evento/{e.pk}/reporte/?nombres=1').content.decode()
    html = client.get(f'/admin/herramientas/preparatoria/{prepa.pk}/qr/').content.decode()
    assert prepa.codigo_qr in html and 'data:image/svg+xml' in html
    assert 'Solicitud' in client.get('/admin/prospectos/evento/').content.decode()


def test_cartas_de_beca_con_folio(client, prepa, promotor):
    from django.core.exceptions import ValidationError
    from prospectos.models import Auditoria
    from prospectos.servicios import cartas
    assert cartas.de_la_prepa('Preparatoria Oficial No. 45') == ('de', 'la Preparatoria Oficial No. 45')
    assert cartas.de_la_prepa('CBT No. 2 Cuautitlán') == ('del', 'CBT No. 2 Cuautitlán')
    assert cartas.de_la_prepa('Isidro Fabela') == ('de', 'la Preparatoria Isidro Fabela')
    e = _evento(prepa, promotor=promotor, beca_carta='especial', beca_porcentaje=30, beca_hojas=4)
    with pytest.raises(ValidationError) as err:
        e.clean()
    assert 'beca_vigencia' in err.value.message_dict  # sin vigencia, la beca sería para siempre
    client.force_login(User.objects.create_superuser('b@x.mx', 'b@x.mx', 'Clave-de-prueba-123'))
    r = client.get(f'/admin/herramientas/evento/{e.pk}/becas/')
    assert r.status_code == 302 and f'/evento/{e.pk}/change/' in r['Location']
    e.beca_vigencia = dt.date(2026, 12, 31)
    e.save()
    html = client.get(f'/admin/herramientas/evento/{e.pk}/becas/').content.decode()
    assert html.count('class="carta"') == 4 and f'{e.codigo}-004' in html and 'BECA ESPECIAL DEL 30%' in html
    assert 'Vigencia: diciembre 2026' in html and 'de la Preparatoria Prepa Uno' not in html and 'de la Prepa Uno' in html
    html = client.get(f'/admin/herramientas/evento/{e.pk}/becas/?desde=3&hasta=99').content.decode()
    assert html.count('class="carta"') == 2 and f'{e.codigo}-003' in html and f'{e.codigo}-002' not in html
    assert Auditoria.objects.filter(accion='cartas_beca').count() == 2
    e.beca_carta, e.beca_inicio = 'regularizacion', dt.date(2027, 1, 1)
    e.save()
    html = client.get(f'/admin/herramientas/evento/{e.pk}/becas/').content.decode()
    assert 'ENERO DE 2027' in html and 'próximo mes de enero' in html and 'Regularización de estudios' in html
    # El promotor imprime las de su evento; otro promotor no.
    client.force_login(promotor)
    assert client.get(f'/admin/herramientas/evento/{e.pk}/becas/').status_code == 200
    from .conftest import usuario
    client.force_login(usuario('otro2@x.mx', 'Promotor', 'P09'))
    assert client.get(f'/admin/herramientas/evento/{e.pk}/becas/').status_code == 403
