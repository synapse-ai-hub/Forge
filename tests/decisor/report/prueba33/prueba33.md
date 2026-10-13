# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:28:38

## Prompt exacto del modelo de decisión

````
Sos el responsable de seguridad que elige el método de autenticación. Contexto:

Una billetera digital con 500000 usuarios sufre takeover de cuentas: atacantes que consiguen la contraseña entran sin fricción porque el segundo factor por SMS se intercepta con SIM swapping, con 300 casos el último mes y pérdida promedio de 400 USD por caso. El 70 por ciento de los usuarios usa Android de gama media y el 25 por ciento cambia de teléfono cada año. Soporte recibe 2000 reclamos mensuales por fricción en el login actual. La regulación exige autenticación reforzada para transferencias mayores a 100 USD pero permite que el usuario elija el método. El equipo de fraude estima que el 80 por ciento de los takeovers usan SIM swapping y el resto phishing de SMS.

Login actual: email más contraseña más SMS, 4 pasos con 45 segundos promedio. El 15 por ciento de los logins falla por SMS que no llega y el usuario reintenta; el 5 por ciento abandona. Los teléfonos de gama media del parque tienen sensor de huella en el 60 por ciento de los casos. Cambiar de teléfono hoy obliga a ir a una sucursal con DNI, lo que genera 300 visitas mensuales. El costo del SMS es 0.02 USD por mensaje con 2 millones de mensajes al mes.   Apps competidoras usan TOTP y reportan adopción del 30 por ciento con caída de takeovers del 70 por ciento; las que usan passkeys reportan adopción del 12 por ciento en el primer año. El directorio quiere resultados en 6 meses sin aumentar el equipo de soporte.

Ampliación del caso con datos de fraude, usuarios y operación:

Fraude en detalle: 300 takeovers el último mes con pérdida promedio de 400 USD por caso (120000 USD mensuales). El vector es SIM swapping en el 80 por ciento de los casos (el atacante transfiere el número a un chip propio y recibe el SMS) y phishing con reenvío del código en el 20 por ciento. El tiempo medio entre el takeover y el vaciamiento es 11 minutos. El equipo de fraude recupera el 30 por ciento de los fondos si el reclamo llega en la primera hora y 0 por ciento después. El seguro cubre hasta 50000 USD mensuales y este mes se superó por 70000 USD. La unidad de fraude tiene 3 personas y procesa 15 casos por día con backlog de 5 días.

Usuarios y dispositivos: 500000 usuarios, 70 por ciento Android de gama media (versiones 10 a 13), 25 por ciento iOS y 5 por ciento otros. El 25 por ciento cambia de teléfono cada año (pérdida de enrolamientos atados al dispositivo). El 40 por ciento tiene más de 50 años y el equipo de UX midió que el 60 por ciento de ese segmento no completa un enrolamiento de más de 3 pasos. El 15 por ciento comparte el teléfono con un familiar. Soporte recibe 2000 reclamos mensuales por fricción en el login actual (códigos que no llegan, demoras de hasta 5 minutos en el SMS, números cambiados). Cada reclamo cuesta 3 USD en tiempo de soporte.

SMS actual: cuesta 2 millones de mensajes al mes a 0.02 USD (40000 USD mensuales). La entrega falla en el 8 por ciento de los casos (operadores del interior, portabilidad reciente, roaming). El SIM swapping creció 200 por ciento en un año según los datos del equipo de fraude. El proveedor de SMS ofrece firma digital del mensaje por 0.005 USD extra pero no evita el swapping (el atacante recibe el SMS firmado igual).

TOTP: las competidoras que lo usan reportan adopción del 30 por ciento (los usuarios tienen que instalar una app autenticadora) y caída de takeovers del 70 por ciento sobre los enrolados. El enrolamiento tarda 5 minutos con QR y el 50 por ciento lo abandona a mitad. El recupero ante cambio de teléfono requiere proceso manual con DNI (10 minutos por caso en soporte). Costo de implementación estimado: 2 meses de 2 desarrolladores más 1 mes de UX. No requiere hardware ni SMS.

Passkeys: las competidoras reportan adopción del 12 por ciento en el primer año (requiere Android 9+ o iOS 16+, deja afuera al 20 por ciento de la base con teléfonos viejos). Elimina el phishing y el swapping por diseño (la clave no sale del dispositivo). El recupero ante cambio de teléfono depende del ecosistema (Google/Apple) y el 30 por ciento de los usuarios pierde el acceso al cambiar de ecosistema. Costo de implementación: 3 meses de 3 desarrolladores. El directorio la ve como la solución de largo plazo pero pide resultados en 6 meses.

Restricciones: el directorio quiere resultados en 6 meses sin aumentar el equipo de soporte (8 personas). El presupuesto del proyecto es 100000 USD. La regulación local exige segundo factor para transferencias sobre 500 USD pero no especifica tecnología. El área legal advierte que cualquier cambio debe mantener el SMS como alternativa por 1 año para usuarios que no puedan migrar (regla de accesibilidad interna).

Incidentes y presión: el mes pasado un takeover de 12000 USD llegó a la prensa y el regulador pidió un plan de mejora con plazo de 90 días. El plan debe incluir metas medibles de reducción de fraude. El equipo de fraude propone enrolamiento obligatorio de TOTP para cuentas con más de 1000 USD de saldo (20 por ciento de los usuarios, 60 por ciento del fraude). El equipo de UX advierte que lo obligatorio genera abandono: en la encuesta, el 35 por ciento dice que dejaría la app si el login se complica. El CEO pidió una propuesta que baje el fraude sin frenar el crecimiento (la app suma 20000 usuarios por mes).

Plan de migración por etapas: el equipo propone enrolamiento voluntario con incentivos (límite de transferencia más alto para enrolados) durante 3 meses, obligatorio para saldos altos desde el mes 4, y SMS solo como alternativa para el 20 por ciento con teléfonos viejos. La meta es 30 por ciento de adopción en 6 meses (igual que las competidoras con TOTP) y caída del fraude del 50 por ciento en ese segmento. El costo del plan (desarrollo más comunicación más soporte para enrolamiento) entra en los 100000 USD de presupuesto. El regulador aceptó metas por segmento siempre que el total baje 40 por ciento en 90 días. El equipo de soporte calcula 500 casos de recupero por cambio de teléfono por mes (10 minutos cada uno, 83 horas mensuales, absorbibles sin contratar si se reparten entre los 8). La decisión pendiente es qué tecnología se enrolará en esas etapas.

Comparación final de tecnologías: SMS (costo 40000 USD mensuales, entrega falla 8 por ciento, vulnerable a swapping que creció 200 por ciento, fricción de 2000 reclamos mensuales, pero funciona en el 100 por ciento de los teléfonos sin enrolamiento), TOTP (costo de desarrollo 2 meses, adopción 30 por ciento en competidoras, baja takeovers 70 por ciento en enrolados, enrolamiento de 5 minutos con 50 por ciento de abandono, recupero manual de 10 minutos por cambio de teléfono, no requiere hardware), passkeys (elimina phishing y swapping por diseño, adopción 12 por ciento en el primer año en competidoras, deja afuera al 20 por ciento con teléfonos viejos, 30 por ciento pierde acceso al cambiar de ecosistema, desarrollo 3 meses). El directorio quiere resultados en 6 meses sin aumentar soporte: la tecnología elegida debe enrolar al 30 por ciento en ese plazo con el equipo actual de 8. El regulador mide el total de fraude en 90 días, no por segmento: si el segmento enrolado baja pero el resto sube, el plan fracasa. El equipo de fraude dice que el 60 por ciento del fraude está en el 20 por ciento de cuentas con más saldo (el segmento que sería obligatorio desde el mes 4).

Decisión del responsable: el responsable de seguridad debe elegir 1 tecnología para el plan de 6 meses con 100000 USD de presupuesto, 8 personas de soporte sin aumento, meta del regulador (40 por ciento menos fraude total en 90 días) y meta del directorio (30 por ciento de adopción en 6 meses). El SMS queda como alternativa por 1 año por accesibilidad (decisión de legal, no se discute). La tecnología elegida se enrolará en las etapas voluntaria (meses 1 a 3) y obligatoria para saldos altos (mes 4). El plan se presenta al regulador en 10 días y al directorio en 15. La recomendación debe decir qué tecnología y por qué cumple las 4 restricciones (presupuesto, soporte, regulador, directorio) mejor que las otras 2.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- sms: seguir con SMS y agregar preguntas de seguridad como refuerzo
- totp: app autenticadora con códigos de un solo uso y respaldos impresos
- passkeys: claves biométricas del dispositivo con PIN como alternativa
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí el método que mejor equilibra seguridad y fricción.",
    "criteria": {
      "sms": "seguir con SMS y agregar preguntas de seguridad como refuerzo",
      "totp": "app autenticadora con códigos de un solo uso y respaldos impresos",
      "passkeys": "claves biométricas del dispositivo con PIN como alternativa"
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
        "choice": "totp",
        "confidence": 0.9943074236598368,
        "probabilities": {
          "sms": 0.0006243483495015371,
          "totp": 0.9962049491065579,
          "passkeys": 0.0031707025439405693
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2200,
    "completion_tokens": 1,
    "total_tokens": 2201,
    "total_time": 5.91
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "totp",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2160,
    "completion_tokens": 2,
    "total_tokens": 2162,
    "total_time": 0.8,
    "time_to_first_token": 0.8
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "totp",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2093,
    "completion_tokens": 230,
    "total_tokens": 2323,
    "total_time": 0.68,
    "time_to_first_token": 0.68
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "totp",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2539,
    "completion_tokens": 186,
    "total_tokens": 2725,
    "total_time": 4.33,
    "time_to_first_token": 4.33
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1207. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}",
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
| openrouter | inception/mercury-decide:free | 2200 | 1 | 5.91 | totp | 0.9943074236598368 | 0.0 |
| google | gemini-3.5-flash-lite | 2160 | 2 | 0.81 | totp | null | 0.000653 |
| groq | openai/gpt-oss-20b | 2093 | 230 | 0.69 | totp | null | 0.000225975 |
| openrouter | inclusionai/ling-3.1-flash | 2539 | 186 | 4.35 | totp | null | 0.0 |
| groq | qwen/qwen3.8-27b | 0 | 0 | 0.12 | "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1207. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}" | null | 0.0 |
