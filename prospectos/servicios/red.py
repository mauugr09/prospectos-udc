"""
Uso desde otras computadoras de la red (Windows o Mac, con el navegador).

Una sola computadora corre el programa; las demás entran por https://<esa-computadora>:8443.
Sin HTTPS, contraseñas y datos de aspirantes viajarían legibles por la red de la oficina, así que en red
el programa SOLO atiende por HTTPS, con un certificado propio:

  - Autoridad local (CA) «Prospectos UDC»: se crea una vez en la carpeta de datos (red/ca.crt y red/ca.key).
    Cada computadora que vaya a entrar instala ca.crt UNA vez (Windows: «Entidades de certificación raíz de
    confianza»; Mac: Acceso a Llaveros → «Confiar siempre»). La llave ca.key nunca sale de esta computadora.
  - Certificado del servidor: firmado por esa CA con los nombres e IP actuales de esta computadora; dura
    397 días y se renueva solo si cambia la IP o está por vencer (los navegadores rechazan más de 398/825 días).

En esta misma computadora se sigue entrando por http://127.0.0.1 (no sale de la máquina).
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import json
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

PUERTO_RED_OMISION = 8443
_VIGENCIA_SERVIDOR = dt.timedelta(days=397)
_RENOVAR_ANTES = dt.timedelta(days=30)


# --------------------------------------------------------------------------- configuración
def activa(config: dict) -> bool:
    """La red se activa con "EN_RED": true. Compatibilidad: "ESCUCHAR_EN": "0.0.0.0" (antes era HTTP en claro)."""
    if config.get('EN_RED'):
        return True
    host = str(config.get('ESCUCHAR_EN', '127.0.0.1'))
    return host not in ('127.0.0.1', 'localhost', '::1', '')


def puerto(config: dict) -> int:
    return int(config.get('PUERTO_RED', PUERTO_RED_OMISION))


def nombres_fijos(config: dict) -> list[str]:
    """Dirección fija que dio sistemas (nombre o IP en la VPN o la red entre planteles). Va en el certificado."""
    valor = config.get('NOMBRES_RED') or []
    if isinstance(valor, str):
        valor = [valor]
    return [n for n in (normalizar_nombre(v) for v in valor) if n]


def normalizar_nombre(texto: str) -> str | None:
    """«https://10.20.1.15:8443/» → «10.20.1.15». None si no es un nombre o IP válidos."""
    import re
    t = (texto or '').strip().lower()
    t = re.sub(r'^[a-z]+://', '', t).split('/')[0]
    if t.startswith('['):
        return None
    t = t.split(':')[0]
    try:
        ipaddress.ip_address(t)
        return t
    except ValueError:
        pass
    if re.fullmatch(r'(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*', t):
        return t
    return None


def guardar_config(config_file: Path, **valores) -> dict:
    datos = json.loads(config_file.read_text(encoding='utf-8'))
    datos.update(valores)
    config_file.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding='utf-8')
    return datos


def guardar_activa(config_file: Path, valor: bool) -> None:
    datos = json.loads(config_file.read_text(encoding='utf-8'))
    datos['EN_RED'] = bool(valor)
    if not valor and str(datos.get('ESCUCHAR_EN', '127.0.0.1')) not in ('127.0.0.1', 'localhost', '::1', ''):
        datos['ESCUCHAR_EN'] = '127.0.0.1'
    config_file.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding='utf-8')


# --------------------------------------------------------------------------- nombres de esta computadora
def nombre_equipo() -> str:
    return socket.gethostname().split('.')[0]


def ips_locales() -> list[str]:
    """IPv4 de esta computadora en la red local (sin 127.x). Sin red, lista vacía."""
    ips: set[str] = set()
    try:  # la interfaz con la que se sale a la red (no envía nada: UDP sin datos)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('10.255.255.255', 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith('127.') and ip != '0.0.0.0')  # nosec B104


def nombres_servidor(fijos: list[str] | tuple = ()) -> list[str]:
    """Nombres con los que las demás computadoras pueden llegar: la dirección fija (si hay), IP, nombre del equipo
    y nombre.local (Bonjour)."""
    equipo = nombre_equipo()
    nombres = [*fijos, equipo, f'{equipo}.local', 'localhost', *ips_locales(), '127.0.0.1']
    vistos, salida = set(), []
    for n in nombres:
        if n and n.lower() not in vistos:
            vistos.add(n.lower())
            salida.append(n)
    return salida


def direcciones(config: dict) -> list[str]:
    """Primero la IP (funciona en cualquier computadora); luego los nombres."""
    p = puerto(config)
    fijos, ips = nombres_fijos(config), ips_locales()
    nombres = [n for n in nombres_servidor() if n not in ('localhost', '127.0.0.1') and n not in ips]
    vistos, salida = set(), []
    for n in [*fijos, *ips, *nombres]:
        if n not in vistos:
            vistos.add(n)
            salida.append(f'https://{n}:{p}/')
    return salida


# --------------------------------------------------------------------------- certificados
def _carpeta(data_dir: Path) -> Path:
    c = Path(data_dir) / 'red'
    c.mkdir(parents=True, exist_ok=True)
    return c


def _guardar_llave(ruta: Path, llave) -> None:
    ruta.write_bytes(llave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()))
    try:
        ruta.chmod(0o600)
    except OSError:  # Windows: los permisos los da la carpeta
        pass


def _corto(texto: str) -> str:
    """El «nombre común» de un certificado admite máximo 64 caracteres; los nombres de Mac suelen ser largos
    («MacBook-Pro-de-…»). El nombre completo sigue en la lista de nombres alternativos."""
    return texto if len(texto) <= 64 else texto[:61] + '...'


def _crear_ca(carpeta: Path):
    llave = ec.generate_private_key(ec.SECP256R1())
    ahora = dt.datetime.now(dt.timezone.utc)
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, _corto(f'Prospectos UDC ({nombre_equipo()})')),
                        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Universidad de Cuautitlán · Admisiones')])
    cert = (x509.CertificateBuilder().subject_name(nombre).issuer_name(nombre).public_key(llave.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(ahora - dt.timedelta(minutes=5)).not_valid_after(ahora + dt.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                         key_encipherment=False, data_encipherment=False, key_agreement=False,
                                         encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(llave.public_key()), critical=False)
            .sign(llave, hashes.SHA256()))
    _guardar_llave(carpeta / 'ca.key', llave)
    (carpeta / 'ca.crt').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert, llave


def _cargar_ca(carpeta: Path):
    crt, key = carpeta / 'ca.crt', carpeta / 'ca.key'
    if crt.exists() and key.exists():
        return (x509.load_pem_x509_certificate(crt.read_bytes()),
                serialization.load_pem_private_key(key.read_bytes(), password=None))
    return _crear_ca(carpeta)


def _sans(nombres: list[str]) -> list[x509.GeneralName]:
    salida = []
    for n in nombres:
        try:
            salida.append(x509.IPAddress(ipaddress.ip_address(n)))
        except ValueError:
            salida.append(x509.DNSName(n))
    return salida


def _vigente(ruta: Path, nombres: list[str]) -> bool:
    if not ruta.exists():
        return False
    try:
        cert = x509.load_pem_x509_certificate(ruta.read_bytes())
        if cert.not_valid_after_utc - dt.datetime.now(dt.timezone.utc) < _RENOVAR_ANTES:
            return False
        actuales = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        tiene = {str(v).lower() for v in actuales.get_values_for_type(x509.DNSName)}
        tiene |= {str(v) for v in actuales.get_values_for_type(x509.IPAddress)}
        return {n.lower() for n in nombres} <= tiene
    except (ValueError, x509.ExtensionNotFound):
        return False


def asegurar_certificados(data_dir: Path, fijos: list[str] | tuple = ()) -> tuple[Path, Path, Path]:
    """Devuelve (ca.crt, servidor.crt, servidor.key); los crea o renueva si hace falta."""
    carpeta = _carpeta(data_dir)
    ca_cert, ca_llave = _cargar_ca(carpeta)
    nombres = nombres_servidor(fijos)
    crt, key = carpeta / 'servidor.crt', carpeta / 'servidor.key'
    if not (_vigente(crt, nombres) and key.exists()):
        llave = ec.generate_private_key(ec.SECP256R1())
        ahora = dt.datetime.now(dt.timezone.utc)
        cert = (x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, _corto(nombres[0]))]))
                .issuer_name(ca_cert.subject).public_key(llave.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(ahora - dt.timedelta(minutes=5)).not_valid_after(ahora + _VIGENCIA_SERVIDOR)
                .add_extension(x509.SubjectAlternativeName(_sans(nombres)), critical=False)
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=False, content_commitment=False,
                                             data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                             crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_llave.public_key()), critical=False)
                .sign(ca_llave, hashes.SHA256()))
        _guardar_llave(key, llave)
        # Cadena completa: servidor + CA (algunos navegadores la piden).
        crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM) + ca_cert.public_bytes(serialization.Encoding.PEM))
    return carpeta / 'ca.crt', crt, key


def huella_ca(data_dir: Path) -> str | None:
    """SHA-256 del certificado de la CA, para comparar en cada computadora antes de confiar en él."""
    ruta = Path(data_dir) / 'red' / 'ca.crt'
    if not ruta.exists():
        return None
    cert = x509.load_pem_x509_certificate(ruta.read_bytes())
    h = cert.fingerprint(hashes.SHA256()).hex().upper()
    return ' '.join(h[i:i + 4] for i in range(0, len(h), 4))


def codigo_ca(data_dir: Path) -> str | None:
    """Los primeros 12 caracteres de la huella («3F2A-91C0-77AB»): lo que se compara al conectar otra PC."""
    h = huella_ca(data_dir)
    return codigo_de_huella(h) if h else None


def codigo_de_huella(huella: str) -> str:
    h = huella.replace(' ', '').replace(':', '').upper()
    return f'{h[0:4]}-{h[4:8]}-{h[8:12]}'


# --------------------------------------------------------------------------- descubrimiento en la red local
def responder_descubrimiento(config: dict, data_dir: Path, puerto_udp: int = 8444):
    """Contesta «¿hay una principal?» (cliente.buscar) con el nombre del equipo, el puerto y el código.
    Es información pública (está en el certificado); nada de datos. Devuelve el socket (para cerrarlo) o None."""
    import threading
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', puerto_udp))  # nosec B104
    except OSError:
        return None
    respuesta = json.dumps({'programa': 'prospectos-udc', 'equipo': nombre_equipo(), 'puerto': puerto(config),
                            'codigo': codigo_ca(data_dir)}).encode()

    def atender():
        while True:
            try:
                datos, origen = s.recvfrom(64)
            except OSError:
                return
            if datos == b'PROSPECTOS-UDC?':
                try:
                    s.sendto(respuesta, origen)
                except OSError:
                    pass

    threading.Thread(target=atender, name='descubrir', daemon=True).start()
    return s


# --------------------------------------------------------------------------- servidor HTTPS
def servidor_https(aplicacion, data_dir: Path, config: dict, hilos: int = 8):
    """Servidor HTTPS (cheroot) para la red. Se arranca con .start() en un hilo aparte."""
    from cheroot import wsgi
    from cheroot.ssl.builtin import BuiltinSSLAdapter

    _, crt, key = asegurar_certificados(data_dir, nombres_fijos(config))
    srv = wsgi.Server(('0.0.0.0', puerto(config)), aplicacion, numthreads=hilos, server_name='Prospectos')  # nosec B104
    adaptador = BuiltinSSLAdapter(str(crt), str(key))
    try:  # solo TLS 1.2 o mayor
        import ssl
        adaptador.context.minimum_version = ssl.TLSVersion.TLSv1_2
    except Exception:  # noqa: BLE001 - versión de cheroot sin .context: usa sus valores seguros por omisión
        pass
    srv.ssl_adapter = adaptador
    return srv
