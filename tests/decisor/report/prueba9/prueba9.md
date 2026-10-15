# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 01:24:20

## Prompt exacto del modelo de decisión

````
Sos el filtro antiphishing del correo corporativo. Un mensaje se marca como phishing si cumple al menos dos de estas señales: el dominio del remitente no coincide con el dominio declarado en la firma, contiene un enlace con texto visible distinto a la URL real, pide credenciales o datos bancarios con urgencia, o el Reply-To apunta a un dominio gratuito distinto al del remitente. Con una sola señal se deja pasar con advertencia, con dos o más se bloquea.

Mensaje recibido, análisis completo:
- De: Facturación Acme <facturacion@acme-facturas.com>. Reply-To: facturacion@acme-facturas.com (mismo dominio, no gratuito).
- Firma: Departamento de Facturación, Acme SA, www.acme.com, CUIT 30-69887766-5.
- Headers de autenticación: SPF pass (el servidor de envío está en el registro SPF de acme-facturas.com), DKIM pass (firma válida del mismo dominio), DMARC pass con política quarantine. IP de origen en rango declarado por el proveedor de email de Acme.
- Dominio acme-facturas.com: registrado a nombre de Acme SA desde 2019, usado históricamente para facturación electrónica (hay 340 mensajes previos del mismo remitente en 2 años, todos legítimos).
- Asunto: Tu factura de marzo está lista. Cuerpo: informa la factura 0004-00088112 por 45230 pesos con vencimiento el 10 de abril según los términos habituales. No pide contraseñas, ni datos bancarios, ni acciones urgentes fuera de lo normal.
- Enlaces (3 en total): el principal dice portal.acme.com/facturas y apunta a https://portal.acme.com/facturas/marzo-2026 (mismo dominio, distinta ruta por el mes). Los otros dos son el pie legal (acme.com/legales) y desuscripción (acme.com/baja), ambos con texto y URL idénticos.
- Adjuntos: un PDF de 84 KB con la factura, hash limpio en los 3 antivirus, sin macros ni scripts.
- Reporte del usuario: lo marcó como sospechoso porque no recordaba haber comprado en marzo; el área de compras confirmó la orden 7710 que originó la factura.

````

### Agregado para LLM tradicional

````
## Tarea
Solo respondé esta pregunta en función a lo indicado por el usuario y devolvé solo la respuesta, sin texto extra, sin argumentar.
Pregunta: El mensaje debe bloquearse como phishing?
````

## Parámetros de modelo de decisión

```json
{
  "noul": {
    "type": "noul",
    "instructions": "El mensaje debe bloquearse como phishing?"
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
        "noul": 0.0758581737534831
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 585,
    "completion_tokens": 1,
    "total_tokens": 586,
    "total_time": 1.2
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
    "prompt_tokens": 579,
    "completion_tokens": 1,
    "total_tokens": 580,
    "total_time": 1.29,
    "time_to_first_token": 1.29
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "No.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 601,
    "completion_tokens": 197,
    "total_tokens": 798,
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
  "data": "No.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 662,
    "completion_tokens": 2541,
    "total_tokens": 3203,
    "total_time": 24.81,
    "time_to_first_token": 24.81
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
    "prompt_tokens": 584,
    "completion_tokens": 2,
    "total_tokens": 586,
    "total_time": 0.3,
    "time_to_first_token": 0.3
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 585 | 1 | 1.21 | 0.08 | null | 0.0 |
| google | gemini-3.5-flash-lite | 579 | 1 | 1.3 | No | null | 0.0001762 |
| groq | openai/gpt-oss-20b | 601 | 197 | 0.88 | No. | null | 0.000104175 |
| openrouter | inclusionai/ling-3.1-flash | 662 | 2541 | 24.81 | No. | null | 0.0 |
| groq | qwen/qwen3.8-27b | 584 | 2 | 0.31 | No | null | 0.0004752 |
