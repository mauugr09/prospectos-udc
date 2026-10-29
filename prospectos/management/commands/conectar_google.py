"""Modo OAuth: autoriza una cuenta de Google de la universidad para leer los Forms (alternativa a la cuenta de servicio)."""

import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ...servicios.fuentes import SCOPES, SCOPES_EDICION, ruta_token_oauth


class Command(BaseCommand):
    help = 'Abre el navegador para autorizar tu cuenta de Google (modo OAuth) y guarda el permiso en datos/google-token.json.'

    def handle(self, *args, **o):
        cliente = settings.DATA_DIR / 'google-oauth-cliente.json'
        if not cliente.exists():
            raise CommandError(f'Falta {cliente}: descárgalo de Google Cloud (ID de cliente OAuth tipo «App de escritorio»). '
                               'Ver docs/formularios.md, opción B.')
        from google_auth_oauthlib.flow import InstalledAppFlow
        flujo = InstalledAppFlow.from_client_secrets_file(str(cliente), SCOPES + SCOPES_EDICION)  # leer y, al publicar, editar
        self.stdout.write('Se abrirá el navegador: entra con la cuenta que es dueña o editora de los Forms y acepta.')
        cred = flujo.run_local_server(port=0, open_browser=True, prompt='consent',
                                      success_message='Listo. Ya puedes cerrar esta pestaña y volver a Prospectos.')
        ruta_token_oauth().write_text(cred.to_json(), encoding='utf-8')
        cfg = settings.CONFIG_FILE
        datos = json.loads(cfg.read_text(encoding='utf-8'))
        if datos.get('GOOGLE_MODO') != 'oauth':
            datos['GOOGLE_MODO'] = 'oauth'
            cfg.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'Cuenta autorizada. Prueba la conexión con: {settings.COMANDO} probar_google'))
