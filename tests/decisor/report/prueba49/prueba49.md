# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:11:39

## Prompt exacto del modelo de decisión

````
Sos el dueño de producto que puntúa una especificación. Puntuá el spec según los criterios indicados.

Spec: login con huella digital en la app mobile, versión 2, 6 páginas.
- Flujo feliz detallado paso a paso con 5 pantallas mockeadas en Figma y link al prototipo navegable.
- Casos borde: qué pasa si el dispositivo no tiene sensor (se ofrece PIN como alternativa), si el usuario rechaza el permiso 2 veces (se muestra tutorial y se reintenta en el próximo login), si cambia la huella del sistema (se pide re-registro), y si hay 5 intentos fallidos seguidos (bloqueo de 30 segundos con mensaje 12 del catálogo).
- Seguridad: la plantilla biométrica nunca sale del secure enclave, sesión con expiración de 15 minutos de inactividad, y re-autenticación obligatoria para transferencias.
- Métricas: tasa de adopción, tiempo medio de login y tasa de fallback a PIN, con dashboard definido.
- Responsables y fechas: implementa mobile (Ana, 3 semanas), backend (Luis, 2 semanas en paralelo), QA (Diego, 1 semana), con milestones semanales.
- Faltante: no define qué pasa si el usuario tiene la app en dos dispositivos y registra huellas distintas, ni cómo se sincroniza ese estado. El equipo lo marcó como pendiente sin dueño.

Más datos: el spec tiene 6 páginas con 3 diagramas de secuencia y una tabla de estados. La API de backend ya existe de otro proyecto y se reutiliza sin cambios. El mensaje 12 del catálogo ya está aprobado por legales. El equipo de accesibilidad pidió que el tutorial tenga versión con audio y no está incluido. Analytics definió 8 eventos pero el spec solo menciona 3. El pendiente de dos dispositivos   afecta al 8 por ciento de los usuarios según datos de soporte. La fecha de lanzamiento es en 6 semanas y el equipo dice que llega si no se agregan más casos borde.

Ampliación del spec con flujo, bordes, seguridad y métricas:

Flujo feliz: 5 pantallas mockeadas en Figma con link al prototipo navegable (login, enrolar huella, confirmar con PIN de respaldo, éxito, gestión desde ajustes). El flujo tiene 7 pasos con tiempos medidos en test de usabilidad (promedio 45 segundos, 90 por ciento lo completa). El equipo de UX validó con 20 usuarios reales (16 lo completaron sin ayuda, 3 pidieron ayuda en el paso del PIN, 1 abandonó). El spec incluye los textos exactos de cada pantalla y los estados de error con su mensaje.

Casos borde: qué pasa si el dispositivo no tiene sensor (se ofrece PIN como alternativa, afecta al 8 por ciento de los usuarios según soporte), si el usuario rechaza el permiso (se reintenta 1 vez y después se ofrece PIN), si la huella falla 3 veces (se bloquea 30 segundos y se ofrece PIN), si el usuario cambia de dispositivo (hay que re-enrolar con verificación por email), si el PIN de respaldo se olvida (recupero por email con 24 horas de espera), y si el sensor se ensucia o moja (mensaje específico con instrucciones). Faltan 2 bordes que el equipo de seguridad pidió y no están: qué pasa si el usuario rootea el teléfono (el spec no lo menciona) y qué pasa si hay 2 huellas enroladas de distintas personas (el spec asume 1 usuario por dispositivo pero el 15 por ciento comparte el teléfono según la encuesta).

Seguridad: el spec define que la huella se valida en el secure enclave del dispositivo y nunca viaja al servidor (solo un token de enrolamiento). El PIN de respaldo tiene 6 dígitos con 5 intentos antes de bloquear 1 hora. La sesión dura 30 días y se revoca al cambiar la huella enrolada. Falta definir el rate limiting del endpoint de enrolamiento (seguridad lo pidió, el spec dice pendiente) y el log de auditoría de enrolamientos (pedido por compliance, no está). El equipo de seguridad revisó el spec y lo aprobó con 2 observaciones menores (las 2 faltantes de arriba).

Métricas y responsables: el spec define éxito como 40 por ciento de adopción en 3 meses y caída del 50 por ciento en reclamos de login. El tracking incluye eventos de enrolamiento, fallo y abandono por paso. Responsables asignados: UX (pantallas), backend (endpoints), mobile (integración con biometría), seguridad (revisión) y QA (plan de pruebas en 12 dispositivos). La fecha de lanzamiento es en 6 semanas y el equipo dice que llega si no se agregan más casos borde. El product manager dejó por escrito que los 2 bordes faltantes entran en la versión 3, no en esta.
Criterios: se valora completitud del flujo, cobertura de casos borde, definición de seguridad, métricas y asignación de responsables.

Antecedentes del equipo: la versión 1 del login (solo PIN) tuvo 500 reclamos en el primer mes por olvidos de PIN. La huella es el pedido número 1 de los usuarios en las encuestas (mencionado por el 45 por ciento). El equipo mobile ya integró biometría en otra app del mismo grupo (reutiliza el 60 por ciento del código). El QA tiene 12 dispositivos físicos que cubren el 85 por ciento del parque. El lanzamiento anterior (pagos con QR) se demoró 2 semanas por casos borde agregados a último momento; por eso el equipo congeló el alcance de este spec.

Checklist de scoring aplicado: flujo completo (7 pasos con textos exactos, 5 pantallas mockeadas, prototipo navegable, test con 20 usuarios: 16 sin ayuda), casos borde (6 cubiertos con alternativa PIN, 2 diferidos a la versión 3 por escrito: rooteo y huellas compartidas), seguridad (validación en enclave, PIN de 6 dígitos con bloqueo, sesión de 30 días, aprobado por seguridad con 2 observaciones: rate limiting y auditoría pendientes), métricas (adopción 40 por ciento, caída de reclamos 50 por ciento, eventos por paso), responsables (5 asignados con entregables). El revisor marcó flujo, métricas y responsables como completos, seguridad como aprobada con observaciones y bordes como parcial con diferimiento justificado. El equipo dice que llega en 6 semanas si no se agregan más bordes; agregar los 2 faltantes sumaría 2 semanas y movería la fecha que el directorio ya comunicó.

Comparación con el spec anterior: el spec de pagos con QR (versión 1) tenía 4 páginas, 3 pantallas sin prototipo, 2 bordes cubiertos y 0 métricas, y se demoró 2 semanas por bordes agregados a último momento. Este spec tiene 6 páginas, 5 pantallas con prototipo, 6 bordes cubiertos, métricas con eventos y 5 responsables. El revisor que puntuó el anterior con 2 sobre 5 (deficiente) dice que este es el mejor spec del año pero mantiene las 2 observaciones de seguridad (rate limiting y auditoría) como condición para no bajar el puntaje. El equipo de seguridad aceptó que entren en la versión 3 solo si hay fecha comprometida (todavía no hay). La fecha de lanzamiento en 6 semanas ya se comunicó a marketing y moverla cuesta la campaña (15000 USD).

Decisión del dueño de producto: puntúa el spec de 0 a 5 según flujo, bordes, seguridad, métricas y responsables. El spec trae flujo validado con 20 usuarios, 6 bordes con 2 diferidos por escrito, seguridad aprobada con 2 observaciones, métricas con eventos y 5 responsables. Las 2 observaciones de seguridad (rate limiting y auditoría) son la única mancha y el equipo pide que no bajen el puntaje porque van a la versión 3. El revisor debe decidir si el diferimiento justificado por escrito mantiene el puntaje o si la falta de rate limiting y auditoría en un login con biometría lo baja. La fecha comunicada a marketing (6 semanas, campaña de 15000 USD) presiona para no reabrir el alcance.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "incompleto", "1": "flojo", "2": "aceptable", "3": "solido", "4": "ejemplar"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá la calidad del spec según los criterios.",
    "criteria": [
      "incompleto",
      "flojo",
      "aceptable",
      "solido",
      "ejemplar"
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
        "score": 3.220378359546199,
        "confidence": 0.8129558501629481,
        "legend": {
          "0": "incompleto",
          "1": "flojo",
          "2": "aceptable",
          "3": "solido",
          "4": "ejemplar"
        },
        "probabilities": {
          "0": 0.00019052871886895777,
          "1": 0.0003789117829253816,
          "2": 0.00070790040667378,
          "3": 0.776306989416201,
          "4": 0.22241566967533083
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1913,
    "completion_tokens": 1,
    "total_tokens": 1914,
    "total_time": 6.81
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "4.2",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1915,
    "completion_tokens": 3,
    "total_tokens": 1918,
    "total_time": 1.56,
    "time_to_first_token": 1.56
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "3.5",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1953,
    "completion_tokens": 1085,
    "total_tokens": 3038,
    "total_time": 1.54,
    "time_to_first_token": 1.54
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "3.5",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2252,
    "completion_tokens": 2807,
    "total_tokens": 5059,
    "total_time": 27.75,
    "time_to_first_token": 27.75
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "3",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1965,
    "completion_tokens": 2,
    "total_tokens": 1967,
    "total_time": 0.52,
    "time_to_first_token": 0.52
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 1913 | 1 | 6.82 | 3.22 | 0.8129558501629481 | 0.0 |
| google | gemini-3.5-flash-lite | 1915 | 3 | 1.56 | 4.2 | null | 0.000582 |
| groq | openai/gpt-oss-20b | 1953 | 1085 | 1.54 | 3.5 | null | 0.000471975 |
| openrouter | inclusionai/ling-3.1-flash | 2252 | 2807 | 27.76 | 3.5 | null | 0.0 |
| groq | qwen/qwen3.8-27b | 1965 | 2 | 0.53 | 3.0 | null | 0.00158 |
