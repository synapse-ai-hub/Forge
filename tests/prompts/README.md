<p align="center">
  <img src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png" alt="Logo" width="150">
</p>

---

<h1 align="center">Tests Prompts — synapseForge</h1>

---

Tests de los prompts del sistema (templates Jinja), del formato de permisos de los agentes y de las reglas de seguridad. Corren contra las funciones reales de la app (`Agent.prompt`, `build_system_prompt`, `_security_block`, el registry real de tools). Sin red y sin LLM.

---

## Requisitos

- Python 3.12+
- `pytest`
- No requiere backend, LLM ni API keys. El entorno de pruebas levanta los servidores MCP configurados del usuario al crear el registry de tools.

---

## Uso

```bash
pytest tests/prompts
pytest tests/prompts -v
```

---

## Tests disponibles

| Archivo | Qué verifica |
|---------|--------------|
| `test_router_prompt.py` | El template del router con todas las tools coincide byte a byte con el texto de referencia (`golden/`); `MANDATORY` pierde la línea del TODO sin `write`; la seguridad va después de `MANDATORY`; un `config.yaml` chico y un router sin tools quitan las secciones de las tools que faltan; `shell` suma las reglas de comandos y SQL; `AGENT.md` se trata como texto plano, nunca como template; un sub-agente recibe la seguridad de sus propias tools |
| `test_prompt_templates.py` | Solo hay templates `.jinja` en `prompts/`; todos se renderizan sin caer al texto crudo; una variable faltante no corta el chat |
| `test_agent_permissions_format.py` | Los ejemplos de `create_agent` e `iterate_agent` y el archivo del agente del scheduler se leen con el formato de permisos real (`permissions.tools`, `skills`, `tasks`) |
| `test_guardrail.py` | Con el modelo de decisión habilitado el router no lleva `## Seguridad` y el decisor recibe las reglas y la pregunta; sin él, el system lleva reglas e instrucciones. Con el decisor deshabilitado no se hace ninguna llamada |

El caso «decisión habilitada» reemplaza `Agent.decision_ready` por un valor fijo, porque la llamada real necesita la API key de un proveedor de decisión.

---

## Scripts de medición

No son tests: llaman a la API real de Gemini y se corren a mano.

| Script | Qué hace |
|--------|----------|
| `compare_tokens.py` | Cuenta los tokens del system prompt del router según los permisos del `config.yaml`, con el endpoint `count_tokens` (sin generar ni escribir en la base). Requiere la API key de Google |
| `injection_check.py` | Manda ataques de prompt injection al modelo con el prompt del router con y sin la sección `## Seguridad`, y marca si obedeció o filtró el prompt. Llama al SDK directamente, sin tocar la base |

```bash
python -m tests.prompts.compare_tokens
python -m tests.prompts.injection_check
```
