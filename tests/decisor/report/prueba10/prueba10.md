# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 01:25:29

## Prompt exacto del modelo de decisión

````
Sos el triage de soporte nivel 1 de una plataforma de facturación electrónica. Un ticket escala a ingeniería solo si se cumplen las tres condiciones juntas: el error es reproducible en más de una cuenta, el cliente ya probó los pasos de la base de conocimiento (limpiar caché, reintentar con otra red, regenerar el certificado), y el impacto es bloqueante (no puede emitir comprobantes). Si falta alguna, se queda en nivel 1.

Ticket 88412, expediente completo:
- Cliente: Distribuidora Sur SA, plan profesional, 45 usuarios activos, cliente desde 2021, sin morosidad.
- Reporte inicial (ayer 9:14): no pueden emitir facturas electrónicas, error 500 con código interno AFIP-REJ-22 en el 100 por ciento de los intentos. Afecta las 3 sucursales (Bahía Blanca, Neuquén, Trelew) y 6 usuarios distintos lo replicaron con capturas.
- Timeline: 9:14 primer reporte, 9:40 se confirma que es total (0 de 63 intentos exitosos), 10:05 el cliente prueba por su cuenta limpiar caché de 4 navegadores (Chrome, Edge, Firefox) sin cambios, 11:20 prueban desde la red del depósito con otro proveedor de internet (Fibertel en vez de Movistar) con el mismo error, 13:05 regeneran el certificado digital y lo reinstalan en las 3 sucursales, 13:40 el error persiste idéntico. Hoy a las 8:00 confirman que sigue igual: 26 horas de bloqueo total.
- Impacto: 230 remitos pendientes de facturar, 14 camiones detenidos esperando comprobantes para circular (costo estimado 900 USD por día en estadías), cierre de mes en 3 días con riesgo de no llegar a facturar 1.2 millones de pesos. La facturación está totalmente detenida: no hay workaround porque el único canal de emisión es la plataforma.
- Reproducibilidad externa: tickets 88419 (Lácteos del Valle, mismo código de error desde las 10:30 de ayer) y 88425 (Repuestos Andinos, mismo código desde las 11:05). Tres cuentas distintas, mismo código, misma ventana temporal.
- Estado del proveedor: la página de AFIP no informa incidentes, pero el conector propio muestra timeouts contra el endpoint de homologación desde ayer a las 9:00.

````

### Agregado para LLM tradicional

````
## Tarea
Solo respondé esta pregunta en función a lo indicado por el usuario y devolvé solo la respuesta, sin texto extra, sin argumentar.
Pregunta: El ticket debe escalar a ingeniería?
````

## Parámetros de modelo de decisión

```json
{
  "noul": {
    "type": "noul",
    "instructions": "El ticket debe escalar a ingeniería?"
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
        "noul": 0.9999724643028303
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 624,
    "completion_tokens": 1,
    "total_tokens": 625,
    "total_time": 0.85
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
    "prompt_tokens": 614,
    "completion_tokens": 1,
    "total_tokens": 615,
    "total_time": 0.62,
    "time_to_first_token": 0.62
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 645,
    "completion_tokens": 70,
    "total_tokens": 715,
    "total_time": 0.53,
    "time_to_first_token": 0.53
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí, el ticket 88412 debe escalar a ingeniería.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 734,
    "completion_tokens": 415,
    "total_tokens": 1149,
    "total_time": 4.73,
    "time_to_first_token": 4.73
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 636,
    "completion_tokens": 2,
    "total_tokens": 638,
    "total_time": 0.57,
    "time_to_first_token": 0.57
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 624 | 1 | 0.86 | 1.0 | null | 0.0 |
| google | gemini-3.5-flash-lite | 614 | 1 | 0.63 | Sí | null | 0.00018669999999999998 |
| groq | openai/gpt-oss-20b | 645 | 70 | 0.53 | Sí. | null | 6.937499999999999e-05 |
| openrouter | inclusionai/ling-3.1-flash | 734 | 415 | 4.73 | Sí, el ticket 88412 debe escalar a ingeniería. | null | 0.0 |
| groq | qwen/qwen3.8-27b | 636 | 2 | 0.57 | Sí | null | 0.0005168 |
