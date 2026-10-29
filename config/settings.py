"""
Configuración del sistema de prospectos.

Los valores sensibles (llaves, contraseñas) NO están aquí: se leen de `datos/config.json`,
que el lanzador genera la primera vez junto al ejecutable. Ese archivo y la base de datos
(`datos/prospectos.sqlite3`) son lo único que hay que respaldar.
"""

import json
import os
import secrets
import sys
from pathlib import Path

from cryptography.fernet import Fernet

# Código (dentro del .exe, PyInstaller lo extrae en sys._MEIPASS).
BASE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))

# Datos:
#  - Windows: carpeta «datos» junto a Prospectos.exe (portable).
#  - macOS: ~/Library/Application Support/Prospectos UDC. Dentro de Prospectos.app no se puede escribir
#    (macOS mueve las apps descargadas a una ubicación de solo lectura y la firma se rompería).
#  - Desarrollo: carpeta «datos» en la raíz del proyecto.
SISTEMA = 'mac' if sys.platform == 'darwin' else 'windows' if os.name == 'nt' else 'linux'
CONGELADO = bool(getattr(sys, 'frozen', False))
if CONGELADO and SISTEMA == 'mac':
    _DATOS_OMISION = Path.home() / 'Library' / 'Application Support' / 'Prospectos UDC'
elif CONGELADO:
    _DATOS_OMISION = Path(sys.executable).resolve().parent / 'datos'
else:
    _DATOS_OMISION = Path(__file__).resolve().parent.parent / 'datos'
DATA_DIR = Path(os.environ.get('PROSPECTOS_DATOS', _DATOS_OMISION))
# Cómo se llama el programa al escribir comandos (para los mensajes de ayuda).
COMANDO = ('Prospectos.exe' if SISTEMA == 'windows' else
           '/Applications/Prospectos.app/Contents/MacOS/Prospectos' if SISTEMA == 'mac' and CONGELADO else 'python lanzador.py')
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = DATA_DIR / 'config.json'


def _cargar_config() -> dict:
    """Lee datos/config.json; si no existe, lo crea con llaves nuevas."""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    cfg = {
        'SECRET_KEY': secrets.token_urlsafe(50),
        # Cifra correos, teléfonos y la fila cruda de cada respuesta. SI SE PIERDE, esos datos son irrecuperables.
        'CLAVE_CIFRADO': Fernet.generate_key().decode(),
        # HMAC para buscar duplicados sobre datos cifrados (índice ciego). Distinta de la de cifrado.
        'CLAVE_INDICE_CIEGO': secrets.token_urlsafe(32),
        'PUERTO': 8000,
        'GOOGLE_CUENTA_SERVICIO': str(DATA_DIR / 'google-service-account.json'),
        'IMPORTADOR_CADA_MINUTOS': 1,
        'CORREO': {'HOST': '', 'PUERTO': 587, 'USUARIO': '', 'CLAVE': '', 'TLS': True,
                   'REMITENTE': 'Admisiones <admisiones@universidad.edu.mx>'},
        'NOMBRE_INSTITUCION': 'la Universidad',
        'CUARENTENA_DIAS': 30,
        'RETENCION_MESES': 18,
        'DIAS_SIN_CONTACTO': 5,
        'RESPALDO_HORA': '02:30',
        'RESPALDO_DIAS_RETENCION': 14,
        'IA_HABILITADA': False,
        'IA_API_KEY': '',
        'IA_MODELO': 'claude-haiku-5-5',
    }
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')
    return cfg


CONFIG = _cargar_config()
if os.environ.get('PROSPECTOS_PRUEBAS'):
    CONFIG.update({'CLAVE_CIFRADO': 'xOxk1b8KXq3v3J6bJ4yS3QmS6m1b1pW8m6l8h3fQb2c=',
                   'CLAVE_INDICE_CIEGO': 'indice-ciego-de-pruebas'})

SECRET_KEY = CONFIG['SECRET_KEY']
DEBUG = os.environ.get('PROSPECTOS_DEBUG') == '1'
# Solo esta computadora; con "EN_RED": true, también por HTTPS desde la red local (ver prospectos/servicios/red.py).
from prospectos.servicios import red as _red  # noqa: E402  (no usa Django: solo nombres y certificados)

EN_RED = _red.activa(CONFIG)
ALLOWED_HOSTS = list(CONFIG.get('HOSTS_PERMITIDOS', ['127.0.0.1', 'localhost']))
if EN_RED:
    ALLOWED_HOSTS += [n for n in _red.nombres_servidor() if n not in ALLOWED_HOSTS]

INSTALLED_APPS = [
    'prospectos',  # primero: sus plantillas sustituyen a las del admin
    'unfold',      # tema moderno del panel (antes de django.contrib.admin)
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'prospectos.middleware.CambioDeClaveObligatorio',
    'prospectos.middleware.ReferrerEnMapas',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]

WSGI_APPLICATION = 'config.wsgi.application'

_SQLITE = {
    'ENGINE': 'django.db.backends.sqlite3',
    'NAME': DATA_DIR / 'prospectos.sqlite3',
    'OPTIONS': {
        # WAL + espera: el servidor web y el programador escriben a la vez sin "database is locked".
        'init_command': 'PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;',
        'timeout': 20,
        'transaction_mode': 'IMMEDIATE',
    },
}

# Base de datos: SQLite (un archivo, predeterminado) o MariaDB 10.11+ (servidor), según datos/config.json:
#   "BASE_DATOS": {"MOTOR": "mariadb", "HOST": "127.0.0.1", "PUERTO": 3306, "NOMBRE": "prospectos",
#                  "USUARIO": "prospectos", "CLAVE": "...", "BIN": "C:\\Program Files\\MariaDB 11.4\\bin"}
BD = {'MOTOR': 'sqlite', **CONFIG.get('BASE_DATOS', {})}
if os.environ.get('PROSPECTOS_BD_JSON'):  # para pruebas
    BD.update(json.loads(os.environ['PROSPECTOS_BD_JSON']))
ES_MARIADB = BD['MOTOR'].lower() in ('mariadb', 'mysql')

if ES_MARIADB:
    import pymysql  # controlador 100 % Python: no requiere instalar nada en Windows

    pymysql.version_info = (2, 2, 7, 'final', 0)  # Django pide mysqlclient >= 2.2.1
    pymysql.install_as_MySQLdb()
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': BD.get('NOMBRE', 'prospectos'),
            'USER': BD.get('USUARIO', 'prospectos'),
            'PASSWORD': BD.get('CLAVE', ''),
            'HOST': BD.get('HOST', '127.0.0.1'),
            'PORT': str(BD.get('PUERTO', 3306)),
            'CONN_MAX_AGE': 60,
            'CONN_HEALTH_CHECKS': True,
            'OPTIONS': {'charset': 'utf8mb4', 'init_command': "SET sql_mode='STRICT_TRANS_TABLES'"},
            'TEST': {'NAME': BD.get('NOMBRE_PRUEBAS', 'test_prospectos'), 'CHARSET': 'utf8mb4', 'COLLATION': 'utf8mb4_unicode_ci'},
        },
    }
    if (DATA_DIR / 'prospectos.sqlite3').exists():
        DATABASES['sqlite'] = _SQLITE  # origen para «pasar_a_mariadb»
else:
    DATABASES = {'default': _SQLITE}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es'  # 'es-mx' de Django deja la mitad del panel en inglés
TIME_ZONE = 'America/Mexico_City'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  # en el .exe ya viene con collectstatic
try:
    STATIC_ROOT.mkdir(exist_ok=True)
except OSError:
    pass
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}
WHITENOISE_USE_FINDERS = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/admin/login/'
LOGIN_REDIRECT_URL = '/admin/'

# Sesiones y cookies.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 8 * 3600
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = 'SAMEORIGIN'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'

# Correo: SMTP si está configurado; si no, se guardan como archivos en datos/correos (demo).
_correo = CONFIG.get('CORREO', {})
if _correo.get('HOST'):
    MAILERS = {'default': {'BACKEND': 'django.core.mail.backends.smtp.EmailBackend', 'OPTIONS': {
        'host': _correo['HOST'], 'port': int(_correo.get('PUERTO', 587)), 'username': _correo.get('USUARIO', ''),
        'password': _correo.get('CLAVE', ''), 'use_tls': bool(_correo.get('TLS', True)), 'timeout': 20}}}
else:
    MAILERS = {'default': {'BACKEND': 'django.core.mail.backends.filebased.EmailBackend',
                           'OPTIONS': {'file_path': str(DATA_DIR / 'correos')}}}
DEFAULT_FROM_EMAIL = _correo.get('REMITENTE', 'admisiones@localhost')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {'simple': {'format': '{asctime} {levelname} {name}: {message}', 'style': '{'}},
    'handlers': {
        'archivo': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': DATA_DIR / 'prospectos.log',
            'maxBytes': 5_000_000, 'backupCount': 5, 'encoding': 'utf-8', 'formatter': 'simple',
        },
        'consola': {'class': 'logging.StreamHandler', 'formatter': 'simple'},
    },
    'root': {'handlers': ['archivo', 'consola'], 'level': 'INFO'},
    'loggers': {'django.server': {'level': 'WARNING'}},
}

# --- Reglas de negocio (valores iniciales; los pesos se editan en el panel) ---------------
PROSPECTOS = {
    'TRASLAPE_MINUTOS': 10,
    'REINTENTOS': 5,
    'UMBRAL_AUTOMATICO': 0.93,
    'UMBRAL_REVISION': 0.82,
    'UMBRAL_SIN_PREPARATORIA': 0.96,
    'EDAD_MAYORIA': 18,
    'CUARENTENA_DIAS': int(CONFIG.get('CUARENTENA_DIAS', 30)),
    'RETENCION_MESES': int(CONFIG.get('RETENCION_MESES', 18)),
    'DIAS_SIN_CONTACTO': int(CONFIG.get('DIAS_SIN_CONTACTO', 5)),
    # Reglas de prioridad para el CUESTIONARIO VOCACIONAL real (suman 100; se cambian en «Reglas de prioridad»).
    'PESOS': {
        'pidio_informacion': 30, 'eligio_carrera': 20, 'pregunta_requisitos': 20,
        'eligio_modalidad': 10, 'pregunta_costos': 10, 'contacto_completo': 10,
        # Solo cuentan cuando la familia contestó su encuesta:
        'familia_pidio_informacion': 10, 'ingresa_proximo_ciclo': 15,
    },
    'SEGMENTOS': {
        'listo_para_convertir_score': 70, 'indeciso_desde_carreras': 3,
    },
    'RESPALDOS_DIR': DATA_DIR / 'respaldos',
    'RESPALDO_HORA': CONFIG.get('RESPALDO_HORA', '02:30'),
    'RESPALDO_DIAS_RETENCION': int(CONFIG.get('RESPALDO_DIAS_RETENCION', 14)),
    'IA_HABILITADA': bool(CONFIG.get('IA_HABILITADA')),
    'IA_API_KEY': CONFIG.get('IA_API_KEY', ''),
    'IA_MODELO': CONFIG.get('IA_MODELO', 'claude-haiku-5-5'),
    'IA_TEMAS': ['costos', 'becas', 'distancia', 'transporte', 'seguridad', 'tramites', 'horarios',
                 'documentos', 'calificaciones', 'trabajo', 'familia', 'otro'],
}

# --- Diseño del panel (django-unfold) con la identidad de la Universidad de Cuautitlán -------
# Azules tomados de udcm.mx: marino #172852, profundo #112349, rey #254099, lavanda #A5B3DF.
# Logo propio: coloca datos/logo.png (fondo transparente, versión clara) y aparece en el panel.
from django.templatetags.static import static  # noqa: E402
from django.urls import reverse_lazy  # noqa: E402

LOGO_ARCHIVO = DATA_DIR / 'logo.png'


def _logo(request):
    return '/marca/logo.png' if LOGO_ARCHIVO.exists() else None


def _permiso(codigo):
    return lambda request: request.user.has_perm(codigo)


UNFOLD = {
    'SITE_TITLE': 'Prospectos UDC',
    'SITE_HEADER': 'Universidad de Cuautitlán',
    'SITE_SUBHEADER': 'Admisiones · Prospectos',
    'SITE_URL': None,
    'SITE_SYMBOL': 'school',
    'SITE_LOGO': _logo,
    'SITE_FAVICONS': [{'rel': 'icon', 'sizes': 'any', 'type': 'image/svg+xml', 'href': lambda r: static('prospectos/marca/favicon.svg')}],
    'SHOW_HISTORY': True,
    'SHOW_VIEW_ON_SITE': False,
    'BORDER_RADIUS': '9px',
    # Sin 'THEME': cada quien elige Claro / Oscuro / Sistema en su menú de usuario (por defecto, el del sistema).
    'LOGIN': {'redirect_after': lambda r: reverse_lazy('admin:index')},
    'STYLES': [lambda r: static('prospectos/css/udc.css')],
    'SCRIPTS': [lambda r: static('prospectos/js/animaciones.js')],
    'DASHBOARD_CALLBACK': 'prospectos.views.contexto_tablero',
    'COLORS': {
        # Grises neutros del sistema (como macOS/iOS): el color lo pone solo la marca.
        'base': {
            '50': '#f5f5f7', '100': '#e8e8ed', '200': '#d2d2d7', '300': '#b0b0b8', '400': '#8e8e93',
            '500': '#6e6e73', '600': '#48484a', '700': '#3a3a3c', '800': '#2c2c2e', '900': '#1c1c1e', '950': '#000000',
        },
        # Azul UDC: 600 es el de los botones; 900/950 son el marino y profundo institucionales.
        'primary': {
            '50': '#eef2fc', '100': '#dde5f8', '200': '#bccbf1', '300': '#93a9e8', '400': '#6f8ff2',
            '500': '#4565d6', '600': '#2447b8', '700': '#254099', '800': '#1f3580', '900': '#172852', '950': '#112349',
        },
    },
    'SIDEBAR': {
        'show_search': True,
        'show_all_applications': False,
        'navigation': [
            {'title': 'Día a día', 'separator': False, 'items': [
                {'title': 'Inicio', 'icon': 'space_dashboard', 'link': reverse_lazy('admin:index')},
                {'title': 'A quién llamar hoy', 'icon': 'support_agent', 'link': reverse_lazy('prospectos:cola'),
                 'permission': _permiso('prospectos.change_prospecto'), 'badge': 'prospectos.views.badge_tareas'},
                {'title': 'Respuestas de los Forms', 'icon': 'inbox', 'link': reverse_lazy('prospectos:respuestas'),
                 'permission': _permiso('prospectos.view_prospecto'), 'badge': 'prospectos.views.badge_esperando'},
                {'title': 'Prospectos', 'icon': 'groups', 'link': reverse_lazy('admin:prospectos_prospecto_changelist'),
                 'permission': _permiso('prospectos.view_prospecto')},
                {'title': 'Familias por unir', 'icon': 'family_restroom', 'link': reverse_lazy('prospectos:familias'),
                 'permission': _permiso('prospectos.resolver_coincidencias'), 'badge': 'prospectos.views.badge_familias'},
                {'title': 'Posibles duplicados', 'icon': 'join_inner', 'link': reverse_lazy('admin:prospectos_posiblecoincidencia_changelist'),
                 'permission': _permiso('prospectos.resolver_coincidencias'), 'badge': 'prospectos.views.badge_coincidencias'},
            ]},
            {'title': 'Visitas a preparatorias', 'separator': True, 'items': [
                {'title': 'Eventos y QR', 'icon': 'qr_code_2', 'link': reverse_lazy('admin:prospectos_evento_changelist'),
                 'permission': _permiso('prospectos.view_evento')},
                {'title': 'Preparatorias', 'icon': 'apartment', 'link': reverse_lazy('admin:prospectos_preparatoria_changelist'),
                 'permission': _permiso('prospectos.view_preparatoria')},
                {'title': 'Etiquetas', 'icon': 'sell', 'link': reverse_lazy('admin:prospectos_etiqueta_changelist'),
                 'permission': _permiso('prospectos.view_etiqueta')},
            ]},
            {'title': 'Análisis', 'separator': True, 'items': [
                {'title': 'Reporte ejecutivo', 'icon': 'insights', 'link': reverse_lazy('prospectos:reporte'),
                 'permission': _permiso('prospectos.reporte_ejecutivo')},
                {'title': 'Mapa de cobertura', 'icon': 'map', 'link': reverse_lazy('prospectos:mapa'),
                 'permission': _permiso('prospectos.ver_reportes')},
            ]},
            {'title': 'Configuración', 'separator': True, 'collapsible': True, 'items': [
                {'title': 'Formularios de Google', 'icon': 'dynamic_form', 'link': reverse_lazy('admin:prospectos_formulario_changelist'),
                 'permission': _permiso('prospectos.view_formulario')},
                {'title': 'Preguntas y opciones', 'icon': 'quiz', 'link': reverse_lazy('admin:prospectos_pregunta_changelist'),
                 'permission': _permiso('prospectos.view_pregunta')},
                {'title': 'Carreras', 'icon': 'menu_book', 'link': reverse_lazy('admin:prospectos_carrera_changelist'),
                 'permission': _permiso('prospectos.view_carrera')},
                {'title': 'Mapa (Google Maps)', 'icon': 'map', 'link': reverse_lazy('prospectos:configurar_mapa'),
                 'permission': lambda r: r.user.is_superuser},
                {'title': 'Otras computadoras', 'icon': 'devices', 'link': reverse_lazy('prospectos:otras_computadoras'),
                 'permission': lambda r: r.user.is_superuser},
                {'title': 'Reglas de prioridad', 'icon': 'tune', 'link': reverse_lazy('prospectos:configuracion'),
                 'permission': _permiso('prospectos.configurar_scoring')},
                {'title': 'Usuarios', 'icon': 'person', 'link': reverse_lazy('admin:auth_user_changelist'),
                 'permission': _permiso('auth.view_user')},
                {'title': 'Roles', 'icon': 'admin_panel_settings', 'link': reverse_lazy('admin:auth_group_changelist'),
                 'permission': lambda r: r.user.is_superuser},
                {'title': 'Respaldos', 'icon': 'backup', 'link': reverse_lazy('admin:prospectos_respaldo_changelist'),
                 'permission': _permiso('prospectos.view_respaldo')},
                {'title': 'Bitácora de auditoría', 'icon': 'policy', 'link': reverse_lazy('admin:prospectos_auditoria_changelist'),
                 'permission': _permiso('prospectos.view_auditoria')},
            ]},
            {'title': 'Ayuda', 'separator': True, 'items': [
                {'title': '¿Cómo funciona?', 'icon': 'help', 'link': reverse_lazy('prospectos:ayuda')},
                {'title': 'Cambiar mi contraseña', 'icon': 'key', 'link': reverse_lazy('admin:password_change')},
            ]},
        ],
    },
}
