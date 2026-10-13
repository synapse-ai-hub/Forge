# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 01:34:31

## Prompt exacto del modelo de decisión

````
Sos el auditor de cumplimiento de políticas de contraseñas. Una cuenta cumple si su última contraseña tiene al menos 12 caracteres, incluye mayúsculas, minúsculas, números y símbolos, no repite ninguna de las últimas 5, y fue rotada en los últimos 90 días. Las cuentas de servicio están exentas de la rotación pero deben cumplir todo lo demás. Un solo incumplimiento es no cumplimiento.

Auditoría de la cuenta deploy-bot:
- Tipo: cuenta de servicio creada en 2023, usada solo por el pipeline de CI para descargar artefactos del registro interno. No la usa ninguna persona.
- Longitud de la contraseña actual: 32 caracteres generados aleatoriamente por el vault.
- Composición: contiene mayúsculas, minúsculas, números y los símbolos !, # y %. Verificado contra la política de complejidad con el validador oficial (score 4 de 4).
- Historial: el hash actual no coincide con ninguno de los últimos 12 hashes guardados en el vault (la política pide 5, el vault guarda 12).
- Última rotación: hace 214 días. La rotación está pausada por el ticket OPS-331 (la rotación automática rompía los runners viejos, fix planificado para el próximo sprint).
- Alcance y permisos: solo lectura sobre el registro de artefactos. Sin acceso a producción, sin acceso a secretos de clientes, sin permiso de escritura en ningún lado. El token expira cada 24 horas y se renueva por el vault.
- Monitoreo: sin intentos de acceso anómalos en los últimos 12 meses, con alerta configurada ante uso fuera del rango horario del pipeline.
- El resto de las cuentas de servicio (14) rotaron en los últimos 60 días; deploy-bot es la única con rotación vencida.

````

### Agregado para LLM tradicional

````
## Tarea
Solo respondé esta pregunta en función a lo indicado por el usuario y devolvé solo la respuesta, sin texto extra, sin argumentar.
Pregunta: La cuenta cumple con la política?
````

## Parámetros de modelo de decisión

```json
{
  "noul": {
    "type": "noul",
    "instructions": "La cuenta cumple con la política?"
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
        "noul": 0.9953904281753021
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 475,
    "completion_tokens": 1,
    "total_tokens": 476,
    "total_time": 0.77
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "No",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 454,
    "completion_tokens": 1,
    "total_tokens": 455,
    "total_time": 1.37,
    "time_to_first_token": 1.37
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Cumple con la política.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 505,
    "completion_tokens": 93,
    "total_tokens": 598,
    "total_time": 0.65,
    "time_to_first_token": 0.65
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
  "message": "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1186. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}",
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
| openrouter | inception/mercury-decide:free | 475 | 1 | 0.78 | 1.0 | null | 0.0 |
| google | gemini-3.5-flash-lite | 454 | 1 | 1.38 | No | null | 0.00013869999999999998 |
| groq | openai/gpt-oss-20b | 505 | 93 | 0.65 | Cumple con la política. | null | 6.5775e-05 |
| openrouter | inclusionai/ling-3.1-flash | 0 | 0 | 2.65 | "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'inclusionai/ling-3.1-flash is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'provider_name': 'Novita', 'is_byok': False, 'limit_source': 'upstream_provider_shared_pool', 'remedy_hint': 'Retry shortly, add your own provider key (https://openrouter.ai/settings/integrations), or route to another provider with provider routing: https://openrouter.ai/docs/features/provider-routing'}}, 'user_id': 'user_3IHIEaL9108If8k2gSzCi1zx2e3'}" | null | 0.0 |
| groq | qwen/qwen3.8-27b | 0 | 0 | 0.12 | "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1186. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}" | null | 0.0 |
