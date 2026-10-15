# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:14:08

## Prompt exacto del modelo de decisión

````
Sos el director comercial que puntúa un email de prospección. Puntuá el borrador según los criterios indicados.

Borrador enviado a 300 gerentes de logística:

Asunto: Consulta
Cuerpo: Estimado, me llamo Diego y trabajo en una empresa de software. Tenemos una solución muy buena que le sirve a empresas como la suya. Me gustaría agendar una reunión de 30 minutos para contarle más. Quedo a disposición. Saludos.

Datos de la campaña: tasa de apertura 18 por ciento, tasa de respuesta 0.3 por ciento (1 respuesta de 300, y fue para pedir que no escriban más). El asunto no dice nada, no menciona ningún dolor del destinatario, no hay prueba social ni números, no hay propuesta de valor concreta, el llamado a la acción es genérico y no hay personalización más allá del nombre. Cumple formalidades básicas: firma con datos de contacto, enlace de baja funcional y se envió solo a base propia con consentimiento.

Más datos: la base de 300 es propia y segmentada por rubro, pero el texto es idéntico para todos. El benchmark del sector para este público es 25 por ciento de apertura y 2 por ciento de respuesta. El email se envió un lunes a las 9:00 sin test A/B. El remitente es una casilla genérica (info@) sin foto ni cargo. La firma incluye teléfono y LinkedIn del vendedor. El equipo de marketing discute si el problema es el texto o el segmento: la mitad dice que estos 300 ya fueron contactados 3 veces este año con otros borradores igual de genéricos. El costo de la campaña fue casi cero (solo tiempo del redactor) y el gerente pide repetirla con otro asunto.

Criterios: se valora asunto, personalización, propuesta de valor, prueba social, llamado a la acción y respeto de normas.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "pesimo", "1": "malo", "2": "regular", "3": "bueno", "4": "muy bueno", "5": "excelente"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá la calidad del email según los criterios.",
    "criteria": [
      "pesimo",
      "malo",
      "regular",
      "bueno",
      "muy bueno",
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
        "score": 0.13455086510702802,
        "confidence": 0.9102994232619813,
        "legend": {
          "0": "pesimo",
          "1": "malo",
          "2": "regular",
          "3": "bueno",
          "4": "muy bueno",
          "5": "excelente"
        },
        "probabilities": {
          "0": 0.8663773871958229,
          "1": 0.13286326558952613,
          "2": 0.0006549610708778336,
          "3": 6.092089850991204e-05,
          "4": 2.2411546099488597e-05,
          "5": 2.1053699163705992e-05
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 558,
    "completion_tokens": 1,
    "total_tokens": 559,
    "total_time": 1.09
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "0.4",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 512,
    "completion_tokens": 3,
    "total_tokens": 515,
    "total_time": 0.69,
    "time_to_first_token": 0.69
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "1",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 569,
    "completion_tokens": 170,
    "total_tokens": 739,
    "total_time": 0.55,
    "time_to_first_token": 0.55
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "1.2",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 635,
    "completion_tokens": 274,
    "total_tokens": 909,
    "total_time": 4.05,
    "time_to_first_token": 4.05
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "1.2",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 534,
    "completion_tokens": 4,
    "total_tokens": 538,
    "total_time": 0.45,
    "time_to_first_token": 0.45
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 558 | 1 | 1.09 | 0.13 | 0.9102994232619813 | 0.0 |
| google | gemini-3.5-flash-lite | 512 | 3 | 0.69 | 0.4 | null | 0.00016109999999999999 |
| groq | openai/gpt-oss-20b | 569 | 170 | 0.55 | 1.0 | null | 9.3675e-05 |
| openrouter | inclusionai/ling-3.1-flash | 635 | 274 | 4.05 | 1.2 | null | 0.0 |
| groq | qwen/qwen3.8-27b | 534 | 4 | 0.45 | 1.2 | null | 0.00044320000000000004 |
