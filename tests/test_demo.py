"""Borrar la demostración: se va lo ficticio y nada real."""
import pytest
from django.contrib.auth.models import User

from prospectos.models import Evento, Formulario, Preparatoria, Prospecto, Respuesta
from prospectos.servicios import demo, respaldos, semillas

from .conftest import alumno, importar


@pytest.fixture
def con_demo(monkeypatch):
    semillas.cargar_demo(familias=12, salida=lambda *a: None)
    monkeypatch.setattr(respaldos, 'crear', lambda: type('R', (), {'estado': 'ok', 'archivo': 'x.gz', 'mensaje': ''})())


def test_borra_lo_ficticio_y_respeta_lo_real(con_demo, f_alumno, client):
    real = User.objects.create_superuser('real@udc.mx', 'real@udc.mx', 'Clave-de-prueba-123')
    importar(f_alumno, alumno('r1', 'Lucía Real Pérez', evento=None))
    reales = set(Respuesta.objects.exclude(formulario__google_form_id__startswith='demo-').values_list('prospecto', flat=True))
    assert demo.hay_demo() and Prospecto.objects.count() > len(reales)
    inv = demo.inventario(real)
    assert inv['prospectos'] > 0 and inv['usuarios'] >= 5 and inv['otro_admin'] and not inv['quien_es_demo']

    client.force_login(real)
    assert 'Hay datos de demostración' in client.get('/admin/').content.decode()
    client.post('/admin/herramientas/demo/borrar/', {'confirmar': 'no'})
    assert demo.hay_demo()  # sin la palabra no se borra
    r = client.post('/admin/herramientas/demo/borrar/', {'confirmar': 'BORRAR'}, follow=True)
    assert 'Listo' in r.content.decode()
    assert not demo.hay_demo()
    assert set(Prospecto.objects.values_list('pk', flat=True)) == reales
    assert not Formulario.objects.filter(google_form_id__startswith='demo-').exists() and Formulario.objects.filter(pk=f_alumno.pk).exists()
    assert not Evento.objects.filter(codigo__startswith='EVDEMO').exists()
    from prospectos.servicios.semillas import PREPAS
    assert not Preparatoria.objects.filter(nombre__in=[p[0] for p in PREPAS]).exclude(prospectos__in=Prospecto.objects.all()).exists()
    assert not Preparatoria.objects.filter(nombre__in=['CEP Coyotepec', 'Instituto simulado', 'Los álamos']).exists()
    assert not User.objects.filter(username__endswith='@demo.local').exists() and User.objects.filter(pk=real.pk).exists()
    assert 'Hay datos de demostración' not in client.get('/admin/').content.decode()


def test_no_borra_si_entras_como_demo_o_no_hay_otro_admin(con_demo):
    admin_demo = User.objects.get(username='admin@demo.local')
    with pytest.raises(ValueError):
        demo.borrar(admin_demo)
    otro = User.objects.create_user('asesor@udc.mx', 'asesor@udc.mx', 'Clave-de-prueba-123', is_staff=True)
    with pytest.raises(ValueError):  # no queda ningún administrador real
        demo.borrar(otro)
    assert demo.hay_demo()


def test_si_falla_el_respaldo_no_se_borra_nada(con_demo, monkeypatch):
    monkeypatch.setattr(respaldos, 'crear', lambda: type('R', (), {'estado': 'error', 'archivo': '', 'mensaje': 'disco lleno'})())
    real = User.objects.create_superuser('real2@udc.mx', 'real2@udc.mx', 'Clave-de-prueba-123')
    antes = Prospecto.objects.count()
    with pytest.raises(RuntimeError):
        demo.borrar(real)
    assert Prospecto.objects.count() == antes and Preparatoria.objects.exists()
