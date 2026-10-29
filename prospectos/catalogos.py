"""
Catálogo de preguntas y opciones del CUESTIONARIO VOCACIONAL real de la universidad.

Los textos de las opciones deben coincidir con los del Form (sin importar acentos, mayúsculas
ni puntuación). El `codigo` de cada pregunta es estable: no cambiarlo, solo agregar.
"""

PLANTELES = {
    'cuautitlan': 'Universidad de Cuautitlán México',
    'tultepec': 'Universidad de Tultepec',
}
PLANTELES_CORTO = {'cuautitlan': 'Cuautitlán', 'tultepec': 'Tultepec'}

MODALIDADES = {
    'semanal': 'Semanal',
    'sabatino': 'Sabatino',
    'dominical': 'Dominical',
    'indeciso': 'Aún no lo sé',
}
FACTORES_ELECCION = {
    'colegiaturas': 'Colegiaturas accesibles',
    'becas': 'Becas y descuentos',
    'horarios': 'Horarios flexibles',
    'cercania': 'Cercanía a mi domicilio',
    'calidad': 'Calidad educativa',
    'oportunidades_laborales': 'Oportunidades laborales',
}
QUIERE_CONOCER = {
    'carreras': 'Carreras disponibles',
    'becas': 'Becas y descuentos',
    'costos': 'Costos y colegiaturas',
    'horarios': 'Horarios',
    'requisitos': 'Requisitos de inscripción',
    'instalaciones': 'Instalaciones',
}
CANAL_INFORMACION = {
    'whatsapp': 'Sí, por WhatsApp',
    'correo': 'Sí, por correo electrónico',
    'no': 'No, gracias',
}
SI_NO = {'si': 'Sí', 'no': 'No'}

# --- Encuesta para padres de familia (mismas claves que el alumno cuando significan lo mismo: así se comparan)
CONSENTIMIENTO_TUTOR = {'si': 'He leído y acepto el aviso de privacidad', 'no': 'No'}
MODALIDADES_TUTOR = {'semanal': 'Escolarizada', 'sabatino': 'Sabatina', 'dominical': 'Dominical',
                     'indeciso': 'Aún no lo hemos decidido'}
TIPO_UNIVERSIDAD = {'publica': 'Pública', 'privada': 'Privada', 'ambas': 'Ambas opciones', 'indeciso': 'Aún no lo hemos decidido'}
FACTORES_TUTOR = {'calidad': 'Calidad académica', 'becas': 'Becas y apoyos económicos', 'cercania': 'Cercanía al domicilio',
                  'horarios': 'Horarios accesibles', 'instalaciones': 'Instalaciones y equipamiento',
                  'oportunidades_laborales': 'Oportunidades laborales'}
PREOCUPACIONES = {'costos': 'Costos educativos', 'distancia': 'Distancia y transporte', 'calidad': 'Calidad académica',
                  'horarios': 'Horarios de estudio', 'admision': 'Proceso de admisión',
                  'oportunidades_laborales': 'Oportunidades laborales', 'ninguna': 'Ninguna por el momento'}
APOYO_ECONOMICO = {'becas': 'Becas académicas', 'descuentos': 'Descuentos en inscripción', 'facilidades': 'Facilidades de pago',
                   'financiamiento': 'Planes de financiamiento', 'ninguno': 'No requerimos apoyo económico'}
CUANDO_INGRESA = {'proximo_ciclo': 'En el próximo ciclo escolar', 'un_ano': 'Dentro de un año',
                  'dos_anos': 'Dentro de dos años o más', 'sin_fecha': 'Aún no tenemos una fecha definida'}
MOTIVO_UBICACION = {'cercania_domicilio': 'Cercanía de domicilio', 'transporte': 'Facilidad de transporte',
                    'cercania_trabajo': 'Cercanía de trabajo', 'recomendacion': 'Recomendación de familiares o conocidos'}
QUIERE_CONOCER_TUTOR = {'carreras': 'Carreras disponibles', 'becas': 'Becas y apoyos económicos',
                        'costos': 'Costos de inscripción y colegiaturas', 'horarios': 'Horarios y modalidades de estudio',
                        'instalaciones': 'Instalaciones', 'requisitos': 'Proceso de inscripción'}
CANAL_TUTOR = {'si': 'Sí, me interesa recibir información', 'no': 'No, por el momento'}

CATALOGOS = {
    'planteles': PLANTELES, 'modalidades': MODALIDADES, 'factores_eleccion': FACTORES_ELECCION,
    'quiere_conocer': QUIERE_CONOCER, 'canal_informacion': CANAL_INFORMACION, 'si_no': SI_NO,
    'consentimiento_tutor': CONSENTIMIENTO_TUTOR, 'modalidades_tutor': MODALIDADES_TUTOR, 'tipo_universidad': TIPO_UNIVERSIDAD,
    'factores_tutor': FACTORES_TUTOR, 'preocupaciones': PREOCUPACIONES, 'apoyo_economico': APOYO_ECONOMICO,
    'cuando_ingresa': CUANDO_INGRESA, 'motivo_ubicacion': MOTIVO_UBICACION, 'quiere_conocer_tutor': QUIERE_CONOCER_TUTOR,
    'canal_tutor': CANAL_TUTOR,
}

# Respuesta del Form que significa «todavía no elige carrera» (no es una carrera).
INDECISO = 'indeciso'
TEXTOS_INDECISO = ('aun no lo se', 'aun no lo decido', 'no lo se', 'no se', 'aun no lo ha decidido', 'aun no lo hemos decidido')

# (nombre, área, planteles donde se ofrece). Nombres corregidos; el Form dice «Ingeniera Industrial».
CARRERAS = [
    ('Derecho', 'Sociales y humanidades', ['cuautitlan', 'tultepec']),
    ('Criminología y Criminalística', 'Sociales y humanidades', ['cuautitlan', 'tultepec']),
    ('Seguridad Pública', 'Sociales y humanidades', ['cuautitlan']),
    ('Pedagogía', 'Sociales y humanidades', ['cuautitlan', 'tultepec']),
    ('Filosofía', 'Sociales y humanidades', ['cuautitlan']),
    ('Idiomas', 'Sociales y humanidades', ['cuautitlan', 'tultepec']),
    ('Negocios Internacionales', 'Económico-administrativas', ['cuautitlan', 'tultepec']),
    ('Administración de Empresas e Innovación de Negocios', 'Económico-administrativas', ['cuautitlan', 'tultepec']),
    ('Contaduría Pública y Finanzas', 'Económico-administrativas', ['cuautitlan']),
    ('Mercadotecnia y Diseño Digital', 'Económico-administrativas', ['cuautitlan']),
    ('Ingeniería Industrial', 'Ingenierías', ['cuautitlan']),
    ('Ingeniería en Sistemas y Ciencia de Datos', 'Ingenierías', ['cuautitlan']),
    ('Ingeniería Ambiental', 'Ingenierías', ['cuautitlan']),
    ('Ingeniería en Logística y Transporte', 'Ingenierías', ['cuautitlan']),
]

# Definición del cuestionario. Tupla: (código, texto como en el Form, tipo, opciones, sensible, clasificable).
# `carrera` y `modalidad` aparecen DOS veces en el Form (una por plantel): ambas preguntas van al mismo código.
PREGUNTAS = {
    'ALUMNO': [
        ('nombre_completo', 'Nombre completo', 'texto', None, False, False),
        ('edad', '¿Cuál es tu edad?', 'numero', None, False, False),
        ('telefono', 'Teléfono', 'telefono', None, True, False),
        ('correo', 'Correo electrónico', 'correo', None, True, False),
        ('preparatoria', '¿En qué preparatoria estudias?', 'catalogo', 'preparatorias', False, False),
        ('plantel', '¿En qué plantel te gustaría estudiar?', 'opcion', 'planteles', False, False),
        ('carrera', '¿Qué carrera te gustaría estudiar?', 'multiple', 'carreras', False, False),
        ('modalidad', '¿Qué modalidad de estudio prefieres?', 'opcion', 'modalidades', False, False),
        ('factor_eleccion', '¿Qué es lo más importante para ti al elegir una universidad?', 'multiple', 'factores_eleccion', False, False),
        ('quiere_conocer', '¿Qué te gustaría conocer sobre la Universidad?', 'multiple', 'quiere_conocer', False, False),
        ('recibir_informacion', '¿Te gustaría recibir información sobre nuestras carreras y beneficios?', 'opcion', 'canal_informacion', False, False),
        # Recomendadas, todavía NO están en el Form (ver docs/formularios.md):
        ('consentimiento_aviso_privacidad', 'He leído y acepto el aviso de privacidad', 'consentimiento', 'si_no', False, False),
        ('tutor_nombre', 'Nombre de tu mamá, papá o tutor', 'texto', None, False, False),
        ('tutor_telefono', 'Teléfono de tu mamá, papá o tutor', 'telefono', None, True, False),
        ('evento', 'Código de evento', 'oculto', None, False, False),
        ('promotor', 'Código de promotor', 'oculto', None, False, False),
        ('token_familia', 'Código de familia', 'oculto', None, False, False),
    ],
    # ENCUESTA PARA PADRES DE FAMILIA (textos como están en el Form).
    'TUTOR': [
        ('consentimiento_aviso_privacidad', '¡AVISO DE PRIVACIDAD!', 'consentimiento', 'consentimiento_tutor', False, False),
        ('tutor_nombre', 'Nombre completo del padre, madre o tutor', 'texto', None, False, False),
        ('nombre_aspirante', 'Nombre completo del aspirante', 'texto', None, False, False),
        ('tutor_telefono', 'Teléfono del padre, madre o tutor', 'telefono', None, True, False),
        ('tutor_correo', 'Correo electrónico del padre, madre o tutor', 'correo', None, True, False),
        ('plantel', '¿Qué plantel te gustaría estudiar?', 'opcion', 'planteles', False, False),
        ('carrera', '¿Qué carrera le interesa estudiar a su hijo(a)?', 'multiple', 'carreras', False, False),
        ('modalidad', '¿Qué modalidad de estudio consideran más conveniente para su hijo(a)?', 'opcion', 'modalidades_tutor', False, False),
        ('tipo_universidad', '¿Qué tipo de universidad están considerando para su hijo(a)?', 'opcion', 'tipo_universidad', False, False),
        ('factor_eleccion', '¿Qué aspectos consideran más importantes al elegir una universidad?', 'multiple', 'factores_tutor', False, False),
        ('preocupacion', '¿Cuál es su principal preocupación respecto al ingreso de su hijo(a) a la universidad?', 'opcion', 'preocupaciones', False, False),
        ('apoyo_economico', '¿Qué tipo de apoyo económico considera más importante para la educación de su hijo(a)?', 'opcion', 'apoyo_economico', False, False),
        ('cuando_ingresa', '¿Cuándo tienen previsto que su hijo(a) ingrese a la universidad?', 'opcion', 'cuando_ingresa', False, False),
        ('motivo_ubicacion', '¿Cuál es el principal motivo por el que prefiere esta ubicación?', 'opcion', 'motivo_ubicacion', False, False),
        ('quiere_conocer', '¿Qué información le gustaría conocer sobre esta universidad?', 'opcion', 'quiere_conocer_tutor', False, False),
        ('recibir_informacion', '¿Le gustaría recibir información personalizada sobre carreras, becas y procesos de inscripción?', 'opcion', 'canal_tutor', False, False),
        # Recomendadas, todavía NO están en la encuesta (ver docs/formularios.md):
        ('aspirante_contacto', 'Correo o teléfono del aspirante', 'texto', None, True, False),
        ('evento', 'Código de evento', 'oculto', None, False, False),
        ('promotor', 'Código de promotor', 'oculto', None, False, False),
        ('token_familia', 'Código de familia', 'oculto', None, False, False),
    ],
}

# Preguntas que el Form puede repetir (una por sección/plantel).
REPETIBLES = {'carrera', 'modalidad'}
# Preguntas del catálogo que hoy NO están en el Form de la universidad: no se reportan como «faltan» con alarma.
RECOMENDADAS = {'consentimiento_aviso_privacidad', 'tutor_nombre', 'tutor_telefono', 'evento', 'promotor', 'token_familia',
                'aspirante_contacto'}
# Se comparan alumno contra tutor (lo demás se muestra lado a lado sin marcar diferencias).
COMPARABLES = {'plantel', 'carrera', 'modalidad'}

# Opciones que usan las reglas de prioridad y los grupos: se pueden renombrar en el panel, no borrar.
FIJAS = {
    'plantel': {'cuautitlan', 'tultepec'},
    'modalidad': {'semanal', 'sabatino', 'dominical', 'indeciso'},
    'factor_eleccion': {'colegiaturas', 'becas', 'horarios'},
    'quiere_conocer': {'requisitos', 'costos', 'becas'},
    'recibir_informacion': {'whatsapp', 'correo', 'no', 'si'},
    'consentimiento_aviso_privacidad': {'si', 'no'},
    'cuando_ingresa': {'proximo_ciclo', 'un_ano', 'dos_anos'},
    'apoyo_economico': {'becas', 'descuentos', 'facilidades', 'financiamiento'},
    'preocupacion': {'costos', 'horarios'},
}

# Dónde se muestra cada pregunta del sistema y con qué nombre corto.
PRESENTACION = {
    'plantel': ('interes', 'Plantel'), 'carrera': ('interes', 'Carreras que le interesan'), 'modalidad': ('interes', 'Modalidad'),
    'factor_eleccion': ('ideal', 'Lo más importante al elegir'), 'quiere_conocer': ('ideal', 'Quiere conocer'),
    'recibir_informacion': ('contacto', 'Recibir información'),
    'edad': ('generales', 'Edad'), 'preparatoria': ('generales', 'Preparatoria'),
    'consentimiento_aviso_privacidad': ('generales', 'Aceptó el aviso de privacidad'),
    'nombre_completo': ('generales', 'Nombre'), 'nombre_aspirante': ('generales', 'Nombre del aspirante'),
    'telefono': ('generales', 'Teléfono'), 'correo': ('generales', 'Correo'),
    'tutor_nombre': ('generales', 'Nombre del tutor'), 'tutor_telefono': ('generales', 'Teléfono del tutor'),
    'tutor_correo': ('generales', 'Correo del tutor'),
    'tipo_universidad': ('ideal', 'Tipo de universidad'),
    'preocupacion': ('expectativas', 'Principal preocupación'), 'apoyo_economico': ('expectativas', 'Apoyo económico que más importa'),
    'cuando_ingresa': ('expectativas', 'Cuándo entraría'), 'motivo_ubicacion': ('expectativas', 'Por qué ese plantel'),
    'aspirante_contacto': ('generales', 'Contacto del aspirante'),
    'evento': ('otras', 'Código de evento'), 'promotor': ('otras', 'Código de promotor'), 'token_familia': ('otras', 'Código de familia'),
}

# Códigos de versiones anteriores del programa (se quitan al actualizar; nunca se borran preguntas agregadas a mano).
RETIRADAS = {'plan_al_terminar', 'plan_al_terminar_otro', 'quiere_info_becas', 'necesita_para_inscribirse', 'quiere_asesor',
             'trabaja', 'dependencia_economica', 'escala_decision', 'decision_comentario', 'habilidades_reforzar',
             'plan_financiero', 'publica_privada', 'busca_en_privada', 'sosten_economico', 'forma_influencia',
             'tramites_independiente', 'quiere_costos_accesibles', 'periodo'}
CARRERAS_RETIRADAS = {'Administración de Empresas', 'Contaduría Pública', 'Mercadotecnia', 'Psicología', 'Enfermería', 'Nutrición',
                      'Ciencias de la Educación', 'Comunicación', 'Diseño Gráfico', 'Arquitectura',
                      'Ingeniería en Sistemas Computacionales', 'Ingeniería Civil', 'Ingeniería Mecatrónica', 'Gastronomía',
                      'Turismo', 'Criminología', 'Aún no lo decido'}
