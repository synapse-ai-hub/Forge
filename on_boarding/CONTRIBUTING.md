<p align="center">
  <img src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png" alt="Logo" width="150">
</p>

---

# Contributing

Gracias por contribuir a `synapseForge`. Este documento resume las normas y buenas prácticas para contribuir de manera ordenada.

---

## Áreas donde podés contribuir

### Providers

El sistema soporta múltiples proveedores de LLM (Ollama local y providers cloud curados como base). Para agregar un nuevo proveedor:

1. Revisar `backend/agent/agent.py` (clase `Agent`) y `backend/agent/llm/` — ahí están los métodos de conexión (`completion.py`, `streaming.py`, `api_type.py`).
2. Agregar el nuevo provider siguiendo la misma interfaz: recibe `model`, `messages` y devuelve streaming o completion.
3. Registrar el provider en `PROVIDER_REGISTRY` de `backend/agent/utils/provider_keys.py` (label, tipo de API, URL base y URL de la key). Los modelos salen del catálogo de models.dev que sincroniza `backend/agent/utils/model_catalog.py`.
4. Para providers locales, agregar la resolución de modelos en `backend/agent/utils/model_resolver.py`.
5. El frontend (`frontend/src/services/configService.ts`) obtiene la lista automáticamente desde `GET /api/config/providers`.

### Skills

- Crear nuevas skills siguiendo el formato `SKILL.md` con frontmatter YAML (`name`, `description` y, opcionalmente, `triggers`).
- Mejorar los prompts de creación en `backend/agent/prompts/create_skill.jinja` e `iterate_skill.jinja`.
- Agregar references/ con material de consulta.

### Tools

- Desarrollar tools externas en Python (archivo `.py` autocontenido con `async def`, type hints, try/except).
- Revisar la sección Tools de `frontend/public/docs.html` y `backend/agent/README.md` para el formato exacto.
- Las tools se instalan en `~/.config/synapseForge/tools/`.

### Agentes

- Crear configuraciones de agente en `~/.config/synapseForge/agents/` con frontmatter YAML + prompt personalizado.
- Agregar nuevas features al sistema de permisos (`permissions.tools`, `permissions.skills` y `permissions.tasks`, con `allow` o `deny`).

### RAG / Vector store

- Mejorar el wrapper de ChromaDB (adaptable a otros motores).
- Agregar soporte para más formatos de archivo en la ingesta RAG.
- Optimizar chunking y estrategias de búsqueda.

### Frontend

- Agregar nuevos componentes, mejorar el panel de creación.
- Mejorar la visualización de métricas, herramientas y skills.
- Nuevos themes y paletas de color.

### MCP

- Soportar nuevos transportes o mejorar el descubrimiento y el health check en `backend/agent/utils/mcp_helper.py`.

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
Tipo: descripción breve en español e imperativo

Ejemplos:
Feat: agregar soporte para provider Anthropic
Fix: corregir parseo de frontmatter en skills
Chore: actualizar dependencias
```

Los tipos válidos son `Fix:`, `Feat:`, `Chore:`, `Docs:`, `Refactor:` y `Update:` (ver [GIT_WORKFLOW.md](./GIT_WORKFLOW.md)).

---

## Revisión y merge

- Pedir al menos 1 revisor.
- Resolver comentarios en el PR antes de mergear.
- Mantener el PR pequeño y enfocado.

---

## Código y pruebas

- Añadir tests para cambios críticos. Los tests nuevos se escriben con `pytest` y pegan a las funciones y endpoints reales (por ejemplo `pytest tests/prompts tests/mcp tests/loop`).
- Mantener el código comentado y legible.
- Respetar las convenciones del proyecto: `snake_case` en Python, `camelCase` en TypeScript, imports absolutos.

---

Autor: synapse.ai  
Última actualización: 2026-10-17
