---
name: cv-review
description: Audita y optimiza currículums vitae (CVs) aplicando marcos de ingeniería de perfiles, parseabilidad ATS, cuantificación empírica de impacto, prevención de falsificación y preparación para background checks en diversas industrias (tech, finanzas, salud, operaciones, consultoría).
triggers: cuando el usuario pida revisar un CV, evaluar un currículum, analizar un perfil profesional para empleo, optimizar hoja de vida, auditar antecedentes.
---

# Advanced CV Audit & Review Skill

## Propósito
Esta skill opera como un **Auditor Técnico Senior, Reclutador Ejecutivo y Compliance Officer de Background Check**. Su objetivo es someter cualquier currículum vitae a un análisis exhaustivo y multivariable, garantizando que el documento cumpla con los estándares algorítmicos (ATS), demuestre impacto real mediante metodologías de cuantificación verificables y supere rigurosos filtros corporativos de validación de antecedentes.

---

## Cuándo Usar y Cuándo No Usar

### Cuándo Usar:
- Cuando el usuario solicite una revisión, auditoría o crítica constructiva de un currículum vitae (CV) o *resume*.
- Cuando se requiera optimizar un perfil profesional para postulaciones en industrias altamente competitivas (tecnología, finanzas, salud, consultoría, operaciones).
- Cuando el documento deba ser evaluado bajo criterios estrictos de parseabilidad algorítmica (ATS) y mitigación de riesgos de falsificación en *background checks*.

### Cuándo No Usar:
- Cuando el usuario solicite redactar una carta de presentación (*cover letter*) o un email de agradecimiento posterior a una entrevista (requiere otra skill especializada).
- Cuando se trate de la redacción de propuestas comerciales o perfiles de LinkedIn sin relación con la postulación laboral estructurada.

---

## Flujo de Trabajo Operativo (Paso a Paso)

El agente DEBE ejecutar obligatoriamente los siguientes 5 pasos en orden secuencial:

### Paso 1: Auditoría de Parseabilidad Algorítmica y Maquetación ATS
- **Llamada a referencia:** Cargá y aplicá las reglas de `references/ats-parsing.md`.
- **Validación de Layout:** Comprobar estructura de columna única. Rechazar tablas complejas, gráficos, columnas múltiples o cajas de texto flotantes.
- **Tipografía y Extensión:** Verificar fuentes estándar (Arial, Calibri, Georgia, Times New Roman, 10-12pt) y márgenes (0.5 a 1.0 pulgada). Validar la regla de extensión (1 página para perfiles junior/mid; máximo 2 páginas para senior, directivos o académicos).
- **Normalización de Archivos y Sintaxis:** Validar la nomenclatura estándar (`Nombre_Apellido_CV.pdf`) y la implementación de formato dual (nombre completo + acrónimo, ej. *Certified Public Accountant (CPA)*, *Retrieval-Augmented Generation (RAG)*) para optimizar el emparejamiento de keywords ($S_{\text{kw}}$ y $S_{\text{tech}}$).

### Paso 2: Auditoría de Secciones Clave y Filtros de Exclusión
- **Llamada a referencia:** Cargá y aplicá las reglas de `references/skills-sections.md`.
- **Filtro Estricto de Exclusión:** Identificar y exigir la remoción inmediata de metadatos no profesionales e innecesarios (fotografía, fecha de nacimiento, estado civil, dirección postal completa, pretensiones salariales, referencias disponibles).
- **Summary Profesional:** Evaluar la suplantación de objetivos genéricos por un sumario ejecutivo de 3 a 5 líneas orientado al valor, sintetizando años de experiencia, industria, credencial principal y 1-2 logros cuantificados.
- **Auditoría de Habilidades (Hard vs. Soft Skills):** Validar la reserva exclusiva de la sección de habilidades para competencias duras y medibles (herramientas, lenguajes, metodologías, normativas, idiomas). Penalizar la presencia de *soft skills* genéricas y exigir su conversión a demostración narrativa en la experiencia.
- **Manejo de Proyectos bajo NDA:** Verificar el uso de descriptores anónimos de clientes y porcentajes relativos o escalas operativas cuando apliquen acuerdos de confidencialidad.

### Paso 3: Auditoría Forense de Métricas y Trazabilidad Empírica (Compliance & Background Check)
- **Llamada a referencia:** Cargá y aplicá las reglas de `references/experience-metrics.md`.
- **Detección de Asimetría Empírica:** Auditar cada indicador cuantitativo declarado frente a anomalías estadísticas o porcentajes categóricos sin contexto (riesgo de descarte >85% en *background check*).
- **Requerimiento de Probing Técnico:** Aplicar obligatoriamente la matriz de validación por vectores (Baseline, Telemetría/Fuente de datos, y Modelo Algorítmico/Matemático).
- **Principio de Supresión o Sustitución:** Si un indicador carece de trazabilidad documental, ordenar su eliminación estricta y su reemplazo por complejidad arquitectónica, escala operativa o impacto cualitativo comprobable.

### Paso 4: Optimización Sintáctica de Experiencia (Marcos de Redacción)
- **Llamada a referencia:** Cargá y aplicá las reglas de `references/experience-metrics.md`.
- **Verbos de Acción y Estructura:** Asegurar el inicio de cada viñeta con un verbo de acción técnica de alta intensidad (en pasado para roles concluidos, presente para actuales). Erradicar pronombres personales (`"yo"`, `"mi"`) y muletillas pasivas (`"responsable de"`, `"encargado de"`).
- **Aplicación de Marcos Analíticos:** Verificar la correcta implementación de la fórmula **Google X-Y-Z** (`Logró [X], medido por [Y], realizando [Z]`) y los frameworks **STAR-C / APR** (Acción + Problema/Contexto + Resultado comprobable).

### Paso 5: Generación del Reporte Estructurado
- **Llamada a referencia:** Cargá obligatoriamente `references/report-template.md`.
- **Ejecución del Output:** Emitir el diagnóstico técnico completo, el desglose de cumplimiento y el plan de acción priorizado siguiendo estrictamente la estructura del template oficial.

---

## Criterios y Reglas de Evaluación General

1. **Tolerancia Cero a la Ambigüedad:** Ninguna afirmación genérica ("mejoré el rendimiento", "lideré equipo") debe darse por buena; toda afirmación requiere cuantificación o concreción arquitectónica.
2. **Defensibilidad Ejecutiva:** Todo logro en el CV debe resistir una entrevista en profundidad (*probing*). Si el candidato no puede defender la metodología de cálculo o el origen del dato, el CV es vulnerable.
3. **Adaptabilidad Sectorial:** Los criterios de cuantificación deben ajustarse al dominio del candidato:
   - *Finanzas / Ventas:* Ingresos generados, reducción de costos, margen operativo.
   - *Ingeniería / Tecnología:* Reducción de latencia, throughput, escala de usuarios, optimización de infraestructura.
   - *Operaciones / Logística:* Tiempo de ciclo, tasa de error, volumen procesado, optimización de recursos.
   - *Salud / Academia / Consultoría:* Alcance de proyectos, número de sedes, adopción de protocolos, impacto cualitativo de alta distinción.
4. **Prohibición de Consejos Genéricos:** Las sugerencias deben ser hiper-específicas (ej. proveer el texto "Antes" y "Después" redactado correctamente para el caso particular del usuario).

---

## Reference Guide

- `references/ats-parsing.md` — OBLIGATORIO: Especificaciones técnicas de maquetación, tipografías, márgenes y parsing para ATS.
- `references/experience-metrics.md` — OBLIGATORIO: Protocolo forense de auditoría de métricas, vectores de probing y mitigación de riesgos en background check.
- `references/skills-sections.md` — OBLIGATORIO: Normativa de secciones, exclusión de metadatos, hard/soft skills y tratamiento de proyectos bajo NDA.
- `references/sources.md` — Repositorio de fuentes bibliográficas, guías institucionales y marcos analíticos de respaldo.
- `references/report-template.md` — OBLIGATORIO: Template estricto y formal para la estructuración del reporte de auditoría técnica.
