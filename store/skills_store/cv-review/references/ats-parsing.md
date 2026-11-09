# Reference: Parseabilidad Algorítmica y ATS (Applicant Tracking Systems)

Los sistemas ATS (*Applicant Tracking Systems*) y los parsers automatizados procesan miles de currículums antes de que lleguen a un reclutador humano. Una maquetación incorrecta destruye el emparejamiento sintáctico.

## 1. Topología de Layout y Maquetación
- **Columna Única Estricta:** Todo el contenido debe estructurarse en una sola columna vertical. Se prohíben categóricamente las tablas complejas, gráficos de barras o niveles de habilidad circulares, barras de porcentaje, iconos flotantes, imágenes, cuadros de texto independientes y diseños multicolumna (2 o 3 columnas). Los parsers leen de izquierda a derecha y se "rompen" ante estructuras en parrilla.
- **Jerarquía Tipográfica y Estándares de Fuente:** Utilizar tipografías sans-serif o serif altamente legibles por motores OCR y algoritmos de extracción (Arial, Calibri, Georgia, Times New Roman, Helvetica). Rango tipográfico de cuerpo: 10–12 pt; Títulos de sección: 14–16 pt en negrita.
- **Márgenes y Espaciado:** Márgenes uniformes entre 0.5 y 1.0 pulgada. Evitar saltos de página artificiales con caracteres invisibles o líneas divisorias gráficas complejas.
- **Extensión Normativa por Senioridad:**
  - *Junior / Recién Graduados / Profesionales < 5 años:* 1 página estricta.
  - *Mid / Senior / Directivos / Académicos:* Máximo 2 páginas. Se penaliza la expansión innecesaria si la densidad de valor cabe en una sola página.
- **Nomenclatura de Archivos:** El documento debe exportarse y nombrarse obligatoriamente bajo el estándar `Nombre_Apellido_CV.pdf` (o `.docx` si el sistema ATS lo solicita explícitamente), prohibiendo nombres informales (`cv_final_2026_v3.pdf`, `curriculum_actualizado.pdf`).

## 2. Optimización Sintáctica y Coincidencia de Keywords ($S_{\text{kw}}$ y $S_{\text{tech}}$)
- **Extracción Algorítmica:** Los sistemas evalúan la densidad de términos clave en relación con la descripción del puesto (*Job Description*).
- **Formato Dual (Acrónimo y Término Completo):** Toda competencia técnica, certificación o metodología regulatoria debe declararse incluyendo simultáneamente su denominación completa y su sigla entre paréntesis (ej. *Certified Public Accountant (CPA)*, *Retrieval-Augmented Generation (RAG)*, *Agile Project Management (APM)*) para capturar ambas variantes de búsqueda en el motor ATS.
- **Ausencia de Encabezados/Pies de Página:** Los datos de contacto y secciones críticas no deben ubicarse en los *headers* o *footers* del documento procesador de texto, ya que muchos parsers omiten esas zonas durante la extracción.
