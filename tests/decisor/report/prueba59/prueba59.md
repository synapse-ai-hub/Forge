# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:38:01

## Prompt exacto del modelo de decisión

````
Sos el brand manager que puntúa un brief de campaña. Puntuá el brief según los criterios indicados.

Brief de lanzamiento de una app de control de gastos para jóvenes, presupuesto 20000 USD:
- Objetivo: 50000 descargas en 3 meses con costo por instalación menor a 0.40 USD. El número cierra justo con el presupuesto si se cumple el CPI.
- Audiencia: 18 a 28 años, definida con 3 personas con nombre, hábitos y frases textuales de 20 entrevistas.
- Mensaje: concepto creativo probado en 2 focus groups con 78 por ciento de aprobación, con 5 piezas adaptadas por formato.
- Canales: TikTok e Instagram con split 70/30 justificado por dónde está la audiencia, más 10 microinfluencers de finanzas con costo y alcance estimado uno por uno.
- Medición: MMP configurada, eventos de activación definidos, y regla de corte semanal para lo que supere 0.50 USD de CPI.
- Debilidad: no hay plan de retención post-instalación (el brief termina en la descarga aunque el negocio vive de usuarios activos a 30 días), ni presupuesto de contingencia si el CPI sale más alto.

Más datos: la app tiene retención a 30 días del 12 por ciento y el negocio necesita 25 por ciento para ser rentable; el brief no menciona ni onboarding ni notificaciones. El presupuesto de 20000 USD se reparte en 14000 de pauta, 4000 de influencers y 2000 de piezas; no hay reserva. El CPI de 0.40 es el promedio de la categoría pero los últimos 3 lanzamientos similares pagaron 0.55. Los 10 microinfluencers tienen entre 50000 y 200000 seguidores con engagement de 3 a 8 por ciento. El MMP cuesta 500 USD al mes y no está en el presupuesto. El equipo de producto dice que sin retención el lanzamiento es tirar plata; marketing dice que su objetivo es solo la descarga.

Detalle ampliado del producto, del mercado y del plan:

La app es de finanzas personales con foco en jóvenes de 18 a 30 años: permite ver gastos por categoría, poner metas de ahorro y recibir alertas de gastos hormiga. Compite con 8 apps similares, 3 de ellas gratis con publicidad. El diferencial declarado es el diseño simple y el onboarding en 2 minutos, pero el brief no detalla ni el onboarding ni las notificaciones push (la app las tiene, pero el brief no dice cómo se usan para retener). La retención a 30 días actual es 12 por ciento y el punto de equilibrio del negocio es 25 por ciento: con 12 por ciento cada usuario descargado vale 0.80 USD y con 25 por ciento vale 2.10 USD. El brief no menciona este número en ningún lado.

Audiencia: el brief define jóvenes de 18 a 30 años interesados en finanzas, sin segmentar por nivel de ingresos, ciudad ni comportamiento. Los datos de la empresa muestran que el 70 por ciento de los usuarios actuales tiene entre 22 y 28 años, vive en capitales y gasta más de 500 USD al mes en tarjeta. El brief no usa estos datos para definir audiencias de pauta: propone una sola audiencia amplia de 18 a 30 en todo el país. El equipo de performance advierte que la audiencia amplia suele dar CPI barato pero retención mala, y propone 3 audiencias (universitarios, jóvenes profesionales y gamers) sin que el brief lo recoja.

Mensaje: el brief propone 3 líneas (controlá tus gastos, ahorrá sin esfuerzo, tu plata bajo control) sin test previo ni datos de cuál funciona. La app ya corrió 2 campañas chicas el año pasado: la línea controlá tus gastos dio CPI de 0.35 con retención de 10 por ciento, y ahorrá sin esfuerzo dio CPI de 0.50 con retención de 18 por ciento. El brief no menciona estos antecedentes ni propone test A/B: asigna las 3 líneas a los influencers a criterio de cada uno.

Canales y pauta: 14000 USD en pauta (10000 en Instagram y TikTok, 4000 en Google App Campaigns), 4000 en 10 microinfluencers (entre 50000 y 200000 seguidores, engagement de 3 a 8 por ciento, 5 de finanzas y 5 de lifestyle sin brief de contenido unificado), 2000 en piezas (10 videos y 20 placas, sin versiones por audiencia). No hay reserva de contingencia: si el CPI sale 0.55 como en los últimos 3 lanzamientos similares, con 14000 USD se consiguen 25000 descargas en vez de 35000 y no hay de dónde sacar más.

Medición: el brief menciona instalar un MMP pero no lo presupuesta (cuesta 500 USD al mes) ni define eventos (registro, primera meta creada, ahorro a 7 días). Sin MMP no se puede atribuir qué canal trae usuarios que retienen vs usuarios que desinstalan al día. El equipo de datos dice que sin eventos no hay forma de optimizar y que la campaña sería a ciegas. Marketing responde que el MMP se puede contratar después con otro presupuesto, pero ese presupuesto no existe.

Retención: el brief termina en la descarga y no incluye plan post-instalación (onboarding, push, email, gamificación) aunque el negocio vive de usuarios activos a 30 días. El equipo de producto calculó que con retención de 12 por ciento el lanzamiento pierde plata aunque el CPI sea 0.40, y que recién con 20 por ciento empata. Marketing dice que su objetivo es solo la descarga y que la retención es problema de producto. La dirección no arbitró y el brief salió así.

Tiempos: el lanzamiento es en 5 semanas y las piezas todavía no están producidas. Los influencers necesitan 2 semanas de anticipación y todavía no están contratados. El MMP tarda 1 semana en integrarse y nadie lo pidió.

Lanzamientos anteriores: en 2024 se hicieron 3 lanzamientos similares con CPI de 0.55, 0.52 y 0.58 (todos sobre el 0.40 del brief) y retención a 30 días de 10, 14 y 11 por ciento. Ninguno llegó al 25 por ciento necesario. El equipo de producto presentó estos números en la reunión del brief y marketing respondió que esta vez los influencers iban a cambiar la ecuación, sin datos que lo respalden.

Piezas y producción: los 2000 USD cubren 10 videos de 15 segundos y 20 placas estáticas, sin versiones por audiencia ni por canal. La productora entrega en 3 semanas y todavía no fue contratada. Los influencers (5 de finanzas y 5 de lifestyle) reciben el mismo brief de una página sin guion ni mensajes obligatorios. No hay piezas para retargeting ni para usuarios que instalaron y no se registraron.
Criterios: se valora objetivo medible, definición de audiencia, mensaje probado, plan de canales, medición y visión de ciclo completo.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "flojo", "1": "aceptable", "2": "solido", "3": "destacado"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá la calidad del brief según los criterios.",
    "criteria": [
      "flojo",
      "aceptable",
      "solido",
      "destacado"
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
        "score": 0.7077203851798578,
        "confidence": 0.6222076793517475,
        "legend": {
          "0": "flojo",
          "1": "aceptable",
          "2": "solido",
          "3": "destacado"
        },
        "probabilities": {
          "0": 0.33503596773419736,
          "1": 0.6259295923138067,
          "2": 0.03531252698993669,
          "3": 0.0037219129620592326
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1698,
    "completion_tokens": 1,
    "total_tokens": 1699,
    "total_time": 0.96
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "0.6",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1724,
    "completion_tokens": 3,
    "total_tokens": 1727,
    "total_time": 1.61,
    "time_to_first_token": 1.61
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "0",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1675,
    "completion_tokens": 138,
    "total_tokens": 1813,
    "total_time": 0.82,
    "time_to_first_token": 0.82
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "0.6",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2016,
    "completion_tokens": 1479,
    "total_tokens": 3495,
    "total_time": 15.18,
    "time_to_first_token": 15.18
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1556. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}",
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
| openrouter | inception/mercury-decide:free | 1698 | 1 | 0.95 | 0.71 | 0.6222076793517475 | 0.0 |
| google | gemini-3.5-flash-lite | 1724 | 3 | 1.6 | 0.6 | null | 0.0005246999999999999 |
| groq | openai/gpt-oss-20b | 1675 | 138 | 0.82 | 0.0 | null | 0.000167025 |
| openrouter | inclusionai/ling-3.1-flash | 2016 | 1479 | 15.2 | 0.6 | null | 0.0 |
| groq | qwen/qwen3.8-27b | 0 | 0 | 0.14 | "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1556. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}" | null | 0.0 |
