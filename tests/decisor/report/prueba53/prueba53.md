# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:22:14

## Prompt exacto del modelo de decisión

````
Sos el tech writer que puntúa un README de un repositorio open source. Puntuá el README según los criterios indicados.

README del proyecto (librería de validación de CUIT/CUIL en Python, 400 estrellas):

Tiene título claro con badges de CI, cobertura y versión en PyPI. La instalación es un pip install con el nombre exacto del paquete y la versión mínima de Python. Hay un ejemplo de 10 líneas que funciona copiando y pegando, con el output esperado comentado. La sección de API documenta las 4 funciones públicas con parámetros y retorno. Hay guía de contribución con cómo correr tests y linter. Faltan: no dice cómo reportar vulnerabilidades de seguridad, no hay changelog (hay que adivinar qué cambió entre versiones), los ejemplos no cubren el caso de CUIT inválido con el manejo de la excepción, y la licencia está mencionada pero sin archivo LICENSE en el repo.

Más datos: el proyecto tiene 400 estrellas, 50 issues abiertos (10 sobre instalación en Windows sin respuesta) y 5 PRs sin revisar hace 3 meses. La cobertura es 85 por ciento según el badge pero el badge lleva roto 2 meses (apunta a un build viejo). El ejemplo funciona en Python 3.10 pero falla en 3.12 por un cambio en el manejo de decimales y nadie lo aclaró en el README. Hay 3 forks con fixes que nunca se mergearon. El mantenedor responde issues cada 2 o 3 semanas. La librería se usa en producción en al menos 2 empresas conocidas según los comentarios.

Criterios: se valora instalación, ejemplo funcional, documentación de API, guía de contribución, seguridad y mantenimiento.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "pesimo", "1": "malo", "2": "regular", "3": "bueno", "4": "excelente"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá la calidad del README según los criterios.",
    "criteria": [
      "pesimo",
      "malo",
      "regular",
      "bueno",
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
        "score": 2.793677082516596,
        "confidence": 0.8261931120823818,
        "legend": {
          "0": "pesimo",
          "1": "malo",
          "2": "regular",
          "3": "bueno",
          "4": "excelente"
        },
        "probabilities": {
          "0": 0.00046800015477771207,
          "1": 0.002529984933686472,
          "2": 0.20098162116056673,
          "3": 0.7948977197421,
          "4": 0.0011226740088690313
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 505,
    "completion_tokens": 1,
    "total_tokens": 506,
    "total_time": 1.27
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "2.3",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 463,
    "completion_tokens": 3,
    "total_tokens": 466,
    "total_time": 0.57,
    "time_to_first_token": 0.57
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "3.2",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 521,
    "completion_tokens": 338,
    "total_tokens": 859,
    "total_time": 0.93,
    "time_to_first_token": 0.93
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "2.3",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 556,
    "completion_tokens": 1328,
    "total_tokens": 1884,
    "total_time": 19.22,
    "time_to_first_token": 19.22
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "3.2",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 490,
    "completion_tokens": 4,
    "total_tokens": 494,
    "total_time": 0.3,
    "time_to_first_token": 0.3
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 505 | 1 | 1.27 | 2.79 | 0.8261931120823818 | 0.0 |
| google | gemini-3.5-flash-lite | 463 | 3 | 0.59 | 2.3 | null | 0.0001464 |
| groq | openai/gpt-oss-20b | 521 | 338 | 0.94 | 3.2 | null | 0.00014047499999999999 |
| openrouter | inclusionai/ling-3.1-flash | 556 | 1328 | 19.22 | 2.3 | null | 0.0 |
| groq | qwen/qwen3.8-27b | 490 | 4 | 0.32 | 3.2 | null | 0.000408 |
