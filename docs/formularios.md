# Configurar los Google Forms

Hay dos formas de que el programa lea los Forms. Empieza por la **A**; si al compartir el Form
Google dice que no se puede compartir fuera de la organización, usa la **B**.

## 1A. Cuenta de servicio (recomendada)

1. En <https://console.cloud.google.com> crea un proyecto (p. ej. `admisiones-prospectos`).
   Usa una cuenta institucional, no personal, para que el proyecto no dependa de una persona.
2. **APIs y servicios → Biblioteca → «Google Forms API» → Habilitar.**
3. **IAM y administración → Cuentas de servicio → Crear.** No le asignes roles del proyecto.
4. En la cuenta creada: **Claves → Agregar clave → Crear clave nueva → JSON**. Guarda el archivo como
   `C:\Prospectos\datos\google-service-account.json`. (Si Windows oculta las extensiones y quedó
   `google-service-account.json.json`, el programa también lo encuentra.)
5. Copia el correo de la cuenta (`algo@proyecto.iam.gserviceaccount.com`).
6. En **cada** Form: botón **⋮ → Agregar colaboradores** → pega ese correo. Google Forms solo permite
   colaboradores con permiso de **edición** (no existe «solo lectura»); el programa únicamente pide
   permisos de lectura (`forms.body.readonly` y `forms.responses.readonly`), así que no puede modificar el Form.

> La llave JSON es una credencial: no la mandes por correo ni la subas a un repositorio.
> Si se filtra, revócala en la consola y genera otra.

## 1B. Cuenta institucional con OAuth (si la universidad bloquea compartir fuera del dominio)

Los correos de cuentas de servicio terminan en `iam.gserviceaccount.com`; muchas cuentas de Google
Workspace de universidades no dejan compartir con ellos. En ese caso:

1. En el mismo proyecto de Google Cloud: **APIs y servicios → Pantalla de consentimiento de OAuth** →
   tipo **Interno** (solo cuentas de la universidad) → nombre «Prospectos».
2. **Credenciales → Crear credenciales → ID de cliente de OAuth → App de escritorio** → Descargar JSON.
   Guárdalo como `C:\Prospectos\datos\google-oauth-cliente.json`.
3. En la carpeta del programa (clic derecho → *Abrir en Terminal*):
   ```
   .\Prospectos.exe conectar_google
   ```
   Se abre el navegador: entra con la cuenta **dueña o editora** de los Forms y acepta. El permiso se
   guarda en `datos\google-token.json` (trátalo como una contraseña) y `config.json` queda con
   `"GOOGLE_MODO": "oauth"`.
4. Si esa persona deja la universidad o le quitan acceso a los Forms, la importación se detiene:
   repite el paso 3 con otra cuenta. Por eso la opción A es preferible cuando se puede.

## 2. Registrar cada Form

**Forma rápida (recomendada):** en la terminal, con la URL de **edición** del Form
(`https://docs.google.com/forms/d/<ID>/edit`):

```
.\Prospectos.exe registrar_formulario alumno "https://docs.google.com/forms/d/XXXX/edit"
.\Prospectos.exe registrar_formulario tutor  "https://docs.google.com/forms/d/YYYY/edit"
.\Prospectos.exe probar_google
```

`registrar_formulario` lee el Form y llena solo el nombre, la URL pública, el **mapeo** (qué pregunta
es qué código) y los `entry.NNNN` de los campos del QR, leídos de la página pública del Form.
`probar_google` comprueba credenciales, acceso, cuántas respuestas hay, el mapeo y que los `entry.NNNN`
existan de verdad.

**Desde el panel:** **Configuración → Formularios de Google → Agregar**: pega la URL de edición en
*ID del Form*, elige el tipo y guarda; luego selecciónalo → acción **Sincronizar con Google**.

En ambos casos, después:

1. **Revisar mapeo** (en la lista de formularios): confirma que cada pregunta apunte al código
   correcto. Las preguntas sin mapear se guardan en la respuesta original (cifrada) pero no se usan.
2. Si un `entry.NNNN` aparece como «deducido» (el Form pide iniciar sesión y no se pudo leer la
   página pública), compruébalo: menú ⋮ del Form → **Obtener enlace prellenado** → escribe `X` en los
   tres campos de uso interno → **Obtener enlace** → la URL trae `entry.123456=X`; corrige
   *Campos prellenados* si no coincide.
3. Selecciona el formulario → **Importar ahora**. En adelante se importa solo cada minuto mientras el
   programa esté abierto. La primera importación trae **todas** las respuestas históricas del Form.

### Qué hace el programa con tu Form

- **«Carrera» y «Modalidad» aparecen dos veces** (una en la sección de Cuautitlán y otra en la de
  Tultepec): las dos van al mismo código. El mapeo lo permite solo para esas dos.
- **Preparatoria en texto libre:** si lo que escribe el alumno se parece a una prepa ya registrada
  (ignorando «Escuela», «Preparatoria», «Oficial», «No.», acentos…), se asigna a esa; si no, se da
  de alta **sola, marcada «por revisar» y sin ubicación**. En **Preparatorias** une las repetidas
  (acción «Unir») y en **Mapa → Ubicar** ponlas en el mapa. Lo que se une se recuerda: la próxima
  vez que alguien la escriba igual, cae sola.
- **Edad en texto libre:** se toma el primer número («17 años» → 17). «diecisiete» no se entiende y
  se trata como menor hasta confirmarlo.
- **Carrera «Otro»:** se conserva lo que escribió (se ve como «Otra: …») pero no cuenta como carrera.
- Si permites «Editar después de enviar», la edición **actualiza** la respuesta (no la duplica).

## 3. Lo que le falta a tu Form (en orden de importancia)

| # | Agregar | Por qué | Cómo |
|---|---|---|---|
| 1 | **Aviso de privacidad**: «He leído y acepto el aviso de privacidad» (Sí / No), con el enlace al aviso en la descripción | Sin esto **nadie** queda «Lista para usar» (salvo que un administrador active en *Reglas de permiso* que el aviso ya se muestra en el Form). | Opción múltiple, obligatoria, en DATOS PERSONALES. |
| 2 | **Validación de la edad** | Hoy es texto libre: «diecisiete» o «17 y medio» obligan a revisar a mano. | ⋮ de la pregunta → *Validación de respuesta* → Número → entre 12 y 99. |
| 3 | **Nombre y teléfono de mamá, papá o tutor** (opcionales) | La mayoría de 6.º semestre tiene 17 años: sin el permiso del tutor no se pueden usar. Con su teléfono, el asesor pide el permiso y lo registra en la respuesta. | Dos preguntas de respuesta corta. Códigos `tutor_nombre`, `tutor_telefono`. |
| 4 | **Código de evento** (respuesta corta; se llena sola con el QR del evento) | Sin ella el programa asigna cada respuesta al evento **por preparatoria y fecha** (funciona, pero si el alumno escribe mal su prepa o contesta otro día, se pierde). Con ella cuenta el QR exacto, y los **QR permanentes por prepa** la identifican aunque no haya evento. | Sección final «Uso interno — no modificar». Código `evento`. Después: en el Form, ⋮ → *Obtener vínculo prellenado*, escribe `EV000` en esa pregunta, copia el enlace y pégalo en Formularios → *Campos prellenados* para que el programa sepa su `entry.NNNN`. |
| 5 | **CURP** (opcional): «Tu CURP» en el del alumno y «CURP del aspirante» en el de padres | De la CURP sale la **edad exacta** (la regla de menores ya no depende de lo que escriban) y une alumno y familia **con certeza**. No se consulta a RENAPO: solo se valida y se lee lo que la clave trae dentro. | Respuesta corta con validación *Expresión regular → Coincide con* `[A-Za-z]{4}\d{6}[HMXhmx][A-Za-z]{5}[A-Za-z0-9]\d`. Códigos `curp`, `curp_aspirante`. **Agrégala al aviso de privacidad** (es un dato que identifica a la persona). |

Si agregas preguntas, en el panel ve a **Formularios → selecciona el Form → «Sincronizar con
Google»**: re-mapea y **reacomoda las respuestas ya importadas** sin pedir nada nuevo a Google.

## 4. Preguntas y opciones de tu Cuestionario Vocacional

El **código** es el identificador estable que usa el sistema: no lo cambies.

| Pregunta en tu Form | Tipo | Opciones | Código |
|---|---|---|---|
| Nombre completo | Respuesta corta | — | `nombre_completo` |
| ¿Cuál es tu edad? | Respuesta corta | — | `edad` |
| Teléfono | Respuesta corta | — | `telefono` (cifrado) |
| Correo electrónico | Respuesta corta | — | `correo` (cifrado) |
| ¿En qué preparatoria estudias? | Respuesta corta | texto libre | `preparatoria` |
| ¿En qué plantel te gustaría estudiar? | Opción múltiple | Universidad de Cuautitlán México · Universidad de Tultepec | `plantel` |
| ¿Qué carrera te gustaría estudiar? (sección Cuautitlán **y** sección Tultepec) | Casillas + Otro | Las del plantel · Aún no lo sé | `carrera` |
| ¿Qué modalidad de estudio prefieres? (ambas secciones) | Opción múltiple | Semanal · Sabatino · Dominical (solo Cuautitlán) · Aún no lo sé | `modalidad` |
| ¿Qué es lo más importante para ti al elegir una universidad? | Casillas (máx. 2) | Colegiaturas accesibles · Becas y descuentos · Horarios flexibles · Cercanía a mi domicilio · Calidad educativa · Oportunidades laborales | `factor_eleccion` |
| ¿Qué te gustaría conocer sobre la Universidad? | Casillas (máx. 2) | Carreras disponibles · Becas y descuentos · Costos y colegiaturas · Horarios · Requisitos de inscripción · Instalaciones | `quiere_conocer` |
| ¿Te gustaría recibir información sobre nuestras carreras y beneficios? | Opción múltiple | Sí, por WhatsApp · Sí, por correo electrónico · No, gracias | `recibir_informacion` |

**Ojo con dos detalles del Form actual:** dice «¿Qué carrera te **gastaría** estudiar?» e «**Ingeniera**
Industrial». El programa los entiende igual, pero los alumnos los ven: conviene corregirlos.

> **«No, gracias»** significa que no quiere que lo contacten: el aspirante cuenta en reportes, pero
> **no** entra a «A quién llamar hoy», no recibe el correo de bienvenida y no genera tareas.

## 5. Encuesta para padres de familia

Regístrala igual: `registrar_formulario tutor "https://docs.google.com/forms/d/1BCtE0gVnEPGF-nNZw5ePRhsyeaOpgdHzoLoWNwf8UvI/edit"`.

| Pregunta en la encuesta | Código | Cómo se usa |
|---|---|---|
| ¡AVISO DE PRIVACIDAD! (casilla «He leído y acepto…») | `consentimiento_aviso_privacidad` | **Da el permiso** para usar los datos del menor, en cuanto la encuesta se enlaza con la del alumno. |
| Nombre completo del padre, madre o tutor | `tutor_nombre` | Ficha. |
| Nombre completo del aspirante | `nombre_aspirante` | **Es lo único que la une con el alumno** (ver abajo). |
| Teléfono / Correo del padre, madre o tutor | `tutor_telefono`, `tutor_correo` (cifrados) | Contacto con la familia. |
| ¿Qué plantel te gustaría estudiar? | `plantel` | Se compara con el del alumno. |
| ¿Qué carrera le interesa estudiar a su hijo(a)? (dos secciones) | `carrera` | Se compara con el alumno. «Administración.» se toma como Administración de Empresas e Innovación de Negocios. |
| ¿Qué modalidad … consideran más conveniente? (dos secciones) | `modalidad` | **Escolarizada se toma como Semanal** del alumno, Sabatina = Sabatino. |
| ¿Qué tipo de universidad están considerando? | `tipo_universidad` | Ficha y reportes. |
| ¿Qué aspectos consideran más importantes…? | `factor_eleccion` | Grupos «Busca beca o precio» / «Horario flexible». |
| ¿Cuál es su principal preocupación…? | `preocupacion` | Costos → «Busca beca o precio»; horarios → «Horario flexible». |
| ¿Qué tipo de apoyo económico…? | `apoyo_economico` | Becas, descuentos, facilidades o financiamiento → «Busca beca o precio». |
| ¿Cuándo tienen previsto que ingrese…? | `cuando_ingresa` | «Próximo ciclo» suma prioridad; «un año» o «dos o más» → grupo «Entraría en un año o más». |
| ¿Cuál es el principal motivo por el que prefiere esta ubicación? | `motivo_ubicacion` | Ficha y reportes. |
| ¿Qué información le gustaría conocer…? | `quiere_conocer` | Requisitos/costos suman prioridad, igual que en el alumno. |
| ¿Le gustaría recibir información personalizada…? | `recibir_informacion` | «Sí» suma prioridad. Si el alumno dijo «No, gracias» pero la familia «Sí», **se contacta a la familia**. |

**Prioridad con la familia:** las reglas de la familia (pidió información, entra el próximo ciclo) solo
cuentan cuando la familia contestó. Quien solo tiene la respuesta del alumno no sale castigado; si la
familia dice que entraría «dentro de dos años», la prioridad baja, y eso es correcto.

### Cómo se une la encuesta de la familia con la del alumno

La encuesta no trae código de familia ni preparatoria, y los papás escriben el nombre del hijo distinto
(«Juan Pérez» contra «Juan Carlos Pérez López»). El programa suma indicios:

| Indicio | Puntos |
|---|---|
| Misma CURP, o la familia dio el correo/teléfono del alumno | seguro |
| El teléfono o correo del tutor es el que dio el alumno | +40 |
| Mismo nombre / el de la familia está contenido en el del alumno / muy parecido / parecido | +50 / +35 / +30 / +15 |
| Un apellido del tutor está en el nombre del alumno | +10 |
| Mismo evento / mismo día | +20 / +12 |
| Mismo plantel / misma carrera | +5 / +5 |
| Planteles distintos | −30 |

- **70 o más, y el segundo candidato al menos 20 abajo** → se unen solas al importar.
- **30 a 69** → van a **Familias por unir** (menú *Día a día*): se confirman con un clic, «Son la misma
  familia» o «No son». Ahí también se puede unir a mano buscando al alumno por nombre.
- Sin ningún parecido en el nombre ni en los contactos, no se propone nada (apellido + mismo día no bastan).

Mientras no se unan, **el permiso que dio la familia no llega al alumno**: el alumno menor sigue «Esperando
permiso». Por eso conviene revisar Familias por unir seguido.

**Lo que más ayudaría (agregar a la encuesta de padres):** una pregunta **«Correo o teléfono del aspirante»**
(respuesta corta, código `aspirante_contacto`). Con eso se une sola aunque el nombre venga mal escrito.
Es dato de contacto del menor: se guarda cifrado y solo se usa para unir.
