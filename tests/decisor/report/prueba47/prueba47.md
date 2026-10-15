# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:06:10

## Prompt exacto del modelo de decisión

````
Sos el auditor de SQL. Puntuá la siguiente consulta según los criterios indicados. Corre cada mañana sobre un Postgres con 12 millones de órdenes para el reporte de operaciones.

```sql
SELECT o.id, o.fecha, o.total, c.nombre,
       (SELECT SUM(total) FROM ordenes WHERE cliente_id = o.cliente_id) AS total_cliente,
       (SELECT COUNT(*) FROM ordenes WHERE cliente_id = o.cliente_id AND estado = 'pendiente') AS pendientes
FROM ordenes o
JOIN clientes c ON c.id = o.cliente_id
WHERE o.fecha >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY o.total DESC
LIMIT 1000;
```

Contexto: la tabla ordenes tiene índice en (cliente_id) y en (fecha). Las dos subconsultas correlacionadas se ejecutan una vez por fila del resultado (hasta 1000 veces cada una) en lugar de calcularse una sola vez con agregación. El ORDER BY sobre total sin índice obliga a ordenar todo el set filtrado. El reporte tarda 47 segundos y bloquea lecturas de la app durante su ejecución (la app muestra timeouts entre las 8:00 y las 8:01). Devuelve los datos correctos: los números fueron validados contra contabilidad en 3 cierres mensuales. El LIMIT 1000 está bien para el uso del reporte. El equipo propuso reescribirla con un CTE agregado pero el cambio lleva 2 meses en espera.

Más datos: la tabla crece 400000 órdenes por mes y el filtro de 30 días ya devuelve 900000 filas antes del LIMIT. El EXPLAIN muestra 2 millones de loops en las subconsultas y un sort en disco de 1.2 GB. El reporte lo miran 5 personas de operaciones a las 8:00 y nadie más en el día. La app que se bloquea atiende 2000 usuarios en ese horario con reclamos registrados 3 veces esta semana. El DBA sugirió un índice en (fecha, total) pero el equipo de backend teme que ralentice las escrituras del pico nocturno. La consulta la escribió el líder técnico hace 2 años cuando la tabla tenía 2 millones de filas y tardaba 3 segundos.

Historial de la consulta y del reporte:

La consulta la escribió el líder técnico hace 2 años cuando la tabla tenía 2 millones de filas y tardaba 3 segundos. Desde entonces la tabla crece 400000 órdenes por mes y hoy tiene 11 millones. El tiempo subió progresivamente: 3 segundos en 2024, 12 segundos a fin de 2024, 28 segundos en marzo de este año y 47 segundos hoy. El reporte se ejecuta todos los días a las 8:00 por un cron y lo miran 5 personas de operaciones durante 10 minutos; nadie más lo usa en el día. Los números fueron validados contra contabilidad en 3 cierres mensuales y son correctos: el problema es solo performance, no exactitud.

Impacto en la app: durante los 47 segundos de ejecución la consulta toma locks que bloquean lecturas de la app de ventas (2000 usuarios activos a las 8:00). Esta semana hubo reclamos 3 veces por timeouts entre las 8:00 y las 8:01. El equipo de soporte tiene un template de respuesta para estos reclamos. El gerente de ventas pidió mover el reporte a las 7:00 pero operaciones se negó porque necesitan los datos del cierre nocturno que termina a las 7:30.

Análisis técnico del plan: el EXPLAIN muestra que las 2 subconsultas correlacionadas (promedio por cliente y conteo de devoluciones) se ejecutan una vez por cada una de las 1000 filas del resultado: 2000 ejecuciones que recorren 900000 filas filtradas, total 2 millones de loops. El ORDER BY sobre total sin índice obliga a un sort en disco de 1.2 GB (la memoria de sort es 256 MB). El filtro por fecha usa el índice en (fecha) pero igual devuelve 900000 filas antes del LIMIT. El JOIN con clientes usa la PK y no es el problema.

Propuestas sobre la mesa: el DBA sugirió un índice en (fecha, total) que eliminaría el sort pero el equipo de backend teme que ralentice las escrituras del pico nocturno (50000 inserts entre las 0 y las 6). El líder técnico propuso reescribirla con un CTE que agregue una sola vez (cambio de 2 días de trabajo) pero lleva 2 meses en espera porque el roadmap no le da prioridad. Un consultor externo propuso una tabla agregada diaria (costo 1 semana) que dejaría el reporte en 200ms pero con datos del día anterior, y operaciones lo rechazó porque necesita el día corriente.

Índices existentes: la tabla tiene btree en (cliente_id), btree en (fecha) y PK en id. No hay particionado aunque la tabla crece 400000 filas por mes. El autovacuum corre de noche y la tabla tiene 8 por ciento de bloat. El DBA informó que el índice sugerido ocuparía 800 MB y que el mantenimiento nocturno tiene ventana suficiente, pero backend insiste en el riesgo de escrituras sin haberlo medido.

Contexto del equipo: el equipo de backend tiene 6 personas y el DBA es compartido con otros 3 equipos (disponibilidad 1 día por semana). El reporte lo pidió el gerente de operaciones hace 2 años y nunca se revisó desde entonces. La app de ventas factura 3 millones de USD mensuales y los timeouts de las 8:00 generan 5 reclamos por semana promedio.

Números del bloqueo: durante los 47 segundos la consulta mantiene 3 locks que bloquean 2000 sesiones de la app; el p99 de la app pasa de 300ms a 8 segundos en esa ventana. El template de respuesta de soporte se usó 15 veces este mes. Mover el reporte a las 7:00 fue rechazado porque el cierre nocturno termina 7:30; moverlo a las 9:00 fue rechazado porque operaciones lo necesita antes de la reunión de las 8:30. La reescritura con CTE está estimada en 2 días pero sin prioridad en el roadmap desde hace 2 meses.

Crecimiento proyectado: a 400000 órdenes por mes, en 6 meses la tabla tendrá 13.5 millones y el filtro de 30 días devolverá 1.1 millones de filas. El DBA proyecta 70 segundos de ejecución para fin de año si no cambia nada. El sort en disco ya es de 1.2 GB y la memoria de sort no se puede subir sin afectar al resto. La tabla no está particionada y el particionado por mes está propuesto desde marzo sin fecha.

Validación de números: contabilidad validó el reporte en 3 cierres mensuales y los números son correctos. El problema es solo performance: el reporte tarda 47 segundos y bloquea la app. Operaciones no acepta datos del día anterior ni mover el horario. La única salida acordada es optimizar la consulta o agregar el índice, pero ninguna tiene fecha.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "pesimo", "1": "deficiente", "2": "aceptable", "3": "bueno", "4": "excelente"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá la calidad de la consulta según los criterios.",
    "criteria": [
      "pesimo",
      "deficiente",
      "aceptable",
      "bueno",
      "excelente"
    ]
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
      "score": {
        "type": "score",
        "score": 0.8764634166609797,
        "confidence": 0.8830394094322875,
        "legend": {
          "0": "pesimo",
          "1": "deficiente",
          "2": "aceptable",
          "3": "bueno",
          "4": "excelente"
        },
        "probabilities": {
          "0": 0.1319446460101377,
          "1": 0.8603871192450241,
          "2": 0.006992808388039747,
          "3": 0.0006110247873180805,
          "4": 6.440156948045781e-05
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1717,
    "completion_tokens": 1,
    "total_tokens": 1718,
    "total_time": 1.17
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "0.5",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1728,
    "completion_tokens": 3,
    "total_tokens": 1731,
    "total_time": 1.61,
    "time_to_first_token": 1.61
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "1.3",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1692,
    "completion_tokens": 579,
    "total_tokens": 2271,
    "total_time": 1.14,
    "time_to_first_token": 1.14
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "1.1",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2030,
    "completion_tokens": 94,
    "total_tokens": 2124,
    "total_time": 2.51,
    "time_to_first_token": 2.51
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "1",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1759,
    "completion_tokens": 2,
    "total_tokens": 1761,
    "total_time": 0.4,
    "time_to_first_token": 0.4
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 1717 | 1 | 1.17 | 0.88 | 0.8830394094322875 | 0.0 |
| google | gemini-3.5-flash-lite | 1728 | 3 | 1.62 | 0.5 | null | 0.0005259 |
| groq | openai/gpt-oss-20b | 1692 | 579 | 1.15 | 1.3 | null | 0.0003006 |
| openrouter | inclusionai/ling-3.1-flash | 2030 | 94 | 2.51 | 1.1 | null | 0.0 |
| groq | qwen/qwen3.8-27b | 1759 | 2 | 0.41 | 1.0 | null | 0.0014152 |
