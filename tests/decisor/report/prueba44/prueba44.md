# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:58:30

## Prompt exacto del modelo de decisión

````
Sos el encargado de comunicaciones que elige el tono de respuesta. Caso:

Un cliente con 6 años de antigüedad y 120000 USD de facturación acumulada publicó en LinkedIn quejándose de que una caída de 5 horas le hizo perder su presentación más importante del año frente a inversores, con capturas del error y 400 reacciones. El post dice que está evaluando a la competencia. El equipo comercial confirma que el cliente siempre pagó en fecha y que su contrato renueva en 45 días. Legal revisó el SLA: la caída está dentro del 99.9 por ciento mensual así que no corresponde compensación automática, pero permite un gesto comercial. El CEO pidió responder hoy mismo antes de que escale a medios. Dos periodistas de medios tech ya compartieron el post.

Contexto: el cliente es referente en su rubro y 3 prospectos en negociación lo siguen en LinkedIn. En los comentarios hay 50 respuestas, la mitad de otros clientes contando caídas propias. Hace un año un caso parecido se respondió con un comunicado formal y el cliente se fue a los 2 meses publicando la carta. El equipo de soporte dice que la caída afectó a 200 cuentas pero solo este cliente perdió algo crítico. Comercial propone visitarlo mañana con una propuesta de 3 meses bonificados; legal advierte que bonificar puede sentar precedente para los otros 199.   El CEO quiere mostrar empatía pero sin admitir culpa por consejo de legales. El contrato del cliente no tiene cláusula de salida anticipada pero renueva en 45 días.

Ampliación del caso con el post, el cliente y las presiones internas:

El post en detalle: publicado hace 48 horas en LinkedIn por el gerente de operaciones del cliente, con capturas del error 500 durante 5 horas, 400 reacciones y 120 comentarios (30 de otros clientes preguntando si les pasó lo mismo). El post dice que perdieron su presentación más importante del año frente a inversores y que están evaluando a la competencia (nombra 2 competidores). El alcance orgánico llegó a 15000 personas y un medio del sector lo levantó ayer. El equipo de marketing quiere responder públicamente en el post; legal dice que no se responda nada público hasta definir la estrategia.

El cliente: 6 años de antigüedad, 120000 USD de facturación acumulada, siempre pagó en fecha, contrato enterprise de 30000 USD anuales que renueva en 45 días. Usa 5 módulos y tiene 40 usuarios activos. Su NPS histórico es 9 y participó en 2 casos de éxito. La caída de 5 horas fue por un deploy con migración que salió mal (el mismo incidente del postmortem interno). El cliente perdió efectivamente su presentación: el comercial lo confirmó con el sponsor (el gerente de operaciones, que es quien publicó). El sponsor dice que su directorio le pidió evaluar alternativas y que necesita una señal para defender la renovación internamente.

SLA y legales: legal revisó el SLA y la caída de 5 horas está dentro del 99.5 por ciento mensual (no genera créditos automáticos). Pero el contrato tiene cláusula de salida por causa mayor reiterada (3 incidentes en 90 días habilitan la salida; este es el segundo en 60 días). Legal advierte que bonificar 3 meses (7500 USD) puede sentar precedente para los otros 199 clientes enterprise (riesgo de 1.5 millones si todos piden lo mismo). Legal propone una nota privada con empatía, un plan de mejora con fechas y una visita del CTO, sin admitir culpa ni bonificar. El CEO quiere mostrar empatía pero sin admitir culpa.

Presiones internas: el gerente de cuenta quiere visitarlo mañana con una propuesta de 3 meses bonificados y un descuento del 10 por ciento en la renovación (total 10500 USD) porque dice que sin eso se pierde la cuenta. Comercial apoya porque el trimestre viene 5 por ciento abajo del target y esta renovación pesa. El CTO ofrece visitarlo con un plan técnico de 30-60-90 días y abrirle el roadmap de confiabilidad. Soporte informa que el cliente abrió 8 tickets en 6 meses (todos resueltos en SLA) y que su único reclamo grave es este. El board se entera mañana en la reunión mensual y el CEO necesita llevar una posición.
Tonos en evaluación: el equipo evalúa 3 tonos (empático con compensación económica, empático con plan técnico sin compensación, y formal apegado al SLA sin concesiones) y pide una recomendación que cuide la renovación sin sentar precedente para los otros 199.

Precedentes con otros clientes: en 2024 hubo 2 casos similares (caídas de 3 y 4 horas con posts públicos). En uno se bonificó 1 mes (2500 USD) y el cliente renovó; en el otro se ofreció plan técnico sin bonificar y el cliente se fue a los 6 meses. Ninguno de los dos sentó precedente formal porque se manejaron como excepciones privadas. El gerente de cuenta cita el primer caso como argumento para bonificar; legal cita el riesgo de escala (199 enterprise) como argumento en contra. El CEO pidió los números de ambos casos antes de decidir.

La visita de mañana y el board: el gerente de cuenta quiere ir mañana con 3 meses bonificados más 10 por ciento de descuento (10500 USD total) y necesita la aprobación hoy para preparar la propuesta. El CTO ofrece ir él con el plan de 30-60-90 días y el roadmap de confiabilidad (sin costo directo, 2 días de trabajo). Legal propone carta privada con empatía más visita del CTO, sin bonificar ni admitir culpa. El sponsor del cliente (quien publicó) dijo al comercial que necesita una señal para defender la renovación en su directorio: no especificó si económica o técnica. El board se reúne mañana a las 9:00 y el CEO debe llevar una posición única (comercial, CTO y legal hoy discrepan). El contrato renueva en 45 días y el proceso de renovación arranca en 15 días con la propuesta formal. Lo que se haga mañana condiciona esos 15 días.

Comparación final de tonos: empático con compensación (3 meses bonificados más 10 por ciento: 10500 USD, renueva casi seguro según el precedente de 2024, pero sienta precedente para 199 enterprise con riesgo de 1.5 millones y legal se opone), empático con plan técnico (visita del CTO con 30-60-90 días, costo 2 días de trabajo, cuida la relación sin precedente económico, pero el precedente de 2024 sin bonificar terminó con el cliente yéndose a los 6 meses), formal apegado al SLA (carta que dice que la caída está dentro del 99.5 por ciento, costo 0, pero ignora que el cliente perdió su presentación y que hay 400 reacciones públicas, y arriesga la renovación de 30000 USD anuales más el daño del post con 15000 de alcance). El sponsor necesita una señal para su directorio: la compensación es señal inmediata, el plan técnico es señal de fondo. El CEO debe elegir mañana a las 9:00 con comercial, CTO y legal en desacuerdo. La recomendación debe cuidar la renovación de 30000 USD sin exponer 1.5 millones en precedente.

Decisión del encargado: debe elegir 1 tono para la respuesta de mañana (visita o carta, con o sin compensación) con el board a las 9:00, la visita a las 11:00 y la renovación en 45 días. Las restricciones son no admitir culpa (legal), dar una señal al sponsor para su directorio (comercial), no sentar precedente para 199 enterprise (legal), y mostrar que la caída no se repite (CTO con el plan 30-60-90). El tono elegido se usa mañana con este cliente y define el playbook para los próximos 2 incidentes del trimestre (el equipo tuvo 2 caídas en 60 días y la cláusula de salida por causa reiterada se activa al tercero). Si el cliente se va, son 30000 USD anuales menos más el post público como referencia para la competencia (que ya fue nombrada 2 veces en los comentarios).

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- formal: respuesta formal citando el SLA sin ofrecer compensación
- empatica: respuesta pública empática con propuesta concreta y gesto comercial
- privado: no responder en público y gestionarlo solo por canal privado
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí el tono de respuesta según el caso.",
    "criteria": {
      "formal": "respuesta formal citando el SLA sin ofrecer compensación",
      "empatica": "respuesta pública empática con propuesta concreta y gesto comercial",
      "privado": "no responder en público y gestionarlo solo por canal privado"
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
        "choice": "empatica",
        "confidence": 0.836177689570398,
        "probabilities": {
          "formal": 0.015326805752326986,
          "empatica": 0.8907851263802654,
          "privado": 0.09388806786740764
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1918,
    "completion_tokens": 1,
    "total_tokens": 1919,
    "total_time": 1.08
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "empatica: respuesta pública empática con propuesta concreta y gesto comercial",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1940,
    "completion_tokens": 13,
    "total_tokens": 1953,
    "total_time": 1.58,
    "time_to_first_token": 1.58
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "privado",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1909,
    "completion_tokens": 349,
    "total_tokens": 2258,
    "total_time": 1.06,
    "time_to_first_token": 1.06
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
  "data": "privado",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1989,
    "completion_tokens": 3,
    "total_tokens": 1992,
    "total_time": 0.48,
    "time_to_first_token": 0.48
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 1918 | 1 | 1.08 | empatica | 0.836177689570398 | 0.0 |
| google | gemini-3.5-flash-lite | 1940 | 13 | 1.59 | empatica: respuesta pública empática con propuesta concreta y gesto comercial | null | 0.0006145 |
| groq | openai/gpt-oss-20b | 1909 | 349 | 1.06 | privado | null | 0.00024787499999999994 |
| openrouter | inclusionai/ling-3.1-flash | 0 | 0 | 2.51 | "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'inclusionai/ling-3.1-flash is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'provider_name': 'Novita', 'is_byok': False, 'limit_source': 'upstream_provider_shared_pool', 'remedy_hint': 'Retry shortly, add your own provider key (https://openrouter.ai/settings/integrations), or route to another provider with provider routing: https://openrouter.ai/docs/features/provider-routing'}}, 'user_id': 'user_3IHIEaL9108If8k2gSzCi1zx2e3'}" | null | 0.0 |
| groq | qwen/qwen3.8-27b | 1989 | 3 | 0.49 | privado | null | 0.0016032000000000002 |
