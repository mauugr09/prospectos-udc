# Autoría y protección de «Prospectos»

> **Esto no es asesoría legal.** Es una guía para que lleguen preparados con un abogado o con la
> oficina de propiedad intelectual. Antes de firmar algo con la UDC, que lo revise un abogado.

## La situación

- El programa lo hicieron **dos personas**, que publican como **NullSpace Studio**.
- Lo hicieron durante su **servicio social** en la Universidad de Cuautitlán. A ustedes les pidieron
  un Google Forms; el sistema completo fue iniciativa suya.
- Según la Ley Federal del Derecho de Autor, la protección **nace al crear la obra**, sin registrarla
  (art. 5). El registro ante INDAUTOR no da el derecho: sirve como **prueba** de quién y cuándo, y es lo
  que importa si hay un desacuerdo.

## Antes de presentarlo: tres cosas que pueden cambiarlo todo

1. **El reglamento y el convenio de servicio social.** Algunas instituciones dicen que lo que se produce
   durante el servicio social es de ellas. Pidan el reglamento de servicio social de la UDC y su carta de
   asignación, y busquen «propiedad intelectual», «derechos de autor» u «obras». Si alguno dice que es
   de la UDC, **no pueden registrarlo a su nombre** sin un acuerdo previo. Lo mismo si usaron equipo de la UDC.
2. **Un acuerdo por escrito entre ustedes dos.** Es la parte incómoda, y por eso se omite. Debe decir qué
   porcentaje es de cada quien, quién puede firmar licencias, cómo se reparte lo que se cobre y qué pasa
   si uno ya no quiere seguir. Sin acuerdo, la ley los trata como coautores en partes iguales y cada
   decisión importante necesita a los dos.
3. **NullSpace Studio no es una persona legal.** Mientras no sea una empresa constituida, los titulares
   son ustedes dos con sus nombres completos. «NullSpace Studio» se puede usar como marca en la pantalla,
   la licencia y los manuales, pero el registro va con sus nombres. Llénenlos en el archivo `AUTORES`.

## Registro ante INDAUTOR (programa de cómputo)

Trámite «Registro de obra», rama **programa de computación**, en ventanilla o en línea (gob.mx → INDAUTOR).

Lo que normalmente se pide (confirmen en gob.mx, porque los formatos y la cuota cambian):

- **Solicitud de registro de obra** (formato RPDA-01), más el anexo de datos de cada coautor.
- **Datos de cada autor:** nombre completo, CURP, nacionalidad, domicilio, identificación oficial y
  porcentaje de participación. Los nombres deben ser **idénticos** en todos los documentos.
- **Ejemplar de la obra:** para software se acostumbra entregar las **primeras y últimas 10 páginas del
  código fuente** (así no se expone todo), más una descripción breve de 5 a 10 renglones y, si se quiere,
  el manual. Esto lo pide, por ejemplo, la guía de la UNAM para sus registros.
- **Pago de derechos** según la Ley Federal de Derechos vigente. La cuota se actualiza cada año: consulten
  el monto en la página del trámite antes de pagar.
- **Título:** «Prospectos». Fecha de terminación: la de la versión que registren (1.0.0, octubre de 2026).

Qué protege y qué no:
- Protege **el código y la forma de expresarlo** (pantallas, textos, documentación).
- **No protege la idea** de «un sistema de prospectos con QR y Google Forms». Otra persona puede hacer
  algo parecido con su propio código.

## La marca «NullSpace Studio» (opcional)

El nombre se registra aparte, ante el **IMPI**, normalmente en las clases 9 (software) y 42 (desarrollo
de software). Conviene buscar antes que nadie lo tenga. No urge para presentar el sistema.

## Cómo entregarlo a la UDC: licencia de uso, no venta

Para que ustedes sigan siendo dueños, la UDC no lo compra: recibe una **licencia de uso**. Puntos que
debe tener el contrato:

| Tema | Qué decidir |
|---|---|
| Alcance | Solo la UDC, solo para Admisiones, ¿cuántas computadoras o planteles? |
| Duración | Un año renovable, o indefinida |
| Exclusividad | **No exclusiva**: así pueden ofrecerlo a otras escuelas |
| Precio | Gratuita (como parte del servicio social) o con pago; y el soporte aparte |
| Soporte y actualizaciones | Quién arregla fallas, en cuánto tiempo y cuánto cuesta |
| Datos personales | La UDC es **responsable** de los datos de aspirantes; el programa corre en su computadora y ustedes no los ven. Si dan soporte con acceso a esa PC, se firma un acuerdo de confidencialidad. |
| Continuidad | Si ustedes dejan de dar soporte, ¿la UDC recibe el código para que otra persona lo mantenga? Un **depósito del código** (con un notario o en un sobre cerrado con condiciones) responde la pregunta del rector «¿y si se van?» sin regalar el código hoy. |
| Marca de la UDC | El logo y la hoja membretada son de la UDC: ustedes no pueden usarlos fuera de ese contrato |

## Lo que ya está hecho en el programa

- `LICENSE`: licencia propietaria, todos los derechos reservados.
- `AUTORES`: lista de titulares, con espacios para sus nombres completos.
- `AVISOS-TERCEROS.md`: licencias de las librerías que usa el programa. Todas permiten un programa propietario.
- Las propiedades de `Prospectos.exe` en Windows dicen «NullSpace Studio» y «© 2026».
- «¿Cómo funciona?» → **Acerca de** muestra versión, autoría y licencias.
- El repositorio de GitHub debe ser **privado**. Fue público hasta octubre de 2026: cualquiera pudo
  descargar una copia. Eso no les quita la autoría, pero por eso conviene registrar pronto.

## Lo que NO protege

- **Ocultar o «cifrar» el código del .exe.** Un programa de Python empaquetado se puede descompilar en
  minutos. La protección real es **el contrato más el registro**, no esconder el código.
- **Mostrar el sistema con el logo de la UDC** en un portafolio o a otra escuela. Quiten antes la marca
  de la UDC (Configuración → Apariencia, y la hoja membretada).

## Fuentes

- Ley Federal del Derecho de Autor, arts. 5, 13, 101 a 114 (programas de computación).
- [Requisitos de registro de programas de cómputo (UNAM, FES Cuautitlán)](https://www.cuautitlan.unam.mx/propiedad_intelectual/descargas/07.pdf)
- [Cambios a los formatos de INDAUTOR (National Law Review, 2022)](https://natlawreview.com/article/new-formats-mexican-copyright-office-indautor)
