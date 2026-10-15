# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:40:34

## Prompt exacto del modelo de decisión

````
Sos el data architect que puntúa un modelo de datos. Puntuá el diseño según los criterios indicados.

Modelo para un sistema de reservas de canchas deportivas (Postgres):

Tablas: usuarios(id, nombre, email único, teléfono), canchas(id, nombre, deporte, precio_hora, activa), reservas(id, usuario_id FK, cancha_id FK, inicio timestamptz, fin timestamptz, estado, precio_final). Índices: único en (cancha_id, inicio, fin) para evitar solapes exactos, btree en (cancha_id, inicio) para búsquedas por día, btree en (usuario_id, inicio) para el historial. Check: fin mayor que inicio, precio_final no negativo, estado en lista cerrada. Las reservas se borran físicamente a los 90 días por política de privacidad, con job documentado. Zona horaria: todo en timestamptz con la zona del complejo como default.

Problemas detectados: el índice único en (cancha_id, inicio, fin) no evita solapes parciales (una reserva de 10 a 12 y otra de 11 a 13 conviven sin violar nada), no hay exclusion constraint con tstzrange que sí lo evitaría. El precio_final se guarda pero nada lo recalcula si cambia el precio de la cancha, y no hay tabla de historial de precios. Los borrados físicos rompen los reportes de ocupación histórica que pide el negocio.

Más datos: el sistema maneja 5000 reservas diarias en 40 canchas con picos de 800 concurrentes a las 19:00. Los solapes parciales ya pasaron 5 veces este mes con doble cobro y reclamos. El precio de las canchas cambia 2 veces al año y la última vez hubo que recalcular 20000 reservas a mano. El negocio pide reporte de ocupación por hora y por deporte de los últimos 2 años y hoy no se puede dar. La política de borrado a 90 días la impuso legales sin consultar al negocio. El equipo de backend propuso soft delete pero legales no aprobó el cambio. El modelo lo diseñó un solo desarrollador sin review de DBA.

Criterios: se valora normalización, integridad referencial, prevención de solapes, índices, auditoría y consistencia histórica.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "deficiente", "1": "regular", "2": "bueno", "3": "muy bueno", "4": "excelente"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá la calidad del modelo según los criterios.",
    "criteria": [
      "deficiente",
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
        "score": 0.9154961710557958,
        "confidence": 0.9129884978234764,
        "legend": {
          "0": "deficiente",
          "1": "regular",
          "2": "bueno",
          "3": "muy bueno",
          "4": "excelente"
        },
        "probabilities": {
          "0": 0.09445881577801624,
          "1": 0.8962002714854355,
          "2": 0.00878603850103634,
          "3": 0.000495674373760025,
          "4": 5.919986175190718e-05
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 648,
    "completion_tokens": 1,
    "total_tokens": 649,
    "total_time": 0.72
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "1.2",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 615,
    "completion_tokens": 3,
    "total_tokens": 618,
    "total_time": 6.02,
    "time_to_first_token": 6.02
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "0",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 649,
    "completion_tokens": 254,
    "total_tokens": 903,
    "total_time": 0.77,
    "time_to_first_token": 0.77
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
  "data": "1.5",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 631,
    "completion_tokens": 4,
    "total_tokens": 635,
    "total_time": 0.39,
    "time_to_first_token": 0.39
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 648 | 1 | 0.73 | 0.92 | 0.9129884978234764 | 0.0 |
| google | gemini-3.5-flash-lite | 615 | 3 | 6.02 | 1.2 | null | 0.000192 |
| groq | openai/gpt-oss-20b | 649 | 254 | 0.78 | 0.0 | null | 0.000124875 |
| openrouter | inclusionai/ling-3.1-flash | 0 | 0 | 2.77 | "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'inclusionai/ling-3.1-flash is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'provider_name': 'Novita', 'is_byok': False, 'limit_source': 'upstream_provider_shared_pool', 'remedy_hint': 'Retry shortly, add your own provider key (https://openrouter.ai/settings/integrations), or route to another provider with provider routing: https://openrouter.ai/docs/features/provider-routing'}}, 'user_id': 'user_3IHIEaL9108If8k2gSzCi1zx2e3'}" | null | 0.0 |
| groq | qwen/qwen3.8-27b | 631 | 4 | 0.4 | 1.5 | null | 0.0005208 |
