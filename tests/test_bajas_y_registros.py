import pytest
from django.contrib.auth.models import User

from prospectos.models import Notificacion, Prospecto, TipoAviso
from prospectos.servicios import avisos, reportes

from .conftest import alumno, importar, tutor, usuario


@pytest.fixture
def jefe(client):
    u = User.objects.create_superuser('jefe@x.mx', 'jefe@x.mx', 'Clave-larga-2026!')
    client.force_login(u)
    return u


def _baja(client, p, motivo='registro_de_prueba'):
    return client.post(f'/admin/herramientas/prospectos/{p.pk}/baja/', {'motivo': motivo, 'confirmo': 'BAJA'})


# --------------------------------------------------------------------------- bajas: apartado y cifra propia
def test_la_baja_sale_de_los_interesados_y_va_a_su_apartado(client, jefe, f_alumno, evento):
    importar(f_alumno, alumno('a1', edad='19'), alumno('a2', 'Bruno Díaz Torres', edad='19'))
    total_antes = reportes.Metricas().total()
    p = Prospecto.objects.get(nombre_aspirante='Bruno Díaz Torres')
    _baja(client, p)
    p.refresh_from_db()
    assert p.baja_en and p.baja_motivo == 'registro_de_prueba' and p.anonimizado_en
    assert reportes.Metricas().total() == total_antes - 1  # ya no cuenta como interesado
    assert not Prospecto.objects.reportables().filter(pk=p.pk).exists()
    assert Prospecto.objects.bajas().count() == 1
    client.get('/admin/')  # muestra el mensaje de la baja (con el nombre, una sola vez)
    html = client.get('/admin/herramientas/prospectos/bajas/').content.decode()
    assert f'Baja #{p.pk}' in html and 'Es una prueba o datos basura' in html and 'Bruno' not in html
    assert 'Baja #' not in client.get('/admin/herramientas/prospectos/bajas/?motivo=derecho_arco').content.decode()
    html = client.get('/admin/herramientas/reporte/').content.decode()
    assert '1 dado de baja en el periodo' in html


def test_anonimizados_por_tiempo_siguen_contando(f_alumno, evento):
    from prospectos.servicios import seguridad
    importar(f_alumno, alumno('a1', edad='19'))
    p = Prospecto.objects.get()
    seguridad.anonimizar(p, 'retencion_inactividad')
    assert Prospecto.objects.reportables().filter(pk=p.pk).exists()  # no es una baja: sigue en la estadística
    assert not Prospecto.objects.bajas().exists()


# --------------------------------------------------------------------------- un aviso por cada alumno que se registra
def _avisos_de(u):
    return list(Notificacion.objects.filter(usuario=u, tipo=TipoAviso.REGISTRO).order_by('pk'))


def test_cada_alumno_nuevo_llega_a_la_campanita(jefe, f_alumno, f_tutor, evento):
    admisiones = usuario('ad@x.mx', 'Admisiones')
    directivo = usuario('di@x.mx', 'Directivo')
    importar(f_alumno, alumno('a1'))  # primera lectura del Form: el histórico llega como un solo aviso
    primero = _avisos_de(jefe)
    assert len(primero) == 1 and 'registro nuevo' in primero[0].titulo
    importar(f_alumno, alumno('a1'), alumno('a2', 'Carla Ruiz Peña', edad='19', minutos=5), alumno('a3', 'Dante Mora Gil', edad='15', minutos=6))
    nuevos = _avisos_de(jefe)[1:]
    assert len(nuevos) == 2
    assert nuevos[0].titulo == 'Nuevo registro de alumno' and 'Prepa Uno' in nuevos[0].detalle
    assert 'Carla' not in nuevos[0].detalle  # sin nombres en la campanita
    assert nuevos[1].titulo.startswith('Nuevo registro: espera el permiso')  # menor sin permiso todavía
    assert len(_avisos_de(admisiones)) == 3 and not _avisos_de(directivo)
    importar(f_tutor, tutor('t9', 'Carla Ruiz Peña'))  # las familias no generan este aviso
    assert len(_avisos_de(jefe)) == 3
    importar(f_alumno, alumno('a2', 'Carla Ruiz Peña', edad='19', minutos=50))  # una edición no es un registro nuevo
    assert len(_avisos_de(jefe)) == 3


def test_muchos_registros_juntos_llegan_como_uno(jefe, f_alumno, evento):
    importar(f_alumno, alumno('a0'))
    lote = [alumno(f'b{i}', f'Alumno{i} Prueba Lote', minutos=10 + i) for i in range(avisos.UNO_POR_UNO + 2)]
    importar(f_alumno, *lote)
    ultimos = _avisos_de(jefe)
    assert ultimos[-1].cantidad >= avisos.UNO_POR_UNO + 2 and 'registros nuevos' in ultimos[-1].titulo


def test_se_puede_apagar(jefe, f_alumno, evento):
    avisos.guardar_preferencias(jefe, {t for t in TipoAviso.values if t != TipoAviso.REGISTRO})
    importar(f_alumno, alumno('a1'))
    importar(f_alumno, alumno('a2', 'Eva Luna Paz', minutos=5))
    assert not _avisos_de(jefe)


def test_el_contador_trae_el_aviso_para_la_ventanita(client, jefe, f_alumno, evento):
    importar(f_alumno, alumno('a1'))
    importar(f_alumno, alumno('a2', 'Eva Luna Paz', minutos=5))
    d = client.get('/admin/herramientas/avisos/contador/').json()
    assert d['sin_leer'] >= 2 and d['recientes'][0]['icono'] == 'how_to_reg'
