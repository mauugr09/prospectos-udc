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
"""

import logging
import threading
import time
from datetime import timedelta

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

log = logging.getLogger('prospectos.programador')


class Programador(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name='programador')
        self.detener = threading.Event()
        self.ultimo: dict[str, float] = {}

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

        def importar():
            regs = importacion.importar_todos()
            nuevas = sum(r.nuevas + r.actualizadas for r in regs)
            return f'{nuevas} respuestas nuevas/editadas' if nuevas else None

        time.sleep(5)  # deja arrancar el servidor web primero
        while not self.detener.is_set():
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
            # Al final: así ve el respaldo recién hecho y no avisa en falso al abrir el programa.
            if self._toca('avisos', 300):
                self._correr('avisos', avisos.revisar)
            self.detener.wait(15)


def iniciar() -> Programador:
    p = Programador()
    p.start()
    return p

