# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:39:10

## Prompt exacto del modelo de decisión

````
Sos el product manager que elige qué construir el próximo trimestre. El equipo tiene capacidad para un solo proyecto grande. Datos RICE (alcance, impacto, confianza, esfuerzo en semanas-persona):

Proyecto A, buscador con filtros facetados: alcance 8000 usuarios, impacto 2 (alto), confianza 80 por ciento, esfuerzo 6. El soporte recibe 400 tickets mensuales porque nadie encuentra nada y el NPS del módulo es -10.

Proyecto B, modo offline: alcance 1500 usuarios, impacto 3 (masivo), confianza 50 por ciento, esfuerzo 10. Lo piden 3 cuentas enterprise que juntas representan el 40 por ciento de la facturación y amenazan con irse si no sale este año.

Proyecto C, dashboard personalizable: alcance 12000 usuarios, impacto 1 (medio), confianza 90 por ciento, esfuerzo 4. Es el feature más votado en el portal de ideas con 2300 votos pero nadie amenaza con irse por esto.

El churn del último trimestre fue 8 por ciento y el board pidió priorizar retención de cuentas grandes sin descuidar la base. El contrato de la cuenta enterprise más grande renueva en 5 meses con cláusula de salida a los 30 días.

Detalle: el proyecto A lo sponsorea soporte (dicen que los tickets les consumen 2 personas full time) pero requiere rediseñar la búsqueda actual que nadie entiende. El proyecto B lo piden las 3 cuentas por escrito con fecha límite diciembre; una ya empezó una prueba piloto con un competidor. El proyecto C lo votó la base pero el análisis muestra que los que votan son usuarios free que casi no pagan. El equipo tiene 5 desarrolladores y un diseñador part time; el trimestre pasado entregó un proyecto de esfuerzo 5 con 2 semanas de atraso. El board mide al PM por retención de revenue, no por votos del portal. El churn del 8 por ciento se compone de 2 enterprise (6 por ciento del revenue) y 400 cuentas chicas.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- buscador: construir el buscador con filtros facetados para reducir tickets y mejorar el NPS
- offline: construir el modo offline para retener las cuentas enterprise en riesgo
- dashboard: construir el dashboard personalizable más votado por la base de usuarios
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí el proyecto a construir según los datos y el contexto.",
    "criteria": {
      "buscador": "construir el buscador con filtros facetados para reducir tickets y mejorar el NPS",
      "offline": "construir el modo offline para retener las cuentas enterprise en riesgo",
      "dashboard": "construir el dashboard personalizable más votado por la base de usuarios"
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
        "choice": "offline",
        "confidence": 0.9888427249076723,
        "probabilities": {
          "buscador": 0.006687829698395581,
          "offline": 0.9925618166051149,
          "dashboard": 0.0007503536964895925
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 569,
    "completion_tokens": 1,
    "total_tokens": 570,
    "total_time": 1.7
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "offline: construir el modo offline para retener las cuentas enterprise en riesgo",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 544,
    "completion_tokens": 14,
    "total_tokens": 558,
    "total_time": 0.8,
    "time_to_first_token": 0.8
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "offline",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 595,
    "completion_tokens": 309,
    "total_tokens": 904,
    "total_time": 0.96,
    "time_to_first_token": 0.96
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "offline: construir el modo offline para retener las cuentas enterprise en riesgo",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 670,
    "completion_tokens": 1092,
    "total_tokens": 1762,
    "total_time": 14.04,
    "time_to_first_token": 14.04
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "offline",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 566,
    "completion_tokens": 2,
    "total_tokens": 568,
    "total_time": 3.01,
    "time_to_first_token": 3.01
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 569 | 1 | 1.72 | offline | 0.9888427249076723 | 0.0 |
| google | gemini-3.5-flash-lite | 544 | 14 | 0.81 | offline: construir el modo offline para retener las cuentas enterprise en riesgo | null | 0.0001982 |
| groq | openai/gpt-oss-20b | 595 | 309 | 0.97 | offline | null | 0.000137325 |
| openrouter | inclusionai/ling-3.1-flash | 670 | 1092 | 14.05 | offline: construir el modo offline para retener las cuentas enterprise en riesgo | null | 0.0 |
| groq | qwen/qwen3.8-27b | 566 | 2 | 3.02 | offline | null | 0.0004608 |
