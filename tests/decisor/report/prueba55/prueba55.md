# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:27:33

## Prompt exacto del modelo de decisión

````
Sos el copywriter senior que puntúa el texto de una landing. Puntuá el copy según los criterios indicados.

Landing de un curso de asado para principiantes (precio 39 USD):

Titular: Aprende a hacer asado. Subtítulo: Un curso online. Cuerpo: El curso tiene videos. Son 20 videos. Duran 5 horas en total. Vas a aprender cosas del asado. Incluye recetas. Podés pagar con tarjeta. Testimonios: dos comentarios genéricos sin nombre ni foto que dicen que está bueno. Garantía: no se menciona. Precio: aparece al final sin anclar contra ningún valor de referencia. Llamado a la acción: botón que dice Enviar. No hay urgencia, ni bonus, ni objeciones respondidas (tiempo, nivel, equipamiento), ni historia del instructor (no dice quién enseña ni por qué creerle).

Métricas: rebote 92 por ciento, conversión 0.2 por ciento, tiempo medio en página 18 segundos.

Más datos: la landing recibe 5000 visitas al mes desde YouTube orgánico y el curso se vende solo por esta página. La competencia vende cursos parecidos a 29 USD con landing de 2000 palabras, 15 testimonios con foto y garantía de 7 días. El instructor tiene 200000 seguidores en Instagram pero la landing no lo menciona ni enlaza sus redes. El botón Enviar lleva a un checkout de 3 pasos que abandona el 70 por ciento. El dueño del curso cree que el problema es el precio y quiere bajarlo a 29; el editor cree que es el copy y propone reescribirlo. Hay 40 alumnos actuales con satisfacción 4.8 sobre 5 que podrían dar testimonios y nadie se los pidió.

Criterios: se valora titular, propuesta de valor, prueba social, manejo de objeciones, llamado a la acción y estructura de precio.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "muy malo", "1": "malo", "2": "regular", "3": "bueno", "4": "muy bueno", "5": "excelente"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá el copy según los criterios.",
    "criteria": [
      "muy malo",
      "malo",
      "regular",
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
        "score": 0.07646636653093297,
        "confidence": 0.9490224223127114,
        "legend": {
          "0": "muy malo",
          "1": "malo",
          "2": "regular",
          "3": "bueno",
          "4": "muy bueno",
          "5": "excelente"
        },
        "probabilities": {
          "0": 0.9238888100689251,
          "1": 0.07583741509333977,
          "2": 0.000226749819073188,
          "3": 2.5440624626062228e-05,
          "4": 8.792044610549157e-06,
          "5": 1.2792349425289251e-05
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 543,
    "completion_tokens": 1,
    "total_tokens": 544,
    "total_time": 4.83
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "0.2",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 519,
    "completion_tokens": 3,
    "total_tokens": 522,
    "total_time": 0.9,
    "time_to_first_token": 0.9
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
    "prompt_tokens": 574,
    "completion_tokens": 327,
    "total_tokens": 901,
    "total_time": 0.94,
    "time_to_first_token": 0.94
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'inclusionai/ling-3.1-flash is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'provider_name': 'Novita', 'is_byok': False, 'limit_source': 'upstream_provider_shared_pool', 'remedy_hint': 'Retry shortly, add your own provider key (https://openrouter.ai/settings/integrations), or route to another provider with provider routing: https://openrouter.ai/docs/features/provider-routing'}}, 'user_id': 'user_3IHIEaL9108If8k2gSzCi1zx2e3'}",
  "data": null,
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "total_time": 0
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1556. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}",
  "data": null,
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "total_time": 0
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 543 | 1 | 4.84 | 0.08 | 0.9490224223127114 | 0.0 |
| google | gemini-3.5-flash-lite | 519 | 3 | 0.9 | 0.2 | null | 0.00016319999999999998 |
| groq | openai/gpt-oss-20b | 574 | 327 | 0.95 | 1.0 | null | 0.00014115 |
| openrouter | inclusionai/ling-3.1-flash | 0 | 0 | 2.61 | "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'inclusionai/ling-3.1-flash is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'provider_name': 'Novita', 'is_byok': False, 'limit_source': 'upstream_provider_shared_pool', 'remedy_hint': 'Retry shortly, add your own provider key (https://openrouter.ai/settings/integrations), or route to another provider with provider routing: https://openrouter.ai/docs/features/provider-routing'}}, 'user_id': 'user_3IHIEaL9108If8k2gSzCi1zx2e3'}" | null | 0.0 |
| groq | qwen/qwen3.8-27b | 0 | 0 | 0.12 | "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1556. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}" | null | 0.0 |
