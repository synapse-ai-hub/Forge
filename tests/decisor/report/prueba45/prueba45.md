# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:01:13

## Prompt exacto del modelo de decisión

````
Sos un lector que elige según el texto dado, sin usar conocimiento externo. El texto es el siguiente.

Texto: Tres ciudades compiten por la feria tecnológica de 2027. Córdoba ofrece un predio para 30000 asistentes con fibra dedicada de 10 Gbps, 4000 plazas hoteleras a 15 minutos y vuelos directos desde 4 capitales regionales. Rosario ofrece un predio para 45000 asistentes con fibra de 5 Gbps y 6000 plazas hoteleras a 25 minutos, más un descuento del 20 por ciento en el alquiler del predio. Mendoza ofrece un predio para 25000 asistentes con fibra de 10 Gbps y 3500 plazas hoteleras a 10 minutos, con vuelos directos desde 6 capitales regionales. La organización espera 28000 asistentes, necesita al menos 8 Gbps de conectividad para el streaming global, y el 60 por ciento de los asistentes viaja en avión.

Datos extra: Córdoba ya hospedó la feria en 2024 sin incidentes y el predio tiene experiencia con eventos de este tamaño; Rosario nunca hospedó nada mayor a 20000 personas y su predio está en obra hasta marzo de 2027; Mendoza hospedó un congreso de 20000 en 2025 con buenas críticas pero su aeropuerto cierra de noche por niebla en invierno (la feria es en julio). El descuento de Rosario equivale a 40000 USD sobre un presupuesto total de 2 millones. La organización firmó con un sponsor que exige streaming en 4K sin cortes (de ahí los 8 Gbps). El 60 por ciento que viaja en avión se reparte en 10 capitales y solo 6 tienen vuelo directo a alguna sede.

Expediente completo de las sedes con visitas técnicas, costos y riesgos:

Asistentes esperados: 28000 (20000 profesionales, 5000 estudiantes, 3000 expositores y prensa). El 60 por ciento viaja en avión desde 10 capitales regionales; solo 6 de esas capitales tienen vuelo directo a alguna de las 3 sedes. El 40 por ciento llega en micro o auto desde un radio de 500 km. Se necesitan 28000 plazas de alojamiento en 3 noches pico más 5000 para staff y expositores que llegan 3 días antes.

Córdoba: predio para 30000 con fibra dedicada de 10 Gbps (contrato con 2 proveedores, redundancia real verificada en la visita técnica), 4000 plazas hoteleras a 15 minutos del predio más 6000 a 30 minutos. Vuelos directos desde 4 capitales. Hospedó la feria en 2024 con 26000 asistentes sin incidentes: el post-evento midió satisfacción 8.5 sobre 10 y conectividad sin caídas. El predio cobra 200000 USD por los 4 días sin descuento. La ciudad ofrece apoyo logístico municipal (cortes de tránsito y seguridad incluidos). Riesgo: las 4000 plazas cercanas no alcanzan para los 28000 y hay que distribuir en 3 zonas con micros pagos por la organización (costo 30000 USD). El aeropuerto no tiene restricciones climáticas en julio.

Rosario: predio para 45000 con fibra de 5 Gbps (un solo proveedor, sin redundancia; la visita técnica encontró que el backup es por radioenlace de 500 Mbps). 6000 plazas hoteleras a 25 minutos más 4000 a 40 minutos. Vuelos directos desde 3 capitales. Nunca hospedó eventos de más de 20000 personas; el predio está en obra de ampliación hasta marzo de 2027 (la feria es en julio de 2027, margen de 4 meses). Descuento del 20 por ciento en el alquiler: 160000 USD en vez de 200000 (ahorro 40000 USD sobre presupuesto total de 2 millones, es decir 2 por ciento). La ciudad ofrece el descuento a cambio de 3 años de sede consecutivos (cláusula de permanencia). Riesgo conectividad: el sponsor exige streaming en 4K sin cortes y necesita 8 Gbps sostenidos; con 5 Gbps no alcanza y habría que contratar un enlace temporal de 5 Gbps extra por 60000 USD (más que el descuento). Riesgo obra: si la ampliación se atrasa, el predio queda en 25000 de capacidad.

Mendoza: predio para 25000 con fibra de 10 Gbps (2 proveedores, redundancia verificada), 3500 plazas hoteleras a 10 minutos más 5000 a 25 minutos. Vuelos directos desde 6 capitales (la mejor conectividad aérea). Hospedó un congreso de 20000 en 2025 con satisfacción 9 sobre 10. El predio cobra 190000 USD. Riesgos: capacidad de 25000 para 28000 esperados (hay que dejar 3000 afuera o agregar carpas por 50000 USD); el aeropuerto cierra de noche por niebla en julio (la feria es en julio) y el historial muestra 12 noches con cierre en julio de 2025, lo que afectaría al 60 por ciento que viaja en avión; las 3500 plazas cercanas son insuficientes y la ciudad es la más cara en hotelería (30 por ciento sobre Córdoba).

Sponsor y streaming: el sponsor principal (400000 USD, 20 por ciento del presupuesto) exige streaming global en 4K sin cortes con su marca, de ahí los 8 Gbps mínimos. Si el streaming se cae, hay penalidad de 100000 USD. El sponsor ya avisó que no acepta radioenlace como backup. La productora del streaming trabajó en Córdoba 2024 sin incidentes y no conoce los otros predios.

Decisión y tiempos: la organización debe firmar la sede este mes o pierde la seña de los 3 predios (50000 USD cada una, solo una es reembolsable). Votan 7 miembros del comité con intereses cruzados: 2 de Córdoba, 2 de Rosario, 1 de Mendoza y 2 neutrales. El presupuesto total es 2 millones con margen de contingencia de 100000 USD.

Señas y penalidades: se pagaron 50000 USD de seña por cada predio para reservar la fecha. Solo la seña de Córdoba es reembolsable (porque hospedó en 2024 y tiene convenio). Si se elige otra sede, la seña de Córdoba se recupera y las otras 2 se pierden (100000 USD). Si no se firma este mes, se pierden las 3 señas (150000 USD) y la fecha de julio queda libre para otro evento. El comité vota en 10 días y necesita 4 votos: hay 2 de Córdoba, 2 de Rosario, 1 de Mendoza y 2 neutrales que piden un informe técnico antes de votar. Este expediente es ese informe.

Alojamiento y transporte interno: Córdoba tiene 4000 plazas a 15 minutos y 6000 a 30 (faltan 18000 que se cubren con 3 zonas y micros por 30000 USD). Rosario tiene 6000 a 25 minutos y 4000 a 40 (faltan 18000 con micros por 25000 USD). Mendoza tiene 3500 a 10 minutos y 5000 a 25 (faltan 19500 con micros por 35000 USD, la ciudad más cara). Los micros los paga la organización en los 3 casos y el costo ya está incluido en el presupuesto de 2 millones.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- cordoba: elegir Córdoba con predio de 30000 y fibra de 10 Gbps
- rosario: elegir Rosario con predio de 45000 y fibra de 5 Gbps
- mendoza: elegir Mendoza con predio de 25000 y fibra de 10 Gbps
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí la ciudad que cumple todos los requisitos según el texto.",
    "criteria": {
      "cordoba": "elegir Córdoba con predio de 30000 y fibra de 10 Gbps",
      "rosario": "elegir Rosario con predio de 45000 y fibra de 5 Gbps",
      "mendoza": "elegir Mendoza con predio de 25000 y fibra de 10 Gbps"
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
        "choice": "cordoba",
        "confidence": 0.9969883266228844,
        "probabilities": {
          "cordoba": 0.9979922177485897,
          "rosario": 0.0010977311577236102,
          "mendoza": 0.0009100510936867544
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1945,
    "completion_tokens": 1,
    "total_tokens": 1946,
    "total_time": 5.76
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "cordoba",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1971,
    "completion_tokens": 2,
    "total_tokens": 1973,
    "total_time": 1.52,
    "time_to_first_token": 1.52
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "cordoba",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1794,
    "completion_tokens": 925,
    "total_tokens": 2719,
    "total_time": 1.41,
    "time_to_first_token": 1.41
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "cordoba",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2322,
    "completion_tokens": 933,
    "total_tokens": 3255,
    "total_time": 11.81,
    "time_to_first_token": 11.81
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1831. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}",
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
| openrouter | inception/mercury-decide:free | 1945 | 1 | 5.76 | cordoba | 0.9969883266228844 | 0.0 |
| google | gemini-3.5-flash-lite | 1971 | 2 | 1.54 | cordoba | null | 0.0005963 |
| groq | openai/gpt-oss-20b | 1794 | 925 | 1.42 | cordoba | null | 0.00041205 |
| openrouter | inclusionai/ling-3.1-flash | 2322 | 933 | 11.81 | cordoba | null | 0.0 |
| groq | qwen/qwen3.8-27b | 0 | 0 | 0.12 | "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1831. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}" | null | 0.0 |
