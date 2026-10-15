# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:56:02

## Prompt exacto del modelo de decisión

````
Sos el hiring manager que elige el track de entrevistas. Candidata:

Paula Torres aplica a data engineer semi-senior. Tiene 3 años de experiencia: 2 años como analista BI armando dashboards y 1 año como data engineer en una startup donde mantuvo pipelines en Airflow y modelos en dbt sobre BigQuery. En la entrevista técnica resolvió bien el ejercicio de SQL pero flojeó en diseño de sistemas distribuidos y nunca trabajó con streaming (todo batch diario). El puesto requiere mantener los pipelines batch actuales desde el día uno y en 6 meses liderar la migración a streaming con Kafka, con mentoría del staff engineer. El equipo necesita alguien productivo rápido pero con potencial de crecimiento. Hay otros 2 candidatos en proceso: uno senior caro que pide 40 por ciento más del presupuesto, y un junior que necesitaría 1 año de formación.

Más datos: en su trabajo actual mantiene 30 DAGs con 99 por ciento de éxito y documentó todo el linaje; su jefe dice que es la que más rápido aprende del equipo. En la entrevista de cultura mostró mucha motivación por streaming y ya hizo un curso de Kafka (sin práctica real). El staff engineer que la mentorearía tiene 2 horas semanales disponibles y ya mentorea a otra persona. El senior caro tiene 8 años con Kafka en producción pero en la entrevista mostró poco interés en mentorear y pidió home office full desde otro país. El junior es referido interno con 6 meses de experiencia. El puesto lleva 4 meses abierto y el equipo está sobrecargado cubriendo las guardias.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- senior: avanzar al track senior con énfasis en diseño de sistemas
- semisenior: avanzar al track semi-senior con foco en batch actual y potencial
- descartar: cerrar el proceso con ella y seguir buscando candidatos
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí el track según el perfil y la necesidad del puesto.",
    "criteria": {
      "senior": "avanzar al track senior con énfasis en diseño de sistemas",
      "semisenior": "avanzar al track semi-senior con foco en batch actual y potencial",
      "descartar": "cerrar el proceso con ella y seguir buscando candidatos"
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
        "choice": "semisenior",
        "confidence": 0.997541159844419,
        "probabilities": {
          "senior": 0.001324605408727988,
          "semisenior": 0.9983607732296126,
          "descartar": 0.00031462136165934587
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 456,
    "completion_tokens": 1,
    "total_tokens": 457,
    "total_time": 5.7
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "semisenior: avanzar al track semi-senior con foco en batch actual y potencial",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 425,
    "completion_tokens": 17,
    "total_tokens": 442,
    "total_time": 1.46,
    "time_to_first_token": 1.46
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "semisenior",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 498,
    "completion_tokens": 148,
    "total_tokens": 646,
    "total_time": 0.51,
    "time_to_first_token": 0.51
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "semisenior: avanzar al track semi-senior con foco en batch actual y potencial",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 554,
    "completion_tokens": 619,
    "total_tokens": 1173,
    "total_time": 7.09,
    "time_to_first_token": 7.09
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "semisenior: avanzar al track semi-senior con foco en batch actual y potencial",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 449,
    "completion_tokens": 19,
    "total_tokens": 468,
    "total_time": 0.37,
    "time_to_first_token": 0.37
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 456 | 1 | 5.71 | semisenior | 0.997541159844419 | 0.0 |
| google | gemini-3.5-flash-lite | 425 | 17 | 1.46 | semisenior: avanzar al track semi-senior con foco en batch actual y potencial | null | 0.00017 |
| groq | openai/gpt-oss-20b | 498 | 148 | 0.52 | semisenior | null | 8.175000000000001e-05 |
| openrouter | inclusionai/ling-3.1-flash | 554 | 619 | 7.1 | semisenior: avanzar al track semi-senior con foco en batch actual y potencial | null | 0.0 |
| groq | qwen/qwen3.8-27b | 449 | 19 | 0.37 | semisenior: avanzar al track semi-senior con foco en batch actual y potencial | null | 0.00043520000000000006 |
