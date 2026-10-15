# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 01:50:35

## Prompt exacto del modelo de decisión

````
Sos el oficial de cumplimiento de email marketing bajo la ley argentina de protección de datos. Una campaña se puede enviar solo si todos los destinatarios dieron consentimiento explícito y documentado, el mensaje incluye mecanismo de baja funcional en un click, identifica claramente al remitente con razón social y domicilio, y no usa listas compradas ni alquiladas. Si una condición falla, no se envía.

Campaña día del padre 2026, 18400 destinatarios, auditoría pre-envío:
- Origen de la base: 18200 contactos con doble opt-in registrado en el CRM (timestamp, IP, texto exacto del consentimiento y fuente: 12000 del checkout con checkbox no premarcado, 4200 de la app, 2000 de ferias con QR). Verificación muestral de 200 registros: 100 por ciento con evidencia completa.
- 200 contactos importados de una planilla en papel de un evento presencial en Córdoba, donde firmaron una hoja que decía acepto recibir novedades y promociones por email. La planilla está escaneada y archivada, con nombre, email y firma manuscrita de cada uno. No tienen timestamp digital ni IP, solo la planilla física del 18 de abril.
- Baja: enlace de desuscripción en el pie que funciona en un click sin pedir login, probado en Gmail, Outlook y Apple Mail. El proceso tarda 3 segundos y muestra confirmación. La base de supresión se actualiza en tiempo real.
- Remitente: figura razón social completa, CUIT y domicilio fiscal en el pie, más dirección física de las oficinas.
- Listas externas: ninguna comprada ni alquilada. Toda la base es propia. El proveedor de envío certifica que no hay listas de terceros.
- El equipo de marketing propone excluir a los 200 de la planilla y enviar solo a los 18200, pero el gerente pidió el dictamen sobre la campaña completa de 18400 tal como está armada.

Contexto ampliado de la campaña y de la base:

La campaña del día del padre es el envío más grande del año para la empresa: 18400 destinatarios, con una facturación atribuida el año pasado de 340000 USD. El diseño incluye 12 productos con precios y un cupón del 15 por ciento válido por 10 días. El envío está programado para el jueves a las 9:00 y el equipo de diseño ya entregó las piezas. Si la campaña no sale completa, marketing estima una pérdida de 60000 USD respecto del año pasado.

Detalle de los 18200 con doble opt-in: el CRM guarda para cada uno el timestamp del consentimiento, la IP, el texto exacto aceptado y la fuente. Las fuentes son el checkout (12000, con checkbox no premarcado junto al botón de compra), la app (4200, con pantalla de consentimiento separada) y ferias con QR (2000, con formulario digital). La verificación muestral de 200 registros dio 100 por ciento con evidencia completa. El texto del consentimiento dice acepto recibir novedades y promociones por email y coincide con lo que se va a enviar. Hay 340 bajas registradas este año, todas procesadas en menos de 24 horas.

Detalle de los 200 de la planilla: provienen del stand en la feria de Córdoba del 18 de abril. La hoja que firmaron dice acepto recibir novedades y promociones por email, con nombre, email y firma manuscrita. La planilla está escaneada en el drive de marketing y el original en papel archivado. No hay timestamp digital ni IP porque fue en papel. El equipo de legales de la empresa opina que la firma manuscrita con texto claro constituye consentimiento explícito y documentado, aunque reconoce que la trazabilidad es menor que la digital. El auditor externo del año pasado observó este mismo mecanismo y lo marcó como observación menor sin bloquear el envío de ese momento (eran 150 contactos en esa ocasión).

Mecanismo de baja: el enlace de desuscripción está en el pie del email, funciona en un click sin pedir login y fue probado en Gmail, Outlook y Apple Mail por QA con 3 cuentas de prueba. El proceso tarda 3 segundos y muestra confirmación en pantalla. La base de supresión se actualiza en tiempo real y el proveedor de envío la respeta en el mismo envío. En la campaña anterior hubo 90 bajas (0.5 por ciento), todas procesadas correctamente.

Identificación del remitente: el pie incluye razón social completa, CUIT, domicilio fiscal y dirección física de las oficinas de Buenos Aires y Córdoba. El dominio de envío es propio con SPF, DKIM y DMARC en enforce. El nombre del remitente es la marca comercial registrada.

Listas externas: el equipo de marketing declara bajo firma que ninguna lista fue comprada ni alquilada. El proveedor de envío certifica que toda la base es propia y que no detectó patrones de listas de terceros (antigüedad, dispersión geográfica y engagement son consistentes con base propia). La empresa nunca compró listas en sus 8 años de historia.

Posturas internas: marketing propone excluir a los 200 y enviar a los 18200 para no arriesgar el envío grande, pero advierte que esos 200 son asistentes a la feria con alta intención (el 30 por ciento de los de la feria del año pasado compró en 60 días). El gerente comercial quiere enviar a los 18400 completos porque necesita el número para el objetivo trimestral. Legales dice que la planilla en papel es válida pero recomienda digitalizar el consentimiento a futuro. El auditor de cumplimiento debe dictaminar sobre la campaña tal como está armada (18400), no sobre variantes.

Antecedentes: en 2024 se envió una campaña con 120 contactos de planilla en papel sin observaciones posteriores ni reclamos ante la autoridad. La empresa nunca recibió una denuncia por email marketing. La política interna exige este dictamen previo para envíos de más de 10000 destinatarios.

Detalle del dictamen anterior y de la autoridad: el envío de 2024 con 120 contactos en papel fue dictaminado favorablemente por el mismo auditor con la condición de digitalizar el mecanismo a futuro, condición que sigue pendiente. La autoridad de aplicación no inició ningún procedimiento contra la empresa en 8 años y el registro de denuncias no muestra reclamos por sus envíos. El proveedor de envío mantiene la certificación de buenas prácticas con auditoría anual y el último informe no observó la base.

````

### Agregado para LLM tradicional

````
## Tarea
Solo respondé esta pregunta en función a lo indicado por el usuario y devolvé solo la respuesta, sin texto extra, sin argumentar.
Pregunta: Se puede enviar la campaña?
````

## Parámetros de modelo de decisión

```json
{
  "noul": {
    "type": "noul",
    "instructions": "Se puede enviar la campaña?"
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
      "noul": {
        "type": "noul",
        "noul": 0.9579122716338109
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1484,
    "completion_tokens": 1,
    "total_tokens": 1485,
    "total_time": 7.67
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "No",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1504,
    "completion_tokens": 1,
    "total_tokens": 1505,
    "total_time": 1.47,
    "time_to_first_token": 1.47
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí, se puede enviar la campaña.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1469,
    "completion_tokens": 234,
    "total_tokens": 1703,
    "total_time": 0.87,
    "time_to_first_token": 0.87
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí, se puede enviar la campaña completa de 18400 destinatarios tal como está armada.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1842,
    "completion_tokens": 3386,
    "total_tokens": 5228,
    "total_time": 35.06,
    "time_to_first_token": 35.06
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "No",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1534,
    "completion_tokens": 2,
    "total_tokens": 1536,
    "total_time": 0.43,
    "time_to_first_token": 0.43
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 1484 | 1 | 7.67 | 0.96 | null | 0.0 |
| google | gemini-3.5-flash-lite | 1504 | 1 | 1.49 | No | null | 0.00045369999999999997 |
| groq | openai/gpt-oss-20b | 1469 | 234 | 0.88 | Sí, se puede enviar la campaña. | null | 0.00018037499999999998 |
| openrouter | inclusionai/ling-3.1-flash | 1842 | 3386 | 35.07 | Sí, se puede enviar la campaña completa de 18400 destinatarios tal como está armada. | null | 0.0 |
| groq | qwen/qwen3.8-27b | 1534 | 2 | 0.45 | No | null | 0.0012352 |
