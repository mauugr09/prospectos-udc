#!/bin/bash
# Ejecutable principal de Prospectos.app.
#  - Con doble clic: abre Terminal con el programa (ahí se ve qué hace; al cerrar la ventana se detiene),
#    igual que la ventana negra de Windows.
#  - Desde Terminal, con o sin argumentos: ejecuta el programa ahí mismo, p. ej.
#      /Applications/Prospectos.app/Contents/MacOS/Prospectos crear_admin
set -u
APP="$(cd "$(dirname "$0")/../.." && pwd)"
PROGRAMA="$APP/Contents/Resources/prospectos/Prospectos"

aviso() {  # ventana nativa de macOS
  /usr/bin/osascript -e "display dialog \"$1\" with title \"Prospectos\" buttons {\"OK\"} default button 1 with icon caution" >/dev/null 2>&1
}

# macOS abre las apps descargadas desde una copia de solo lectura hasta que se mueven a Aplicaciones.
case "$APP" in
  */AppTranslocation/*)
    aviso "Antes de abrir Prospectos, arrástralo a la carpeta Aplicaciones y ábrelo desde ahí."
    exit 1 ;;
esac

# La persona ya aprobó abrir esta app (Ajustes > Privacidad y seguridad > Abrir igualmente).
# Se quita la marca de «descargado de internet» de las piezas internas para que macOS no vuelva
# a preguntar por cada una (no está firmada con un certificado de Apple de pago).
/usr/bin/xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true

if [ "$#" -gt 0 ] || [ -t 0 ]; then
  exec "$PROGRAMA" "$@"
fi
exec /usr/bin/open -a Terminal "$PROGRAMA"
