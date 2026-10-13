# Decision Probe

- provider: openrouter
- model: inception/mercury-decide:free
- timestamp: 2026-10-11 01:42:11

## Prompt exacto del modelo de decisión

````
Sos el validador de importaciones masivas al ERP. Un archivo se importa solo si tiene exactamente las 8 columnas esperadas en el orden correcto, no trae filas duplicadas por clave (código de producto), todos los precios son números positivos con máximo 2 decimales, y ninguna fila supera los 200 caracteres en el campo descripción. Un solo error bloquea toda la importación.

Archivo lista_precios_junio.csv, informe del pre-validador (1240 filas de datos más encabezado):
- Encabezado: codigo,descripcion,precio_costo,precio_venta,stock,proveedor,moneda,fecha_vigencia. Son las 8 columnas esperadas en el orden esperado, sin columnas extra ni faltantes, sin BOM ni caracteres raros.
- Clave: el código CH-8821 aparece en la fila 44 (precio de venta 1520.50, stock 30) y en la fila 1107 (precio de venta 1520.05, stock 12). El resto de los 1238 códigos son únicos. El área comercial aclara que la fila 1107 era la corrección de un error de tipeo de la fila 44 y que la válida es la 1107, pero ambas quedaron en el archivo.
- Precios: los 2480 valores (costo y venta) son positivos, con 2 decimales como máximo. El más alto es 89999.99, el más bajo 0.50. Margen venta sobre costo siempre positivo.
- Descripciones: la más larga tiene 187 caracteres (fila 902), el promedio es 64. Ninguna supera los 200.
- Moneda: 1237 filas en ARS y 3 en USD, ambas aceptadas por la columna. Fechas todas en formato ISO dentro del trimestre vigente.
- Stock: todos enteros no negativos. Proveedores: los 18 códigos existen en el maestro.
- El pre-validador marcó exactamente 1 observación: el duplicado de CH-8821. Todo lo demás está verde.

Contexto del proceso de importación y del archivo:

El archivo lo generó el área comercial el 2 de junio a las 18:40 desde la planilla maestra de precios que mantienen en Google Sheets. Es la lista de precios del tercer trimestre y debe estar cargada antes del 10 de junio porque el 11 arranca la facturación con los precios nuevos. La importación la ejecuta el responsable de administración (un solo usuario con permiso) y una vez importada no se puede deshacer en bloque: hay que corregir fila por fila desde el panel. El trimestre pasado una importación con 3 duplicados generó 3 semanas de reclamos de clientes por precios distintos para el mismo producto según la sucursal que facturaba.

Detalle de las filas observadas: la fila 44 trae CH-8821 con precio de venta 1520.50 y stock 30; la fila 1107 trae CH-8821 con precio de venta 1520.05 y stock 12. La diferencia de 45 centavos parece menor pero el producto vende 400 unidades mensuales y la diferencia anual supera los 2000 USD. El área comercial dice por email que la válida es la 1107, pero el email no está adjunto al expediente de importación y el procedimiento exige que las correcciones vengan en el archivo, no por fuera. El responsable de administración no tiene criterio para elegir entre las dos filas y pide definición escrita.

Muestras de otras filas: la fila 1 trae el producto AA-0001 con descripción de 12 caracteres; la fila 902 trae la descripción más larga con 187 caracteres (un kit con 14 componentes detallados); la fila 1240 cierra con un producto nuevo sin stock inicial. Las 3 filas en USD corresponden a productos importados con precio atado al dólar oficial del día de vigencia. Los 18 proveedores del archivo existen en el maestro y 4 de ellos cambiaron su código interno este año, pero los códigos del archivo son los vigentes.

Historial de importaciones: en los últimos 12 meses se intentaron 9 importaciones de listas de precios. 5 pasaron limpias al primer intento, 2 fueron rechazadas por columnas desordenadas, 1 por precios con 3 decimales y 1 por descripciones de más de 200 caracteres. En todos los casos de rechazo el archivo se devolvió al área comercial y se reimportó corregido en 48 horas promedio. Nunca se importó un archivo con observaciones pendientes: la política del ERP es todo o nada y no existe la importación parcial.

Circuito de aprobación: el pre-validador corre automáticamente al subir el archivo y genera el informe que se muestra arriba. Si el informe tiene observaciones, el responsable puede devolverlo o elevarlo al gerente de administración con una nota de excepción. El gerente puede autorizar la importación con observaciones solo si firma una excepción por escrito asumiendo la corrección posterior fila por fila. Este mes el gerente ya firmó 2 excepciones por archivos de stock y dijo que no va a firmar más hasta fin de trimestre.

Impacto de cada alternativa: si se importa con el duplicado, el ERP toma la primera ocurrencia (fila 44) e ignora la segunda, quedando el precio viejo de 1520.50. Si se devuelve, la lista del tercer trimestre no entra antes del 11 y la facturación arranca con precios del trimestre anterior, lo que comercial estima en 8000 USD de margen perdido en la primera semana. El área comercial presiona para importar ya y corregir después; administración responde que la corrección fila por fila de 1240 filas para encontrar el duplicado no es viable y que el error quedaría hasta la próxima lista.

Datos del sistema: la importación corre en horario nocturno por ventana de mantenimiento (2 a 4 de la mañana) y bloquea la tabla de precios durante 40 minutos. Si falla a mitad de camino hace rollback completo y deja la tabla anterior intacta. El log de la última importación exitosa muestra 1180 filas en 32 minutos sin errores.

Nota del procedimiento: la excepción por escrito del gerente debe detallar qué filas se corrigen, quién las corrige y en qué plazo, con seguimiento semanal hasta cerrar. Las 2 excepciones firmadas este mes fueron por archivos de stock con 5 y 8 filas observadas, corregidas en 3 y 5 días respectivamente. Una excepción por un duplicado en lista de precios no tiene precedente este año.

Precedente de 2025: en septiembre del año pasado se importó una lista con 2 duplicados por excepción verbal (sin firma) y los precios quedaron 4 meses hasta la lista siguiente, con 12000 USD de margen perdido y 9 reclamos. Desde entonces el procedimiento exige la firma escrita. El gerente que firmaba antes renunció en abril y el actual dijo que no firma excepciones sin el detalle fila por fila.

````

### Agregado para LLM tradicional

````
## Tarea
Solo respondé esta pregunta en función a lo indicado por el usuario y devolvé solo la respuesta, sin texto extra, sin argumentar.
Pregunta: Se importa el archivo?
````

## Parámetros de modelo de decisión

```json
{
  "noul": {
    "type": "noul",
    "instructions": "Se importa el archivo?"
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
        "noul": 0.00021654394930761332
      }
    },
    "model": "inception/mercury-decide-20260930",
    "provider": "openrouter"
  },
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1585,
    "completion_tokens": 1,
    "total_tokens": 1586,
    "total_time": 0.76
  }
}
```

## Respuesta gemini-3.5-flash-lite

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "No",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1623,
    "completion_tokens": 1,
    "total_tokens": 1624,
    "total_time": 1.1,
    "time_to_first_token": 1.1
  }
}
```

## Respuesta openai/gpt-oss-20b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "No.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1584,
    "completion_tokens": 113,
    "total_tokens": 1697,
    "total_time": 0.54,
    "time_to_first_token": 0.54
  }
}
```

## Respuesta inclusionai/ling-3.1-flash

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "No.",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 2008,
    "completion_tokens": 995,
    "total_tokens": 3003,
    "total_time": 12.58,
    "time_to_first_token": 12.58
  }
}
```

## Respuesta qwen/qwen3.8-27b

```json
{
  "status": "success",
  "message": "Proceso ok.",
  "data": "No",
  "tool_calls": null,
  "usage": {
    "prompt_tokens": 1650,
    "completion_tokens": 2,
    "total_tokens": 1652,
    "total_time": 0.42,
    "time_to_first_token": 0.42
  }
}
```

## Tabla comparativa

| proveedor | modelo | tokens_entrada | tokens_salida | tiempo | decision | confianza | gasto_usd |
|---|---|---|---|---|---|---|---|
| openrouter | inception/mercury-decide:free | 1585 | 1 | 0.77 | 0.0 | null | 0.0 |
| google | gemini-3.5-flash-lite | 1623 | 1 | 1.1 | No | null | 0.0004894 |
| groq | openai/gpt-oss-20b | 1584 | 113 | 0.55 | No. | null | 0.0001527 |
| openrouter | inclusionai/ling-3.1-flash | 2008 | 995 | 12.59 | No. | null | 0.0 |
| groq | qwen/qwen3.8-27b | 1650 | 2 | 0.42 | No | null | 0.001328 |
