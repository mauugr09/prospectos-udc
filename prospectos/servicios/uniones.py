"""
Separar dos fichas que se unieron por error (familia equivocada o duplicado que no era).

Desde esta versión, cada unión guarda en la bitácora qué respuestas, seguimientos, etiquetas y campos
se movieron, y separar los regresa exactamente. Las uniones hechas antes no tienen ese registro: si fue
familia + alumno se separa por tipo de cuestionario (las respuestas de la familia regresan a su ficha);
si fueron dos fichas del mismo tipo no hay forma segura de saber qué era de quién y se rechaza.

Lo que NO se puede deshacer: un correo de bienvenida que ya salió, o llamadas hechas con datos mezclados.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ..models import (Auditoria, Cuestionario, PosibleCoincidencia, Prospecto, Respuesta, Seguimiento, TipoSeguimiento)
from . import auditoria
from .familias import _otro_sexo

# Campos que recalcular() rellena desde las respuestas «si están vacíos»: se limpian antes de recalcular
# para que la ficha que se queda no conserve datos de la otra.
DERIVADOS = ['correo', 'telefono', 'tutor_nombre', 'tutor_correo', 'tutor_telefono', 'carrera_tutor', 'modalidad_tutor',
             'curp', 'fecha_nacimiento', 'edad', 'consentimiento_en', 'canal_informacion', 'plantel', 'modalidad']
VACIO = {'tutor_nombre': '', 'modalidad_tutor': '', 'canal_informacion': '', 'plantel': '', 'modalidad': ''}


class NoSeparable(Exception):
    pass


def _registro(absorbido: Prospecto):
    return (Auditoria.objects.filter(accion='fusionar', objeto_id=str(absorbido.fusionado_en_id),
                                     detalle__absorbido_id=absorbido.pk).order_by('-creado_en').first())


def recientes(dias: int = 90, limite: int = 200) -> list[dict]:
    """Uniones de los últimos días, marcando las sospechosas."""
    desde = timezone.now() - timedelta(days=dias)
    filas = []
    for a in (Auditoria.objects.filter(accion='fusionar', creado_en__gte=desde).select_related('usuario')[:limite]):
        sale_id = (a.detalle or {}).get('absorbido_id')
        sale = Prospecto.objects.filter(pk=sale_id).select_related('fusionado_en').first() if sale_id else None
        if not sale or not sale.fusionado_en_id or str(sale.fusionado_en_id) != a.objeto_id:
            continue  # ya se separó, o se volvió a unir con otra
        queda = sale.fusionado_en
        alertas = []
        if _otro_sexo(queda.nombre_aspirante, sale.nombre_aspirante):
            alertas.append('nombres de otro sexo')
        if queda.anonimizado_en:
            continue
        filas.append({'registro': a, 'queda': queda, 'sale': sale, 'automatica': a.usuario_id is None,
                      'exacta': 'respuestas' in (a.detalle or {}), 'alertas': alertas})
    return filas


def separar(sale: Prospecto, usuario=None) -> tuple[Prospecto, Prospecto]:
    from .inteligencia import recalcular
    if not sale.fusionado_en_id:
        raise NoSeparable('Esta ficha no está unida con otra.')
    queda = sale.fusionado_en
    if queda.fusionado_en_id:
        raise NoSeparable('La ficha con la que se unió también se unió después con otra: sepárala primero.')
    if queda.anonimizado_en or sale.anonimizado_en:
        raise NoSeparable('Una de las dos fichas ya se anonimizó: no queda nada que separar.')
    reg = _registro(sale)
    detalle = (reg.detalle or {}) if reg else {}
    with transaction.atomic():
        if 'respuestas' in detalle:
            respuestas = Respuesta.objects.filter(pk__in=detalle['respuestas'], prospecto=queda)
            seguimientos = Seguimiento.objects.filter(pk__in=detalle['seguimientos'], prospecto=queda)
            campos = detalle.get('campos', [])
        else:
            tipos = set(queda.respuestas.values_list('cuestionario', flat=True))
            if tipos != {Cuestionario.ALUMNO, Cuestionario.TUTOR}:
                raise NoSeparable('Esta unión se hizo con una versión anterior y las dos fichas eran del mismo tipo: '
                                  'no se puede saber qué respuesta era de cuál. Pide ayuda a quien administra el sistema.')
            # Unión vieja de familia + alumno: lo de la familia regresa a la ficha que salió.
            de_familia = sale.tiene_tutor and not sale.tiene_alumno
            respuestas = queda.respuestas.filter(cuestionario=Cuestionario.TUTOR if de_familia else Cuestionario.ALUMNO)
            seguimientos = Seguimiento.objects.none()
            campos = []
        if not respuestas.exists():
            raise NoSeparable('No se encontraron las respuestas de la otra ficha.')
        respuestas.update(prospecto=sale)
        seguimientos.update(prospecto=sale)
        if detalle.get('etiquetas_nuevas'):
            queda.etiquetas.remove(*detalle['etiquetas_nuevas'])
        for p in (queda, sale):
            for campo in DERIVADOS:
                setattr(p, campo, VACIO.get(campo))
        for campo in campos:
            if campo != 'token_familia':
                setattr(queda, campo, None)
        if 'token_familia' in campos:
            sale.token_familia, queda.token_familia = queda.token_familia, None
        if detalle.get('estatus_previo'):
            queda.estatus = detalle['estatus_previo']
        sale.fusionado_en = None
        queda.save()
        sale.save()
        # Que no se vuelvan a unir solas.
        par = PosibleCoincidencia.objects.filter(prospecto=queda, candidato=sale).first() or \
            PosibleCoincidencia.objects.filter(prospecto=sale, candidato=queda).first()
        if par:
            par.estado, par.revisado_por, par.revisado_en = 'rechazada', usuario, timezone.now()
            par.save()
        else:
            PosibleCoincidencia.objects.create(prospecto=queda, candidato=sale, similitud=0, motivo='Separadas a mano',
                                               estado='rechazada', revisado_por=usuario, revisado_en=timezone.now())
        for p, otro in ((queda, sale), (sale, queda)):
            Seguimiento.objects.create(prospecto=p, usuario=usuario, tipo=TipoSeguimiento.SISTEMA,
                                       notas=f'Separado del prospecto #{otro.pk} (se habían unido por error).')
        auditoria.registrar('separar', queda, {'separado_id': sale.pk, 'exacta': 'respuestas' in detalle}, usuario)
        return recalcular(Prospecto.objects.get(pk=queda.pk)), recalcular(Prospecto.objects.get(pk=sale.pk))
