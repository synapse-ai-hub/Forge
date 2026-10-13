# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 01:39:33

## Prompt exacto del modelo de decisión

````
Sos el filtro de CV para un puesto de desarrollador backend senior con Python y Postgres. Pasa a entrevista técnica solo si cumple todo: al menos 5 años de experiencia con Python en producción, experiencia comprobable con Postgres (replicación, índices o tuning, no solo usarlo como ORM), haber trabajado con sistemas de alta concurrencia o colas de mensajes, y disponibilidad para zona horaria GMT-3 con solapamiento de 6 horas. Inglés técnico para leer documentación. Si falta un requisito, no pasa.

CV de Carolina Méndez, expediente completo:
- Experiencia: 7 años como desarrolladora Python. 2022 a la fecha: senior en PagosAndinos (fintech, 180 empleados), equipo de autorizaciones con FastAPI, Celery y Redis procesando 2 millones de transacciones diarias con picos de 800 por segundo. 2019-2022: semi-senior en LogiSoft con Django y Postgres. Referencias: su ex-líder técnico deja teléfono y autoriza contacto.
- Postgres (sección con métricas y links): administró réplica primaria-secundaria con Patroni y failover probado 2 veces en producción, diseñó el particionado por rango de la tabla de movimientos (900 millones de filas, 40 particiones mensuales), y tuning documentado que bajó el p95 de la consulta crítica de 800ms a 90ms (EXPLAIN antes y después en el portfolio). El portfolio incluye scripts de migración, análisis de bloat y tuning de autovacuum.
- Concurrencia y colas: workers asincrónicos con Celery (120 workers), idempotencia con claves de negocio, patrón outbox para exactly-once en pagos, y manejo de DLQ con reintento y alerta. Describe un incidente donde una condición de carrera duplicó acreditaciones y cómo lo corrigió con locks pesimistas.
- Código: portfolio con 3 proyectos, tests con 85 por ciento de cobertura, y contribuciones a 2 librerías open source de Postgres.
- Disponibilidad: vive en Medellín (GMT-5), propone jornada de 7:00 a 16:00 hora local, lo que da 8 horas de solapamiento con GMT-3 (de 9:00 a 17:00 argentinas). Acepta viajar una semana por trimestre.
- Inglés: certificación B2 de 2024, lee RFCs y documentación sin problema, escribe design docs en inglés (adjunta uno). Habla intermedio: se defiende en dailies pero pide apoyo para presentaciones.
- Pretensión salarial: dentro de la banda publicada para el puesto.

Ampliación del expediente con verificaciones, referencias y contexto del puesto:

Verificación de experiencia: los 7 años están respaldados por certificados laborales de PagosAndinos (2022 a la fecha, senior) y LogiSoft (2019-2022, semi-senior). Antes de 2019 trabajó 1 año como trainee en una software factory (no cuenta como producción según el criterio del equipo). El ex-líder técnico de PagosAndinos deja teléfono y autoriza contacto; en la llamada de verificación (realizada ayer) confirmó el rol, el equipo de autorizaciones y los 2 millones de transacciones diarias. Recursos humanos de LogiSoft confirmó fechas y puesto por email. No hay gaps sin explicar en el historial.

Detalle de Postgres: administró réplica primaria-secundaria con Patroni con 2 failovers probados en producción (uno real por caída de disco en 2023, uno simulado en game day de 2024). Diseñó el particionado por rango de la tabla de movimientos (900 millones de filas, 40 particiones mensuales) con script de creación automática de particiones y retención de 36 meses. El tuning documentado bajó el p95 de la consulta crítica de 800ms a 90ms con EXPLAIN antes y después en el portfolio (agregó índice compuesto y reescribió una subconsulta correlacionada). El portfolio incluye scripts de migración con rollback, análisis de bloat trimestral y tuning de autovacuum para tablas de alta escritura. En la entrevista de screening resolvió correctamente 2 preguntas de índices (compuesto vs simple, cuándo un índice no se usa) y 1 de replicación (lag y cómo medirlo).

Concurrencia y colas en detalle: 120 workers de Celery con Redis como broker, idempotencia con claves de negocio en pagos (evita doble acreditación ante reintentos), patrón outbox para exactly-once entre la base y la cola, y DLQ con reintento exponencial y alerta a PagerDuty. Describe un incidente de 2023 donde una condición de carrera duplicó acreditaciones por 45000 USD: lo detectó por conciliación, lo corrigió con locks pesimistas en la fila de cuenta y agregó test de concurrencia. El incidente está documentado en su portfolio con timeline. Picos de 800 transacciones por segundo sostenidos durante 3 horas en Hot Sale sin degradación.

Código y open source: portfolio con 3 proyectos (un rate limiter con Redis, un audit logger para Django y un particionador automático para Postgres), tests con 85 por ciento de cobertura verificada en CI, y contribuciones a 2 librerías open source de Postgres (un fix de documentación y un fix menor de un tipo de dato). El equipo técnico revisó el portfolio y lo calificó como sólido pero no excepcional.

Disponibilidad y zona horaria: vive en Medellín (GMT-5) y propone jornada de 7:00 a 16:00 hora local, lo que da 8 horas de solapamiento con GMT-3 (de 9:00 a 17:00 argentinas), por encima de las 6 exigidas. Acepta viajar una semana por trimestre a Buenos Aires. El equipo actual está en GMT-3 con dailies a las 10:00 argentinas (8:00 de ella, dentro de su jornada). No pide excepciones de horario.

Inglés: certificación B2 de 2024, lee RFCs y documentación sin problema, escribe design docs en inglés (adjunta uno de 6 páginas sobre el outbox, bien escrito según el revisor). Habla intermedio: se defiende en dailies pero pide apoyo para presentaciones. El puesto exige inglés técnico para leer documentación, no para presentar. El equipo tiene 2 reuniones mensuales en inglés con la casa matriz donde participaría como oyente.

Contexto del puesto: backend senior para el equipo de pagos con 8 personas, stack FastAPI, Celery, Redis y Postgres con Patroni (idéntico al de la candidata). El puesto lleva 2 meses abierto, hubo 40 postulantes y solo 3 llegaron a entrevista técnica. La banda salarial publicada es 4000-5000 USD y la candidata pide 4400 USD. El manager valora experiencia en pagos y Postgres administrado (no solo ORM) porque el equipo tuvo 2 incidentes por tuning el año pasado. La última contratación del equipo tardó 4 meses y renunció a los 6 meses por falta de experiencia en concurrencia real; desde entonces el filtro exige concurrencia comprobable.

Referencias adicionales: un compañero de PagosAndinos dice que es la referente de Postgres del equipo y que la consultan de otros equipos. Su manager actual dice que es sólida técnicamente pero que a veces demora en estimar (sus estimaciones se pasan 30 por ciento en promedio). Ninguna referencia menciona problemas de trabajo en equipo ni de comunicación.

Proceso de selección y estado del filtro: el filtro de CV lo aplica el equipo de recruiting con los 4 requisitos como checklist binario (experiencia Python, Postgres comprobable, concurrencia o colas, solapamiento horario) más inglés técnico. De 40 postulantes, 25 fueron descartados por menos de 5 años, 8 por Postgres solo como ORM sin administración, 3 por zona horaria incompatible y 1 por inglés insuficiente. Quedan 3 candidatas en revisión, incluida Carolina. La entrevista técnica dura 90 minutos con 2 ingenieros del equipo y cubre Postgres (tuning en vivo), concurrencia (diseño con colas) y código (pair programming). El SLA del filtro es 3 días hábiles y este expediente lleva 1 día. El manager pidió priorizar perfiles con experiencia en pagos porque el dominio (autorizaciones, conciliación, idempotencia) tarda 3 meses en aprenderse y Carolina lo trae. Las otras 2 candidatas en revisión tienen 6 y 9 años de Python pero sin experiencia en pagos ni Postgres administrado (una usa solo ORM, la otra trabajó con MySQL). El comité de hiring sesiona los viernes y necesita los 3 expedientes completos antes del jueves a las 18:00.

Screening técnico previo: Carolina ya pasó un screening de 30 minutos con un ingeniero del equipo donde resolvió 2 preguntas de índices y 1 de replicación sin errores. El ingeniero la calificó como fuerte en Postgres y recomendó pasarla a entrevista técnica. La única duda registrada es si su experiencia en presentaciones en inglés alcanza para las 2 reuniones mensuales con la casa matriz, donde participaría como oyente y solo respondería preguntas simples. El puesto no exige presentar en inglés y el manager dijo que con B2 y design docs escritos alcanza.

Checklist del filtro aplicado: 5 o más años de Python en producción (sí, 7 con certificados), Postgres comprobable con replicación, índices o tuning (sí, Patroni con 2 failovers, particionado de 900 millones de filas, tuning de 800ms a 90ms con EXPLAIN), alta concurrencia o colas (sí, 120 workers Celery, outbox, DLQ, incidente de condición de carrera resuelto), solapamiento de 6 horas con GMT-3 (sí, 8 horas con jornada de 7:00 a 16:00 hora de Medellín), inglés técnico para documentación (sí, B2 2024, lee RFCs, escribe design docs). Los 5 puntos están tildados por recruiting con evidencia adjunta por punto. De 40 postulantes es la única con los 5 puntos tildados sin salvedades; las otras 2 en revisión tienen salvedades en Postgres (solo ORM y MySQL).

Decisión del comité: el comité sesiona el viernes y necesita los 3 expedientes antes del jueves a las 18:00. El manager ya dijo que si Carolina pasa el filtro la cita a entrevista técnica el lunes (los 2 ingenieros tienen agenda reservada). La entrevista técnica define si entra; el filtro solo decide si llega a esa instancia. Recruiting pide que la decisión del filtro quede con el checklist firmado para auditoría del proceso (el proceso se audita trimestralmente y exige evidencia por cada punto).

Cierre del expediente: el expediente lleva 1 día contra un SLA de 3. Recruiting recomienda el pase con los 5 puntos tildados y evidencia adjunta. La entrevista técnica del lunes (90 minutos, 2 ingenieros, Postgres en vivo, concurrencia y pair programming) es la que define la contratación. Si el filtro la frena, el puesto sigue con 2 candidatas con salvedades en Postgres y el manager ya dijo que ninguna de las 2 lo convence para el equipo de pagos (una solo ORM, la otra MySQL). El costo de una mala contratación en este equipo ya se pagó una vez (4 meses de búsqueda más 6 meses de sueldo para alguien sin concurrencia real que renunció).

````

### Agregado para LLM tradicional

````
## Tarea
Solo respondé esta pregunta en función a lo indicado por el usuario y devolvé solo la respuesta, sin texto extra, sin argumentar.
Pregunta: El CV pasa a entrevista técnica?
````

## Parámetros de modelo de decisión

```json
{
  "noul": {
    "type": "noul",
    "instructions": "El CV pasa a entrevista técnica?"
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
        "noul": 0.9998415637257391
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2586,
    "completion_tokens": 1,
    "total_tokens": 2587,
    "total_time": 0.82
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
    "prompt_tokens": 2603,
    "completion_tokens": 1,
    "total_tokens": 2604,
    "total_time": 1.71,
    "time_to_first_token": 1.71
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí, pasa a entrevista técnica.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2584,
    "completion_tokens": 72,
    "total_tokens": 2656,
    "total_time": 0.49,
    "time_to_first_token": 0.49
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'inclusionai/ling-3.1-flash is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'provider_name': 'Novita', 'is_byok': False, 'limit_source': 'upstream_provider_shared_pool', 'remedy_hint': 'Retry shortly, add your own provider key (https://openrouter.ai/settings/integrations), or route to another provider with provider routing: https://openrouter.ai/docs/features/provider-routing'}}, 'user_id': 'user_3IHIEaL9108If8k2gSzCi1zx2e3'}",
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

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2680,
    "completion_tokens": 2,
    "total_tokens": 2682,
    "total_time": 0.51,
    "time_to_first_token": 0.51
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 2586 | 1 | 0.83 | 1.0 | null | 0.0 |
| google | gemini-3.5-flash-lite | 2603 | 1 | 1.72 | Sí | null | 0.0007834 |
| groq | openai/gpt-oss-20b | 2584 | 72 | 0.49 | Sí, pasa a entrevista técnica. | null | 0.00021539999999999998 |
| openrouter | inclusionai/ling-3.1-flash | 0 | 0 | 2.47 | "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'inclusionai/ling-3.1-flash is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'provider_name': 'Novita', 'is_byok': False, 'limit_source': 'upstream_provider_shared_pool', 'remedy_hint': 'Retry shortly, add your own provider key (https://openrouter.ai/settings/integrations), or route to another provider with provider routing: https://openrouter.ai/docs/features/provider-routing'}}, 'user_id': 'user_3IHIEaL9108If8k2gSzCi1zx2e3'}" | null | 0.0 |
| groq | qwen/qwen3.8-27b | 2680 | 2 | 0.52 | Sí | null | 0.0021520000000000003 |
