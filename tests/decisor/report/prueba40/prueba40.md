# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:48:11

## Prompt exacto del modelo de decisión

````
Sos el ingeniero que elige la estructura de datos. Requerimiento:

Sistema de turnos médicos con 50000 turnos diarios en 200 consultorios. Operaciones: insertar turnos nuevos, buscar el próximo turno libre de un médico después de una fecha dada, cancelar turnos, y listar todos los turnos de un día ordenados por hora. El 80 por ciento de las operaciones son búsquedas del próximo libre. Hay picos de 2000 operaciones por segundo a las 8 de la mañana cuando se liberan los turnos del día. La memoria disponible es 16 GB y el dataset activo de 30 días entra holgado. Se necesita además detectar doble reserva del mismo médico a la misma hora en tiempo constante.

Detalle: los turnos se liberan en bloque a las 8:00 y en 10 minutos se reservan 30000; el resto del día el tráfico es 10 veces menor. Las cancelaciones son el 15 por ciento y liberan el slot al instante. El listado por día lo usan las recepcionistas (200 concurrentes) y debe paginar de a 50. La doble reserva hoy pasa 3 veces por semana y genera reclamos con obra social.   El sistema actual en MySQL tarda 3 segundos en el pico y se cae 2 veces por mes. El equipo es de 2 desarrolladores que conocen bien hash y listas pero nunca implementaron un árbol balanceado en producción. Hay que migrar sin downtime porque los consultorios atienden de 8 a 20.

Ampliación del requerimiento con operaciones, picos y restricciones:

Operaciones en detalle: insertar turnos nuevos (50000 por día, distribuidos en 200 consultorios), buscar el próximo turno libre de un médico después de una fecha dada (80 por ciento de las operaciones, 1600 por segundo en pico), cancelar turnos (5 por ciento, con reordenamiento de la agenda), y listar todos los turnos de un día ordenados por hora (para la pantalla del consultorio, 200 consultas por minuto a las 8:00). La búsqueda del próximo libre debe responder en menos de 100ms en p95 porque la recepcionista lo hace con el paciente al teléfono. Hoy en MySQL tarda 3 segundos en el pico y se cae 2 veces por mes (la última caída dejó 40 consultorios sin agenda por 2 horas).

Picos y memoria: picos de 2000 operaciones por segundo a las 8:00 cuando se liberan los turnos del día (los 200 consultorios abren a la vez). La memoria disponible para la estructura es 4 GB en el servidor actual. Hay 50000 turnos diarios con 30 días de ventana (1.5 millones de turnos activos). Cada turno ocupa 200 bytes con datos del paciente (nombre, obra social, teléfono). El 60 por ciento de los turnos son con obra social y requieren validación extra contra el padrón (otra consulta, fuera de esta estructura).

Equipo y conocimiento: 2 desarrolladores que conocen bien hash y listas pero nunca implementaron un árbol balanceado en producción. Uno hizo un curso de estructuras hace 2 años. El equipo usa Python y la librería estándar (bisect, heapq, sortedcontainers no está aprobada por seguridad). Hay 6 semanas para la migración y los consultorios atienden de 8 a 20 sin downtime posible (la migración debe ser en caliente con doble escritura durante 1 semana). El gerente de tecnología prefiere una estructura que el equipo pueda mantener sin depender de un experto externo.

Alternativas evaluadas: el equipo probó un dict con listas por médico (búsqueda lineal del próximo libre: 800ms en pico, no alcanza), una lista ordenada con bisect (inserción O(n): 2 segundos con 1.5 millones de turnos), y un heap por médico (no sirve para listar ordenado ni para cancelar en el medio). Falta evaluar el árbol balanceado (búsqueda e inserción logarítmicas, orden natural, pero el equipo nunca lo implementó) y una tabla hash con buckets por día (rápida pero con picos de memoria en la migración). El equipo pide una recomendación con números de complejidad y riesgo de implementación.
Estructuras candidatas: el equipo evalúa hash con listas, lista ordenada con bisect, heap por médico, árbol balanceado y hash con buckets por día, y pide una recomendación que cumpla los 100ms en pico y que el equipo pueda mantener.

Migración en caliente: el plan es doble escritura durante 1 semana (MySQL y la estructura nueva en paralelo) con verificación nocturna de consistencia. Si hay divergencias, se usa MySQL como fuente de verdad. El corte final es un domingo a las 22:00 con 2 horas de ventana (los consultorios cierran a las 20:00 y hay margen). El rollback es volver a MySQL con 1 hora de trabajo. El equipo ya hizo una migración similar para el padrón de obras sociales el año pasado sin incidentes.

Números de cada estructura: hash con listas (búsqueda del próximo libre O(n) por médico: 800ms en pico, no cumple los 100ms), lista ordenada con bisect (búsqueda O(log n) pero inserción O(n): 2 segundos con 1.5 millones de turnos, no cumple), heap por médico (próximo libre O(1) pero cancelar y listar ordenado son O(n): no cumple las 4 operaciones), árbol balanceado (las 4 operaciones en O(log n): 5ms estimados en pico, cumple todo, pero el equipo nunca lo implementó y hay riesgo de bugs en 6 semanas), hash con buckets por día (próximo libre O(1) amortizado con buckets ordenados, inserción O(1), memoria 20 por ciento mayor: 4.8 GB contra 4 GB disponibles, exige pedir más memoria). El servidor no se puede ampliar antes de la migración (compra aprobada para el trimestre que viene). La recomendación debe cumplir los 100ms en pico con 4 GB y con un equipo que conoce hash y listas pero no árboles. El gerente acepta comprar memoria después del corte si la estructura lo justifica, pero no antes.

Comparación final de estructuras: hash con listas (el equipo la domina, implementación 1 semana, pero 800ms en pico: no cumple y repite la caída actual de 3 segundos), lista ordenada con bisect (implementación 1 semana con la estándar, pero inserción de 2 segundos con 1.5 millones: no cumple y empeora con el crecimiento), heap por médico (próximo libre instantáneo pero cancelar y listar son lineales: no cumple las 4 operaciones y la pantalla del consultorio se vuelve lenta), árbol balanceado (cumple las 4 en 5ms con 1.5 millones, memoria 3.5 GB dentro de los 4 GB, pero 4 semanas de implementación con riesgo de bugs para un equipo que nunca hizo uno), hash con buckets por día (cumple las 4 en tiempo constante, implementación 2 semanas con lo que el equipo sabe, pero 4.8 GB superan los 4 GB y exige comprar memoria que llega el trimestre que viene). La librería sortedcontainers (árbol listo para usar) no está aprobada por seguridad y su aprobación tarda 3 semanas. La recomendación debe cumplir 100ms, 4 GB y 6 semanas con 2 desarrolladores que conocen hash y listas.

Decisión del ingeniero: debe elegir 1 estructura para la migración en caliente (doble escritura 1 semana, corte un domingo a las 22:00, rollback a MySQL en 1 hora) con 6 semanas de plazo y 2 desarrolladores. Las restricciones son 100ms en p95 con 2000 operaciones por segundo, 4 GB de memoria, las 4 operaciones (insertar, próximo libre, cancelar, listar ordenado), y mantenimiento por el equipo actual sin expertos externos. La estructura elegida se implementa en Python con la estándar (bisect, heapq, dict) salvo que seguridad apruebe sortedcontainers (3 semanas de trámite que comen la mitad del plazo). El corte no se puede mover (los consultorios atienden de 8 a 20 y el domingo a las 22:00 es la única ventana de 2 horas). Si la estructura falla en el pico de las 8:00, 200 consultorios quedan sin agenda como en las 2 caídas mensuales actuales.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- lista: lista ordenada con búsqueda binaria e inserción con desplazamiento
- arbol: árbol balanceado indexado por médico y fecha
- hash: tabla hash por médico combinada con lista ordenada por día
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí la estructura que mejor cumple las operaciones y los picos.",
    "criteria": {
      "lista": "lista ordenada con búsqueda binaria e inserción con desplazamiento",
      "arbol": "árbol balanceado indexado por médico y fecha",
      "hash": "tabla hash por médico combinada con lista ordenada por día"
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
        "choice": "arbol",
        "confidence": 0.9998682229112367,
        "probabilities": {
          "lista": 1.3006152504101634e-05,
          "arbol": 0.9999121486074912,
          "hash": 7.484524000464189e-05
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2007,
    "completion_tokens": 1,
    "total_tokens": 2008,
    "total_time": 1.38
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "hash: tabla hash por médico combinada con lista ordenada por día",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1987,
    "completion_tokens": 13,
    "total_tokens": 2000,
    "total_time": 0.91,
    "time_to_first_token": 0.91
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "arbol",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1984,
    "completion_tokens": 400,
    "total_tokens": 2384,
    "total_time": 0.88,
    "time_to_first_token": 0.88
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "hash: tabla hash por médico combinada con lista ordenada por día",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2369,
    "completion_tokens": 3688,
    "total_tokens": 6057,
    "total_time": 38.47,
    "time_to_first_token": 38.47
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1940. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}",
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

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 2007 | 1 | 1.38 | arbol | 0.9998682229112367 | 0.0 |
| google | gemini-3.5-flash-lite | 1987 | 13 | 0.91 | hash: tabla hash por médico combinada con lista ordenada por día | null | 0.0006286 |
| groq | openai/gpt-oss-20b | 1984 | 400 | 0.89 | arbol | null | 0.0002688 |
| openrouter | inclusionai/ling-3.1-flash | 2369 | 3688 | 38.47 | hash: tabla hash por médico combinada con lista ordenada por día | null | 0.0 |
| groq | qwen/qwen3.8-27b | 0 | 0 | 0.16 | "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1940. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}" | null | 0.0 |
