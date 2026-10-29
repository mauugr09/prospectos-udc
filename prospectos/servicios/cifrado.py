"""
Cifrado de datos personales en la base (Fernet = AES-128-CBC + HMAC-SHA256) e índice ciego.

El cifrado usa IV aleatorio: el mismo correo cifrado dos veces da textos distintos, así que
para encontrar duplicados se guarda además un HMAC del valor normalizado (índice ciego) con
una llave DISTINTA a la de cifrado.
"""

import hashlib
import hmac
import json
import re

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _fernet() -> Fernet:
    return Fernet(settings.CONFIG['CLAVE_CIFRADO'].encode())


def cifrar(texto: str | None) -> str | None:
    if texto is None or texto == '':
        return None
    return _fernet().encrypt(texto.encode('utf-8')).decode('ascii')


def descifrar(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode('ascii')).decode('utf-8')
    except InvalidToken as e:
        raise ValueError('No se pudo descifrar: la CLAVE_CIFRADO de datos/config.json no corresponde a estos datos.') from e


class CampoCifrado(models.TextField):
    """TextField que se guarda cifrado y se lee en claro."""

    def from_db_value(self, value, expression, connection):
        return descifrar(value)

    def get_prep_value(self, value):
        return cifrar(value)


class JSONCifrado(models.TextField):
    """JSON que se guarda cifrado (la fila cruda de cada respuesta)."""

    def from_db_value(self, value, expression, connection):
        texto = descifrar(value)
        return json.loads(texto) if texto else None

    def to_python(self, value):
        # Al cargar un volcado (loaddata) llega como texto JSON.
        if isinstance(value, str):
            try:
                return json.loads(value)
            except ValueError:
                return value
        return value

    def value_to_string(self, obj):
        # Volcado (dumpdata): JSON real, en claro; se vuelve a cifrar al cargar.
        return json.dumps(self.value_from_object(obj), ensure_ascii=False)

    def get_prep_value(self, value):
        return None if value is None else cifrar(json.dumps(value, ensure_ascii=False))


def _hmac(tipo: str, valor: str) -> str:
    llave = settings.CONFIG['CLAVE_INDICE_CIEGO']
    if llave == settings.CONFIG['CLAVE_CIFRADO']:
        raise RuntimeError('CLAVE_INDICE_CIEGO debe ser distinta de CLAVE_CIFRADO.')
    return hmac.new(llave.encode(), f'{tipo}|{valor}'.encode(), hashlib.sha256).hexdigest()


def normalizar_telefono(telefono: str | None) -> str | None:
    digitos = re.sub(r'\D+', '', telefono or '')
    return digitos[-10:] if len(digitos) >= 10 else None


def indice_correo(correo: str | None) -> str | None:
    c = (correo or '').strip().lower()
    return _hmac('correo', c) if '@' in c else None


def indice_telefono(telefono: str | None) -> str | None:
    t = normalizar_telefono(telefono)
    return _hmac('telefono', t) if t else None


def enmascarar_correo(correo: str | None) -> str:
    if not correo or '@' not in correo:
        return '•••' if correo else '—'
    usuario, dominio = correo.split('@', 1)
    return f'{usuario[:1]}•••@{dominio[:1]}•••'


def enmascarar_telefono(telefono: str | None) -> str:
    if not telefono:
        return '—'
    return '•••• ••' + re.sub(r'\D+', '', telefono)[-2:]
