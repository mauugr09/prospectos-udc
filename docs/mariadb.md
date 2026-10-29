# Usar MariaDB en lugar del archivo SQLite

## ¿Lo necesitas?

| Quieres… | Qué usar |
|---|---|
| **Ver o consultar** los datos con un programa (HeidiSQL, DBeaver) | **No necesitas MariaDB.** Abre `datos\prospectos.sqlite3` con HeidiSQL (*Tipo de red: SQLite*) o DBeaver (*SQLite*). Ábrelo en **solo lectura** o con el programa cerrado. |
| Que la base viva en un servidor de la universidad, con sus respaldos | MariaDB **10.11 o mayor** |
| Que varias computadoras usen el sistema a la vez | MariaDB + instalar el programa en un servidor (no en la PC de un asesor). Este paquete no lo resuelve por sí solo. |

En ambos casos los **correos y teléfonos se ven cifrados** (`gAAAAAB…`): es intencional. Solo el
programa, con las llaves de `datos\config.json`, los descifra.

## Versión requerida: 10.11 o mayor (10.3 NO funciona)

Django, el marco del sistema, exige **MariaDB 10.11+**. MariaDB 10.3 dejó de recibir parches de
seguridad en mayo de 2023 y 10.4 en junio de 2024. Si el programa detecta una versión menor, se
detiene con un mensaje en español. Recomendado: **MariaDB 11.4 LTS** o **10.11 LTS**.

> XAMPP trae MariaDB 10.4: tampoco sirve. Instala MariaDB por separado (instalador MSI de
> mariadb.org, servicio de Windows) o pide una base al área de sistemas.

## 1. Crear la base y el usuario

En HeidiSQL o en la consola `mariadb -u root -p`:

```sql
CREATE DATABASE prospectos CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'prospectos'@'localhost' IDENTIFIED BY 'una-contraseña-larga-y-única';
GRANT ALL PRIVILEGES ON prospectos.* TO 'prospectos'@'localhost';
-- Para la verificación semanal de respaldos (carga el respaldo en una base temporal):
GRANT ALL PRIVILEGES ON `prospectos_verificacion`.* TO 'prospectos'@'localhost';
FLUSH PRIVILEGES;
```

Si MariaDB está en otro equipo, cambia `'localhost'` por la IP de la PC de Admisiones y abre el
puerto 3306 **solo** a esa IP en el firewall del servidor.

## 2. Configurar el programa

Con el programa **cerrado**, edita `datos\config.json` y agrega (respetando comas):

```json
"BASE_DATOS": {
  "MOTOR": "mariadb",
  "HOST": "127.0.0.1",
  "PUERTO": 3306,
  "NOMBRE": "prospectos",
  "USUARIO": "prospectos",
  "CLAVE": "una-contraseña-larga-y-única",
  "BIN": "C:\\Program Files\\MariaDB 11.4\\bin"
}
```

`BIN` es la carpeta donde están `mariadb.exe` y `mariadb-dump.exe` (se usan para los respaldos).

## 3. Pasar los datos que ya tienes

```
.\Prospectos.exe pasar_a_mariadb
```

Copia **todo** lo de `datos\prospectos.sqlite3` a MariaDB (usuarios, prospectos, respuestas,
seguimientos, bitácora) y compara los conteos al final. **Borra lo que hubiera en la base MariaDB.**
El archivo SQLite no se toca: queda como respaldo. Después abre `Prospectos.exe` normalmente.

## 4. Respaldos con MariaDB

Los respaldos automáticos (diarios) usan `mariadb-dump --single-transaction` (no bloquea) y se guardan
en `datos\respaldos\prospectos-AAAAMMDD-HHMMSS.sql.gz`. La verificación semanal los carga en
`prospectos_verificacion`, cuenta filas y borra esa base. Comandos:

```
.\Prospectos.exe respaldo crear
.\Prospectos.exe respaldo verificar
.\Prospectos.exe respaldo restaurar prospectos-20261028-023000.sql.gz   (con el programa cerrado)
```

Si el servidor ya tiene su propio esquema de respaldos, mantenlo: estos son una segunda copia.

## 5. Acceso con HeidiSQL o DBeaver

- **Red:** MariaDB (TCP/IP) · **Host:** el de `BASE_DATOS.HOST` · **Puerto:** 3306.
- **Usuario de consulta (recomendado):** no uses el usuario del programa para consultar. Crea uno
  de solo lectura:
  ```sql
  CREATE USER 'consulta'@'localhost' IDENTIFIED BY 'otra-contraseña';
  GRANT SELECT ON prospectos.* TO 'consulta'@'localhost';
  ```
- **No modifiques datos a mano.** Los campos calculados (score, segmentos, consentimiento) y la
  bitácora de auditoría se rompen; cambia las cosas desde el panel.
- Tablas principales: `prospectos_prospecto`, `prospectos_respuesta`, `prospectos_respuestaitem`
  (una fila por respuesta a cada pregunta; `codigo` y `valor_normalizado`), `prospectos_seguimiento`,
  `prospectos_evento`, `prospectos_preparatoria`, `prospectos_auditoria`.
