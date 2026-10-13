# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 01:47:27

## Prompt exacto del modelo de decisión

````
Sos el comité de arquitectura. Un diseño de invalidación de caché se aprueba solo si garantiza que ningún dato se sirve vencido por más de 60 segundos, no genera thundering herd ante vencimientos masivos, incluye versionado o tags para invalidación selectiva, y tiene plan de rollback que no deja la caché en estado inconsistente. Si falla un punto, se rechaza.

Propuesta del equipo de plataforma, documento ARC-118:
- TTL de 45 segundos en todas las claves de catálogo (12 millones de claves, 800 GB en Redis Cluster de 18 nodos). El peor caso de dato vencido es 45 segundos.
- Vencimientos masivos: a las 00:00 vencen 3 millones de claves juntas por el recambio de lista de precios. Ante vencimiento, solo el primer request regenera y el resto espera con singleflight con timeout de 2 segundos y fallback al valor vencido marcado como stale. Probado en staging con 10x de tráfico simulado: el pico a la base fue de 40 conexiones vs 9000 sin singleflight.
- Invalidación selectiva: cada clave lleva tag por categoría (1200 categorías) y por proveedor (340 proveedores). El panel de administración permite invalidar por tag en un click, con confirmación y dry-run que muestra cuántas claves afecta. Tiempo medio de invalidación por tag medido: 8 segundos.
- Rollback: los deploys versionan las claves (v1 y v2 conviven con prefijo). Si el deploy nuevo falla, el router vuelve a v1 en 30 segundos y un job de limpieza borra v2 después de 10 minutos. Durante la convivencia ambas versiones son válidas y el router dirige a la estable. El game day de abril probó el rollback con tráfico real al 5 por ciento sin inconsistencias.
- Monitoreo: alerta si el hit rate cae debajo de 85 por ciento por más de 5 minutos, y dashboard de edad máxima de dato servido con percentil 99 en 44 segundos.
- Costo: la convivencia de versiones duplica memoria por 10 minutos (pico de 1.6 TB, capacidad disponible 2 TB).

Contexto ampliado de la propuesta ARC-118:

El catálogo tiene 4.2 millones de productos activos y cada ficha promedia 190 KB con descripciones, imágenes en 3 tamaños, precios por lista y stock por depósito. Las 12 millones de claves incluyen fichas, listados por categoría, resultados de búsqueda precacheados y fragmentos de la home. El tráfico es de 90000 lecturas por segundo en pico (19 a 22 horas) y 15000 en valle. La base Postgres primaria está al 70 por ciento de CPU en pico y las réplicas al 55 por ciento; el equipo de base de datos informó que no hay margen para absorber el tráfico sin caché.

Historial de incidentes de caché: en el Hot Sale del año pasado un vencimiento masivo a las 00:00 generó 9000 conexiones simultáneas a la base, que se cayó durante 22 minutos con pérdida estimada de 180000 USD. En marzo de este año una invalidación manual por error borró 2 millones de claves sin tags y el sitio mostró precios de la lista anterior durante 3 horas. En mayo un deploy sin versionado sirvió fichas mezcladas (precio nuevo con descripción vieja) durante 40 minutos. Estos 3 incidentes motivaron la exigencia de los 4 puntos de la regla.

Detalle del recambio de precios: todos los días a las 00:00 entra la lista nueva con 400000 precios actualizados. Hoy el recambio se hace borrando por patrón (KEYS por prefijo, operación bloqueante que tarda 9 minutos y degrada el cluster). La propuesta reemplaza ese borrado por vencimiento natural con TTL de 45 segundos más invalidación por tag para urgencias. El tag por categoría cubre 1200 categorías y el tag por proveedor 340 proveedores; cada clave lleva en promedio 3 tags. El panel de administración lo usan 25 personas de marketing y catálogo con distintos permisos.

Singleflight y fallback: cuando una clave vence, el primer request dispara la regeneración y los siguientes esperan hasta 2 segundos. Si la regeneración tarda más, se sirve el valor vencido con un header que lo marca como stale y se registra en el log. En staging se probó con 10x de tráfico simulado y el pico a la base fue de 40 conexiones. El riesgo registrado es que si la base está caída, todos los requests reciben stale hasta que expire el fallback de 5 minutos, y después empiezan los errores. El documento no detalla qué pasa si el singleflight mismo falla (el coordinador en memoria del gateway), solo dice que hay un timeout.

Versionado y convivencia: cada deploy genera claves con prefijo de versión y el router dirige a la estable. La convivencia dura 10 minutos con pico de memoria de 1.6 TB sobre 2 TB disponibles. El game day de abril probó el rollback con 5 por ciento de tráfico real y midió 30 segundos de cambio de versión sin errores. Lo que no se probó es el rollback con el 100 por ciento del tráfico ni con el cluster al 90 por ciento de memoria. El equipo de plataforma reconoce que si un deploy coincide con el pico de las 20 horas, el margen de memoria es de 400 GB y el monitoreo debe estar mirado por una persona.

Monitoreo y alertas: el dashboard muestra hit rate, edad máxima del dato servido (p99 en 44 segundos en staging), claves por versión y memoria por nodo. La alerta de hit rate debajo de 85 por ciento por 5 minutos pagea al on-call. No hay alerta específica para proporción de respuestas stale: si el 30 por ciento del tráfico recibe stale por una hora, ninguna alerta se dispara mientras el hit rate se mantenga. El equipo de observabilidad propuso agregarla pero quedó fuera del documento.

Costos y alternativas: la convivencia de versiones no tiene costo extra de infraestructura porque usa la capacidad existente. La alternativa de no versionar (deploy directo con purga) fue descartada por el incidente de mayo. La alternativa de TTL más largo (5 minutos) fue descartada porque violaría el tope de 60 segundos de dato vencido. El documento estima 3 semanas de implementación con 2 ingenieros y 1 semana de game days.

Posturas: el equipo de plataforma pide aprobación para empezar ya porque el próximo recambio grande es el Hot Sale en 6 semanas. El equipo de base de datos apoya pero pide que el singleflight tenga un límite de espera configurable por endpoint. El responsable de catálogo pide que la invalidación por tag tenga auditoría de quién invalidó qué (hoy el panel no loguea usuario). Arquitectura ya observó que falta la alerta de stale y el rollback al 100 por ciento de tráfico.

````

### Agregado para LLM tradicional

````
## Tarea
Solo respondé esta pregunta en función a lo indicado por el usuario y devolvé solo la respuesta, sin texto extra, sin argumentar.
Pregunta: Se aprueba el diseño?
````

## Parámetros de modelo de decisión

```json
{
  "noul": {
    "type": "noul",
    "instructions": "Se aprueba el diseño?"
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
        "noul": 0.9859363697800155
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1600,
    "completion_tokens": 1,
    "total_tokens": 1601,
    "total_time": 1.43
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Rechazado",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1586,
    "completion_tokens": 4,
    "total_tokens": 1590,
    "total_time": 0.81,
    "time_to_first_token": 0.81
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "No.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1571,
    "completion_tokens": 413,
    "total_tokens": 1984,
    "total_time": 1.11,
    "time_to_first_token": 1.11
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "No, se rechaza. Falla el punto 1: el fallback de stale de 5 minutos sirve datos vencidos por más de 60 segundos (riesgo reconocido en el documento si la base está caída), y el punto 2 queda sin garantía porque el fallo del coordinador de singleflight no está contemplado, lo que reeditaría el thundering herd de 9000 conexiones.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1887,
    "completion_tokens": 1404,
    "total_tokens": 3291,
    "total_time": 20.28,
    "time_to_first_token": 20.28
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "No se aprueba",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1623,
    "completion_tokens": 5,
    "total_tokens": 1628,
    "total_time": 0.45,
    "time_to_first_token": 0.45
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 1600 | 1 | 1.43 | 0.99 | null | 0.0 |
| google | gemini-3.5-flash-lite | 1586 | 4 | 0.82 | Rechazado | null | 0.0004858 |
| groq | openai/gpt-oss-20b | 1571 | 413 | 1.11 | No. | null | 0.00024172499999999998 |
| openrouter | inclusionai/ling-3.1-flash | 1887 | 1404 | 20.29 | No, se rechaza. Falla el punto 1: el fallback de stale de 5 minutos sirve datos vencidos por más de 60 segundos (riesgo reconocido en el documento si la base está caída), y el punto 2 queda sin garantía porque el fallo del coordinador de singleflight no está contemplado, lo que reeditaría el thundering herd de 9000 conexiones. | null | 0.0 |
| groq | qwen/qwen3.8-27b | 1623 | 5 | 0.46 | No se aprueba | null | 0.0013184000000000002 |
