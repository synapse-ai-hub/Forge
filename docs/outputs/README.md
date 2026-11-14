<p align="center">
  <img src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png" alt="Logo" width="150">
</p>

---

<h1 align="center">Salidas multimodales (imagen, audio/TTS, video) — Índice de investigación</h1>

---

# Salidas multimodales — Índice

**Tipo**: Especificación de Investigación
**Fecha**: 2026-11-14
**Rama**: `feat/outputs`
**Autores**: Builder (Equipo **synapse.ai**)
**Estado**: Para revisión — no implementa código, solo investiga y documenta

## Pregunta de investigación

¿Cómo integrar modelos que generan imágenes, TTS/audio y video, cuando hoy el sistema solo devuelve texto o JSON? El usuario debe poder elegir el tipo de salida deseado dentro de todas las posibilidades que ofrece el modelo, tomando esas posibilidades de `models.dev` (tabla que se actualiza), con llamadas vía SDK para cada opción.

## Documentos

| Archivo | Contenido |
|---|---|
| `01-estado-actual.md` | Cómo funciona hoy el repo: catálogo, `response_format`, streaming, frontend y por qué TTS/imagen no funcionan |
| `02-models-dev-outputs.md` | Qué dice `models.dev`: `modalities.output`, `type`, conteos reales por provider y ejemplos |
| `03-sdk-openai.md` | SDK `openai` 3.16.2: `chat.completions`, `images.generate`, `audio.speech`, `videos` y qué usan los providers OpenAI-compatibles |
| `04-sdk-gemini.md` | SDK `google-genai` 2.24.0: `response_modalities`, `image_config`, `speech_config`, TTS, imagen y Live API |
| `05-sdk-ollama.md` | SDK `ollama` 0.6.2: `generate`/`chat` con `width`/`height`/`steps`, `capabilities`, límites (sin TTS nativo) |
| `06-propuesta-diseno.md` | Propuesta de diseño: desplegable de salida, mapeo modelo→salidas, endpoints, render y plan por fases |

## Cómo leer

1. Empezar por `01-estado-actual.md` para entender el punto de partida.
2. Seguir por `02-models-dev-outputs.md` para ver la fuente de verdad.
3. Leer `03`, `04`, `05` para los SDKs (cada uno es independiente).
4. Terminar con `06-propuesta-diseno.md` para la decisión de diseño.

## Conclusión anticipada

- El catálogo ya guarda `modalities_output` (`text`, `image`, `audio`, `video`) pero el backend y el frontend solo usan `text`/`json`.
- Cada familia necesita una llamada SDK distinta: no alcanza con `chat.completions`.
- El desplegable de salida debe derivarse de `modalities.output` + `type` de `models.dev`, no de valores fijos.
- Fases sugeridas: 1) exponer `output_modalities` en el selector, 2) imagen vía SDK, 3) TTS/audio vía SDK, 4) video (solo donde exista), 5) render y persistencia multimodal.

---

Copyright (c) 2026 synapse.ai

---
