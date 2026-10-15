# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 02:26:04

## Prompt exacto del modelo de decisión

````
Sos el arquitecto cloud que elige el servicio de almacenamiento. Workload:

Una plataforma de cursos online con 200000 estudiantes necesita guardar 80000 videos (promedio 400 MB cada uno, total 32 TB y creciendo 2 TB por mes), con picos de 15000 reproducciones simultáneas en época de exámenes. Los videos se suben una vez y se leen miles de veces. El 90 por ciento de las reproducciones son de videos subidos hace más de 6 meses. El presupuesto de infraestructura es ajustado y el equipo no quiere administrar servidores. La latencia de inicio de reproducción debe ser menor a 2 segundos en toda Latinoamérica. Hoy los videos están en un servidor propio que se cae en cada pico y el equipo de soporte recibe 500 reclamos por semana por videos que no cargan.

Tráfico: el 60 por ciento de los estudiantes está en Argentina, 20 por ciento en México y el resto repartido en 8 países. Los picos son de 19 a 23 horas y duran 3 semanas por cuatrimestre. El 70 por ciento mira desde el celular con conexiones 4G inestables, así que se necesita streaming adaptativo con al menos 3 calidades. Los videos nuevos (10 por ciento del catálogo) concentran el 50 por ciento de las vistas en su primera semana. Hay que guardar también subtítulos y miniaturas, y por contrato con los profesores los videos no pueden salir de la región. El equipo es de 4 personas sin especialista en infraestructura y el presupuesto mensual total es 8000 USD.

Detalle técnico del catálogo y del consumo:

Los 80000 videos promedian 400 MB en calidad original (1080p), total 32 TB, con crecimiento de 2 TB por mes (5000 videos nuevos mensuales de 400 MB). Cada video necesita 3 versiones para streaming adaptativo (360p, 720p, 1080p) más miniatura y subtítulos en español y portugués. Con las 3 calidades el almacenamiento real es 48 TB y crece 3 TB por mes. El 90 por ciento de las reproducciones son de videos de más de 6 meses (el catálogo viejo rinde), pero los videos nuevos concentran el 50 por ciento de las vistas en su primera semana (pico de demanda sobre contenido recién subido).

Picos y exámenes: 3 semanas por cuatrimestre (2 cuatrimestres) con 15000 reproducciones simultáneas entre las 19 y las 23. Fuera de pico el promedio es 2000 simultáneas. El servidor propio actual (2 máquinas con 20 TB cada una en RAID, sin réplica geográfica) se cae en cada pico: en el último pico estuvo caído 6 horas repartidas en 3 noches con 500 reclamos por semana a soporte. La latencia de inicio debe ser menor a 2 segundos; hoy en pico llega a 25 segundos y el 40 por ciento abandona antes de que arranque.

Distribución geográfica: 60 por ciento Argentina, 20 por ciento México, 20 por ciento en 8 países (Colombia, Perú, Chile, Uruguay, Ecuador, España, EEUU y Brasil). Por contrato con los profesores los videos no pueden salir de Latinoamérica (restricción regional que hay que poder configurar). El 70 por ciento mira desde celular con 4G inestable: sin streaming adaptativo con al menos 3 calidades la experiencia se corta. El 20 por ciento mira desde PC y el 10 por ciento desde tablet.

Equipo y presupuesto: 4 personas (2 backend, 1 frontend, 1 diseñador que hace de devops part time). Nadie administró nunca almacenamiento distribuido ni CDN. El presupuesto mensual total de infraestructura es 8000 USD e incluye todo (cómputo, base de datos, almacenamiento y transferencia). Hoy gastan 3000 USD en los servidores propios (alquiler de rack y conectividad) más 2000 USD en transferencia por picos. La dirección no va a aprobar más presupuesto este año pero sí un cambio de arquitectura si entra en los 8000.

Requisitos no funcionales: subida de videos por los profesores (100 subidas diarias de 400 MB con reintentos), procesamiento automático a las 3 calidades al subir (hoy lo hacen a mano y tarda 2 días), subtítulos y miniaturas asociados a cada video, borrado lógico con retención de 1 año por contrato, y métricas de visualización por video para pagar regalías a los profesores (hoy las métricas se pierden cuando se cae el servidor).

Alternativas evaluadas por el equipo: seguir con servidores propios agregando 2 máquinas más (costo 2500 USD extra por mes, sin réplica geográfica, el equipo seguiría administrando todo), almacenamiento en red administrado con caché por región (costo estimado 6000 USD por mes, con caché local que hay que dimensionar), y almacenamiento de objetos con CDN y tiers por antigüedad (costo estimado 4500 USD por mes con el 90 por ciento del catálogo en tier frío). El equipo nunca usó ninguna de las tres y pide una recomendación con números.

Números de transferencia y costos actuales: cada reproducción consume en promedio 250 MB (calidad adaptativa media). Con 2000 simultáneas promedio son 500 GB por hora y 12 TB por día; en pico de 15000 simultáneas son 3.75 TB por hora. La transferencia actual cuesta 2000 USD por mes en promedio y 6000 en meses de pico. Los servidores propios (rack y conectividad) cuestan 3000 USD fijos más el tiempo del diseñador haciendo de devops (10 horas semanales). El presupuesto total de 8000 USD incluye cómputo (2500), base de datos (1500) y el resto para almacenamiento y transferencia. Cualquier alternativa debe entrar en 3000 USD para almacenamiento más transferencia sin pasar el total.

Subida y procesamiento: los profesores suben 100 videos diarios de 400 MB por una interfaz web con reintentos (las subidas se cortan con 4G inestable y hoy hay que empezar de nuevo). El procesamiento a las 3 calidades se hace a mano en una PC del equipo y tarda 2 días por lote, lo que retrasa la publicación de los videos nuevos que concentran la demanda de la primera semana. Cualquier alternativa debe incluir subida con reanudación y procesamiento automático al subir, con cola para los picos de 100 videos diarios.

Métricas para regalías: cada reproducción debe registrarse con video, usuario, fecha y porcentaje visto para pagar a los profesores por visualización. Hoy las métricas se guardan en la misma base del servidor propio y se pierden cuando se cae (en el último pico se perdieron 3 días). Los profesores reclaman todos los meses por diferencias y el equipo tarda 1 semana en conciliar a mano.

````

### Agregado para LLM tradicional

````
## Tarea
En base a lo indicado en el prompt y a la solicitud del usuario, elige una de las siguientes opciones y devuelve solo la opción elegida, sin texto extra, sin argumentar.
Opciones:
- objetos: almacenamiento de objetos con CDN y tiers por antigüedad sin administrar servidores
- bloque: discos en bloque en instancias propias con réplica manual
- nas: almacenamiento en red administrado con caché local por región
````

## Parámetros de modelo de decisión

```json
{
  "choice": {
    "type": "choice",
    "instructions": "Elegí la opción que mejor resuelve el workload.",
    "criteria": {
      "objetos": "almacenamiento de objetos con CDN y tiers por antigüedad sin administrar servidores",
      "bloque": "discos en bloque en instancias propias con réplica manual",
      "nas": "almacenamiento en red administrado con caché local por región"
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
        "choice": "objetos",
        "confidence": 0.9715275080722862,
        "probabilities": {
          "objetos": 0.9810183387148574,
          "bloque": 0.0010136839177590225,
          "nas": 0.017967977367383516
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1732,
    "completion_tokens": 1,
    "total_tokens": 1733,
    "total_time": 1.71
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "objetos",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1664,
    "completion_tokens": 2,
    "total_tokens": 1666,
    "total_time": 7.66,
    "time_to_first_token": 7.66
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "objetos",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1632,
    "completion_tokens": 301,
    "total_tokens": 1933,
    "total_time": 0.66,
    "time_to_first_token": 0.66
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "objetos: almacenamiento de objetos con CDN y tiers por antigüedad sin administrar servidores",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2037,
    "completion_tokens": 48,
    "total_tokens": 2085,
    "total_time": 1.81,
    "time_to_first_token": 1.81
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "error",
  "message": "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1267. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}",
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
| openrouter | inception/mercury-decide:free | 1732 | 1 | 1.7 | objetos | 0.9715275080722862 | 0.0 |
| google | gemini-3.5-flash-lite | 1664 | 2 | 7.67 | objetos | null | 0.0005042 |
| groq | openai/gpt-oss-20b | 1632 | 301 | 0.67 | objetos | null | 0.0002127 |
| openrouter | inclusionai/ling-3.1-flash | 2037 | 48 | 1.83 | objetos: almacenamiento de objetos con CDN y tiers por antigüedad sin administrar servidores | null | 0.0 |
| groq | qwen/qwen3.8-27b | 0 | 0 | 0.39 | "Error code: 429 - {'error': {'message': \"Request too large for model `qwen/qwen3.8-27b` in organization `org_01knygg3ate5a9mqy8my4acsb5` service tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 1267. The request's expected output tokens exceed the enforced limit; reduce max_tokens (or the request's expected output) and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing\", 'type': 'tokens', 'code': 'rate_limit_exceeded'}}" | null | 0.0 |
