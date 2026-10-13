# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:21:00

## Prompt exacto del modelo de decisión

````
Sos el DBA que elige la estrategia para un reporte mensual. Requerimiento:

Para cada vendedor, mostrar el total vendido en los últimos 12 meses, el promedio mensual, y la posición en el ranking nacional del mes corriente. La tabla ventas tiene 25 millones de filas con índice en (vendedor_id, fecha). El reporte lo consultan 40 gerentes al mismo tiempo el primer día de cada mes. Debe responder en menos de 3 segundos y los datos pueden tener hasta 1 hora de antigüedad. El equipo quiere evitar una consulta monstruosa imposible de mantener: la versión actual tiene 300 líneas con 4 niveles de subconsultas y tarda 45 segundos con un solo usuario.

Perfil de uso: los gerentes filtran por región y por categoría, ordenan por ranking y exportan a Excel. El primer día del mes el reporte se abre unas 400 veces entre las 8 y las 11. La tabla crece 800000 filas por mes y el índice actual ya pesa 6 GB. Hay ventana de mantenimiento los domingos de 2 a 4 de la mañana donde se puede recargar lo que sea. El equipo de BI ya mantiene 3 jobs horarios con el mismo scheduler que proponen reusar. Finanzas usa los mismos números para comisiones, así que el reporte y la liquidación tienen que coincidir al centavo. El año pasado intentaron una vista común y la abandonaron porque nadie la mantenía y quedó con datos de 2 meses atrás.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- ventana: calcular todo al vuelo con funciones de ventana en una sola consulta
- agregada: mantener una tabla de agregados mensuales actualizada por un job periódico
- materializada: usar una vista materializada con refresh periódico de agregados y ranking
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí la estrategia que mejor cumple el requerimiento.",
    "criteria": {
      "ventana": "calcular todo al vuelo con funciones de ventana en una sola consulta",
      "agregada": "mantener una tabla de agregados mensuales actualizada por un job periódico",
      "materializada": "usar una vista materializada con refresh periódico de agregados y ranking"
    }
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
      "choice": {
        "type": "choice",
        "choice": "agregada",
        "confidence": 0.33803106501676694,
        "probabilities": {
          "ventana": 0.006206456873341122,
          "agregada": 0.5586873766778446,
          "materializada": 0.43510616644881434
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 442,
    "completion_tokens": 1,
    "total_tokens": 443,
    "total_time": 5.98
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "agregada",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 420,
    "completion_tokens": 3,
    "total_tokens": 423,
    "total_time": 5.33,
    "time_to_first_token": 5.33
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "agregada",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 478,
    "completion_tokens": 515,
    "total_tokens": 993,
    "total_time": 1.08,
    "time_to_first_token": 1.08
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "materializada: usar una vista materializada con refresh periódico de agregados y ranking",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 532,
    "completion_tokens": 1803,
    "total_tokens": 2335,
    "total_time": 25.99,
    "time_to_first_token": 25.99
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "materializada",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 438,
    "completion_tokens": 3,
    "total_tokens": 441,
    "total_time": 0.3,
    "time_to_first_token": 0.3
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 442 | 1 | 5.98 | agregada | 0.33803106501676694 | 0.0 |
| google | gemini-3.5-flash-lite | 420 | 3 | 5.33 | agregada | null | 0.0001335 |
| groq | openai/gpt-oss-20b | 478 | 515 | 1.08 | agregada | null | 0.00019035 |
| openrouter | inclusionai/ling-3.1-flash | 532 | 1803 | 26.0 | materializada: usar una vista materializada con refresh periódico de agregados y ranking | null | 0.0 |
| groq | qwen/qwen3.8-27b | 438 | 3 | 0.32 | materializada | null | 0.0003624000000000001 |
