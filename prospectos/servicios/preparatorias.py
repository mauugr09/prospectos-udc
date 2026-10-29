"""Preparatorias escritas a mano en el Form: unir duplicados y ubicarlas en el mapa."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Count

from ..models import Evento, Preparatoria, Prospecto
from . import auditoria, texto


def elegir_principal(prepas) -> Preparatoria:
    """La que se queda: ubicada y revisada primero; luego la que tiene más aspirantes."""
    return sorted(prepas, key=lambda p: (p.lat is None, p.por_revisar, -getattr(p, 'n', 0), p.pk))[0]


def unir(prepas, usuario=None) -> Preparatoria:
    prepas = list(Preparatoria.objects.filter(pk__in=[p.pk for p in prepas]).annotate(n=Count('prospectos')))
    if len(prepas) < 2:
        raise ValueError('Selecciona al menos dos preparatorias.')
    queda = elegir_principal(prepas)
    otras = [p for p in prepas if p.pk != queda.pk]
    with transaction.atomic():
        alias = list(queda.alias or [])
        claves = {texto.clave_prepa(a) for a in alias} | {texto.clave_prepa(queda.nombre)}
        for o in otras:
            for nombre in [o.nombre, *(o.alias or [])]:
                if texto.clave_prepa(nombre) not in claves:
                    alias.append(nombre)
                    claves.add(texto.clave_prepa(nombre))
            for campo in ('municipio', 'alumnos_estimados', 'lat', 'lng'):
                if getattr(queda, campo) in (None, '') and getattr(o, campo) not in (None, ''):
                    setattr(queda, campo, getattr(o, campo))
        queda.alias = alias
        queda.save()
        ids = [o.pk for o in otras]
        Prospecto.objects.filter(preparatoria_id__in=ids).update(preparatoria=queda)
        Evento.objects.filter(preparatoria_id__in=ids).update(preparatoria=queda)
        # Las respuestas guardan el id de la prepa en el valor normalizado: se apuntan a la que queda.
        from ..models import RespuestaItem
        RespuestaItem.objects.filter(codigo='preparatoria', valor_normalizado__in=[str(i) for i in ids]).update(
            valor_normalizado=str(queda.pk))
        Preparatoria.objects.filter(pk__in=ids).delete()
        auditoria.registrar('unir_preparatorias', queda, {'unidas': ids}, usuario)
    return queda


def ubicar(prepa: Preparatoria, lat, lng, municipio: str | None = None, usuario=None) -> Preparatoria:
    lat, lng = Decimal(str(lat)).quantize(Decimal('0.0000001')), Decimal(str(lng)).quantize(Decimal('0.0000001'))
    # Rectángulo de México (con margen): evita guardar un clic accidental en el mar o en otro país.
    if not (Decimal('14.3') <= lat <= Decimal('32.8') and Decimal('-118.5') <= lng <= Decimal('-86.6')):
        raise ValueError('Esa ubicación está fuera de México.')
    prepa.lat, prepa.lng = lat, lng
    if municipio:
        prepa.municipio = texto.limpiar(municipio)[:120]
    prepa.por_revisar = False
    prepa.save()
    auditoria.registrar('ubicar_preparatoria', prepa, None, usuario)
    return prepa
