"""
«Conectar a Prospectos.cmd»: un archivo de un clic para las computadoras Windows que se conectan a la principal.

Lo genera la principal (Otras computadoras → Descargar) con sus direcciones y la huella SHA-256 COMPLETA de su
certificado ya escrita adentro. En la otra computadora, doble clic:
  1. prueba las direcciones en orden y descarga el certificado de la primera que responda;
  2. lo compara con la huella incrustada (si no es idéntica, se detiene: alguien se hace pasar por la principal);
  3. lo instala en los certificados de confianza DEL USUARIO (Windows pide confirmar; no requiere administrador);
  4. deja un acceso directo «Prospectos UDC» en el Escritorio y abre el navegador.
No copia el programa ni guarda datos. La confianza viene de cómo llega el archivo (memoria USB, carpeta compartida
de la oficina, correo interno): por eso no se ofrece en la página pública conectar/.
Variable PROSPECTOS_SIN_INSTALAR=1: hace todo menos instalar el certificado y abrir el navegador (para pruebas).
"""

from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

PLANTILLA_PS = r"""
$ErrorActionPreference = 'Stop'
$direcciones = @(__DIRECCIONES__)
$huella = '__HUELLA__'
$codigo = '__CODIGO__'
Write-Host ''
Write-Host '  Prospectos UDC - conectar esta computadora a la principal' -ForegroundColor Cyan
Write-Host "  Codigo de la principal: $codigo"
Write-Host ''
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
function Descargar($url, $sinVerificar) {
  if ($PSVersionTable.PSVersion.Major -ge 6) {
    if ($sinVerificar) { $c = (Invoke-WebRequest -Uri $url -SkipCertificateCheck -NoProxy -TimeoutSec 8 -UseBasicParsing).Content }
    else { $c = (Invoke-WebRequest -Uri $url -NoProxy -TimeoutSec 8 -UseBasicParsing).Content }
    if ($c -is [byte[]]) { $c = [Text.Encoding]::ASCII.GetString($c) }
    return $c
  }
  if ($sinVerificar) { [Net.ServicePointManager]::ServerCertificateValidationCallback = { $true } } else { [Net.ServicePointManager]::ServerCertificateValidationCallback = $null }
  $wc = New-Object Net.WebClient
  $wc.Proxy = $null
  try { return $wc.DownloadString($url) } finally { $wc.Dispose() }
}
$servidor = $null; $pem = $null
foreach ($d in $direcciones) {
  Write-Host "  Probando $d ..."
  try { $pem = Descargar ($d + 'conectar/Prospectos-UDC.crt') $true; if ($pem -match 'BEGIN CERTIFICATE') { $servidor = $d; break } } catch { }
}
if (-not $servidor) {
  Write-Host ''
  Write-Host '  No se encontro la principal. Revisa que este encendida, con el programa abierto y el acceso por red activo,' -ForegroundColor Yellow
  Write-Host '  y que esta computadora este en la misma red o en la VPN.' -ForegroundColor Yellow
  exit 2
}
$b64 = ($pem -replace '-----[A-Z ]+-----', '' -replace '\s', '')
$der = [Convert]::FromBase64String($b64)
$sha = [Security.Cryptography.SHA256]::Create()
$calculada = ([BitConverter]::ToString($sha.ComputeHash($der)) -replace '-', '')
if ($calculada -ne $huella) {
  Write-Host ''
  Write-Host '  ALTO: el certificado NO es el de la principal (la huella no coincide).' -ForegroundColor Red
  Write-Host '  No se instalo nada. Avisa a quien administra el programa.' -ForegroundColor Red
  exit 3
}
Write-Host '  Certificado comprobado.' -ForegroundColor Green
if ($env:PROSPECTOS_SIN_INSTALAR -eq '1') { Write-Host "  (prueba) Se conectaria a $servidor"; exit 0 }
$cert = New-Object Security.Cryptography.X509Certificates.X509Certificate2 (, $der)
$almacen = New-Object Security.Cryptography.X509Certificates.X509Store ('Root', 'CurrentUser')
$almacen.Open('ReadWrite')
try {
  if (-not ($almacen.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint })) {
    Write-Host '  Windows te preguntara si instalas el certificado de Prospectos UDC: elige Si.'
    $almacen.Add($cert)
  }
} finally { $almacen.Close() }
$escritorio = [Environment]::GetFolderPath('Desktop')
$atajo = Join-Path $escritorio 'Prospectos UDC.url'
Set-Content -Path $atajo -Value "[InternetShortcut]`r`nURL=$($servidor)admin/`r`n" -Encoding ASCII
Write-Host ''
Write-Host '  Listo. En el Escritorio quedo el acceso directo "Prospectos UDC".' -ForegroundColor Green
Write-Host '  Si el navegador abierto muestra un aviso de seguridad, cierralo y vuelve a abrirlo.'
Start-Process ($servidor + 'admin/')
exit 0
"""

CABECERA_CMD = (
    '@echo off\r\n'
    'rem Prospectos UDC: conecta esta computadora a la principal. Es un archivo de texto: puedes abrirlo y leerlo.\r\n'
    'powershell -NoProfile -ExecutionPolicy Bypass -Command "$t=[IO.File]::ReadAllText(\'%~f0\'); '
    'iex ($t.Substring($t.IndexOf(\'#\'+\'POWERSHELL#\')+12))"\r\n'
    'echo.\r\n'
    'pause\r\n'
    'exit /b\r\n'
    '#POWERSHELL#\r\n'
)


def huella_completa(ca_crt: Path) -> str:
    cert = x509.load_pem_x509_certificate(Path(ca_crt).read_bytes())
    return cert.fingerprint(hashes.SHA256()).hex().upper()


def generar(direcciones: list[str], ca_crt: Path, codigo: str) -> str:
    """El contenido del .cmd (solo ASCII; los textos van sin acentos a propósito: la consola de Windows los rompe)."""
    if not direcciones:
        raise ValueError('La principal no tiene direcciones de red: activa el acceso por red primero.')
    for d in direcciones:
        if "'" in d or not d.startswith('https://'):
            raise ValueError(f'Dirección inválida: {d}')
    lista = ', '.join(f"'{d}'" for d in direcciones)
    ps = (PLANTILLA_PS.replace('__DIRECCIONES__', lista).replace('__HUELLA__', huella_completa(ca_crt))
          .replace('__CODIGO__', codigo or ''))
    return CABECERA_CMD + ps.replace('\n', '\r\n')


def pem_der(ca_crt: Path) -> bytes:
    return x509.load_pem_x509_certificate(Path(ca_crt).read_bytes()).public_bytes(serialization.Encoding.DER)
