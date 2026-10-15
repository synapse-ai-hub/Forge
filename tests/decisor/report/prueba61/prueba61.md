# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:43:23

## Prompt exacto del modelo de decisión

````
Sos el engineering manager que puntúa un postmortem. Puntuá el documento según los criterios indicados.

Postmortem de la caída del 12 de mayo (checkout caído 2 horas, 180000 USD perdidos):
- Timeline minuto a minuto desde la primera alerta hasta la resolución, con quién hizo qué en cada paso y links a los dashboards.
- Causa raíz: deploy con migración que agregó una columna NOT NULL sin default sobre una tabla de 90 millones de filas, que tomó lock exclusivo y trabó todas las escrituras. Incluye la query exacta y el análisis del lock.
- Por qué no se detectó: el staging tiene 10000 filas y la migración tardó 200ms ahí, y nadie revisó el tamaño de la tabla de producción. El checklist de deploy no pedía ese dato.
- Acciones: 5 acciones concretas con dueño y fecha (linter de migraciones peligrosas, checklist con tamaño de tabla, dry-run de migraciones en réplica, alerta de locks de más de 30 segundos, game day mensual). 3 ya completadas a la fecha del documento.
- Sin culpas: no nombra culpables, habla de fallas del proceso y el ingeniero que hizo el deploy participó en la redacción.
- Debilidad: no cuantifica cuántos clientes fueron afectados ni el impacto en NPS o churn posterior, solo la pérdida directa.

Más datos: la caída afectó al checkout de 3 marcas del grupo con 50000 visitas en esas 2 horas; el documento no dice cuántas compraron después ni cuántas se fueron. Soporte recibió 1200 tickets ese día y el tiempo medio de respuesta pasó de 10 minutos a 3 horas. El documento se escribió 5 días después con participación de 6 personas y se presentó al directorio. De las 5 acciones, las 3 completadas son las de menor costo; el dry-run en réplica sigue pendiente por falta de infraestructura. El ingeniero que hizo el deploy sigue en el equipo y ya aplicó el nuevo checklist en 4 deploys sin incidentes. No hay seguimiento de si el NPS cayó: la última medición es de abril, anterior a la caída.

Ampliación del postmortem con timeline, acciones y contexto:

Timeline del incidente (jueves 28 de mayo): 14:02 deploy de la versión 4.9 con migración de la tabla de pagos. 14:05 primeros errores 500 en el checkout (0.5 por ciento). 14:12 el error sube al 15 por ciento y el monitoreo dispara la alerta (el umbral es 10 por ciento, por eso tardó 10 minutos). 14:20 se declara el incidente y se convoca al equipo. 14:35 se identifica la migración como causa probable. 14:50 se decide el rollback. 15:10 rollback completo pero los errores siguen (la migración había dejado datos inconsistentes). 15:40 se aplica el script de reparación. 16:05 el error baja a 0. El documento registra cada hito con hora y responsable, y adjunta los gráficos del monitoreo.

Causa raíz: la migración agregaba una columna NOT NULL sin default a una tabla con 40 millones de filas, lo que bloqueó escrituras durante 8 minutos y dejó 12000 transacciones a medio procesar. El script de deploy no tenía verificación previa del tamaño de la tabla ni dry-run. El ingeniero que hizo el deploy siguió el checklist vigente, que no exigía ninguna de esas dos cosas. El documento identifica como falla del proceso que el checklist no cubría migraciones grandes, no como error individual, y no nombra culpables.

Detección: el monitoreo tardó 10 minutos porque el umbral de alerta estaba en 10 por ciento y el error arrancó bajo. Los clientes avisaron antes que el monitoreo: 40 tickets llegaron entre las 14:05 y las 14:12. El documento propone bajar el umbral a 2 por ciento y agregar alerta de tasa de error por minuto, pero no dice quién lo implementa ni cuándo.

Las 5 acciones: 1) nuevo checklist de deploys con verificación de migraciones (completada, aplicada en 4 deploys sin incidentes). 2) dry-run obligatorio en réplica antes de cada migración (pendiente por falta de infraestructura: la réplica no tiene capacidad y piden 8000 USD de hardware). 3) bajar umbrales de alerta (completada). 4) script de reparación de transacciones a medio procesar documentado y versionado (completada). 5) capacitar al equipo en migraciones sin downtime (pendiente, sin fecha). Las 3 completadas son las de menor costo; las 2 pendientes son las estructurales.

Impacto: 2 horas de checkout degradado en 3 marcas con 50000 visitas en la ventana. Pérdida directa estimada 180000 USD. El documento no cuantifica cuántos clientes no volvieron, ni el NPS posterior (última medición abril, anterior a la caída), ni el costo de los 1200 tickets de soporte (tiempo medio de 10 minutos a 3 horas ese día). El directorio pidió el número de churn y el documento no lo trae.

Cultura y proceso: el documento se escribió 5 días después con 6 personas (ingeniería, soporte, producto y comercial), se presentó al directorio sin buscar culpables y el ingeniero del deploy participó y sigue en el equipo. El proceso de postmortem se cumplió en tiempo y forma. Lo que falta es seguimiento: no hay fecha de revisión de las 2 acciones pendientes ni dueño del seguimiento del NPS.

Costo de las acciones pendientes: el hardware para el dry-run en réplica cuesta 8000 USD y lleva 3 semanas de compra e instalación. La capacitación en migraciones sin downtime es un curso de 2 días para 8 personas que cuesta 6000 USD. Ambas están pedidas desde hace 2 meses sin aprobación de presupuesto. El directorio pidió priorizarlas pero no liberó los fondos.

Seguimiento del documento: el postmortem no tiene dueño de seguimiento asignado ni fecha de revisión. La práctica del equipo es revisar las acciones pendientes en la retrospectiva mensual, pero las retrospectivas de junio y julio se suspendieron por el release. El ingeniero del deploy propuso presentar el avance en la próxima reunión de arquitectura, todavía sin fecha. Soporte informa que los tiempos de respuesta volvieron a 10 minutos promedio y que no hubo reclamos residuales por transacciones a medio procesar después del script de reparación.

Pedido del directorio: el directorio pidió el número de churn posterior a la caída y un plan de compensación para los clientes afectados. Ninguno de los dos está en el documento. Comercial estima 200 clientes que no volvieron pero sin datos duros. El documento cierra con las 5 acciones sin mencionar compensaciones ni comunicación a clientes.
Criterios: se valora timeline, causa raíz, detección de fallas del proceso, acciones concretas, cultura sin culpas y medición de impacto.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "pobre", "1": "aceptable", "2": "bueno", "3": "ejemplar"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá la calidad del postmortem según los criterios.",
    "criteria": [
      "pobre",
      "aceptable",
      "bueno",
      "ejemplar"
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
        "score": 1.7513817416622204,
        "confidence": 0.7452561398568558,
        "legend": {
          "0": "pobre",
          "1": "aceptable",
          "2": "bueno",
          "3": "ejemplar"
        },
        "probabilities": {
          "0": 0.004186352480047567,
          "1": 0.2433083542803668,
          "2": 0.7494424923369033,
          "3": 0.0030628009026823343
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1688,
    "completion_tokens": 1,
    "total_tokens": 1689,
    "total_time": 0.72
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "1.6",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1656,
    "completion_tokens": 3,
    "total_tokens": 1659,
    "total_time": 7.22,
    "time_to_first_token": 7.22
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "2",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1665,
    "completion_tokens": 182,
    "total_tokens": 1847,
    "total_time": 0.71,
    "time_to_first_token": 0.71
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "2.4",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1979,
    "completion_tokens": 1191,
    "total_tokens": 3170,
    "total_time": 18.01,
    "time_to_first_token": 18.01
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "2",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1709,
    "completion_tokens": 2,
    "total_tokens": 1711,
    "total_time": 0.42,
    "time_to_first_token": 0.42
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 1688 | 1 | 0.73 | 1.75 | 0.7452561398568558 | 0.0 |
| google | gemini-3.5-flash-lite | 1656 | 3 | 7.22 | 1.6 | null | 0.0005043 |
| groq | openai/gpt-oss-20b | 1665 | 182 | 0.72 | 2.0 | null | 0.000179475 |
| openrouter | inclusionai/ling-3.1-flash | 1979 | 1191 | 18.02 | 2.4 | null | 0.0 |
| groq | qwen/qwen3.8-27b | 1709 | 2 | 0.43 | 2.0 | null | 0.0013752 |
