"""Calendario de Admisiones: actividades, visitas a prepas, llamadas que vencen y exportación .ics."""
import datetime as dt

from django.contrib.auth.models import User
from django.utils import timezone

from prospectos.models import Actividad, Evento
from prospectos.servicios import calendario

from .conftest import usuario

URL = '/admin/herramientas/calendario/'


def _admin(client):
    u = User.objects.create_superuser('c@x.mx', 'c@x.mx', 'Clave-de-prueba-123')
    client.force_login(u)
    return u


def test_mes_muestra_eventos_actividades_de_varios_dias(prepa, promotor):
    hoy = timezone.localdate()
    Evento.objects.create(codigo='C1', preparatoria=prepa, promotor=promotor, fecha=hoy, hora_inicio=dt.time(9), estado='confirmado')
    Actividad.objects.create(titulo='Inscripciones', tipo='inscripciones', fecha=hoy, fecha_fin=hoy + dt.timedelta(days=2))
    m = calendario.mes(hoy.year, hoy.month)
    dias = {d['fecha']: d for s in m['semanas'] for d in s}
    assert [c['clase'] for c in dias[hoy]['cosas']] == ['evento', 'actividad']  # con hora primero
    assert dias[hoy]['hoy'] and all(len(s) == 7 for s in m['semanas'])
    assert any(c['titulo'] == 'Inscripciones' for c in dias[hoy + dt.timedelta(days=2)]['cosas'])
    assert not any(c['titulo'] == 'Inscripciones' for c in dias.get(hoy + dt.timedelta(days=3), {'cosas': []})['cosas'])


def test_crear_editar_y_borrar_actividad(client):
    _admin(client)
    hoy = timezone.localdate()
    html = client.get(f'{URL}?dia={hoy:%Y-%m-%d}').content.decode()
    assert 'Nueva actividad' in html and f'value="{hoy:%Y-%m-%d}"' in html
    r = client.post(URL, {'accion': 'guardar', 'titulo': 'Open house', 'tipo': 'open_house', 'fecha': f'{hoy:%Y-%m-%d}',
                          'hora_inicio': '10:00', 'hora_fin': '09:00'})
    assert r.status_code == 200 and 'va después' in r.content.decode() and not Actividad.objects.exists()
    r = client.post(URL, {'accion': 'guardar', 'titulo': 'Open house', 'tipo': 'open_house', 'fecha': f'{hoy:%Y-%m-%d}',
                          'hora_inicio': '10:00', 'hora_fin': '13:00', 'lugar': 'Auditorio'})
    assert r.status_code == 302
    a = Actividad.objects.get()
    assert a.creado_por.username == 'c@x.mx'
    assert 'Open house' in client.get(URL).content.decode()
    client.post(URL, {'accion': 'guardar', 'pk': a.pk, 'titulo': 'Open house Tultepec', 'tipo': 'open_house', 'fecha': f'{hoy:%Y-%m-%d}'})
    a.refresh_from_db()
    assert a.titulo == 'Open house Tultepec' and a.hora_inicio is None
    client.post(URL, {'accion': 'borrar', 'pk': a.pk})
    assert not Actividad.objects.exists()


def test_promotor_ve_solo_sus_visitas_y_no_edita(client, prepa, prepa2, promotor):
    otro = usuario('otro@x.mx', 'Promotor', 'P02')
    hoy = timezone.localdate()
    Evento.objects.create(codigo='M1', preparatoria=prepa, promotor=promotor, fecha=hoy)
    Evento.objects.create(codigo='M2', preparatoria=prepa2, promotor=otro, fecha=hoy)
    client.force_login(promotor)
    html = client.get(URL).content.decode()
    assert 'Prepa Uno' in html and 'Prepa Dos' not in html and 'Nueva actividad' not in html
    assert client.post(URL, {'accion': 'guardar', 'titulo': 'x', 'tipo': 'otro', 'fecha': f'{hoy:%Y-%m-%d}'}).status_code == 403
    assert 'Prepa Dos' not in client.get(f'{URL}?ics=1').content.decode()


def test_ics_valido(client, prepa, promotor):
    _admin(client)
    hoy = timezone.localdate()
    Evento.objects.create(codigo='I1', preparatoria=prepa, promotor=promotor, fecha=hoy, hora_inicio=dt.time(9), hora_fin=dt.time(11))
    Evento.objects.create(codigo='I2', preparatoria=prepa, promotor=promotor, fecha=hoy, estado='cancelado')
    Actividad.objects.create(titulo='Examen de admisión, grupo «A»; turno matutino con una descripción muy larga que hay que partir',
                             tipo='examen', fecha=hoy, fecha_fin=hoy + dt.timedelta(days=1))
    r = client.get(f'{URL}?ics=1')
    assert r['Content-Type'].startswith('text/calendar') and 'attachment' in r['Content-Disposition']
    t = r.content.decode()
    assert t.count('BEGIN:VEVENT') == 2 and 'UID:evento-' in t and '\\,' in t and '\\;' in t
    assert all(len(l.encode()) <= 75 for l in t.split('\r\n'))
    assert f'DTEND;VALUE=DATE:{hoy + dt.timedelta(days=2):%Y%m%d}' in t  # fin exclusivo


def test_llamadas_vencidas_cuentan_hoy():
    from prospectos.models import Prospecto, Seguimiento, TipoSeguimiento
    p = Prospecto.objects.create(nombre_aspirante='Ana López', consentimiento=True)
    ahora, hoy = timezone.now(), timezone.localdate()
    for horas in (-72, 1, 48):
        Seguimiento.objects.create(prospecto=p, tipo=TipoSeguimiento.TAREA, vence_en=ahora + dt.timedelta(hours=horas))
    Seguimiento.objects.create(prospecto=p, tipo=TipoSeguimiento.TAREA, vence_en=ahora, completada_en=ahora)
    t = calendario.tareas_por_dia(hoy, hoy + dt.timedelta(days=5))
    assert t[timezone.localtime(ahora + dt.timedelta(hours=1)).date()] >= 1 and t[hoy] >= 1 and sum(t.values()) == 3 and t[timezone.localtime(ahora + dt.timedelta(hours=48)).date()] == 1
    assert calendario.vencidas() == 1
