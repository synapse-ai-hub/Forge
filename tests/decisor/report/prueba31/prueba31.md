# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:23:30

## Prompt exacto del modelo de decisión

````
Sos el scoring de leads de una empresa que vende un ERP para pymes industriales. Clasificá este lead en un nivel según su encaje y su intención.

Lead: Roberto Díaz, dueño de Metalúrgica Díaz e Hijos, Córdoba. Empresa familiar de 35 empleados fabricando piezas para maquinaria agrícola. Facturación anual aproximada de 2.5 millones de USD. Hoy gestionan todo con Excel y cuadernos, el dueño reconoce que pierden stock y que los costos los calculan a ojo. Asistió a una demo grupal, hizo 4 preguntas sobre control de stock y costos, y pidió una cotización para 8 usuarios. Dijo que si el precio entra en 12000 USD anuales lo decide este trimestre porque su contador se jubila en septiembre y quiere dejar todo ordenado. No pidió integraciones raras: solo necesita importar su Excel actual. La semana pasada visitó el stand en la feria industrial y dejó su tarjeta pidiendo que lo llamen.

Más datos: el hijo del dueño (ingeniero, 30 años) impulsa el cambio y ya probó la versión trial con datos reales durante 2 semanas; el dueño decide pero escucha al hijo. Están evaluando también a un competidor local que les pasó precio 30 por ciento más barato pero sin módulo de costos. El contador saliente les recomendó no cambiar nada hasta fin de año para no complicar el balance, y el dueño duda por eso. La empresa tiene crédito aprobado en el banco para equipamiento pero nunca compró software. El ciclo de venta típico de este segmento es 4 meses y este lead lleva 5 semanas desde el primer contacto con 6 interacciones registradas.

Expediente ampliado del lead con visitas, números y contexto familiar:

La empresa Metalúrgica Díaz e Hijos la fundó el padre del actual dueño en 1988 con 6 empleados. Hoy tiene 35 empleados: 22 en planta, 6 en administración y ventas, 4 en logística y 3 en mantenimiento. Fabrican 400 piezas distintas para maquinaria agrícola (cosechadoras y sembradoras) y venden a 60 clientes, con 5 que concentran el 70 por ciento de la facturación. La facturación 2025 fue 2.5 millones de USD con margen neto del 8 por ciento. El dueño tiene 62 años y quiere ordenar la empresa antes de jubilarse; el hijo ingeniero de 30 años es el sucesor designado y entró a la empresa hace 3 años.

Situación operativa actual: gestionan stock con 6 planillas de Excel sin conexión entre sí y cuadernos en planta. El último inventario físico (hace 8 meses) mostró diferencias del 12 por ciento contra las planillas. Los costos los calculan a ojo con un margen fijo del 25 por ciento sobre materiales, sin incluir horas de máquina ni retrabajos. El año pasado perdieron 2 licitaciones grandes por no poder costear con precisión. El contador externo (que se jubila en septiembre) lleva la contabilidad en un sistema viejo y les advirtió que un cambio de sistema a mitad de año complica el balance anual.

Historial comercial: primer contacto hace 5 semanas en la feria industrial (el hijo dejó la tarjeta y pidió que lo llamen). Semana 2: llamado de descubrimiento de 30 minutos con el hijo, que contó la situación y pidió demo. Semana 3: demo grupal de 90 minutos con el dueño, el hijo y el jefe de planta; hicieron 4 preguntas (control de stock por lote, costeo por orden, permisos por rol y migración desde Excel). Semana 4: el hijo probó la trial con 200 artículos reales durante 2 semanas y reportó 3 bugs menores (ya corregidos) y 1 pedido de mejora (en roadmap). Semana 5: pidieron cotización para 8 usuarios y el dueño dijo que si entra en 12000 USD anuales lo decide este trimestre. En total 6 interacciones registradas con scoring alto.

Competencia: evalúan a un competidor local que les pasó 8400 USD anuales (30 por ciento menos) pero sin módulo de costos, que es justo lo que más les duele. El hijo descartó al competidor por eso; el dueño todavía lo menciona por precio. No evalúan a nadie más. En 2023 probaron otro sistema y lo abandonaron al mes porque era muy complejo para planta.

Decisión y tiempos: decide el dueño pero escucha al hijo, que empuja fuerte. El jefe de planta es neutral pero pide que el sistema funcione en tablets del taller (la trial se probó en PC, no en tablet). El contador saliente recomendó esperar a fin de año y el dueño duda por eso: teme que el cambio complique el balance y la jubilación del contador. Si deciden este trimestre, la implementación sería en agosto-septiembre con el contador todavía disponible para el traspaso. El presupuesto: no hay partida formal, pero el dueño dijo que 12000 USD anuales entran si se justifica con el ahorro de stock (estiman 30000 USD anuales en pérdidas por descontrol).

Financiamiento: tienen crédito aprobado en el banco por 200000 USD para equipamiento (nunca compraron software con crédito). Prefieren pago anual adelantado con descuento antes que mensual. La cotización enviada es 11500 USD anuales por 8 usuarios con implementación incluida, dentro del número que el dueño mencionó.

Riesgos registrados: la duda del contador y el balance, la falta de prueba en tablets, el precio del competidor dando vueltas, y que el dueño viaja todo julio (si no se decide en junio, pasa a agosto). El ciclo típico del segmento es 4 meses y este va en 5 semanas con velocidad superior al promedio.

Actividad de la trial: el hijo cargó 200 artículos reales, 3 listas de precios y 2 usuarios de prueba. Generó 40 movimientos de stock, 15 órdenes de compra simuladas y 3 reportes de costos. Reportó 3 bugs menores (un filtro que no ordenaba, un decimal mal redondeado y un permiso mal asignado) corregidos en 48 horas, y 1 pedido de mejora (exportar costos a Excel) que entró al roadmap del trimestre. El uso fue de 2 horas diarias durante 10 días hábiles. El jefe de planta no participó de la trial y pide probarla en una tablet del taller antes de opinar.

Números del descontrol actual: el inventario físico mostró 12 por ciento de diferencias, equivalentes a 180000 USD en stock fantasma y faltantes. Los retrabajos por falta de materiales cuestan 5000 USD mensuales. Las 2 licitaciones perdidas sumaban 400000 USD anuales. El hijo calculó que con el sistema recuperarían 30000 USD anuales solo en stock, sin contar licitaciones.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- hot: encaje perfecto con decisión inminente y presupuesto confirmado
- warm: buen encaje pero con tiempos o decisión indefinidos
- cold: encaje parcial que requiere nutrición de largo plazo
- descartado: sin encaje o sin posibilidad real de compra
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí el nivel que mejor describe al lead.",
    "criteria": {
      "hot": "encaje perfecto con decisión inminente y presupuesto confirmado",
      "warm": "buen encaje pero con tiempos o decisión indefinidos",
      "cold": "encaje parcial que requiere nutrición de largo plazo",
      "descartado": "sin encaje o sin posibilidad real de compra"
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
        "choice": "hot",
        "confidence": 0.7026469123730529,
        "probabilities": {
          "hot": 0.7769851842797897,
          "warm": 0.2226099823854585,
          "cold": 0.0003346804924722884,
          "descartado": 7.015284227952892e-05
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1648,
    "completion_tokens": 1,
    "total_tokens": 1649,
    "total_time": 0.89
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "hot",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1624,
    "completion_tokens": 1,
    "total_tokens": 1625,
    "total_time": 3.28,
    "time_to_first_token": 3.28
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "warm",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1634,
    "completion_tokens": 284,
    "total_tokens": 1918,
    "total_time": 0.93,
    "time_to_first_token": 0.93
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
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1167. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}",
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
| openrouter | inception/mercury-decide:free | 1648 | 1 | 0.91 | hot | 0.7026469123730529 | 0.0 |
| google | gemini-3.5-flash-lite | 1624 | 1 | 3.28 | hot | null | 0.0004896999999999999 |
| groq | openai/gpt-oss-20b | 1634 | 284 | 0.93 | warm | null | 0.00020774999999999998 |
| openrouter | inclusionai/ling-3.1-flash | 0 | 0 | 2.49 | "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'inclusionai/ling-3.1-flash is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'provider_name': 'Novita', 'is_byok': False, 'limit_source': 'upstream_provider_shared_pool', 'remedy_hint': 'Retry shortly, add your own provider key (https://openrouter.ai/settings/integrations), or route to another provider with provider routing: https://openrouter.ai/docs/features/provider-routing'}}, 'user_id': 'user_3IHIEaL9108If8k2gSzCi1zx2e3'}" | null | 0.0 |
| groq | qwen/qwen3.8-27b | 0 | 0 | 0.13 | "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1167. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}" | null | 0.0 |
