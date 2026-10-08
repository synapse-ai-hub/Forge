<p align="center">
  <img src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png" alt="Logo" width="150">
</p>

---

<h1 align="center">
  <img src="https://github.com/synapse-ai-hub/sources/raw/main/forge.png" alt="synapseForge" width="420">
</h1>

---

<p align="center">
  <a href="./LICENSE">
    <img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License: Apache 2.0" />
  </a>
  &nbsp;
  <a href="https://link.mercadopago.com.ar/synapseforge">
    <img src="https://github.com/synapse-ai-hub/sources/raw/main/badges/mercadopago-support.svg" alt="Support this project" />
  </a>
</p>

---

<h3 align="center">Forjá agentes. Distribuí inteligencia.</h3>

---

<p align="center">
  Una fábrica open-source para crear, equipar, ejecutar y distribuir agentes de IA autónomos.

---

<p align="center">
  <sub>CLI · Fábrica de Agentes · Distribución</sub>
</p>
</p>

---

```
    FORJAR             EQUIPAR           EJECUTAR         DISTRIBUIR
    ───────          ───────           ─────────        ──────────
    Agentes          Permisos          AgentLoop        Docker
    Skills           Proveedores       Tool calling     App de escritorio
    Tools            Modelos           RAG search       Zip portable
    Conocimiento                     Memoria           Listo para usar
                                     Streaming SSE
```

---

## ¿Qué es synapseForge?

La mayoría de las herramientas de agentes de IA te dan piezas y reglas. synapseForge te da la forja.

No armás un agente. Forjás un sistema.

synapseForge parte de una idea simple: los agentes deben construirse como sistemas, no armarse desde prompts.

Definí tus agentes, equipalos con skills y tools, conectalos a tus fuentes de datos, y distribuí una aplicación autónoma — desde `pip install` hasta un build distribuible (Docker, app de escritorio o zip portable).

### Una fábrica que se extiende a sí misma

Creá agentes, skills, tools y workflows a través de una entrevista asistida por LLM. synapseForge no solo ejecuta agentes — puede crear las capacidades que necesitan.

---

## Cómo funciona

### Vos construís

- **Agentes** — definí roles, permisos y comportamiento en archivos `.md`
- **Skills** — paquetes de conocimiento estructurado con referencias y frontmatter
- **Tools** — nativos (filesystem, web, shell, email) o archivos `.py` externos
- **Colecciones RAG** — subí archivos y páginas web, indexados con embeddings vectoriales
- **Workflows** — DAGs deterministas de nodos agente, tool, RAG y shell definidos en YAML

### La fábrica

La fábrica transforma esas definiciones en sistemas autónomos.

- **Motor de permisos** — deny-by-default, por agente, con wildcards y grupos
- **Agent loop** — razonamiento iterativo → tool calling → ejecución → continuación, con streaming SSE
- **Workflows** — ejecución determinista de DAGs: steps secuenciales, nodos del mismo step en paralelo, con streaming SSE
- **Memoria** — indexación persistente de conversaciones y recuperación cross-sesión
- **LLM multi-proveedor** — Ollama (local), providers cloud curados (OpenAI-compatibles + Google)
- **Integración MCP** — conectá servidores de herramientas externos vía Model Context Protocol
- **Scheduler** — ejecutá prompts en un schedule, notificá vía UI y Telegram

### Vos distribuís

```bash
synapseforge init my-project      # scaffolding con GUI
synapseforge run .                # desarrollo local
synapseforge launch -n my-app     # app de escritorio / zip portable
docker compose up --build -d      # o desplegá con Docker
```

El resultado es una distribución de aplicación autónoma. Elegí la modalidad que te convenga: un contenedor **Docker** (autocontenido o solo backend), una **app de escritorio** (Python embebido + launcher nativo) o un **zip portable** listo para entregar a quien quieras.

---

## Inicio rápido

> Actualmente disponible en [PyPI](https://pypi.org/project/synapseForge/).

```bash
pip install synapseForge

# Crear un proyecto (GUI interactiva)
synapseforge init my-project
cd my-project

# Iniciar en modo desarrollo
synapseforge run .
```

En el primer inicio, configurá una API key de cualquier proveedor cloud curado (todos con free tier) y presioná **Apply**. Ollama es opcional. La base de conocimiento requiere una key de Google, y las notas de voz requieren una key de Groq.

---

## CLI

| Comando | Qué hace |
|---------|----------|
| `synapseforge init [dir]` | Crear un proyecto con GUI interactiva |
| `synapseforge launch -p <path> -n <name>` | Construir una app de escritorio / zip de distribución portable |
| `synapseforge colors [dir]` | Editar colores del proyecto en vivo |
| `synapseforge run [dir]` | Iniciar servidores de desarrollo |
| `synapseforge update [dir]` | Actualizar el proyecto al último template (preserva datos) |

```mermaid
flowchart LR
    A["pip install synapseForge"] --> B["synapseforge init"]
    B --> C["GUI: nombre, logo, colores"]
    C --> D["Template + venv + deps"]
    D --> E["Proyecto listo"]
    E --> F["synapseforge run"]
    E --> G["synapseforge launch"]
    E --> I["docker compose up"]
    G --> H["App de escritorio / zip portable"]
    I --> J["Contenedor Docker"]
```

---

## Arquitectura

### Backend

Aplicación FastAPI con routers REST/SSE. El framework de agentes vive en `backend/agent/`: AgentLoop con tool calling nativo, registro de tools (nativos + externos + MCP), sesiones SQLite, permisos por agente, skills, RAG (ChromaDB) y memoria de largo plazo.

**Tools nativos**: `read`, `write`, `edit`, `glob`, `grep`, `list_dir`, `webfetch`, `websearch`, `shell`, `task` (delegación a sub-agentes), `skill`, `reference`, `rag`, `search_memory`, `check_email`, `send_email`, `help`.

### Workflows

Flujos deterministas definidos como archivos YAML planos (`~/.config/synapseForge/workflows/<nombre>.yaml`, un archivo por workflow). Cada workflow es una lista de nodos con `id`, `type` (`agent`, `tool`, `rag` o `run`), `step` (entero desde 1) y exactamente un nodo con `final: true`. Los nodos del mismo step corren en paralelo con barrera; los distintos steps corren en secuencia. Los nodos agente corren en una sesión hija con los permisos propios de ese agente; los nodos `run` ejecutan comandos shell estilo GitHub Actions.

El chat corre en modo **smart** (el agente decide) o con un workflow determinista seleccionado desde el panel de info del agente. Antes de ejecutar, el backend verifica que cada agente, tool y colección referenciada exista — si falta algo, responde con un mensaje amigable en vez de ejecutar. Los workflows corren con permisos de mínimo privilegio derivados de sus propios nodos. Un creador dedicado (entrevista + validación + aprobación del usuario) genera el YAML; los prompts propios pueden vivir como archivos sueltos en `workflows/prompts/`.

### Frontend

SPA React/Vite/TypeScript con Tailwind v4 y shadcn/ui. Multi-página: chat, creación de skills, gestión de RAG, documentación. Streaming SSE, visualización de tool calls, indicador de contexto, tareas programadas, uso y facturación, dashboard de métricas, toggle de Telegram.

### Proveedores

| Proveedor | Tipo | Notas |
|-----------|------|-------|
| Ollama | Local | Opcional, requiere instalación local; figura solo mientras está corriendo |
| Google | Cloud | Modelos Gemini + embeddings de RAG; free tier |
| OpenAI-compatibles | Cloud | Groq, OpenRouter, OpenAI, DeepSeek, xAI, Together AI, Fireworks AI, Cerebras, Mistral AI, Perplexity, Meta, Moonshot AI, Zhipu AI, Alibaba; free tiers |

Los providers cloud están curados en la app: cada API key se valida en vivo contra su propia API y se guarda encriptada (Fernet) en SQLite, y un proveedor figura solo mientras su key está guardada. No se necesitan variables de entorno. Los modelos vienen del catálogo models.dev cacheado en SQLite — elegí proveedor + modelo explícitamente y presioná **Apply**.

### Base de conocimiento (RAG)

ChromaDB con embeddings de Gemini (`gemini-embedding-2`) vía el proveedor Google. Subí archivos y páginas web — el contenido se extrae, chunking y se indexa para recuperación semántica. Requiere una API key de Google: sin ella, la base de conocimiento queda deshabilitada y el resto de la app funciona normalmente. Memoria de largo plazo: cada turno de conversación se indexa automáticamente y se puede buscar cross-sesión vía `search_memory`.

### Telegram

Control remoto del agente. Mandá mensajes, cambiá modelos, creá skills/tools, administrá tareas programadas — todo vía Telegram. El bot conecta al mismo flujo de chat que usa el frontend.

### Tareas programadas

Definí tareas (nombre + prompt + uno o más horarios) desde la UI o Telegram. Cada tarea se puede equipar con tools, skills y parámetros del modelo, y su prompt se puede refinar con el wizard del LLM. Al activar una tarea, el backend crea un sub-agente dedicado con esos permisos y lo ejecuta en el horario definido, notificando vía la UI y Telegram.

### Uso y facturación

En el header hay dos botones: **Uso** y **Facturación**, con los datos del mes.

**Uso** muestra el consumo del mes: solicitudes, tokens totales, gasto en USD y el desglose de tokens de entrada y salida, más el detalle por proveedor y los límites configurados.

**Facturación** muestra el gasto del mes por proveedor y modelo, con filtros por proveedor y modelo. Por cada modelo ves los tokens de entrada y salida con su tarifa y su costo, el costo total y la cantidad de solicitudes. También permite configurar límites de gasto por proveedor o por modelo: si se alcanza un límite, las solicitudes se bloquean hasta aumentarlo.

Se registra toda la actividad con modelos cloud: chat, tools, creadores, agenda, embeddings y transcripciones. Los modelos locales (Ollama) no tienen costo y no se contabilizan.

---

## Estructura del proyecto

```plaintext
synapseForge/
├─ synapseforge/              # CLI + GUIs tkinter
├─ pipeline/                  # Init (template) + Launch (forja)
├─ backend/                   # FastAPI + Framework de Agentes
│  ├─ agent/                  #   AgentLoop, Tools, Sesiones, Permisos
│  ├─ routes/                 #   Endpoints API
│  └─ telegram/               #   Bot de Telegram
├─ frontend/                  # SPA React/Vite/TypeScript
├─ template/                  # Template de proyecto (usado por init)
├─ tests/                     # Suite E2E declarativa (YAML)
└─ pyproject.toml             # Config del paquete
```

---

## Configuración del usuario

```plaintext
~/.config/synapseForge/
├─ skills/            # Skills instalados
├─ tools/             # Tools custom (.py)
├─ agents/            # Definiciones de agentes (.md)
├─ knowledge/         # Colecciones RAG (ChromaDB)
├─ mcp.json           # Servidores MCP
└─ config.yaml        # Permisos del router (opcional)
```

---

## Testing

Suite E2E declarativa en `tests/e2e/`. Escenarios YAML que manejan el backend real — chat vía SSE, llamadas API directas — validando contratos y estructura.

```bash
python -m tests.e2e.runner                # todos los escenarios
python -m tests.e2e.runner --only rag     # filtrar por nombre
```

---

## Docker

Desplegá la app como contenedor. Hay dos targets disponibles en `docker-compose.yml`:

- **`app`** — autocontenido: compila el frontend y lo sirve desde el backend en un solo contenedor.
- **`backend`** — solo backend, para despliegues separados (ej. ACI).

```bash
docker compose up --build -d
# App en http://localhost:8000
```

---

## Tech Stack

[![Python](https://github.com/synapse-ai-hub/sources/raw/main/badges/python.svg)](https://www.python.org/)
[![FastAPI](https://github.com/synapse-ai-hub/sources/raw/main/badges/fastapi.svg)](https://fastapi.tiangolo.com/)
[![SQLite](https://github.com/synapse-ai-hub/sources/raw/main/badges/sqlite.svg)](https://www.sqlite.org/)
[![ChromaDB](https://github.com/synapse-ai-hub/sources/raw/main/badges/chromadb.svg)](https://www.trychroma.com/)
[![React](https://github.com/synapse-ai-hub/sources/raw/main/badges/react.svg)](https://react.dev/)
[![TypeScript](https://github.com/synapse-ai-hub/sources/raw/main/badges/typescript.svg)](https://www.typescriptlang.org/)
[![Vite](https://github.com/synapse-ai-hub/sources/raw/main/badges/vite.svg)](https://vite.dev/)
[![Tailwind](https://github.com/synapse-ai-hub/sources/raw/main/badges/tailwind.svg)](https://tailwindcss.com/)
[![shadcn/ui](https://img.shields.io/badge/shadcn%2Fui-UI-555?labelColor=d0d4dc&logo=shadcnui&logoColor=111)](https://ui.shadcn.com/)
[![Node.js](https://github.com/synapse-ai-hub/sources/raw/main/badges/nodejs.svg)](https://nodejs.org/)
[![PyInstaller](https://github.com/synapse-ai-hub/sources/raw/main/badges/pyinstaller.svg)](https://pyinstaller.org/)
[![Docker](https://github.com/synapse-ai-hub/sources/raw/main/badges/docker.svg)](https://www.docker.com/)
[![Telegram](https://github.com/synapse-ai-hub/sources/raw/main/badges/telegram.svg)](https://telegram.org/)
[![PyPI](https://github.com/synapse-ai-hub/sources/raw/main/badges/pypi.svg)](https://pypi.org/)
[![Groq](https://github.com/synapse-ai-hub/sources/raw/main/badges/groq.svg)](https://groq.com/)
[![Google Gemini](https://github.com/synapse-ai-hub/sources/raw/main/badges/gemini.svg)](https://ai.google.dev/)
[![OpenRouter](https://github.com/synapse-ai-hub/sources/raw/main/badges/openrouter.svg)](https://openrouter.ai/)
[![Ollama](https://img.shields.io/badge/Ollama-Local-555?labelColor=d0d4dc&logo=ollama&logoColor=111)](https://ollama.com/)

---

## Apoyá este proyecto

synapseForge es free y open source. Si te resulta útil, considerá apoyar su desarrollo con una [donación vía Mercado Pago](https://link.mercadopago.com.ar/synapseforge).

---

## Licencia

Este proyecto está licenciado bajo los términos especificados en el archivo [LICENSE](./LICENSE).

---

Copyright (c) 2026 SYNAPSE AI SAS

---

*The forge is heating up...*
