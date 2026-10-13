# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:48:39

## Prompt exacto del modelo de decisión

````
Sos el abogado que puntúa un borrador de cláusulas de un contrato de desarrollo de software. Puntuá el borrador según los criterios indicados.

Borrador de 8 cláusulas entre una software factory y un cliente retail:
- Alcance: describe los 4 módulos con criterios de aceptación medibles y qué se considera fuera de alcance, con procedimiento para cambios (presupuesto y plazo por escrito antes de ejecutar).
- Plazos: hitos mensuales con entregables y penalidad del 0.5 por ciento semanal con tope del 10 por ciento, bilateral (también aplica si el cliente demora aprobaciones más de 5 días).
- Propiedad intelectual: el código es del cliente desde el pago de cada hito, con cesión firmada por cada desarrollador involucrado.
- Confidencialidad: mutua, 3 años post-contrato, con excepciones estándar (información pública, orden judicial).
- Soporte: 90 días de garantía por bugs con SLA de respuesta (crítico 4 horas, mayor 24 horas), excluyendo cambios de alcance.
- Rescisión: cualquiera puede rescindir con 30 días, pagando lo trabajado más el 20 por ciento del hito en curso.
- Faltantes: no define dónde se resuelven disputas (jurisdicción), no pone tope a la responsabilidad total (solo a la penalidad por mora), y no regula qué pasa con los datos del cliente alojados en la infra de la factory al terminar.

Más datos: el contrato es por 12 meses y 480000 USD con 4 hitos de 120000. El cliente maneja datos de 2 millones de consumidores en la infra de la factory durante el desarrollo. La factory trabaja con 6 desarrolladores asignados y subcontrata el módulo de pagos a un tercero que no firma cesión directa con el cliente. En un contrato anterior hubo una disputa por un atraso de 3 semanas que se resolvió por negociación directa porque tampoco había jurisdicción definida. El cliente pidió que la garantí  a sea de 180 días y la factory ofreció 90; el borrador refleja los 90 sin nota de la negociación. La póliza de errores y omisiones de la factory cubre hasta 500000 USD.

Ampliación del borrador con las 8 cláusulas y el contexto de la negociación:

Alcance: describe los 4 módulos (catálogo, carrito, pagos, reportes) con criterios de aceptación medibles (tiempos de respuesta, casos de prueba por módulo) y qué se considera fuera de alcance (migración de datos históricos, integraciones con el ERP salvo la definida, diseño gráfico). Procedimiento para cambios: presupuesto y plazo por escrito antes de ejecutar, con firma de ambas partes. El cliente ya pidió 2 cambios verbales que no están en el borrador (un módulo de cupones y una app mobile) y la factory los dejó afuera correctamente según el procedimiento.

Plazos: hitos mensuales con entregas parciales y penalidad del 1 por ciento por semana de atraso (tope 10 por ciento). El plazo total es 6 meses desde la firma. El borrador no contempla qué pasa si el cliente demora las aprobaciones (el cliente tarda 10 días promedio en aprobar entregas según la experiencia previa). La factory propuso una cláusula de pausa por demora del cliente que no está en el borrador. El último proyecto similar se atrasó 2 meses por demoras del cliente sin penalidad para nadie.

Propiedad intelectual: el código es del cliente al pagar cada hito (cesión parcial progresiva), con licencia de uso para la factory de sus librerías previas. El borrador no aclara quién es dueño de los componentes nuevos reutilizables (la factory quiere retenerlos, el cliente quiere todo). Este punto está en negociación y el borrador refleja la posición de la factory sin nota. En el contrato anterior hubo un conflicto por este punto que se resolvió con un anexo 6 meses después.

Confidencialidad: NDA mutuo por 3 años con multa de 50000 USD por divulgación. El borrador no incluye a los subcontratistas (la factory usa 2 freelancers para QA que verán datos del cliente). Legales de la factory dice que los freelancers firman NDA individual pero no está en el borrador. El cliente maneja datos de 200000 usuarios finales y su legales exige que el NDA cubra a toda la cadena.

Soporte: 90 días de garantía por bugs desde cada entrega (el cliente pedía 180, la factory ofreció 90, el borrador refleja los 90 sin nota de la negociación). Soporte posterior: bolsa de 40 horas mensuales a 100 USD la hora con SLA de 48 horas. El borrador no define qué es bug vs mejora (fuente histórica de conflictos: en el proyecto anterior el 30 por ciento de los tickets fueron disputados). La póliza de errores y omisiones de la factory cubre hasta 500000 USD con deducible de 25000 USD.

Disputas y responsabilidad: mediación obligatoria antes de juicio, con tope de responsabilidad de 12 meses de facturación (300000 USD). El borrador no fija sede ni idioma del arbitraje (las partes están en distintos países). No hay cláusula de salida anticipada con sus costos (el cliente la pidió, la factory la resiste). El abogado del cliente marcó 5 observaciones y el borrador responde 3.
Criterios: se valora alcance, plazos, propiedad intelectual, confidencialidad, soporte y previsión de disputas y responsabilidad.

Estado de la negociación: van 3 rondas en 6 semanas. El cliente aceptó el precio (300000 USD en 6 hitos) pero discute garantía (180 vs 90 días), propiedad de reutilizables y cláusula de salida. La factory no cede en esos 3 puntos y ofrece a cambio 20 horas de soporte gratis el primer mes. El socio de la factory quiere firmar este mes porque el equipo queda libre y no tiene otro proyecto. El abogado que puntúa debe evaluar el borrador tal como está, sin asumir que los puntos en disputa se van a resolver.

Checklist de scoring aplicado: alcance (4 módulos con aceptación medible, fuera de alcance definido, procedimiento de cambios por escrito, 2 pedidos verbales correctamente excluidos), plazos (hitos mensuales con penalidad, pero sin cláusula de pausa por demora del cliente que ya causó 2 meses de atraso en el proyecto anterior), propiedad intelectual (cesión progresiva clara, pero reutilizables en disputa sin nota en el borrador), confidencialidad (NDA mutuo con multa, pero sin cubrir a los 2 freelancers de QA que verán datos de 200000 usuarios), soporte (90 días reflejados sin nota de que el cliente pedía 180, bolsa posterior definida, pero sin distinguir bug de mejora que ya generó 30 por ciento de tickets disputados), disputas (mediación y tope de 300000 USD, pero sin sede, sin idioma y sin salida anticipada que el cliente pidió). El abogado del cliente marcó 5 observaciones y el borrador responde 3. La póliza de 500000 USD cubre el tope de responsabilidad con deducible de 25000 USD.

Comparación con el contrato anterior: el contrato anterior de la factory (2024, 200000 USD) tenía los mismos 6 puntos flojos (sin pausa por demora, reutilizables sin definir, freelancers sin NDA, bug vs mejora sin distinguir, sin sede de arbitraje, sin salida anticipada) y 4 de los 6 generaron conflicto real (2 meses de atraso sin penalidad, anexo por reutilizables 6 meses después, 30 por ciento de tickets disputados, 1 mediación por salida). El abogado que puntuó aquel contrato le puso 2 sobre 5 y recomendó no firmar sin corregir. Este borrador repite los 6 puntos flojos con montos mayores (300000 USD, 200000 usuarios, tope de 300000 USD). La factory dice que esta vez será distinto porque el cliente es más ordenado, pero no hay nada escrito que lo garantice. El socio quiere firmar este mes por el equipo libre; el abogado debe puntuar el borrador, no la urgencia.

Decisión del abogado: puntúa el borrador de 0 a 5 según alcance, plazos, propiedad intelectual, confidencialidad, soporte y disputas. El borrador trae alcance sólido con procedimiento de cambios, pero plazos sin pausa por demora (que ya costó 2 meses), reutilizables en disputa sin nota, freelancers sin NDA con datos de 200000 usuarios, soporte con 90 días sin nota del pedido de 180 y sin distinguir bug de mejora (que ya generó 30 por ciento de disputas), y disputas sin sede, sin idioma y sin salida. El cliente marcó 5 observaciones y el borrador responde 3. La póliza de 500000 USD cubre el tope con deducible de 25000 USD. El socio presiona para firmar este mes; el abogado debe puntuar lo escrito, no la promesa de que esta vez será distinto.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "flojo", "1": "aceptable", "2": "bueno", "3": "muy bueno"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá la calidad del borrador según los criterios.",
    "criteria": [
      "flojo",
      "aceptable",
      "bueno",
      "muy bueno"
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
        "score": 1.071850848220459,
        "confidence": 0.7101604661139529,
        "legend": {
          "0": "flojo",
          "1": "aceptable",
          "2": "bueno",
          "3": "muy bueno"
        },
        "probabilities": {
          "0": 0.10899434283279398,
          "1": 0.7107324159333747,
          "2": 0.17970129141440952,
          "3": 0.0005719498194217701
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2208,
    "completion_tokens": 1,
    "total_tokens": 2209,
    "total_time": 0.82
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "1.5",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2147,
    "completion_tokens": 3,
    "total_tokens": 2150,
    "total_time": 0.94,
    "time_to_first_token": 0.94
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "1.5",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2102,
    "completion_tokens": 753,
    "total_tokens": 2855,
    "total_time": 1.48,
    "time_to_first_token": 1.48
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
  "data": "2",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2216,
    "completion_tokens": 2,
    "total_tokens": 2218,
    "total_time": 0.72,
    "time_to_first_token": 0.72
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 2208 | 1 | 0.83 | 1.07 | 0.7101604661139529 | 0.0 |
| google | gemini-3.5-flash-lite | 2147 | 3 | 0.95 | 1.5 | null | 0.0006516 |
| groq | openai/gpt-oss-20b | 2102 | 753 | 1.48 | 1.5 | null | 0.00038355 |
| openrouter | inclusionai/ling-3.1-flash | 0 | 0 | 2.46 | "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'inclusionai/ling-3.1-flash is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'provider_name': 'Novita', 'is_byok': False, 'limit_source': 'upstream_provider_shared_pool', 'remedy_hint': 'Retry shortly, add your own provider key (https://openrouter.ai/settings/integrations), or route to another provider with provider routing: https://openrouter.ai/docs/features/provider-routing'}}, 'user_id': 'user_3IHIEaL9108If8k2gSzCi1zx2e3'}" | null | 0.0 |
| groq | qwen/qwen3.8-27b | 2216 | 2 | 0.72 | 2.0 | null | 0.0017808000000000001 |
