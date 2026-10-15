# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:50:45

## Prompt exacto del modelo de decisión

````
Sos el tech lead que elige cómo refactorizar. Código heredado:

Un módulo de 4500 líneas en un solo archivo calcula comisiones de vendedores con 40 ifs anidados, sin tests, con variables globales y con la lógica de 3 países mezclada (Argentina, Chile y Uruguay tienen reglas distintas de impuestos y redondeo). Cada cambio rompe algo de otro país: el último fix para Chile rompió el redondeo de Uruguay y costó 12000 USD en comisiones mal pagadas. El equipo le tiene miedo al archivo y tarda 3 días en promedio por cambio chico. Hay que agregar Perú en 2 meses. No se puede parar el desarrollo de features porque el negocio sigue pidiendo cambios cada semana.

Detalle: el archivo lo escribió un consultor que ya no está y nadie entiende las 200 líneas de redondeo con comentarios en otro idioma. Hay 3 copias del archivo en distintas ramas con fixes distintos sin mergear. El cálculo alimenta la liquidación de sueldos del día 5, así que un error afecta 400 vendedores. El negocio pide para el mes que viene un cambio en el esquema de Chile y para el otro la entrada de Perú con reglas todavía sin definir. El equipo son 4 desarrolladores que nunca hicieron refactor grande; 2 entraron hace 3 meses. La última vez que intentaron reescribir algo (el módulo de facturación) tardaron el doble y lo revertieron. No hay ambiente de pruebas con datos reales de comisiones.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- reescritura: reescribir el módulo completo desde cero con el equipo dedicado
- gradual: refactor por extracción con tests de caracterización y separación por país
- congelar: congelar lo viejo y construir lo nuevo en un servicio aparte
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí la estrategia de refactor según el contexto.",
    "criteria": {
      "reescritura": "reescribir el módulo completo desde cero con el equipo dedicado",
      "gradual": "refactor por extracción con tests de caracterización y separación por país",
      "congelar": "congelar lo viejo y construir lo nuevo en un servicio aparte"
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
        "choice": "gradual",
        "confidence": 0.9430491402962548,
        "probabilities": {
          "reescritura": 0.005048285192747779,
          "gradual": 0.9620327601975031,
          "congelar": 0.032918954609749106
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 446,
    "completion_tokens": 1,
    "total_tokens": 447,
    "total_time": 1.31
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "gradual",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 425,
    "completion_tokens": 2,
    "total_tokens": 427,
    "total_time": 1.36,
    "time_to_first_token": 1.36
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "gradual",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 484,
    "completion_tokens": 117,
    "total_tokens": 601,
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
  "data": "gradual",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 533,
    "completion_tokens": 537,
    "total_tokens": 1070,
    "total_time": 9.18,
    "time_to_first_token": 9.18
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "gradual",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 440,
    "completion_tokens": 3,
    "total_tokens": 443,
    "total_time": 0.3,
    "time_to_first_token": 0.3
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 446 | 1 | 1.32 | gradual | 0.9430491402962548 | 0.0 |
| google | gemini-3.5-flash-lite | 425 | 2 | 1.37 | gradual | null | 0.00013250000000000002 |
| groq | openai/gpt-oss-20b | 484 | 117 | 0.47 | gradual | null | 7.14e-05 |
| openrouter | inclusionai/ling-3.1-flash | 533 | 537 | 9.19 | gradual | null | 0.0 |
| groq | qwen/qwen3.8-27b | 440 | 3 | 0.31 | gradual | null | 0.000364 |
