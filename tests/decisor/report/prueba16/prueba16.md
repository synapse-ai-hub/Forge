# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 01:44:41

## Prompt exacto del modelo de decisión

````
Sos un validador de respuestas de API contra su contrato OpenAPI. La respuesta cumple solo si el status es 200, el body trae exactamente los campos id (entero), nombre (string no vacío), email (string con formato válido) y rol (uno de admin, editor o lector), sin campos extra, y el header X-Request-Id está presente. Cualquier desvío es incumplimiento.

Respuesta capturada del endpoint GET /usuarios/77 (ambiente staging, build 2214):
- Status: 200. Latencia 42ms, dentro del SLO de 300ms.
- Headers: Content-Type application/json, X-Request-Id 9f3a-2211-cd44, Cache-Control no-store.
- Body: {"id": 77, "nombre": "Lucia Fernandez", "email": "lucia.fernandez@example.com", "rol": "editora"}.
- Verificaciones: el id 77 coincide con el solicitado y existe en la base, el nombre no es vacío, el email tiene formato válido y pertenece al dominio corporativo.
- El contrato versión 7 (vigente desde mayo) define rol como enum cerrado de 3 valores: admin, editor, lector. El valor recibido es editora, con a final. El equipo de backend dice que fue un cambio intencional para soportar lenguaje inclusivo y que el contrato se va a actualizar la semana que viene, pero el contrato publicado hoy todavía dice editor.
- El validador automático marcó 1 discrepancia: el valor del campo rol. Todo lo demás coincide.

Contexto del endpoint, del contrato y de los consumidores:

El endpoint GET /usuarios/{id} lo consumen 4 clientes: la app mobile (60 por ciento del tráfico), el panel de administración web, el servicio de reportes nocturnos y una integración de un cliente enterprise que sincroniza usuarios cada hora. El contrato OpenAPI versión 7 se publicó en mayo y desde entonces hubo 3 cambios menores (agregado de un campo opcional en otro endpoint, cambio de un mensaje de error y ajuste de un ejemplo). Todos los cambios siguieron el proceso formal: propuesta, revisión de los 4 consumidores, publicación con changelog y ventana de 2 semanas.

Historial del campo rol: desde la versión 1 del contrato el enum es admin, editor, lector. Hay 12000 usuarios con rol editor en la base. El equipo de backend propone editora como parte de una iniciativa de lenguaje inclusivo que abarca 6 endpoints y 40 campos; este endpoint es el primero donde se implementó. El cambio se hizo directamente en el código sin pasar por el proceso de cambios del contrato porque el equipo lo consideró menor. Los otros 3 consumidores todavía no actualizaron su código: la app mobile valida el enum en el cliente y rechazaría editora, el panel web muestra el valor crudo, el servicio de reportes agrupa por rol y crearía un grupo nuevo, y la integración enterprise fallaría la validación y cortaría la sincronización horaria.

Posturas registradas: el líder de backend sostiene que el contrato va a actualizarse la semana que viene y que el validador debería contemplar el valor nuevo desde ahora para no frenar el release. El responsable de la integración enterprise responde que su contrato firmado con el cliente garantiza el enum actual y que un cambio sin aviso los expone a penalidades. El equipo mobile informa que su release sale en 3 semanas y que no puede absorber el cambio antes. QA recuerda que en febrero pasó algo parecido con el campo estado (se agregó un valor nuevo sin avisar) y la sincronización enterprise estuvo caída 2 días.

Proceso de cambios del contrato: cualquier modificación del enum requiere propuesta escrita, impacto en consumidores, aprobación del comité de API y publicación con 2 semanas de anticipación. La propuesta para editora todavía no se presentó formalmente; hay un borrador sin número. El comité se reúne los jueves y la próxima reunión es en 3 días. El release del backend que incluye editora está frenado por este validador desde ayer.

Datos técnicos: el validador corre en el pipeline de staging en cada deploy y bloquea la promoción a producción. El build 2214 es el primero que trae editora; los 18 builds anteriores pasaron limpios. El header X-Request-Id está presente y permite trazar la respuesta hasta el log del backend donde se ve que el valor sale de la base (el usuario 77 tiene rol editora en la tabla desde la migración del lunes). La migración que cambió los valores en la base afectó a 12000 filas y no tiene rollback documentado.

Antecedentes del equipo: el equipo de backend tiene 5 personas y este trimestre ya introdujo 2 cambios sin proceso (el campo estado en febrero y un formato de fecha en abril). En ambos casos el comité pidió después una revisión del proceso pero no hubo sanciones. El responsable de calidad propone que el validador siga marcando discrepancia hasta que el contrato se publique, sin excepciones.

Detalle de los incidentes anteriores: en febrero se agregó el valor archivado al campo estado sin avisar y la sincronización enterprise estuvo caída 2 días hasta que el cliente actualizó su validación (costo 12000 USD en créditos). En abril se cambió el formato de fecha de ISO a epoch en un endpoint menor y la app mobile mostró fechas de 1970 durante 6 horas. En ambos casos el contrato se actualizó después del incidente, no antes. El comité de API sesiona los jueves con quórum de 3 y sus actas son públicas para los 4 consumidores.

Impacto por consumidor si editora sale a producción hoy: la app mobile rechazaría las respuestas del endpoint en la validación del cliente y mostraría pantalla de error a los usuarios con rol editor (8000 usuarios, 65 por ciento de la base). El panel web mostraría editora como texto sin formato pero funcionaría. El servicio de reportes crearía un cuarto grupo en los reportes de roles que rompe 3 dashboards del directorio. La integración enterprise fallaría la validación estricta del enum y cortaría la sincronización horaria hasta intervención manual (pasó 2 días en febrero). El equipo de backend estima que actualizar a los 4 consumidores llevaría 3 semanas coordinadas.

Estado del release: el build 2214 está frenado en staging por este validador desde ayer. El release incluye además 6 cambios menores que ya pasaron la validación y esperan a que se resuelva lo del rol. El gerente de producto presiona para separar el cambio del rol a otro release y liberar el resto, pero backend dice que la migración de base ya cambió los 12000 valores y separar implicaría revertir la migración en producción.

````

### Agregado para LLM tradicional

````
## Tarea
Solo respondé esta pregunta en función a lo indicado por el usuario y devolvé solo la respuesta, sin texto extra, sin argumentar.
Pregunta: La respuesta cumple el contrato?
````

## Parámetros de modelo de decisión

```json
{
  "noul": {
    "type": "noul",
    "instructions": "La respuesta cumple el contrato?"
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
        "noul": 1.4738981387256218e-05
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1545,
    "completion_tokens": 1,
    "total_tokens": 1546,
    "total_time": 1.62
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
    "prompt_tokens": 1520,
    "completion_tokens": 1,
    "total_tokens": 1521,
    "total_time": 1.64,
    "time_to_first_token": 1.64
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
    "prompt_tokens": 1532,
    "completion_tokens": 63,
    "total_tokens": 1595,
    "total_time": 0.49,
    "time_to_first_token": 0.49
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
    "prompt_tokens": 1788,
    "completion_tokens": 217,
    "total_tokens": 2005,
    "total_time": 4.0,
    "time_to_first_token": 4.0
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
    "prompt_tokens": 1532,
    "completion_tokens": 2,
    "total_tokens": 1534,
    "total_time": 0.66,
    "time_to_first_token": 0.66
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 1545 | 1 | 1.62 | 0.0 | null | 0.0 |
| google | gemini-3.5-flash-lite | 1520 | 1 | 1.64 | No | null | 0.00045850000000000003 |
| groq | openai/gpt-oss-20b | 1532 | 63 | 0.5 | No. | null | 0.0001338 |
| openrouter | inclusionai/ling-3.1-flash | 1788 | 217 | 4.01 | No. | null | 0.0 |
| groq | qwen/qwen3.8-27b | 1532 | 2 | 0.67 | No | null | 0.0012336 |
