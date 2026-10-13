# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:17:59

## Prompt exacto del modelo de decisión

````
Sos el arquitecto que elige el patrón de diseño. El problema:

Tenemos un motor de notificaciones que hoy envía email. El roadmap pide agregar SMS, WhatsApp y push en los próximos 6 meses, cada uno con formato y reintentos distintos, y el equipo de producto quiere poder combinar canales por usuario (por ejemplo email más push para alertas críticas, solo WhatsApp para promociones). El código actual tiene un switch gigante de 400 líneas que ya es difícil de testear: cada cambio rompe otro canal y no hay tests unitarios. Se necesita una estructura donde agregar un canal nuevo no toque el código existente, y donde las combinaciones se armen en tiempo de ejecución según las preferencias de cada usuario.

Restricciones: el equipo es chico (3 desarrolladores), no se puede reescribir todo de cero, y la solución debe poder testearse canal por canal con mocks. El primer canal nuevo (SMS) debe salir en 4 semanas.

Detalle de los canales: el email usa plantillas HTML con 40 variables y reintenta 3 veces con backoff; el SMS tiene límite de 160 caracteres, requiere acortar links y el proveedor cobra por tramo; WhatsApp exige plantillas preaprobadas por Meta y ventana de 24 horas para conversar; el push necesita tokens por dispositivo con expiración y manejo de tokens inválidos. Cada canal tiene su propio proveedor con SDK distinto y sus propios códigos de error. Hoy la tasa de entrega del email es 94 por ciento y el rebote por casillas llenas es el principal motivo de reclamo a soporte. El equipo conoce bien el código actual pero nadie trabajó con WhatsApp Business API. Producto ya prometió a un cliente grande que las alertas críticas llegan por email y push a la vez desde julio.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- strategy: encapsular cada algoritmo o canal en una clase intercambiable con una interfaz común
- observer: notificar automáticamente a múltiples suscriptores cuando cambia el estado del sujeto
- decorator: agregar comportamiento por capas envolviendo objetos en tiempo de ejecución
- factory: centralizar la creación de objetos relacionados detrás de un método creador
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí el patrón que mejor resuelve el problema descripto.",
    "criteria": {
      "strategy": "encapsular cada algoritmo o canal en una clase intercambiable con una interfaz común",
      "observer": "notificar automáticamente a múltiples suscriptores cuando cambia el estado del sujeto",
      "decorator": "agregar comportamiento por capas envolviendo objetos en tiempo de ejecución",
      "factory": "centralizar la creación de objetos relacionados detrás de un método creador"
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
        "choice": "strategy",
        "confidence": 0.9869897174496648,
        "probabilities": {
          "strategy": 0.9902422880872486,
          "observer": 0.0005145047463803648,
          "decorator": 0.005196313861753038,
          "factory": 0.004046893304618061
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 517,
    "completion_tokens": 1,
    "total_tokens": 518,
    "total_time": 0.79
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "strategy",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 491,
    "completion_tokens": 1,
    "total_tokens": 492,
    "total_time": 1.3,
    "time_to_first_token": 1.3
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "strategy",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 552,
    "completion_tokens": 201,
    "total_tokens": 753,
    "total_time": 0.9,
    "time_to_first_token": 0.9
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "strategy: encapsular cada algoritmo o canal en una clase intercambiable con una interfaz común",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 631,
    "completion_tokens": 292,
    "total_tokens": 923,
    "total_time": 4.11,
    "time_to_first_token": 4.11
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1025. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}",
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
| openrouter | inception/mercury-decide:free | 517 | 1 | 0.79 | strategy | 0.9869897174496648 | 0.0 |
| google | gemini-3.5-flash-lite | 491 | 1 | 1.31 | strategy | null | 0.00014979999999999998 |
| groq | openai/gpt-oss-20b | 552 | 201 | 0.91 | strategy | null | 0.00010169999999999999 |
| openrouter | inclusionai/ling-3.1-flash | 631 | 292 | 4.12 | strategy: encapsular cada algoritmo o canal en una clase intercambiable con una interfaz común | null | 0.0 |
| groq | qwen/qwen3.8-27b | 0 | 0 | 0.15 | "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1025. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}" | null | 0.0 |
