# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:32:48

## Prompt exacto del modelo de decisión

````
Sos el editor que puntúa un reporte de bug. Puntuá el reporte según los criterios indicados.

Reporte 77120 del módulo de stock:

Título: No anda el stock. Descripción: cuando hago cosas se rompe. Pasos: 1) entro, 2) hago click, 3) se rompe. Resultado esperado: que ande. Resultado real: no anda. Versión: no sé. Dispositivo: mi compu. Adjuntos: ninguno. El reportante no responde los pedidos de aclaración desde hace 4 días. El equipo intentó adivinar con 3 escenarios distintos y no reprodujo nada. Hay otros 2 reportes del mismo usuario con el mismo nivel de detalle, también sin respuesta.

Más datos: el módulo de stock tuvo 40 reportes este mes y 35 traían pasos reproducibles; este es de los 5 peores. El reportante es un usuario final sin capacitación en cómo reportar (nunca abrió la guía de 2 páginas). El equipo de QA tiene una plantilla obligatoria pero el formulario web permite enviarla vacía. El bug podría ser real: hay 2 reclamos de clientes por stock mal descontado esta semana sin causa encontrada. El reporte lleva 4 días en la cola y el SLA de triage es 48 horas. El líder de QA discute si devolverlo al reportante o salir a buscar el bug con los datos de los reclamos.

Contexto ampliado del módulo, de los reclamos y del proceso:

El módulo de stock maneja 120000 artículos en 4 depósitos con movimientos de 8000 por día. En el último deploy (hace 3 semanas) se cambió la lógica de descuento por lote y desde entonces hay 2 reclamos de clientes por stock mal descontado sin causa encontrada: uno por 200 unidades de más en un artículo de alta rotación y otro por 50 unidades de menos en un kit. Ambos reclamos están abiertos y el área comercial presiona porque afectan facturación. El equipo de desarrollo dice que la lógica nueva pasó 120 tests, pero reconoce que ningún test cubre el flujo exacto que describe el reporte (aunque el reporte no describe ningún flujo con precisión).

El reportante: usuario final del depósito de Córdoba con 2 años usando el sistema, 6 reportes previos (4 fueron errores de uso por no actualizar la página, 2 fueron bugs reales confirmados). Nunca abrió la guía de 2 páginas sobre cómo reportar que se envió por email en marzo. No responde los pedidos de aclaración desde hace 4 días (se le pidió versión, pasos exactos y capturas en 2 oportunidades). Hay otros 2 reportes del mismo usuario con el mismo nivel de detalle, también sin respuesta, de la semana pasada.

La plantilla y el formulario: QA tiene una plantilla obligatoria con 8 campos (título, descripción, pasos numerados, resultado esperado, resultado real, versión, dispositivo y adjuntos). El formulario web la muestra como ayuda pero permite enviar con todos los campos vacíos o con texto libre. El 30 por ciento de los reportes llega con la plantilla incompleta. Hay un proyecto para hacer los campos obligatorios pero está frenado porque el área comercial dice que los clientes se quejarían.

El proceso de triage: el SLA es 48 horas para clasificar (bug real, error de uso o necesita más datos). Este reporte lleva 4 días porque el analista asignado estuvo de licencia y nadie lo reasignó. El líder de QA discute dos caminos: devolverlo al reportante por falta de datos (con riesgo de que no responda y el bug real, si existe, siga vivo) o salir a buscar el bug con los datos de los 2 reclamos de clientes (con costo de 3 días de un QA senior que está asignado al release). El release de la semana que viene incluye 40 cambios en stock y el QA senior es el único que conoce el módulo.

Historial del mes: 40 reportes de stock, 35 con pasos reproducibles (28 fueron errores de uso, 7 bugs reales ya corregidos). Los 5 peores (incluido este) no tienen ni versión ni pasos. De los 5, 3 se cerraron como error de uso después de contactar al reportante por teléfono y 2 siguen abiertos. El tiempo promedio de resolución de reportes sin datos es 9 días vs 2 días con datos completos.

Versión y dispositivo: el reporte dice versión no sé y dispositivo mi compu. El sistema registra la versión en el footer y el 90 por ciento de los usuarios de ese depósito están en la última (3.8.2), pero hay 3 máquinas con la 3.7 que tienen un bug conocido de stock ya corregido. Sin el dato no se puede descartar que sea ese bug viejo.

El bug conocido de la 3.7: descontaba stock duplicado en devoluciones parciales y fue corregido en la 3.8. Los síntomas (diferencias de stock sin explicación) coinciden parcialmente con los 2 reclamos abiertos, pero esos clientes están en la 3.8.2 según el registro. El equipo de soporte actualizó 40 de las 43 máquinas del depósito de Córdoba; las 3 restantes son las de los usuarios de turno noche, que es el turno del reportante.

Los 2 reclamos abiertos en detalle: el primero es de un cliente con 200 unidades de más en un artículo de alta rotación (detectado en inventario del lunes, sin movimientos que lo expliquen). El segundo es de otro cliente con 50 unidades de menos en un kit armado (detectado el miércoles, con 3 movimientos registrados que no cierran). Ambos están en la versión 3.8.2 y ninguno coincide con el flujo del reporte (que no describe flujo alguno). El área comercial pidió prioridad porque suman 45000 USD en diferencias.

Cola y SLA: el reporte lleva 4 días en la cola y el SLA de triage es 48 horas. El analista asignado estuvo de licencia y nadie lo reasignó. Hay 12 reportes más vencidos en la cola del mismo módulo. El líder de QA evalúa asignar el QA senior (único que conoce el módulo) a buscar el bug con los datos de los reclamos, con costo de 3 días que impactan en el release de la semana que viene con 40 cambios en stock.

Historial del reportante: 6 reportes previos en 2 años (4 errores de uso por no actualizar la página, 2 bugs reales confirmados y corregidos). Los 2 bugs reales que reportó fueron de stock y se confirmaron en 48 horas porque traían capturas. Este reporte no trae capturas ni versión y el usuario no responde desde hace 4 días.
Criterios: se valora título descriptivo, pasos reproducibles, resultado esperado y real, datos de entorno, adjuntos y colaboración del reportante.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "inutil", "1": "deficiente", "2": "aceptable", "3": "bueno", "4": "excelente"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá la calidad del reporte según los criterios.",
    "criteria": [
      "inutil",
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
        "score": 0.22383909469495905,
        "confidence": 0.8134674210875341,
        "legend": {
          "0": "inutil",
          "1": "deficiente",
          "2": "aceptable",
          "3": "bueno",
          "4": "excelente"
        },
        "probabilities": {
          "0": 0.7768701083842049,
          "1": 0.2225770192226825,
          "2": 0.0004296746761664458,
          "3": 9.006474784115564e-05,
          "4": 3.3132969105051206e-05
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1581,
    "completion_tokens": 1,
    "total_tokens": 1582,
    "total_time": 0.74
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "0",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1591,
    "completion_tokens": 1,
    "total_tokens": 1592,
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
  "data": "1",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1615,
    "completion_tokens": 224,
    "total_tokens": 1839,
    "total_time": 1.06,
    "time_to_first_token": 1.06
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "0.5",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1904,
    "completion_tokens": 680,
    "total_tokens": 2584,
    "total_time": 9.04,
    "time_to_first_token": 9.04
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "0.5",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1630,
    "completion_tokens": 4,
    "total_tokens": 1634,
    "total_time": 0.63,
    "time_to_first_token": 0.63
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 1581 | 1 | 0.74 | 0.22 | 0.8134674210875341 | 0.0 |
| google | gemini-3.5-flash-lite | 1591 | 1 | 1.61 | 0.0 | null | 0.00047979999999999995 |
| groq | openai/gpt-oss-20b | 1615 | 224 | 1.06 | 1.0 | null | 0.000188325 |
| openrouter | inclusionai/ling-3.1-flash | 1904 | 680 | 9.05 | 0.5 | null | 0.0 |
| groq | qwen/qwen3.8-27b | 1630 | 4 | 0.63 | 0.5 | null | 0.00132 |
