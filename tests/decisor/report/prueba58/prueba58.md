# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:35:20

## Prompt exacto del modelo de decisión

````
Sos el API designer que puntúa un fragmento de diseño de API REST. Puntuá el diseño según los criterios indicados.

Fragmento del endpoint de devoluciones:

POST /api/v1/returns con body {"order_id": 88123, "items": [{"sku": "REM-221", "qty": 2, "reason": "damaged"}], "refund_method": "original"}. Responde 201 con {"return_id": "R-5521", "status": "pending", "eta_days": 5}. Errores: 400 con código RETURN_INVALID_QTY si la cantidad supera la comprada, 404 con ORDER_NOT_FOUND, 409 con RETURN_ALREADY_EXISTS si ya hay una devolución abierta para la orden. Todos los errores siguen el envelope {"error": {"code": "...", "message": "...", "request_id": "..."}}. La API es idempotente con header Idempotency-Key y lo documenta con ejemplo. Paginación de GET /api/v1/returns con cursor y límite máximo 100. Versionado en la URL. Faltan: no hay rate limits documentados, el webhook de cambio de estado se menciona pero sin firma ni reintentos, y no aclara si refund_method acepta otros valores además de original.

Más datos: la API la consumen 3 clientes (web propia, app mobile y un integrador externo) con 2 millones de llamadas al mes. El integrador ya se quejó 2 veces por cambios no avisados en los errores. El webhook lo necesitan 2 clientes para actualizar sus sistemas y hoy lo consultan por polling cada 5 minutos (80000 llamadas diarias evitables). No hay SDK ni colección de Postman; los clientes se quejan del onboarding. El versionado en URL existe pero nunca se publicó una v2 ni hay política de deprecación. El equipo de seguridad pidió rate limits hace 3 meses después de un abuso que tumbó el endpoint 20 minutos. El diseño lo hizo el equipo de backend sin review de los consumidores.

Criterios: se valora consistencia REST, manejo de errores, idempotencia, paginación, versionado y documentación de integración.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "flojo", "1": "aceptable", "2": "bueno", "3": "muy bueno", "4": "excelente"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá la calidad del diseño según los criterios.",
    "criteria": [
      "flojo",
      "aceptable",
      "bueno",
      "muy bueno",
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
        "score": 1.842370439629832,
        "confidence": 0.845048778738468,
        "legend": {
          "0": "flojo",
          "1": "aceptable",
          "2": "bueno",
          "3": "muy bueno",
          "4": "excelente"
        },
        "probabilities": {
          "0": 0.005188471233080129,
          "1": 0.16140857047584303,
          "2": 0.8197003692830312,
          "3": 0.013249225444256173,
          "4": 0.0004533635637894937
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 614,
    "completion_tokens": 1,
    "total_tokens": 615,
    "total_time": 0.66
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "1.8",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 583,
    "completion_tokens": 3,
    "total_tokens": 586,
    "total_time": 0.84,
    "time_to_first_token": 0.84
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "1.5",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 617,
    "completion_tokens": 258,
    "total_tokens": 875,
    "total_time": 0.91,
    "time_to_first_token": 0.91
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
    "prompt_tokens": 670,
    "completion_tokens": 530,
    "total_tokens": 1200,
    "total_time": 8.07,
    "time_to_first_token": 8.07
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "{\n  \"0\": \"failing\",\n  \"1\": \"weak\",\n  \"2\": \"fair\",\n  \"3\": \"good\",\n  \"4\": \"excellent\"\n}",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 597,
    "completion_tokens": 46,
    "total_tokens": 643,
    "total_time": 0.39,
    "time_to_first_token": 0.39
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 614 | 1 | 0.66 | 1.84 | 0.845048778738468 | 0.0 |
| google | gemini-3.5-flash-lite | 583 | 3 | 0.85 | 1.8 | null | 0.0001824 |
| groq | openai/gpt-oss-20b | 617 | 258 | 0.92 | 1.5 | null | 0.000123675 |
| openrouter | inclusionai/ling-3.1-flash | 670 | 530 | 8.08 | 2.4 | null | 0.0 |
| groq | qwen/qwen3.8-27b | 597 | 46 | 0.4 | {   "0": "failing",   "1": "weak",   "2": "fair",   "3": "good",   "4": "excellent" } | null | 0.0006616 |
