from django.core import mail

from prospectos.models import Configuracion, EstadoRespuesta, Prospecto, Respuesta, Segmento
from prospectos.servicios import inteligencia, seguridad

from .conftest import alumno, importar, tutor


def p():
    return Prospecto.objects.get()


def test_score_100_con_todo(f_alumno, evento):
    importar(f_alumno, alumno('a1', edad='18'))
    assert p().score == 100 and p().plantel == 'cuautitlan' and p().canal_informacion == 'whatsapp'


def test_respeta_pesos_editados(f_alumno, evento):
    importar(f_alumno, alumno('a1', edad='18', recibir_informacion='Sí, por correo electrónico', quiere_conocer=['Instalaciones']))
    antes = p().score
    Configuracion.guardar('score.pesos', {'pidio_informacion': 50, 'contacto_completo': 50, 'eligio_carrera': 0,
                                          'pregunta_requisitos': 0, 'eligio_modalidad': 0, 'pregunta_costos': 0,
                                          'alumno_pidio_asesor': 30})  # regla retirada: se ignora
    assert inteligencia.recalcular(p()).score == 100 and antes < 100


def test_segmentos(f_alumno, evento):
    importar(f_alumno, alumno('a1', edad='18', modalidad='Sabatino', carrera=['Aún no lo se']))
    s = set(p().segmentos)
    assert {Segmento.BECA, Segmento.HORARIO, Segmento.INDECISO} <= s
    assert p().carrera is None and p().carreras.count() == 0


def test_listo_para_inscribirse(f_alumno, evento):
    importar(f_alumno, alumno('a1', edad='18'))
    assert p().segmento_principal == Segmento.LISTO


def test_no_gracias_sale_de_la_cola_y_no_recibe_correo(f_alumno, evento, client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        importar(f_alumno, alumno('a1', edad='18', recibir_informacion='No, gracias'))
    x = p()
    assert x.no_contactar and x.segmentos[0] == Segmento.NO_CONTACTAR and x.consentimiento
    assert len(mail.outbox) == 0
    from prospectos.servicios import seguimiento
    from django.utils import timezone
    from datetime import timedelta
    Prospecto.objects.update(creado_en=timezone.now() - timedelta(days=30))
    assert seguimiento.generar_tareas_sin_contacto() == 0


def test_carreras_multiples_y_otra(f_alumno, evento):
    importar(f_alumno, alumno('a1', edad='18', carrera=['Ingeniera Industrial', 'Derecho', 'Psicología']))
    x = p()
    assert x.carrera.nombre == 'Ingeniería Industrial'  # el Form dice «Ingeniera»
    assert sorted(x.carreras.values_list('nombre', flat=True)) == ['Derecho', 'Ingeniería Industrial']
    assert Respuesta.objects.get().valores('carrera')[-1] == 'Psicología'  # «Otro»: se conserva lo escrito


def test_edad_escrita_a_mano(f_alumno, evento):
    importar(f_alumno, alumno('a1', edad='18 años'), alumno('a2', 'Luis Pérez Ruiz', edad='dieciocho', minutos=5))
    assert Prospecto.objects.get(nombre_aspirante__startswith='Ana').edad == 18
    luis = Prospecto.objects.get(nombre_aspirante='Luis Pérez Ruiz')
    assert luis.edad is None and not luis.consentimiento  # no se entiende: se trata como menor


def test_brechas(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', carrera=['Derecho'], modalidad='Sabatino', plantel='Universidad de Tultepec'))
    importar(f_tutor, tutor('t1', carrera=['Pedagogía'], modalidad='Semanal'))
    assert [b['tipo'] for b in p().brechas] == ['carrera', 'modalidad', 'plantel'] and p().tiene_brecha


def test_sin_brecha_cuando_coinciden(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1'))
    importar(f_tutor, tutor('t1'))
    assert p().brechas == [] and not p().tiene_brecha


# --------------------------------------------------------------- consentimiento
def test_menor_en_cuarentena_hasta_que_el_tutor_consienta(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', edad='16'))
    assert not p().consentimiento and Respuesta.objects.get().estado == EstadoRespuesta.CUARENTENA
    assert Prospecto.objects.utilizables().count() == 0
    importar(f_tutor, tutor('t1'))
    assert p().consentimiento and p().origen_consentimiento == 'tutor'
    assert set(Respuesta.objects.values_list('estado', flat=True)) == {EstadoRespuesta.VALIDA}


def test_mayor_de_edad_consiente_por_si_mismo(f_alumno, evento):
    importar(f_alumno, alumno('a1', edad='19'))
    assert p().consentimiento and p().origen_consentimiento == 'alumno'


def test_tutor_niega_todo_queda_sin_consentimiento(f_alumno, f_tutor, evento):
    importar(f_alumno, alumno('a1', edad='19'))
    importar(f_tutor, tutor('t1', consentimiento_aviso_privacidad='No'))
    assert p().consentimiento  # el adulto consintió por sí mismo
    importar(f_alumno, alumno('a2', 'Luis Pérez Ruiz', edad='16'))
    importar(f_tutor, tutor('t2', 'Luis Pérez Ruiz', consentimiento_aviso_privacidad='No'))
    luis = Prospecto.objects.get(nombre_aspirante='Luis Pérez Ruiz')
    assert not luis.consentimiento and luis.consentimiento_negado
    assert set(luis.respuestas.values_list('estado', flat=True)) == {EstadoRespuesta.SIN_CONSENTIMIENTO}


def test_purga_cuarentena_vencida_y_no_revive(f_alumno, evento, settings):
    importar(f_alumno, alumno('a1', edad='16'))
    from datetime import timedelta
    from django.utils import timezone
    Prospecto.objects.update(creado_en=timezone.now() - timedelta(days=31))
    assert seguridad.purgar_sin_consentimiento() == 1
    x = p()
    assert x.anonimizado_en and x.correo is None and x.nombre_aspirante.startswith('Anónimo')
    assert Respuesta.objects.get().estado == EstadoRespuesta.DESCARTADA
    r = importar(f_alumno, alumno('a1', edad='16'))
    assert r.omitidas == 1 and Prospecto.objects.count() == 1


def test_anonimiza_inactivos(f_alumno, evento):
    importar(f_alumno, alumno('a1', edad='19'))
    from datetime import timedelta
    from django.utils import timezone
    Prospecto.objects.update(ultima_actividad_en=timezone.now() - timedelta(days=30 * 19))
    assert seguridad.anonimizar_inactivos() == 1
    assert p().telefono is None and Prospecto.objects.reportables().count() == 1


def test_bienvenida_una_vez_y_solo_con_consentimiento(f_alumno, f_tutor, evento, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        importar(f_alumno, alumno('a1', edad='16'))
    assert len(mail.outbox) == 0
    with django_capture_on_commit_callbacks(execute=True):
        importar(f_tutor, tutor('t1'))
    with django_capture_on_commit_callbacks(execute=True):
        importar(f_tutor, tutor('t1', minutos=90, carrera=['Pedagogía']))
    assert len(mail.outbox) == 1 and p().bienvenida_enviada_en


def test_mayor_sin_pregunta_de_aviso_espera_hasta_que_se_active_el_aviso_en_el_form(f_alumno, evento):
    importar(f_alumno, alumno('a1', edad='19', consentimiento_aviso_privacidad=None))
    assert not p().consentimiento
    from prospectos.servicios import reportes
    assert 'no le pidió aceptar el aviso' in reportes.explicar_estado(Respuesta.objects.get())[2]
    Configuracion.guardar('permisos.aviso_en_form', {'activo': True, 'url': 'https://x.mx/aviso'})
    assert inteligencia.recalcular(p()).consentimiento and p().origen_consentimiento == 'aviso'


def test_aviso_en_el_form_no_alcanza_a_menores(f_alumno, evento):
    Configuracion.guardar('permisos.aviso_en_form', {'activo': True, 'url': 'https://x.mx/aviso'})
    importar(f_alumno, alumno('a1', edad='17', consentimiento_aviso_privacidad=None))
    assert not p().consentimiento


def test_permiso_del_tutor_registrado_por_asesor(f_alumno, evento):
    from .conftest import usuario
    importar(f_alumno, alumno('a1', edad='17', consentimiento_aviso_privacidad=None))
    asesora = usuario('as@x.mx', 'Admisiones')
    x = inteligencia.registrar_permiso_tutor(p(), asesora, 'María García', 'llamada')
    assert x.consentimiento and x.origen_consentimiento == 'asesor' and 'María García' in x.permiso_nota
    assert Respuesta.objects.get().estado == EstadoRespuesta.VALIDA
    assert x.seguimientos.filter(notas__contains='Permiso del tutor').exists()
    # Si después dice «No» en el Form, gana el «No».
    importar(f_alumno, alumno('a1', edad='17', consentimiento_aviso_privacidad='No', minutos=60))
    assert not p().consentimiento
