# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 01:21:39

## Prompt exacto del modelo de decisión

````
Sos el revisor de código automático de un equipo backend. La regla de aprobación de merge es: se aprueba solo si el código maneja todos los errores de red con reintentos con backoff exponencial, no deja conexiones abiertas, loguea cada intento fallido con nivel warning, y corta después de un máximo de 5 intentos devolviendo un error tipado. Si hay un solo incumplimiento, no se aprueba.

Pull request 4417, módulo integraciones/pagos, archivo retry_client.py completo (214 líneas, se muestra íntegro):

```python
import time
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
NON_RETRYABLE_STATUS = {400, 401, 403, 404, 422}
MAX_ATTEMPTS = 5
BASE_DELAY = 1.0
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 10

class RetryExhausted(Exception):
    def __init__(self, url, attempts, last_error=None):
        super().__init__('Se agotaron los reintentos contra {}'.format(url))
        self.url = url
        self.attempts = attempts
        self.last_error = last_error

class NonRetryableError(Exception):
    def __init__(self, url, status, body=None):
        super().__init__('Error no reintentable {} contra {}'.format(status, url))
        self.url = url
        self.status = status
        self.body = body

class CircuitOpenError(Exception):
    pass

def _is_retryable(exc, response=None):
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    if response is not None and response.status_code in RETRYABLE_STATUS:
        return True
    return False

def _parse_error_body(response):
    try:
        data = response.json()
        return data.get('error', {}).get('code', 'UNKNOWN')
    except (ValueError, AttributeError):
        return 'UNPARSEABLE'

def retry_request(url, payload, max_attempts=MAX_ATTEMPTS, idempotency_key=None):
    attempt = 0
    session = requests.Session()
    session.mount('https://', HTTPAdapter(pool_connections=10, pool_maxsize=10))
    headers = {}
    if idempotency_key:
        headers['Idempotency-Key'] = idempotency_key
    try:
        while attempt < max_attempts:
            response = None
            try:
                response = session.post(url, json=payload, headers=headers, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
                if response.status_code in RETRYABLE_STATUS:
                    raise requests.HTTPError('Status reintentable: {}'.format(response.status_code))
                if response.status_code in NON_RETRYABLE_STATUS:
                    code = _parse_error_body(response)
                    raise NonRetryableError(url, response.status_code, code)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                attempt += 1
                logger.warning('Intento %d de %d fallido contra %s: %s', attempt, max_attempts, url, exc)
                if response is not None:
                    response.close()
                if attempt >= max_attempts or not _is_retryable(exc, response):
                    if isinstance(exc, NonRetryableError):
                        raise
                    raise RetryExhausted(url, attempt, exc) from exc
                delay = BASE_DELAY * (2 ** (attempt - 1))
                logger.debug('Reintentando en %.1f segundos', delay)
                time.sleep(delay)
    finally:
        session.close()
    raise RetryExhausted(url, attempt)
```

Evidencia del PR:
- El backoff entre los 5 intentos es 1, 2, 4 y 8 segundos (BASE_DELAY 1.0 por 2 elevado a attempt-1). Verificado en los tests con reloj mockeado: test_backoff_sequence aserciona [1.0, 2.0, 4.0, 8.0].
- Los 400, 401, 403, 404 y 422 cortan en el primer intento con NonRetryableError sin reintentar (test_non_retryable_status parametrizado con los 5 códigos, verifica 1 solo request).
- Los 429, 500, 502, 503 y 504 reintentan hasta 5 intentos (test_retryable_status parametrizado, verifica 5 requests y RetryExhausted con attempts=5).
- Cada response de intento fallido se cierra explícitamente (test_response_closed verifica response.close en los 4 fallidos). La sesión se cierra en el finally aunque haya excepción (test_session_closed). En el camino feliz el .json() consume el body y la conexión vuelve al pool.
- Cada intento fallido genera un log warning con intento, total, URL y error (test_warning_logs cuenta 4 warnings en un caso de 5 intentos con éxito al quinto). El handler del módulo es rotativo a archivo con nivel INFO, así que los warning quedan persistidos.
- CI: 34 tests del módulo todos pasados, cobertura del archivo 96 por ciento (sin cubrir solo el logger.debug y el raise final inalcanzable), bandit sin findings, mypy estricto sin errores.
- El ADR 12 del equipo exige exactamente este comportamiento (5 intentos, backoff exponencial desde 1 segundo, corte inmediato en 4xx, errores tipados) y cita este PR como implementación de referencia. El incidente de marzo (reintentos infinitos contra el proveedor caído que amplificaron la caída) es lo que motivó la regla de 5 intentos.

````

### Agregado para LLM tradicional

````
## Tarea
Solo respondé esta pregunta en función a lo indicado por el usuario y devolvé solo la respuesta, sin texto extra, sin argumentar.
Pregunta: El código cumple todas las reglas y se puede aprobar el merge?
````

## Parámetros de modelo de decisión

```json
{
  "noul": {
    "type": "noul",
    "instructions": "El código cumple todas las reglas y se puede aprobar el merge?"
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
        "noul": 0.9975273764677868
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1376,
    "completion_tokens": 1,
    "total_tokens": 1377,
    "total_time": 1.11
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
    "prompt_tokens": 1477,
    "completion_tokens": 1,
    "total_tokens": 1478,
    "total_time": 1.43,
    "time_to_first_token": 1.43
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1340,
    "completion_tokens": 1224,
    "total_tokens": 2564,
    "total_time": 1.84,
    "time_to_first_token": 1.84
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "No, no se aprueba.\n\nIncumplimiento: al recibir 400/401/403/404/422, `NonRetryableError` se lanza dentro del `try` pero no hereda de `requests.RequestException`, por lo que el `except` no la captura: ese intento fallido no genera el `logger.warning` obligatorio (los warnings solo se emiten en la rama de errores reintentables; el test citado solo cubre esa rama). Además, `max_attempts` es un parámetro sobrescribible por el caller, con lo que no se garantiza el corte máximo de 5 intentos.\n\nCon un solo incumplimiento, la regla de merge no se cumple.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1526,
    "completion_tokens": 11262,
    "total_tokens": 12788,
    "total_time": 110.77,
    "time_to_first_token": 110.77
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
    "prompt_tokens": 1391,
    "completion_tokens": 2,
    "total_tokens": 1393,
    "total_time": 0.47,
    "time_to_first_token": 0.47
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 1376 | 1 | 1.12 | 1.0 | null | 0.0 |
| google | gemini-3.5-flash-lite | 1477 | 1 | 1.44 | Sí | null | 0.0004456 |
| groq | openai/gpt-oss-20b | 1340 | 1224 | 1.84 | Sí. | null | 0.0004677 |
| openrouter | inclusionai/ling-3.1-flash | 1526 | 11262 | 110.78 | No, no se aprueba.  Incumplimiento: al recibir 400/401/403/404/422, `NonRetryableError` se lanza dentro del `try` pero no hereda de `requests.RequestException`, por lo que el `except` no la captura: ese intento fallido no genera el `logger.warning` obligatorio (los warnings solo se emiten en la rama de errores reintentables; el test citado solo cubre esa rama). Además, `max_attempts` es un parámetro sobrescribible por el caller, con lo que no se garantiza el corte máximo de 5 intentos.  Con un solo incumplimiento, la regla de merge no se cumple. | null | 0.0 |
| groq | qwen/qwen3.8-27b | 1391 | 2 | 0.47 | Sí | null | 0.0011208 |
