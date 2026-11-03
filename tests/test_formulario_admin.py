import pytest
from django.contrib.auth.models import User

from prospectos.formularios_panel import FormularioForm
from prospectos.models import Formulario
from prospectos.servicios.fuentes import explicar_http

ID_A = '15yKpCaIUBX98tBvfdVcd7uqPXEppT6jfOjc9BSM2XgU'
ID_B = '1BCtE0gVnEPGF-nNZw5ePRhsyeaOpgdHzoLoWNwf8UvI'


def _datos(**k):
    d = {'nombre': 'Tutores', 'tipo': 'TUTOR', 'google_form_id': ID_B, 'url_publica': '', 'activo': 'on',
         'mapeo_campos': '{}', 'campos_prellenado': '{}'}
    d.update(k)
    return d


@pytest.mark.django_db
def test_url_de_un_form_ya_registrado_da_mensaje_no_error_500():
    Formulario.objects.create(nombre='Alumno', tipo='ALUMNO', google_form_id=ID_A)
    tutores = Formulario.objects.create(nombre='Tutores', tipo='TUTOR', google_form_id=ID_B)
    f = FormularioForm(_datos(google_form_id=f'https://docs.google.com/forms/d/{ID_A}/edit'), instance=tutores)
    assert not f.is_valid()
    assert 'ya está registrado como «Alumno»' in str(f.errors['google_form_id'])


@pytest.mark.django_db
def test_url_de_edicion_se_guarda_como_id():
    f = FormularioForm(_datos(google_form_id=f'https://docs.google.com/forms/d/{ID_B}/edit?usp=sharing'))
    assert f.is_valid(), f.errors
    assert f.save().google_form_id == ID_B


@pytest.mark.django_db
def test_enlace_viewform_se_rechaza_con_explicacion():
    f = FormularioForm(_datos(google_form_id='https://docs.google.com/forms/d/e/1FAIpQLSedhaCrlP8lMTzcBbgFguxsqOGWpqW-qAzflOsFRS9-Bl2pOQ/viewform'))
    assert not f.is_valid()
    assert 'EDICIÓN' in str(f.errors['google_form_id'])


@pytest.mark.django_db
def test_admin_responde_200_con_duplicado(client):
    admin = User.objects.create_superuser('a@x.mx', 'a@x.mx', 'Clave-larga-2026!')
    client.force_login(admin)
    s = client.session
    s['dos_pasos_ok'] = True
    s.save()
    Formulario.objects.create(nombre='Alumno', tipo='ALUMNO', google_form_id=ID_A)
    tutores = Formulario.objects.create(nombre='Tutores', tipo='TUTOR', google_form_id=ID_B)
    r = client.post(f'/admin/prospectos/formulario/{tutores.pk}/change/', _datos(google_form_id=ID_A))
    assert r.status_code == 200
    assert 'ya está registrado' in r.content.decode()


def test_404_explica_permisos_y_no_vuelca_html():
    m = explicar_http(404, '<!DOCTYPE html><html>' + 'x' * 5000)
    assert 'NO tiene acceso' in m and 'DOCTYPE' not in m and len(m) < 600
