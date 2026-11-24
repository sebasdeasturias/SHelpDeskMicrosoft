# Compromiso de servicio (SLA) — SHelpDesk

**Versión:** 0.1 — propuesta para ratificar
**Ámbito:** mesa de ayuda interna de TI (HelpDesk)
**Fecha:** 2026-10-06

Este documento define **qué promete la mesa de ayuda**, por prioridad y en
horario laboral, y sirve de contrato contra el que medir todo lo demás. La §9
confronta cada cláusula con lo que el software soporta hoy: una promesa que el
sistema no puede medir no es un compromiso, es una intención.

> Aplica por igual a `SHelpDeskMicrosoft` y a `SHelpDeskAlternativeDesign`: el
> backend y la base de datos son idénticos en ambos.

---

## 1. Objeto y alcance

Cubre las incidencias y peticiones registradas en el portal de HelpDesk por
personal interno, desde su registro hasta su resolución.

**Queda dentro:** incidencias de hardware, software, red y accesos gestionados
por TI. **Queda fuera:** peticiones que requieren compra o aprobación
presupuestaria, cambios de alcance de proyecto y soporte a terceros.

---

## 2. Horario de servicio

| | |
|---|---|
| Días laborables | lunes a viernes |
| Horas de servicio | **08:00 – 18:00** (Europe/Madrid) = 10 h/día, 50 h/semana |
| Fuera de horario | el portal **registra 24×7**, pero el reloj del SLA **no corre** |
| Festivos | calendario laboral oficial (nacionales y autonómicos) más los cierres publicados con ≥15 días de antelación |
| Indisponibilidad del propio HelpDesk | cuenta como festivo a efectos del reloj |

**Pendiente de ratificar:** el horario anterior es una propuesta. Si tu horario
real es otro, es un cambio de una línea en este documento — pero **cambia todos
los números de la §4** y obliga a recortar el compromiso en consecuencia.

---

## 3. Definiciones

- **Respuesta (R)** — primera intervención **humana** de un agente sobre el
  ticket: comentario público, asignación, o paso a `asignado`/`en_proceso`.
  **No cuenta** la clasificación automática de la IA ni el acuse de recibo del
  portal: eso es automatización, no atención.
- **Resolución (S)** — ticket en `resuelto` o `cerrado` con solución registrada.
- **Reloj** — suma de tiempo **dentro** del horario de servicio (§2).
- **Pausa** — mientras el ticket espera información del solicitante, el reloj se
  detiene y el tiempo no computa.
- **Incumplimiento** — R o S por encima del compromiso. Se mide por ticket y por
  periodo, desglosado por prioridad.
- **Prioridad** — la fija quien registra y la puede corregir el coordinador. La
  prioridad vigente es la que manda; **un cambio de prioridad recalcula el
  compromiso desde la fecha de creación**, no desde el cambio, para que subir la
  prioridad no sirva para perdonar un retraso ya acumulado.

---

## 4. Compromisos por prioridad

Los compromisos se expresan **en días hábiles**, que es lo que hace medible la
§2, y no en minutos sueltos a reloj corrido.

| Prioridad | Respuesta (R) | Resolución (S) | Vencimiento en calendario |
| --- | --- | --- | --- |
| **Crítica** | 15 min laborables | mismo día hábil | si entra a las 17:45, vence a las 08:15 del siguiente día hábil |
| **Alta** | 30 min laborables | mismo día hábil si entra antes de las 14:00 | si no, antes de las 12:00 del siguiente día hábil |
| **Media** | 1 h laborable | fin del siguiente día hábil | — |
| **Baja** | 2 h laborables | fin del segundo día hábil siguiente | — |

**Qué es una prioridad crítica:** servicio caído para más de una persona, pérdida
o riesgo de pérdida de datos, o un servicio de cara al cliente interrumpido. La
crítica la declara el agente, el coordinador o quien registre, y **el
coordinador puede degradarla** si no se sostiene.

### 4.1 Efecto de adoptar horario laboral

Los números de hoy están configurados como **minutos a reloj corrido**. Pasar a
reloj laborable **no es cosmético**: la misma cifra significa más tiempo real.
Sobre un día de 10 h frente a 24 h, el compromiso se relaja entre **×2,3 y ×2,4**
si no se recorta. Por eso la tabla de arriba está escrita en días hábiles y no
como minutos heredados: son la promesa, y las cifras anteriores quedan como
referencia en el Anexo B.

---

## 5. Escalado

| Prioridad | Aviso | Escalado |
| --- | --- | --- |
| Crítica | al superar el **75%** de R y de S | el ticket pasa a `escalado` si supera R; aviso al coordinador |
| Alta | al superar el 75% de S | aviso al coordinador en el informe diario |
| Media | — | informe diario |
| Baja | — | informe semanal |

Nadie escala por encima de dos niveles sin comunicarlo al coordinador.

---

## 6. Exclusiones

No computan contra el compromiso:

- el tiempo en **pausa** (§3) y el tiempo fuera de horario;
- tickets en `archivado` (archivar es limpieza del tablero, no revierte trabajo);
- duplicados, incidencias de prueba o de carga, y spam;
- peticiones fuera del alcance de §1;
- mantenimientos planificados y anunciados con antelación.

---

## 7. Medición y revisión

Informe **mensual** con, como mínimo:

1. cumplimiento de **R y de S desglosado por prioridad**;
2. tiempo medio de resolución;
3. tasa de reapertura;
4. satisfacción del solicitante (CSAT) al cierre;
5. backlog vencido y su antigüedad.

Revisión del contrato cada **trimestre**. Cualquier cambio de horario, de
compromiso o de exclusión se versiona en este documento.

---

## 8. Conformidad del software

Cada cláusula de este contrato, contra lo que el sistema soporta hoy. Sin esta
columna, el contrato prometería cosas que nadie puede medir.

| # | Cláusula | ¿Soportado? | Qué hay / qué falta |
| --- | --- | --- | --- |
| 1 | §2 reloj laboral (10 h/día, L–V, festivos) | **No** | El cálculo usa reloj corrido: `backend/coordinator.py:65-66`. No existe tabla de horario, festivos ni zona horaria. |
| 2 | §3 R = primera intervención humana | **No** | `solicitud` no tiene fecha de primera respuesta; solo `fecha_creacion`, `fecha_actualizacion` y `solucion`. **R es inmedible.** |
| 3 | §3 pausa por espera del solicitante | **No** | No existe estado de espera. Estados: `nuevo`, `asignado`, `en_proceso`, `escalado`, `resuelto`, `cerrado`, `archivado`. |
| 4 | §4 fecha límite por ticket | **No** | No hay columna de vencimiento. El compromiso no se materializa en ninguna parte. |
| 5 | §4 medición por prioridad | **No** | El cumplimiento es un **único agregado global** (`coordinator.py:57-74`, sin agrupar por prioridad). |
| 6 | §4 exactitud de la medición | **Parcial** | Usa `fecha_actualizacion`, que cambia con **cualquier** edición, no al resolver. Los instantes reales están en `historial`. |
| 7 | §5 aviso al 75% | **No** | No hay planificador (nada en `backend/main.py` ni en el compose) y no hay canal de notificación. |
| 8 | §5 escalado automático | **No** | `escalado` es estado válido (`backend/tickets.py:32,154`) pero **ningún control lo pone** y nada automático lo asigna. |
| 9 | §5 aviso al coordinador | **No** | El proyecto **no envía correo ni SMS**: cero librerías y cero secretos de proveedor en todo el repo. |
| 10 | §4/§5 SLA activo por prioridad | **Parcial** | Existe la columna `sla.activo`, pero el cálculo no la consulta: se aplica a todas las prioridades. |
| 11 | §3 prioridad y re-priorización | **Parcial** | Los 4 niveles y el cambio existen; no hay regla de recálculo del compromiso al cambiar de prioridad. |
| 12 | §6 excluir pruebas y duplicados | **No** | No hay filtro: los tickets de prueba se mezclan con los reales. |
| 13 | §7 informe con R y S por prioridad | **No** | Hay informes y exportación, pero no exponen R, ni S por prioridad. |
| 14 | §7 tasa de reapertura | **No** | No existe la reapertura. |
| 15 | §7 CSAT al cierre | **No** | No existe encuesta ni valoración. |
| 16 | §3 registro auditable | **Sí** | `historial` (transiciones con fecha, estado y usuario) y `log` (auditoría de acciones). |
| 17 | §4 niveles y tiempos configurables | **Sí** | Tabla `prioridad` y panel de SLAs; el panel guarda los minutos por prioridad. |

**Resumen:** 2 de 17 cláusulas están soportadas, 4 parcialmente y 11 no. El
registro auditable es sólido —lo que falta no es trazabilidad, es **medición**:
el sistema sabe qué pasó, pero no cuándo vencía.

### 8.1 Controles que prometen y no cumplen

Dos controles de la interfaz afirman cosas que el software descarta. Conviene
quitarlos o implementarlos, porque un control que no hace nada es peor que su
ausencia: entrena a confiar en él.

- **Los checkboxes de reglas del panel SLAs** (`dashboard-coordinador.html:600-667`,
  8 en total, 2 por tarjeta). Al guardar, el cliente lee **solo el primero** de
  cada tarjeta y lo almacena como `activo`; el segundo **nunca se envía**. Se
  descartan así: «Escalar al Coordinador automáticamente», «Notificación por
  correo al agente» y «Escalamiento automático» (×2). Y la llamada devuelve un
  toast verde de éxito.
- **El `activo` que sí se guarda tampoco se consulta** (fila 10): marcar o
  desmarcar ese checkbox no cambia ningún cálculo.

---

## Anexo A — la configuración viva contradice el seed

Los tiempos de respuesta sembrados en `database/db_logic.sql:299-303` **no
coinciden** con los de la base de datos en funcionamiento:

| Prioridad | Respuesta — seed | Respuesta — BD viva |
| --- | --- | --- |
| Crítica | 15 | 15 |
| Alta | **30** | **60** |
| Media | **60** | **120** |
| Baja | **120** | **240** |

La BD viva duplica los tiempos de respuesta de alta, media y baja. Los valores
operativos son los de la BD (**lo que la mesa está usando de verdad**); el seed
está desactualizado. **Hay que decidir cuál es la fuente de verdad** y alinear la
otra, porque hoy una base recién sembrada nacería con compromisos más estrictos
que la que está en producción.

---

## Anexo B — valores operativos actuales (referencia)

Tal como están configurados hoy, **en minutos a reloj corrido**:

| Prioridad | Respuesta | Resolución | SLA activo |
| --- | --- | --- | --- |
| Crítica | 15 min | 60 min | sí |
| Alta | 60 min | 240 min | sí |
| Media | 120 min | 480 min | sí |
| Baja | 240 min | 1440 min | sí |

Origen: tabla `prioridad` (columnas `tiempo_respuesta_min`, `tiempo_solucion_min`)
y tabla `sla` (`tiempo_resp_max`, `tiempo_sol_max`, `activo`), leídas vía
`GET /api/coordinator/sla`. Se conservan aquí solo como referencia: **la promesa
vigente es la tabla de §4.**

---

## Pendientes para que este contrato sea real

Por orden de dependencia:

1. **Ratificar §2 y §4** — horario y compromisos. Nada más se puede medir sin esto.
2. **Guardar la fecha de primera respuesta** al primer toque humano (habilita R, filas 2 y 6).
3. **Materializar el vencimiento** por ticket a partir de creación + compromiso, en horas laborables (habilita la fila 4).
4. **Un planificador** que evalúe vencimientos y marque incumplimiento (habilita las filas 1, 4, 7, 8).
5. **Un canal de notificación** — hoy no existe ninguno (fila 9).
6. **Desglosar el cumplimiento por prioridad** en informes (fila 5).
7. **Quitar o implementar los controles de §8.1**, empezando por los checkboxes que se descartan.
