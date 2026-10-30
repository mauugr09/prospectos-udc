# Teléfonos y tabletas (Android, iPhone y iPad)

Prospectos se usa igual desde una computadora (Windows o Mac), un teléfono o una tableta Android, un
iPhone o un iPad. No hay una app aparte en Play Store ni en App Store: el programa sigue corriendo en
**una sola** computadora de Admisiones y los demás equipos entran con el navegador. En el teléfono se
puede **agregar a la pantalla de inicio** y se abre como una app, con su icono y sin la barra del navegador.

## Qué se necesita

> **Con servidor central** ([docs/servidor.md](servidor.md)) todo esto se simplifica: se entra desde
> cualquier lugar (Wi‑Fi o datos móviles) y **no hay que instalar certificados**. Basta abrir la dirección
> (o escanear el QR de Configuración → Otras computadoras) y agregarla a la pantalla de inicio. Lo de abajo es
> para cuando el programa corre solo en una PC de la oficina, sin dirección pública.

- El **acceso por red** activo en la computadora del programa (Configuración → Otras computadoras).
- El teléfono o tableta en el **Wi‑Fi de la oficina** (la misma red que esa computadora). Con datos
  móviles no se llega.
- Android 9 o mayor con Chrome, Edge o Samsung Internet; iPhone/iPad con iOS/iPadOS 15 o mayor y Safari.
- En Android, que el teléfono tenga bloqueo de pantalla (PIN, patrón o huella): Android lo exige para
  instalar certificados.

## Conectar un teléfono o tableta (una sola vez)

1. En la computadora del programa: **Configuración → Otras computadoras**. Con el acceso por red activo
   aparece un **código QR**.
2. En el teléfono, apunta la cámara al QR. Se abre la página **Conectar con Prospectos**, que ya muestra
   los pasos del sistema del teléfono (pestañas Windows · Mac · Android · iPhone/iPad).
   - La primera vez el navegador dice que la conexión no es privada: es normal antes de instalar el
     certificado. Android: *Configuración avanzada → Acceder*. iPhone: *Mostrar detalles → visitar este sitio web*.
3. **Descarga el certificado**, compara la huella y sigue los pasos:

   **Android**
   1. Toca *Descargar certificado* (queda en Descargas).
   2. Ajustes → busca «certificado» → *Instalar un certificado* → *Certificado de CA* → *Instalar de todas
      formas* → elige `Prospectos-UDC.crt` → confirma con tu PIN.
   3. Para comparar la huella: Ajustes → *Credenciales de confianza* → pestaña *Usuario* → Prospectos UDC.
   4. Cierra Chrome por completo y vuelve a abrirlo. (Firefox para Android no usa estos certificados.)

   **iPhone / iPad**
   1. En **Safari** (no en Chrome), toca *Descargar certificado* → *Permitir*.
   2. Ajustes → *Perfil descargado* → *Instalar* → código → *Instalar*. En «Más detalles» está la huella SHA‑256.
   3. Ajustes → General → Información → *Ajustes de confianza de certificados* → activa **Prospectos UDC**.
      Sin este paso el iPhone tiene el certificado pero no confía en él.
   4. Cierra Safari y vuelve a abrirlo.

4. Entra a `https://<IP>:8443/admin/` y agrégalo a la pantalla de inicio:
   - **iPhone/iPad:** Compartir → *Agregar a inicio* → Agregar.
   - **Android:** menú ⋮ → *Instalar app* (o *Agregar a la pantalla principal*). En la página de conectar
     también aparece el botón **Instalar Prospectos** cuando Chrome ya lo permite.

En Android usa siempre la dirección con números (la IP): muchos teléfonos no reconocen los nombres `.local`.

## Qué cambia en un teléfono

- **Todas las pantallas se acomodan** al ancho del teléfono o tableta. Las listas largas del panel
  (Eventos, Preparatorias…) se deslizan de lado; **Prospectos** (Llamar hoy, Nuevos, Todos…) se ve como lista.
- En la **ficha**, al pulsar *Mostrar* en Contacto aparecen botones **Llamar**, **WhatsApp** y **Correo**.
  Los números de 10 dígitos se marcan con +52. En la computadora abren lo que tenga configurado
  (WhatsApp Web, la app de correo).
- Los campos de texto usan letra de 16 px en pantallas táctiles: así el iPhone no hace zoom al tocarlos.
- Las **cartas y reportes imprimibles** (solicitud, reporte final, cartas de beca) se ven completos a
  escala; al imprimir o «Guardar como PDF» salen en tamaño carta real.
- Sin Wi‑Fi de la oficina, la app muestra **«Sin conexión con Prospectos»** con qué revisar, en vez de un
  error del navegador.

## Privacidad (LFPDPPP)

- El teléfono **no guarda datos de aspirantes**. El *service worker* (`/sw.js`) solo guarda la pantalla
  «Sin conexión» y un icono; todas las páginas del programa se piden siempre a la computadora. Si un
  teléfono se pierde, no lleva fichas, listas ni reportes dentro.
- La sesión se cierra a los 30 minutos sin uso, igual que en las computadoras. Recomendado: teléfonos con
  bloqueo de pantalla y no guardar la contraseña en teléfonos compartidos.
- Instalar el certificado de Prospectos hace que ese equipo confíe en lo que firme la autoridad del
  programa. Por eso `datos/red/ca.key` nunca sale de la computadora del programa. Si un teléfono deja de
  usarse (cambio de personal), quita el certificado: Android, *Credenciales de confianza → Usuario*;
  iPhone, *General → VPN y administración de dispositivos → Prospectos UDC → Eliminar perfil*.

## Para quien da mantenimiento

| Pieza | Dónde |
|---|---|
| Etiquetas para instalar (manifiesto, icono de Apple, `theme-color`) | `prospectos/templates/prospectos/_movil_head.html`, incluida en todas las pantallas desde `prospectos/templates/unfold/layouts/skeleton.html` (extiende la de unfold y solo cambia el bloque `responsive`) |
| Manifiesto, service worker, sistema del visitante, enlaces tel:/WhatsApp/mailto | `prospectos/servicios/movil.py` · vistas `manifiesto`, `service_worker`, `sin_conexion` en `prospectos/views.py` |
| Registro del service worker | `prospectos/static/prospectos/js/movil.js` |
| Iconos | `prospectos/static/prospectos/marca/icono-180.png` (Apple, cuadrado sin transparencia), `icono-192.png`, `icono-512.png`, `icono-maskable-512.png` (Android, dibujo dentro del 80 % central) |
| Estilos táctiles y tablas que se vuelven tarjetas (`.tabla-tarjetas` + `data-et` en cada celda) | sección «TELÉFONOS Y TABLETAS» al final de `estilos/udc.css` (recompilar con Tailwind, ver el encabezado del archivo) |
| Pruebas | `tests/test_movil.py` |

`/sw.js`, `/manifest.webmanifest` y `/sin-conexion/` no cuentan como actividad para el cierre por
inactividad (el teléfono los pide solo) ni exigen haber cambiado la contraseña temporal.
Si se cambia el service worker, sube `VERSION_SW` en `movil.py` para que los teléfonos tomen el nuevo.

Para agregar otra tabla que se vuelva tarjetas en el teléfono: clase `tabla-tarjetas` en `<table>`,
`tt-score` y `tt-principal` en las dos primeras celdas y `data-et="Nombre de la columna"` en las demás.
