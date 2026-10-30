"""
Emergencia: quita la verificación en 2 pasos a una cuenta que perdió su teléfono y sus códigos de recuperación,
cuando no hay otro administrador que lo haga desde el panel. Requiere estar sentado en la PC del programa.

    Prospectos.exe quitar_dos_pasos correo@udc.mx
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from ...models import Perfil
from ...servicios import auditoria, dos_pasos


class Command(BaseCommand):
    help = 'Quita la verificación en 2 pasos de una cuenta (emergencia, desde la PC del programa).'

    def add_arguments(self, parser):
        parser.add_argument('usuario', help='Correo con el que entra')

    def handle(self, *args, usuario, **o):
        u = get_user_model().objects.filter(username__iexact=usuario.strip()).first()
        if not u:
            raise CommandError(f'No existe la cuenta «{usuario}».')
        p = Perfil.de(u)
        if not p.dos_pasos_activo:
            self.stdout.write('Esa cuenta no tenía la verificación en 2 pasos.')
            return
        dos_pasos.desactivar(p)
        auditoria.registrar('dos_pasos_quitar', u, {'por': 'consola de la PC del programa'}, usuario=None)
        self.stdout.write(self.style.SUCCESS(
            f'Listo: {u.get_username()} ya puede entrar solo con su contraseña'
            + (' y tendrá que configurar la verificación de nuevo.' if dos_pasos.obligatoria(u) else '.')))
