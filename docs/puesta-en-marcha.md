# Puesta en marcha: de la demo a tus datos reales

Sigue el orden. Cada paso dice cómo comprobar que salió bien antes de pasar al siguiente.

## Paso 0 · Dos carpetas: pruebas y real

| Carpeta | Para qué |
|---|---|
| `C:\ProspectosPrueba` | Probar con tus Forms y respuestas reales **sin compromiso**. Se puede borrar y empezar de nuevo. |
| `C:\Prospectos` | El sistema de verdad. Solo se arma cuando la prueba salió bien. |

Descomprime el zip en **ambas**. Cada carpeta tiene su propia `datos` (base, llaves, respaldos), así
que no se mezclan. Si abres las dos a la vez, la segunda usa otro puerto (8001): fíjate en la
dirección que muestra la ventana negra para saber cuál estás viendo. Lo más seguro es tener abierta
solo una.

## Paso 1 · Crear el administrador (en la carpeta de pruebas)

1. Doble clic en `C:\ProspectosPrueba\Prospectos.exe` → elige **A** → correo y contraseña.
2. Entra al panel. Debe verse el tablero vacío.

## Paso 2 · Conectar Google

Sigue [formularios.md](formularios.md), sección **1A** (cuenta de servicio). Si Google no te deja
compartir el Form con el correo `…iam.gserviceaccount.com`, usa la **1B** (OAuth).

✅ Comprobación: en la carpeta, clic derecho → *Abrir en Terminal*:

```
.\Prospectos.exe probar_google
```

Debe decir `1. Credenciales de Google ........ OK` (todavía no hay formularios registrados).

## Paso 3 · Registrar tu Form

```
.\Prospectos.exe registrar_formulario alumno "https://docs.google.com/forms/d/15yKpCaIUBX98tBvfdVcd7uqPXEppT6jfOjc9BSM2XgU/edit"
.\Prospectos.exe probar_google
```

(Si algún día crean un cuestionario para papás: `registrar_formulario tutor "URL"`.)

✅ Comprobación: `probar_google` muestra para cada Form `Acceso al Form … OK`, el número de
respuestas que ya tiene y `Mapeo … N/N`. Si dice **Códigos sin pregunta**, al Form le falta esa
pregunta o tiene otro texto: corrige el mapeo en el panel (**Formularios → Revisar mapeo**).

> El catálogo ya está hecho con **tu Cuestionario Vocacional**. Antes de usarlo en serio, agrégale
> lo de la sección 3 de [formularios.md](formularios.md) (sobre todo el **aviso de privacidad**).
> Después del primer arranque, ubica las preparatorias en **Mapa de cobertura → Ubicar**.

## Paso 4 · Importar y revisar con tus datos

1. Panel → **Formularios de Google** → selecciona ambos → **Importar ahora**.
2. Revisa, en este orden:
   - **Tablero:** ¿el número de prospectos se parece al de respuestas de alumno en tu Sheet?
   - **Prospectos → vista «Todos»:** los menores sin cuestionario del tutor aparecen **sin
     consentimiento** (cuarentena). Es correcto: no deben usarse hasta que el tutor consienta.
   - **Posibles duplicados:** cuántos quedaron por revisar. Si son muchas (más de ~20 % de los tutores), el
     problema son los nombres sin código de familia → usa tarjetas familiares en las próximas visitas.
   - **Abre 5 o 6 fichas** de aspirantes que conozcas: ¿las respuestas lado a lado son correctas?
     ¿el score y los segmentos tienen sentido? Si algo sale raro (carrera vacía, modalidad vacía), casi
     siempre es una opción del Form escrita distinto al catálogo.
3. Prueba un QR: **Eventos y QR → Agregar** (prepa, fecha, promotor) → **QR** → escanéalo con el
   celular. El Form debe abrir con *Código de evento* ya lleno. Contéstalo con datos de prueba y en
   ~1 minuto aparece en el tablero (con el programa abierto).

✅ Si todo cuadra, la prueba terminó. Si no, corrige y vuelve a empezar borrando
`C:\ProspectosPrueba\datos` (se pierde todo lo de esa carpeta; para eso es).

## Paso 5 · Pasar a real

1. Cierra la carpeta de pruebas.
2. Abre `C:\Prospectos\Prospectos.exe` → **A** → crea el administrador real.
3. Repite los pasos 2 y 3 en esta carpeta (copia `google-service-account.json` o
   `google-oauth-cliente.json` a `C:\Prospectos\datos`).
4. Importa. **Guarda una copia de `C:\Prospectos\datos\config.json` en un USB** y en el gestor de
   contraseñas de la institución.
5. Crea los usuarios reales: **Configuración → Usuarios → Agregar** y asígnales el rol (Admisiones,
   Promotor, Directivo). A los promotores ponles su *código de promotor* en el perfil.

## Paso 6 · (Opcional) MariaDB

Solo si necesitas la base en un servidor: [mariadb.md](mariadb.md). Requiere **MariaDB 10.11 o mayor**.
Para solo consultar los datos no hace falta: HeidiSQL y DBeaver abren `datos\prospectos.sqlite3`.

## Si algo falla

| Mensaje | Qué hacer |
|---|---|
| `HTTP 403` en *Estado* del formulario | El Form no está compartido con la cuenta de servicio (o la universidad lo bloquea → opción OAuth). |
| `HTTP 404` | Pegaste la URL **pública** (`/forms/d/e/…/viewform`); se necesita la de **edición** (`/forms/d/…/edit`). |
| `Falta autorizar la cuenta de Google` | Modo OAuth sin autorizar: `.\Prospectos.exe conectar_google`. |
| `entry.NNNN que NO existen en el Form` | Formularios → selecciona → **Sincronizar con Google**. |
| `La versión de MariaDB es demasiado vieja` | Necesitas 10.11+, o quita `BASE_DATOS` de `config.json` para volver a SQLite. |
