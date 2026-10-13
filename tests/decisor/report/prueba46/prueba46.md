# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:03:41

## Prompt exacto del modelo de decisión

````
Sos el revisor de calidad de código. Puntuá la siguiente función de scraping según los criterios indicados. La función corre todos los días a las 6 de la mañana sobre un portal de empleos para extraer avisos nuevos.

```python
import requests
from bs4 import BeautifulSoup

def scrape_jobs(url):
    html = requests.get(url, timeout=15).text
    soup = BeautifulSoup(html, 'html.parser')
    jobs = []
    for card in soup.select('div.job-card'):
        title = card.select_one('h2.title').text.strip()
        company = card.select_one('span.company').text.strip()
        link = card.select_one('a.apply')['href']
        jobs.append({'title': title, 'company': company, 'link': link})
    return jobs
```

Contexto operativo: el portal cambió su HTML 3 veces este año y cada vez el scraper devolvió listas vacías sin alertar a nadie durante días (la última vez 6 días sin datos hasta que un analista lo notó). El timeout de 15 segundos sin reintentos hace que una caída nocturna del portal pierda el día completo: pasó 4 veces este trimestre. No hay paginado: solo trae la primera página de 20 avisos aunque haya 400 publicados. No se guarda estado de lo ya visto, así que cada corrida re-procesa todo y genera duplicados en la base. No hay logs ni métricas: cuando falla no queda registro de qué pasó. El código no valida que los selectores existan antes de usarlos (si falta un campo, rompe con AttributeError a mitad de la corrida). Funciona cuando el portal responde bien y no cambió nada: en esos casos devuelve los 20 avisos correctamente.

Volumen e impacto: el portal publica 400 avisos por día y el scraper trae 20, así que se pierde el 95 por ciento de la oferta. Los duplicados ya generaron 3 reclamos de clientes que vieron el mismo aviso 5 veces. El equipo de datos usa esta salida para un reporte semanal que sale con datos incompletos desde hace 2 meses. La función la escribió un pasante en 2 días y nadie la revisó. Hay un ticket abierto hace 6 semanas para agregarle reintentos que nadie tomó. El portal ofrece una API paga de 200 USD al mes que nadie evaluó.

Historial del scraper y del portal:

La función la escribió un pasante en 2 días como prueba de concepto y quedó en producción sin revisión porque el responsable renunció esa misma semana. Desde entonces pasaron 8 meses sin que nadie la toque, salvo un cambio de timeout de 10 a 15 segundos en marzo. El portal cambió su HTML 3 veces este año (enero, abril y mayo): cada vez el scraper devolvió listas vacías sin alertar durante días (6 días en enero, 4 en abril, 3 en mayo) hasta que un analista notó el reporte semanal vacío. Después de cada cambio alguien ajustó los selectores a mano en 2 horas, sin agregar validaciones ni alertas.

Caídas nocturnas: el portal se cae o responde lento 2 o 3 noches por mes entre las 2 y las 5. El scraper corre a las 3:00 sin reintentos: si el portal está caído a esa hora, se pierde el día completo. Pasó 4 veces este trimestre. El ticket para agregar reintentos está abierto hace 6 semanas sin dueño; el equipo de datos dice que no tiene capacidad y el de backend dice que el scraper no es suyo.

Paginado y cobertura: el portal muestra 20 avisos por página y publica 400 por día. El scraper trae solo la primera página (20 avisos, 5 por ciento del total) porque el pasante no implementó el paginado. Nadie sabe cuáles 20 trae (los más nuevos o los destacados, según el día). El reporte semanal que usa esta salida informa al directorio sobre la oferta del mercado con el 5 por ciento de los datos desde hace 2 meses, sin advertirlo.

Duplicados y estado: no se guarda estado de lo ya visto, así que cada corrida inserta los mismos 20 avisos de nuevo. La base tiene 8 meses de duplicados acumulados (aproximadamente 4800 filas para 600 avisos únicos). Los 3 reclamos de clientes fueron por ver el mismo aviso 5 veces en una búsqueda. El equipo de datos limpia duplicados a mano una vez por mes en 4 horas.

Observabilidad: no hay logs (solo prints que nadie mira), no hay métricas, no hay alerta si devuelve vacío, no hay registro de duración ni de cantidad traída. Cuando falla no queda registro de qué pasó: el diagnóstico se hace preguntando al analista si el reporte salió vacío. El validador de datos del warehouse rechaza el 30 por ciento de las filas por campos nulos (el scraper no valida que los selectores existan y cuando falta un campo rompe a mitad de corrida con AttributeError, dejando la mitad de los avisos sin procesar).

Alternativa API: el portal ofrece una API paga de 200 USD al mes con los 400 avisos diarios, paginado, webhooks de cambios y SLA. Nadie la evaluó formalmente; el responsable de datos pidió presupuesto hace 2 meses y sigue sin respuesta. El costo de las horas perdidas por datos incompletos se estima en 5000 USD mensuales entre reclamos y decisiones con datos parciales.

Lo que sí funciona: cuando el portal responde bien y no cambió el HTML, la función devuelve los 20 avisos con título, precio y ubicación correctos en 40 segundos. El código es corto (60 líneas), legible y sin dependencias raras. El pasante documentó los selectores en un comentario.

Costos y tiempos: el reporte semanal con datos incompletos lleva 2 meses saliendo así al directorio sin advertencia. El equipo de datos dedica 4 horas mensuales a limpiar duplicados a mano y 2 horas por cada cambio de HTML del portal. La API paga de 200 USD mensuales sigue sin evaluación formal después de 2 meses de pedido de presupuesto. Las horas perdidas entre reclamos, limpieza y decisiones con datos parciales se estiman en 5000 USD mensuales.

El pasante y la documentación: el pasante dejó un documento de 3 páginas con los selectores, el flujo y las limitaciones conocidas (sin paginado, sin estado, sin reintentos). El documento está en la wiki pero nadie lo leyó hasta esta auditoría. El responsable que renunció no designó dueño y el scraper no figura en el inventario de sistemas del equipo de backend.

Reclamos de clientes: los 3 reclamos fueron por el mismo aviso repetido 5 veces en búsquedas de 2 ambientes. En los 3 casos soporte respondió que era un problema de actualización del portal y no del scraper. El cuarto reclamo potencial (un cliente que preguntó por qué hay tan pocos avisos) quedó sin respuesta hace 3 semanas.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "muy malo", "1": "malo", "2": "regular", "3": "bueno", "4": "muy bueno", "5": "excelente"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá la calidad de la función según los criterios.",
    "criteria": [
      "muy malo",
      "malo",
      "regular",
      "bueno",
      "muy bueno",
      "excelente"
    ]
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
      "score": {
        "type": "score",
        "score": 0.226963546626251,
        "confidence": 0.8486909689158326,
        "legend": {
          "0": "muy malo",
          "1": "malo",
          "2": "regular",
          "3": "bueno",
          "4": "muy bueno",
          "5": "excelente"
        },
        "probabilities": {
          "0": 0.7756021981064561,
          "1": 0.22221375683529304,
          "2": 0.0019225254648964113,
          "3": 0.00017882280938117298,
          "4": 4.5213486844605004e-05,
          "5": 3.7483297128644016e-05
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1709,
    "completion_tokens": 1,
    "total_tokens": 1710,
    "total_time": 1.11
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "0.5",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1652,
    "completion_tokens": 3,
    "total_tokens": 1655,
    "total_time": 1.58,
    "time_to_first_token": 1.58
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "0",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1660,
    "completion_tokens": 161,
    "total_tokens": 1821,
    "total_time": 0.63,
    "time_to_first_token": 0.63
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "0.3",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1945,
    "completion_tokens": 109,
    "total_tokens": 2054,
    "total_time": 2.58,
    "time_to_first_token": 2.58
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1474. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}",
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
| openrouter | inception/mercury-decide:free | 1709 | 1 | 1.11 | 0.23 | 0.8486909689158326 | 0.0 |
| google | gemini-3.5-flash-lite | 1652 | 3 | 1.58 | 0.5 | null | 0.0005031 |
| groq | openai/gpt-oss-20b | 1660 | 161 | 0.63 | 0.0 | null | 0.00017279999999999997 |
| openrouter | inclusionai/ling-3.1-flash | 1945 | 109 | 2.59 | 0.3 | null | 0.0 |
| groq | qwen/qwen3.8-27b | 0 | 0 | 0.14 | "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1474. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}" | null | 0.0 |
