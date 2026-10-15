# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:19:30

## Prompt exacto del modelo de decisión

````
Sos el líder de soporte que puntúa una respuesta a un cliente enojado. Puntuá la respuesta según los criterios indicados.

Reclamo del cliente: lleva 3 días sin poder facturar por un error de la plataforma, perdió un cliente importante, y amenaza con irse a la competencia y escrachar en redes. Es cuenta enterprise con 80000 USD anuales.

Respuesta enviada por el agente:

Hola Carlos, gracias por escribirnos. Te cuento que ya identificamos el problema: un certificado vencido en el conector con AFIP que afectó a 12 cuentas enterprise. Lo renovamos hace 2 horas y verificamos que ya podés emitir con normalidad (probamos con tu CUIT y salió bien). Como compensación te acreditamos un mes de servicio y tu ejecutiva de cuenta te va a llamar hoy a las 16 para revisar el impacto en tu operación. Además sumamos un monitoreo específico para que esto no se repita. Perdón por las molestias.

Datos: la respuesta se envió 40 minutos después del reclamo. Menciona la causa, la verificación con el CUIT del cliente, la acreditación de un mes de servicio, el llamado de la ejecutiva hoy a las 16 y el monitoreo nuevo.

Más datos: el cliente es enterprise con 80000 USD anuales y 4 años de antigüedad; es la primera vez que reclama. El SLA de respuesta para enterprise es 2 horas y se cumplió. La acreditación de un mes equivale a 6600 USD y el agente la otorgó sin pedir autorización (su límite es 10000 USD). La ejecutiva de cuenta confirmó el llamado y el cliente aceptó. El monitoreo nuevo costó 2 días de trabajo y cubre a las 12 cuentas afectadas. En la encuesta posterior el c  liente puso 8 sobre 10 y escribió que el problema fue grave pero la respuesta fue rápida. El equipo de soporte usa esta respuesta como ejemplo en la capacitación.

Ampliación del caso con el reclamo, la respuesta y el seguimiento:

Reclamo en detalle: cuenta enterprise de 80000 USD anuales, 3 días sin poder facturar por un error de la plataforma (un deploy que rompió el módulo de facturación para el 5 por ciento de las cuentas). El cliente perdió un cliente importante (un contrato de 200000 USD anuales que no pudo facturar a tiempo y se cayó) y amenaza con irse a la competencia y escrachar en redes (tiene 50000 seguidores en LinkedIn). Abrió el ticket un lunes a las 9:00 con prioridad crítica y llamó 4 veces el primer día. Su ejecutivo de cuenta estaba de licencia y nadie lo contactó hasta el martes.

Respuesta del agente (texto completo evaluado): saludo personalizado con el nombre, disculpa sin excusas, explicación de la causa en lenguaje simple (un cambio del fin de semana afectó su cuenta, ya identificado), tiempo de resolución comprometido (24 horas con actualizaciones cada 6), verificación ofrecida (el agente dice que va a probar personalmente la facturación antes de avisar), compensación (1 mes bonificado sin que el cliente lo pida, 6600 USD), seguimiento (llamado del supervisor en 48 horas) y prevención (el caso entró al comité de cambios para que no se repita). El tono es empático sin admitir culpa legal (revisado por el playbook, sin palabras prohibidas).

Tiempos: el agente respondió en 2 horas (SLA enterprise: 4 horas), resolvió en 20 horas (compromiso: 24), el supervisor llamó a las 48 horas como prometido, y a los 7 días el agente escribió para verificar que todo seguía bien. El cliente respondió a los 7 días con 8 sobre 10 y el comentario de que el problema fue grave pero la respuesta fue rápida. No se fue a la competencia, no publicó en redes y renovó por 1 año 2 meses después. El ejecutivo de cuenta retomó la relación con una visita presencial.

Contexto del equipo: el equipo de soporte tiene 10 personas con 1 supervisor. Esta respuesta se usa como ejemplo en la capacitación de nuevos agentes desde hace 2 meses. El playbook de crisis se actualizó con este caso (compensación proactiva, llamado del supervisor, verificación a los 7 días). El agente que la escribió tiene 3 años de experiencia y NPS de 9.2. El costo de la compensación (6600 USD) se aprobó en 1 hora por el supervisor según la política (hasta 10000 USD sin aprobación del gerente).
Criterios: se valora tiempo de respuesta, explicación de la causa, verificación de la solución, compensación, seguimiento y prevención.

Métricas del caso: tiempo de primera respuesta 2 horas (SLA 4), resolución en 20 horas (compromiso 24), 3 actualizaciones intermedias (cada 6 horas como prometido), 0 escalamientos, satisfacción 8 sobre 10, renovación a los 2 meses, 0 menciones en redes. El costo total del caso (compensación más 6 horas de trabajo) fue 7000 USD contra un riesgo de 80000 USD anuales más el daño reputacional. El comité de cambios implementó la verificación pre-deploy que faltaba y no hubo incidentes similares en 4 meses.

Checklist de scoring aplicado: tiempo de respuesta (2 horas contra SLA de 4, con 4 llamados del cliente el primer día atendidos), explicación de la causa (lenguaje simple, causa identificada, sin palabras prohibidas del playbook), verificación de la solución (el agente probó personalmente antes de avisar, más llamado del supervisor a las 48 horas y verificación a los 7 días), compensación (1 mes proactivo de 6600 USD aprobado en 1 hora según política), seguimiento (3 actualizaciones cada 6 horas, llamado del supervisor, verificación a los 7 días, visita del ejecutivo), prevención (caso al comité de cambios, verificación pre-deploy implementada, 4 meses sin repetir). El supervisor marcó los 6 criterios como cumplidos y la respuesta entró a la capacitación como ejemplo. El cliente renovó por 1 año y su NPS posterior fue 8 (venía de 9, cayó 1 punto por el incidente pero se mantuvo en zona de promotor).

Comparación con otras respuestas del trimestre: el promedio del equipo es primera respuesta en 3 horas (SLA 4), resolución en 30 horas, 1 actualización intermedia, satisfacción 7 sobre 10 y 0 verificaciones a los 7 días. Esta respuesta está por encima del promedio en los 6 criterios y es la única del trimestre con compensación proactiva (las otras 3 compensaciones fueron pedidas por el cliente), llamado del supervisor y verificación a los 7 días. Por eso entró a la capacitación: de 200 respuestas del trimestre, solo 2 se usan como ejemplo. La otra es de un caso simple (reclamo por demora de 1 día) y esta es la única de un caso grave (3 días sin facturar con pérdida de un cliente del cliente). El líder de soporte la propone como respuesta modelo para crisis enterprise.

Decisión del líder de soporte: puntúa la respuesta de 0 a 5 según tiempo, explicación, verificación, compensación, seguimiento y prevención. La respuesta trae 2 horas contra SLA de 4, causa en lenguaje simple, prueba personal más llamado del supervisor más verificación a los 7 días, 1 mes proactivo de 6600 USD, 3 actualizaciones más visita del ejecutivo, y prevención con verificación pre-deploy que lleva 4 meses sin repetir. El cliente renovó por 1 año con NPS de 8. La única mancha del caso es que el ejecutivo estaba de licencia y nadie contactó al cliente el primer día (el agente lo compensó con las 4 llamadas atendidas y la respuesta en 2 horas). El líder debe decidir si esa mancha del primer día baja el puntaje o si la respuesta del agente la compensa.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "muy mala", "1": "mala", "2": "regular", "3": "buena", "4": "muy buena", "5": "excelente"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá la calidad de la respuesta según los criterios.",
    "criteria": [
      "muy mala",
      "mala",
      "regular",
      "buena",
      "muy buena",
      "excelente"
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
        "score": 4.618800184759992,
        "confidence": 0.7458667898399947,
        "legend": {
          "0": "muy mala",
          "1": "mala",
          "2": "regular",
          "3": "buena",
          "4": "muy buena",
          "5": "excelente"
        },
        "probabilities": {
          "0": 9.248762881879312e-05,
          "1": 0.0001432476417633742,
          "2": 8.16200459599787e-05,
          "3": 0.0015400565511160139,
          "4": 0.3768394132887485,
          "5": 0.6213031748435934
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1926,
    "completion_tokens": 1,
    "total_tokens": 1927,
    "total_time": 4.75
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "4.8",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1852,
    "completion_tokens": 3,
    "total_tokens": 1855,
    "total_time": 1.57,
    "time_to_first_token": 1.57
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "5",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1887,
    "completion_tokens": 264,
    "total_tokens": 2151,
    "total_time": 0.84,
    "time_to_first_token": 0.84
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "4.5",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2257,
    "completion_tokens": 174,
    "total_tokens": 2431,
    "total_time": 3.09,
    "time_to_first_token": 3.09
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "5",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1923,
    "completion_tokens": 2,
    "total_tokens": 1925,
    "total_time": 0.47,
    "time_to_first_token": 0.47
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 1926 | 1 | 4.74 | 4.62 | 0.7458667898399947 | 0.0 |
| google | gemini-3.5-flash-lite | 1852 | 3 | 1.57 | 4.8 | null | 0.0005631000000000001 |
| groq | openai/gpt-oss-20b | 1887 | 264 | 0.85 | 5.0 | null | 0.000220725 |
| openrouter | inclusionai/ling-3.1-flash | 2257 | 174 | 3.09 | 4.5 | null | 0.0 |
| groq | qwen/qwen3.8-27b | 1923 | 2 | 0.48 | 5.0 | null | 0.0015464 |
