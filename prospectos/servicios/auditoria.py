"""Bitácora de quién vio / exportó / modificó datos personales."""

from ..models import Auditoria


def registrar(accion: str, objeto=None, detalle: dict | None = None, usuario=None, request=None) -> None:
    if request is not None and usuario is None and getattr(request, 'user', None) and request.user.is_authenticated:
        usuario = request.user
    Auditoria.objects.create(
        usuario=usuario if (usuario and getattr(usuario, 'pk', None)) else None,
        accion=accion,
        objeto_tipo=objeto.__class__.__name__ if objeto is not None else '',
        objeto_id=str(objeto.pk) if objeto is not None and getattr(objeto, 'pk', None) else '',
        detalle=detalle or None,
        ip=(request.META.get('REMOTE_ADDR', '') if request is not None else 'consola')[:45],
    )
