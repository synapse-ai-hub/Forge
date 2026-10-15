# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:10:27

## Prompt exacto del modelo de decisión

````
Sos el router de un asistente de operaciones. El usuario escribió el siguiente mensaje:

Che, se cayó el servicio de pagos hace 20 minutos, los clientes no pueden pagar y el dashboard muestra error 502 en el gateway. Ya reinicié el pod de la API dos veces y sigue igual. Los logs del gateway muestran timeouts contra el procesador externo desde las 14:03, pero no sé si es la base nuestra o el proveedor. El status page del proveedor dice todo operativo. Tengo al gerente comercial preguntándome cada 5 minutos porque hay una campaña activa y estiman 3000 USD de venta perdida por hora. Necesito que alguien mire los logs del gateway ahora mismo y me diga dónde está el problema. El último deploy fue ayer a las 18:00 y no tocó pagos.

Datos del dashboard que adjunta: tasa de error del gateway 98 por ciento desde las 14:03, latencia p99 del endpoint de pagos 30 segundos (timeout), base de datos con CPU al 22 por ciento y replicación sin lag, cola de webhooks con 12000 mensajes acumulados. En el canal de incidentes alguien escribió que el proveedor avisó por email un mantenimiento para esta noche a las 23:00, no para ahora. El servicio se cayó hace 2 meses por un problema parecido y en esa ocasión era la base (un lock por una migración). Hoy está de guardia el equipo de plataforma y el runbook de pagos dice que ante 502 sostenido hay que revisar primero los logs del gateway y después escalar al proveedor con el request id.

Transcripción parcial del canal de incidentes (últimos 20 minutos, se adjunta como contexto):

14:05 - monitoreo: alerta GATEWAY_502 disparada, error rate 45 por ciento y subiendo. 14:07 - ana_dev: veo timeouts contra el procesador externo en los logs del gateway desde las 14:03, todos con el mismo request id de correlación. 14:09 - juan_ops: reinicié el pod de la API por las dudas, no cambió nada. 14:11 - comercial_maria: los clientes nos están matando, la campaña de hoy trae el triple de tráfico, ¿cuándo vuelve? 14:12 - ana_dev: la base está tranquila, CPU 22 por ciento, replicación sin lag, no parece la base. 14:14 - proveedor_status: alguien revisó el status page del proveedor? dice todo operativo. 14:15 - juan_ops: segundo restart del pod de la API, sigue igual, el 502 viene del gateway no de la API. 14:17 - comercial_maria: el gerente quiere un ETA ya, estiman 3000 USD por hora de pérdida. 14:19 - ana_dev: los timeouts son todos de 30 segundos clavados, parece timeout de conexión no de respuesta lenta. 14:21 - guardia_plataforma: estoy entrando, pasen los request ids para escalar al proveedor. 14:23 - alguien: ojo que hace 2 meses fue la base con un lock, no descartemos nada todavía. 14:25 - ana_dev: en esa ocasión la base estaba al 100 por ciento de CPU, ahora está al 22, no es lo mismo.

Runbook de pagos (extracto vigente): ante 502 sostenido por más de 5 minutos, el primer paso es revisar los logs del gateway buscando el request id de correlación y clasificar entre timeout contra el procesador, error del procesador o error interno. El segundo paso es verificar el status page del proveedor y el email de mantenimientos programados. El tercer paso es escalar al proveedor con 5 request ids de ejemplo si el problema es externo, o a base de datos si los logs muestran locks o conexiones agotadas. El runbook prohíbe reiniciar pods más de 2 veces sin diagnóstico (ya se hicieron 2). El tiempo objetivo de diagnóstico es 15 minutos y ya pasaron 20.

Historial de incidentes de pagos (últimos 6 meses): hace 2 meses, caída de 40 minutos por un lock de una migración en la base (CPU al 100 por ciento, replicación con lag de 2 horas). Hace 4 meses, degradación de 2 horas por saturación del pool de conexiones del gateway (se resolvió subiendo el pool de 200 a 500). Hace 5 meses, caída del procesador externo de 50 minutos que volvió sola (el status page tardó 30 minutos en reflejarla). Hace 6 meses, error de certificado vencido en el gateway de 15 minutos. El equipo de plataforma tiene 4 personas y hoy hay 2 de guardia.

Datos del proveedor: el contrato incluye SLA de 99.9 por ciento con créditos por incumplimiento. El email de mantenimiento programado para hoy a las 23:00 anuncia ventana de 2 horas con degradación parcial esperada. El status page muestra todo operativo pero tiene historial de demoras de hasta 30 minutos en reflejar incidentes (como hace 5 meses). El contacto de escalamiento responde en 20 minutos promedio en horario comercial.

Impacto comercial: la campaña activa es el Hot Sale con pauta de 5000 USD por hora que lleva a un checkout roto. El gerente comercial reporta 8000 usuarios activos intentando comprar y 600 tickets a soporte en 20 minutos. El 70 por ciento de las ventas del día se hacen con tarjeta (el resto Mercado Pago y transferencia siguen funcionando). La estimación de 3000 USD por hora de pérdida viene del promedio de venta del Hot Sale del año pasado.

Estado de los equipos: el equipo de plataforma (4 personas, 2 de guardia hoy) está mirando el gateway. El equipo de base de datos confirma CPU al 22 por ciento y replicación sin lag, y pide que no se los convoque salvo que los logs muestren locks. El proveedor externo todavía no respondió el email de consulta enviado a las 14:10. El gerente comercial pide un ETA cada 5 minutos y el vocero designado es el líder de guardia. El último deploy (ayer 18:00) tocó solo el módulo de reportes y su diff ya fue revisado sin relación con pagos.

Cola de webhooks: los 12000 mensajes acumulados son notificaciones de pago que no salieron al comercio. Si el incidente dura 1 hora más, la cola llega a 30000 y el reprocesamiento tarda 2 horas con el consumidor actual. El equipo de plataforma evalúa levantar 5 consumidores extra para drenarla cuando vuelva el servicio. Los webhooks tienen reintento automático por 24 horas antes de marcarse como fallidos definitivos.

Comunicación con clientes: soporte tiene 600 tickets abiertos por el incidente con un template que dice estamos trabajando en el problema sin ETA. El gerente comercial quiere publicar un ETA de 1 hora pero el líder de guardia se niega sin diagnóstico. La última comunicación oficial a clientes fue hace 10 minutos.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- diagnosticar: analizar logs y métricas del incidente en curso para encontrar la causa
- documentar: escribir el postmortem del incidente para el registro interno
- investigar: abrir una investigación profunda de causa raíz con el equipo para después del incidente
- delegar: derivar el caso a otro equipo o persona para que lo resuelva
- responder: dar una respuesta directa al usuario sin usar herramientas ni delegar
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí la acción que mejor responde al mensaje del usuario.",
    "criteria": {
      "diagnosticar": "analizar logs y métricas del incidente en curso para encontrar la causa",
      "documentar": "escribir el postmortem del incidente para el registro interno",
      "investigar": "abrir una investigación profunda de causa raíz con el equipo para después del incidente",
      "delegar": "derivar el caso a otro equipo o persona para que lo resuelva",
      "responder": "dar una respuesta directa al usuario sin usar herramientas ni delegar"
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
        "choice": "diagnosticar",
        "confidence": 0.8265349742008193,
        "probabilities": {
          "diagnosticar": 0.8612279793606555,
          "documentar": 0.001073430229962912,
          "investigar": 0.0008899049169743372,
          "delegar": 0.11655454293885767,
          "responder": 0.02025414255354953
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1784,
    "completion_tokens": 1,
    "total_tokens": 1785,
    "total_time": 0.77
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "diagnosticar",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1711,
    "completion_tokens": 3,
    "total_tokens": 1714,
    "total_time": 1.39,
    "time_to_first_token": 1.39
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "diagnosticar",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1679,
    "completion_tokens": 135,
    "total_tokens": 1814,
    "total_time": 0.77,
    "time_to_first_token": 0.77
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
  "data": "diagnosticar",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1737,
    "completion_tokens": 4,
    "total_tokens": 1741,
    "total_time": 0.43,
    "time_to_first_token": 0.43
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 1784 | 1 | 0.77 | diagnosticar | 0.8265349742008193 | 0.0 |
| google | gemini-3.5-flash-lite | 1711 | 3 | 1.4 | diagnosticar | null | 0.0005208 |
| groq | openai/gpt-oss-20b | 1679 | 135 | 0.77 | diagnosticar | null | 0.000166425 |
| openrouter | inclusionai/ling-3.1-flash | 0 | 0 | 2.47 | "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'inclusionai/ling-3.1-flash is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'provider_name': 'Novita', 'is_byok': False, 'limit_source': 'upstream_provider_shared_pool', 'remedy_hint': 'Retry shortly, add your own provider key (https://openrouter.ai/settings/integrations), or route to another provider with provider routing: https://openrouter.ai/docs/features/provider-routing'}}, 'user_id': 'user_3IHIEaL9108If8k2gSzCi1zx2e3'}" | null | 0.0 |
| groq | qwen/qwen3.8-27b | 1737 | 4 | 0.44 | diagnosticar | null | 0.0014056000000000001 |
