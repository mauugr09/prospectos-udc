"""
Respaldos comprimidos (gzip) con rotación, verificación por restauración y restauración real.

- SQLite: copia consistente en caliente con la API de backup de sqlite3; se verifica con
  integrity_check + conteos.
- MariaDB: mariadb-dump --single-transaction (sin bloquear); se verifica cargándolo en una base
  temporal «<nombre>_verificacion» y contando filas. Necesita los programas mariadb-dump y
  mariadb (config.json → BASE_DATOS.BIN, o en el PATH) y permiso CREATE/DROP sobre esa base temporal.

Un respaldo SIN datos/config.json (CLAVE_CIFRADO) no permite leer correos ni teléfonos.
"""

import gzip
import hashlib
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.utils import timezone

from ..models import Respaldo

TABLAS = ['prospectos_prospecto', 'prospectos_respuesta', 'prospectos_respuestaitem', 'prospectos_seguimiento', 'auth_user']


class ErrorRespaldo(Exception):
    pass


def directorio() -> Path:
    d = Path(settings.PROSPECTOS['RESPALDOS_DIR'])
    d.mkdir(parents=True, exist_ok=True)
    return d


def archivos() -> list[Path]:
    return sorted(directorio().glob('prospectos-*.gz'))


def es_mariadb() -> bool:
    return connection.vendor == 'mysql'


# --------------------------------------------------------------------------- MariaDB
def _bin(nombre: str) -> str:
    carpeta = (settings.BD.get('BIN') or '').strip()
    exe = nombre + ('.exe' if os.name == 'nt' else '')
    if carpeta:
        return str(Path(carpeta) / exe)
    encontrado = shutil.which(exe) or shutil.which(nombre.replace('mariadb', 'mysql'))
    if not encontrado:
        raise ErrorRespaldo(f'No se encontró {exe}. Indica la carpeta bin de MariaDB en config.json → BASE_DATOS.BIN.')
    return encontrado


def _conexion_args() -> tuple[list[str], dict]:
    db = settings.DATABASES['default']
    args = ['-h', db['HOST'] or '127.0.0.1', '-P', str(db['PORT'] or 3306), '-u', db['USER'], '--default-character-set=utf8mb4']
    entorno = {**os.environ, 'MYSQL_PWD': db['PASSWORD'] or ''}  # la clave no aparece en la lista de procesos
    return args, entorno


def _correr(cmd: list[str], entorno: dict, entrada=None, tiempo: int = 1800) -> None:
    r = subprocess.run(cmd, env=entorno, stdin=entrada, capture_output=True, timeout=tiempo,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if r.returncode != 0:
        raise ErrorRespaldo(r.stderr.decode('utf-8', 'replace')[:1500] or f'{Path(cmd[0]).name} terminó con código {r.returncode}')


def _crear_mariadb(destino: Path) -> None:
    args, entorno = _conexion_args()
    sql = destino.with_suffix('')  # .sql
    try:
        _correr([_bin('mariadb-dump'), *args, '--single-transaction', '--quick', '--routines', '--triggers', '--hex-blob',
                 f'--result-file={sql}', settings.DATABASES['default']['NAME']], entorno)
        if not sql.exists() or sql.stat().st_size < 100:
            raise ErrorRespaldo('El respaldo quedó vacío.')
        with open(sql, 'rb') as fin, gzip.open(destino, 'wb', compresslevel=9) as fout:
            shutil.copyfileobj(fin, fout, 1 << 20)
    finally:
        sql.unlink(missing_ok=True)


def _cargar_mariadb(ruta: Path, base: str, recrear: bool) -> None:
    args, entorno = _conexion_args()
    cliente = _bin('mariadb')
    if recrear:
        _correr([cliente, *args, '-e', f'DROP DATABASE IF EXISTS `{base}`; CREATE DATABASE `{base}` '
                 'CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;'], entorno, tiempo=120)
    with tempfile.TemporaryDirectory() as d:
        sql = Path(d) / 'respaldo.sql'
        _descomprimir(ruta, sql)
        with open(sql, 'rb') as entrada:
            _correr([cliente, *args, base], entorno, entrada=entrada)


def _verificar_mariadb(ruta: Path) -> dict[str, int]:
    base = settings.DATABASES['default']['NAME'] + '_verificacion'
    _cargar_mariadb(ruta, base, recrear=True)
    try:
        with connection.cursor() as c:
            conteos = {}
            for t in TABLAS:
                c.execute(f'SELECT COUNT(*) FROM `{base}`.`{t}`')
                conteos[t] = c.fetchone()[0]
    finally:
        args, entorno = _conexion_args()
        _correr([_bin('mariadb'), *args, '-e', f'DROP DATABASE IF EXISTS `{base}`'], entorno, tiempo=120)
    return conteos


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, 'rb') as f:
        for bloque in iter(lambda: f.read(1 << 20), b''):
            h.update(bloque)
    return h.hexdigest()


def crear() -> Respaldo:
    extension = 'sql.gz' if es_mariadb() else 'sqlite3.gz'
    destino = directorio() / f'prospectos-{timezone.localtime():%Y%m%d-%H%M%S}.{extension}'
    tmp = destino.with_suffix('')  # .sqlite3
    try:
        if es_mariadb():
            _crear_mariadb(destino)
        elif connection.in_atomic_block:
            raise ErrorRespaldo('No se puede respaldar dentro de una transacción abierta.')
        else:
            connection.ensure_connection()
            copia = sqlite3.connect(tmp)
            with copia:
                connection.connection.backup(copia)  # copia consistente en caliente
            copia.close()
            with open(tmp, 'rb') as fin, gzip.open(destino, 'wb', compresslevel=9) as fout:
                shutil.copyfileobj(fin, fout, 1 << 20)
    except Exception as e:  # noqa: BLE001
        destino.unlink(missing_ok=True)
        return Respaldo.objects.create(archivo=destino.name, estado='error', mensaje=str(e)[:2000])
    finally:
        tmp.unlink(missing_ok=True)
    return Respaldo.objects.create(archivo=destino.name, bytes=destino.stat().st_size, sha256=_sha256(destino), estado='ok')


def rotar() -> int:
    limite = time.time() - settings.PROSPECTOS['RESPALDO_DIAS_RETENCION'] * 86400
    borrados = 0
    for f in archivos():
        if f.stat().st_mtime < limite:
            f.unlink(missing_ok=True)
            borrados += 1
    return borrados


def resolver(archivo: str | None) -> Path:
    if archivo:
        ruta = Path(archivo)
        if not ruta.is_file():
            ruta = directorio() / Path(archivo).name
    else:
        lista = archivos()
        ruta = lista[-1] if lista else None
    if not ruta or not ruta.is_file():
        raise ErrorRespaldo('No hay respaldos para verificar o restaurar.')
    return ruta


def _descomprimir(origen: Path, destino: Path) -> None:
    with gzip.open(origen, 'rb') as fin, open(destino, 'wb') as fout:
        shutil.copyfileobj(fin, fout, 1 << 20)


def verificar(archivo: str | None = None) -> dict[str, int]:
    """Prueba de restauración: descomprime en un temporal, revisa integridad y cuenta filas."""
    ruta = resolver(archivo)
    if es_mariadb() != ruta.name.endswith('.sql.gz'):
        raise ErrorRespaldo('Ese respaldo es de otro motor de base de datos (SQLite ↔ MariaDB).')
    if es_mariadb():
        conteos = _verificar_mariadb(ruta)
        Respaldo.objects.filter(archivo=ruta.name).update(verificado_en=timezone.now())
        return conteos
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / 'verificar.sqlite3'
        _descomprimir(ruta, tmp)
        con = sqlite3.connect(tmp)
        try:
            if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ErrorRespaldo('El respaldo está dañado (integrity_check).')
            conteos = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in TABLAS}
        except sqlite3.DatabaseError as e:
            raise ErrorRespaldo(f'El respaldo no es una base válida: {e}') from e
        finally:
            con.close()
    Respaldo.objects.filter(archivo=ruta.name).update(verificado_en=timezone.now())
    return conteos


def restaurar(archivo: str) -> None:
    """Reemplaza la base ACTUAL (destructivo). Quien llama debe crear un respaldo antes."""
    ruta = resolver(archivo)
    verificar(str(ruta))
    if es_mariadb():
        connection.close()
        _cargar_mariadb(ruta, settings.DATABASES['default']['NAME'], recrear=False)
        return
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / 'restaurar.sqlite3'
        _descomprimir(ruta, tmp)
        # API de backup sobre la conexión abierta: funciona en Windows aunque el archivo esté
        # en uso (no hay que borrar ni renombrar el .sqlite3 ni su -wal).
        if connection.in_atomic_block:
            raise ErrorRespaldo('No se puede restaurar dentro de una transacción abierta.')
        connection.ensure_connection()
        origen = sqlite3.connect(tmp)
        try:
            origen.backup(connection.connection)
        finally:
            origen.close()


# --------------------------------------------------------------------------- copia fuera de esta computadora
# Si el disco falla o se roban la PC, los respaldos de datos/respaldos se pierden con ella. Cada respaldo
# se copia además a otra carpeta (memoria USB, disco externo o carpeta de red), CIFRADO con la llave de
# config.json: quien encuentre la memoria no puede leer nombres ni respuestas. Para restaurar hace falta
# esa misma llave (guárdala aparte: Configuración → Protección de datos → Llave de recuperación).

SUFIJO_CIFRADO = '.cifrado'
COPIAS_A_CONSERVAR = 30


def carpeta_copia() -> Path | None:
    from ..models import Configuracion
    valor = (Configuracion.obtener('respaldo.copia_carpeta') or '').strip()
    return Path(valor) if valor else None


def estado_copia() -> dict:
    from ..models import Configuracion
    return Configuracion.obtener('respaldo.copia_estado') or {}


def _guardar_estado(**datos) -> None:
    from ..models import Configuracion
    Configuracion.guardar('respaldo.copia_estado', estado_copia() | datos | {'intento': timezone.now().isoformat()})


def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(settings.CONFIG['CLAVE_CIFRADO'].encode())


def probar_carpeta(ruta: Path) -> None:
    """Lanza ErrorRespaldo con un mensaje claro si no se puede escribir ahí."""
    if not ruta.is_absolute():
        raise ErrorRespaldo('Escribe la ruta completa, por ejemplo E:\\Respaldos o \\\\servidor\\Admisiones\\Respaldos.')
    try:
        if ruta.resolve() == directorio().resolve() or directorio().resolve() in ruta.resolve().parents \
                or Path(settings.DATA_DIR).resolve() in ruta.resolve().parents:
            raise ErrorRespaldo('Esa carpeta está dentro de los datos del programa: no protege de nada. Usa otra unidad.')
    except OSError:
        pass
    if not ruta.exists():
        raise ErrorRespaldo('No encuentro esa carpeta. ¿Está conectada la memoria o el disco?')
    prueba = ruta / '.prueba-prospectos'
    try:
        prueba.write_bytes(b'ok')
        prueba.unlink()
    except OSError as e:
        raise ErrorRespaldo(f'No se puede escribir en esa carpeta ({e.strerror or e}).') from e


def copiar_externo(archivo: str | None = None) -> str | None:
    """Copia cifrada del respaldo indicado (o del último bueno). Devuelve el nombre copiado, o None si no hay carpeta."""
    destino_dir = carpeta_copia()
    if not destino_dir:
        return None
    ultimo = Respaldo.objects.filter(estado='ok', **({'archivo': archivo} if archivo else {})).order_by('-creado_en').first()
    if not ultimo:
        return None
    origen = directorio() / ultimo.archivo
    try:
        probar_carpeta(destino_dir)
        if not origen.is_file():
            raise ErrorRespaldo(f'No encuentro {ultimo.archivo} en esta computadora.')
        nombre = ultimo.archivo + SUFIJO_CIFRADO
        tmp = destino_dir / (nombre + '.parcial')
        tmp.write_bytes(_fernet().encrypt(origen.read_bytes()))
        os.replace(tmp, destino_dir / nombre)
        copias = sorted(destino_dir.glob('prospectos-*.gz' + SUFIJO_CIFRADO))
        for viejo in copias[:-COPIAS_A_CONSERVAR]:
            viejo.unlink(missing_ok=True)
    except (ErrorRespaldo, OSError) as e:
        _guardar_estado(ok=False, mensaje=str(e)[:300])
        raise ErrorRespaldo(str(e)) from e
    _guardar_estado(ok=True, mensaje='', archivo=nombre, fecha=timezone.now().isoformat())
    return nombre


def copia_pendiente() -> bool:
    """Hay carpeta configurada y el último respaldo bueno todavía no está copiado."""
    if not carpeta_copia():
        return False
    ultimo = Respaldo.objects.filter(estado='ok').order_by('-creado_en').first()
    return bool(ultimo) and estado_copia().get('archivo') != ultimo.archivo + SUFIJO_CIFRADO


def descifrar_copia(ruta: Path, destino_dir: Path) -> Path:
    """Convierte una copia .cifrado en un respaldo .gz normal (necesita la misma llave de config.json)."""
    from cryptography.fernet import InvalidToken
    try:
        datos = _fernet().decrypt(ruta.read_bytes())
    except InvalidToken as e:
        raise ErrorRespaldo('Esta copia se cifró con otra llave. Pon en datos/config.json la llave de recuperación '
                            'de la computadora donde se hizo.') from e
    salida = destino_dir / ruta.name.removesuffix(SUFIJO_CIFRADO)
    salida.write_bytes(datos)
    return salida
