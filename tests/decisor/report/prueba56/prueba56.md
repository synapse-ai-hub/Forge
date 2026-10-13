# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:30:12

## Prompt exacto del modelo de decisión

````
Sos el arquitecto que puntúa una propuesta de migración a microservicios. Puntuá la propuesta según los criterios indicados.

Propuesta del equipo para partir un monolito de e-learning (300000 líneas, 8 años de historia):
- Corte por dominios: pagos, catálogo, usuarios y notificaciones como primeros 4 servicios, con matriz de dependencias que muestra que pagos solo depende de usuarios.
- Estrategia strangler fig: el monolito sigue vivo y el tráfico se mueve por endpoints con feature flags, con rollback apagando el flag.
- Datos: cada servicio con su base propia desde el día uno, eventos de dominio para sincronizar catálogo, y plan de consistencia eventual documentado con ejemplos de cada flujo.
- Observabilidad: tracing distribuido obligatorio, dashboards por servicio y alertas por SLO antes de migrar cada endpoint.
- Equipo: 2 personas por servicio con dueño claro, y regla de que nadie toca código de otro servicio sin review del dueño.
- Debilidades: no estima costos de infraestructura duplicada durante la convivencia (calculada en 18 meses), no define cómo se versionan los eventos cuando cambian, y el plan de testing entre servicios es solo una línea que dice se testeará la integración.

Más datos: el monolito factura 2 millones de USD al año y cualquier caída en época de inscripciones cuesta 50000 USD por día. El equipo son 8 desarrolladores que conocen el monolito pero solo 2 trabajaron con eventos. La convivencia estimada es 18 meses con doble infraestructura de 15000 USD mensuales. Los 4 primeros servicios concentran el 70 por ciento de los cambios; el 30 por ciento restante queda en el monolito sin plan. No hay fecha de corte para apagar el monolito ni criterio para decidir qué endpoint migrar primero. El CTO quiere empezar ya y el equipo de plataforma advierte que sin versionado de eventos van a romper consumidores.

Criterios: se valora corte de dominios, estrategia de migración, manejo de datos, observabilidad, organización y estimación de costos.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "mala", "1": "regular", "2": "buena", "3": "muy buena"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá la calidad de la propuesta según los criterios.",
    "criteria": [
      "mala",
      "regular",
      "buena",
      "muy buena"
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
        "score": 1.7112807573406015,
        "confidence": 0.6937287224266915,
        "legend": {
          "0": "mala",
          "1": "regular",
          "2": "buena",
          "3": "muy buena"
        },
        "probabilities": {
          "0": 0.0034367378159573946,
          "1": 0.2906217844844387,
          "2": 0.6971654602426489,
          "3": 0.00877601745695501
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 550,
    "completion_tokens": 1,
    "total_tokens": 551,
    "total_time": 0.67
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
    "prompt_tokens": 536,
    "completion_tokens": 3,
    "total_tokens": 539,
    "total_time": 1.57,
    "time_to_first_token": 1.57
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "2.1",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 591,
    "completion_tokens": 640,
    "total_tokens": 1231,
    "total_time": 1.23,
    "time_to_first_token": 1.23
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "1.4",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 656,
    "completion_tokens": 1194,
    "total_tokens": 1850,
    "total_time": 14.26,
    "time_to_first_token": 14.26
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1523. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}",
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
| openrouter | inception/mercury-decide:free | 550 | 1 | 0.68 | 1.71 | 0.6937287224266915 | 0.0 |
| google | gemini-3.5-flash-lite | 536 | 3 | 1.57 | 1.8 | null | 0.00016829999999999997 |
| groq | openai/gpt-oss-20b | 591 | 640 | 1.25 | 2.1 | null | 0.000236325 |
| openrouter | inclusionai/ling-3.1-flash | 656 | 1194 | 14.27 | 1.4 | null | 0.0 |
| groq | qwen/qwen3.8-27b | 0 | 0 | 0.12 | "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1523. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}" | null | 0.0 |
