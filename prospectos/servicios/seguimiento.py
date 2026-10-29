"""Embudo, bitácora de contactos, tareas automáticas y correo de bienvenida."""

import logging
import queue
import threading
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import close_old_connections, transaction
from django.db.models import Exists, OuterRef, Q
from django.template.loader import render_to_string
from django.utils import timezone

from ..models import ACTIVOS, CONTACTOS, Estatus, Prospecto, Seguimiento, TipoSeguimiento
from . import auditoria

log = logging.getLogger('prospectos.seguimiento')


def registrar(p: Prospecto, tipo: str, notas: str = '', usuario=None, fecha=None) -> Seguimiento:
    fecha = fecha or timezone.now()
    with transaction.atomic():
        s = Seguimiento.objects.create(prospecto=p, usuario=usuario, tipo=tipo, fecha=fecha, notas=notas or '')
        if tipo in CONTACTOS:
            p.ultimo_contacto_en = fecha
            p.ultima_actividad_en = fecha
            p.save()
            # Primer contacto real: avanza el embudo automáticamente.
            if p.estatus == Estatus.REGISTRADO:
                cambiar_estatus(p, Estatus.CONTACTADO, usuario, 'Avance automático por primer contacto.')
            # Contactar cierra las tareas automáticas pendientes.
            Seguimiento.objects.filter(prospecto=p, tipo=TipoSeguimiento.TAREA, automatica=True,
                                       completada_en__isnull=True).update(completada_en=fecha)
        return s


def cambiar_estatus(p: Prospecto, nuevo: str, usuario=None, notas: str = '') -> None:
    anterior = p.estatus
    if anterior == nuevo:
        return
    with transaction.atomic():
        p.estatus = nuevo
        p.ultima_actividad_en = timezone.now()
        p.save()
        Seguimiento.objects.create(prospecto=p, usuario=usuario, tipo=TipoSeguimiento.CAMBIO_ESTATUS,
                                   estatus_anterior=anterior, estatus_nuevo=nuevo, notas=notas or '')
        auditoria.registrar('cambiar_estatus', p, {'de': anterior, 'a': nuevo}, usuario)


def generar_tareas_sin_contacto() -> int:
    """Tarea automática para cada prospecto activo con consentimiento, X días sin contacto y sin tarea abierta."""
    dias = settings.PROSPECTOS['DIAS_SIN_CONTACTO']
    limite = timezone.now() - timedelta(days=dias)
    abierta = Seguimiento.objects.filter(prospecto=OuterRef('pk'), tipo=TipoSeguimiento.TAREA, completada_en__isnull=True)
    qs = (Prospecto.objects.utilizables().filter(estatus__in=ACTIVOS, no_contactar=False)
          .filter(Q(ultimo_contacto_en__isnull=True, creado_en__lte=limite) | Q(ultimo_contacto_en__lte=limite))
          .exclude(Exists(abierta)).only('id', 'asesor_id'))
    ahora = timezone.now()
    tareas = [Seguimiento(prospecto_id=p.pk, usuario_id=p.asesor_id, tipo=TipoSeguimiento.TAREA, fecha=ahora,
                          vence_en=ahora + timedelta(days=1), automatica=True,
                          notas=f'Sin contacto en {dias} días o más. Llamar o escribir.') for p in qs.iterator()]
    Seguimiento.objects.bulk_create(tareas, batch_size=500)
    return len(tareas)


def completar_tarea(tarea: Seguimiento, usuario=None) -> None:
    tarea.completada_en = timezone.now()
    tarea.save(update_fields=['completada_en'])
    auditoria.registrar('completar_tarea', tarea.prospecto, {'seguimiento_id': tarea.pk}, usuario)


# --------------------------------------------------------------------------- bienvenida
def _enviar(pid: int) -> None:
    try:
        p = Prospecto.objects.select_related('carrera', 'carrera_tutor').get(pk=pid)
        if p.bienvenida_enviada_en or not p.consentimiento or p.anonimizado_en:
            return
        destino = p.correo or p.tutor_correo
        if not destino:
            return
        carrera = p.carrera or p.carrera_tutor
        cuerpo = render_to_string('prospectos/correo_bienvenida.txt', {
            'nombre': (p.nombre_aspirante or '').split(' ')[0] or p.nombre_aspirante,
            'carrera': carrera.nombre if carrera else None,
            'institucion': settings.CONFIG.get('NOMBRE_INSTITUCION', 'la Universidad'),
        })
        EmailMessage('¡Gracias por tu interés!', cuerpo, to=[destino]).send()
        Prospecto.objects.filter(pk=pid).update(bienvenida_enviada_en=timezone.now())
        Seguimiento.objects.create(prospecto=p, tipo=TipoSeguimiento.SISTEMA, notas='Correo de bienvenida enviado.')
    except Exception as e:  # noqa: BLE001 - el correo nunca debe tumbar la importación
        log.warning('No se pudo enviar la bienvenida al prospecto %s: %s', pid, type(e).__name__)


_cola: queue.Queue[int] = queue.Queue()
_trabajador: threading.Thread | None = None
_candado = threading.Lock()


def _trabajar() -> None:
    while True:
        pid = _cola.get()
        close_old_connections()  # hilo propio: conexiones propias
        try:
            _enviar(pid)
        finally:
            close_old_connections()
            _cola.task_done()


def enviar_bienvenida(pid: int) -> None:
    """Un solo hilo en segundo plano envía los correos (no frena la importación si el SMTP tarda)."""
    global _trabajador
    if getattr(settings, 'CORREO_SINCRONO', False):
        _enviar(pid)
        return
    with _candado:
        if _trabajador is None or not _trabajador.is_alive():
            _trabajador = threading.Thread(target=_trabajar, daemon=True, name='correo-bienvenida')
            _trabajador.start()
    _cola.put(pid)


def reintentar_bienvenidas() -> int:
    """Encola bienvenidas que no salieron (programa cerrado o SMTP caído) de los últimos 3 días."""
    desde = timezone.now() - timedelta(days=3)
    n = 0
    for p in (Prospecto.objects.utilizables().filter(bienvenida_enviada_en__isnull=True, consentimiento_en__gte=desde)
              .only('id', 'correo', 'tutor_correo')):
        if p.correo or p.tutor_correo:
            enviar_bienvenida(p.pk)
            n += 1
    return n


def esperar_correos(timeout: float = 60) -> None:
    """Para comandos de consola: espera a que salgan los correos pendientes antes de terminar."""
    import time
    fin = time.monotonic() + timeout
    while _cola.unfinished_tasks and time.monotonic() < fin:
        time.sleep(0.2)
