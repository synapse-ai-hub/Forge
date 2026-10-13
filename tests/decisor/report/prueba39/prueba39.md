# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:45:07

## Prompt exacto del modelo de decisión

````
Sos el ejecutivo de cuentas que recomienda el plan. Cliente:

Estudio jurídico con 22 abogados y 8 administrativos. Hoy usan el plan básico de 10 usuarios que les cuesta 199 USD mensuales y viven pidiendo ampliaciones temporales. Consumen 900 GB de almacenamiento (el básico incluye 500 GB y pagan excedentes caros), necesitan auditoría de accesos por una certificación ISO que están sacando, y 5 abogados trabajan desde Mac donde el cliente pesado del plan básico no funciona (solo web). El plan profesional sale 499 USD hasta 25 usuarios con 2 TB y auditoría incluida y cliente nativo para Mac. El plan enterprise sale 990 USD desde 25 usuarios con SSO y soporte dedicado, pero ellos no tienen SSO ni lo planean. Crecen 2 personas por año y el socio director odia pagar excedentes y parches. La certificación ISO la auditan en 4 meses y sin logs de acceso no la pasan.

Uso: trabajan con expedientes de 200 MB promedio, comparten carpetas con clientes externos (el básico no permite links con expiración) y usan la versión web en Mac con quejas semanales. Pagan 180 USD al mes en excedentes de almacenamiento y 120 USD en ampliaciones temporales: en total 499 USD, lo mismo que el profesional. El contrato del básico renueva en 2 meses con aumento del 15 por ciento anunciado. Deciden el socio director y la gerenta de administración; el área de sistemas es un externo part time que no quiere SSO porque no lo sabe mantener. Evaluaron a un competidor que sale 350 USD pero sin cliente Mac y con migración manual de 900 GB.

Números finos y contexto de la decisión:

Dotación real: 22 abogados (5 socios, 8 seniors, 9 juniors) y 8 administrativos. De los 22 abogados, 5 usan Mac como máquina principal y 3 más usan Mac personal para trabajar desde casa. El plan básico cubre 10 usuarios nominales pero lo usan 30 con ampliaciones temporales que se piden por ticket y tardan 48 horas en activarse. En los últimos 6 meses pidieron 14 ampliaciones. El costo real mensual es 199 del plan más 180 de excedentes de almacenamiento más 120 de ampliaciones: 499 USD, exactamente lo que sale el profesional.

Almacenamiento: 900 GB actuales con crecimiento de 40 GB por mes (expedientes escaneados a 200 MB promedio, 200 expedientes nuevos por mes). El básico incluye 500 GB y el excedente se cobra a 0.45 USD por GB (400 GB por 180 USD). El profesional incluye 2 TB, lo que da margen para 2 años y medio al ritmo actual. El enterprise incluye 5 TB. La migración de 900 GB la hace el proveedor sin costo en los planes profesional y enterprise (fin de semana, con corte de 4 horas); el competidor de 350 USD exige migración manual por el cliente.

Certificación ISO: la auditan en 4 meses y exige logs de acceso a documentos (quién vio qué y cuándo) con retención de 1 año. El básico no tiene auditoría; el profesional la incluye con reportes listos para auditoría; el enterprise agrega alertas en tiempo real. Sin logs no pasan la auditoría y pierden 2 clientes corporativos que exigen la certificación (representan el 30 por ciento de la facturación). La gerenta de administración ya avisó que si no se resuelve este mes, no llegan a tener 3 meses de logs antes de la auditoría.

Mac y cliente: los 5 abogados con Mac usan la versión web porque el cliente pesado del básico es solo Windows. La web no permite trabajo offline ni sincronización selectiva, y hay quejas semanales registradas (23 tickets en 6 meses). El profesional incluye cliente nativo para Mac con offline; el enterprise agrega despliegue masivo por MDM (no tienen MDM). El competidor evaluado tampoco tiene cliente Mac.

Enterprise y SSO: el enterprise exige SSO (Google Workspace o Entra ID) y ellos no tienen ninguno: usan cuentas locales. Implementar SSO les costaría 3000 USD de consultoría más el externo part time que dice no saber mantenerlo. No lo planean este año. El soporte dedicado del enterprise (teléfono 24/7) les serviría poco: su horario es 9 a 18 y el soporte estándar del profesional (email con respuesta en 4 horas) les alcanza según la gerenta.

Contrato y tiempos: el básico renueva en 2 meses con aumento del 15 por ciento (pasaría a 229 más excedentes). El profesional se puede contratar ya con migración el próximo fin de semana. Crecen 2 personas por año: en 2 años serían 34 usuarios y el profesional cubre hasta 25 (habría que pasar a enterprise o pagar ampliaciones). El socio director odia los parches y quiere una decisión para 3 años; la gerenta prefiere resolver ya el problema de la auditoría y rever en 2 años.

Competidor: 350 USD por 30 usuarios con 1 TB, sin cliente Mac, sin auditoría (la venden como módulo aparte por 150 USD), migración manual. El costo total comparable sería 500 USD con las mismas limitaciones de Mac y migración a pulso.

Links con expiración y trabajo externo: el estudio comparte 50 carpetas por mes con clientes externos (pericias, expedientes para peritos y documentación para juzgados). El básico no permite links con expiración: comparten con links permanentes y una vez por mes alguien tiene que revisar y revocar a mano (2 horas de la gerenta). El profesional incluye links con expiración y contraseña; el enterprise agrega marca de agua en documentos. En 2024 un link permanente quedó activo 8 meses después de terminado el caso y un ex-cliente descargó 3 expedientes (sin consecuencias legales, pero con apercibimiento interno).

Versión web en Mac: los 5 abogados con Mac usan la web con 23 tickets en 6 meses (lentitud con expedientes de más de 500 MB, sin vista previa de 12 formatos, sin sincronización selectiva). El cliente nativo del profesional resuelve los 3 puntos según la prueba que hizo uno de los socios con la trial de 14 días. El externo part time estima 2 días para desplegarlo en las 5 Mac.

Crecimiento y techo del profesional: con 2 personas por año, en 2 años serán 34 usuarios y el profesional cubre hasta 25. El proveedor confirmó que se pueden pagar 9 ampliaciones sueltas a 25 USD cada una (225 USD extra) o saltar a enterprise. El socio director quiere una decisión para 3 años sin parches; la gerenta propone resolver la auditoría ya y renegociar en 2 años cuando el techo apriete.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- basico: seguir en el plan básico pagando excedentes y ampliaciones temporales
- profesional: subir al plan profesional que cubre almacenamiento, auditoría y Mac
- enterprise: saltar al plan enterprise con SSO y soporte dedicado
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí el plan que mejor se ajusta al cliente.",
    "criteria": {
      "basico": "seguir en el plan básico pagando excedentes y ampliaciones temporales",
      "profesional": "subir al plan profesional que cubre almacenamiento, auditoría y Mac",
      "enterprise": "saltar al plan enterprise con SSO y soporte dedicado"
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
        "choice": "profesional",
        "confidence": 0.9996907325613552,
        "probabilities": {
          "basico": 7.483637099862073e-05,
          "profesional": 0.9997938217075703,
          "enterprise": 0.00013134192143113792
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1705,
    "completion_tokens": 1,
    "total_tokens": 1706,
    "total_time": 0.95
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "profesional",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1652,
    "completion_tokens": 3,
    "total_tokens": 1655,
    "total_time": 9.59,
    "time_to_first_token": 9.59
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "profesional",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1634,
    "completion_tokens": 373,
    "total_tokens": 2007,
    "total_time": 0.82,
    "time_to_first_token": 0.82
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "profesional",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1989,
    "completion_tokens": 1783,
    "total_tokens": 3772,
    "total_time": 21.77,
    "time_to_first_token": 21.77
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1390. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}",
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
| openrouter | inception/mercury-decide:free | 1705 | 1 | 0.96 | profesional | 0.9996907325613552 | 0.0 |
| google | gemini-3.5-flash-lite | 1652 | 3 | 9.59 | profesional | null | 0.0005031 |
| groq | openai/gpt-oss-20b | 1634 | 373 | 0.84 | profesional | null | 0.00023444999999999998 |
| openrouter | inclusionai/ling-3.1-flash | 1989 | 1783 | 21.78 | profesional | null | 0.0 |
| groq | qwen/qwen3.8-27b | 0 | 0 | 0.12 | "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1390. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}" | null | 0.0 |
