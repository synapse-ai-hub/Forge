# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:51:07

## Prompt exacto del modelo de decisión

````
Sos el BI manager que puntúa una propuesta de dashboard. Puntuá la propuesta según los criterios indicados.

Dashboard de control para el gerente de e-commerce, un mock en 3 pantallas:
- Pantalla 1: ventas del día vs mismo día semana anterior, con alerta si cae más de 10 por ciento, top 10 productos y conversión por canal. Todo con números grandes y semáforos.
- Pantalla 2: funnel completo (visita, carrito, checkout, pago) con caídas porcentuales por paso y comparación de 7 días.
- Pantalla 3: stock crítico (menos de 5 días de cobertura), reclamos abiertos por estado y NPS semanal con tendencia de 12 semanas.
- Datos: refresco cada 15 minutos desde el warehouse, diccionario de cada métrica con fórmula y dueño, y log de cambios cuando se redefine una métrica.
- Accesos: por rol (el gerente ve todo, los analistas ven sin costos), export a Excel con marca de fecha de extracción.
- Debilidades: no incluye costos de adquisición por canal (el gerente los mira en otra herramienta y hay que cruzar a mano), no hay vista mobile y el gerente revisa todo desde el teléfono, y las alertas solo se ven entrando al dashboard (no llegan por ningún canal).

Más datos: el gerente revisa los números 3 veces al día, 2 de ellas desde el teléfono en viaje. Hoy cruza a mano 4 herramientas y tarda 40 minutos por revisión. El warehouse tiene los datos con 15 minutos de delay y el diccionario de métricas ya existe para 30 de las 40 métricas del mock. El equipo de BI son 2 personas y estiman 5 semanas de trabajo. Los costos de adquisición los tiene la agencia en otra plataforma sin API y habría que cargarlos a mano cada semana. El gerente pidió que las alertas lleguen por WhatsApp pero la propuesta no lo incluye. El export a Excel lo usan 10 analistas para armar reportes que el dashboard debería reemplazar.

Criterios: se valora relevancia de KPIs, accionabilidad, calidad de datos, accesos, diseño mobile y sistema de alertas.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "insuficiente", "1": "aceptable", "2": "bueno", "3": "muy bueno", "4": "excelente"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá la calidad de la propuesta según los criterios.",
    "criteria": [
      "insuficiente",
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
        "score": 1.3143742495360984,
        "confidence": 0.712033787305359,
        "legend": {
          "0": "insuficiente",
          "1": "aceptable",
          "2": "bueno",
          "3": "muy bueno",
          "4": "excelente"
        },
        "probabilities": {
          "0": 0.015592602848735409,
          "1": 0.6630144036035953,
          "2": 0.3131858375815353,
          "3": 0.007840453095103816,
          "4": 0.000366702871030243
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 583,
    "completion_tokens": 1,
    "total_tokens": 584,
    "total_time": 0.67
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "2.2",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 560,
    "completion_tokens": 3,
    "total_tokens": 563,
    "total_time": 1.79,
    "time_to_first_token": 1.79
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "2.5",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 622,
    "completion_tokens": 506,
    "total_tokens": 1128,
    "total_time": 0.92,
    "time_to_first_token": 0.92
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
  "data": "1.8",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 593,
    "completion_tokens": 4,
    "total_tokens": 597,
    "total_time": 0.35,
    "time_to_first_token": 0.35
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 583 | 1 | 0.68 | 1.31 | 0.712033787305359 | 0.0 |
| google | gemini-3.5-flash-lite | 560 | 3 | 1.78 | 2.2 | null | 0.00017549999999999998 |
| groq | openai/gpt-oss-20b | 622 | 506 | 0.93 | 2.5 | null | 0.00019844999999999997 |
| openrouter | inclusionai/ling-3.1-flash | 0 | 0 | 2.28 | "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'inclusionai/ling-3.1-flash is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'provider_name': 'Novita', 'is_byok': False, 'limit_source': 'upstream_provider_shared_pool', 'remedy_hint': 'Retry shortly, add your own provider key (https://openrouter.ai/settings/integrations), or route to another provider with provider routing: https://openrouter.ai/docs/features/provider-routing'}}, 'user_id': 'user_3IHIEaL9108If8k2gSzCi1zx2e3'}" | null | 0.0 |
| groq | qwen/qwen3.8-27b | 593 | 4 | 0.37 | 1.8 | null | 0.0004904 |
