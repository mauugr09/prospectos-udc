"""Anonimización irreversible, retención (LFPDPPP) y clasificación opcional con IA."""

import logging
import re
from datetime import timedelta

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
        p.correo = p.telefono = p.tutor_correo = p.tutor_telefono = p.curp = None
        p.fecha_nacimiento = None
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


# --------------------------------------------------------------------------- temas de las respuestas abiertas (propio)
# Antes esto usaba una IA externa; ahora son palabras clave propias: gratis, sin internet y sin enviar textos fuera.
# Un texto puede tener varios temas (máximo 3). Para afinar, agrega palabras (sin acentos) a la lista del tema.
PALABRAS_TEMA = {
    'costos': ['costo', 'cuesta', 'caro', 'cara', 'precio', 'colegiatura', 'mensualidad', 'pagar', 'pago', 'dinero', 'economic',
               'inscripcion cuesta', 'barato', 'cuota'],
    'becas': ['beca', 'descuento', 'apoyo economico', 'financiamiento', 'credito educativo'],
    'distancia': ['lejos', 'distancia', 'cerca', 'queda', 'ubicacion', 'donde esta'],
    'transporte': ['transporte', 'camion', 'combi', 'pasaje', 'metro', 'mexibus', 'trasladar', 'llegar'],
    'seguridad': ['seguro', 'segura', 'inseguridad', 'asalto', 'peligro', 'vigilancia'],
    'tramites': ['tramite', 'inscripcion', 'inscribir', 'proceso', 'requisito', 'examen', 'ficha', 'revalid', 'equivalencia'],
    'horarios': ['horario', 'sabado', 'sabatino', 'turno', 'matutino', 'vespertino', 'entre semana', 'fin de semana', 'domingo'],
    'documentos': ['certificado', 'documento', 'acta', 'curp', 'papeles', 'constancia', 'titulo'],
    'calificaciones': ['promedio', 'calificacion', 'reprob', 'materias', 'extraordinario', 'adeudo'],
    'trabajo': ['trabajo', 'trabajar', 'empleo', 'laboral', 'practicas', 'servicio social', 'bolsa de trabajo'],
    'familia': ['papas', 'mama', 'papa', 'familia', 'hijo', 'hija', 'tutor'],
}


def depurar(texto: str) -> str:
    """Quita correos, URLs y números (se usa antes de mostrar o analizar textos libres)."""
    texto = re.sub(r'[\w.+-]+@[\w-]+(\.[\w-]+)+', '[correo]', texto)
    texto = re.sub(r'https?://\S+|www\.\S+', '[url]', texto, flags=re.I)
    texto = re.sub(r'\+?\d[\d\s().-]{6,}\d', '[numero]', texto)
    texto = re.sub(r'\d+', '#', texto)
    return texto.strip()[:1000]


def ia_habilitada() -> bool:
    """Se conserva el nombre por compatibilidad: la clasificación propia siempre está disponible."""
    return True


def _clasificar(texto: str) -> list[str]:
    from .texto import normalizar
    t = f' {normalizar(texto)} '
    puntos = {tema: sum(t.count(' ' + normalizar(p)) for p in palabras) for tema, palabras in PALABRAS_TEMA.items()}
    temas = [tema for tema, n in sorted(puntos.items(), key=lambda x: -x[1]) if n][:3]
    return temas or ['otro']


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
        except Exception as e:  # noqa: BLE001 - un texto raro no detiene a los demás
            log.warning('No se pudo clasificar el item %s: %s', item.pk, type(e).__name__)
    return hechos
