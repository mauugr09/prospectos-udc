"""Pruebas contra MariaDB: PROSPECTOS_BD_JSON='{"MOTOR":"mariadb",...}' pytest --ds=config.settings_pruebas_mariadb"""
import json
import os

os.environ.setdefault('PROSPECTOS_BD_JSON', json.dumps({
    'MOTOR': 'mariadb', 'HOST': '127.0.0.1', 'PUERTO': 3307, 'NOMBRE': 'prospectos', 'USUARIO': 'prospectos',
    'CLAVE': 'Clave-Prueba-123'}))

from .settings_pruebas import *  # noqa: E402,F401,F403
