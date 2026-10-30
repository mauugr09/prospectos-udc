"""Configuración para pruebas: llaves fijas, datos en una carpeta temporal, correo en memoria."""
import os
import tempfile

os.environ['PROSPECTOS_PRUEBAS'] = '1'
os.environ['PROSPECTOS_DATOS'] = tempfile.mkdtemp(prefix='prospectos-pruebas-')

from .settings import *  # noqa: E402,F401,F403

MAILERS = {'default': {'BACKEND': 'django.core.mail.backends.locmem.EmailBackend'}}
CORREO_SINCRONO = True
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
ALLOWED_HOSTS = ['*']
LOGGING['root']['handlers'] = ['archivo']  # noqa: F405

CONFIG = {**CONFIG, 'DOS_PASOS_ADMINS': False}  # noqa: F405  (las pruebas de 2 pasos lo encienden)
