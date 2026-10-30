"""Avisos (campanita): agrupación, sin repetir, preferencias, privacidad y pantallas."""
import datetime as dt

from django.contrib.auth.models import User
from django.utils import timezone

from prospectos.models import Configuracion, Evento, Notificacion, Prospecto, Respaldo, Seguimiento, TipoAviso, TipoSeguimiento
from prospectos.servicios import avisos

from .conftest import alumno, importar, usuario

URL = '/admin/herramientas/avisos/'


def _admin(client=None):
    u = User.objects.create_superuser('jefa@x.mx', 'jefa@x.mx', 'Clave-de-prueba-123')
    if client:
        client.force_login(u)
    return u


def test_misma_clave_no_se_repite_y_se_actualiza_la_cifra(promotor):
    a = avisos.avisar(promotor, TipoAviso.VENCIDAS, 'vencidas:hoy', 'Tienes 3', cantidad=3)
    assert a.es_nuevo
    b = avisos.avisar(promotor, TipoAviso.VENCIDAS, 'vencidas:hoy', 'Tienes 5', cantidad=5)
    assert b.pk == a.pk and not b.es_nuevo and Notificacion.objects.get().cantidad == 5
    Notificacion.objects.update(leida_en=timezone.now())
    assert avisos.avisar(promotor, TipoAviso.VENCIDAS, 'vencidas:hoy', 'Tienes 6', cantidad=6) is None  # ya la leyó hoy
    assert Notificacion.objects.count() == 1


def test_acumular_suma_mientras_no_se_lea(promotor):
    avisos.avisar(promotor, TipoAviso.ASIGNADO, 'k', 't', acumular=True)
    avisos.avisar(promotor, TipoAviso.ASIGNADO, 'k', 't', cantidad=2, acumular=True)
    assert Notificacion.objects.get().cantidad == 3
    Notificacion.objects.update(leida_en=timezone.now())
    avisos.avisar(promotor, TipoAviso.ASIGNADO, 'k', 't', acumular=True)
    assert Notificacion.objects.count() == 2  # leído: empieza uno nuevo


def test_preferencias_apagan_menos_los_del_sistema(promotor):
    avisos.guardar_preferencias(promotor, {'evento', 'sistema'})
    assert avisos.apagados(promotor) == {'asignado', 'vencidas'}
    assert avisos.avisar(promotor, TipoAviso.VENCIDAS, 'x', 't') is None
    assert avisos.avisar(promotor, TipoAviso.EVENTO, 'y', 't')
    avisos.guardar_preferencias(promotor, set())
    assert avisos.avisar(promotor, TipoAviso.SISTEMA, 'z', 't')  # no se puede apagar


def test_usuario_inactivo_no_recibe(promotor):
    promotor.is_active = False
    promotor.save()
    assert avisos.avisar(promotor, TipoAviso.EVENTO, 'y', 't') is None


def test_aspirantes_de_mis_visitas_se_siguen_por_id_no_por_fecha(f_alumno, evento, promotor):
    assert avisos.registrados_en_mis_visitas() == 0  # primera vez: marca el punto de partida
    # La respuesta es de septiembre (la PC estuvo apagada): por fecha se perdería.
    importar(f_alumno, alumno('a1', evento='EV1'), alumno('a2', nombre='Luis Pérez Soto', evento='EV1', minutos=5))
    assert Prospecto.objects.filter(promotor=promotor).count() == 2
    assert avisos.registrados_en_mis_visitas() == 2
    n = Notificacion.objects.get(usuario=promotor)
    assert n.tipo == 'asignado' and n.cantidad == 2 and 'Se registraron 2 aspirantes' in n.titulo
    assert avisos.registrados_en_mis_visitas() == 0  # no repite


def test_avisos_no_guardan_nombres(f_alumno, evento, promotor):
    avisos.registrados_en_mis_visitas()
    importar(f_alumno, alumno('a1', nombre='Ana Sofía López García'))
    avisos.registrados_en_mis_visitas()
    p = Prospecto.objects.get()
    avisos.asignado(promotor, p, por=_admin())
    for n in Notificacion.objects.all():
        assert 'Ana' not in n.titulo + n.detalle + n.url


def test_asignar_desde_la_ficha_avisa_al_asesor_pero_no_a_uno_mismo(client, f_alumno, evento, promotor):
    jefa = _admin(client)
    importar(f_alumno, alumno('a1'))
    p = Prospecto.objects.get()
    url = f'/admin/prospectos/prospecto/{p.pk}/change/'
    datos = {'estatus': p.estatus, 'asesor': promotor.pk, 'seguimientos-TOTAL_FORMS': '0', 'seguimientos-INITIAL_FORMS': '0'}
    r = client.post(url, datos)
    assert r.status_code == 302, r.content.decode()[:2000]
    n = Notificacion.objects.get(usuario=promotor)
    assert n.titulo == 'Te asignaron un aspirante' and n.url.endswith(f'/{p.pk}/change/')
    client.post(url, datos | {'asesor': jefa.pk})
    assert not Notificacion.objects.filter(usuario=jefa).exists()


def test_vencidas_un_aviso_por_persona_con_la_cifra(f_alumno, evento, promotor):
    importar(f_alumno, alumno('a1', edad='19'), alumno('a2', nombre='Luis Pérez Soto', minutos=3, edad='19'))  # mayores: con permiso
    jefa = _admin()
    pasado = timezone.now() - dt.timedelta(hours=3)
    for p in Prospecto.objects.all():
        Seguimiento.objects.create(prospecto=p, usuario=promotor, tipo=TipoSeguimiento.TAREA, vence_en=pasado)
    Seguimiento.objects.create(prospecto=Prospecto.objects.first(), tipo=TipoSeguimiento.TAREA, vence_en=pasado)
    assert avisos.vencidas_del_dia() == 1
    n = Notificacion.objects.get(usuario=promotor)
    assert n.titulo == 'Tienes 2 llamadas vencidas'
    assert Notificacion.objects.get(usuario=jefa).titulo == '1 llamada vencida sin asesor'
    assert avisos.vencidas_del_dia() == 0


def test_visita_de_manana_y_permiso_sin_pedir(prepa, promotor):
    manana = timezone.localdate() + dt.timedelta(days=1)
    Evento.objects.create(codigo='M1', preparatoria=prepa, promotor=promotor, fecha=manana, hora_inicio=dt.time(9),
                          estado='confirmado', beca_carta='especial', beca_porcentaje=30, beca_hojas=120,
                          beca_vigencia=manana + dt.timedelta(days=60))
    Evento.objects.create(codigo='M2', preparatoria=prepa, promotor=promotor, fecha=manana + dt.timedelta(days=4))
    Evento.objects.create(codigo='M3', preparatoria=prepa, promotor=promotor, fecha=manana, estado='cancelado')
    assert avisos.visitas_proximas() == 2
    titulos = set(Notificacion.objects.values_list('titulo', 'detalle'))
    assert ('Mañana: visita a Prepa Uno', 'Plática informativa a las 09:00. Lleva 120 cartas de beca impresas.') in titulos
    assert ('Falta pedir permiso a Prepa Uno', 'La visita es en 5 días y la solicitud no se ha enviado.') in titulos
    assert avisos.visitas_proximas() == 0


def test_problemas_del_sistema_solo_a_administradores(promotor):
    jefa = _admin()
    Respaldo.objects.create(archivo='r.gz', estado='error', mensaje='disco lleno')
    # falló el último, no hay uno bueno en 48 h y los respaldos no se copian fuera de la PC
    assert avisos.problemas_del_sistema() == 3
    assert Notificacion.objects.filter(usuario=jefa, titulo='Los respaldos solo están en esta computadora').exists()
    assert not Notificacion.objects.filter(usuario=promotor).exists()
    assert set(Notificacion.objects.filter(usuario=jefa).values_list('tipo', flat=True)) == {'sistema'}
    assert avisos.problemas_del_sistema() == 0
    Respaldo.objects.create(archivo='r2.gz', estado='ok')  # se arregló solo
    avisos.problemas_del_sistema()
    assert avisos.no_leidas(jefa) == 1 and Notificacion.objects.filter(usuario=jefa).count() == 3  # sigue sin copia externa


def test_limpiar_borra_los_viejos(promotor):
    viejo = timezone.now() - dt.timedelta(days=avisos.DIAS_GUARDADOS + 1)
    Notificacion.objects.create(usuario=promotor, tipo='evento', clave='v', titulo='v', actualizada_en=viejo)
    avisos.avisar(promotor, TipoAviso.EVENTO, 'n', 'n')
    assert avisos.limpiar() == 1 and Notificacion.objects.count() == 1


def test_campanita_panel_abrir_y_leer_todo(client, promotor):
    client.force_login(promotor)
    a = avisos.avisar(promotor, TipoAviso.EVENTO, 'a', 'Visita mañana', url='/admin/herramientas/calendario/')
    avisos.avisar(promotor, TipoAviso.EVENTO, 'b', 'Otra', url='https://malo.example.com/')
    html = client.get('/admin/').content.decode()
    assert 'id="av-campana"' in html and 'class="av-cifra">2<' in html
    assert client.get(URL + 'contador/').json() == {'sin_leer': 2}
    assert 'Visita mañana' in client.get(URL + 'panel/').content.decode()
    r = client.get(f'{URL}{a.pk}/')
    assert r.status_code == 302 and r.url == '/admin/herramientas/calendario/'
    otra = Notificacion.objects.get(clave='b')
    assert client.get(f'{URL}{otra.pk}/').url == URL  # nunca redirige fuera del sistema
    assert client.get(URL + 'contador/').json() == {'sin_leer': 0}
    avisos.avisar(promotor, TipoAviso.EVENTO, 'c', 'Tercera')
    assert client.post(URL + 'leer-todo/', HTTP_X_REQUESTED_WITH='fetch').json() == {'sin_leer': 0}


def test_no_se_pueden_abrir_avisos_ajenos(client, promotor):
    otro = usuario('otro@x.mx', 'Promotor', 'P02')
    a = avisos.avisar(otro, TipoAviso.EVENTO, 'a', 'Privado')
    client.force_login(promotor)
    assert client.get(f'{URL}{a.pk}/').status_code == 404
    assert 'Privado' not in client.get(URL + '?ver=todos').content.decode()


def test_bandeja_guarda_preferencias(client, promotor):
    client.force_login(promotor)
    html = client.get(URL).content.decode()
    assert 'Qué avisos recibir' in html and 'Problemas del sistema' not in html  # no es admin
    client.post(URL, {'tipo': ['evento']})
    assert avisos.apagados(promotor) == {'asignado', 'vencidas'}


def test_revisar_marca_punto_de_partida_sin_avisar_historico(f_alumno, evento, promotor):
    importar(f_alumno, alumno('a1'))
    avisos.revisar()
    assert not Notificacion.objects.filter(usuario=promotor, tipo='asignado').exists()
    assert Configuracion.obtener('avisos.ultimo_prospecto') == Prospecto.objects.get().pk
