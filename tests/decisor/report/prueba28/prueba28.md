# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:15:30

## Prompt exacto del modelo de decisión

````
Sos el clasificador de errores de un pipeline de datos nocturno. El log de anoche dice:

03:12:04 INFO inicio de extracción, 184 tablas programadas.
03:12:41 INFO conexión al data warehouse establecida en 380ms.
03:15:02 INFO 40 tablas de clientes cargadas sin errores.
03:33:18 INFO 120 tablas de ventas cargadas, 4 con warnings de formato en fechas (parseadas con fallback).
03:47:19 ERROR timeout agotado esperando respuesta del endpoint de inventario (api.inventario.internal/v2/stock) tras 120 segundos y 3 reintentos.
03:47:20 WARN se omiten 12 tablas dependientes del inventario, el resto continúa.
04:31:55 INFO carga finalizada: 172 de 184 tablas, 0 errores de transformación, 0 errores de escritura.
04:32:01 INFO resumen enviado al canal de monitoreo.

Contexto: el endpoint de inventario es un servicio externo del proveedor del ERP, fuera de la red propia. El warehouse respondió todas las consultas en tiempos normales (p95 200ms). Las transformaciones corrieron sin errores y la escritura finalizó correctamente. Es la tercera vez en el mes que el endpoint de inventario da timeout entre las 3 y las 4 de la mañana.

Historial de la semana: lunes y miércoles la corrida terminó con las 184 tablas sin errores. El martes falló la carga de 6 tablas de RRHH por un CSV con encoding distinto (problema de datos que se resolvió reenviando el archivo). Las 12 tablas omitidas anoche contienen stock por depósito y las usan el reporte de compras de las 9:00 y el dashboard de logística; ambos mostraron datos del día anterior con un cartel de desactualizado. El SLA del pipeline exige 180 de 184 tablas antes de las 6:00; anoche se cumplió con 172. El proveedor del ERP publicó que hace mantenimiento de su API todos los días de 3:00 a 5:00 pero con degradación parcial, no con caída total. El equipo de red confirma que no hubo cortes ni cambios de firewall anoche.

Bitácora completa de la corrida de anoche y contexto del pipeline:

La corrida arranca todos los días a la 1:00 con la extracción de 184 tablas desde 6 fuentes: el ERP del proveedor externo (40 tablas por API REST), el warehouse propio (90 tablas), 3 archivos CSV que deja el área de RRHH en el SFTP (12 tablas), el CRM por API (22 tablas) y 20 tablas de referencia que se recalculan localmente. Anoche la secuencia fue: 1:00 inicio normal, 1:40 terminan las 90 del warehouse sin errores, 2:15 terminan las 22 del CRM, 2:50 terminan los CSV de RRHH, 3:05 arranca el lote del ERP externo, 3:12 primer timeout contra el endpoint de inventario, 3:15 a 3:58 reintentos automáticos (3 por tabla con backoff de 2 minutos), 4:02 el orquestador marca las 12 tablas como omitidas y sigue con el resto, 4:40 terminan las 20 de referencia, 5:12 fin de la corrida con 172 de 184. El log muestra 47 timeouts consecutivos contra el mismo endpoint, todos de 30 segundos, sin una sola respuesta exitosa en el medio.

Detalle del endpoint de inventario: es un GET paginado que devuelve 5000 registros por página; las 12 tablas requieren 340 páginas en total. El timeout del cliente está configurado en 30 segundos y no hay circuit breaker: cada timeout se reintenta 3 veces antes de marcar la tabla como omitida. El proveedor publica un rate limit de 100 requests por minuto y el pipeline hace 40, así que no es throttling. La autenticación es por token que se renueva cada hora; el log muestra que el token se renovó correctamente a las 3:00. El equipo de integraciones confirma que no hubo cambios de código en 3 semanas.

Ventana de mantenimiento del proveedor: el proveedor publica en su portal que todos los días de 3:00 a 5:00 hace mantenimiento con degradación parcial esperada (respuestas más lentas, no caída total). El historial de los últimos 30 días muestra que en 22 de esos días el endpoint respondió con latencia de 5 a 15 segundos en esa ventana (degradado pero funcional) y en 8 días respondió normal. Es la primera vez en el mes que da timeout total sostenido por casi una hora. El contrato con el proveedor incluye SLA de 99.5 por ciento mensual y el mes viene en 99.7, así que todavía hay margen. El contacto técnico del proveedor responde en 4 horas promedio y todavía no respondió el ticket abierto a las 6:30.

Impacto aguas abajo: el reporte de compras de las 9:00 salió con stock del día anterior y el área de compras hizo 3 órdenes con datos viejos (una por 40000 USD que ahora hay que revisar). El dashboard de logística muestra el cartel de desactualizado y el gerente de logística llamó 2 veces. El proceso de reposición automática no corrió porque le faltan las 12 tablas y 40 productos quedaron sin reposición hoy. El equipo de datos estima que si hoy a la noche vuelve a fallar, mañana el reporte de compras sale con 2 días de atraso y el área comercial no puede facturar 200000 USD en pedidos pendientes de stock.

Historial del mes: además de anoche, hubo timeouts parciales (algunas páginas, no todas) en 6 noches del mes, siempre entre las 3 y las 4. En esas ocasiones los reintentos alcanzaron y ninguna tabla se omitió. El martes el fallo fue distinto: 6 tablas de RRHH con un CSV en encoding Latin-1 en vez de UTF-8 (problema de datos, resuelto reenviando el archivo a las 7:00). Lunes y miércoles de esta semana terminaron con 184 de 184 sin observaciones.

Infraestructura propia: el orquestador corre en un cluster que anoche estuvo al 40 por ciento de CPU y 60 por ciento de memoria, sin presión. El warehouse respondió las 90 consultas con p95 de 200ms. La red corporativa no tuvo cortes (el monitoreo de red muestra 0 pérdida de paquetes toda la noche) y no hubo cambios de firewall en 2 meses. El SFTP de RRHH recibió los 3 archivos a horario. El CRM respondió las 22 tablas en tiempos normales.

Posturas: el líder de datos quiere declarar causa externa y pedir al proveedor que mueva su ventana de mantenimiento fuera del horario de la corrida. El responsable de integraciones quiere agregar circuit breaker y reintentos con backoff más largo antes de culpar al proveedor. El gerente de logística quiere una corrida de recuperación al mediodía solo con las 12 tablas para no esperar a esta noche. El proveedor todavía no respondió.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- red: el problema está en la conectividad o en un servicio externo que no responde
- datos: el problema está en la calidad o el formato de los datos de origen
- codigo: el problema está en un bug de la lógica de transformación o del pipeline
- infraestructura: el problema está en los recursos propios como disco, memoria o el warehouse
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí la categoría que mejor explica la falla.",
    "criteria": {
      "red": "el problema está en la conectividad o en un servicio externo que no responde",
      "datos": "el problema está en la calidad o el formato de los datos de origen",
      "codigo": "el problema está en un bug de la lógica de transformación o del pipeline",
      "infraestructura": "el problema está en los recursos propios como disco, memoria o el warehouse"
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
        "choice": "red",
        "confidence": 0.9998772009449809,
        "probabilities": {
          "red": 0.9999079007087357,
          "datos": 4.264535576438746e-05,
          "codigo": 2.930969580709029e-05,
          "infraestructura": 2.0144239692837866e-05
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1791,
    "completion_tokens": 1,
    "total_tokens": 1792,
    "total_time": 4.69
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "red",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1767,
    "completion_tokens": 1,
    "total_tokens": 1768,
    "total_time": 1.65,
    "time_to_first_token": 1.65
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "red",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1695,
    "completion_tokens": 66,
    "total_tokens": 1761,
    "total_time": 0.42,
    "time_to_first_token": 0.42
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'inclusionai/ling-3.1-flash is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'provider_name': 'Novita', 'is_byok': False, 'limit_source': 'upstream_provider_shared_pool', 'remedy_hint': 'Retry shortly, add your own provider key (https://openrouter.ai/settings/integrations), or route to another provider with provider routing: https://openrouter.ai/docs/features/provider-routing'}}, 'user_id': 'user_3IHIEaL9108If8k2gSzCi1zx2e3'}",
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

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "red",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1818,
    "completion_tokens": 2,
    "total_tokens": 1820,
    "total_time": 2.52,
    "time_to_first_token": 2.52
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 1791 | 1 | 4.69 | red | 0.9998772009449809 | 0.0 |
| google | gemini-3.5-flash-lite | 1767 | 1 | 1.66 | red | null | 0.0005326 |
| groq | openai/gpt-oss-20b | 1695 | 66 | 0.43 | red | null | 0.00014692499999999998 |
| openrouter | inclusionai/ling-3.1-flash | 0 | 0 | 3.19 | "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'inclusionai/ling-3.1-flash is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'provider_name': 'Novita', 'is_byok': False, 'limit_source': 'upstream_provider_shared_pool', 'remedy_hint': 'Retry shortly, add your own provider key (https://openrouter.ai/settings/integrations), or route to another provider with provider routing: https://openrouter.ai/docs/features/provider-routing'}}, 'user_id': 'user_3IHIEaL9108If8k2gSzCi1zx2e3'}" | null | 0.0 |
| groq | qwen/qwen3.8-27b | 1818 | 2 | 2.54 | red | null | 0.0014624 |
