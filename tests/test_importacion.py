from datetime import timedelta

from prospectos.models import Formulario, Importacion, Prospecto, Respuesta, RespuestaItem
from prospectos.servicios import importacion
from prospectos.servicios.fuentes import FuenteGoogle, FuenteMemoria

from .conftest import BASE, alumno, importar


def test_idempotente_aunque_corra_varias_veces(f_alumno, evento):
    r1 = importar(f_alumno, alumno('a1'), alumno('a2', 'Luis Pérez Ruiz'))
    r2 = importar(f_alumno, alumno('a1'), alumno('a2', 'Luis Pérez Ruiz'))
    assert (r1.nuevas, r2.nuevas, r2.omitidas) == (2, 0, 2)
    assert Respuesta.objects.count() == 2 and Prospecto.objects.count() == 2


def test_respuesta_editada_se_actualiza_no_duplica(f_alumno, evento):
    importar(f_alumno, alumno('a1', carrera=['Pedagogía']))
    r = importar(f_alumno, alumno('a1', carrera=['Derecho'], minutos=60))
    assert r.actualizadas == 1 and Respuesta.objects.count() == 1
    resp = Respuesta.objects.get()
    assert resp.version == 2 and Prospecto.objects.get().carrera.nombre == 'Derecho'


def test_contacto_no_se_guarda_en_items(f_alumno, evento):
    importar(f_alumno, alumno('a1'))
    codigos = set(RespuestaItem.objects.values_list('codigo', flat=True))
    assert 'correo' not in codigos and 'telefono' not in codigos and 'carrera' in codigos


def test_marca_de_agua_con_traslape(f_alumno, evento):
    importar(f_alumno, alumno('a1', minutos=0), alumno('a2', 'Luis Pérez', minutos=90))
    f = Formulario.objects.get(pk=f_alumno.pk)
    assert f.ultima_respuesta_en == BASE + timedelta(minutes=90)

    vistos = {}

    class Espia(FuenteMemoria):
        def respuestas(self, formulario, desde):
            vistos['desde'] = desde
            return iter([])
    importacion.importar(f, Espia())
    assert vistos['desde'] == BASE + timedelta(minutes=80)


class FalsaSesion:
    def __init__(self, respuestas):
        self.respuestas, self.llamadas = list(respuestas), []

    def get(self, url, params=None, **kw):
        self.llamadas.append(params)
        r = self.respuestas.pop(0)
        return r


class R:
    def __init__(self, status, datos=None):
        self.status_code, self.datos, self.text = status, datos or {}, str(datos)

    def json(self):
        return self.datos


def test_recorre_paginas_y_reintenta_429(f_alumno, evento, monkeypatch):
    monkeypatch.setattr(FuenteGoogle, '_esperar', staticmethod(lambda i: None))
    s = FalsaSesion([R(429), R(200, {'responses': [alumno('a1')], 'nextPageToken': 'p2'}),
                     R(503), R(200, {'responses': [alumno('a2', 'Luis Pérez')]})])
    r = importacion.importar(f_alumno, FuenteGoogle(s, token='x'))
    assert r.estado == 'ok' and r.nuevas == 2
    assert s.llamadas[-1]['pageToken'] == 'p2'


def test_error_se_registra_y_no_avanza_marca(f_alumno, evento, monkeypatch):
    monkeypatch.setattr(FuenteGoogle, '_esperar', staticmethod(lambda i: None))
    importar(f_alumno, alumno('a1'))
    marca = Formulario.objects.get().ultima_respuesta_en
    s = FalsaSesion([R(500)] * 5)
    r = importacion.importar(Formulario.objects.get(), FuenteGoogle(s, token='x'))
    f = Formulario.objects.get()
    assert r.estado == 'error' and 'HTTP 500' in f.ultimo_error and f.errores_consecutivos == 1
    assert f.ultima_respuesta_en == marca
    assert Importacion.objects.filter(estado='error').count() == 1


def test_propone_mapeo_desde_estructura(f_alumno):
    class Estructura(FuenteMemoria):
        def estructura(self, formulario):
            return {'x1': 'Nombre completo', 'x2': 'Carrera que te gustaría estudiar', 'x3': 'Pregunta que no existe zzz'}
    f_alumno.mapeo_campos = {}
    p = {x['question_id']: x['codigo'] for x in importacion.proponer_mapeo(f_alumno, Estructura())}
    assert p == {'x1': 'nombre_completo', 'x2': 'carrera', 'x3': None}


def test_formulario_acepta_url_de_edicion_y_deduce_entries(f_alumno):
    from prospectos.models import Cuestionario
    f = Formulario.objects.create(nombre='x', tipo=Cuestionario.TUTOR,
                                  google_form_id='https://docs.google.com/forms/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit?usp=sharing')
    assert f.google_form_id == '1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789'
    importacion.aplicar_mapeo(f, [{'question_id': '1a2b3c4d', 'codigo': 'evento'}, {'question_id': '0f', 'codigo': 'carrera'}])
    assert f.campos_prellenado == {'evento': f'entry.{int("1a2b3c4d", 16)}'}


def test_sincronizar_toma_url_publica_y_mapeo(f_alumno):
    class Falsa(FuenteMemoria):
        def info(self, formulario):
            return {'info': {'title': 'Vocacional 2027'}, 'responderUri': 'https://docs.google.com/forms/d/e/XYZ/viewform'}

        def estructura(self, formulario):
            return {'aa01': 'Nombre completo', 'aa02': 'Código de evento (uso interno, no modificar)'}
    f_alumno.url_publica = ''
    f_alumno.mapeo_campos = {}
    f_alumno.campos_prellenado = {}
    f_alumno.google_form_id = 'formulario-real-123456789012345'
    f_alumno.save()
    import prospectos.servicios.fuentes as fuentes
    fuentes_orig = fuentes.entries_publicos
    fuentes.entries_publicos = lambda url, sesion=None: {}
    try:
        r = importacion.sincronizar(f_alumno, Falsa())
    finally:
        fuentes.entries_publicos = fuentes_orig
    f = Formulario.objects.get(pk=f_alumno.pk)
    assert r['titulo'] == 'Vocacional 2027' and f.url_publica.endswith('/viewform')
    assert f.mapeo_campos == {'aa01': 'nombre_completo', 'aa02': 'evento'}
    assert f.campos_prellenado == {'evento': f'entry.{int("aa02", 16)}'}


def test_entries_publicos_lee_la_pagina_del_form():
    from prospectos.servicios.fuentes import entries_publicos

    class Resp:
        status_code = 200
        text = ('<script>var FB_PUBLIC_LOAD_DATA_ = [null,["desc",[[111,"Nombre completo",null,0,[[2092238618,null,1]]],'
                '[222,"Código de evento (uso interno, no modificar)",null,0,[[555666777,null,0]]],[333,"Sección",null,8]]],"/forms"];</script>')

    class Sesion:
        def get(self, *a, **k):
            return Resp()
    r = entries_publicos('https://docs.google.com/forms/d/e/X/viewform', Sesion())
    assert r['nombre completo'] == 'entry.2092238618'
    assert r['codigo de evento uso interno no modificar'] == 'entry.555666777'


def test_mapeo_prefiere_entries_verificados(f_alumno):
    origen = importacion.aplicar_mapeo(
        f_alumno, [{'question_id': '1a2b3c4d', 'codigo': 'evento', 'titulo': 'Código de evento'},
                   {'question_id': '0f0f0f0f', 'codigo': 'promotor', 'titulo': 'Código de promotor'}],
        {'codigo de evento': 'entry.999'})
    f = Formulario.objects.get(pk=f_alumno.pk)
    assert f.campos_prellenado['evento'] == 'entry.999' and origen == {'evento': 'verificado'}
