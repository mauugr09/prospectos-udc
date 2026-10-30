# Guía de operación para Admisiones

## Roles

| Rol | Puede | No puede |
|---|---|---|
| **Administrador** | Todo: usuarios, roles, formularios, reglas de prioridad, auditoría, respaldos. | Borrar prospectos (solo anonimizar). |
| **Coordinación** | Lo de Admisiones + preguntas y opciones, carreras, reglas de prioridad, sincronizar Forms y usuarios (no administradores). | Roles, administradores, auditoría, respaldos. |
| **Admisiones** | A quién llamar hoy, fichas con contacto, seguimiento, revisar posibles duplicados, exportar, eventos y catálogos. | Usuarios, auditoría, reglas de prioridad. |
| **Promotor** | Sus eventos, QR/tarjetas, modo en vivo, sus prospectos (contacto **enmascarado**). | Ver prospectos de otros, exportar, registrar seguimiento. |
| **Directivo** | Tablero, mapa y reporte ejecutivo (solo cifras agregadas). | Ver fichas o datos personales. |

> **¿Primera vez?** En el menú lateral, **Ayuda → ¿Cómo funciona?** explica el programa en una
> pantalla: el camino de una respuesta, qué significa cada estado, cómo se calcula la prioridad y
> las palabras que vas a ver. Al administrador, el **Inicio** le muestra una lista de *Primeros
> pasos* hasta que todo está configurado.

## «Contestaron y no aparece»

Abre **Respuestas de los Forms**. Ahí está *todo* lo que llegó, aunque todavía no se pueda usar,
con su estado en palabras simples:

| Estado | Qué significa | Qué hacer |
|---|---|---|
| **Lista para usar** | Ya está en Prospectos y en la cola. | Nada. |
| **Esperando permiso** | Menor de edad (o no dijo su edad) sin el cuestionario del tutor que acepta el aviso. | Que el tutor conteste su Form con el **código de familia** de la tarjeta. Si no llega en 30 días, se borra. |
| **Sin permiso** | No aceptó el aviso de privacidad. | Nada: no se puede usar. |
| **Borrada** | Venció la espera o se ejerció un derecho ARCO. | Nada. |

Si la respuesta **no está ni siquiera ahí**: el programa estaba cerrado (se pone al día al abrirlo)
o el Form tiene un error de conexión (aviso rojo en el Inicio).

Al abrir una respuesta se ven las preguntas **agrupadas por tema** (Su futuro, Lo que necesita,
Dinero y apoyo, Quién decide, Datos generales) con etiquetas cortas en lugar del texto largo de la
pregunta (pasa el mouse sobre la etiqueta para ver la pregunta original).

## Editar carreras, preguntas, opciones y usuarios

Todo está en **Configuración** (menú lateral). Lo que cambies ahí **ya no lo pisa el programa** al
abrirse ni al instalar una versión nueva.

| Qué | Dónde | Quién (por rol) |
|---|---|---|
| Carreras (nombre, área, planteles, otras formas de escribirla, apagar) | Configuración → Carreras | Administrador, Coordinación, Admisiones |
| Preguntas y sus opciones | Configuración → Preguntas y opciones | Administrador, Coordinación |
| Reglas de prioridad | Configuración → Reglas de prioridad | Administrador, Coordinación |
| Usuarios | Configuración → Usuarios | Administrador; Coordinación solo usuarios que no sean administradores |
| Roles (qué puede hacer cada rol) | Configuración → Roles | Solo Administrador |
| Tu propia contraseña | Ayuda → Cambiar mi contraseña | Todos |

**Carreras.** Si el Form escribe una carrera distinto («Ingeniera Industrial»), agrégalo en «Otras
formas de escribirla». Una carrera que ya no se ofrece se **apaga** (no se borra): los aspirantes que
la eligieron la conservan. Al guardar, las respuestas ya importadas se vuelven a leer.

**Preguntas.** Hay dos tipos:
- **Del sistema**: las usan las reglas de prioridad. Puedes cambiar su texto, su nombre corto, dónde se
  muestran y el texto de sus opciones; no puedes borrarlas ni cambiarles el tipo. Las opciones marcadas
  «Usada por las reglas» se pueden renombrar pero no borrar.
- **Agregadas**: las creas tú. Para agregar una pregunta: (1) créala en el Google Form, (2) créala aquí
  con el **mismo texto**, tipo y opciones, (3) en Formularios → «Sincronizar con Google». Aparece en la
  ficha, en las respuestas y en el reporte ejecutivo. *No suma puntos de prioridad*: eso requiere
  cambiar las reglas en el programa.

Si cambias el texto de una opción en el Form, cámbialo también aquí: el texto anterior se guarda solo
como «otra forma», así las respuestas viejas siguen contando.

**Usuarios.** Se crean en un paso: correo, nombre, rol y (opcional) código de promotor. La contraseña
temporal se muestra **una sola vez** al guardar: dásela en persona o por un medio privado. La persona
debe cambiarla al entrar. Los usuarios no se borran: se **desactivan** (acción en la lista), así su
historial y la bitácora conservan quién hizo qué. Al restablecer la contraseña de alguien, también se
le pide cambiarla al entrar.

## Preparatorias y mapa

Los alumnos escriben su prepa a mano. Las que no se parecen a ninguna registrada se dan de alta
solas como «por revisar» y **sin ubicación**:

1. **Preparatorias** → filtra «por revisar» → si dos son la misma escuela escrita distinto,
   selecciónalas → acción **«Unir»**. Los nombres quedan como alias: la próxima vez caen solas.
2. **Mapa de cobertura → Ubicar** (o el aviso «N prepas sin ubicar» del Inicio): elige la prepa,
   búscala por nombre o dirección, o haz clic donde está, y **Guardar**. El municipio se llena solo
   si hay internet.

El mapa muestra los 32 estados aunque no haya internet; con internet agrega calles y colonias
(de Google Maps si un administrador puso la llave en **Configuración → Mapa**; si no, de OpenStreetMap).

**Truco sin llave:** si el buscador no encuentra una escuela, búscala en Google Maps, haz clic derecho
sobre ella, haz clic en las coordenadas (se copian) y pégalas en el buscador de «Ubicar». También
funciona pegar el enlace largo de Google Maps; los enlaces cortos (maps.app.goo.gl) no.

**Cómo se lee el mapa de cobertura.** Cada círculo es una prepa: su tamaño y el número son los aspirantes con
permiso. Arriba se elige cómo colorearlos:

- **Respuesta:** qué parte de los alumnos de la prepa contestó (verde 15 % o más, ámbar 5–15 %, rojo menos de 5 %;
  gris si no se capturó cuántos alumnos tiene).
- **Última visita:** azul si ya hay una programada; verde si fue hace menos de 3 meses, ámbar de 3 a 12, rojo más de
  un año o nunca. Sirve para decidir a dónde ir.
- **Plantel:** el círculo se parte en azul (Cuautitlán) y rosa (Tultepec).

A la derecha está la lista con buscador. Al elegir una prepa se ve su ficha: respuesta, última y próxima visita,
distancia al plantel y botones para **programar visita**, **ver aspirantes** y el **QR permanente**.
Para ver los planteles y los anillos de 5, 10 y 15 km, un administrador pega sus coordenadas en
**Configuración → Mapa → Dónde están los planteles** (clic derecho sobre el plantel en Google Maps → clic en los números).

## Antes de usarlo con datos reales

Si al instalar elegiste la demostración, el Inicio muestra «Hay datos de demostración». Crea tu usuario administrador
real, entra con él y pulsa **Borrar**: se guarda un respaldo y se borran los prospectos, respuestas, eventos, prepas y
usuarios ficticios. Lo real no se toca.

Las explicaciones de cada pantalla están en **¿Cómo funciona?** (botón «Cómo se usa» junto a cada título).

## Calendario

**Visitas a preparatorias → Calendario** junta en un mes las visitas (punto de color según su estado: por
solicitar, solicitada, confirmada, realizada), las actividades del equipo (punto morado) y, en naranja, cuántas
llamadas vencen ese día (las vencidas se suman a hoy). Con **+** en un día se agrega una actividad (open house,
examen, inscripciones, junta…); clic sobre ella para cambiarla o quitarla. Las visitas se crean y cambian en
**Eventos y QR**. **Descargar .ics** sirve para pasarlo a Google Calendar u Outlook (es una copia: si algo cambia,
descárgalo otra vez).

## Antes de la visita (promotor / admisiones)

1. **Eventos y QR → Agregar evento**: preparatoria, fecha, promotor, meta de registros y costo. El código del
   evento se genera solo.
2. **Solicitud** (en la lista de eventos): la carta de «Difusión educativa» en la hoja membretada de la UDC, con la
   fecha, el horario y lo que se pide a la prepa. Quién firma (por omisión, Rectoría) se cambia arriba de la carta.
3. **Cartas de beca** (si se van a entregar): en el evento, sección «Cartas de beca para los alumnos», elige la carta
   (beca especial o regularización), el porcentaje, la vigencia y cuántas imprimir. En la lista aparece **Becas (N)**:
   imprime todas, o solo un rango de folios si se acabaron. Cada carta lleva un folio (`EV…-001`) para saber de qué
   evento viene cuando el alumno la presente.
4. En la lista de eventos: **QR** (general, para proyectar) y **Tarjetas** (una por alumno, con
   dos QR que comparten código de familia). Indica cuántas y presiona Imprimir.
5. Durante la visita abre **En vivo** en el proyector: contador, avance contra la meta y
   ranking de promotores del día. No muestra nombres.

> Las respuestas aparecen en **menos de 2 minutos** (el importador corre cada minuto) **siempre que
> el programa esté abierto en la PC de Admisiones**.

## Trabajo diario del asesor

1. Abre **A quién llamar hoy**. Está ordenada por **prioridad** (0–100) y, a igual prioridad, por
   quien lleva más tiempo sin contacto. Filtra "Asignados a mí", "Con tareas abiertas", por grupo o
   con diferencias alumno/tutor.
2. En la ficha revisa:
   - Arriba, tres tarjetas: si contestó el **alumno**, si contestó el **tutor**, y cuántas
     respuestas **coinciden** entre los dos (con el aviso concreto si algo no cuadra, p. ej. de
     quién depende económicamente).
   - Las respuestas **por tema, alumno y tutor en dos columnas**. Las que no coinciden se marcan
     en ámbar con «No coinciden»: si el alumno quiere Derecho y el tutor Ingeniería, la llamada es
     distinta. «No se le pregunta» significa que esa pregunta solo existe en el otro cuestionario.
   - Pestaña **Prioridad y grupos**: de dónde salen los puntos y los grupos (Listo para
     inscribirse, Sensible a beca, Riesgo de deserción…).
3. En la ficha, sección **Registrar contacto o nota**: tipo, fecha y notas; luego *Guardar*. El
   primer contacto real (llamada, WhatsApp, correo, visita) mueve al prospecto a *Contactado* y
   cierra las tareas automáticas. Una *nota interna* no cuenta como contacto.
4. **Estatus** (arriba en la ficha) conforme avanza: Contactado → Asistió a open house → Solicitó inscripción → Inscrito
   (o Descartado).
5. Si pasan **5 días sin contacto**, el sistema crea una tarea automática.

## Avisos (campanita)

- Arriba a la derecha. El número rojo son los avisos sin leer; al abrir uno se marca como leído.
- **Ver todos** → elegir qué avisos recibir. Los problemas del sistema solo les llegan a los administradores y no se apagan: si aparece «Falló el respaldo» o «No se pudieron traer las respuestas», atiéndelo el mismo día (ver «Si algo falla»).
- Las llamadas vencidas llegan como un aviso al día con la cifra; el detalle está en *A quién llamar hoy*.
- Se generan cada 5 minutos solo mientras el programa está abierto en la PC del sistema.

## Posibles duplicados (revisar al menos 2 veces por semana)

Aparecen cuando el sistema **no está seguro** de que dos respuestas sean de la misma familia
(nombre parecido pero incompleto, o tutor que contestó sin código de evento).

En **Posibles duplicados**, cada fila muestra la respuesta nueva y el prospecto existente (con enlace a
cada ficha). Selecciónala y elige la acción:
- **Es la misma persona: fusionar**: se conserva el prospecto existente y recibe todo el historial
  de la respuesta nueva.
- **Son personas distintas: rechazar**: se descarta la sugerencia.

Pistas: misma preparatoria, mismo apellido materno, si uno tiene solo alumno y el otro solo tutor.

**La mayoría vendrán de la Encuesta para padres**: el padre escribe el nombre del hijo incompleto
(«Ana López») y el sistema no adivina. Mientras no los unas, el permiso que dio la familia **no llega** al
alumno menor, que sigue «Esperando permiso». Revisa esta lista al menos dos veces por semana.
**Nunca** fusiones dos registros con códigos de familia distintos (el sistema lo impide).

## Permiso (aviso de privacidad) y «Esperando permiso»

- Un **menor de edad** solo se usa con permiso de su mamá, papá o tutor. Mientras tanto queda
  «Esperando permiso»: no aparece en la cola, ni en reportes, ni recibe correos. Si en **30 días**
  no hay permiso, sus datos se borran solos.
- **Cómo se obtiene sin cuestionario del tutor:** abre la respuesta en **Respuestas de los Forms** →
  «Pedir el permiso del tutor». Llama o escribe **solo para pedir el permiso**, explica el aviso, y si
  acepta registra nombre del tutor y medio (llamada, WhatsApp, en persona, por escrito). Queda tu
  nombre, la fecha y el medio en el historial y en la bitácora. Si después el alumno contesta «No» al
  aviso, gana el «No».
- Un **mayor de edad** da su propio permiso con la pregunta del aviso en el Form. Si el Form no la
  tiene pero muestra el aviso, un administrador puede activarlo en **Reglas de prioridad y de
  permiso** (decisión de jurídico; queda en la bitácora).
- Quien contesta **«No, gracias»** a recibir información no se contacta: no sale en la cola.

## Derechos ARCO (acceso, rectificación, cancelación, oposición)

- **Cancelación / oposición**: en la lista de prospectos (vista *Todos*), selecciona y usa la acción
  **Anonimizar (derecho de cancelación ARCO)**; pide escribir ANONIMIZAR. Es irreversible y
  conserva solo cifras agregadas.
- **Acceso**: busca por nombre, selecciona y usa **Exportar a Excel CON datos de contacto**;
  entrégalo por canal seguro.
- **Rectificación**: corrige en el Google Form (si la respuesta es editable) o pide a un admin.

## Exportaciones

- *Exportar*: sin datos de contacto.
- *Exportar con contacto*: solo con permiso de datos personales; **queda registrada** en la
  bitácora. El archivo se descarga a tu equipo: bórralo cuando termines y no lo reenvíes por
  correo personal ni WhatsApp.

## Si algo falla

| Síntoma | Qué revisar |
|---|---|
| No llegan respuestas | ¿Está abierta la ventana de Prospectos? Luego Formularios → columna *Estado* (y aviso en el tablero). Error 403 = el Form no está compartido con la cuenta de servicio. |
| Llegan pero sin carrera/modalidad | El texto de la opción en el Form no coincide con el catálogo. Corrige el Form o la carrera en Catálogos. |
| Un QR abre el Form sin el código | Revisa los `entry.NNNN` del formulario. |
| Muchas coincidencias por revisar | Usar tarjetas familiares y pedir al tutor que conteste con su QR. |
| "Windows protegió su PC" | El programa no está firmado: *Más información → Ejecutar de todas formas*. |
| El navegador dice que no se puede conectar | La ventana de Prospectos se cerró: vuelve a abrir `Prospectos.exe` (o Prospectos en Mac). |
| Mac: «No se puede verificar que Prospectos esté libre de malware» | Elige *Listo* y ve a Ajustes del Sistema → Privacidad y seguridad → *Abrir igualmente*. Solo la primera vez. |
| Mac: «Arrástralo a la carpeta Aplicaciones» | macOS lo abrió desde Descargas o desde la imagen de disco: muévelo a Aplicaciones y ábrelo desde ahí. |
| Desde otra computadora: «La conexión no es privada» | Falta instalar el certificado en esa computadora: abre `https://<IP>:8443/conectar/`. Si ya estaba instalado, ¿cambió la huella? Entonces alguien borró `datos/red/`: vuelve a instalarlo. |
| Desde otra computadora no abre nada | ¿Está abierto el programa en la computadora principal? ¿Cambió su IP? (Configuración → Otras computadoras muestra la actual). En Windows, permite a Prospectos en el firewall para *Redes privadas*. |
