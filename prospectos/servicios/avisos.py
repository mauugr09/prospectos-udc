"""
Avisos dentro del sistema (la campanita).

Para que no se vuelvan ruido:
  - Las llamadas vencidas llegan como UN aviso diario por persona, con la cifra, no uno por aspirante.
  - Los aspirantes nuevos se agrupan: mientras el aviso no se lea, sube la cifra en vez de crear otro.
  - Un mismo aviso (misma clave) no se repite aunque la tarea corra cada hora.
  - Cada quien apaga los tipos que no le sirven; los problemas del sistema no se pueden apagar.
  - No se guardan nombres ni datos de contacto, solo cifras y enlaces (ver Notificacion).
"""

import logging
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from ..models import Configuracion, Evento, Formulario, Notificacion, Perfil, Prospecto, Respaldo, TipoAviso
from .calendario import _tareas_abiertas

log = logging.getLogger('prospectos.avisos')

OBLIGATORIOS = {TipoAviso.SISTEMA}
DIAS_GUARDADOS = 60
DESCRIPCIONES = {
    TipoAviso.ASIGNADO: 'Cuando te asignan un aspirante o se registra uno en tus visitas.',
    TipoAviso.VENCIDAS: 'Un resumen al día de las llamadas que ya se pasaron de fecha.',
    TipoAviso.EVENTO: 'Un día antes de cada visita, y si falta pedir permiso a la prepa.',
    TipoAviso.SISTEMA: 'Respaldos o importaciones que fallaron. Solo administradores; no se puede apagar.',
}


def apagados(usuario) -> set[str]:
    perfil = Perfil.objects.filter(usuario=usuario).only('avisos_apagados').first()
    return set(perfil.avisos_apagados or []) - OBLIGATORIOS if perfil else set()


def guardar_preferencias(usuario, encendidos: set[str]) -> None:
    validos = {t for t in TipoAviso.values if t not in OBLIGATORIOS}
    Perfil.objects.update_or_create(usuario=usuario, defaults={'avisos_apagados': sorted(validos - set(encendidos))})


def avisar(usuario, tipo: str, clave: str, titulo: str, detalle: str = '', url: str = '',
           cantidad: int = 1, acumular: bool = False) -> Notificacion | None:
    """
    Crea el aviso si no existe ya uno con la misma clave.
    acumular=True: si hay uno sin leer con esa clave, le suma la cantidad (y lo sube arriba);
    si ya se leyó, crea uno nuevo. acumular=False: una clave avisa una sola vez; si sigue sin leer
    se actualiza la cifra (p. ej. las vencidas del día cambian a lo largo de la mañana).
    """
    if usuario is None or not usuario.is_active or tipo in apagados(usuario):
        return None
    ahora = timezone.now()
    previos = Notificacion.objects.filter(usuario=usuario, clave=clave)
    sin_leer = previos.filter(leida_en__isnull=True).first()
    if sin_leer:
        nueva = sin_leer.cantidad + cantidad if acumular else cantidad
        if nueva != sin_leer.cantidad or sin_leer.titulo != titulo or acumular:
            sin_leer.cantidad, sin_leer.titulo, sin_leer.detalle, sin_leer.url = nueva, titulo, detalle, url
            sin_leer.actualizada_en = ahora
            sin_leer.save(update_fields=['cantidad', 'titulo', 'detalle', 'url', 'actualizada_en'])
        sin_leer.es_nuevo = False
        return sin_leer
    if not acumular and previos.exists():
        return None
    n = Notificacion.objects.create(usuario=usuario, tipo=tipo, clave=clave, titulo=titulo, detalle=detalle,
                                    url=url, cantidad=cantidad, creada_en=ahora, actualizada_en=ahora)
    n.es_nuevo = True
    return n


def _plural(n: int, uno: str, varios: str) -> str:
    return uno if n == 1 else varios.replace('{n}', str(n))


def _admins():
    return get_user_model().objects.filter(is_superuser=True, is_active=True)


# --------------------------------------------------------------------------- aspirantes nuevos

def asignado(asesor, prospecto, por=None) -> None:
    """Alguien le asignó un aspirante a otra persona (desde la ficha o la lista)."""
    if asesor is None or (por is not None and asesor.pk == por.pk):
        return
    hoy = timezone.localdate().isoformat()
    lista = reverse('admin:prospectos_prospecto_changelist') + f'?asesor__id__exact={asesor.pk}'
    n = avisar(asesor, TipoAviso.ASIGNADO, f'asignado:{hoy}', 'Te asignaron un aspirante', url=lista, acumular=True)
    if n:
        if n.cantidad == 1:
            n.url = reverse('admin:prospectos_prospecto_change', args=[prospecto.pk])
        else:
            n.titulo = f'Te asignaron {n.cantidad} aspirantes'
        n.detalle = f'Asignado por {por.get_full_name() or por.get_username()}' if por and n.cantidad == 1 else 'Revisa tu lista y haz el primer contacto.'
        n.save(update_fields=['url', 'titulo', 'detalle'])


def registrados_en_mis_visitas() -> int:
    """
    Aspirantes que entraron desde la última revisión con el código de un promotor (QR o visita).
    Se sigue por ID y no por fecha: el prospecto lleva la fecha en que contestó el Form, que puede
    ser de días antes si la PC estuvo apagada.
    """
    tope = Prospecto.objects.order_by('-pk').values_list('pk', flat=True).first() or 0
    desde = Configuracion.obtener('avisos.ultimo_prospecto')
    if desde != tope:
        Configuracion.guardar('avisos.ultimo_prospecto', tope)
    if desde is None:
        return 0  # primera vez: no avisa del histórico
    qs = (Prospecto.objects.filter(pk__gt=desde, pk__lte=tope, promotor__isnull=False,
                                   fusionado_en__isnull=True, anonimizado_en__isnull=True)
          .values('promotor').annotate(n=Count('id')).order_by())
    hoy = timezone.localdate().isoformat()
    usuarios = get_user_model().objects.in_bulk([f['promotor'] for f in qs])
    total = 0
    for fila in qs:
        u = usuarios.get(fila['promotor'])
        url = reverse('admin:prospectos_prospecto_changelist') + f'?promotor__id__exact={u.pk}&o=-1' if u else ''
        n = avisar(u, TipoAviso.ASIGNADO, f'visitas:{hoy}', '', url=url, cantidad=fila['n'], acumular=True)
        if n:
            n.titulo = _plural(n.cantidad, 'Se registró 1 aspirante en tus visitas', 'Se registraron {n} aspirantes en tus visitas')
            n.detalle = 'Los menores aparecen cuando su familia da permiso.'
            n.save(update_fields=['titulo', 'detalle'])
            total += fila['n']
    return total


# --------------------------------------------------------------------------- llamadas vencidas

def vencidas_del_dia() -> int:
    hoy = timezone.localdate()
    filas = (_tareas_abiertas().filter(vence_en__lt=timezone.now())
             .values('usuario').annotate(n=Count('id')).order_by())
    cola = reverse('prospectos:cola')
    usuarios = get_user_model().objects.in_bulk([f['usuario'] for f in filas if f['usuario']])
    enviados = 0
    sin_asesor = 0
    for fila in filas:
        if not fila['usuario']:
            sin_asesor += fila['n']
            continue
        n = avisar(usuarios.get(fila['usuario']), TipoAviso.VENCIDAS, f'vencidas:{hoy}',
                   _plural(fila['n'], 'Tienes 1 llamada vencida', 'Tienes {n} llamadas vencidas'),
                   'Ya pasó la fecha para contactarlos.', cola, fila['n'])
        enviados += bool(n and n.es_nuevo)
    if sin_asesor:
        for u in _admins():
            avisar(u, TipoAviso.VENCIDAS, f'vencidas-sin-asesor:{hoy}',
                   _plural(sin_asesor, '1 llamada vencida sin asesor', '{n} llamadas vencidas sin asesor'),
                   'Nadie tiene asignados a estos aspirantes. Asígnalos desde la lista.', cola, sin_asesor)
    return enviados


# --------------------------------------------------------------------------- visitas

def visitas_proximas() -> int:
    hoy = timezone.localdate()
    manana = hoy + timedelta(days=1)
    n = 0
    activos = Evento.objects.exclude(estado__in=['cancelado', 'realizado']).select_related('preparatoria', 'promotor')
    for ev in activos.filter(fecha=manana):
        hora = f' a las {ev.hora_inicio:%H:%M}' if ev.hora_inicio else ''
        detalle = f'{ev.get_actividad_display()}{hora}.'
        url = reverse('admin:prospectos_evento_change', args=[ev.pk])
        if ev.beca_carta and ev.beca_hojas:
            detalle += f' Lleva {ev.beca_hojas} cartas de beca impresas.'
            url = reverse('prospectos:evento_becas', args=[ev.pk])
        if ev.estado != 'confirmado':
            detalle += ' La prepa aún no confirma.'
        for u in [ev.promotor] if ev.promotor else _admins():
            a = avisar(u, TipoAviso.EVENTO, f'evento:{ev.pk}:{ev.fecha}', f'Mañana: visita a {ev.preparatoria.nombre}', detalle, url)
            n += bool(a and a.es_nuevo)
    for ev in activos.filter(estado='por_solicitar', fecha__gt=hoy, fecha__lte=hoy + timedelta(days=7)):
        dias = (ev.fecha - hoy).days
        for u in [ev.promotor] if ev.promotor else _admins():
            a = avisar(u, TipoAviso.EVENTO, f'evento-solicitar:{ev.pk}:{ev.fecha}',
                       f'Falta pedir permiso a {ev.preparatoria.nombre}',
                       _plural(dias, 'La visita es mañana', 'La visita es en {n} días') + ' y la solicitud no se ha enviado.',
                       reverse('prospectos:evento_solicitud', args=[ev.pk]))
            n += bool(a and a.es_nuevo)
    return n


# --------------------------------------------------------------------------- sistema

def problemas_del_sistema() -> int:
    hoy = timezone.localdate().isoformat()
    problemas = []
    respaldos = reverse('admin:prospectos_respaldo_changelist')
    ultimo = Respaldo.objects.order_by('-creado_en').first()
    if ultimo and ultimo.estado != 'ok':
        problemas.append((f'respaldo:{ultimo.pk}', 'Falló el respaldo automático',
                          'Los datos de hoy no están respaldados. Revisa el espacio en disco.', respaldos))
    ok = Respaldo.objects.filter(estado='ok').order_by('-creado_en').first()
    if ok is None or ok.creado_en < timezone.now() - timedelta(hours=48):
        problemas.append((f'sin-respaldo:{hoy}', 'No hay un respaldo de los últimos 2 días',
                          'Si la computadora falla, se pierde lo de esos días.', respaldos))
    from . import respaldos as _resp
    proteccion = reverse('prospectos:proteccion')
    if not _resp.carpeta_copia():
        semana = timezone.localdate().isocalendar()
        problemas.append((f'sin-copia:{semana[0]}-{semana[1]}', 'Los respaldos solo están en esta computadora',
                          'Si el disco falla o se pierde la PC, se pierde todo. Configura una copia en una memoria o carpeta de red.',
                          proteccion))
    elif _resp.copia_pendiente():
        est = _resp.estado_copia()
        fecha = est.get('fecha')
        if not fecha or datetime.fromisoformat(fecha) < timezone.now() - timedelta(hours=48):
            problemas.append((f'copia:{hoy}', 'La copia fuera de esta PC no se ha hecho',
                              (est.get('mensaje') or 'Conecta la memoria o revisa la carpeta de red.')[:200], proteccion))
    for f in Formulario.objects.filter(activo=True):
        ultima = f.importaciones.order_by('-iniciada_en').first()
        if ultima and ultima.estado == 'error':
            problemas.append((f'importacion:{f.pk}:{hoy}', f'No se pudieron traer las respuestas de «{f}»',
                              (ultima.mensaje or 'Error sin detalle.')[:200],
                              reverse('admin:prospectos_formulario_change', args=[f.pk])))
    # Lo que ya se arregló solo (el respaldo volvió a salir bien, el Form volvió a leerse) deja de contar como pendiente.
    Notificacion.objects.filter(tipo=TipoAviso.SISTEMA, leida_en__isnull=True).exclude(
        clave__in=[p[0] for p in problemas]).update(leida_en=timezone.now())
    n = 0
    for u in _admins():
        for clave, titulo, detalle, url in problemas:
            a = avisar(u, TipoAviso.SISTEMA, clave, titulo, detalle, url)
            n += bool(a and a.es_nuevo)
    return n


def limpiar() -> int:
    return Notificacion.objects.filter(actualizada_en__lt=timezone.now() - timedelta(days=DIAS_GUARDADOS)).delete()[0]


def revisar() -> str | None:
    """Lo que corre el programador cada pocos minutos."""
    partes = {'visitas': registrados_en_mis_visitas(), 'vencidas': vencidas_del_dia(),
              'eventos': visitas_proximas(), 'sistema': problemas_del_sistema(), 'borrados': limpiar()}
    hechos = {k: v for k, v in partes.items() if v}
    return ' · '.join(f'{k} {v}' for k, v in hechos.items()) or None


def no_leidas(usuario) -> int:
    return Notificacion.objects.filter(usuario=usuario, leida_en__isnull=True).count()
