# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:53:24

## Prompt exacto del modelo de decisión

````
Sos el incident commander que clasifica la severidad. Situación actual:

Desde hace 35 minutos el checkout del ecommerce rechaza el 100 por ciento de los pagos con tarjeta con error del procesador externo. Mercado Pago y transferencia siguen funcionando y representan el 30 por ciento de las ventas. Es viernes a las 19:40, pico de ventas del mes por el Hot Sale, con 8000 usuarios activos intentando comprar. El procesador externo confirmó una caída general en la región sin ETA. El equipo estima que cambiar al procesador de respaldo tarda 50 minutos y nunca se probó en producción. Se pierden aproximadamente 25000 USD por hora. El status page todavía muestra todo verde porque nadie lo actualizó.

Clientes: el 70 por ciento de los que pagan con tarjeta reintenta y el 40 por ciento abandona después del tercer intento fallido. Soporte recibió 600 tickets en 30 minutos y el tiempo de respuesta pasó de 5 minutos a 2 horas. En redes ya hay 200 menciones quejándose y un influencer con 500000 seguidores publicó el error. El procesador de respaldo cobra 1 punto más de comisión y tarda 48 horas en acreditar. El gerente general está en el canal pidiendo updates cada 10 minutos y el equipo de marketing quiere pausar la pauta (gastan 5000 USD por hora en ads que llevan a un checkout roto). La última vez que se cayó el procesador (hace 6 meses) volvió solo en 50 minutos.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- sev1: pérdida casi total del servicio crítico con impacto masivo en ingresos
- sev2: degradación importante con alternativa disponible para los usuarios
- sev3: problema menor con impacto acotado y sin urgencia
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí la severidad que corresponde a la situación.",
    "criteria": {
      "sev1": "pérdida casi total del servicio crítico con impacto masivo en ingresos",
      "sev2": "degradación importante con alternativa disponible para los usuarios",
      "sev3": "problema menor con impacto acotado y sin urgencia"
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
        "choice": "sev1",
        "confidence": 0.839735339322101,
        "probabilities": {
          "sev1": 0.8931568928814007,
          "sev2": 0.10667238838196051,
          "sev3": 0.00017071873663877915
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 456,
    "completion_tokens": 1,
    "total_tokens": 457,
    "total_time": 5.19
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "sev1: pérdida casi total del servicio crítico con impacto masivo en ingresos",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 438,
    "completion_tokens": 15,
    "total_tokens": 453,
    "total_time": 0.76,
    "time_to_first_token": 0.76
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "sev1",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 475,
    "completion_tokens": 106,
    "total_tokens": 581,
    "total_time": 0.72,
    "time_to_first_token": 0.72
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "sev2: degradación importante con alternativa disponible para los usuarios",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 544,
    "completion_tokens": 660,
    "total_tokens": 1204,
    "total_time": 10.02,
    "time_to_first_token": 10.02
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 2048. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}",
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
| openrouter | inception/mercury-decide:free | 456 | 1 | 5.2 | sev1 | 0.839735339322101 | 0.0 |
| google | gemini-3.5-flash-lite | 438 | 15 | 0.76 | sev1: pérdida casi total del servicio crítico con impacto masivo en ingresos | null | 0.00016889999999999999 |
| groq | openai/gpt-oss-20b | 475 | 106 | 0.72 | sev1 | null | 6.7425e-05 |
| openrouter | inclusionai/ling-3.1-flash | 544 | 660 | 10.03 | sev2: degradación importante con alternativa disponible para los usuarios | null | 0.0 |
| groq | qwen/qwen3.8-27b | 0 | 0 | 0.38 | "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 2048. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}" | null | 0.0 |
