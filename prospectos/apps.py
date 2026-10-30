from django.apps import AppConfig


def _avatar_url(usuario):
    """Foto de «Mi perfil» para el avatar de unfold (menú y cabecera). None muestra la inicial."""
    from django.urls import reverse
    try:
        p = usuario.perfil
    except Exception:  # sin perfil todavía
        return None
    if not p.foto:
        return None
    return f"{reverse('prospectos:perfil_foto', args=[usuario.pk])}?v={p.foto_version}"


class ProspectosConfig(AppConfig):
    name = "prospectos"

    def ready(self):
        from django.contrib.auth import get_user_model
        get_user_model().add_to_class('avatar_url', property(_avatar_url))
