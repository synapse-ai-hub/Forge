# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:16:57

## Prompt exacto del modelo de decisión

````
Sos el filtro técnico que puntúa un CV para un puesto de SRE con Kubernetes. Puntuá el CV según los criterios indicados.

CV de Andrés Vega:
- 5 años como sysadmin Linux y 2 años como SRE en un ecommerce con 200 nodos en GKE, guardias rotativas y SLOs definidos por servicio.
- Kubernetes: migró 40 servicios de VMs a GKE, escribe Helm charts desde cero, debuggeó OOMKills y throttling de CPU en producción, y configuró HPA con métricas custom de Prometheus.
- Incidentes: lideró la respuesta de 3 sev1 (caída de pagos, corrupción de cola, región caída) con postmortems públicos en su blog con métricas y timelines.
- Código: Go intermedio (operadores y exporters propios), Terraform para todo el stack, pipelines de GitLab con canary deploys.
- Debilidad: nunca trabajó con multi-región activo-activo ni con service mesh (solo ingress-nginx), y su inglés es B1 según certificación de 2023.
- Referencias: dos ex-jefes directos dejan teléfono y autorizan contacto.

El puesto exige Kubernetes en producción, guardias, código para automatizar e inglés para leer incident reviews globales. La descripción del puesto lista multi-región y mesh como deseables.

Más datos: el puesto es para un equipo de 6 SREs con guardias semanales rotativas y 3 incidentes nocturnos al mes en promedio. El stack es GKE, Terraform, Prometheus y GitLab, idéntico al que usa el candidato. El inglés se usa para leer incident reviews de la casa matriz y para 2 reuniones mensuales en inglés (no para escribir ni presentar). El presupuesto del puesto llega hasta semi-senior alto; el senior caro excede el 40 por ciento. La última contratación del equipo tardó 5 meses y renunció a los 8 meses por falta de mentoreo. El manager del equipo valora más la experiencia en incidentes reales que las certificaciones (el candidato no tiene CKAs pero sí 2 años de guardia real).

Expediente ampliado del candidato y del puesto:

El candidato tiene 4 años de experiencia total: 2 años como sysadmin con Linux y redes, 2 años como SRE en una fintech de 150 personas. En su rol actual administra 40 microservicios en GKE con Terraform (todo como código, 200 módulos), Prometheus con 300 alertas que él mismo definió y GitLab CI con 50 pipelines. Hace guardias semanales rotativas con 3 incidentes nocturnos al mes en promedio, igual que el puesto. Documentó 25 incident reviews con causa raíz y acciones, y lideró la respuesta en 2 caídas grandes (una de 2 horas por saturación de disco, otra de 45 minutos por un deploy con migración incompatible).

Profundidad en Kubernetes: maneja clusters de 60 nodos con 3 ambientes, hizo 4 upgrades de versión sin downtime, configuró HPA y PDB en todos los servicios críticos, y debuguea con kubectl, logs y métricas sin depender del dashboard. Lo que no tiene: nunca operó multi-región (todo en una sola región), nunca usó service mesh (usan ingress simple con NGINX), y su cluster más grande es 5 veces más chico que el del puesto (60 vs 300 nodos). En la entrevista técnica resolvió bien un caso de CrashLoopBackOff y uno de OOMKilled, pero flojeó en una pregunta de diseño multi-región (propuso DNS con failover manual en vez de activo-activo).

Código y automatización: escribe Python y Go para automatizar (tiene 15 scripts en producción: rotación de secretos, limpieza de imágenes viejas, reporte de costos). No escribe operadores ni controllers custom. Su código tiene tests en el 70 por ciento y pasa linting. El puesto pide código para automatizar tareas repetitivas, no desarrollo de plataforma desde cero.

Inglés: lee incident reviews de la casa matriz sin problema y participa en 2 reuniones mensuales en inglés (solo escucha y responde preguntas simples). No escribe documentos en inglés ni presenta. El puesto exige inglés para leer documentación y participar en esas reuniones, no para escribir ni liderar en inglés. Tiene certificación B1 de 2023.

Equipo y contexto: el equipo tiene 6 SREs con guardias semanales y 3 incidentes nocturnos al mes. El stack es idéntico al del candidato (GKE, Terraform, Prometheus, GitLab), así que sería productivo desde la primera semana en lo operativo. La última contratación tardó 5 meses en cerrarse y renunció a los 8 meses por falta de mentoreo; el manager prometió un plan de mentoreo esta vez con un buddy asignado. El presupuesto llega hasta semi-senior alto y el candidato pide 10 por ciento menos que el tope. El senior caro que también está en proceso pide 40 por ciento sobre el tope, tiene 8 años con multi-región y mesh, pero en la entrevista mostró poco interés en guardias y pidió 100 por ciento remoto desde otro huso horario (el puesto exige solapamiento de 6 horas).

Referencias: su manager actual dice que es el primero en responder en incidentes y el que mejor documenta, pero que a veces evita los proyectos largos de automatización. Un compañero dice que es sólido en lo operativo pero que nunca lideró un proyecto de más de 1 mes. El puesto necesita alguien que cubra guardias y opere desde el día uno, con crecimiento hacia proyectos en 1 año.

Tiempos: el puesto lleva 3 meses abierto, el equipo está sobrecargado cubriendo las guardias de a 5, y el manager quiere cerrar este mes. El candidato tiene otra oferta con decisión en 10 días.

Plan de mentoreo prometido: buddy asignado las primeras 4 semanas, 1 hora semanal con el manager los primeros 3 meses, y rotación por los 3 proyectos del equipo en el primer trimestre. Es el mismo plan que se prometió en la contratación anterior, que renunció a los 8 meses diciendo que el buddy nunca tuvo tiempo. El manager dice que esta vez el buddy tendrá 4 horas semanales reservadas en el calendario.

La otra oferta del candidato: una startup de 30 personas con sueldo 5 por ciento mayor pero sin guardias pagadas (las guardias son ad honorem rotativas) y stack distinto (ECS en vez de GKE). El candidato prefiere este puesto por el stack idéntico y las guardias pagas, pero decide en 10 días por el plazo de la otra oferta.
Criterios: se valora experiencia relevante, profundidad en Kubernetes, manejo de incidentes, capacidad de código e inglés.

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "no apto", "1": "apto con dudas", "2": "apto", "3": "apto destacado"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá el CV según los criterios.",
    "criteria": [
      "no apto",
      "apto con dudas",
      "apto",
      "apto destacado"
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
        "score": 2.094654778149454,
        "confidence": 0.883487390899001,
        "legend": {
          "0": "no apto",
          "1": "apto con dudas",
          "2": "apto",
          "3": "apto destacado"
        },
        "probabilities": {
          "0": 0.0005540522428555414,
          "1": 0.009820810990061537,
          "2": 0.8840414431418566,
          "3": 0.10558369362522638
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1542,
    "completion_tokens": 1,
    "total_tokens": 1543,
    "total_time": 6.88
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "2.6",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1562,
    "completion_tokens": 3,
    "total_tokens": 1565,
    "total_time": 1.38,
    "time_to_first_token": 1.38
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "3.0",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1605,
    "completion_tokens": 239,
    "total_tokens": 1844,
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
  "data": "2.6",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1907,
    "completion_tokens": 1642,
    "total_tokens": 3549,
    "total_time": 18.16,
    "time_to_first_token": 18.16
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "2",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1607,
    "completion_tokens": 2,
    "total_tokens": 1609,
    "total_time": 0.43,
    "time_to_first_token": 0.43
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 1542 | 1 | 6.89 | 2.09 | 0.883487390899001 | 0.0 |
| google | gemini-3.5-flash-lite | 1562 | 3 | 1.37 | 2.6 | null | 0.00047609999999999997 |
| groq | openai/gpt-oss-20b | 1605 | 239 | 0.63 | 3.0 | null | 0.000192075 |
| openrouter | inclusionai/ling-3.1-flash | 1907 | 1642 | 18.18 | 2.6 | null | 0.0 |
| groq | qwen/qwen3.8-27b | 1607 | 2 | 0.44 | 2.0 | null | 0.0012936000000000002 |
