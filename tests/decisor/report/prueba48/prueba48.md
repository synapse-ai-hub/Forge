# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 03:08:39

## Prompt exacto del modelo de decisión

````
Sos el scoring de calidad de leads para un CRM que vende software de gestión de flotas a empresas de transporte. Puntuá el lead según los criterios indicados.

Lead: Jorge Salinas, gerente de mantenimiento de Transportes del Litoral SA, Santa Fe. Flota propia de 85 camiones más 30 tercerizados, operando en 6 provincias. 210 empleados. Hoy controlan combustible y mantenimiento con planillas y el gerente admite un desvío de combustible del 8 por ciento que no pueden explicar (estiman 40000 USD anuales de pérdida). Abrió 7 correos, descargó el caso de éxito de una empresa similar, asistió a una demo de 45 minutos con 3 personas de su equipo e hizo preguntas sobre integración con los tacógrafos que ya tienen. Pidieron cotización para 40 unidades y dijeron que el directorio aprueba compras de hasta 50000 USD sin licitación. El presupuesto 2026 incluye una partida de 60000 USD para tecnología de flota. La decisión la toman entre el gerente y el director de operaciones, ambos ya involucrados. Único riesgo: quieren arrancar en 60 días y la implementación típica tarda 90.

Más datos: la empresa viene de un intento fallido con otro proveedor hace 2 años (lo abandonaron a los 4 meses por mala implementación) y el directorio pide referencias de clientes similares antes de firmar. El competidor que usan los tercerizados les ofreció 20 por ciento menos pero sin integración a tacógrafos. El gerente quiere arrancar con 40 unidades como piloto y escalar a 85 si funciona; el director quiere todo junto para negociar mejor precio. La partida de 60000 USD compite con la renovación de 10 camiones   que también pide el directorio. El lead lleva 3 meses en el pipeline con 11 interacciones y la última demo la pidió el director personalmente.

Ampliación del lead con flota, dolor, decisores y presupuesto:

Flota y operación: 85 camiones propios más 30 tercerizados, operando en 6 provincias con base en Santa Fe. 210 empleados (45 administrativos, 120 choferes, 45 taller). Hoy controlan combustible y mantenimiento con planillas Excel que maneja 1 sola persona (punto único de falla: cuando se enferma nadie actualiza). El consumo de combustible es 180000 litros mensuales por 900000 USD anuales. No tienen telemetría ni GPS propio (usan el del cliente para 20 camiones). El taller hace mantenimiento correctivo (promedio 8 camiones parados por semana) sin plan preventivo. La última rotura en ruta costó 25000 USD entre grúa, reparación y penalidad del cliente.

Dolor cuantificado: el gerente calculó 120000 USD anuales en combustible sin control (desvíos del 8 por ciento sobre el estándar por ruta), 80000 USD en mantenimiento correctivo evitable y 60000 USD en multas de clientes por demoras (3 por mes promedio). Total: 260000 USD anuales. El director pidió el ROI por escrito y el vendedor lo presentó: con el software (45000 USD anuales) el ahorro estimado es 150000 USD (recupero en 4 meses). El director dijo que los números le cierran pero quiere hablar con 2 clientes de referencia antes de firmar.

Decisores: Jorge Salinas (gerente de mantenimiento, sponsor técnico, quien sufre el dolor), el director de operaciones (quien pidió la última demo personalmente y maneja el presupuesto) y el gerente de administración (quien firma compras sobre 30000 USD). Los 3 participaron de la demo. El director de operaciones dijo que la flota es prioridad 2026 del directorio. No hay bloqueadores identificados: IT (2 personas) confirmó que la integración con su ERP lleva 2 semanas y no pone objeciones.

Presupuesto y tiempos: 50000 USD aprobados para 2026 en la partida de sistemas (el software cuesta 45000 más 10000 de implementación). La compra debe cerrarse antes de octubre porque en noviembre congelan compras por el cierre. El lead lleva 3 meses en el pipeline con 11 interacciones (3 demos, 2 visitas a planta, 4 llamadas técnicas, 1 presentación de ROI y 1 visita a un cliente de referencia). La última demo la pidió el director personalmente con los 3 decisores presentes. El vendedor califica el cierre al 70 por ciento para septiembre.

Competencia y alternativas: evalúan 2 competidores (uno de 30000 USD sin módulo de mantenimiento, otro de 60000 USD con telemetría incluida que no necesitan). El gerente prefiere esta opción por el módulo de mantenimiento preventivo. El competidor barato ya fue descartado por el director por falta de soporte local. Queda el de 60000 USD como alternativa si la negociación de precio falla.
Criterios: se valora tamaño de flota, dolor cuantificado, involucramiento de decisores, presupuesto asignado, interacciones concretas y encaje de tiempos.

Historial del pipeline: el lead entró en marzo por referidos de un cliente actual (que ahorró 100000 USD con el software). En abril se hizo la primera demo con el gerente solo. En mayo el director se sumó y pidió el ROI. En junio se hizo la visita a planta y la demo con los 3 decisores. El pronóstico del vendedor pasó de 30 a 70 por ciento en 3 meses. El único riesgo registrado es que el director quiere las 2 referencias antes de firmar y una de ellas está en cosecha gruesa (responde en 2 semanas).

Checklist de scoring aplicado: tamaño de flota (85 propios más 30 tercerizados, 210 empleados, 6 provincias: flota grande para el segmento), dolor cuantificado (260000 USD anuales con ROI presentado y aceptado por el director), decisores involucrados (los 3, incluido el director que pidió la demo personalmente), presupuesto asignado (50000 USD aprobados en partida 2026, compra antes de octubre), interacciones concretas (11 en 3 meses con avance de pronóstico de 30 a 70), encaje de tiempos (cierre estimado septiembre, dentro de la ventana de compra). El vendedor marcó los 6 criterios como altos y su gerente los validó. El directorio pide el scoring para priorizar los 40 leads del trimestre y este es el único con los 3 decisores identificados y presupuesto aprobado.

Comparación con el resto del pipeline: de 40 leads, 12 tienen flota de más de 50 camiones, 8 tienen dolor cuantificado con ROI, 5 tienen al director involucrado, 3 tienen presupuesto aprobado y solo 1 (este) tiene las 6 cosas a la vez. El segundo mejor lead tiene 5 de 6 (le falta presupuesto hasta 2027). El scoring del trimestre define dónde van las 2 visitas a planta que quedan (cada visita cuesta 3000 USD y el vendedor ya usó 1 con este lead en junio). El gerente comercial quiere concentrar en los 3 mejores y este lidera por ser el único con cierre estimado en septiembre dentro de la ventana de compra de octubre.

Decisión del scoring: el CRM puntúa de 0 a 5 según tamaño de flota, dolor cuantificado, decisores, presupuesto, interacciones y tiempos. Este lead tiene flota grande (85 más 30), dolor de 260000 USD con ROI aceptado, 3 decisores con el director a favor, 50000 USD aprobados, 11 interacciones con pronóstico al 70 por ciento y cierre en septiembre dentro de la ventana. El único riesgo es la referencia en cosecha (2 semanas) y la alternativa de 60000 USD si falla el precio. El scoring define si va primero en las visitas y en el forecast del trimestre (el vendedor lo puso al 70 por ciento y su gerente lo validó).

````

### Agregado para LLM tradicional

````
## Tarea
Asigná un puntaje en base a los criterios del usuario y devolvé solo el puntaje como número (puede tener decimales, puede caer entre niveles), sin texto extra, sin argumentar.
Escala:
```json
{"0": "descartable", "1": "frio", "2": "tibio", "3": "caliente", "4": "muy caliente"}
```
````

## Parámetros de modelo de decisión

```json
{
  "score": {
    "type": "score",
    "instructions": "Puntuá la calidad del lead según los criterios.",
    "criteria": [
      "descartable",
      "frio",
      "tibio",
      "caliente",
      "muy caliente"
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
        "score": 3.99629820103172,
        "confidence": 0.9969151675264335,
        "legend": {
          "0": "descartable",
          "1": "frio",
          "2": "tibio",
          "3": "caliente",
          "4": "muy caliente"
        },
        "probabilities": {
          "0": 1.7714398659564467e-05,
          "1": 7.860716754885618e-06,
          "2": 6.93705818828139e-06,
          "3": 0.003593485107000294,
          "4": 0.9963740027193969
        }
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1968,
    "completion_tokens": 1,
    "total_tokens": 1969,
    "total_time": 1.68
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "4.8",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1908,
    "completion_tokens": 3,
    "total_tokens": 1911,
    "total_time": 1.67,
    "time_to_first_token": 1.67
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "5",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1848,
    "completion_tokens": 59,
    "total_tokens": 1907,
    "total_time": 0.68,
    "time_to_first_token": 0.68
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
  "data": "4",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1951,
    "completion_tokens": 2,
    "total_tokens": 1953,
    "total_time": 0.66,
    "time_to_first_token": 0.66
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 1968 | 1 | 1.69 | 4.0 | 0.9969151675264335 | 0.0 |
| google | gemini-3.5-flash-lite | 1908 | 3 | 1.66 | 4.8 | null | 0.0005799 |
| groq | openai/gpt-oss-20b | 1848 | 59 | 0.69 | 5.0 | null | 0.00015629999999999998 |
| openrouter | inclusionai/ling-3.1-flash | 0 | 0 | 2.15 | "Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'inclusionai/ling-3.1-flash is temporarily rate-limited upstream. Please retry shortly, or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations', 'provider_name': 'Novita', 'is_byok': False, 'limit_source': 'upstream_provider_shared_pool', 'remedy_hint': 'Retry shortly, add your own provider key (https://openrouter.ai/settings/integrations), or route to another provider with provider routing: https://openrouter.ai/docs/features/provider-routing'}}, 'user_id': 'user_3IHIEaL9108If8k2gSzCi1zx2e3'}" | null | 0.0 |
| groq | qwen/qwen3.8-27b | 1951 | 2 | 0.68 | 4.0 | null | 0.0015688000000000002 |
