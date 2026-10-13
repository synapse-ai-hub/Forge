# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 01:37:05

## Prompt exacto del modelo de decisión

````
Sos el aprobador de pagos a proveedores. Un pago se aprueba solo si existe orden de compra abierta por el mismo monto o mayor, la factura coincide en CUIT y razón social con el proveedor registrado, el monto no supera los 50000 USD sin aprobación del director financiero, y la mercadería o servicio figura como recibido. Si algo no cierra, se retiene.

Caso: factura 0004-00088123 de Metalúrgica Andina SRL por 38500 USD en concepto de 12 toneladas de chapa galvanizada calibre 22, con vencimiento a 30 días.
- Orden de compra 7712: abierta el 12 de mayo por 40000 USD para el mismo concepto y proveedor, con saldo disponible de 40000 USD (sin consumos previos). La OC fue aprobada por el jefe de planta y el gerente de compras según el flujo de doble firma para montos sobre 10000 USD.
- Proveedor: Metalúrgica Andina SRL, CUIT 30-70112233-4, legajo activo desde 2019, estado en AFIP activo sin retenciones pendientes. CUIT y razón social de la factura coinciden carácter por carácter con el legajo. Domicilio fiscal coincidente.
- Recepción: remito 55231 firmado por el jefe de depósito el 3 de junio a las 10:20, con pesaje de balanza (12.04 toneladas) y control de calidad aprobado sin observaciones (espesor y galvanizado dentro de tolerancia, informe QC-2291 adjunto).
- Monto: 38500 USD, por debajo del umbral de 50000 USD que exige firma del director financiero. Tipo de cambio aplicado el del día de recepción según cláusula del contrato marco 2026.
- Historial: el proveedor entregó 4 veces este año (enero, febrero, abril, mayo), siempre en fecha, con calidad aprobada y sin reclamos. Precio unitario 3208 USD por tonelada, 2 por ciento debajo del promedio de las otras dos cotizaciones del trimestre.
- Deuda: no hay facturas vencidas impagas con este proveedor; la última se pagó a 28 días.

Historial completo del proveedor y de la relación comercial:

Metalúrgica Andina SRL es proveedora desde 2019 con legajo activo y 23 operaciones cerradas sin reclamos. Este año entregó 4 veces (enero, febrero, abril, mayo) siempre en fecha y con calidad aprobada: enero 10 toneladas en 6 días, febrero 8 toneladas en 5 días, abril 12 toneladas en 7 días, mayo 10 toneladas en 6 días. El plazo contractual es 10 días y el promedio real es 6. El control de calidad aprobó las 4 entregas sin observaciones (espesor, galvanizado y ancho dentro de tolerancia en los 4 informes QC). El precio unitario de esta factura es 3208 USD por tonelada, 2 por ciento debajo del promedio de las otras 2 cotizaciones del trimestre (3270 y 3290) y 1 por ciento debajo del promedio histórico del proveedor (3240).

La orden de compra 7712: abierta el 12 de mayo por 40000 USD para 12 toneladas de chapa galvanizada calibre 22, con doble firma del jefe de planta y el gerente de compras (flujo obligatorio sobre 10000 USD). Sin consumos previos: saldo disponible 40000 USD. La OC detalla especificaciones (calibre 22, galvanizado Z275, ancho 1000 mm) que coinciden con lo recibido según el informe QC-2291. La OC vence en 60 días y lleva 22 días abierta. El área de compras confirma que no hay otra OC abierta con este proveedor para el mismo concepto.

Recepción y control: remito 55231 firmado por el jefe de depósito el 3 de junio a las 10:20, con pesaje de balanza fiscal (12.04 toneladas, diferencia de 0.3 por ciento sobre las 12 facturadas, dentro de la tolerancia de 1 por ciento). El control de calidad midió espesor en 20 puntos (todos entre 0.68 y 0.72 mm para calibre 22) y galvanizado por encima del mínimo Z275. El informe QC-2291 está firmado y archivado. La mercadería ingresó al stock el mismo día y ya se consumieron 2 toneladas en producción sin reclamos de planta.

Factura y proveedor registrado: factura 0004-00088123 por 38500 USD con vencimiento a 30 días (3 de julio). CUIT 30-70112233-4 y razón social Metalúrgica Andina SRL coinciden carácter por carácter con el legajo. Domicilio fiscal coincidente con el registrado. Estado en AFIP activo sin retenciones pendientes (verificado el 4 de junio). El proveedor factura siempre con el mismo punto de venta (0004) y la numeración es correlativa con la última registrada (0004-00088119 de mayo).

Umbral de aprobación: 38500 USD por debajo de los 50000 USD que exigen firma del director financiero. El flujo para este monto requiere doble firma de planta y compras (cumplido) más recepción conforme (cumplido). El tipo de cambio aplicado es el del día de recepción según el contrato marco 2026 (cláusula 7.3). La factura está en USD y se paga por transferencia a la cuenta declarada en el legajo (misma cuenta de las 23 operaciones anteriores).

Pagos anteriores: la última factura (mayo, 32000 USD) se pagó a 28 días sin descuentos ni recargos. No hay facturas vencidas impagas ni notas de débito pendientes. El proveedor nunca pidió adelantos ni cambió condiciones de pago. El límite de crédito interno para este proveedor es 60000 USD y con esta factura el expuesto llega a 38500 USD.

Contexto del área y del flujo: el área de pagos procesa 200 facturas por mes con 2 analistas y un supervisor. El SLA de aprobación es 5 días hábiles y esta factura lleva 2 días en circuito. En lo que va del año se retuvieron 12 pagos (8 por falta de recepción, 3 por diferencias de CUIT y 1 por superar el umbral sin firma del director). Ninguna retención fue de este proveedor. La auditoría externa de marzo no observó el circuito de pagos. El contrato marco 2026 con el proveedor incluye cláusula de pronto pago con 2 por ciento de descuento a 10 días, que vence mañana: si se aprueba hoy, tesorería puede pagar con descuento y ahorrar 770 USD.

Contrato marco 2026 y condiciones: firmado en enero con vigencia anual, cubre chapa galvanizada calibre 20 a 24 con precios por tonelada revisables trimestralmente. El precio de esta factura (3208 USD por tonelada) corresponde a la revisión de abril y está vigente hasta julio. La cláusula 7.3 fija el tipo de cambio del día de recepción para facturas en USD. La cláusula 9.1 establece el descuento por pronto pago (2 por ciento a 10 días) que el proveedor ofrece desde 2024 y que la empresa usó 3 veces este año (ahorro total 2100 USD). El contrato incluye penalidad por entrega tardía (1 por ciento por día sobre el valor) que nunca se aplicó porque el proveedor siempre entregó en fecha.

Tesorería y programación: tesorería programa pagos los martes y jueves. Si se aprueba hoy (jueves), el pago sale en el lote de hoy y alcanza el descuento por pronto pago (vence mañana viernes). Si se aprueba el lunes, se pierde el descuento de 770 USD pero el pago sigue dentro del vencimiento a 30 días (3 de julio). El flujo de caja de junio tiene margen para el pago anticipado según el reporte de tesorería del lunes. El supervisor de pagos ya visó el expediente y lo elevó para aprobación final.

Verificación AFIP y legajo: CUIT 30-70112233-4 activo, sin retenciones pendientes, domicilio fiscal coincidente, punto de venta 0004 con numeración correlativa (última registrada 0004-00088119). El legajo del proveedor se actualizó en marzo con balance 2025 y certificado de calidad ISO 9001 vigente. La auditoría externa de marzo revisó 5 legajos al azar (incluido este) sin observaciones. El proveedor está en la lista de proveedores estratégicos con 23 operaciones cerradas y cero reclamos en 6 años.

Checklist de aprobación aplicado: proveedor registrado y activo (sí, legajo vigente), OC abierta con saldo suficiente (sí, 7712 por 40000 sin consumos), recepción conforme con pesaje y QC (sí, remito 55231 e informe QC-2291), factura coincidente en CUIT, razón social, monto y punto de venta (sí, verificado carácter por carácter), monto bajo el umbral de 50000 USD (sí, 38500), doble firma de planta y compras (sí, consta en la OC), sin facturas vencidas impagas (sí, última pagada a 28 días). Los 8 puntos del checklist están tildados por el analista y visados por el supervisor. En lo que va del año, 188 facturas pasaron este checklist sin observaciones y 12 fueron retenidas (ninguna de este proveedor). El expediente lleva 2 días en circuito contra un SLA de 5 días.

Decisión de tesorería y descuento: si se aprueba hoy jueves, el pago sale en el lote de hoy y se usa el descuento por pronto pago del 2 por ciento (770 USD de ahorro, vence mañana viernes). Tesorería confirmó por email que el flujo de junio admite el pago anticipado y que el lote de hoy cierra a las 16:00. El supervisor de pagos visó el expediente a las 10:00 y lo elevó para la aprobación final. Si la aprobación llega después de las 16:00, el pago pasa al lote del martes y se pierde el descuento pero se mantiene dentro del vencimiento del 3 de julio. El gerente de compras pide que conste en el acta si se aprovecha el descuento para informar el ahorro en el reporte mensual (este año se ahorraron 2100 USD con 3 descuentos similares). El proveedor nunca reclamó un pago y su cuenta bancaria es la misma de las 23 operaciones anteriores (verificada contra el legajo).

Cierre del expediente: el expediente lleva 2 días contra un SLA de 5. El analista marcó los 8 puntos del checklist y el supervisor los visó. La aprobación de hoy permite el pago en el lote de las 16:00 con el descuento de 770 USD. Si se retiene, el motivo debe registrarse por escrito según el procedimiento (las 12 retenciones del año tienen motivo registrado: 8 por recepción, 3 por CUIT, 1 por umbral). No hay motivo de retención en este expediente: proveedor activo, OC con saldo, recepción conforme, factura coincidente, monto bajo umbral, doble firma, sin deuda vencida. El gerente de planta (uno de los firmantes) confirmó que las 12 toneladas ya se consumieron 2 en producción sin reclamos y que necesita el resto para el plan de la semana que viene.

````

### Agregado para LLM tradicional

````
## Tarea
Solo respondé esta pregunta en función a lo indicado por el usuario y devolvé solo la respuesta, sin texto extra, sin argumentar.
Pregunta: Se aprueba el pago?
````

## Parámetros de modelo de decisión

```json
{
  "noul": {
    "type": "noul",
    "instructions": "Se aprueba el pago?"
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
        "noul": 0.9998601779009003
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2733,
    "completion_tokens": 1,
    "total_tokens": 2734,
    "total_time": 1.4
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2714,
    "completion_tokens": 1,
    "total_tokens": 2715,
    "total_time": 1.42,
    "time_to_first_token": 1.42
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2533,
    "completion_tokens": 214,
    "total_tokens": 2747,
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
  "data": "Sí, se aprueba el pago.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 3288,
    "completion_tokens": 694,
    "total_tokens": 3982,
    "total_time": 7.55,
    "time_to_first_token": 7.55
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí, se aprueba el pago.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2747,
    "completion_tokens": 9,
    "total_tokens": 2756,
    "total_time": 0.53,
    "time_to_first_token": 0.53
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 2733 | 1 | 1.41 | 1.0 | null | 0.0 |
| google | gemini-3.5-flash-lite | 2714 | 1 | 1.41 | Sí | null | 0.0008167 |
| groq | openai/gpt-oss-20b | 2533 | 214 | 0.84 | Sí | null | 0.000254175 |
| openrouter | inclusionai/ling-3.1-flash | 3288 | 694 | 7.56 | Sí, se aprueba el pago. | null | 0.0 |
| groq | qwen/qwen3.8-27b | 2747 | 9 | 0.54 | Sí, se aprueba el pago. | null | 0.0022336 |
