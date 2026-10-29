"""Modelo de datos del sistema de prospectos."""

import secrets
from difflib import SequenceMatcher

from django.conf import settings
from django.db import models
from django.utils import timezone

from .servicios import texto
from .servicios.cifrado import CampoCifrado, JSONCifrado, indice_correo, indice_telefono


class Cuestionario(models.TextChoices):
    ALUMNO = 'ALUMNO', 'Alumno (vocacional)'
    TUTOR = 'TUTOR', 'Tutor (papás)'


class EstadoRespuesta(models.TextChoices):
    VALIDA = 'valida', 'Válida'
    CUARENTENA = 'cuarentena', 'En cuarentena'
    SIN_CONSENTIMIENTO = 'sin_consentimiento', 'Sin consentimiento'
    DESCARTADA = 'descartada', 'Descartada'


class Estatus(models.TextChoices):
    """Embudo de conversión. El orden ES el orden del embudo."""
    REGISTRADO = 'registrado', 'Registrado'
    CONTACTADO = 'contactado', 'Contactado'
    OPEN_HOUSE = 'asistio_open_house', 'Asistió a open house'
    SOLICITO = 'solicito_inscripcion', 'Solicitó inscripción'
    INSCRITO = 'inscrito', 'Inscrito'
    DESCARTADO = 'descartado', 'Descartado'


EMBUDO = [Estatus.REGISTRADO, Estatus.CONTACTADO, Estatus.OPEN_HOUSE, Estatus.SOLICITO, Estatus.INSCRITO]
ACTIVOS = [Estatus.REGISTRADO, Estatus.CONTACTADO, Estatus.OPEN_HOUSE, Estatus.SOLICITO]


class Segmento(models.TextChoices):
    # El orden es la prioridad: el primero que aplique es el «grupo principal».
    NO_CONTACTAR = 'no_contactar', 'No quiere información'
    LISTO = 'listo_para_convertir', 'Listo para inscribirse'
    BECA = 'sensible_beca', 'Busca beca o precio'
    HORARIO = 'horario_flexible', 'Necesita horario flexible'
    INDECISO = 'indeciso_carrera', 'Aún no decide carrera'
    LARGO_PLAZO = 'largo_plazo', 'Entraría en un año o más'


class Plantel(models.TextChoices):
    CUAUTITLAN = 'cuautitlan', 'Cuautitlán'
    TULTEPEC = 'tultepec', 'Tultepec'


PRIORIDAD_SEGMENTO = [s.value for s in Segmento]  # orden de declaración = prioridad


def etiqueta_segmento(clave: str) -> str:
    """Nombre legible; tolera grupos retirados que aún no se recalculan."""
    return dict(Segmento.choices).get(clave) or clave.replace('_', ' ').capitalize()


class TipoSeguimiento(models.TextChoices):
    LLAMADA = 'llamada', 'Llamada'
    WHATSAPP = 'whatsapp', 'WhatsApp'
    CORREO = 'correo', 'Correo'
    VISITA = 'visita', 'Visita'
    CAMBIO_ESTATUS = 'cambio_estatus', 'Cambio de estatus'
    TAREA = 'tarea', 'Tarea'
    NOTA = 'nota', 'Nota interna'
    SISTEMA = 'sistema', 'Sistema'


CONTACTOS = {TipoSeguimiento.LLAMADA, TipoSeguimiento.WHATSAPP, TipoSeguimiento.CORREO, TipoSeguimiento.VISITA}


class Perfil(models.Model):
    """Datos extra del usuario del sistema."""
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='perfil')
    codigo_promotor = models.CharField('código de promotor', max_length=20, unique=True, null=True, blank=True,
                                       help_text='Se envía en el campo prellenado "promotor" del Form.')
    debe_cambiar_clave = models.BooleanField('debe cambiar su contraseña al entrar', default=False,
                                             help_text='Se activa al crear la cuenta o al restablecer la contraseña.')

    class Meta:
        verbose_name = 'perfil'

    def __str__(self):
        return str(self.usuario)


class Preparatoria(models.Model):
    nombre = models.CharField(max_length=255)
    nombre_normalizado = models.CharField(max_length=255, db_index=True, editable=False)
    municipio = models.CharField(max_length=120, blank=True)
    lat = models.DecimalField('latitud', max_digits=10, decimal_places=7, null=True, blank=True)
    lng = models.DecimalField('longitud', max_digits=10, decimal_places=7, null=True, blank=True)
    alumnos_estimados = models.PositiveIntegerField(null=True, blank=True, help_text='Para la tasa de respuesta.')
    alias = models.JSONField('otras formas de escribirla', default=list, blank=True,
                             help_text='Cómo la escriben los alumnos en el Form (se llena al unir preparatorias).')
    por_revisar = models.BooleanField('por revisar', default=False, db_index=True,
                                      help_text='Se creó sola con lo que escribió un alumno: revisa el nombre y ubícala en el mapa.')
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['nombre']
        constraints = [models.UniqueConstraint(fields=['nombre_normalizado', 'municipio'], name='prepa_unica')]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        self.nombre_normalizado = texto.normalizar(self.nombre)
        super().save(*args, **kwargs)

    @classmethod
    def resolver(cls, valor: str | None, crear: bool = False):
        """Busca la prepa por nombre, alias o parecido. Con `crear`, da de alta la que no exista (por revisar)."""
        n = texto.clave_prepa(valor)
        if not n:
            return None
        mejor, sim = None, 0.0
        for p in cls.objects.filter(activo=True):
            claves = {texto.clave_prepa(p.nombre), *(texto.clave_prepa(a) for a in p.alias or [])}
            if n in claves:
                return p
            s = max(texto.jaro_winkler(n, c) for c in claves if c) if any(claves) else 0
            if s > sim:
                mejor, sim = p, s
        if sim >= 0.95:  # mejor crear una de más (se unen con un clic) que juntar dos escuelas distintas
            return mejor
        if not crear:
            return None
        nombre = texto.limpiar(valor)[:255]
        return cls.objects.create(nombre=nombre[:1].upper() + nombre[1:], por_revisar=True)


class Carrera(models.Model):
    nombre = models.CharField(max_length=255)
    nombre_normalizado = models.CharField(max_length=255, unique=True, editable=False)
    area = models.CharField('área', max_length=120, blank=True)
    planteles = models.JSONField(default=list, blank=True, help_text='Planteles donde se ofrece.')
    alias = models.JSONField('otras formas de escribirla', default=list, blank=True,
                             help_text='Cómo aparece en el Form si no es igual al nombre (una por renglón).')
    activo = models.BooleanField(default=True, help_text='Apágala si ya no se ofrece: se conserva en el historial.')
    editada = models.BooleanField(default=False, editable=False,
                                  help_text='La cambió alguien en el panel: las actualizaciones del programa no la tocan.')

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        self.nombre_normalizado = texto.normalizar(self.nombre)
        super().save(*args, **kwargs)

    @classmethod
    def resolver(cls, valor: str | None):
        n = texto.normalizar(valor)
        if not n:
            return None
        exacta = cls.objects.filter(nombre_normalizado=n).first()
        if exacta:
            return exacta
        mejor, sim = None, 0.0
        for c in cls.objects.all():
            if n in {texto.normalizar(a) for a in c.alias or []}:
                return c
            if n.startswith(c.nombre_normalizado) or c.nombre_normalizado.startswith(n):
                return c
            s = SequenceMatcher(None, n, c.nombre_normalizado).ratio()
            if s > sim:
                mejor, sim = c, s
        return mejor if sim >= 0.93 else None  # p. ej. «Ingeniera Industrial» (así viene en el Form)


class Etiqueta(models.Model):
    nombre = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


def _codigo_evento():
    while True:
        c = 'EV' + secrets.token_hex(3).upper()
        if not Evento.objects.filter(codigo=c).exists():
            return c


class Evento(models.Model):
    codigo = models.CharField('código', max_length=20, unique=True, default=_codigo_evento, editable=False,
                              help_text='Viaja en el QR como campo prellenado "evento".')
    preparatoria = models.ForeignKey(Preparatoria, on_delete=models.PROTECT, related_name='eventos')
    promotor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='eventos')
    fecha = models.DateField(default=timezone.localdate, db_index=True)
    alumnos_asistentes = models.PositiveIntegerField(null=True, blank=True)
    meta_registros = models.PositiveIntegerField('meta de registros', null=True, blank=True)
    costo = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notas = models.TextField(blank=True)

    class Meta:
        ordering = ['-fecha']

    def __str__(self):
        return f'{self.codigo} · {self.preparatoria} · {self.fecha:%d/%m/%Y}'


class Formulario(models.Model):
    nombre = models.CharField(max_length=255)
    tipo = models.CharField(max_length=10, choices=Cuestionario.choices)
    google_form_id = models.CharField('ID del Form', max_length=255, unique=True,
                                      help_text='Pega la URL de EDICIÓN del Form (docs.google.com/forms/d/<ID>/edit) o solo el ID.')
    url_publica = models.URLField('URL pública (viewform)', max_length=500, blank=True)
    mapeo_campos = models.JSONField('mapeo questionId → código', default=dict, blank=True)
    campos_prellenado = models.JSONField('campos prellenados (código → entry.NNNN)', default=dict, blank=True)
    activo = models.BooleanField(default=True)
    ultima_respuesta_en = models.DateTimeField(null=True, blank=True, editable=False)
    ultima_importacion_en = models.DateTimeField(null=True, blank=True, editable=False)
    ultimo_error = models.TextField(blank=True, editable=False)
    errores_consecutivos = models.PositiveIntegerField(default=0, editable=False)

    def __str__(self):
        return self.nombre

    @staticmethod
    def extraer_id(texto: str) -> str:
        """Acepta la URL completa de edición o el ID solo."""
        import re
        m = re.search(r'/forms/d/(?!e/)([A-Za-z0-9_-]{20,})', texto or '')
        return m.group(1) if m else (texto or '').strip()

    def save(self, *args, **kwargs):
        self.google_form_id = self.extraer_id(self.google_form_id)
        super().save(*args, **kwargs)

    def url_prellenada(self, valores: dict) -> str | None:
        from urllib.parse import urlencode
        if not self.url_publica:
            return None
        params = {'usp': 'pp_url'}
        for codigo, valor in valores.items():
            entry = (self.campos_prellenado or {}).get(codigo)
            if entry and valor:
                params[entry] = valor
        return self.url_publica + ('&' if '?' in self.url_publica else '?') + urlencode(params)


class Importacion(models.Model):
    formulario = models.ForeignKey(Formulario, on_delete=models.CASCADE, related_name='importaciones')
    iniciada_en = models.DateTimeField(default=timezone.now)
    terminada_en = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=12, default='en_curso')
    nuevas = models.PositiveIntegerField(default=0)
    actualizadas = models.PositiveIntegerField(default=0)
    omitidas = models.PositiveIntegerField(default=0)
    mensaje = models.TextField(blank=True)

    class Meta:
        ordering = ['-iniciada_en']
        verbose_name_plural = 'importaciones'


class TipoPregunta(models.TextChoices):
    """Tipos que puede elegir una persona al agregar una pregunta (el resto los usa solo el sistema)."""
    TEXTO = 'texto', 'Respuesta corta'
    PARRAFO = 'abierta', 'Párrafo'
    NUMERO = 'numero', 'Número'
    OPCION = 'opcion', 'Opción múltiple (una respuesta)'
    MULTIPLE = 'multiple', 'Casillas (varias respuestas)'
    SI_NO = 'si_no', 'Sí / No'


TEMAS_PREGUNTA = [('interes', 'Lo que quiere estudiar'), ('ideal', 'Su universidad ideal'),
                  ('expectativas', 'Expectativas de la familia'), ('contacto', 'Cómo quiere que lo contactemos'),
                  ('generales', 'Datos generales'), ('otras', 'Otras preguntas')]


class Pregunta(models.Model):
    cuestionario = models.CharField(max_length=10, choices=Cuestionario.choices)
    codigo = models.CharField('código', max_length=60, blank=True,
                              help_text='Identificador interno. Si lo dejas vacío se arma con el texto.')
    texto = models.TextField('texto como está en el Form',
                             help_text='Cópialo igual que en el Google Form: así se reconoce sola al sincronizar.')
    etiqueta = models.CharField('nombre corto', max_length=80, blank=True,
                                help_text='Cómo se muestra en la ficha y en los reportes (p. ej. «Trabaja»).')
    tema = models.CharField('dónde mostrarla', max_length=20, choices=TEMAS_PREGUNTA, default='otras')
    tipo = models.CharField(max_length=20)
    opciones = models.JSONField('catálogo', null=True, blank=True, editable=False)
    sensible = models.BooleanField(default=False, help_text='Dato de contacto: se guarda cifrado y no en reportes.')
    clasificable = models.BooleanField('clasificable con IA', default=False)
    orden = models.PositiveSmallIntegerField(default=0)
    de_sistema = models.BooleanField('del sistema', default=False, editable=False,
                                     help_text='Las reglas de prioridad la usan: no se puede borrar ni cambiar de tipo.')
    editada = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ['cuestionario', 'orden']
        constraints = [models.UniqueConstraint(fields=['cuestionario', 'codigo'], name='pregunta_unica')]

    def __str__(self):
        return self.etiqueta or self.texto[:80]

    def save(self, *args, **kwargs):
        if not self.codigo:
            base = texto.normalizar(self.etiqueta or self.texto).replace(' ', '_')[:50] or 'pregunta'
            codigo, n = base, 2
            while Pregunta.objects.filter(cuestionario=self.cuestionario, codigo=codigo).exclude(pk=self.pk).exists():
                codigo, n = f'{base}_{n}', n + 1
            self.codigo = codigo
        super().save(*args, **kwargs)

    @property
    def con_opciones(self) -> bool:
        return self.tipo in ('opcion', 'multiple')

    def lista_opciones(self) -> list:
        if not hasattr(self, '_opciones_cache'):
            self._opciones_cache = list(self.opciones_lista.all()) if self.pk else []
        return self._opciones_cache

    def etiquetas_opciones(self) -> dict:
        """{clave: texto} de las opciones editables; si no tiene, las del código (compatibilidad)."""
        lista = self.lista_opciones()
        if lista:
            return {o.clave: o.texto for o in lista}
        from . import catalogos
        if isinstance(self.opciones, str):
            return catalogos.CATALOGOS.get(self.opciones, {})
        return self.opciones if isinstance(self.opciones, dict) else {}

    def textos_opciones(self) -> dict:
        """{clave: [texto, alias…]} para reconocer lo que llega del Form."""
        lista = self.lista_opciones()
        if lista:
            return {o.clave: [o.texto, *o.alias_lista()] for o in lista}
        return {k: [v] for k, v in self.etiquetas_opciones().items()}


class OpcionPregunta(models.Model):
    pregunta = models.ForeignKey(Pregunta, on_delete=models.CASCADE, related_name='opciones_lista')
    clave = models.CharField(max_length=60, blank=True, help_text='Se arma sola con el texto.')
    texto = models.CharField('texto como está en el Form', max_length=255)
    alias = models.TextField('otras formas', blank=True,
                             help_text='Textos anteriores u otras formas en que llega (una por renglón). '
                                       'Al cambiar el texto, el anterior se guarda aquí solo.')
    orden = models.PositiveSmallIntegerField(default=0)
    fija = models.BooleanField(default=False, editable=False, help_text='La usan las reglas: se puede renombrar, no borrar.')

    class Meta:
        ordering = ['orden', 'id']
        verbose_name = 'opción'
        verbose_name_plural = 'opciones'
        constraints = [models.UniqueConstraint(fields=['pregunta', 'clave'], name='opcion_unica')]

    def __str__(self):
        return self.texto

    def alias_lista(self) -> list[str]:
        return [a.strip() for a in (self.alias or '').splitlines() if a.strip()]

    def save(self, *args, **kwargs):
        if not self.clave:
            base = texto.normalizar(self.texto).replace(' ', '_')[:50] or 'opcion'
            clave, n = base, 2
            while OpcionPregunta.objects.filter(pregunta_id=self.pregunta_id, clave=clave).exclude(pk=self.pk).exists():
                clave, n = f'{base}_{n}', n + 1
            self.clave = clave
        if self.pk:
            antes = OpcionPregunta.objects.filter(pk=self.pk).values_list('texto', flat=True).first()
            if antes and texto.normalizar(antes) != texto.normalizar(self.texto) and antes not in self.alias_lista():
                self.alias = '\n'.join([*self.alias_lista(), antes])  # las respuestas viejas siguen reconociéndose
        super().save(*args, **kwargs)


class ProspectoQuerySet(models.QuerySet):
    def utilizables(self):
        """Para seguimiento: con consentimiento, sin fusionar ni anonimizar."""
        return self.filter(consentimiento=True, fusionado_en__isnull=True, anonimizado_en__isnull=True)

    def reportables(self):
        """Para estadísticas: con consentimiento y sin fusionar (incluye anonimizados)."""
        return self.filter(consentimiento=True, fusionado_en__isnull=True)


class Prospecto(models.Model):
    CAMPOS_CONTACTO = ['correo', 'telefono', 'tutor_correo', 'tutor_telefono']

    nombre_aspirante = models.CharField('aspirante', max_length=255)
    nombre_normalizado = models.CharField(max_length=255, db_index=True, editable=False)
    preparatoria = models.ForeignKey(Preparatoria, null=True, blank=True, on_delete=models.SET_NULL, related_name='prospectos')
    evento = models.ForeignKey(Evento, null=True, blank=True, on_delete=models.SET_NULL, related_name='prospectos')
    promotor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='prospectos_promovidos')
    asesor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='prospectos_asignados')
    edad = models.PositiveSmallIntegerField(null=True, blank=True)
    plantel = models.CharField(max_length=12, choices=Plantel.choices, blank=True, db_index=True)
    carrera = models.ForeignKey(Carrera, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
                                verbose_name='carrera principal', help_text='La primera que marcó.')
    carreras = models.ManyToManyField(Carrera, blank=True, related_name='interesados', verbose_name='carreras de interés')
    canal_informacion = models.CharField('quiere información por', max_length=12, blank=True,
                                         choices=[('whatsapp', 'WhatsApp'), ('correo', 'Correo'),
                                                  ('si', 'Sí (lo pidió la familia, sin canal)'), ('no', 'No quiere información')])
    no_contactar = models.BooleanField('no quiere información', default=False, db_index=True,
                                       help_text='Contestó «No, gracias»: no entra a la cola ni recibe correos.')
    carrera_tutor = models.ForeignKey(Carrera, null=True, blank=True, on_delete=models.SET_NULL, related_name='+', verbose_name='carrera (tutor)')
    modalidad = models.CharField(max_length=30, blank=True, choices=[('semanal', 'Semanal / escolarizada'), ('sabatino', 'Sabatino'),
                                                                  ('dominical', 'Dominical'), ('indeciso', 'Aún no lo sabe')])
    modalidad_tutor = models.CharField(max_length=30, blank=True)
    token_familia = models.CharField('código de familia', max_length=64, unique=True, null=True, blank=True)

    correo = CampoCifrado(null=True, blank=True)
    correo_bi = models.CharField(max_length=64, null=True, blank=True, db_index=True, editable=False)
    telefono = CampoCifrado('teléfono', null=True, blank=True)
    telefono_bi = models.CharField(max_length=64, null=True, blank=True, db_index=True, editable=False)
    tutor_nombre = models.CharField('tutor', max_length=255, blank=True)
    tutor_correo = CampoCifrado('correo del tutor', null=True, blank=True)
    tutor_correo_bi = models.CharField(max_length=64, null=True, blank=True, db_index=True, editable=False)
    tutor_telefono = CampoCifrado('teléfono del tutor', null=True, blank=True)
    tutor_telefono_bi = models.CharField(max_length=64, null=True, blank=True, db_index=True, editable=False)

    tiene_alumno = models.BooleanField(default=False)
    tiene_tutor = models.BooleanField(default=False)
    consentimiento = models.BooleanField(default=False, db_index=True)
    origen_consentimiento = models.CharField(max_length=10, blank=True)
    consentimiento_en = models.DateTimeField(null=True, blank=True)
    consentimiento_negado = models.BooleanField(default=False)
    permiso_registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                               related_name='+', verbose_name='permiso del tutor registrado por')
    permiso_nota = models.CharField('cómo se obtuvo el permiso', max_length=255, blank=True)

    score = models.PositiveSmallIntegerField('prioridad', default=0, db_index=True)
    score_detalle = models.JSONField(default=dict, blank=True)
    segmentos = models.JSONField(default=list, blank=True)
    segmento_principal = models.CharField(max_length=40, blank=True, choices=Segmento.choices, db_index=True)
    brechas = models.JSONField(default=list, blank=True)
    tiene_brecha = models.BooleanField(default=False, db_index=True)
    estatus = models.CharField(max_length=30, choices=Estatus.choices, default=Estatus.REGISTRADO, db_index=True)
    etiquetas = models.ManyToManyField(Etiqueta, blank=True)

    ultimo_contacto_en = models.DateTimeField(null=True, blank=True)
    ultima_actividad_en = models.DateTimeField(null=True, blank=True, db_index=True)
    bienvenida_enviada_en = models.DateTimeField(null=True, blank=True)
    anonimizado_en = models.DateTimeField(null=True, blank=True)
    fusionado_en = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='absorbidos')
    creado_en = models.DateTimeField('registro', default=timezone.now, db_index=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    objects = ProspectoQuerySet.as_manager()

    class Meta:
        ordering = ['-score']
        permissions = [
            ('ver_datos_personales', 'Puede ver correos y teléfonos en claro'),
            ('exportar_prospectos', 'Puede exportar prospectos'),
            ('ver_propios', 'Solo ve sus propios prospectos (promotor)'),
            ('ver_reportes', 'Puede ver tablero y reportes'),
            ('reporte_ejecutivo', 'Puede ver el reporte ejecutivo'),
            ('configurar_scoring', 'Puede cambiar pesos de scoring'),
            ('resolver_coincidencias', 'Puede fusionar o rechazar coincidencias'),
            ('ver_eventos_propios', 'Solo ve sus propios eventos (promotor)'),
        ]

    def __str__(self):
        return self.nombre_aspirante

    def save(self, *args, **kwargs):
        self.nombre_normalizado = texto.clave_nombre(self.nombre_aspirante)
        self.correo_bi = indice_correo(self.correo)
        self.telefono_bi = indice_telefono(self.telefono)
        self.tutor_correo_bi = indice_correo(self.tutor_correo)
        self.tutor_telefono_bi = indice_telefono(self.tutor_telefono)
        super().save(*args, **kwargs)

    def tiene_contacto(self) -> bool:
        return any(getattr(self, c) for c in self.CAMPOS_CONTACTO)

    @property
    def posicion_embudo(self) -> int:
        return EMBUDO.index(self.estatus) if self.estatus in EMBUDO else -1


class Respuesta(models.Model):
    formulario = models.ForeignKey(Formulario, on_delete=models.PROTECT, related_name='respuestas')
    cuestionario = models.CharField(max_length=10, choices=Cuestionario.choices, db_index=True)
    google_response_id = models.CharField(max_length=255)
    hash_respuesta = models.CharField(max_length=64, unique=True)
    prospecto = models.ForeignKey(Prospecto, null=True, blank=True, on_delete=models.SET_NULL, related_name='respuestas')
    evento = models.ForeignKey(Evento, null=True, blank=True, on_delete=models.SET_NULL, related_name='respuestas')
    promotor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    token_familia = models.CharField('código de familia', max_length=64, null=True, blank=True, db_index=True)
    nombre_aspirante = models.CharField(max_length=255, blank=True)
    consentimiento_aviso_privacidad = models.BooleanField(default=False)
    consentimiento_en = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=EstadoRespuesta.choices, default=EstadoRespuesta.CUARENTENA, db_index=True)
    enviada_en = models.DateTimeField(db_index=True)
    version = models.PositiveIntegerField(default=1)
    raw_json = JSONCifrado()

    class Meta:
        ordering = ['enviada_en', 'id']

    def valor(self, codigo: str, normalizado: bool = True):
        for i in self._items():
            if i.codigo == codigo:
                return (i.valor_normalizado or i.valor) if normalizado else i.valor
        return None

    def valores(self, codigo: str) -> list[str]:
        return [i.valor_normalizado or i.valor for i in self._items() if i.codigo == codigo and (i.valor_normalizado or i.valor)]

    def _items(self):
        if not hasattr(self, '_cache_items'):
            self._cache_items = list(self.items.all())
        return self._cache_items


class RespuestaItem(models.Model):
    respuesta = models.ForeignKey(Respuesta, on_delete=models.CASCADE, related_name='items')
    pregunta = models.ForeignKey(Pregunta, null=True, blank=True, on_delete=models.SET_NULL)
    codigo = models.CharField(max_length=60)
    valor = models.TextField(blank=True)
    valor_normalizado = models.CharField(max_length=120, null=True, blank=True)
    etiqueta_ia = models.JSONField(null=True, blank=True)
    clasificado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['codigo', 'valor_normalizado'])]


class Seguimiento(models.Model):
    prospecto = models.ForeignKey(Prospecto, on_delete=models.CASCADE, related_name='seguimientos')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    tipo = models.CharField(max_length=20, choices=TipoSeguimiento.choices)
    fecha = models.DateTimeField(default=timezone.now, db_index=True)
    notas = models.TextField(blank=True)
    estatus_anterior = models.CharField(max_length=30, blank=True, choices=Estatus.choices)
    estatus_nuevo = models.CharField(max_length=30, blank=True, choices=Estatus.choices)
    vence_en = models.DateTimeField(null=True, blank=True)
    completada_en = models.DateTimeField(null=True, blank=True)
    automatica = models.BooleanField(default=False)

    class Meta:
        ordering = ['-fecha']

    def __str__(self):
        return f'{self.get_tipo_display()} · {timezone.localtime(self.fecha):%d/%m/%Y %H:%M}'


class PosibleCoincidencia(models.Model):
    prospecto = models.ForeignKey(Prospecto, on_delete=models.CASCADE, related_name='coincidencias', verbose_name='respuesta nueva')
    candidato = models.ForeignKey(Prospecto, on_delete=models.CASCADE, related_name='+', verbose_name='prospecto existente')
    similitud = models.FloatField()
    motivo = models.CharField(max_length=255)
    estado = models.CharField(max_length=12, default='pendiente', db_index=True,
                              choices=[('pendiente', 'Pendiente'), ('fusionada', 'Fusionada'), ('rechazada', 'Rechazada')])
    revisado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    revisado_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'posible duplicado'
        verbose_name_plural = 'posibles duplicados'
        ordering = ['-similitud']
        constraints = [models.UniqueConstraint(fields=['prospecto', 'candidato'], name='coincidencia_unica')]

    def __str__(self):
        return f'{self.prospecto} ↔ {self.candidato}'


class Configuracion(models.Model):
    clave = models.CharField(max_length=100, unique=True)
    valor = models.JSONField()
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    actualizado_en = models.DateTimeField(auto_now=True)

    @classmethod
    def obtener(cls, clave: str, defecto=None):
        fila = cls.objects.filter(clave=clave).first()
        return fila.valor if fila else defecto

    @classmethod
    def guardar(cls, clave: str, valor, usuario=None):
        cls.objects.update_or_create(clave=clave, defaults={'valor': valor, 'actualizado_por': usuario})


class Auditoria(models.Model):
    """Solo inserción: guarda nombres de campos e IDs, nunca valores personales."""
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    accion = models.CharField(max_length=40, db_index=True)
    objeto_tipo = models.CharField(max_length=60, blank=True)
    objeto_id = models.CharField(max_length=40, blank=True)
    detalle = models.JSONField(null=True, blank=True)
    ip = models.CharField(max_length=45, blank=True)
    creado_en = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-creado_en']
        verbose_name = 'registro de auditoría'
        verbose_name_plural = 'bitácora de auditoría'

    def save(self, *args, **kwargs):
        if self.pk:
            raise RuntimeError('La bitácora de auditoría es de solo inserción.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError('La bitácora de auditoría es de solo inserción.')


class Respaldo(models.Model):
    archivo = models.CharField(max_length=255)
    bytes = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    estado = models.CharField(max_length=12)
    mensaje = models.TextField(blank=True)
    verificado_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-creado_en']
