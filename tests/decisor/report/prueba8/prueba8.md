# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 01:22:50

## Prompt exacto del modelo de decisión

````
Sos el auditor de consultas SQL de un data warehouse en Postgres 15. La regla es: una consulta se aprueba solo si usa los índices existentes, no hace full scan de facturas, no usa SELECT *, y devuelve como máximo 5000 filas. Se rechaza si viola cualquiera de estos puntos.

Esquema relevante:
- facturas: 40 millones de filas, 320 GB. Índices: btree en (cliente_id, fecha), btree en estado, btree en id (PK). Sin particionado.
- clientes: 800 mil filas. Índice en id (PK), índice único en email.
- Distribución: el cliente 45231 tiene 137 facturas pagadas desde enero, sobre un promedio de 22 por cliente. El 92 por ciento de las facturas están en estado pagada.

Consulta a auditar:

```sql
SELECT f.id, f.fecha, f.total, c.nombre, c.email
FROM facturas f
JOIN clientes c ON c.id = f.cliente_id
WHERE f.cliente_id = 45231
  AND f.fecha >= DATE '2026-01-01'
  AND f.estado = 'pagada'
ORDER BY f.fecha DESC
LIMIT 200;
```

EXPLAIN ANALYZE real ejecutado en la réplica de lectura:
- Index Scan usando facturas_cliente_fecha_idx, condición (cliente_id = 45231 AND fecha >= '2026-01-01'), filas 141, tiempo 3.2ms, con filtro adicional por estado que descarta 4 filas.
- Nested Loop con Index Scan en clientes por PK, 141 loops, tiempo total 1.1ms.
- Sort evitado: el ORDER BY fecha DESC se satisface con recorrido backward del índice.
- Planning 0.4ms, execution 4.8ms, filas devueltas 137. Buffers: 100 por ciento hits, 0 lecturas físicas.
- No aparece ningún Seq Scan en el plan. El JOIN usa la PK de clientes. Las columnas pedidas son 5 explícitas, ninguna es *.

Historial: una versión anterior de este reporte usaba SELECT * con un LIKE sobre el nombre del cliente y hacía Seq Scan de 40 millones de filas en 9 minutos; fue dada de baja en marzo. La versión actual corre cada hora desde abril sin incidentes y con p95 de 12ms. El LIMIT 200 está fijo en el código y el máximo teórico de filas del cliente más grande es 4100, por debajo del tope de 5000 de la regla.

Historia completa del reporte y del equipo de datos:

El reporte de facturas por cliente lo usan 15 personas del área comercial todos los días para responder consultas de clientes sobre su facturación. La versión anterior (enero a marzo) traía SELECT * con un LIKE sobre el nombre del cliente sin índice, lo que generaba un Seq Scan de 40 millones de filas en 9 minutos por ejecución. Como corría cada hora, el warehouse pasaba 3.6 horas por día escaneando la tabla completa y degradaba al resto de los reportes. En marzo el DBA lo dio de baja por violar 3 de las 4 reglas (full scan, SELECT * y sin límite efectivo) y el área comercial estuvo 2 semanas sin el reporte hasta que se escribió la versión actual.

La versión actual la escribió el analista de datos en abril con las 4 reglas como checklist explícito: columnas explícitas (id, fecha, total, nombre, email), filtro por cliente_id con índice, filtro por fecha con el mismo índice compuesto, filtro por estado, ORDER BY satisfecho por el índice y LIMIT 200 fijo en el código (no parametrizable por el usuario). Desde abril corre cada hora sin incidentes con p95 de 12ms y p99 de 25ms. El área comercial firmó la conformidad en mayo y el reporte figura como ejemplo de buenas prácticas en la wiki del equipo.

La tabla facturas: 40 millones de filas, 320 GB, crecimiento de 800000 filas por mes. Tiene btree en (cliente_id, fecha), btree en estado y PK en id. No está particionada aunque el particionado por año está propuesto desde 2024 sin fecha. El 92 por ciento de las facturas están en estado pagada, 5 por ciento pendiente y 3 por ciento anulada. El cliente 45231 tiene 137 facturas pagadas desde enero (promedio por cliente: 22) y es el tercer cliente con más facturas del año. El cliente más grande tiene 4100 facturas, por debajo del tope de 5000 de la regla incluso sin LIMIT.

El índice (cliente_id, fecha): creado en 2023 para otro reporte, con 850 MB de tamaño y mantenimiento nocturno. El EXPLAIN muestra Index Scan con 141 filas leídas y 137 devueltas (4 descartadas por el filtro de estado), 3.2ms de ejecución, 100 por ciento buffers hits. El ORDER BY fecha DESC se satisface con recorrido backward del índice sin sort. El JOIN con clientes usa la PK con 141 loops en 1.1ms. Planning 0.4ms. No hay Seq Scan, no hay sort en disco, no hay SELECT *.

Política de auditoría: todo reporte nuevo o modificado pasa por el auditor con las 4 reglas (índices, sin full scan, sin SELECT *, máximo 5000 filas). En lo que va del año se auditaron 30 reportes: 22 aprobados, 5 rechazados por SELECT * y 3 por full scan. Los rechazados se reescriben en 1 semana promedio. Este reporte es una modificación menor (se agregó el filtro por estado en mayo) y por eso se re-audita. El filtro por estado usa el índice simple en estado solo para descartar 4 filas después del Index Scan principal; el auditor anterior lo consideró aceptable porque no agrega un scan.

Otros reportes del mismo autor: el analista escribió 6 reportes este año, 5 aprobados sin observaciones y 1 rechazado por un LIKE sin índice (corregido en 3 días). El equipo de datos tiene 4 personas y el DBA dedica 1 día por semana a auditorías. El SLA de auditoría es 5 días hábiles y este expediente lleva 2 días.

Contexto de carga del warehouse: la réplica de lectura donde se ejecutó el EXPLAIN atiende 40 reportes por hora en horario comercial con CPU promedio de 45 por ciento. La consulta auditada representa el 0.1 por ciento de la carga. El autovacuum de facturas corre de noche y la tabla tiene 5 por ciento de bloat. El índice (cliente_id, fecha) se usa en 12 reportes distintos y su hit rate es 99 por ciento. La última vez que un reporte aprobado causó un incidente fue en 2024 (un LIMIT parametrizable que un usuario puso en 10 millones); desde entonces los LIMIT son fijos en código por política.

Detalle del cliente 45231: empresa con 137 facturas pagadas desde enero por 2.3 millones de pesos, sin facturas pendientes ni anuladas. El filtro por estado pagada descarta 4 filas (3 pendientes de enero que después se pagaron y 1 anulada por error de carga). El reporte se usa para responderle a este cliente su historial cuando lo pide por email (4 pedidos este año). El área comercial confirma que el cliente nunca reclamó datos faltantes con la versión actual.

Auditoría externa y precedentes: la auditoría externa de sistemas de marzo revisó 10 reportes al azar y observó 2 por SELECT * (ya corregidos). Este reporte no fue observado. En 2024 hubo un incidente con un reporte aprobado que tenía LIMIT parametrizable: un usuario lo puso en 10 millones y degradó la réplica por 40 minutos. Desde entonces la política exige LIMIT fijo en código y este reporte lo cumple (200 fijo, no parametrizable). El auditor anterior aprobó la versión actual en abril con una sola nota: documentar por qué el filtro de estado no usa índice propio. La respuesta documentada es que el filtro descarta 4 de 141 filas después del Index Scan y que un índice adicional no cambia el plan (verificado con EXPLAIN: el planificador elige el mismo Index Scan con o sin el índice en estado).

Carga de la réplica y convivencia: la réplica de lectura atiende 40 reportes por hora con CPU de 45 por ciento promedio y picos de 70 por ciento a las 9:00. Esta consulta consume 3.2ms de CPU por ejecución (0.1 por ciento de la carga horaria). El DBA confirma que hay margen para 3 veces más carga antes de necesitar otra réplica. El reporte corre cada hora en el minuto 15, fuera de los picos de los otros 3 reportes grandes (minutos 0, 30 y 45). No hubo quejas de performance desde abril.

Otros usos del índice: el índice (cliente_id, fecha) lo usan 12 reportes con hit rate de 99 por ciento y 850 MB de tamaño. Su mantenimiento nocturno tarda 4 minutos dentro de la ventana de 2 horas. Eliminar o modificar el índice afectaría a los 12 reportes; la auditoría no propone cambios. El particionado de facturas por año está propuesto desde 2024 pero frenado porque exige cambiar 30 reportes; no es condición para aprobar este.

Conformidad comercial y SLA: el área comercial firmó la conformidad en mayo después de 1 mes de uso paralelo con la versión vieja (diferencias: solo las 4 filas de estado, explicadas). El SLA de auditoría es 5 días hábiles y el expediente lleva 2 días. Si se aprueba hoy, el filtro por estado queda oficializado y el reporte sale del circuito de re-auditorías por 1 año según la política.

Nota del auditor anterior y checklist aplicado: el auditor que aprobó la versión en abril dejó un checklist firmado con las 4 reglas tildadas (índice usado: sí, full scan: no, SELECT *: no, filas máximas: 200 por LIMIT fijo). Para esta re-auditoría el checklist se repite con el filtro de estado agregado: el plan no cambia (Index Scan por cliente_id y fecha), las columnas no cambian (las mismas 5 explícitas), el LIMIT sigue fijo en 200 y el máximo teórico sigue en 4100 para el cliente más grande. El DBA adjuntó el EXPLAIN actualizado con el filtro de estado (3.2ms, 141 filas leídas, 137 devueltas). La única diferencia con abril son las 4 filas descartadas por estado, que el auditor anterior ya había anticipado como aceptables en su nota.

Uso real y conformidad del área: el reporte se ejecuta cada hora en el minuto 15 y lo consultan 15 personas de comercial (promedio 40 consultas diarias al panel). Desde abril no hubo reclamos por datos faltantes ni por performance. La conformidad firmada en mayo incluye la aceptación explícita del filtro por estado (comercial verificó que las 4 filas descartadas corresponden a pendientes y anuladas que no deben mostrarse). El área pide que la aprobación de hoy deje constancia de que el filtro por estado es parte oficial del reporte para no re-auditarlo cada vez que alguien pregunte. El DBA confirma que el plan es estable (no cambió en 50 ejecuciones muestreadas) y que el índice tiene espacio para 3 años de crecimiento antes de necesitar particionado.

Cierre del expediente: el expediente lleva 2 días contra un SLA de 5. El analista recomienda aprobar con la constancia del filtro por estado como parte oficial. El supervisor visó la recomendación. La aprobación de hoy cierra la re-auditoría y el reporte queda con conformidad por 1 año. Si se rechaza, vuelve al analista para reescribir (1 semana estimada) y comercial queda sin el filtro por estado (tendría que filtrar a mano las 4 filas en cada consulta, 40 veces por día).

````

### Agregado para LLM tradicional

````
## Tarea
Solo respondé esta pregunta en función a lo indicado por el usuario y devolvé solo la respuesta, sin texto extra, sin argumentar.
Pregunta: La consulta cumple todas las reglas y se aprueba?
````

## Parámetros de modelo de decisión

```json
{
  "noul": {
    "type": "noul",
    "instructions": "La consulta cumple todas las reglas y se aprueba?"
  }
}
```

## Respuesta modelo de decisión

```json
{
  "status": "success",
  "message": "Decision ok.",
  "data": {
    "available": true,
    "answers": {
      "noul": {
        "type": "noul",
        "noul": 0.99962001545215
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2755,
    "completion_tokens": 1,
    "total_tokens": 2756,
    "total_time": 0.9
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2814,
    "completion_tokens": 1,
    "total_tokens": 2815,
    "total_time": 1.45,
    "time_to_first_token": 1.45
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí, la consulta cumple todas las reglas y se aprueba.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2709,
    "completion_tokens": 93,
    "total_tokens": 2802,
    "total_time": 0.6,
    "time_to_first_token": 0.6
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí, cumple las cuatro reglas (usa índices existentes, sin full scan, sin SELECT *, máximo 5000 filas) y se aprueba.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 3333,
    "completion_tokens": 306,
    "total_tokens": 3639,
    "total_time": 4.58,
    "time_to_first_token": 4.58
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2847,
    "completion_tokens": 2,
    "total_tokens": 2849,
    "total_time": 0.6,
    "time_to_first_token": 0.6
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 2755 | 1 | 0.91 | 1.0 | null | 0.0 |
| google | gemini-3.5-flash-lite | 2814 | 1 | 1.46 | Sí | null | 0.0008466999999999999 |
| groq | openai/gpt-oss-20b | 2709 | 93 | 0.61 | Sí, la consulta cumple todas las reglas y se aprueba. | null | 0.000231075 |
| openrouter | inclusionai/ling-3.1-flash | 3333 | 306 | 4.58 | Sí, cumple las cuatro reglas (usa índices existentes, sin full scan, sin SELECT *, máximo 5000 filas) y se aprueba. | null | 0.0 |
| groq | qwen/qwen3.8-27b | 2847 | 2 | 0.61 | Sí | null | 0.0022856 |
