# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:31:23

## Prompt exacto del modelo de decisión

````
Sos el líder técnico que elige la estrategia de caché. Situación:

Un ecommerce con 2 millones de visitas diarias tiene el catálogo en Postgres. El 95 por ciento del tráfico son lecturas del catálogo, los precios cambian 3 veces por día por promociones, y el stock debe ser exacto al momento de pagar (no se puede vender sin stock). Hoy la base está al 90 por ciento de CPU en picos y la página de categoría tarda 900ms. El equipo probó cachear todo por 1 hora pero generó reclamos por precios viejos y ventas sin stock. Necesitan bajar la base a menos del 50 por ciento de CPU sin mostrar datos incorrectos en el checkout. El pico del Hot Sale es en 3 semanas y esperan el triple de tráfico.

Arquitectura: Postgres primario con 2 réplicas de lectura, 64 GB de RAM, 12000 IOPS. Las fichas de producto pesan 40 KB promedio y el catálogo activo son 80000 productos. El checkout lee stock con SELECT FOR UPDATE y no puede tolerar datos viejos ni por segundos. Las promociones las carga el equipo de marketing en un admin que escribe directo a la base sin eventos. El equipo nunca implementó invalidación por eventos y estima 3 semanas de trabajo.   Redis ya está instalado para sesiones (hit rate 98 por ciento) con 30 GB libres. En el último Hot Sale la base llegó al 100 por ciento de CPU durante 40 minutos y se perdieron 15000 USD en ventas por timeouts.

Ampliación del caso con tráfico, datos y equipo:

Tráfico y picos: 2 millones de visitas diarias con 95 por ciento de lecturas de catálogo. Los picos son a las 12:00 y 20:00 (3 veces el promedio) y en eventos (Hot Sale: 10 veces el promedio durante 3 días). La página de categoría tarda 900ms en p50 y 2500ms en p95 durante picos. El objetivo es p95 bajo 500ms. La base está al 90 por ciento de CPU en picos normales y al 100 por ciento durante 40 minutos en el último Hot Sale (15000 USD perdidos en timeouts). Escalar la base verticalmente cuesta 3000 USD más por mes y solo da 30 por ciento más de CPU.

Catálogo y cambios: 800000 productos en 400 categorías. Los precios cambian 3 veces por día por promociones (a las 8:00, 13:00 y 19:00) y el stock cambia en tiempo real con cada venta (5000 ventas por hora en pico). El stock debe ser exacto al pagar: no se puede vender sin stock (política comercial por 2 incidentes de sobreventa en 2024 con 200 pedidos cancelados y 50000 USD en compensaciones). Los precios tienen tolerancia de 5 minutos (un precio viejo de hasta 5 minutos es aceptable según comercial), pero el stock no tiene tolerancia.

Prueba fallida de caché total: el equipo probó cachear todo el catálogo por 1 hora en Redis y generó 300 reclamos en 1 día por precios viejos (las promociones de las 13:00 no se veían hasta las 14:00). Se revirtió en 24 horas. El aprendizaje documentado es que precio y stock necesitan estrategias distintas: el precio tolera minutos, el stock no tolera nada. El equipo nunca implementó invalidación por eventos y estima 3 semanas de trabajo para un consumidor de eventos de precio y stock (hay un bus de eventos con los cambios, usado hoy solo para el buscador).

Redis disponible: instalado para sesiones con hit rate de 98 por ciento, 30 GB libres de 64 GB, latencia p99 de 2ms. El equipo lo opera hace 2 años sin incidentes. Hay runbooks de failover y monitoreo. Agregar el catálogo consumiría 15 GB estimados (ficha de producto serializada de 20 KB por 800000 productos, con compresión). El presupuesto permite subir a 128 GB por 500 USD más por mes si hace falta.

Equipo y tiempos: 4 desarrolladores backend, ninguno implementó invalidación por eventos antes. El próximo Hot Sale es en 8 semanas y el objetivo es no repetir los timeouts. El gerente de tecnología pide una estrategia que el equipo pueda implementar en 4 semanas con lo que ya opera (Redis) sin sumar sistemas nuevos que no sepan operar. Hay un spike de 1 semana ya hecho que valida TTL corto para precios y lectura directa para stock, pero sin números de producción.
Opciones de caché: el equipo evalúa 3 estrategias (TTL corto para todo, eventos para precio con lectura directa de stock, y caché solo de fichas con stock en vivo) y pide una recomendación con el tradeoff de cada una en CPU, frescura y complejidad.

Números del spike: con TTL de 60 segundos para fichas y stock en vivo desde la base, la CPU bajó de 90 a 55 por ciento en prueba de carga con la mitad del tráfico de pico. El p95 de categoría bajó de 2500ms a 600ms. El spike no probó invalidación por eventos ni el comportamiento con los 3 cambios de precio diarios. El equipo estima que la invalidación por eventos bajaría la CPU a 40 por ciento pero llevaría 3 semanas extra. La decisión es si alcanza con TTL corto para el Hot Sale o si se invierte en eventos ahora.

Proyección para el Hot Sale: con 10 veces el tráfico promedio, el TTL de 60 segundos llevaría la CPU al 85 por ciento estimado (por encima del 70 por ciento que el equipo considera seguro). Con invalidación por eventos la proyección es 60 por ciento. El riesgo del TTL corto es que un cambio de precio tarda hasta 60 segundos en verse (dentro de la tolerancia de 5 minutos de comercial) pero el stock en vivo desde la base suma 200ms por consulta de stock en pico (la base seguiría recibiendo 5000 consultas de stock por hora). El gerente comercial aceptó precios con hasta 5 minutos de demora pero no acepta vender sin stock bajo ningún concepto. El bus de eventos ya publica los cambios de precio y stock (lo usa el buscador) y el consumidor nuevo tardaría 3 semanas según la estimación del equipo (que nunca hizo uno). El Hot Sale es en 8 semanas y la implementación debe estar lista en 4 para probar con 2 semanas de carga. La recomendación debe decir qué estrategia se implementa ahora y qué queda para después del Hot Sale.

Comparación final de estrategias: TTL corto para todo (implementación 1 semana, CPU proyectada 85 por ciento en Hot Sale, precio con hasta 60 segundos de demora, stock con hasta 60 segundos de demora: viola la política de stock exacto y arriesga otra sobreventa como las 2 de 2024), eventos para precio con stock en vivo (implementación 4 semanas: 3 del consumidor más 1 de pruebas, CPU 60 por ciento, precio instantáneo, stock exacto con 200ms extra por consulta, cumple todo pero sin margen si el consumidor se demora), caché de fichas con stock en vivo (implementación 2 semanas, CPU 70 por ciento, precio con 60 segundos de demora dentro de tolerancia, stock exacto, cumple todo con el equipo actual y deja 2 semanas de pruebas). El gerente de tecnología prefiere la tercera porque el equipo la puede hacer en 2 semanas con Redis (que opera hace 2 años) y deja margen antes del Hot Sale. El riesgo de la segunda es que el equipo nunca hizo un consumidor de eventos y la estimación de 3 semanas puede duplicarse (entonces no llega al Hot Sale). La recomendación debe elegir una y decir qué se hace con las otras dos después del evento.

Decisión del líder técnico: debe elegir 1 estrategia para implementar ya (4 semanas disponibles, 2 de pruebas, Hot Sale en 8 semanas) con 4 desarrolladores que operan Redis hace 2 años y nunca hicieron un consumidor de eventos. Las restricciones son CPU bajo 70 por ciento en Hot Sale, precio con hasta 5 minutos de demora aceptable, stock exacto sin excepciones, y sin sistemas nuevos que el equipo no sepa operar. La estrategia elegida se implementa ahora; las otras 2 quedan para después del Hot Sale (el gerente ya dijo que la de eventos se hará en el trimestre siguiente con capacitación previa). La recomendación se presenta mañana en la revisión técnica con el gerente comercial (que defiende la frescura) y el gerente de tecnología (que defiende el plazo).

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- todo: cachear el catálogo completo con expiración fija por tiempo
- selectiva: cachear fichas con invalidación por eventos de precio y stock
- sesiones: no cachear catálogo y cachear solo sesiones y carritos
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí la estrategia que mejor cumple las restricciones.",
    "criteria": {
      "todo": "cachear el catálogo completo con expiración fija por tiempo",
      "selectiva": "cachear fichas con invalidación por eventos de precio y stock",
      "sesiones": "no cachear catálogo y cachear solo sesiones y carritos"
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
        "choice": "selectiva",
        "confidence": 0.8912655575615474,
        "probabilities": {
          "todo": 0.04075196558387834,
          "selectiva": 0.9275103717076982,
          "sesiones": 0.031737662708423396
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2055,
    "completion_tokens": 1,
    "total_tokens": 2056,
    "total_time": 1.62
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "selectiva",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2041,
    "completion_tokens": 2,
    "total_tokens": 2043,
    "total_time": 1.93,
    "time_to_first_token": 1.93
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "selectiva",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2007,
    "completion_tokens": 1149,
    "total_tokens": 3156,
    "total_time": 1.58,
    "time_to_first_token": 1.58
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "selectiva",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2486,
    "completion_tokens": 1541,
    "total_tokens": 4027,
    "total_time": 17.58,
    "time_to_first_token": 17.58
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "selectiva",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2091,
    "completion_tokens": 3,
    "total_tokens": 2094,
    "total_time": 0.76,
    "time_to_first_token": 0.76
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 2055 | 1 | 1.63 | selectiva | 0.8912655575615474 | 0.0 |
| google | gemini-3.5-flash-lite | 2041 | 2 | 1.94 | selectiva | null | 0.0006173 |
| groq | openai/gpt-oss-20b | 2007 | 1149 | 1.59 | selectiva | null | 0.000495225 |
| openrouter | inclusionai/ling-3.1-flash | 2486 | 1541 | 17.59 | selectiva | null | 0.0 |
| groq | qwen/qwen3.8-27b | 2091 | 3 | 0.77 | selectiva | null | 0.0016848000000000002 |
