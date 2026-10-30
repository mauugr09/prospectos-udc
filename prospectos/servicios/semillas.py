"""Catálogos iniciales, roles (grupos con permisos) y datos de DEMOSTRACIÓN 100 % ficticios."""

import json
import random
import unicodedata
from datetime import datetime, time, timedelta, timezone as dt_tz

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.utils import timezone

from .. import catalogos
from . import texto
from ..models import (Carrera, Cuestionario, Estatus, Evento, Formulario, Perfil, Pregunta, Preparatoria, Prospecto,
                      TipoSeguimiento)

CLAVE_DEMO = 'Demo-Prospectos-2026!'

ROLES = {
    'Administrador': None,  # todos los permisos
    'Admisiones': [
        'view_prospecto', 'change_prospecto', 'exportar_prospectos', 'ver_datos_personales', 'resolver_coincidencias',
        'view_posiblecoincidencia', 'change_posiblecoincidencia', 'ver_reportes',
        'view_seguimiento', 'add_seguimiento', 'change_seguimiento',
        'view_preparatoria', 'add_preparatoria', 'change_preparatoria',
        'view_carrera', 'add_carrera', 'change_carrera', 'view_etiqueta', 'add_etiqueta', 'change_etiqueta',
        'view_evento', 'add_evento', 'change_evento', 'view_formulario', 'view_importacion',
    ],
    'Promotor': ['view_prospecto', 'ver_propios', 'view_evento', 'ver_eventos_propios', 'ver_reportes'],
    # Admisiones + editar catálogos (preguntas, opciones, carreras, prepas), reglas y usuarios que no sean administradores.
    'Coordinación': 'Admisiones+',
    'Directivo': ['ver_reportes', 'reporte_ejecutivo'],
}


def _datos_pregunta(cuestionario, orden, codigo, txt, tipo, opciones, sensible, clasificable):
    tema, etiqueta = catalogos.PRESENTACION.get(codigo, ('otras', ''))
    return {'texto': txt, 'tipo': tipo, 'opciones': opciones, 'sensible': sensible, 'clasificable': clasificable,
            'orden': orden * 10, 'tema': tema, 'etiqueta': etiqueta, 'de_sistema': True}


def _sembrar_opciones(p: Pregunta, sobrescribir: bool) -> None:
    """Crea en la base las opciones del catálogo (editables desde el panel)."""
    from ..models import OpcionPregunta
    if not isinstance(p.opciones, str) or p.opciones not in catalogos.CATALOGOS:
        return
    fijas = catalogos.FIJAS.get(p.codigo, set())
    for orden, (clave, txt) in enumerate(catalogos.CATALOGOS[p.opciones].items(), 1):
        o = OpcionPregunta.objects.filter(pregunta=p, clave=clave).first()
        if o is None:
            OpcionPregunta.objects.create(pregunta=p, clave=clave, texto=txt, orden=orden * 10, fija=clave in fijas)
        else:
            if sobrescribir and o.texto != txt:
                o.texto = txt  # el texto anterior queda como alias
            o.fija = clave in fijas
            o.save()


def crear_catalogos() -> None:
    """Crea lo que FALTE. Nunca sobrescribe ni borra lo que alguien editó o agregó en el panel."""
    for cuestionario, lista in catalogos.PREGUNTAS.items():
        for orden, fila in enumerate(lista, 1):
            p = Pregunta.objects.filter(cuestionario=cuestionario, codigo=fila[0]).first()
            if p is None:
                p = Pregunta.objects.create(cuestionario=cuestionario, codigo=fila[0],
                                            **_datos_pregunta(cuestionario, orden, *fila))
                _sembrar_opciones(p, sobrescribir=True)
    if not Carrera.objects.exists():
        for nombre, area, planteles in catalogos.CARRERAS:
            Carrera.objects.create(nombre=nombre, area=area, planteles=planteles)


def aplicar_catalogo_del_programa() -> None:
    """
    Solo al instalar una versión nueva del programa: lleva las preguntas y carreras DEL SISTEMA a lo que
    trae el código, respetando las que alguien editó en el panel (marcadas «editada»).
    """
    for cuestionario, lista in catalogos.PREGUNTAS.items():
        Pregunta.objects.filter(cuestionario=cuestionario, codigo__in=catalogos.RETIRADAS).delete()
        for orden, fila in enumerate(lista, 1):
            datos = _datos_pregunta(cuestionario, orden, *fila)
            p = Pregunta.objects.filter(cuestionario=cuestionario, codigo=fila[0]).first()
            if p is None:
                p = Pregunta.objects.create(cuestionario=cuestionario, codigo=fila[0], **datos)
            else:
                if p.editada:  # lo que la persona cambió se queda; lo que usa la lógica se corrige
                    datos = {k: datos[k] for k in ('tipo', 'opciones', 'sensible', 'de_sistema')}
                for k, v in datos.items():
                    setattr(p, k, v)
                p.save()
            _sembrar_opciones(p, sobrescribir=not p.editada)
    vigentes = []
    for nombre, area, planteles in catalogos.CARRERAS:
        c = Carrera.objects.filter(nombre=nombre).first() or Carrera(nombre=nombre)
        if not c.editada:
            c.area, c.planteles, c.activo = area, planteles, True
            c.save()
        vigentes.append(c.pk)
    # Carreras de versiones anteriores que ya no se ofrecen: se apagan (no se borran) si nadie las editó.
    Carrera.objects.filter(nombre__in=catalogos.CARRERAS_RETIRADAS, editada=False).exclude(pk__in=vigentes).update(activo=False)


EXTRA_COORDINACION = [
    'view_pregunta', 'add_pregunta', 'change_pregunta', 'delete_pregunta',
    'view_opcionpregunta', 'add_opcionpregunta', 'change_opcionpregunta', 'delete_opcionpregunta',
    'delete_carrera', 'delete_preparatoria', 'delete_etiqueta', 'configurar_scoring', 'change_formulario',
    'ver_reportes', 'reporte_ejecutivo', 'auth.view_user', 'auth.add_user', 'auth.change_user',
]


def crear_roles() -> None:
    """Roles base. Solo se crean/actualizan una vez por versión: los cambios hechos en «Roles» se respetan."""
    from ..models import Configuracion
    if Configuracion.obtener('roles.version') == VERSION_CATALOGO and Group.objects.filter(name__in=ROLES).count() == len(ROLES):
        return
    propios = Permission.objects.filter(content_type__app_label='prospectos')
    for nombre, codigos in ROLES.items():
        g, nuevo = Group.objects.get_or_create(name=nombre)
        if not nuevo and codigos is not None and Configuracion.obtener('roles.version') is not None and nombre != 'Coordinación':
            continue  # ya existía y pudo editarse en «Roles»: no se toca (Administrador siempre recibe todo)
        if codigos is None:
            g.permissions.set(Permission.objects.filter(content_type__app_label__in=['prospectos', 'auth']))
            continue
        if codigos == 'Admisiones+':
            codigos = ROLES['Admisiones'] + EXTRA_COORDINACION
        locales = [c for c in codigos if '.' not in c]
        auth = [c.split('.', 1)[1] for c in codigos if c.startswith('auth.')]
        g.permissions.set([*propios.filter(codename__in=locales),
                           *Permission.objects.filter(content_type__app_label='auth', codename__in=auth)])
    Configuracion.guardar('roles.version', VERSION_CATALOGO)


# Súbelo cuando cambien las preguntas del catálogo: al abrir el programa se re-mapean los Forms y se recalcula todo.
VERSION_CATALOGO = 4


def preparar() -> None:
    crear_catalogos()
    crear_roles()
    actualizar_por_catalogo()
    mejoras_unicas()


# Los Forms reales de la UDC (los de producción). Se registran solos al crear el administrador real;
# el tipo se confirma con el título del Form al conectar Google (importacion.sincronizar).
FORMS_UDC = [
    {'nombre': 'Cuestionario vocacional (alumno)', 'tipo': 'ALUMNO', 'google_form_id': '15yKpCaIUBX98tBvfdVcd7uqPXEppT6jfOjc9BSM2XgU',
     'url_publica': 'https://docs.google.com/forms/d/e/1FAIpQLSebI1Qa5nzAUCj36XNA0ZQL5AruA_JpT3SSzfoyW9NQ6kIThg/viewform'},
    {'nombre': 'Encuesta para padres de familia', 'tipo': 'TUTOR', 'google_form_id': '1BCtE0gVnEPGF-nNZw5ePRhsyeaOpgdHzoLoWNwf8UvI',
     'url_publica': 'https://docs.google.com/forms/d/e/1FAIpQLSedhaCrlP8lMTzcBbgFguxsqOGWpqW-qAzflOsFRS9-Bl2pOQ/viewform'},
]


def forms_predeterminados() -> int:
    """Registra los Forms de la UDC una sola vez (si alguien los quita, no vuelven). Devuelve cuántos creó."""
    from ..models import Configuracion
    if Configuracion.obtener('forms.predeterminados'):
        return 0
    creados = 0
    if not Formulario.objects.exclude(google_form_id__startswith='demo-').exists():
        for f in FORMS_UDC:
            _, nuevo = Formulario.objects.get_or_create(google_form_id=f['google_form_id'], defaults=f)
            creados += nuevo
    Configuracion.guardar('forms.predeterminados', True)
    return creados


def tipo_por_titulo(titulo: str | None) -> str | None:
    t = texto.normalizar(titulo or '')
    if not t:
        return None
    return 'TUTOR' if any(p in t for p in ('padre', 'madre', 'tutor', 'familia')) else 'ALUMNO'


def mejoras_unicas() -> None:
    """Una sola vez por versión: aplica a lo ya importado los criterios nuevos (eventos por prepa y fecha; familias)."""
    from ..models import Configuracion
    if Configuracion.obtener('mejoras.eventos_familias') == 1:
        return
    from ..models import PosibleCoincidencia
    from . import eventos, familias
    # Las propuestas alumno ↔ familia de antes vivían en «Posibles duplicados»: pasan a «Familias por unir».
    for c in PosibleCoincidencia.objects.filter(estado='pendiente', motivo__icontains='encuesta de padres'):
        c.motivo = f'{familias.MOTIVO}: nombre parecido ({c.similitud:.0%})'
        c.save(update_fields=['motivo'])
    eventos.reatribuir()
    familias.buscar_para_todos()
    Configuracion.guardar('mejoras.eventos_familias', 1)


def actualizar_por_catalogo() -> None:
    """Tras cambiar el catálogo (p. ej. al adaptarlo al Form real): re-mapea los Forms y reacomoda lo importado."""
    import logging
    from ..models import Configuracion
    from . import importacion, inteligencia
    if Configuracion.obtener('catalogo.version') == VERSION_CATALOGO:
        return
    aplicar_catalogo_del_programa()
    log = logging.getLogger('prospectos.importador')
    for f in Formulario.objects.filter(activo=True).exclude(google_form_id__startswith='demo-'):
        try:
            importacion.sincronizar(f)
        except Exception as e:  # noqa: BLE001 - sin conexión: queda el aviso en el formulario y en el Inicio
            f.ultimo_error = (f'Se actualizaron las preguntas del programa y no se pudo leer el Form ({e}). '
                              'Abre Formularios → «Sincronizar con Google».')[:2000]
            f.save(update_fields=['ultimo_error'])
            log.warning('No se pudo re-mapear %s: %s', f, e)
    inteligencia.recalcular_todos()
    Configuracion.guardar('catalogo.version', VERSION_CATALOGO)


# --------------------------------------------------------------------------- demo
NOMBRES_H = ['José', 'Luis', 'Miguel', 'Juan', 'Carlos', 'Jorge', 'Diego', 'Emiliano', 'Santiago', 'Mateo',
             'Sebastián', 'Leonardo', 'Ángel', 'Ricardo', 'Fernando', 'Iván', 'Héctor', 'Óscar', 'Raúl', 'Andrés']
NOMBRES_M = ['María', 'Guadalupe', 'Fernanda', 'Valeria', 'Ximena', 'Camila', 'Daniela', 'Sofía', 'Regina', 'Andrea',
             'Mariana', 'Renata', 'Paola', 'Itzel', 'Yesenia', 'Abril', 'Natalia', 'Jimena', 'Lucía', 'Karla']
APELLIDOS = ['Hernández', 'García', 'Martínez', 'López', 'González', 'Pérez', 'Rodríguez', 'Sánchez', 'Ramírez', 'Cruz',
             'Flores', 'Gómez', 'Morales', 'Vázquez', 'Reyes', 'Jiménez', 'Torres', 'Díaz', 'Gutiérrez', 'Ruiz',
             'Mendoza', 'Aguilar', 'Ortiz', 'Moreno', 'Castillo', 'Romero', 'Álvarez', 'Chávez', 'Rivera', 'Juárez']
# (nombre oficial, municipio, lat, lng, alumnos estimados, formas en que lo escriben los alumnos). Todo ficticio.
PREPAS = [
    ('Preparatoria Ficticia Los Álamos', 'Cuautitlán', 19.6706, -99.1786, 420, ['Prepa Los Alamos', 'los álamos']),
    ('Bachillerato Demo Izcalli', 'Cuautitlán Izcalli', 19.6466, -99.2116, 380, ['Bachillerato demo izcalli']),
    ('Colegio de Prueba Tultepec', 'Tultepec', 19.6850, -99.1280, 260, ['colegio prueba tultepec']),
    ('Preparatoria Ejemplo Teoloyucan', 'Teoloyucan', 19.7440, -99.1810, 300, ['Prepa ejemplo teoloyucan']),
    ('Instituto Simulado Melchor Ocampo', 'Melchor Ocampo', 19.7080, -99.1440, 220, ['instituto simulado']),
    ('Bachillerato Ficticio Zumpango', 'Zumpango', 19.7970, -99.0990, 340, ['Bachillerato ficticio zumpango']),
    # Sin ubicar: así llegan las que escriben los alumnos y aún nadie revisa.
    ('Centro de Estudios de Prueba Coyotepec', '', None, None, None, ['CEP Coyotepec']),
    ('Preparatoria Demo Huehuetoca', '', None, None, None, ['prepa demo huehuetoca']),
]


def _sin_acentos(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


def _usuario(username, nombre, rol, codigo=None, superusuario=False):
    User = get_user_model()
    u = User.objects.filter(username=username).first() or User(username=username)
    u.email = username
    u.first_name, u.last_name = nombre.split(' ', 1)
    u.is_staff, u.is_active, u.is_superuser = True, True, superusuario
    u.set_password(CLAVE_DEMO)
    u.save()
    u.groups.set([Group.objects.get(name=rol)])
    Perfil.objects.update_or_create(usuario=u, defaults={'codigo_promotor': codigo})
    return u


def _respuesta_api(rid: str, fecha: datetime, valores: dict) -> dict:
    answers = {}
    for codigo, v in valores.items():
        lista = [x for x in (v if isinstance(v, list) else [v]) if x not in (None, '')]
        if lista:
            answers['q_' + codigo] = {'questionId': 'q_' + codigo,
                                      'textAnswers': {'answers': [{'value': str(x)} for x in lista]}}
    iso = fecha.astimezone(dt_tz.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return {'responseId': 'demo-' + rid, 'createTime': iso, 'lastSubmittedTime': iso, 'answers': answers}


def cargar_demo(familias: int = 160, salida=print) -> dict:
    """
    Genera respuestas ficticias con la MISMA estructura que el Cuestionario Vocacional real (una pregunta de
    carrera y otra de modalidad por plantel, preparatoria escrita a mano, sin pregunta de aviso de privacidad)
    y las pasa por el importador REAL.
    """
    from . import importacion, seguimiento
    from .fuentes import FuenteDemo
    from .inteligencia import registrar_permiso_tutor
    from ..models import Configuracion

    rnd = random.Random(2026)
    preparar()
    admin = _usuario('admin@demo.local', 'Admin Demo', 'Administrador', superusuario=True)
    admisiones = _usuario('admisiones@demo.local', 'Asesora Demo', 'Admisiones')
    _usuario('directivo@demo.local', 'Director Demo', 'Directivo')
    promotores = [_usuario(f'promotor{i}@demo.local', n, 'Promotor', f'P0{i}')
                  for i, n in enumerate(['Promotor Uno', 'Promotora Dos', 'Promotor Tres'], 1)]
    Configuracion.guardar('permisos.aviso_en_form', {'activo': True, 'url': 'https://ejemplo.invalid/aviso-demo',
                                                     'por': 'demo', 'en': timezone.now().isoformat()}, admin)

    prepas = []
    for nombre, mun, lat, lng, est, _ in PREPAS:
        p = Preparatoria.objects.filter(nombre=nombre).first() or Preparatoria(nombre=nombre)
        p.municipio, p.lat, p.lng, p.alumnos_estimados, p.activo = mun, lat, lng, est, True
        p.por_revisar = lat is None
        p.save()
        prepas.append(p)

    hoy = timezone.localdate()
    eventos = []
    for i, prepa in enumerate(prepas[:6]):
        fecha = hoy - timedelta(weeks=8 - i, days=hoy.weekday()) + timedelta(days=i % 5)
        e, _ = Evento.objects.update_or_create(codigo=f'EVDEMO{i + 1:02d}', defaults={
            'preparatoria': prepa, 'promotor': promotores[i % 3], 'fecha': fecha,
            'alumnos_asistentes': round(prepa.alumnos_estimados * 0.4), 'meta_registros': 40, 'costo': 1500 + 250 * (i % 4)})
        eventos.append(e)
    e, _ = Evento.objects.update_or_create(codigo='EVDEMOHOY', defaults={
        'preparatoria': prepas[0], 'promotor': promotores[0], 'fecha': hoy,
        'alumnos_asistentes': 120, 'meta_registros': 60, 'costo': 2000})
    eventos.append(e)

    # Estructura igual a la del Form real: carrera y modalidad aparecen dos veces (Cuautitlán / Tultepec).
    textos = dict(Pregunta.objects.filter(cuestionario=Cuestionario.ALUMNO).values_list('codigo', 'texto'))
    estructura = {f'q_{c}': textos[c] for c in ('nombre_completo', 'edad', 'telefono', 'correo', 'preparatoria', 'plantel',
                                                'factor_eleccion', 'quiere_conocer', 'recibir_informacion')}
    estructura.update({'q_carrera_c': textos['carrera'], 'q_modalidad_c': textos['modalidad'],
                       'q_carrera_t': textos['carrera'], 'q_modalidad_t': textos['modalidad']})
    mapeo = {q: q[2:] for q in estructura}
    mapeo.update({'q_carrera_c': 'carrera', 'q_modalidad_c': 'modalidad', 'q_carrera_t': 'carrera', 'q_modalidad_t': 'modalidad'})
    form, _ = Formulario.objects.update_or_create(google_form_id='demo-alumno', defaults={
        'nombre': 'Cuestionario Vocacional (demo)', 'tipo': Cuestionario.ALUMNO,
        'url_publica': 'https://docs.google.com/forms/d/e/demo-alumno/viewform', 'mapeo_campos': mapeo, 'activo': True,
        'campos_prellenado': {}})

    por_plantel = {pl: [n for n, _, pls in catalogos.CARRERAS if pl in pls] for pl in catalogos.PLANTELES}
    cat = lambda c: list(catalogos.CATALOGOS[c].values())  # noqa: E731
    alumnos, tutores = [], []
    for i in range(familias):
        ev = eventos[i % len(eventos)]
        base = timezone.make_aware(datetime.combine(ev.fecha, time(9))) + timedelta(minutes=rnd.randint(0, 240))
        nombre = rnd.choice(NOMBRES_H if rnd.random() < .5 else NOMBRES_M)
        ap1, ap2 = rnd.choice(APELLIDOS), rnd.choice(APELLIDOS)
        plantel = 'cuautitlan' if rnd.random() < .65 else 'tultepec'
        sufijo = 'c' if plantel == 'cuautitlan' else 't'
        r = rnd.random()
        carreras = (['Aún no lo se'] if r < .15 else rnd.sample(por_plantel[plantel], 1 if r < .7 else rnd.randint(2, 3)))
        if rnd.random() < .04:
            carreras = ['Psicología']  # «Otro»: carrera que la universidad no ofrece
        prepa = rnd.choice(prepas)
        escrito = rnd.choice([prepa.nombre, *next(x[5] for x in PREPAS if x[0] == prepa.nombre)])
        edad = rnd.choice(['17', '17', '17', '18', '18', '17 años', '19', '16', 'diecisiete', '18'])
        alumnos.append(_respuesta_api(f'A{i}', base, {
            'nombre_completo': f'{nombre} {ap1} {ap2}',
            'edad': edad,
            'telefono': f'55{rnd.randint(10000000, 99999999)}',
            'correo': f'{_sin_acentos(nombre).lower()}.{_sin_acentos(ap1).lower()}{rnd.randint(1, 99)}@correo-demo.mx',
            'preparatoria': escrito,
            'plantel': catalogos.PLANTELES[plantel],
            f'carrera_{sufijo}': carreras,
            f'modalidad_{sufijo}': rnd.choice(['Semanal', 'Semanal', 'Sabatino', 'Aun no lo se'] + (['Dominical'] if sufijo == 'c' else [])),
            'factor_eleccion': rnd.sample(cat('factores_eleccion'), rnd.randint(1, 2)),
            'quiere_conocer': rnd.sample(cat('quiere_conocer'), rnd.randint(1, 2)),
            'recibir_informacion': rnd.choices(cat('canal_informacion'), weights=[6, 3, 1])[0],
        }))
        if rnd.random() > .55:
            continue  # ~45 % de las familias no contesta la encuesta de padres
        # A veces escriben el nombre igual (se enlaza solo) y a veces incompleto (va a «Posibles duplicados»).
        aspirante = f'{nombre} {ap1} {ap2}' if rnd.random() < .8 else rnd.choice([f'{nombre} {ap1}', f'{ap1} {ap2} {nombre}'])
        mod_t = rnd.choice(['Escolarizada', 'Escolarizada', 'Sabatina', 'Aún no lo hemos decidido.'] + (['Dominical'] if sufijo == 'c' else []))
        car_t = carreras if rnd.random() < .7 else rnd.sample(por_plantel[plantel], 1)
        tutores.append(_respuesta_api(f'T{i}', base + timedelta(hours=rnd.randint(5, 72)), {
            'consentimiento_aviso_privacidad': 'He leído y acepto el aviso de privacidad. Como padre, madre o tutor legal, '
                                               'otorgo mi consentimiento expreso para el tratamiento de los datos del menor a mi cargo.',
            'tutor_nombre': f'{rnd.choice(NOMBRES_H + NOMBRES_M)} {ap1}',
            'nombre_aspirante': aspirante,
            'tutor_telefono': f'55{rnd.randint(10000000, 99999999)}',
            'tutor_correo': f'{_sin_acentos(rnd.choice(NOMBRES_M)).lower()}{rnd.randint(1, 999)}@correo-demo.mx',
            'plantel': catalogos.PLANTELES[plantel],
            f'carrera_{sufijo}': [c + '.' for c in car_t] if car_t != ['Aún no lo se'] else ['Aún no lo ha decidido.'],
            f'modalidad_{sufijo}': mod_t,
            'tipo_universidad': rnd.choice(cat('tipo_universidad')),
            'factor_eleccion': rnd.sample(cat('factores_tutor'), rnd.randint(1, 3)),
            'preocupacion': rnd.choice(cat('preocupaciones')),
            'apoyo_economico': rnd.choice(cat('apoyo_economico')),
            'cuando_ingresa': rnd.choices(cat('cuando_ingresa'), weights=[6, 2, 1, 2])[0],
            'motivo_ubicacion': rnd.choice(cat('motivo_ubicacion')),
            'quiere_conocer': rnd.choice(cat('quiere_conocer_tutor')),
            'recibir_informacion': rnd.choices(cat('canal_tutor'), weights=[8, 1])[0] if rnd.random() < .9 else None,
        }))

    carpeta = settings.DATA_DIR / 'demo-forms'
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f'{form.google_form_id}.json').write_text(
        json.dumps({'estructura': estructura, 'responses': alumnos}, ensure_ascii=False, indent=1), encoding='utf-8')
    r = importacion.importar(form, FuenteDemo())
    salida(f'Importado {form.nombre}: {r.estado} · nuevas {r.nuevas}' + (f' · {r.mensaje}' if r.mensaje else ''))

    # Encuesta para padres: misma estructura que la real (carrera y modalidad por plantel).
    textos_t = dict(Pregunta.objects.filter(cuestionario=Cuestionario.TUTOR).values_list('codigo', 'texto'))
    codigos_t = ['consentimiento_aviso_privacidad', 'tutor_nombre', 'nombre_aspirante', 'tutor_telefono', 'tutor_correo', 'plantel',
                 'tipo_universidad', 'factor_eleccion', 'preocupacion', 'apoyo_economico', 'cuando_ingresa', 'motivo_ubicacion',
                 'quiere_conocer', 'recibir_informacion']
    estructura_t = {f'q_{c}': textos_t[c] for c in codigos_t}
    estructura_t.update({'q_carrera_c': textos_t['carrera'], 'q_modalidad_c': textos_t['modalidad'],
                         'q_carrera_t': textos_t['carrera'], 'q_modalidad_t': textos_t['modalidad']})
    mapeo_t = {q: q[2:] for q in estructura_t}
    mapeo_t.update({'q_carrera_c': 'carrera', 'q_modalidad_c': 'modalidad', 'q_carrera_t': 'carrera', 'q_modalidad_t': 'modalidad'})
    form_t, _ = Formulario.objects.update_or_create(google_form_id='demo-tutor', defaults={
        'nombre': 'Encuesta para padres de familia (demo)', 'tipo': Cuestionario.TUTOR,
        'url_publica': 'https://docs.google.com/forms/d/e/demo-tutor/viewform', 'mapeo_campos': mapeo_t, 'activo': True,
        'campos_prellenado': {}})
    (carpeta / f'{form_t.google_form_id}.json').write_text(
        json.dumps({'estructura': estructura_t, 'responses': tutores}, ensure_ascii=False, indent=1), encoding='utf-8')
    r = importacion.importar(form_t, FuenteDemo())
    salida(f'Importado {form_t.nombre}: {r.estado} · nuevas {r.nuevas}' + (f' · {r.mensaje}' if r.mensaje else ''))

    # Algunos menores ya tienen el permiso de su tutor registrado por la asesora.
    from ..models import EstadoRespuesta
    espera = Prospecto.objects.filter(respuestas__estado=EstadoRespuesta.CUARENTENA).distinct().order_by('id')
    for i, p in enumerate(list(espera)):
        if i % 3 != 2:
            registrar_permiso_tutor(p, admisiones, f'Tutor de {p.nombre_aspirante.split()[0]}', 'llamada' if i % 2 else 'whatsapp')

    etapas = [Estatus.OPEN_HOUSE, Estatus.SOLICITO, Estatus.INSCRITO]
    with transaction.atomic():
        for i, p in enumerate(Prospecto.objects.utilizables().filter(no_contactar=False).order_by('-score', 'id')):
            p.asesor = admisiones
            p.save()
            if i % 3 == 2:
                continue  # sin contacto todavía → generará tareas
            seguimiento.registrar(p, TipoSeguimiento.LLAMADA if i % 2 else TipoSeguimiento.WHATSAPP,
                                  'Seguimiento de demostración.', admisiones, p.creado_en + timedelta(days=2))
            hasta = min(4, (100 - i % 100) // 25)
            for etapa in etapas[:max(0, hasta - 1)]:
                p.refresh_from_db()
                seguimiento.cambiar_estatus(p, etapa, admisiones)
    seguimiento.generar_tareas_sin_contacto()
    return {'usuarios': ['admin@demo.local', 'admisiones@demo.local', 'directivo@demo.local',
                         'promotor1@demo.local', 'promotor2@demo.local', 'promotor3@demo.local'],
            'clave': CLAVE_DEMO, 'admin': admin.pk}
