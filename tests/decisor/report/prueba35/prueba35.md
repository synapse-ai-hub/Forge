# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:33:59

## Prompt exacto del modelo de decisión

````
Sos el SRE que elige la estrategia de despliegue. Contexto:

Un servicio de pagos procesa 500 transacciones por segundo con SLO de 99.95 por ciento de disponibilidad mensual, lo que deja 21 minutos de error budget al mes. El deploy actual es big bang con 4 minutos de downtime y ya consumió 18 minutos del budget este mes. El equipo hace 3 deploys por semana y cada rollback tarda 25 minutos porque hay que restaurar la base. La base tiene migraciones que agregan columnas y backfill de datos históricos que tarda 40 minutos. No se puede parar el servicio en horario comercial y el próximo deploy incluye un cambio en el cálculo de comisiones que debe poder revertirse en minutos si falla.

Historial: en los últimos 2 meses hubo 4 deploys con incidentes (2 por migraciones, 1 por un flag mal configurado, 1 por saturación de conexiones). El rollback por restore de base se usó 2 veces y en una tardó 40 minutos por el tamaño del backup. El equipo es de 8 personas con guardia rotativa y el on-call tarda 15 minutos en responder de noche.   La base es Postgres de 2 TB con réplica sincrónica; los backfills se corren a mano con scripts. Montar un segundo entorno completo costaría 12000 USD al mes y el presupuesto de infra está al límite. Los feature flags ya se usan para 2 funcionalidades chicas con una librería interna que nadie documentó.

Ampliación del caso con SLO, deploys e historia:

SLO y error budget: 99.95 por ciento mensual deja 21 minutos de budget. Este mes se consumieron 18 minutos (un deploy con 4 minutos de downtime, un incidente de 9 minutos por saturación de conexiones y un rollback de 5 minutos). Quedan 3 minutos hasta fin de mes (faltan 9 días). Si se supera el SLO, el contrato con los 2 clientes enterprise exige créditos por 30000 USD. El próximo deploy incluye el cambio en el cálculo de comisiones que debe poder revertirse en minutos si falla (es cambio regulatorio con fecha legal fija).

Deploys y rollbacks: 3 deploys por semana, big bang con 4 minutos de downtime cada uno (12 minutos semanales, 48 mensuales: más del doble del budget). Cada rollback tarda 25 minutos porque hay que restaurar la base desde backup (la última restauración tardó 40 minutos por el tamaño de 2 TB). En los últimos 2 meses hubo 4 deploys con incidentes: 2 por migraciones incompatibles, 1 por un flag mal configurado y 1 por saturación de conexiones. El rollback por restore se usó 2 veces y en una dejó 15 minutos de datos inconsistentes que hubo que conciliar a mano.

Base y migraciones: Postgres de 2 TB con réplica sincrónica. Las migraciones agregan columnas y hacen backfill de datos históricos que tarda 40 minutos con scripts a mano. No hay migraciones reversibles ni expand-contract: si una migración falla, la única salida es el restore. El DBA propuso migraciones online 3 veces y fue rechazado por falta de tiempo. El cambio de comisiones del próximo deploy agrega 2 columnas y backfillea 500 millones de filas (estimado 50 minutos).

Equipo y guardia: 8 personas con guardia rotativa, on-call que tarda 15 minutos en responder de noche. Los deploys se hacen de día por decisión del equipo (de noche nadie los mira) y cada deploy corta el servicio 4 minutos en horario comercial. Los clientes enterprise ya reclamaron 2 veces por deploys en horario comercial. No se puede parar el servicio en horario comercial según el contrato, pero se hace igual porque de noche no hay quién atienda un rollback.

Costos y flags: montar un segundo entorno completo (blue-green) cuesta 12000 USD al mes y el presupuesto de infra está al límite (ya se pasó 5 por ciento este trimestre). Los feature flags se usan para 2 funcionalidades chicas con una librería interna sin documentar que solo conocen 2 personas. El equipo nunca hizo un deploy con flags en el cálculo de comisiones ni en migraciones. La librería no soporta flags por porcentaje de tráfico, solo on-off global.
Opciones de despliegue: el equipo evalúa 3 estrategias (big bang con ventana nocturna, flags con base compatible hacia atrás, y blue-green con doble entorno) y pide una recomendación que proteja el error budget con el presupuesto y el equipo actuales.

Ventana nocturna y clientes: mover los deploys a las 3:00 reduce el impacto (10 transacciones por segundo vs 500) pero nadie del equipo quiere hacer guardia de deploy de noche sin pago extra. El on-call tarda 15 minutos en responder y un rollback de 25 minutos a las 3:00 deja el servicio degradado hasta las 3:40 sin nadie mirando los primeros 15. Los clientes enterprise aceptaron ventanas mensuales de 30 minutos con 15 días de aviso, pero el equipo hace 12 deploys por mes y solo puede avisar 1 ventana. El contrato permite 1 ventana mensual, no 12.

Números de cada estrategia: big bang nocturno mantiene los 4 minutos de downtime por deploy (48 minutos mensuales, más del doble del budget de 21) pero fuera de horario pico; no resuelve el rollback de 25 minutos ni las migraciones. Blue-green elimina el downtime pero cuesta 12000 USD mensuales (el presupuesto ya está 5 por ciento pasado) y exige duplicar la base de 2 TB con réplica (3 semanas de trabajo del DBA). Flags con base compatible hacia atrás permite revertir en minutos sin restore (protege el budget) pero exige reescribir las migraciones en formato expand-contract (2 semanas de trabajo) y documentar la librería interna que solo conocen 2 personas. El cambio de comisiones (regulatory, fecha legal fija, debe revertirse en minutos) no admite restore de 25 minutos: si falla, los 25 minutos de rollback superan el budget restante de 3 minutos y activan los créditos de 30000 USD. El equipo tiene 9 días hasta fin de mes y 1 deploy por hacer antes del cambio de comisiones.

Comparación final de estrategias: big bang con ventana nocturna (costo 0, downtime 48 minutos mensuales que supera el budget, rollback 25 minutos que no sirve para el cambio de comisiones, pero no requiere trabajo previo y el equipo lo sabe hacer), blue-green con doble entorno (downtime 0, rollback instantáneo por cambio de tráfico, pero 12000 USD mensuales sin presupuesto y 3 semanas del DBA que no hay antes del cambio de comisiones), flags con base compatible (reversión en minutos sin restore, protege los 3 minutos de budget restantes, costo 2 semanas de reescribir migraciones más documentar la librería, riesgo de que la librería sin documentar falle en el cambio más crítico del año). El DBA dice que las 2 semanas de expand-contract son viables antes del cambio de comisiones si se empieza ya. El dueño de la librería de flags (una de las 2 personas que la conocen) dice que soporta el caso de comisiones con un flag on-off global pero sin porcentaje de tráfico (todo o nada). La recomendación debe proteger los 3 minutos de budget con lo que el equipo puede hacer en 9 días.

Decisión del SRE: debe elegir 1 estrategia para el cambio de comisiones (fecha legal fija, reversión en minutos obligatoria, 3 minutos de budget restantes, 9 días de plazo) con 8 personas, guardia con 15 minutos de respuesta y presupuesto pasado 5 por ciento. La estrategia elegida se aplica al cambio de comisiones y define el estándar de deploys del trimestre (el equipo quiere dejar el big bang sea cual sea la decisión). El SRE presenta la recomendación mañana con el DBA (que defiende expand-contract), el dueño de la librería (que defiende flags) y el gerente de infra (que defiende no gastar los 12000 USD). Si el cambio de comisiones falla sin reversión en minutos, se activan los créditos de 30000 USD y se pierde el SLO del mes.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- bigbang: despliegue total con ventana de mantenimiento nocturna
- bluegreen: dos entornos completos con cambio de tráfico entre ellos
- flags: liberación gradual con interruptores y base compatible hacia atrás
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí la estrategia que mejor protege el error budget.",
    "criteria": {
      "bigbang": "despliegue total con ventana de mantenimiento nocturna",
      "bluegreen": "dos entornos completos con cambio de tráfico entre ellos",
      "flags": "liberación gradual con interruptores y base compatible hacia atrás"
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
        "choice": "flags",
        "confidence": 0.9949064957269546,
        "probabilities": {
          "bigbang": 0.0016978347576818125,
          "bluegreen": 0.0016978347576818125,
          "flags": 0.9966043304846363
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1982,
    "completion_tokens": 1,
    "total_tokens": 1983,
    "total_time": 1.53
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "flags",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1922,
    "completion_tokens": 1,
    "total_tokens": 1923,
    "total_time": 1.59,
    "time_to_first_token": 1.59
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "flags",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1922,
    "completion_tokens": 157,
    "total_tokens": 2079,
    "total_time": 1.11,
    "time_to_first_token": 1.11
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "flags",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2277,
    "completion_tokens": 624,
    "total_tokens": 2901,
    "total_time": 9.69,
    "time_to_first_token": 9.69
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1176. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}",
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
| openrouter | inception/mercury-decide:free | 1982 | 1 | 1.53 | flags | 0.9949064957269546 | 0.0 |
| google | gemini-3.5-flash-lite | 1922 | 1 | 1.59 | flags | null | 0.0005791 |
| groq | openai/gpt-oss-20b | 1922 | 157 | 1.12 | flags | null | 0.00019125000000000001 |
| openrouter | inclusionai/ling-3.1-flash | 2277 | 624 | 9.7 | flags | null | 0.0 |
| groq | qwen/qwen3.8-27b | 0 | 0 | 0.12 | "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1176. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}" | null | 0.0 |
