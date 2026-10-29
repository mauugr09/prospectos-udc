from prospectos.models import PosibleCoincidencia, Prospecto
from prospectos.servicios import inteligencia

from .conftest import alumno, importar, tutor


def test_enlaza_por_token_aunque_el_nombre_sea_distinto(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', 'Ana Sofía López García', token_familia='FABC1234'))
    importar(f_tutor, tutor('t1', 'Sofi', token_familia='fabc 1234'))
    p = Prospecto.objects.get()
    assert p.tiene_alumno and p.tiene_tutor


def test_enlaza_por_nombre_difuso_en_la_misma_prepa(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', 'Ximena Hernández López'))
    importar(f_tutor, tutor('t1', 'hernandez lopez jimena'))
    assert Prospecto.objects.count() == 1 and Prospecto.objects.get().tiene_tutor


def test_caso_dudoso_va_a_revision_y_se_puede_rechazar_o_fusionar(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', 'Ana Sofía López García'))
    importar(f_tutor, tutor('t1', 'Ana Sofía López'))
    assert Prospecto.objects.count() == 2
    c = PosibleCoincidencia.objects.get()
    inteligencia.fusionar(c.candidato, c.prospecto)
    p = Prospecto.objects.utilizables().get()
    assert p.tiene_alumno and p.tiene_tutor and PosibleCoincidencia.objects.get().estado == 'fusionada'


def test_rechazar_coincidencia(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', 'Ana Sofía López García'))
    importar(f_tutor, tutor('t1', 'Ana Sofía López'))
    c = PosibleCoincidencia.objects.get()
    inteligencia.rechazar(c)
    assert PosibleCoincidencia.objects.get().estado == 'rechazada' and Prospecto.objects.count() == 2


def test_no_enlaza_por_nombre_en_otra_prepa(f_alumno, f_tutor, evento, evento2):
    importar(f_alumno, alumno('a1', 'Ana Sofía López García'))
    importar(f_tutor, tutor('t1', 'Ana Sofía López García', evento='EV2', tutor_correo=None, tutor_telefono=None))
    assert Prospecto.objects.count() == 2


def test_dos_tokens_distintos_nunca_se_enlazan(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', 'Ana López García', token_familia='FAAAAAAA'))
    importar(f_tutor, tutor('t1', 'Ana López García', token_familia='FBBBBBBB'))
    assert Prospecto.objects.count() == 2


def test_reenvio_mismo_correo_es_historial(f_alumno, evento):
    importar(f_alumno, alumno('a1', 'Luis Pérez Ruiz', correo='luis@x.mx'))
    importar(f_alumno, alumno('a2', 'Luis Peres', correo='LUIS@x.mx', minutos=120))
    assert Prospecto.objects.count() == 1 and Prospecto.objects.get().respuestas.count() == 2


def test_hermanos_con_mismo_telefono_de_tutor_no_se_fusionan(f_tutor, evento):
    importar(f_tutor, tutor('t1', 'Carlos Ramírez Cruz', tutor_telefono='7221234567'))
    importar(f_tutor, tutor('t2', 'Mariana Ramírez Cruz', tutor_telefono='722-123-4567'))
    assert Prospecto.objects.count() == 2


def test_encuesta_de_padres_sin_codigo_enlaza_por_nombre_identico_y_unico(f_alumno, f_tutor, evento):
    # La encuesta real no trae código de familia ni prepa: solo el nombre del aspirante y el plantel.
    importar(f_alumno, alumno('a1', 'Ana Sofía López García'))
    importar(f_tutor, tutor('t1', 'ana sofia LOPEZ garcia', evento=None, tutor_correo=None, tutor_telefono=None))
    p = Prospecto.objects.get()
    assert p.tiene_alumno and p.tiene_tutor and p.consentimiento and p.origen_consentimiento == 'tutor'


def test_homonimos_o_nombre_incompleto_van_a_revision(f_alumno, f_tutor, evento, evento2):
    importar(f_alumno, alumno('a1', 'Luis Pérez Ruiz'), alumno('a2', 'Luis Pérez Ruiz', evento='EV2', correo='otro@x.mx'))
    importar(f_tutor, tutor('t1', 'Luis Pérez Ruiz', evento=None, tutor_correo=None, tutor_telefono=None))
    assert Prospecto.objects.filter(tiene_tutor=True, tiene_alumno=False).count() == 1  # dos «Luis Pérez Ruiz»: no adivina
    importar(f_alumno, alumno('a3', 'Ana Sofía López García'))
    importar(f_tutor, tutor('t2', 'Ana López', evento=None, tutor_correo=None, tutor_telefono=None))
    assert PosibleCoincidencia.objects.filter(prospecto__nombre_aspirante='Ana López').exists()


def test_plantel_distinto_no_enlaza_por_nombre(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', 'Ana Sofía López García'))
    importar(f_tutor, tutor('t1', 'Ana Sofía López García', evento=None, tutor_correo=None, tutor_telefono=None,
                            plantel='Universidad de Tultepec'))
    assert Prospecto.objects.count() == 2


def test_familia_contesta_antes_que_el_alumno(f_alumno, f_tutor, evento):
    importar(f_tutor, tutor('t1', 'Ana Sofía López García', evento=None, minutos=0))
    importar(f_alumno, alumno('a1', 'Ana Sofía López García', minutos=60))
    p = Prospecto.objects.get()
    assert p.tiene_alumno and p.tiene_tutor


def test_contacto_del_aspirante_en_la_encuesta_enlaza_aunque_el_nombre_venga_mal(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', 'Ana Sofía López García', correo='ana@x.mx'))
    importar(f_tutor, tutor('t1', 'Sofi', evento=None, aspirante_contacto='ANA@x.mx'))
    assert Prospecto.objects.get().tiene_tutor
