"""Anonimización irreversible, retención (LFPDPPP) y clasificación opcional con IA."""

import json
import logging
import re
from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ..models import EstadoRespuesta, Pregunta, Prospecto, RespuestaItem, Seguimiento
from . import auditoria

log = logging.getLogger('prospectos.seguridad')
P = settings.PROSPECTOS


def anonimizar(p: Prospecto, motivo: str, descartar_respuestas: bool = False) -> None:
    """Borra nombres, contactos, texto libre y la fila cruda; conserva lo agregable para estadísticas."""
    if p.anonimizado_en:
        return
    libres = set(Pregunta.objects.filter(Q(tipo__in=['texto', 'abierta', 'correo', 'telefono']) | Q(sensible=True))
                 .values_list('codigo', flat=True))
    libres |= {'nombre_completo', 'nombre_aspirante', 'tutor_nombre', 'token_familia'}
    with transaction.atomic():
        for r in p.respuestas.all():
            RespuestaItem.objects.filter(respuesta=r, codigo__in=libres).delete()
            r.raw_json = {'anonimizado': True}
            r.nombre_aspirante = ''
            r.token_familia = None
            if descartar_respuestas:
                r.estado = EstadoRespuesta.DESCARTADA
            r.save()
        p.nombre_aspirante = f'Anónimo #{p.pk}'
        p.correo = p.telefono = p.tutor_correo = p.tutor_telefono = None
        p.tutor_nombre = ''
        p.token_familia = None
        p.edad = None
        p.anonimizado_en = timezone.now()
        p.save()
        Seguimiento.objects.filter(prospecto=p).update(notas='')
        p.etiquetas.clear()
        auditoria.registrar('anonimizar', p, {'motivo': motivo})


def purgar_sin_consentimiento() -> int:
    """Tutor que negó el consentimiento o menor cuya cuarentena venció: se anonimiza y se descarta."""
    limite = timezone.now() - timedelta(days=P['CUARENTENA_DIAS'])
    n = 0
    qs = Prospecto.objects.filter(consentimiento=False, anonimizado_en__isnull=True).filter(
        Q(consentimiento_negado=True) | Q(creado_en__lte=limite))
    for p in qs.iterator(chunk_size=200):
        anonimizar(p, 'consentimiento_negado' if p.consentimiento_negado else 'cuarentena_vencida', True)
        n += 1
    return n


def anonimizar_inactivos() -> int:
    limite = timezone.now() - timedelta(days=30 * P['RETENCION_MESES'])
    n = 0
    qs = Prospecto.objects.filter(consentimiento=True, anonimizado_en__isnull=True).filter(
        Q(ultima_actividad_en__lte=limite) | Q(ultima_actividad_en__isnull=True, creado_en__lte=limite))
    for p in qs.iterator(chunk_size=200):
        anonimizar(p, 'retencion_inactividad')
        n += 1
    return n


# --------------------------------------------------------------------------- IA (opcional)
def depurar(texto: str) -> str:
    """Quita correos, URLs, teléfonos y números ANTES de enviar el texto fuera."""
    texto = re.sub(r'[\w.+-]+@[\w-]+(\.[\w-]+)+', '[correo]', texto)
    texto = re.sub(r'https?://\S+|www\.\S+', '[url]', texto, flags=re.I)
    texto = re.sub(r'\+?\d[\d\s().-]{6,}\d', '[numero]', texto)
    texto = re.sub(r'\d+', '#', texto)
    return texto.strip()[:1000]


def ia_habilitada() -> bool:
    return bool(P['IA_HABILITADA'] and P['IA_API_KEY'])


def _clasificar(texto: str) -> list[str]:
    temas = P['IA_TEMAS']
    r = requests.post('https://api.anthropic.com/v1/messages', timeout=30, headers={
        'x-api-key': P['IA_API_KEY'], 'anthropic-version': '2023-06-01', 'content-type': 'application/json',
    }, json={
        'model': P['IA_MODELO'], 'max_tokens': 100,
        'system': ('Clasificas respuestas abiertas de una encuesta vocacional en temas. Responde SOLO con JSON '
                   '{"temas": [...]} usando únicamente estos temas: ' + ', '.join(temas) + '. Máximo 3 temas.'),
        'messages': [{'role': 'user', 'content': texto}],
    })
    r.raise_for_status()
    salida = (r.json().get('content') or [{}])[0].get('text', '')
    m = re.search(r'\{.*\}', salida, re.S)
    datos = json.loads(m.group(0)) if m else {}
    return [t for t in datos.get('temas', []) if t in temas]


def clasificar_pendientes(limite: int = 100) -> int:
    if not ia_habilitada():
        return 0
    hechos = 0
    items = RespuestaItem.objects.filter(clasificado_en__isnull=True, pregunta__clasificable=True,
                                         respuesta__estado=EstadoRespuesta.VALIDA).exclude(valor='')[:limite]
    for item in items:
        texto = depurar(item.valor)
        if len(texto) < 3:
            item.etiqueta_ia, item.clasificado_en = {'temas': []}, timezone.now()
            item.save(update_fields=['etiqueta_ia', 'clasificado_en'])
            continue
        try:
            item.etiqueta_ia, item.clasificado_en = {'temas': _clasificar(texto)}, timezone.now()
            item.save(update_fields=['etiqueta_ia', 'clasificado_en'])
            hechos += 1
        except Exception as e:  # noqa: BLE001 - cuota/red: se reintenta en la siguiente corrida
            log.warning('Clasificación IA falló (item %s): %s', item.pk, type(e).__name__)
            break
    return hechos
