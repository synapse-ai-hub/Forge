# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:12:55

## Prompt exacto del modelo de decisión

````
Sos el clasificador de tickets de una empresa de software. Llegó este ticket:

Asunto: Me cobraron dos veces la suscripción de abril
Cuerpo: Hola, soy cliente del plan anual desde 2023. En el resumen de mi tarjeta veo dos cargos idénticos de 8990 pesos el 3 de abril con números de operación distintos (OP-88112 y OP-88119). Ya revisé y solo tengo una suscripción activa a mi nombre, sin usuarios extra ni cambios de plan este mes. Necesito que me devuelvan uno de los cargos urgente porque me dejó sin límite para otros pagos. Adjunto capturas de ambos cargos y del resumen. Mi cuenta es juan.perez@example.com, cliente 45231. El vencimiento de la tarjeta opera el 10 de abril y necesito el reintegro antes para no pagar intereses.

Historial del cliente: paga en fecha desde 2023, plan anual renovado en enero sin cambios. En noviembre tuvo un reclamo por un cargo duplicado de un add-on que se resolvió con nota de crédito en 48 horas. El sistema antifraude marcó score 12 sobre 100 (bajo) para ambas operaciones, mismo dispositivo y misma IP de siempre. Las dos operaciones tienen 4 minutos de diferencia (14:02 y 14:06) y el log muestra que el usuario apretó pagar dos veces porque la primera quedó en spinner. La política de devoluciones dice que los duplicados con evidencia se reintegran sin pasar por riesgo. El equipo de ingeniería confirmó que hubo un bug de doble submit en el checkout esa tarde que afectó a 30 clientes.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- facturacion: derivar al equipo de billing por cobros, devoluciones y suscripciones
- soporte_tecnico: derivar a ingeniería por errores, caídas o bugs de la plataforma
- ventas: derivar al equipo comercial por nuevos planes, upgrades o cotizaciones
- fraude: derivar al equipo de riesgo por accesos no autorizados o cargos desconocidos
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí el equipo que debe atender el ticket.",
    "criteria": {
      "facturacion": "derivar al equipo de billing por cobros, devoluciones y suscripciones",
      "soporte_tecnico": "derivar a ingeniería por errores, caídas o bugs de la plataforma",
      "ventas": "derivar al equipo comercial por nuevos planes, upgrades o cotizaciones",
      "fraude": "derivar al equipo de riesgo por accesos no autorizados o cargos desconocidos"
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
        "choice": "facturacion",
        "confidence": 0.9995432885913714,
        "probabilities": {
          "facturacion": 0.9996574664435286,
          "soporte_tecnico": 0.0002611691122336876,
          "ventas": 6.5382407910703315e-06,
          "fraude": 7.482620344666883e-05
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 533,
    "completion_tokens": 1,
    "total_tokens": 534,
    "total_time": 0.91
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "facturacion",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 496,
    "completion_tokens": 3,
    "total_tokens": 499,
    "total_time": 0.66,
    "time_to_first_token": 0.66
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "facturacion",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 536,
    "completion_tokens": 51,
    "total_tokens": 587,
    "total_time": 0.47,
    "time_to_first_token": 0.47
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "facturacion: derivar al equipo de billing por cobros, devoluciones y suscripciones",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 618,
    "completion_tokens": 284,
    "total_tokens": 902,
    "total_time": 4.07,
    "time_to_first_token": 4.07
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "facturacion",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 512,
    "completion_tokens": 3,
    "total_tokens": 515,
    "total_time": 0.37,
    "time_to_first_token": 0.37
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 533 | 1 | 0.91 | facturacion | 0.9995432885913714 | 0.0 |
| google | gemini-3.5-flash-lite | 496 | 3 | 0.67 | facturacion | null | 0.00015629999999999998 |
| groq | openai/gpt-oss-20b | 536 | 51 | 0.47 | facturacion | null | 5.5499999999999994e-05 |
| openrouter | inclusionai/ling-3.1-flash | 618 | 284 | 4.07 | facturacion: derivar al equipo de billing por cobros, devoluciones y suscripciones | null | 0.0 |
| groq | qwen/qwen3.8-27b | 512 | 3 | 0.37 | facturacion | null | 0.00042160000000000006 |
