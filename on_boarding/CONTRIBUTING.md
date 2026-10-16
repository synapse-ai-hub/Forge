<p align="center">
  <img src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png" alt="Logo" width="150">
</p>

---

# Contributing

Gracias por contribuir a `<repo>nombre_repo</repo>`. Este documento resume las normas y buenas prácticas para contribuir de manera ordenada.

---

## Áreas donde podés contribuir

### Providers

El sistema soporta múltiples proveedores de LLM (Ollama local y providers cloud curados como base). Para agregar un nuevo proveedor:

1. Revisar `backend/agent/agent.py` — ahí está la clase `Agent` con los métodos de conexión.
2. Agregar el nuevo provider siguiendo la misma interfaz: recibe `model`, `messages` y devuelve streaming o completion.
3. Agregar el provider al selector en `backend/routes/config/providers.py` (lista de proveedores).
4. Agregar la lógica de resolución de modelos en `backend/agent/utils/model_resolver.py`.
5. El frontend (`frontend/src/services/configService.ts`) obtiene la lista automáticamente desde `GET /api/config/providers`.

### Skills

- Crear nuevas skills siguiendo el formato `SKILL.md` con frontmatter YAML (`name`, `description`, `metadata.triggers`).
- Mejorar los prompts de creación en `backend/agent/prompts/create_skill.md` e `iterate_skill.md`.
- Agregar references/ con material de consulta.

### Tools

- Desarrollar tools externas en Python (archivo `.py` autocontenido con `async def`, type hints, try/except).
- Revisar `docs/tools/guia-creacion-tools.md` para el formato exacto.
- Las tools se instalan en `~/.config/synapseForge/tools/`.

### Agentes

- Crear configuraciones de agente en `~/.config/synapseForge/agents/` con frontmatter YAML + prompt personalizado.
- Agregar nuevas features al sistema de permisos (tool/skill/task allow/deny/ask).

### RAG / Vector store

- Mejorar el wrapper de ChromaDB (adaptable a otros motores).
- Agregar soporte para más formatos de archivo en la ingesta RAG.
- Optimizar chunking y estrategias de búsqueda.

### Frontend

- Agregar nuevos componentes, mejorar el panel de creación.
- Mejorar la visualización de métricas, herramientas y skills.
- Nuevos themes y paletas de color.

---

## Normas básicas

- Trabajar en ramas con nombres descriptivos: `feature/...`, `fix/...`, `chore/...`.
- Mantener commits atómicos y mensajes en imperativo.
- Antes de abrir un PR, actualizar tu rama con `main` y ejecutar tests/linter.
- Al abrir PR en GitHub, usar el template correspondiente según el tipo de cambio:
  - General: `?template=general.md`
  - Feature: `?template=feature.md`
  - Fix: `?template=fix.md`

---

## Estilo de commits

Usar un formato simple y claro:

```
Tipo: descripción breve

Ejemplos:
feat: agregar soporte para provider Anthropic
fix: corregir parseo de frontmatter en skills
chore: actualizar dependencias
```

---

## Revisión y merge

- Pedir al menos 1 revisor.
- Resolver comentarios en el PR antes de mergear.
- Mantener el PR pequeño y enfocado.

---

## Código y pruebas

- Añadir tests para cambios críticos.
- Mantener el código comentado y legible.
- Respetar las convenciones del proyecto: `snake_case` en Python, `camelCase` en TypeScript, imports absolutos.

---

Autor: synapse.ai 
Última actualización: 2026-07-27

