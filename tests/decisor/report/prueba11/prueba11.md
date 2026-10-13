# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 01:26:37

## Prompt exacto del modelo de decisión

````
Sos el guardián de deploys a producción. Un deploy se aprueba solo si pasaron todos los checks del pipeline: tests unitarios al 100 por ciento, cobertura mínima de 80 por ciento en el módulo tocado, sin vulnerabilidades críticas en el scan de dependencias, migración de base marcada como reversible, y aprobación de dos revisores humanos. Un solo check en rojo bloquea el deploy.

Resultado del pipeline para el release 4.18.2 (rama release/4.18, commit 9f3ac21 auditado):
- Tests unitarios: 1243 pasados, 0 fallados, 0 skipeados, en 8 minutos 12 segundos. Incluye 41 tests nuevos del cambio de redondeo de facturas.
- Tests de integración: 187 pasados, 0 fallados (informativo, no bloqueante por política del equipo).
- Cobertura del módulo facturación (el único tocado según el diff: 6 archivos, 412 líneas agregadas, 88 eliminadas): 87.4 por ciento, con las líneas sin cubrir marcadas como defensivas (logs de error y asserts).
- Cobertura global del repo: 81.2 por ciento.
- Scan de dependencias (Trivy + Dependabot): 0 críticas, 2 altas. Alta 1: librería de logging usada solo en el entorno de desarrollo, sin ruta a producción (el SBOM del artefacto no la incluye). Alta 2: paquete deprecado que este mismo release elimina del requirements (el diff lo borra). El informe del scan las marca a ambas como no explotables en el artefacto final.
- Migración 0042_agrega_indice_facturas: CREATE INDEX CONCURRENTLY (sin lock de escritura), marcada como reversible, con script down probado en staging ayer (rollback medido en 40 segundos). No toca datos, solo agrega índice.
- Revisiones humanas: aprobada por Lucía Fernández (backend senior, revisó la lógica de redondeo) y por Marco Ruiz (DBA, revisó la migración), sin comentarios pendientes. Un tercer revisor dejó un comentario de estilo ya resuelto.
- Chequeos extra: el changelog está firmado, el tag v4.18.2 coincide con el commit auditado, y el canary en el 5 por ciento del tráfico durante 2 horas mostró error rate 0.01 por ciento (baseline 0.01 por ciento).

````

### Agregado para LLM tradicional

````
## Tarea
Solo respondé esta pregunta en función a lo indicado por el usuario y devolvé solo la respuesta, sin texto extra, sin argumentar.
Pregunta: Se aprueba el deploy a producción?
````

## Parámetros de modelo de decisión

```json
{
  "noul": {
    "type": "noul",
    "instructions": "Se aprueba el deploy a producción?"
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
        "noul": 0.9995121428361189
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 614,
    "completion_tokens": 1,
    "total_tokens": 615,
    "total_time": 0.89
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
    "prompt_tokens": 592,
    "completion_tokens": 1,
    "total_tokens": 593,
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
  "data": "Sí",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 631,
    "completion_tokens": 124,
    "total_tokens": 755,
    "total_time": 0.75,
    "time_to_first_token": 0.75
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
    "prompt_tokens": 691,
    "completion_tokens": 251,
    "total_tokens": 942,
    "total_time": 3.3,
    "time_to_first_token": 3.3
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí, se aprueba el deploy.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 611,
    "completion_tokens": 9,
    "total_tokens": 620,
    "total_time": 0.44,
    "time_to_first_token": 0.44
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 614 | 1 | 0.91 | 1.0 | null | 0.0 |
| google | gemini-3.5-flash-lite | 592 | 1 | 0.66 | Sí | null | 0.00018010000000000001 |
| groq | openai/gpt-oss-20b | 631 | 124 | 0.77 | Sí | null | 8.4525e-05 |
| openrouter | inclusionai/ling-3.1-flash | 691 | 251 | 3.3 | Sí. | null | 0.0 |
| groq | qwen/qwen3.8-27b | 611 | 9 | 0.44 | Sí, se aprueba el deploy. | null | 0.0005248000000000001 |
