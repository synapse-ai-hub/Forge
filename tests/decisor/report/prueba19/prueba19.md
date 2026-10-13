# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 01:53:05

## Prompt exacto del modelo de decisión

````
Sos el triage de reportes de error de una app mobile. Un reporte se clasifica como bug real solo si describe pasos reproducibles, ocurre en la última versión publicada, no es causado por configuración del dispositivo del usuario (modo ahorro, VPN, fecha mal puesta), y al menos otro usuario reportó lo mismo o el equipo lo reprodujo en laboratorio. Si no, se cierra como error de uso.

Reporte 55210, expediente completo:
- Usuario: teléfono gama media con Android 12, app versión 3.4.1 (la última, publicada hace 5 días, con 60 por ciento de adopción). Sin root, fecha y hora automáticas correctas.
- Descripción con pasos: abrir la app, ir a pagar, elegir tarjeta, ingresar CVV, tocar pagar. La app se cierra justo después de ingresar el CVV, siempre: 8 de 8 intentos, con dos tarjetas distintas (Visa y Mastercard), en 3 días distintos.
- Configuración del dispositivo: modo ahorro de batería activado y VPN corporativa siempre conectada (el usuario trabaja en una empresa con MDM). El equipo probó en 2 dispositivos con modo ahorro y VPN activados y no logró reproducirlo en 10 intentos.
- Volumen: 14 usuarios más reportaron el mismo cierre en el mismo paso esta semana. Modelos variados (Samsung, Motorola, Xiaomi), Android 11 a 14. De los 14, 3 confirman no tener modo ahorro ni VPN. Todos están en la versión 3.4.1; en la 3.4.0 nadie reportó esto.
- Laboratorio: con un dispositivo limpio (sin ahorro, sin VPN) y la versión 3.4.1, el equipo reprodujo el cierre 2 de 5 veces. Con la 3.4.0 en el mismo dispositivo, 0 de 5.
- Dato adicional: la 3.4.1 actualizó el SDK del procesador de pagos de la versión 8.2 a 9.0. El changelog del SDK menciona cambios en el manejo del CVV.

````

### Agregado para LLM tradicional

````
## Tarea
Solo respondé esta pregunta en función a lo indicado por el usuario y devolvé solo la respuesta, sin texto extra, sin argumentar.
Pregunta: Es un bug real?
````

## Parámetros de modelo de decisión

```json
{
  "noul": {
    "type": "noul",
    "instructions": "Es un bug real?"
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
        "noul": 0.9875683517308854
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 514,
    "completion_tokens": 1,
    "total_tokens": 515,
    "total_time": 1.56
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 496,
    "completion_tokens": 1,
    "total_tokens": 497,
    "total_time": 1.96,
    "time_to_first_token": 1.96
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 555,
    "completion_tokens": 135,
    "total_tokens": 690,
    "total_time": 0.5,
    "time_to_first_token": 0.5
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 610,
    "completion_tokens": 268,
    "total_tokens": 878,
    "total_time": 3.92,
    "time_to_first_token": 3.92
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "No",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 515,
    "completion_tokens": 2,
    "total_tokens": 517,
    "total_time": 0.42,
    "time_to_first_token": 0.42
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 514 | 1 | 1.56 | 0.99 | null | 0.0 |
| google | gemini-3.5-flash-lite | 496 | 1 | 1.96 | Sí | null | 0.0001513 |
| groq | openai/gpt-oss-20b | 555 | 135 | 0.52 | Sí | null | 8.2125e-05 |
| openrouter | inclusionai/ling-3.1-flash | 610 | 268 | 3.93 | Sí. | null | 0.0 |
| groq | qwen/qwen3.8-27b | 515 | 2 | 0.42 | No | null | 0.00041999999999999996 |
