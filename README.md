# Prospectos · Admisiones

Programa para la computadora de Admisiones que importa las respuestas de los dos Google Forms
aplicados en las visitas a preparatorias (alumno y tutor), las une por aspirante, las segmenta,
prioriza el seguimiento de los asesores y genera reportes. **No se instala nada**: es una carpeta
con `Prospectos.exe`.

> **Empieza aquí: [Puesta en marcha con tus datos reales](docs/puesta-en-marcha.md)** ·
> [Configurar los Google Forms](docs/formularios.md) · [MariaDB y acceso a la base](docs/mariadb.md) ·
> [Guía para Admisiones](docs/operacion.md) · [Seguridad y LFPDPPP](docs/seguridad.md) · [Decisiones de diseño](docs/decisiones.md)

## Usarlo (Windows 10/11)

1. Descomprime `Prospectos-windows.zip` en **`C:\Prospectos`** (no en Descargas ni en OneDrive:
   si OneDrive sincroniza la base de datos mientras está abierta, se puede dañar).
2. Doble clic en **`Prospectos.exe`**.
   - Windows puede mostrar *«Windows protegió su PC»* porque el programa no está firmado
     digitalmente: **Más información → Ejecutar de todas formas**. Si el antivirus lo bloquea,
     agrega `C:\Prospectos` a sus exclusiones (ver «Limitaciones»).
3. La primera vez pregunta:
   - **D** → carga datos de **demostración** ficticios. Usuarios `admin@demo.local`,
     `admisiones@demo.local`, `directivo@demo.local`, `promotor1@demo.local` con contraseña
     `Demo-Prospectos-2026!`.
   - **A** → crea el **administrador real** (correo y contraseña de 12+ caracteres).
4. Se abre el navegador en `http://127.0.0.1:8000/admin/`. **Deja abierta la ventana negra**:
   ahí corren la importación (cada minuto), las tareas, los respaldos y la retención. Para
   apagar el sistema, cierra esa ventana.

Si abres `Prospectos.exe` otra vez con el programa ya abierto, solo abre el navegador.

**¿No sabes por dónde empezar?** Menú lateral → **¿Cómo funciona?** Y si contestaron un Form y
«no aparece», revisa **Respuestas de los Forms**: casi siempre está *Esperando permiso* (dice qué falta).

El programa ya está hecho para el **Cuestionario Vocacional** y la **Encuesta para padres de familia**
de la universidad (Cuautitlán y Tultepec). Lo que conviene agregarle al Form está en [docs/formularios.md](docs/formularios.md), sección 3.

### Pasar de la demo a datos reales

Sigue [docs/puesta-en-marcha.md](docs/puesta-en-marcha.md): primero en una carpeta de **pruebas**
(`C:\ProspectosPrueba`) con tus Forms reales y, cuando cuadre, en la carpeta definitiva.

## Qué hay en la carpeta `datos` (lo único que hay que respaldar)

| Archivo | Qué es |
|---|---|
| `config.json` | Configuración y **llaves de cifrado**. Sin este archivo los correos y teléfonos guardados **no se pueden leer nunca más**. Guarda una copia en un USB o en el gestor de contraseñas de la institución, **separada** de los respaldos. |
| `prospectos.sqlite3` (+ `-wal`, `-shm`) | La base de datos. No la copies con el programa abierto: usa los respaldos. |
| `respaldos\` | Un respaldo comprimido cada noche (02:30, o al abrir si se perdió), 14 días de historia, verificado cada semana. **Cópialos a otro equipo**: si el disco falla, se pierden junto con la base. |
| `prospectos.log` | Bitácora técnica (errores del importador, etc.). No contiene datos personales. |
| `correos\` | Solo en demo: los correos de bienvenida se guardan aquí en vez de enviarse. |
| `google-service-account.json` | La llave de la cuenta de servicio de Google (la pones tú). Si Windows la dejó como `.json.json` por la extensión oculta, también funciona. |
| `google-oauth-cliente.json`, `google-token.json` | Solo en modo OAuth (ver docs/formularios.md, 1B). El token es una credencial. |
| `logo.png` | Opcional: logotipo blanco para el menú lateral. |

## Configuración (`datos\config.json`)

Ábrelo con el Bloc de notas con el programa **cerrado**. **No cambies** `SECRET_KEY`,
`CLAVE_CIFRADO` ni `CLAVE_INDICE_CIEGO`.

| Clave | Para qué |
|---|---|
| `GOOGLE_CUENTA_SERVICIO` | Ruta del JSON de la cuenta de servicio. |
| `GOOGLE_MODO` | `"oauth"` para leer los Forms con una cuenta institucional (lo pone `conectar_google`). Sin la clave: cuenta de servicio. |
| `BASE_DATOS` | Opcional: usar MariaDB **10.11+** en vez del archivo SQLite. Ver [docs/mariadb.md](docs/mariadb.md). |
| `CORREO` | Servidor SMTP para el correo de bienvenida (`HOST`, `PUERTO`, `USUARIO`, `CLAVE`, `TLS`, `REMITENTE`). Vacío = no se envía (se guarda en `datos\correos`). |
| `NOMBRE_INSTITUCION` | Firma del correo de bienvenida (opcional). |
| `PUERTO` | Puerto local (8000). |
| `CUARENTENA_DIAS` | Días que se conserva la respuesta de un menor sin consentimiento del tutor (30). |
| `RETENCION_MESES` | Meses sin actividad tras los que se anonimiza un prospecto (18). |
| `DIAS_SIN_CONTACTO` | Días sin contacto para crear una tarea automática (5). |
| `RESPALDO_HORA`, `RESPALDO_DIAS_RETENCION` | Hora del respaldo diario y días que se guardan. |
| `IA_HABILITADA`, `IA_API_KEY`, `IA_MODELO` | Clasificación opcional de respuestas abiertas (apagada). |
| `GOOGLE_MAPS_API_KEY` | Opcional: llave de Google Maps (mejor ponerla en el panel: Configuración → Mapa). Sin llave se usa OpenStreetMap. |
| `MAPA_TILES` | Opcional: otro proveedor de fondo de mapa (URL con `{z}/{x}/{y}`) y `MAPA_TILES_ATRIBUCION`. Por defecto OpenStreetMap, sin llave. (CARTO ya no sirve sin llave: si estaba configurado se ignora.) |

## Diseño e identidad de la Universidad

Diseño al estilo de las apps de Apple, en modo **claro u oscuro** (según el sistema, o el que elija cada quien en su menú de usuario: Claro / Oscuro / Sistema). El Inicio abre con **a quién llamar hoy** y los pendientes; debajo, el resumen del periodo
(7, 30, 90 días o 12 meses): cifras clave, gráfica de actividad, mapa de preparatorias, embudo, carreras y grupos.
Un solo color de acción, el azul rey de udcm.mx (`#254099`, un punto más vivo en pantalla), sobre grises neutros;
la letra es la del sistema (Segoe UI en Windows). El vidrio se usa solo en lo que flota sobre el contenido y las
animaciones solo responden a lo que hace la persona; con «reducir movimiento» de Windows activado no hay ninguna.

**Logotipo:** el programa no trae el logo oficial. Para mostrarlo en el menú lateral, guarda la
versión **blanca** con fondo transparente como `datos\logo.png` (PNG, ~300 px de ancho) y recarga
la página. Usa el archivo oficial que te dé Comunicación/Imagen institucional.

## Comandos (opcionales)

En la carpeta `C:\Prospectos`, clic derecho → *Abrir en Terminal*:

```
.\Prospectos.exe registrar_formulario alumno "URL de edición del Form"
.\Prospectos.exe probar_google             (diagnóstico de la conexión con Google)
.\Prospectos.exe conectar_google           (modo OAuth: autorizar la cuenta institucional)
.\Prospectos.exe pasar_a_mariadb           (copiar los datos de SQLite a MariaDB)
.\Prospectos.exe respaldo crear
.\Prospectos.exe respaldo listar
.\Prospectos.exe respaldo verificar
.\Prospectos.exe respaldo restaurar prospectos-20261027-023000.sqlite3.gz   (con el programa CERRADO)
.\Prospectos.exe crear_admin                (crear otro admin o restablecer una contraseña)
.\Prospectos.exe importar_respuestas
.\Prospectos.exe sincronizar_preguntas 1    (ver el mapeo propuesto del formulario 1)
.\Prospectos.exe recalcular
.\Prospectos.exe retencion
```

La restauración pide escribir `RESTAURAR`, crea antes un respaldo de lo actual y se niega a
correr si el programa está abierto.

## Windows y Mac

| | Windows 10/11 | Mac con chip Apple (macOS 12+) |
|---|---|---|
| Descarga | `Prospectos-windows.zip` | `Prospectos-mac.dmg` |
| Instalar | Descomprimir en `C:\Prospectos` | Arrastrar a Aplicaciones; la primera vez *Privacidad y seguridad → Abrir igualmente* |
| Ventana del programa | Ventana negra | Ventana de Terminal |
| Datos | `C:\Prospectos\datos` | `~/Library/Application Support/Prospectos UDC` |
| Comandos | `Prospectos.exe respaldo crear` | `/Applications/Prospectos.app/Contents/MacOS/Prospectos respaldo crear` |

Los datos son los mismos en los dos sistemas: para pasar de uno a otro se copia la carpeta de datos completa
(con su `config.json`) con el programa cerrado en ambos. Las dos versiones se compilan solas en GitHub
(`.github/workflows/compilar.yml`): corre las pruebas, compila en un Windows y en una Mac reales, arranca cada
versión y comprueba que responde por HTTP local y por HTTPS en red antes de publicarla.

## Limitaciones (léelas antes de decidir)

- **Una computadora corre el programa; las demás entran por la red.** Windows o Mac, con el navegador
  (Configuración → *Otras computadoras*). En la red solo atiende por **HTTPS** con un certificado propio que
  cada computadora instala una vez; nunca por HTTP en claro. Si se instala el programa en varias computadoras,
  cada una tiene **datos separados**: no lo hagan. Con la base SQLite aguanta bien a un equipo de admisiones
  (unas 10 personas a la vez); más que eso, MariaDB (`docs/mariadb.md`).
- **Solo trabaja mientras está abierto.** Si la PC está apagada no se importa ni se respalda;
  al abrirlo se pone al día (la importación es incremental y no pierde respuestas).
- **Fuera de la oficina no se puede entrar** (el modo en vivo desde la preparatoria tampoco) sin una VPN.
  No abran el puerto a internet.
- **Sin firma digital de pago**: en Windows, SmartScreen y algunos antivirus desconfían de los programas
  hechos con PyInstaller; en Mac hay que permitirlo una vez en *Privacidad y seguridad → Abrir igualmente*.
  Quitar esos avisos requiere un certificado de firma de código (Windows) y una cuenta de Apple Developer
  (99 USD al año, para firmar y «notarizar» la app de Mac).
- **Mac: solo chip Apple** (M1 en adelante, macOS 12 o mayor). Las Mac con Intel no están contempladas.
- El detalle de calles del mapa necesita internet (solo se piden mosaicos a OpenStreetMap por coordenadas; sin datos personales). Sin internet se ven los 32 estados, los municipios cercanos a los planteles y los pines. La búsqueda de direcciones al ubicar prepas usa Nominatim (OpenStreetMap) y también necesita internet.

## Para desarrolladores

Requiere Python 3.13.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/pytest                          # 192 pruebas (SQLite)
.venv/bin/pytest --ds=config.settings_pruebas_mariadb   # las mismas contra MariaDB 10.11+
.venv/bin/python lanzador.py              # igual que el .exe (datos en ./datos)
.venv/bin/python manage.py demo           # datos ficticios
```

### Construir `Prospectos.exe`

- **GitHub**: sube el proyecto a un repositorio y ejecuta la acción *Construir Prospectos.exe*
  (`.github/workflows/windows.yml`): corre las pruebas en Windows, construye, hace una prueba de
  humo del .exe y deja la carpeta como artefacto descargable.
- **En Windows con Python**:
  ```
  pip install -r requirements.txt pyinstaller==6.22.3
  python manage.py collectstatic --noinput
  python -m PyInstaller --noconfirm prospectos.spec
  ```
  Resultado: `dist\Prospectos\` (comprímela y distribúyela).

### Estructura

| Ruta | Qué |
|---|---|
| `lanzador.py` | Punto de entrada del .exe: prepara la base, primer arranque, servidor (waitress) y navegador. |
| `prospectos/programador.py` | Tareas periódicas en un hilo (importar, tareas, respaldos, verificación, retención, IA). |
| `prospectos/servicios/` | Lógica: `importacion`, `fuentes` (Forms API / demo), `inteligencia` (enlace, score, segmentos, brechas, fusión), `seguimiento`, `seguridad` (anonimización, retención, IA), `respaldos`, `reportes` (métricas, comparativo, QR), `cifrado`, `texto`, `semillas`. |
| `prospectos/admin.py`, `views.py` | Panel (Django admin con el tema django-unfold) y pantallas extra. |
| `estilos/udc.css` | Fuente del CSS de la marca (Tailwind 4). Se compila a `prospectos/static/prospectos/css/udc.css` con `npm i tailwindcss@4 @tailwindcss/cli@4` y `npx tailwindcss -i estilos/udc.css -o prospectos/static/prospectos/css/udc.css --minify` (en la carpeta donde se instaló). |
| `estilos/traducciones.py` | Traducciones al español del tema (genera `prospectos/locale/es/LC_MESSAGES/django.mo`). |
| `tests/` | Pruebas (pytest). |
