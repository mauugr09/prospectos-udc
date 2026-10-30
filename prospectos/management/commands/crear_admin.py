import getpass
import os

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from ...servicios import auditoria, semillas


class Command(BaseCommand):
    help = 'Crea (o restablece) un usuario administrador.'

    def add_arguments(self, parser):
        parser.add_argument('--correo')
        parser.add_argument('--clave-desde-entorno', action='store_true',
                            help='Toma la contraseña de PROSPECTOS_ADMIN_CLAVE (servidor sin teclado, p. ej. Docker).')

    def handle(self, *args, correo=None, clave_desde_entorno=False, **o):
        semillas.crear_roles()
        correo = (correo or input('Correo del administrador: ')).strip().lower()
        if '@' not in correo:
            raise CommandError('Correo no válido.')
        User = get_user_model()
        u = User.objects.filter(username=correo).first() or User(username=correo, email=correo)
        if clave_desde_entorno:
            clave = os.environ.get('PROSPECTOS_ADMIN_CLAVE', '')
            try:
                password_validation.validate_password(clave, u)
            except ValidationError as e:
                raise CommandError('PROSPECTOS_ADMIN_CLAVE no sirve: ' + ' '.join(e.messages)) from e
        for _ in range(0 if clave_desde_entorno else 3):
            clave = getpass.getpass('Contraseña (mínimo 12 caracteres): ')
            if clave != getpass.getpass('Repite la contraseña: '):
                self.stderr.write('No coinciden.')
                continue
            try:
                password_validation.validate_password(clave, u)
                break
            except ValidationError as e:
                self.stderr.write(' '.join(e.messages))
        else:
            if not clave_desde_entorno:
                raise CommandError('No se creó el usuario.')
        u.set_password(clave)
        u.is_staff = u.is_superuser = u.is_active = True
        u.save()
        u.groups.add(Group.objects.get(name='Administrador'))
        if clave_desde_entorno:  # esa contraseña quedó escrita en el archivo .env del servidor: se cambia al entrar
            from ...models import Perfil
            Perfil.objects.update_or_create(usuario=u, defaults={'debe_cambiar_clave': True})
        auditoria.registrar('usuario_admin', u)
        self.stdout.write(self.style.SUCCESS(f'Administrador listo: {correo}'))
