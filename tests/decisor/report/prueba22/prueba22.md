# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:00:31

## Prompt exacto del modelo de decisión

````
Sos el analista del SOC. Un incidente se declara intrusión confirmada solo si hay evidencia de acceso no autorizado exitoso (no solo intentos), el origen es externo a la red corporativa, se observa movimiento lateral o exfiltración, y la cuenta comprometida no pertenece a un test de pentesting autorizado. Con solo intentos fallidos, es escaneo y no intrusión.

Cronología de eventos de la madrugada en el servidor de archivos FS-02:
- 02:14 a 02:47: 3400 intentos de login SSH fallidos desde una IP de un datacenter de otro país, todos rechazados por fail2ban al minuto 3. Después silencio total desde esa IP. Ningún acceso exitoso por esa vía.
- 03:05: login exitoso a la VPN corporativa con las credenciales del usuario j.perez (empleado del área contable, sin privilegios especiales) desde una IP residencial del mismo país que no pertenece a ningún empleado ni sede. Autenticación solo con contraseña (j.perez no tenía 2FA activado). El usuario declaró por escrito estar dormido y no reconocer la sesión; su laptop estaba apagada en su casa.
- 03:09: desde esa sesión VPN se accede a FS-02 con las credenciales de j.perez (acceso válido según permisos, el usuario tiene lectura sobre balances).
- 03:09 a 03:31: copia de 4.2 GB de las carpetas de balances 2024 y 2025 hacia una máquina externa (IP del mismo datacenter extranjero de los intentos SSH). Registro completo de la transferencia en el firewall, con el 100 por ciento de los bytes confirmados.
- 03:33: la sesión VPN se cierra. A las 09:00 j.perez cambia su contraseña y activa 2FA.
- Pentesting: el único test autorizado del trimestre fue en abril sobre la DMZ, cerrado con informe entregado el 28 de abril. La empresa de pentesting confirmó por escrito que no tuvo actividad en junio. Nadie interno autorizó nada.
- Alcance: no se observa instalación de persistencia ni acceso a otros servidores, pero la exfiltración está confirmada por los logs del firewall y del servidor.

Ampliación del incidente con telemetría completa y contexto del SOC:

Cronología detallada de la madrugada (hora local del servidor): 02:14 comienzan 3400 intentos de login SSH fallidos desde una IP de un datacenter de otro país, distribuidos en 33 minutos (100 por minuto). A los 3 minutos fail2ban bloquea la IP por 1 hora. 02:47 cesan los intentos y hay silencio total de esa IP. 03:05 un login exitoso como usuario backup-svc desde una IP residencial del mismo país extranjero (IP distinta a la bloqueada). El usuario backup-svc existe y tiene clave válida pero no tiene 2FA (es cuenta de servicio para backups nocturnos). 03:06 a 03:40: 12 comandos ejecutados (listado de directorios, compresión de 3 carpetas con datos de clientes por 2.4 GB, y 1 conexión saliente al puerto 443 de un servidor externo). 03:41 el firewall registra 2.4 GB salientes hacia ese servidor externo en 35 minutos. 03:42 cierra la sesión. 04:00 el backup nocturno legítimo falla porque la cuenta backup-svc estaba bloqueada por sesión duplicada.

Cuenta backup-svc: cuenta de servicio creada en 2022 para el backup nocturno con acceso de lectura a los 4 fileshares del servidor. Su clave se rota cada 90 días (última rotación hace 40 días). No tiene 2FA por limitación del script de backup. El script corre a las 4:00 desde el servidor de backup interno (IP de la red corporativa). El login de las 03:05 vino de una IP externa residencial, no del servidor de backup. El dueño del script (infraestructura) confirma que nadie lanzó un backup manual esa noche. La política del SOC exige 2FA en todas las cuentas con acceso externo; esta cuenta es una excepción documentada desde 2023 con revisión pendiente.

Origen externo: las 2 IPs pertenecen a otro país (un datacenter y una residencial). La red corporativa no tiene presencia en ese país. El GeoIP del firewall las marca como no vistas antes en 12 meses de logs. La IP del datacenter está en 2 listas públicas de reputación por escaneo SSH. La IP residencial no está en listas pero el proveedor es un ISP residencial común. No hay VPN corporativa que origine en ese país ni empleados viajando allí (verificado con RRHH y con los logs de la VPN).

Movimiento lateral y exfiltración: no se observa instalación de persistencia (sin claves SSH nuevas, sin tareas programadas, sin usuarios creados) ni acceso a otros servidores (los logs de los 3 servidores vecinos no muestran conexiones desde FS-02 esa noche). Pero la exfiltración está confirmada: 2.4 GB salientes a un servidor externo con los 3 archivos comprimidos que coinciden en tamaño con las 3 carpetas de datos de clientes. El DLP no cubre este servidor (está en la lista de pendientes desde enero). Los datos exfiltrados incluyen nombres, emails y saldos de 80000 clientes.

Pentesting y actividad autorizada: el último pentest sobre la DMZ fue en abril (informe entregado el 28 de abril, sin hallazgos críticos). La empresa de pentesting confirmó por escrito que no tuvo actividad en junio y que sus IPs autorizadas son otras 2 (registradas en el SOC). Nadie interno autorizó nada: el gerente de infraestructura, el responsable de backups y el CISO confirmaron que no había actividad programada. El test de vulnerabilidades automatizado corre los domingos a las 22:00 desde el escáner interno (otra IP, otro horario, sin logins con cuentas de servicio).

Intentos fallidos vs acceso exitoso: los 3400 intentos iniciales fueron todos rechazados (fail2ban al minuto 3) y por sí solos serían escaneo. Pero a las 03:05 hubo un login exitoso con credenciales válidas desde otra IP externa, seguido de comandos y exfiltración. El SOC evalúa si los intentos fueron distracción o un ataque distinto del mismo actor. Las credenciales de backup-svc no estaban en ningún leak conocido (verificado en 2 servicios de monitoreo) y la clave tiene 20 caracteres aleatorios: el SOC investiga si se obtuvo por otro medio (posible compromiso previo del servidor de backup, en revisión).

Estado del SOC y acciones tomadas: el incidente lo detectó el analista de turno a las 06:30 por la alerta de transferencia anómala (regla nueva de mayo). Se aisló FS-02 de la red a las 07:00, se preservaron los logs y se abrió el ticket SOC-2026-1847 con severidad crítica. Se notificó al CISO a las 07:30 y a legales a las 08:00 por los datos de clientes. El servidor de backup está en revisión forense (resultados en 48 horas). La cuenta backup-svc fue deshabilitada a las 07:15 y los backups corren con una cuenta nueva con 2FA desde hoy. El SOC pide declarar el incidente según la evidencia reunida para activar el protocolo de notificación a clientes (plazo legal 72 horas).

Checklist del SOC aplicado: acceso no autorizado exitoso (sí, login de las 03:05 con la cuenta backup-svc desde IP externa, seguido de 12 comandos y exfiltración de 2.4 GB), origen externo a la red corporativa (sí, 2 IPs de otro país sin presencia corporativa, sin VPN ni empleados viajando), movimiento lateral o exfiltración (sí, exfiltración confirmada de 2.4 GB con datos de 80000 clientes; sin movimiento lateral a otros servidores), cuenta no perteneciente a pentesting autorizado (sí, el pentest fue en abril sobre la DMZ con otras IPs, la empresa confirmó por escrito que no tuvo actividad en junio, nadie interno autorizó nada). Los 4 puntos están documentados con evidencia (logs de SSH, firewall, DLP pendiente, confirmaciones escritas). Los 3400 intentos fallidos previos por sí solos serían escaneo, pero el login exitoso posterior con comandos y exfiltración los excede. El analista de turno marcó los 4 puntos como cumplidos y el líder del SOC los validó a las 08:30.

Notificación y plazos legales: con 80000 clientes afectados (nombres, emails y saldos), legales evalúa la notificación a la autoridad en 72 horas y a los clientes sin demoras indebidas. El CISO pidió la declaración formal del incidente para activar el protocolo (vocero designado, call center reforzado, página de estado). El costo estimado de la notificación y el monitoreo de crédito para 80000 clientes es 120000 USD. La forense del servidor de backup (en curso, 48 horas) dirá si las credenciales se obtuvieron de ahí; si se confirma, hay que rotar todas las cuentas de servicio (40 cuentas) y revisar sus logs de 90 días. El ticket SOC-2026-1847 queda abierto hasta cerrar la forense y la notificación.

Lecciones y cuenta backup-svc: la excepción que dejaba a backup-svc sin 2FA (documentada en 2023, revisión pendiente) queda revocada desde hoy: todas las cuentas de servicio tendrán 2FA o certificado antes de fin de mes (40 cuentas, plan del área de infraestructura en 3 semanas). El DLP se extiende a FS-02 y a los otros 5 servidores de archivos antes de fin de trimestre (estaban en la lista de pendientes desde enero). El backup nocturno ya corre con cuenta nueva con 2FA y falló 0 veces en 3 noches. El SOC agrega una regla de alerta para logins de cuentas de servicio desde IPs externas (la que faltaba: la transferencia anómala se detectó, el login no). La revisión forense dirá si hubo compromiso previo del servidor de backup y condiciona la rotación masiva.

````

### Agregado para LLM tradicional

````
## Tarea
Solo respondé esta pregunta en función a lo indicado por el usuario y devolvé solo la respuesta, sin texto extra, sin argumentar.
Pregunta: Es una intrusión confirmada?
````

## Parámetros de modelo de decisión

```json
{
  "noul": {
    "type": "noul",
    "instructions": "Es una intrusión confirmada?"
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
        "noul": 0.9997546306241358
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2320,
    "completion_tokens": 1,
    "total_tokens": 2321,
    "total_time": 0.9
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
    "prompt_tokens": 2360,
    "completion_tokens": 1,
    "total_tokens": 2361,
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
  "data": "Sí",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2324,
    "completion_tokens": 88,
    "total_tokens": 2412,
    "total_time": 0.82,
    "time_to_first_token": 0.82
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
    "prompt_tokens": 2425,
    "completion_tokens": 2,
    "total_tokens": 2427,
    "total_time": 0.47,
    "time_to_first_token": 0.47
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 2320 | 1 | 0.91 | 1.0 | null | 0.0 |
| google | gemini-3.5-flash-lite | 2360 | 1 | 1.47 | Sí | null | 0.0007105 |
| groq | openai/gpt-oss-20b | 2324 | 88 | 0.82 | Sí | null | 0.00020069999999999997 |
| openrouter | inclusionai/ling-3.1-flash | 0 | 0 | 2.22 | "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'inclusionai/ling-3.1-flash is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'provider_name': 'Novita', 'is_byok': False, 'limit_source': 'upstream_provider_shared_pool', 'remedy_hint': 'Retry shortly, add your own provider key (https://openrouter.ai/settings/integrations), or route to another provider with provider routing: https://openrouter.ai/docs/features/provider-routing'}}, 'user_id': 'user_3IHIEaL9108If8k2gSzCi1zx2e3'}" | null | 0.0 |
| groq | qwen/qwen3.8-27b | 2425 | 2 | 0.47 | Sí | null | 0.001948 |
