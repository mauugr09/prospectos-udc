# Revisión de seguridad y LFPDPPP

> No es asesoría legal. La LFPDPPP se reformó en 2025: el área jurídica debe validar el aviso
> de privacidad, las finalidades y los plazos de conservación configurados aquí.

## Datos que se tratan

| Dato | Dónde | Protección |
|---|---|---|
| Nombre del aspirante y del tutor | `prospectos_prospecto` | En claro (necesario para enlazar y buscar). Se borra al anonimizar. |
| Correo y teléfono (aspirante y tutor) | `prospectos_prospecto` | **Cifrados** (Fernet: AES-128-CBC + HMAC-SHA256) + índice ciego HMAC-SHA256 para duplicados. Nunca en `respuestaitem` ni en el log. |
| Respuesta original de Google | `prospectos_respuesta.raw_json` | **Cifrada**. Se reemplaza por `{"anonimizado": true}` al purgar. |
| Respuestas económicas | `prospectos_respuestaitem` | Solo roles con acceso a fichas; reportes únicamente agregados. |
| Respuestas abiertas | `prospectos_respuestaitem` | Se borran al anonimizar. A la IA (si se activa) solo va el texto depurado de correos, teléfonos, URLs y números. |

## Controles implementados

**Programa**
- Por omisión escucha solo en `127.0.0.1` (no es accesible desde la red) y `ALLOWED_HOSTS` restringido.
- Con el acceso por red activo (Configuración → Otras computadoras, solo superusuario) abre además el puerto 8443
  **solo con HTTPS** (TLS 1.2 o mayor). El certificado lo firma una autoridad propia creada en `datos/red/`;
  su llave privada (`ca.key`) no sale de esa computadora y cada equipo confía en el certificado público
  (`ca.crt`) tras comparar su huella SHA-256. El certificado del servidor dura 397 días y se renueva solo.
  Las configuraciones viejas con `"ESCUCHAR_EN": "0.0.0.0"` ya no abren HTTP en claro: se convierten en HTTPS.
  Si alguien roba `ca.key` puede hacerse pasar por el programa ante los equipos que confían en él: la carpeta
  de datos se protege igual que `config.json`. Para revocar, borra `datos/red/` (se crea otra autoridad) y
  quita el certificado viejo de cada computadora.
- Sin CDN: Chart.js y Leaflet van dentro del programa. Solo salen a internet: Google (Forms API),
  el SMTP configurado, la IA si se activa y los mosaicos del mapa.
- Llaves generadas al primer arranque en `datos\config.json`; la del índice ciego debe ser
  distinta de la de cifrado (el programa lo verifica).
- Exportaciones a Excel con protección contra inyección de fórmulas.

**Accesos**
- Roles (grupos): Administrador, Admisiones, Promotor, Directivo, con permisos de Django.
- Promotores filtrados por consulta: no ven prospectos ni eventos ajenos.
- Datos de contacto **enmascarados siempre**; quien tiene permiso los revela con un botón y
  la consulta queda en bitácora.
- Contraseñas de 12+ caracteres, no comunes, no numéricas; sesión de 8 horas; cookies `HttpOnly`.
- **Bitácora de auditoría** de solo inserción (el modelo rechaza editar o borrar): ver ficha,
  ver datos de contacto, exportar (con o sin contacto), cambiar estatus, fusionar, rechazar
  coincidencias, anonimizar, generar tarjetas, cambios de scoring, usuarios, respaldos.
  Guarda nombres de campos e IDs, nunca valores personales.
- No se puede borrar un prospecto desde el panel: se anonimiza.

**Ciclo de vida del dato**
- Consentimiento por respuesta; válido el del tutor, o el del aspirante solo si es mayor de edad.
- Menor sin consentimiento del tutor: **cuarentena** (fuera de cola, reportes y correos) y purga a los `CUARENTENA_DIAS`.
- Consentimiento negado: purga en la siguiente corrida diaria.
- Inactividad: anonimización a los `RETENCION_MESES`.
- Anonimización manual por derecho ARCO (con confirmación escrita).
- Respaldo diario, rotación y **prueba de restauración semanal** (integridad + conteos).

## Riesgos abiertos (decisión de la institución)

1. **`datos\config.json` es la llave de todo.** Quien tenga ese archivo y un respaldo puede leer
   correos y teléfonos. Si se pierde, no se pueden leer nunca más. Guárdalo aparte de los respaldos.
2. **Disco de la PC sin cifrar.** Nombres y respuestas no van cifrados en la base. Activa
   **BitLocker** en esa computadora y usa una cuenta de Windows con contraseña, solo para Admisiones.
3. **Respaldos en el mismo disco.** Copia `datos\respaldos` a otro medio con frecuencia; si sale
   del edificio, cífralo (p. ej. un USB con BitLocker To Go).
4. **Una sola PC = punto único de falla y de acceso.** Si varias personas usan la misma cuenta de
   Windows, la bitácora del sistema distingue usuarios del panel, pero no a quién estaba sentado.
5. **Ejecutable sin firma.** No hay forma de que el usuario verifique que el .exe no fue alterado;
   distribúyelo solo desde un canal interno y conserva el hash SHA-256 publicado con cada versión.
6. **Correo de bienvenida a menores**: sale solo tras consentimiento del tutor. Revisa con jurídico
   si prefieren enviarlo únicamente al tutor.
7. **IA externa** (si se activa): aunque el texto se depura, es una transferencia a un tercero que
   debe declararse en el aviso de privacidad.

## Checklist antes de usarlo con datos reales

- [ ] Carpeta en `C:\Prospectos` (fuera de OneDrive), BitLocker activo en la PC.
- [ ] Datos de demostración borrados; administrador real creado con **A**.
- [ ] Copia de `datos\config.json` guardada fuera de la PC.
- [ ] Aviso de privacidad aprobado por jurídico y enlazado en ambos Forms.
- [ ] `Prospectos.exe respaldo crear` y `Prospectos.exe respaldo verificar` con resultado correcto.
- [ ] Copia externa de `datos\respaldos` programada (aunque sea manual, semanal).

## Agregado: MariaDB, OAuth y mapas

- **MariaDB:** usa un usuario exclusivo del programa con permisos solo sobre `prospectos` y
  `prospectos_verificacion`, y otro de **solo lectura** para consultas (ver [mariadb.md](mariadb.md)).
  La contraseña queda en `config.json`: protege ese archivo igual que las llaves.
- **Modo OAuth:** `datos\google-token.json` permite leer los Forms de la cuenta que lo autorizó.
  Trátalo como contraseña; si se filtra, revoca el acceso en <https://myaccount.google.com/permissions>.
- **Mapas:** el fondo se pide a Google Maps (si hay llave) o a OpenStreetMap, con coordenadas del mapa
  y solo el **origen** `http://127.0.0.1:8000` como Referer (las dos lo exigen; en el resto del programa
  no se manda). Nunca se envían datos de aspirantes. La llave de Google es de navegador: se ve en el
  código de la página, por eso **debe restringirse** a ese origen y a esas tres APIs, y conviene una
  alerta de presupuesto. La búsqueda de «Ubicar» envía solo lo que se escribe en el buscador.