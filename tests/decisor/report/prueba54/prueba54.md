# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:25:01

## Prompt exacto del modelo de decisión

````
Sos el QA manager que puntúa un plan de pruebas. Puntuá el plan según los criterios indicados.

Plan de pruebas para el lanzamiento de pagos con QR en la app, 12 páginas:
- Alcance: cubre flujo feliz, 18 casos borde (sin cámara, sin internet a mitad del pago, QR vencido, monto cero, doble escaneo), pruebas de concurrencia con 500 pagos simultáneos, y pruebas de accesibilidad básica.
- Datos: define 40 juegos de datos con QR válidos, vencidos y malformados, más usuarios con distintos saldos y límites.
- Entornos: staging espejo de producción con el simulador del procesador, más 10 dispositivos físicos de distintas gamas.
- Criterios de salida: cero bugs críticos, menos de 3 mayores, 95 por ciento de casos pasados, y rollback probado.
- Riesgos: identifica la dependencia del simulador (puede diferir del procesador real) y propone una ventana de beta con 1000 usuarios reales antes del lanzamiento general.
- Debilidad: no incluye pruebas de performance del backend bajo carga sostenida de 1 hora (solo picos de 5 minutos), ni pruebas de seguridad más allá del checklist OWASP sin pentest.

Más datos: el lanzamiento es en 10 semanas y el plan prevé 6 semanas de ejecución con 2 testers manuales más 1 automatizador que entra el mes que viene. El simulador del procesador lo mantiene otro equipo que avisa cambios con 1 semana de anticipación (el año pasado un cambio no avisado rompió 40 casos). Los 10 dispositivos físicos cubren el 80 por ciento del parque instalado según analytics. El beta de 1000 usuarios lo tiene que aprobar legales por manejo de dinero real. El presupuesto de testing es 30000 USD y el plan consume 25000. La última vez que lanzaron algo parecido (pagos con tarjeta) hubo 2 bugs críticos en producción por casos borde no cubiertos.

Detalle ampliado del plan y del contexto del lanzamiento:

Los 18 casos borde cubren sin cámara, sin internet a mitad del pago, QR vencido, monto cero, doble escaneo, QR de otro comercio, monto con más de 2 decimales, pago con saldo exacto, pago con saldo insuficiente, cancelación a mitad del flujo, rotación de pantalla durante el pago, app en segundo plano por llamada entrante, cambio de red wifi a datos a mitad del pago, QR impreso dañado, QR en pantalla con brillo bajo, doble confirmación rápida, timeout del procesador y reverso del pago. Cada caso tiene pasos, datos y resultado esperado. Lo que no está: pago con tarjeta extranjera, QR con monto en otra moneda, ni accesibilidad más allá de lo básico (contraste y tamaño de fuente, sin lector de pantalla completo).

Datos de prueba: 40 juegos con QR válidos, vencidos y malformados, usuarios con saldos de 0 a 500000, límites diarios variados y comercios de 3 rubros. Los datos se generan con un script versionado y se resetean cada noche. No hay datos de performance históricos para comparar (es la primera vez que se mide concurrencia en este flujo).

Entornos: staging espejo de producción con el simulador del procesador (versión 3.2, la producción usa 3.4 con 2 diferencias conocidas en timeouts), más 10 dispositivos físicos de distintas gamas que cubren el 80 por ciento del parque instalado (quedan afuera 3 modelos viejos con Android 9 que representan el 8 por ciento de los usuarios). No hay entorno de performance dedicado: las pruebas de concurrencia con 500 pagos simultáneos se corren en staging de noche.

Equipo y tiempos: 2 testers manuales desde ya más 1 automatizador que entra el mes que viene (semana 5 de 10). El plan prevé 6 semanas de ejecución y 2 de buffer antes del lanzamiento. El automatizador todavía no está contratado (hay 2 candidatos en proceso). Los testers manuales conocen el flujo pero nunca probaron pagos. El líder de QA estima que sin automatizador se cubre el 70 por ciento del plan.

Simulador y riesgos: el simulador lo mantiene el equipo de integraciones con 1 semana de aviso ante cambios. El año pasado un cambio no avisado rompió 40 casos y se perdieron 3 días. La propuesta de ventana beta con 1000 usuarios reales antes del lanzamiento general requiere aprobación de legales por manejo de dinero real (trámite de 3 semanas, todavía no iniciado). El riesgo del simulador está identificado en el plan con mitigación (validación cruzada de 50 casos contra el procesador real en sandbox), pero la mitigación no tiene dueño ni fecha.

Criterios de salida: cero bugs críticos, menos de 3 mayores, 95 por ciento de casos pasados y rollback probado. El rollback consiste en desactivar el QR por feature flag y volver al flujo anterior (probado 1 vez en staging). No hay criterio de performance (tiempo de pago aceptable) ni de monitoreo post-lanzamiento en el plan.

Presupuesto: 30000 USD total, el plan consume 25000 (18000 en horas, 5000 en dispositivos, 2000 en el beta). Quedan 5000 de margen. El lanzamiento anterior (pagos con tarjeta) costó 35000 con 2 bugs críticos en producción por casos borde no cubiertos (uno era doble escaneo, que este plan sí cubre).

Automatización: el plan prevé automatizar 60 de los 120 casos con el automatizador que entra en la semana 5. Si la contratación se cae, esos 60 casos se hacen manuales y el plan se estira 2 semanas, comiéndose el buffer. Los 2 testers manuales nunca automatizaron y no hay framework previo: habría que crearlo desde cero.

Beta con usuarios reales: los 1000 usuarios del beta saldrían del programa de early adopters (5000 anotados). Legales exige consentimiento explícito para mover dinero real en beta y un fondo de resarcimiento de 10000 USD por errores (no presupuestado). El trámite tarda 3 semanas y todavía no se inició. Sin beta, el lanzamiento sería directo al 100 por ciento.

Dispositivos y cobertura: los 10 físicos cubren el 80 por ciento del parque (gamas medias y altas de los últimos 3 años). Quedan afuera 3 modelos con Android 9 (8 por ciento de los usuarios) donde el QR se escanea con una librería vieja. El plan no incluye esos modelos y el equipo discute si comprar 2 de esos equipos usados por 300 USD o excluirlos del soporte con un mensaje en la app.
Criterios: se valora cobertura, datos, entornos, criterios de salida, gestión de riesgos y performance.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "insuficiente", "1": "basico", "2": "aceptable", "3": "completo", "4": "ejemplar"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá la calidad del plan según los criterios.",
    "criteria": [
      "insuficiente",
      "basico",
      "aceptable",
      "completo",
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
        "score": 2.174853666608772,
        "confidence": 0.8397004524078712,
        "legend": {
          "0": "insuficiente",
          "1": "basico",
          "2": "aceptable",
          "3": "completo",
          "4": "ejemplar"
        },
        "probabilities": {
          "0": 0.0014698207358440952,
          "1": 0.005813253779202975,
          "2": 0.8104911324245355,
          "3": 0.18084502426117124,
          "4": 0.001380768799246058
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1696,
    "completion_tokens": 1,
    "total_tokens": 1697,
    "total_time": 5.88
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "2.2",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1639,
    "completion_tokens": 3,
    "total_tokens": 1642,
    "total_time": 1.37,
    "time_to_first_token": 1.37
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "2.4",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1613,
    "completion_tokens": 692,
    "total_tokens": 2305,
    "total_time": 1.35,
    "time_to_first_token": 1.35
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "2.3",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1977,
    "completion_tokens": 1088,
    "total_tokens": 3065,
    "total_time": 16.04,
    "time_to_first_token": 16.04
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1279. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}",
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
| openrouter | inception/mercury-decide:free | 1696 | 1 | 5.89 | 2.17 | 0.8397004524078712 | 0.0 |
| google | gemini-3.5-flash-lite | 1639 | 3 | 1.39 | 2.2 | null | 0.0004992 |
| groq | openai/gpt-oss-20b | 1613 | 692 | 1.36 | 2.4 | null | 0.000328575 |
| openrouter | inclusionai/ling-3.1-flash | 1977 | 1088 | 16.05 | 2.3 | null | 0.0 |
| groq | qwen/qwen3.8-27b | 0 | 0 | 0.14 | "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1279. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}" | null | 0.0 |
