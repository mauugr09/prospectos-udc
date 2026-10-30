# Un solo Prospectos para todos, desde cualquier lugar

El programa corre en **un servidor** con **una sola base de datos**. Todas las computadoras, celulares y
tabletas entran por la misma dirección con HTTPS (por ejemplo `https://prospectos.udcm.mx`), desde la
oficina, desde casa o desde una prepa con datos móviles. Lo que uno captura, los demás lo ven al instante.

```
 Computadoras ─┐                          ┌────────────── servidor ──────────────┐
 Celulares    ─┼── internet (HTTPS) ──► Caddy o Cloudflare ──► Prospectos ──► MariaDB
 Tabletas     ─┘                          └───────────────────────────────────────┘
```

## 1. Elegir dónde vive

| | A. Servidor en la nube | B. Servidor de la universidad | C. Una PC de la oficina |
|---|---|---|---|
| Qué es | Un servidor Linux rentado (DigitalOcean, Hetzner, AWS Lightsail…) | Un servidor que da el área de sistemas | La PC de Admisiones, siempre encendida |
| Costo aproximado | Servidor ~5–15 USD/mes + dominio | Sin costo si lo prestan | Sin costo (luz) + dominio |
| Cómo llega internet | Caddy saca el certificado HTTPS solo | Caddy si tiene IP pública; si no, Cloudflare Tunnel | Cloudflare Tunnel (no se abre ningún puerto) |
| Base de datos | MariaDB (Docker) | MariaDB (Docker) | SQLite (el archivo de siempre) |
| Si se apaga | Casi nunca: lo atiende el proveedor | Depende de sistemas | Nadie puede entrar hasta que se prenda |
| Instalación | `docker compose up -d` | `docker compose up -d` | `Prospectos.exe` + `cloudflared` |

**Recomendado: A.** Siempre encendido, respaldos fuera de la oficina y nadie depende de una PC.
En los tres casos se necesita un **dominio** (por ejemplo, pedir a sistemas `prospectos.udcm.mx`).

## 2. Opción A o B: servidor con Docker

Requisitos: Linux con [Docker](https://docs.docker.com/engine/install/) (incluye `docker compose`),
2 GB de RAM y 20 GB de disco.

1. **DNS:** apunta el dominio a la IP del servidor (registro A). Con Cloudflare Tunnel, no hace falta.
2. **Copia el proyecto** al servidor (`git clone` del repositorio) y entra a la carpeta.
3. **Configura:** `cp .env.ejemplo .env` y llénalo:
   - `DOMINIO=prospectos.udcm.mx`
   - `COMPOSE_PROFILES=https` (servidor con IP pública y puertos 80/443 abiertos) o `tunel` (detrás de un firewall).
   - `BD_CLAVE` y `BD_CLAVE_ROOT`: contraseñas largas (`openssl rand -base64 30`).
   - `ADMIN_CORREO` y `ADMIN_CLAVE`: el primer administrador (al entrar, el programa pide cambiar la contraseña).
   - Solo con `tunel`: `TUNEL_TOKEN` (ver abajo).
4. **Arranca:** `docker compose up -d --build`
5. **Entra:** `https://prospectos.udcm.mx/admin/`. Caddy tarda unos segundos la primera vez en sacar el certificado.

Con `COMPOSE_PROFILES=tunel` (servidor sin IP pública):
1. Cuenta gratis en Cloudflare con el dominio (o subdominio) administrado ahí.
2. Zero Trust → Networks → Tunnels → **Create a tunnel** (tipo Cloudflared) → copia el **token** a `TUNEL_TOKEN`.
3. En el túnel, **Public hostname**: el dominio → servicio `HTTP` → `app:8000`.

Comandos útiles (en la carpeta del proyecto):

```
docker compose logs -f app                                      ver qué está haciendo
docker compose exec app python lanzador.py crear_admin          otro administrador o restablecer contraseña
docker compose exec app python lanzador.py respaldo listar
docker compose exec app python lanzador.py respaldo crear
docker compose exec app python lanzador.py probar_google
```

**Actualizar a una versión nueva:** `git pull` y `docker compose up -d --build`. Antes de cambiar la base, el
programa guarda solo una copia «antes-de-actualizar».

## 3. Opción C: la PC de la oficina con Cloudflare Tunnel

1. Con el programa **cerrado**, agrega a `datos\config.json`: `"URL_PUBLICA": "https://prospectos.udcm.mx"`.
2. Instala [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
   y crea el túnel como en la opción B, pero con el servicio `HTTP` → `127.0.0.1:8000` (el `PUERTO` de config.json).
3. Instálalo como servicio para que arranque con la PC: `cloudflared service install <TOKEN>` (en Windows,
   en una terminal como administrador).
4. Abre `Prospectos.exe` como siempre. Ahora abre la dirección pública, y todos entran por ella.

La PC debe quedar **encendida, conectada a la corriente y con el programa abierto**. El programa evita que se
duerma sola, pero no evita apagones ni actualizaciones de Windows.

## 3 bis. Para presentar o probar: compartir por internet desde tu computadora (gratis)

Sin servidor, sin dominio y sin cuenta de Cloudflare. El programa y la base se quedan en tu computadora;
Cloudflare da un enlace `https://<palabras>.trycloudflare.com` para entrar desde cualquier computadora,
celular o tableta, en cualquier lugar. La base de datos **no** se publica: se entra con usuario y contraseña.

1. Instala cloudflared (una sola vez):
   - Windows, en PowerShell: `winget install --id Cloudflare.cloudflared` y abre una ventana nueva.
   - Mac: `brew install cloudflared`.
2. En el programa: **Configuración → Otras computadoras → Compartir por internet**.
3. Cierra el programa y vuelve a abrirlo. En la ventana aparece el enlace, y en **Otras computadoras** su QR.
4. Comparte el enlace o el QR. Con HTTPS real: los celulares no instalan certificados.

Límites: el enlace **cambia cada vez** que abres el programa y solo funciona mientras tu computadora esté
encendida con el programa abierto. Cloudflare lo ofrece para pruebas, sin garantía de servicio. Para el uso
diario de Admisiones, usa las opciones A, B o C.

## 4. Pasar los datos que ya tienen

Los correos y teléfonos están **cifrados con las llaves de `config.json`**. El servidor debe usar el
**mismo** `config.json` que la PC donde están los datos; si no, esos datos quedan ilegibles.

Opción A o B (Docker), con el programa de la PC **cerrado**:

```
docker compose stop app
docker compose cp datos/config.json app:/datos/config.json
docker compose cp datos/prospectos.sqlite3 app:/datos/prospectos.sqlite3
docker compose run --rm app python lanzador.py pasar_a_mariadb --si
docker compose up -d
```

`pasar_a_mariadb` copia todo (usuarios, prospectos, respuestas, seguimientos, bitácora) y compara los
conteos. Copia también, si existen, `logo.png`, `hoja-membretada.jpg` y los archivos de Google
(`google-service-account.json`, `google-oauth-cliente.json`, `google-token.json`) con `docker compose cp`.
Después deja de usar el programa de la PC: si alguien sigue capturando ahí, eso no llega al servidor.

Opción C: no hay nada que pasar, los datos ya están en esa PC.

## 5. Las demás computadoras, celulares y tabletas

- **Con el navegador:** abrir la dirección y guardarla en favoritos. Chrome y Edge permiten instalarla
  como app (icono de instalar en la barra de direcciones).
- **Con el icono de Prospectos.exe / Prospectos.app:** la primera vez pregunta el papel de la computadora:
  elige **C · Conectarme** y escribe la dirección completa del servidor (`https://prospectos.udcm.mx`). Con su
  certificado HTTPS real no hay código que comparar; desde entonces el icono solo abre el servidor (queda en
  `datos/conexion.json`, sin base propia). Para cambiarla: `Prospectos.exe conectar`.
- **Celulares y tabletas:** en Configuración → **Otras computadoras** hay un QR. Con HTTPS real **no hay que
  instalar certificados**: se entra y se agrega a la pantalla de inicio (iPhone: Compartir → Agregar a
  inicio; Android: ⋮ → Instalar app). Ver [Teléfonos y tabletas](moviles.md).

## 6. Respaldos en el servidor

- Diarios y automáticos, como siempre (con MariaDB: `mariadb-dump`), en el volumen `datos` → `/datos/respaldos`.
- **Sácalos del servidor** regularmente: `docker compose cp app:/datos/respaldos ./respaldos-servidor`.
- Guarda `config.json` (`docker compose cp app:/datos/config.json .`) **aparte** de los respaldos, en un
  lugar seguro: sin él los respaldos no sirven, y con él cualquiera podría leerlos.
- El proveedor de la nube suele ofrecer instantáneas del disco (snapshots); actívalas como segunda copia.

## 7. Seguridad (el programa ahora está en internet)

Ya incluido:
- Solo HTTPS; el navegador recuerda que el dominio es solo HTTPS (HSTS, 30 días) y las cookies de sesión
  solo viajan cifradas.
- La base de datos no se publica: solo el programa llega a ella por la red interna de Docker.
- El programa ve la **IP real** de cada persona (no la del proxy): el bloqueo tras 5 contraseñas
  equivocadas y la bitácora funcionan por persona.
- Sesión que se cierra a los 30 minutos sin uso, contraseñas de 12+ caracteres, roles y bitácora, como antes.
- Si dos procesos usan la misma base (por error, o dos copias del servidor), solo uno corre las tareas
  automáticas: no se duplican importaciones ni respaldos.

Recomendado antes de usarlo con datos reales:
- **Segundo factor:** con Cloudflare (opciones B y C) se puede poner **Cloudflare Access** delante, gratis
  hasta 50 usuarios: antes de ver el programa, cada quien confirma con un código que llega a su correo
  institucional. El programa todavía no tiene segundo factor propio.
- **LFPDPPP:** los datos de aspirantes, muchos menores, quedan en un servidor de un tercero (opción A).
  Que jurídico lo revise: aviso de privacidad (transferencia/remisión al proveedor) y contrato con él.
- Que solo los administradores tengan acceso al servidor y al archivo `.env`.

## Variables de entorno (referencia)

| Variable | Para qué |
|---|---|
| `PROSPECTOS_URL_PUBLICA` | Dirección con la que entra todo el mundo (`https://…`). Equivale a `URL_PUBLICA` en config.json. |
| `PROSPECTOS_PROXY_CONFIABLE` | IP del proxy con HTTPS cuyos encabezados `X-Forwarded-*` se creen. `*` solo si el puerto del programa no está expuesto (Docker). |
| `PROSPECTOS_ESCUCHAR` | Dirección y puerto internos (`0.0.0.0:8000`). |
| `PROSPECTOS_BD_MOTOR`, `_HOST`, `_PUERTO`, `_NOMBRE`, `_USUARIO`, `_CLAVE`, `_BIN` | Base de datos (sustituyen a `BASE_DATOS` de config.json). |
| `PROSPECTOS_ADMIN_CORREO`, `PROSPECTOS_ADMIN_CLAVE` | Primer administrador, solo si no hay usuarios. |
| `PROSPECTOS_DATOS` | Carpeta de datos (`/datos` en Docker). |
