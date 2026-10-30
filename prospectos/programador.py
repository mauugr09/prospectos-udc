"""
Tareas periódicas dentro del mismo programa (sustituye al cron/scheduler):
  - importar respuestas: cada IMPORTADOR_CADA_MINUTOS (1 por defecto)
  - clasificación IA (si está activa): cada 10 min
  - tareas de seguimiento: cada hora
  - respaldo + rotación: diario a RESPALDO_HORA (o al arrancar si el último tiene > 24 h)
  - verificación del respaldo: semanal
  - retención / purga de cuarentena: diario
  - avisos de la campanita: cada 5 min (deduplicados; ver servicios/avisos.py)

Limitación honesta: solo corre mientras el programa está abierto. Si la PC está apagada,
lo pendiente se hace al volver a abrirlo (la importación es incremental y no pierde nada).

Un solo programador por base de datos: si dos procesos o dos equipos usan la misma base (servidor y una PC,
o dos réplicas), solo uno tiene el «turno» (fila programador.turno en Configuración, que se renueva cada
15 s y vence a los 2 min). Así no se importan las respuestas dos veces ni se hacen dos respaldos.
"""

import logging
import os
import socket
import threading
import time
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone

log = logging.getLogger('prospectos.programador')

TURNO = 'programador.turno'
VIGENCIA_TURNO = 120  # segundos sin renovarse para que otro proceso tome el turno


def tomar_turno(ident: str, ahora: float | None = None) -> bool:
    """True si este proceso tiene (o acaba de tomar) el turno de correr las tareas."""
    from .models import Configuracion
    ahora = time.time() if ahora is None else ahora
    try:
        with transaction.atomic():
            fila, _ = Configuracion.objects.select_for_update().get_or_create(clave=TURNO, defaults={'valor': {}})
            actual = fila.valor or {}
            if actual.get('id') != ident and float(actual.get('hasta') or 0) > ahora:
                return False
            if actual.get('id') != ident:
                log.info('Este proceso toma el turno de las tareas automáticas (antes: %s).', actual.get('equipo') or 'nadie')
            fila.valor = {'id': ident, 'equipo': f'{socket.gethostname()} pid {os.getpid()}', 'hasta': ahora + VIGENCIA_TURNO}
            fila.save(update_fields=['valor', 'actualizado_en'])
            return True
    except IntegrityError:  # otro proceso creó la fila en el mismo instante: que gane él esta vuelta
        return False


class Programador(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name='programador')
        self.detener = threading.Event()
        self.ultimo: dict[str, float] = {}
        self.id_turno = uuid.uuid4().hex
        self._esperando = False

    def _toca(self, nombre: str, cada_segundos: float) -> bool:
        ahora = time.monotonic()
        if ahora - self.ultimo.get(nombre, -1e12) >= cada_segundos:
            self.ultimo[nombre] = ahora
            return True
        return False

    def _correr(self, nombre: str, funcion):
        close_old_connections()
        try:
            resultado = funcion()
            if resultado:
                log.info('%s: %s', nombre, resultado)
        except Exception:  # noqa: BLE001 - una tarea que falla no detiene a las demás
            log.exception('Falló la tarea %s', nombre)
        finally:
            close_old_connections()

    def run(self):
        from .models import Configuracion, Respaldo
        from .servicios import avisos, importacion, respaldos, seguimiento, seguridad

        cada_import = max(1, int(settings.CONFIG.get('IMPORTADOR_CADA_MINUTOS', 1))) * 60
        hh, mm = (int(x) for x in settings.PROSPECTOS['RESPALDO_HORA'].split(':'))

        def respaldo_pendiente() -> bool:
            ultimo = Respaldo.objects.filter(estado='ok').order_by('-creado_en').first()
            ahora = timezone.localtime()
            programado = ahora.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if ahora < programado:
                programado -= timedelta(days=1)
            return ultimo is None or ultimo.creado_en < programado

        def respaldar():
            if not respaldo_pendiente():
                return None
            r = respaldos.crear()
            texto = f'{r.archivo} {r.estado} · rotados {respaldos.rotar()}'
            if r.estado == 'ok' and respaldos.carpeta_copia():
                try:
                    texto += f' · copia externa {respaldos.copiar_externo(r.archivo)}'
                except respaldos.ErrorRespaldo as e:
                    texto += f' · copia externa FALLÓ: {e}'
            return texto

        def copiar():  # la memoria USB no estaba conectada: se reintenta sola
            if respaldos.copia_pendiente():
                try:
                    return f'copia externa {respaldos.copiar_externo()}'
                except respaldos.ErrorRespaldo:
                    return None
            return None

        def verificar():
            ultimo = Respaldo.objects.filter(estado='ok').order_by('-creado_en').first()
            if not ultimo or (ultimo.verificado_en and ultimo.verificado_en > timezone.now() - timedelta(days=7)):
                return None
            hace = Respaldo.objects.filter(verificado_en__gt=timezone.now() - timedelta(days=7)).exists()
            return None if hace else f'verificado {respaldos.verificar(ultimo.archivo)}'

        def retencion():
            hoy = timezone.localdate().isoformat()
            if Configuracion.obtener('programador.retencion') == hoy:
                return None
            r = f'purgados {seguridad.purgar_sin_consentimiento()} · anonimizados {seguridad.anonimizar_inactivos()}'
            Configuracion.guardar('programador.retencion', hoy)
            return r

        def mantenimiento():
            """Una vez al día (SQLite): estadísticas para las consultas, vaciar el diario WAL y revisión rápida de integridad."""
            from django.db import connection
            hoy = timezone.localdate().isoformat()
            if connection.vendor != 'sqlite' or Configuracion.obtener('programador.mantenimiento') == hoy:
                return None
            with connection.cursor() as c:
                c.execute('PRAGMA optimize')
                c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                c.execute('PRAGMA quick_check')
                estado = c.fetchone()[0]
            Configuracion.guardar('programador.mantenimiento', hoy)
            if estado != 'ok':
                from .models import TipoAviso
                for u in get_user_model().objects.filter(is_superuser=True, is_active=True):
                    avisos.avisar(u, TipoAviso.SISTEMA, 'bd-integridad', 'La base de datos tiene un error de integridad',
                                  'Restaura el último respaldo verificado (Protección de datos) y avisa a soporte.', '')
            return f'base: {estado}'

        def importar():
            regs = importacion.importar_todos()
            nuevas = sum(r.nuevas + r.actualizadas for r in regs)
            return f'{nuevas} respuestas nuevas/editadas' if nuevas else None

        time.sleep(5)  # deja arrancar el servidor web primero
        while not self.detener.is_set():
            close_old_connections()
            try:
                turno = tomar_turno(self.id_turno)
            except Exception:  # noqa: BLE001 - base caída un momento: se reintenta en la siguiente vuelta
                log.exception('No se pudo revisar el turno del programador')
                turno = False
            if not turno:
                if not self._esperando:
                    log.info('Otro proceso ya corre las tareas automáticas con esta base de datos; este espera.')
                    self._esperando = True
                self.detener.wait(15)
                continue
            self._esperando = False
            if self._toca('importar', cada_import):
                self._correr('importar', importar)
            if self._toca('ia', 600):
                self._correr('ia', seguridad.clasificar_pendientes)
            if self._toca('bienvenidas', 900):
                self._correr('bienvenidas', seguimiento.reintentar_bienvenidas)
            if self._toca('tareas', 3600):
                self._correr('tareas', seguimiento.generar_tareas_sin_contacto)
            if self._toca('respaldo', 300):
                self._correr('respaldo', respaldar)
            if self._toca('copia', 1800):
                self._correr('copia', copiar)
            if self._toca('verificar', 3600):
                self._correr('verificar', verificar)
            if self._toca('retencion', 3600):
                self._correr('retencion', retencion)
            if self._toca('mantenimiento', 3600):
                self._correr('mantenimiento', mantenimiento)
            # Al final: así ve el respaldo recién hecho y no avisa en falso al abrir el programa.
            if self._toca('avisos', 300):
                self._correr('avisos', avisos.revisar)
            self.detener.wait(15)


def iniciar() -> Programador:
    p = Programador()
    p.start()
    return p

