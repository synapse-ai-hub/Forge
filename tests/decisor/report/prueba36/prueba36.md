# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:36:28

## Prompt exacto del modelo de decisión

````
Sos el QA lead que elige la estrategia de testing. Proyecto:

Una app bancaria mobile con 1.2 millones de usuarios va a lanzar transferencias inmediatas 24/7. La regulación exige evidencia de pruebas de cada release, el historial muestra que el 60 por ciento de los bugs de producción fueron errores de integración con el core bancario y el 25 por ciento fueron problemas de concurrencia en saldos. El equipo tiene 6 desarrolladores y 2 testers manuales, el release sale en 8 semanas, y cada bug crítico en producción cuesta en promedio 50000 USD entre compensaciones y multas. Hoy solo hay tests manuales que tardan 5 días por release. El core bancario expone un ambiente de pruebas con datos sintéticos pero con ventana de uso de 4 horas diarias.

Bugs históricos: el año pasado un error de redondeo en saldos duplicó acreditaciones por 200000 USD (tardó 3 días en detectarse), y un timeout contra el core dejó 5000 transferencias en estado desconocido. La regulación pide matriz de trazabilidad entre requisitos y casos más evidencia de ejecución firmada. Los 2 testers manuales conocen el negocio pero nunca automatizaron; los desarrolladores escriben pocos unitarios (cobertura 20 por ciento). El release incluye 40 requisitos funcionales y 15 no funcionales. Una consultora cotizó testing externo en 80000 USD por release con 2 semanas de plazo. El banco ya fue multado una vez por fallas en transferencias y el directorio no tolera otro incidente.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- e2e: automatizar el flujo feliz punta a punta más exploratorio manual
- piramide: pirámide completa con unitarios, contrato e integración y pocos e2e críticos
- externo: tercerizar testing manual masivo para cada release
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí la estrategia que mejor reduce el riesgo con los recursos dados.",
    "criteria": {
      "e2e": "automatizar el flujo feliz punta a punta más exploratorio manual",
      "piramide": "pirámide completa con unitarios, contrato e integración y pocos e2e críticos",
      "externo": "tercerizar testing manual masivo para cada release"
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
        "choice": "piramide",
        "confidence": 0.9959992289857457,
        "probabilities": {
          "e2e": 0.0016990762251630446,
          "piramide": 0.9973328193238303,
          "externo": 0.0009681044510065533
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 467,
    "completion_tokens": 1,
    "total_tokens": 468,
    "total_time": 0.65
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "piramide",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 449,
    "completion_tokens": 2,
    "total_tokens": 451,
    "total_time": 1.73,
    "time_to_first_token": 1.73
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "piramide",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 500,
    "completion_tokens": 257,
    "total_tokens": 757,
    "total_time": 0.69,
    "time_to_first_token": 0.69
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
  "status": "success",
  "message": "Proceso ok.",
  "data": "piramide",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 465,
    "completion_tokens": 3,
    "total_tokens": 468,
    "total_time": 0.36,
    "time_to_first_token": 0.36
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 467 | 1 | 0.66 | piramide | 0.9959992289857457 | 0.0 |
| google | gemini-3.5-flash-lite | 449 | 2 | 1.74 | piramide | null | 0.0001397 |
| groq | openai/gpt-oss-20b | 500 | 257 | 0.7 | piramide | null | 0.0001146 |
| openrouter | inclusionai/ling-3.1-flash | 0 | 0 | 3.0 | "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'inclusionai/ling-3.1-flash is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'provider_name': 'Novita', 'is_byok': False, 'limit_source': 'upstream_provider_shared_pool', 'remedy_hint': 'Retry shortly, add your own provider key (https://openrouter.ai/settings/integrations), or route to another provider with provider routing: https://openrouter.ai/docs/features/provider-routing'}}, 'user_id': 'user_3IHIEaL9108If8k2gSzCi1zx2e3'}" | null | 0.0 |
| groq | qwen/qwen3.8-27b | 465 | 3 | 0.36 | piramide | null | 0.000384 |
