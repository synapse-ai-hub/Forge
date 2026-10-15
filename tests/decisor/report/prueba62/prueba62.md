# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:46:10

## Prompt exacto del modelo de decisión

````
Sos el UX lead que puntúa un flujo de onboarding. Puntuá el flujo según los criterios indicados.

Onboarding de una app de inversiones para principiantes, 7 pasos:
- Paso 1: pide email y valida formato en vivo, con explicación de para qué se usa cada dato.
- Paso 2: perfil de riesgo con 5 preguntas simples con ejemplos, barra de progreso visible desde el inicio.
- Paso 3: verificación de identidad con foto del DNI y selfie, con guía visual y reintento sin perder lo anterior.
- Paso 4: tutorial interactivo donde el usuario hace una inversión simulada de 1000 pesos antes de poner plata real.
- Paso 5: primer depósito con montos sugeridos (1000, 5000, 10000) y advertencia de riesgo en lenguaje simple.
- Se puede salir y retomar donde quedó en cualquier paso, y hay ayuda contextual en cada pantalla.
- Métricas: 68 por ciento completa el flujo (benchmark del sector 45 por ciento), tiempo medio 6 minutos, paso con más abandono el 3 con 18 por ciento.
- Debilidad: no hay versión para usuarios avanzados que quieren saltear el tutorial, y el paso 3 no ofrece alternativa si la cámara falla.

Más datos: la app tiene 200000 descargas y el onboarding es obligatorio antes de operar. El 18 por ciento que abandona en el paso 3 se reparte entre cámara que falla (6 por ciento), DNI ilegible (7 por ciento) y abandono voluntario (5 por ciento). Los usuarios avanzados son el 15 por ciento del registro y reclaman el tutorial obligatorio en las reviews (nota media 3.2 por este tema). La verificación la hace un proveedor externo que tarda 2 minutos promedio y cobra por intento. El equipo de compliance exige que el tutorial incluya la advertencia de riesgo antes del primer depósito y eso está cumplido. La última versión redujo el flujo de 9 a 7 pasos y la completitud subió de 55 a 68 por ciento.

Criterios: se valora claridad, progresión, educación, recuperabilidad, métricas y flexibilidad.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "malo", "1": "regular", "2": "bueno", "3": "muy bueno", "4": "excelente"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá la calidad del onboarding según los criterios.",
    "criteria": [
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
        "score": 2.5620081647879798,
        "confidence": 0.6287370863475166,
        "legend": {
          "0": "malo",
          "1": "regular",
          "2": "bueno",
          "3": "muy bueno",
          "4": "excelente"
        },
        "probabilities": {
          "0": 0.0006958686879161922,
          "1": 0.002428820374186494,
          "2": 0.4348084189853786,
          "3": 0.5583050613670388,
          "4": 0.003761830585479934
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 615,
    "completion_tokens": 1,
    "total_tokens": 616,
    "total_time": 0.69
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "2.8",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 575,
    "completion_tokens": 3,
    "total_tokens": 578,
    "total_time": 7.76,
    "time_to_first_token": 7.76
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "2.8",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 614,
    "completion_tokens": 261,
    "total_tokens": 875,
    "total_time": 0.89,
    "time_to_first_token": 0.89
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "3.2",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 689,
    "completion_tokens": 1239,
    "total_tokens": 1928,
    "total_time": 15.1,
    "time_to_first_token": 15.1
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "3.4",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 599,
    "completion_tokens": 4,
    "total_tokens": 603,
    "total_time": 0.62,
    "time_to_first_token": 0.62
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 615 | 1 | 0.7 | 2.56 | 0.6287370863475166 | 0.0 |
| google | gemini-3.5-flash-lite | 575 | 3 | 7.76 | 2.8 | null | 0.00017999999999999998 |
| groq | openai/gpt-oss-20b | 614 | 261 | 0.89 | 2.8 | null | 0.00012435 |
| openrouter | inclusionai/ling-3.1-flash | 689 | 1239 | 15.1 | 3.2 | null | 0.0 |
| groq | qwen/qwen3.8-27b | 599 | 4 | 0.63 | 3.4 | null | 0.0004952 |
