"""Entrada con usuario y contraseña, con una regla extra para las cuentas de demostración."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

DOMINIO_DEMO = '@demo.local'


class SinDemoConDatosReales(ModelBackend):
    """
    Las cuentas @demo.local tienen una contraseña conocida (está en los manuales) y no piden la verificación en 2 pasos.
    En cuanto existe un administrador real, dejan de poder entrar: si alguien olvidó borrar la demostración,
    no quedan como puerta abierta. El administrador real puede borrarla desde el Inicio.
    """

    def user_can_authenticate(self, user):
        if not super().user_can_authenticate(user):
            return False
        if user.get_username().lower().endswith(DOMINIO_DEMO):
            return not get_user_model().objects.filter(is_superuser=True, is_active=True).exclude(
                username__iendswith=DOMINIO_DEMO).exists()
        return True
