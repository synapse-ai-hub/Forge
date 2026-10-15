# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 01:18:42

## Prompt exacto del modelo de decisión

````
Sos el filtro de calificación de un CRM para una empresa que vende software de gestión logística a medianas empresas de Argentina, Chile y Uruguay. El criterio de lead calificado es estricto: la empresa tiene que tener entre 50 y 500 empleados, operar en al menos dos países o mover más de 2000 envíos mensuales, tener un responsable de operaciones o logística identificado con poder de decisión, y haber mostrado intención concreta (pidió demo, preguntó precios o respondió dos o más correos). Si falta el dato de empleados pero todo lo demás cierra, se acepta igual. Si la empresa tiene menos de 50 empleados, se descarta sin excepción aunque todo lo demás cierre.

Expediente completo del lead, con fuentes cruzadas:

Empresa: LogiFreight SRL, CUIT 30-71234567-8, sede central en Rosario (Av. Pellegrini 2450), depósito propio de 8000 m2 en Mendoza (Ruta 40 km 12) y operación en Santiago de Chile mediante operador tercerizado (contrato vigente desde 2022, renovado en enero de 2026, 45 empleados del operador que NO pertenecen a LogiFreight). Actividad: distribución de alimentos no perecederos y artículos de limpieza. Antigüedad: 14 años. Facturación 2025: 9.4 millones de USD. Sitio web con 40 clientes publicados, 3 de ellos top 100 del país.

Dotación (verificar que corresponde a la empresa y no a terceros):
- LinkedIn: rango 51-200, 142 perfiles asociados, 118 con actividad en los últimos 6 meses. Hay una segunda página llamada LogiFreight Chile SpA con 12 perfiles: es la razón social del operador tercerizado, empresa distinta (CUIT chileno diferente), no suma dotación propia.
- Guía industrial de Santa Fe 2026: 120 empleados en planta Rosario y depósito Mendoza.
- Declarado por el contacto: 120 personas (85 en depósito y logística, 20 en administración y ventas, 15 en mantenimiento y sistemas).
- Prensa: una nota de 2022 informa 80 despidos en la división de transporte de larga distancia, división que la empresa vendió ese mismo año. Otro artículo menciona 45 empleados al hablar de la operación chilena, que está tercerizada.
Operación mensual promedio del último trimestre: 3400 envíos (2100 nacionales dentro de Argentina, 900 Argentina-Chile con aduana propia, 400 Chile interno con flota tercerizada). Temporada alta diciembre-marzo: 4100. Temporada baja: 2700. Reclamos por extravío: 1.8 por ciento, por encima del 1 por ciento que toleran sus clientes grandes. Perdieron una cuenta de 800 mil USD anuales en marzo por fallas de trazabilidad.

Contactos identificados con rol en la decisión:
- Martín Aguirre, jefe de operaciones, 6 años en la empresa, reporta directo al gerente general. Maneja el presupuesto de herramientas de 18000 USD anuales (partida aprobada en presupuesto 2026, con remanente disponible de 18000 porque no se gastó nada aún). Fue quien pidió la demo y define los requisitos.
- Paula Sosa, responsable de sistemas, 4 años en la empresa. Evaluó la integración técnica: su ERP es Tango versión 22 con API disponible, ya integraron otro SaaS por API en 2024 sin problemas. Aprobó la factibilidad por escrito el 22 de mayo con 6 requisitos técnicos (todos cumplidos según preventa).
- Diego Fuentes, gerente general y dueño del 60 por ciento. Participa de la decisión final, delega la evaluación en Aguirre, asistirá a la demo del 9 de junio. Historial: aprobó las últimas 3 compras de software que le propuso Aguirre.

Historial de interacciones con fechas (últimos 45 días):
- 22 de abril: apertura del correo de presentación y click en el caso de éxito de distribución (2 minutos en la página de precios según el tracking).
- 29 de abril: primera respuesta. Texto: nos interesa, necesitamos saber precios para 15 usuarios y si integran con Tango. Respondido el 30 de abril con cotización estimada de 16500 USD anuales.
- 6 de mayo: segunda respuesta con 8 preguntas técnicas (trazabilidad por lote, reportes para directorio, permisos por rol, app mobile para choferes, SLA, backups, migración desde Excel, capacitación). Respondidas por preventa el 8 de mayo; el 9 de mayo Aguirre confirma que 7 de 8 los dejan conformes y pide profundizar migración en la demo.
- 14 de mayo: asistencia al webinar de gestión de depósitos (52 de 60 minutos, 2 preguntas en el chat sobre control de vencimientos).
- 20 de mayo: tercera respuesta pidiendo demo para su equipo de 6 personas la semana del 9 de junio, con agenda propuesta por ellos: stock y vencimientos, trazabilidad del tramo Chile, reportes para el directorio, plan de migración.
- 28 de mayo: llamado de 20 minutos. Aguirre confirma presupuesto de 18000 USD, decisión antes de septiembre (el contador que maneja el FoxPro se jubila en octubre y quieren cerrar el ejercicio con el sistema nuevo), y que descartaron a dos competidores en 2025 por falta de soporte local en Chile.

Situación actual y urgencia: 14 archivos de Excel vinculados con 2 roturas de fórmulas este año (una perdió una semana de datos de stock), FoxPro con un único mantenedor que se jubila en octubre, pérdida de una cuenta grande en marzo por trazabilidad. Evaluaron a dos competidores en 2025 y los descartaron; este año solo evalúan esta propuesta.

Verificación de fuentes del CRM: los datos de dotación provienen de 4 fuentes independientes (LinkedIn, guía industrial, declaración del contacto y prensa) y 3 de ellas coinciden en el rango 118-142 para la empresa propia. La guía industrial 2026 se publica con datos auditados por la cámara empresaria de Santa Fe. El contrato del operador chileno está cargado en el CRM con vigencia y dotación del operador (45 personas) claramente marcadas como tercerizadas. La política de conteo del equipo comercial indica que el personal tercerizado no suma dotación propia bajo ningún concepto. El lead lleva 45 días en el pipeline con 9 interacciones registradas y scoring de actividad alto.

Nota de auditoría interna: el trimestre pasado se descalificaron 3 leads por contar empleados de tercerizadas como propios; desde entonces el CRM exige marcar el origen de cada dato de dotación. En este expediente cada fuente está etiquetada y la chilena figura como operador externo.

````

### Agregado para LLM tradicional

````
## Tarea
Solo respondé esta pregunta en función a lo indicado por el usuario y devolvé solo la respuesta, sin texto extra, sin argumentar.
Pregunta: El lead califica según los criterios indicados?
````

## Parámetros de modelo de decisión

```json
{
  "noul": {
    "type": "noul",
    "instructions": "El lead califica según los criterios indicados?"
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
        "noul": 0.9995121427811692
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1604,
    "completion_tokens": 1,
    "total_tokens": 1605,
    "total_time": 0.85
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
    "prompt_tokens": 1602,
    "completion_tokens": 1,
    "total_tokens": 1603,
    "total_time": 1.62,
    "time_to_first_token": 1.62
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
    "prompt_tokens": 1565,
    "completion_tokens": 202,
    "total_tokens": 1767,
    "total_time": 0.97,
    "time_to_first_token": 0.97
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "Sí, el lead califica.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1974,
    "completion_tokens": 923,
    "total_tokens": 2897,
    "total_time": 9.98,
    "time_to_first_token": 9.98
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
    "prompt_tokens": 1641,
    "completion_tokens": 2,
    "total_tokens": 1643,
    "total_time": 0.42,
    "time_to_first_token": 0.42
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 1604 | 1 | 0.85 | 1.0 | null | 0.0 |
| google | gemini-3.5-flash-lite | 1602 | 1 | 1.63 | Sí | null | 0.0004831 |
| groq | openai/gpt-oss-20b | 1565 | 202 | 0.98 | Sí. | null | 0.00017797499999999998 |
| openrouter | inclusionai/ling-3.1-flash | 1974 | 923 | 9.99 | Sí, el lead califica. | null | 0.0 |
| groq | qwen/qwen3.8-27b | 1641 | 2 | 0.42 | Sí | null | 0.0013208000000000002 |
