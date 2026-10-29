"""
Fuentes de respuestas: Google Forms API (producción) o archivo de demostración.

Por qué Forms API y no la Sheet vinculada: cada respuesta trae un responseId estable
(idempotencia real) y lastSubmittedTime (importación incremental y detección de ediciones);
además no se rompe si alguien ordena o borra filas de la hoja.
"""

import json
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_tz

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

BASE = 'https://forms.googleapis.com/v1'
SCOPES = ['https://www.googleapis.com/auth/forms.responses.readonly',
          'https://www.googleapis.com/auth/forms.body.readonly']
# Solo al «Publicar en Google» (cambiar preguntas y opciones del Form). Importar sigue siendo de solo lectura.
SCOPES_EDICION = ['https://www.googleapis.com/auth/forms.body']


@dataclass
class RespuestaCruda:
    response_id: str
    enviada_en: datetime
    respuestas: dict[str, list[str]]
    original: dict = field(default_factory=dict)

    @classmethod
    def desde_api(cls, r: dict) -> 'RespuestaCruda':
        respuestas = {}
        for qid, ans in (r.get('answers') or {}).items():
            vals = [str(a['value']) for a in ((ans.get('textAnswers') or {}).get('answers') or []) if a.get('value') not in (None, '')]
            respuestas[str(qid)] = vals
        fecha = r.get('lastSubmittedTime') or r.get('createTime')
        return cls(str(r['responseId']), datetime.fromisoformat(fecha.replace('Z', '+00:00')), respuestas, r)


class ErrorFuente(Exception):
    pass


def explicar_http(codigo: int, cuerpo: str) -> str:
    pistas = {
        400: 'Petición inválida (¿el ID del Form está bien copiado?).',
        401: 'Credenciales vencidas o inválidas.',
        403: ('Sin permiso: comparte el Form como COLABORADOR (editor) con el correo de la cuenta de servicio, '
              'o, si la universidad no permite compartir fuera del dominio, usa el modo OAuth (docs/formularios.md).'),
        404: 'No existe un Form con ese ID (usa el ID de la URL de EDICIÓN: docs.google.com/forms/d/<ID>/edit).',
        429: 'Google limitó las peticiones (cuota); se reintenta solo en la siguiente corrida.',
    }
    return f'HTTP {codigo}: {pistas.get(codigo, "Error de Google.")} Detalle: {cuerpo}'


def entries_publicos(url_publica: str, sesion=None) -> dict[str, str]:
    """
    Lee la página pública del Form y devuelve {título normalizado: 'entry.NNNN'}.
    Es la fuente confiable de los entry.NNNN de los enlaces prellenados (la Forms API no los publica).
    Si el Form exige iniciar sesión, devuelve {} y hay que copiarlos a mano.
    """
    import re

    from . import texto
    if not url_publica:
        return {}
    try:
        r = (sesion or requests).get(url_publica, timeout=20, headers={'Accept-Language': 'es-MX'})
    except requests.RequestException:
        return {}
    m = re.search(r'FB_PUBLIC_LOAD_DATA_\s*=\s*(\[.*?\]);\s*</script>', r.text, re.S)
    if r.status_code != 200 or not m:
        return {}
    try:
        datos = json.loads(m.group(1))
        items = datos[1][1] or []
    except (ValueError, IndexError, TypeError):
        return {}
    res = {}
    for item in items:
        try:
            titulo, campos = item[1], item[4]
        except (IndexError, TypeError):
            continue
        if titulo and campos and isinstance(campos, list) and campos[0] and isinstance(campos[0][0], int):
            res[texto.normalizar(titulo)] = f'entry.{campos[0][0]}'
    return res


def modo_google() -> str:
    return 'oauth' if str(settings.CONFIG.get('GOOGLE_MODO', '')).lower() == 'oauth' else 'cuenta_servicio'


def ruta_token_oauth():
    return settings.DATA_DIR / 'google-token.json'


def ruta_cuenta_servicio():
    """Ruta del JSON de la cuenta de servicio. Tolera el error típico de Windows: «.json.json»
    (el Explorador oculta la extensión y la persona escribe «.json» de más)."""
    from pathlib import Path
    ruta = Path(settings.CONFIG.get('GOOGLE_CUENTA_SERVICIO') or settings.DATA_DIR / 'google-service-account.json')
    if not ruta.exists():
        doble = ruta.with_name(ruta.name + '.json')
        if doble.exists():
            return doble
    return ruta


def credenciales_listas() -> bool:
    """¿Hay con qué conectarse a Google? (solo revisa que exista el archivo, no que sea válido)."""
    return ruta_token_oauth().exists() if modo_google() == 'oauth' else ruta_cuenta_servicio().exists()


def credenciales_oauth(scopes=None):
    """Credenciales de una cuenta de Google de la universidad (modo OAuth). Renueva y guarda el token."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    ruta = ruta_token_oauth()
    if not ruta.exists():
        raise ErrorFuente(f'Falta autorizar la cuenta de Google: ejecuta «{settings.COMANDO} conectar_google».')
    cred = Credentials.from_authorized_user_file(str(ruta), scopes or SCOPES)
    if not cred.valid:
        cred.refresh(Request())
        ruta.write_text(cred.to_json(), encoding='utf-8')
    return cred


class FuenteGoogle:
    def __init__(self, sesion: requests.Session | None = None, token: str | None = None, edicion: bool = False):
        self.sesion = sesion or requests.Session()
        self._token = token
        self.edicion = edicion  # permiso para cambiar el Form (solo al publicar)

    def token(self) -> str:
        if self._token:
            return self._token
        clave = 'google:token:edicion' if self.edicion else 'google:token'
        t = cache.get(clave)
        if t:
            return t
        from google.auth.exceptions import GoogleAuthError
        from google.auth.transport.requests import Request
        scopes = SCOPES_EDICION if self.edicion else SCOPES
        try:
            if modo_google() == 'oauth':
                cred = credenciales_oauth(scopes)
            else:
                from google.oauth2 import service_account
                ruta = ruta_cuenta_servicio()
                try:
                    cred = service_account.Credentials.from_service_account_file(str(ruta), scopes=scopes)
                except FileNotFoundError as e:
                    raise ErrorFuente(f'No se encuentra el JSON de la cuenta de servicio en {ruta}. '
                                      'Revisa docs\\formularios.md, sección 1A (o usa el modo OAuth, sección 1B).') from e
                cred.refresh(Request())
        except GoogleAuthError as e:
            raise ErrorFuente(f'Google rechazó las credenciales: {e}') from e
        cache.set(clave, cred.token, 50 * 60)
        return cred.token

    def actualizar_form(self, form_id: str, solicitudes: list[dict], revision: str | None) -> dict:
        """forms.batchUpdate. Con `revision`, Google rechaza el cambio si alguien editó el Form mientras tanto."""
        cuerpo = {'requests': solicitudes, 'includeFormInResponse': False}
        if revision:
            cuerpo['writeControl'] = {'requiredRevisionId': revision}
        r = self.sesion.post(f'{BASE}/forms/{form_id}:batchUpdate', json=cuerpo, timeout=60,
                             headers={'Authorization': f'Bearer {self.token()}', 'Accept': 'application/json'})
        if r.status_code == 403 and 'scope' in r.text.lower():
            raise ErrorFuente('La cuenta de Google conectada solo tiene permiso de lectura. En modo OAuth vuelve a ejecutar '
                              f'«{settings.COMANDO} conectar_google» y acepta el permiso para editar los Forms.')
        if r.status_code == 400 and 'revision' in r.text.lower():
            raise ErrorFuente('Alguien cambió el Form en Google mientras revisabas. Vuelve a abrir «Publicar en Google» '
                              'para ver los cambios actualizados.')
        if r.status_code >= 400:
            raise ErrorFuente(explicar_http(r.status_code, r.text[:300]))
        return r.json()

    def info(self, formulario) -> dict:
        """Título, URL pública y preguntas del Form (para registrarlo y armar el mapeo)."""
        return self._get(f'/forms/{formulario.google_form_id}', {})

    def _get(self, ruta: str, params: dict) -> dict:
        intentos = settings.PROSPECTOS['REINTENTOS']
        for intento in range(1, intentos + 1):
            try:
                r = self.sesion.get(BASE + ruta, params=params, timeout=30,
                                    headers={'Authorization': f'Bearer {self.token()}', 'Accept': 'application/json'})
            except requests.RequestException as e:
                if intento == intentos:
                    raise ErrorFuente(f'Error de red: {e}') from e
                self._esperar(intento)
                continue
            if r.status_code == 401:
                cache.delete('google:token')
            # Cuota excedida (429) o error del servidor: reintento con backoff exponencial + jitter.
            if (r.status_code == 429 or r.status_code >= 500) and intento < intentos:
                self._esperar(intento)
                continue
            if r.status_code >= 400:
                raise ErrorFuente(explicar_http(r.status_code, r.text[:300]))
            return r.json()
        raise ErrorFuente('Sin respuesta de Google')

    @staticmethod
    def _esperar(intento: int):
        time.sleep(min(30.0, 0.5 * 2 ** intento) + random.random() * 0.25)

    def respuestas(self, formulario, desde: datetime | None):
        token_pagina = None
        while True:
            params = {'pageSize': 500}
            if desde:
                params['filter'] = 'timestamp >= ' + desde.astimezone(dt_tz.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            if token_pagina:
                params['pageToken'] = token_pagina
            datos = self._get(f'/forms/{formulario.google_form_id}/responses', params)
            for r in datos.get('responses', []):
                yield RespuestaCruda.desde_api(r)
            token_pagina = datos.get('nextPageToken')
            if not token_pagina:
                break

    def estructura(self, formulario) -> dict[str, str]:
        datos = self._get(f'/forms/{formulario.google_form_id}', {})
        preguntas = {}
        for item in datos.get('items', []):
            qid = ((item.get('questionItem') or {}).get('question') or {}).get('questionId')
            if qid:
                preguntas[qid] = item.get('title', '')
            for q in (item.get('questionGroupItem') or {}).get('questions', []):
                preguntas[q['questionId']] = f"{item.get('title', '')} - {(q.get('rowQuestion') or {}).get('title', '')}"
        return preguntas


class FuenteDemo:
    """Lee datos/demo-forms/<form_id>.json con el MISMO formato que la Forms API."""

    def _leer(self, formulario) -> dict:
        ruta = settings.DATA_DIR / 'demo-forms' / f'{formulario.google_form_id}.json'
        return json.loads(ruta.read_text(encoding='utf-8')) if ruta.exists() else {}

    def respuestas(self, formulario, desde):
        for r in self._leer(formulario).get('responses', []):
            c = RespuestaCruda.desde_api(r)
            if desde is None or c.enviada_en >= desde:
                yield c

    def estructura(self, formulario):
        return self._leer(formulario).get('estructura', {})


class FuenteMemoria:
    """Para pruebas: respuestas en memoria."""

    def __init__(self, respuestas: list[dict] | None = None):
        self.datos = respuestas or []

    def respuestas(self, formulario, desde):
        for r in self.datos:
            c = RespuestaCruda.desde_api(r)
            if desde is None or c.enviada_en >= desde:
                yield c

    def estructura(self, formulario):
        return {}


class FuenteAutomatica:
    """Formularios de demostración (ID «demo-…») salen de archivos; los reales, de la Forms API."""

    def __init__(self):
        self.demo, self.google = FuenteDemo(), FuenteGoogle()

    def _de(self, formulario):
        return self.demo if formulario.google_form_id.startswith('demo-') else self.google

    def respuestas(self, formulario, desde):
        return self._de(formulario).respuestas(formulario, desde)

    def estructura(self, formulario):
        return self._de(formulario).estructura(formulario)

    def info(self, formulario):
        return self.google.info(formulario)


def fuente_por_defecto():
    return FuenteAutomatica()


def ahora():
    return timezone.now()
