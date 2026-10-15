# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:42:12

## Prompt exacto del modelo de decisión

````
Sos el growth marketer que elige el canal para lanzar un curso de Excel para contadores. Datos:

Presupuesto total 5000 USD para 6 semanas. Meta: 400 inscriptos a 49 USD cada uno. Audiencia: contadores de 25 a 45 años en Argentina y Uruguay, que pasan mucho tiempo en LinkedIn y YouTube, desconfían de los anuncios de Instagram y compran por recomendación de colegas. El equipo tiene un canal de YouTube con 8000 suscriptores donde los videos promedian 3000 vistas, una lista de email de 12000 ex-alumnos con 35 por ciento de apertura, y cero presencia en TikTok. Un lanzamiento anterior a esta misma lista convirtió al 4 por ciento en inscriptos pagos. Un webinar gratuito histórico convirtió al 12 por ciento de los asistentes. El costo por lead en LinkedIn Ads para este público es 3.5 USD, en Google Search es 1.8 USD con intención alta pero volumen bajo (800 búsquedas mensuales de estos términos).

Números: con 5000 USD en LinkedIn a 3.5 USD por lead se consiguen 1400 leads; con conversión del 4 por ciento son 56 inscriptos, lejos de los 400. En Search el volumen máximo es 800 búsquedas en 6 semanas y aunque convierta al 10 por ciento son 80 inscriptos. La lista de 12000 con 35 por ciento de apertura son 4200 lectores y al 4 por ciento histórico son 168 inscriptos. El webinar histórico tuvo 900 asistentes con 12 por ciento de conversión (108 inscriptos) usando solo tráfico orgánico. El equipo tiene un diseñador part time y nadie con experiencia en pauta; la agencia que la maneja cobra 1000 USD de fee. El curso anterior se vendió a 39 USD y subir a 49 es una apuesta del dueño.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- linkedin: pautar en LinkedIn Ads al público profesional exacto
- search: Google Search de alta intención más email a la base de ex-alumnos
- webinar: webinar gratuito con tráfico orgánico de YouTube y email
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí el canal que mejor cumple la meta con el presupuesto dado.",
    "criteria": {
      "linkedin": "pautar en LinkedIn Ads al público profesional exacto",
      "search": "Google Search de alta intención más email a la base de ex-alumnos",
      "webinar": "webinar gratuito con tráfico orgánico de YouTube y email"
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
        "choice": "search",
        "confidence": 0.9520726297362768,
        "probabilities": {
          "linkedin": 0.0027190483663227095,
          "search": 0.9680484198241845,
          "webinar": 0.029232531809492687
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 556,
    "completion_tokens": 1,
    "total_tokens": 557,
    "total_time": 1.01
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "webinar",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 543,
    "completion_tokens": 2,
    "total_tokens": 545,
    "total_time": 3.64,
    "time_to_first_token": 3.64
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "webinar",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 570,
    "completion_tokens": 823,
    "total_tokens": 1393,
    "total_time": 1.48,
    "time_to_first_token": 1.48
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "webinar",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 648,
    "completion_tokens": 3175,
    "total_tokens": 3823,
    "total_time": 33.32,
    "time_to_first_token": 33.32
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1969. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}",
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
| openrouter | inception/mercury-decide:free | 556 | 1 | 1.01 | search | 0.9520726297362768 | 0.0 |
| google | gemini-3.5-flash-lite | 543 | 2 | 3.65 | webinar | null | 0.00016790000000000002 |
| groq | openai/gpt-oss-20b | 570 | 823 | 1.48 | webinar | null | 0.00028964999999999997 |
| openrouter | inclusionai/ling-3.1-flash | 648 | 3175 | 33.33 | webinar | null | 0.0 |
| groq | qwen/qwen3.8-27b | 0 | 0 | 0.13 | "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1969. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}" | null | 0.0 |
