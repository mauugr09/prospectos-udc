import pytest
from django.db import connection

from prospectos.models import Auditoria, Prospecto
from prospectos.servicios import cifrado, texto
from prospectos.servicios.seguridad import depurar


def test_normaliza_acentos_mayusculas_y_signos():
    assert texto.normalizar('  ÁNGEL   Núñez-Peña! ') == 'angel nunez pena'


@pytest.mark.parametrize('a,b', [
    ('Ximena Hernández López', 'jimena hernandez lopez'),
    ('Hernández López Ximena', 'Ximena Hernández López'),
    ('Valeria Pérez Ruiz', 'Baleria Peres Ruiz'),
    ('María de la Luz Gómez', 'Maria Luz Gomez'),
])
def test_mismo_nombre_con_variantes(a, b):
    assert texto.similitud_nombres(a, b) >= 0.93


def test_falta_un_apellido_va_a_revision():
    s = texto.similitud_nombres('Ana Sofía López García', 'Ana Sofía López')
    assert 0.82 <= s < 0.93


def test_personas_distintas_con_apellido_en_comun():
    assert texto.similitud_nombres('Carlos López García', 'Mariana López García') < 0.82


def test_si_no_y_catalogos():
    assert texto.si_no('Sí') == 'si' and texto.si_no('NO') == 'no' and texto.si_no('tal vez') is None
    assert texto.clave_catalogo('En línea', {'en_linea': 'En línea', 'mixta': 'Mixta'}) == 'en_linea'


def test_depura_pii_antes_de_ia():
    t = depurar('Escríbeme a ana@correo.mx o al 722 123 4567, ver https://x.com tengo 17')
    assert 'ana@' not in t and '722' not in t and 'https' not in t and '17' not in t


def test_cifra_contacto_en_bd_e_indice_ciego(db):
    p = Prospecto.objects.create(nombre_aspirante='Ana', correo='Ana@Correo.mx', telefono='(722) 111-2233',
                                 tutor_correo='papa@x.mx', tutor_telefono='+52 722 999 8877')
    with connection.cursor() as c:
        c.execute('SELECT correo, telefono, tutor_correo, tutor_telefono FROM prospectos_prospecto WHERE id=%s', [p.pk])
        crudo = c.fetchone()
    assert all(v and '@' not in v and '722' not in v for v in crudo)
    assert Prospecto.objects.get(pk=p.pk).correo == 'Ana@Correo.mx'
    assert p.correo_bi == cifrado.indice_correo(' ana@correo.MX ')
    assert p.telefono_bi == cifrado.indice_telefono('7221112233')


def test_no_acepta_misma_llave_para_cifrado_e_indice(settings):
    settings.CONFIG = dict(settings.CONFIG, CLAVE_INDICE_CIEGO=settings.CONFIG['CLAVE_CIFRADO'])
    with pytest.raises(RuntimeError):
        cifrado.indice_correo('a@b.mx')


def test_auditoria_solo_insercion(db):
    a = Auditoria.objects.create(accion='x')
    with pytest.raises(RuntimeError):
        a.save()
    with pytest.raises(RuntimeError):
        a.delete()
