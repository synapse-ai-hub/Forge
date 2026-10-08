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

<h3 align="center">Forge agents. Ship intelligence.</h3>

---

<p align="center">
  An open-source forge for creating, equipping, running and shipping autonomous AI agents.

---

<p align="center">
  <sub>CLI · Agent Factory · Distribution</sub>
</p>
</p>

---

```
    FORGE             EQUIP             RUN              SHIP
    ─────             ─────             ───              ────
    Agents            Permissions       AgentLoop        Docker
    Skills            Providers         Tool calling     Desktop app
    Tools             Models            RAG search       Portable zip
    Knowledge                           Memory           Ready to ship
                                        Streaming SSE
```

---

## What is synapseForge?

Most AI agent tools give you pieces and rules. synapseForge gives you the forge.

You don't assemble an agent. You forge a system.

synapseForge is designed around a simple idea: agents should be built as systems, not assembled from prompts.

Define your agents, equip them with skills and tools, connect them to your data sources, and ship a self-contained application — from `pip install` to a distributable build (Docker, desktop app or portable zip).

### A forge that can extend itself

Create agents, skills, tools and workflows through an LLM-assisted interview. synapseForge doesn't just run agents — it can create the capabilities they need.

---

## How it works

### You build

- **Agents** — define roles, permissions and behavior in `.md` files
- **Skills** — structured knowledge packages with references and frontmatter
- **Tools** — native (filesystem, web, shell, email) or external `.py` files
- **RAG collections** — upload files and web pages, indexed with vector embeddings
- **Workflows** — deterministic DAGs of agent, tool, RAG and shell nodes defined in YAML

### The Forge

The Forge turns those definitions into autonomous systems.

- **Permission engine** — deny-by-default, per-agent, with wildcards and groups
- **Agent loop** — iterative reasoning → tool calling → execution → continuation, with streaming SSE
- **Workflows** — deterministic DAG execution: sequential steps, same-step nodes in parallel, with streaming SSE
- **Memory** — persistent conversation indexing and cross-session retrieval
- **Multi-provider LLM** — Ollama (local), curated cloud providers (OpenAI-compatible + Google)
- **MCP integration** — connect external tool servers via the Model Context Protocol
- **Scheduler** — run prompts on a schedule, notify via UI and Telegram

### You ship

```bash
synapseforge init my-project      # scaffold with GUI
synapseforge run .                # develop locally
synapseforge launch -n my-app     # build a desktop app / portable zip
docker compose up --build -d      # or deploy with Docker
```

The result is a self-contained application distribution. Choose the modality that fits: a **Docker** container (autocontained or backend-only), a **desktop app** (embedded Python + native launcher), or a **portable zip** ready to hand to anyone.

---

## Quick start

> Currently available on [PyPI](https://pypi.org/project/synapseForge/).

```bash
pip install synapseForge

# Create a project (interactive GUI)
synapseforge init my-project
cd my-project

# Start in development mode
synapseforge run .
```

On first launch, configure an API key from any curated cloud provider (all offer free tiers) and press **Apply**. Ollama is optional. The knowledge base requires a Google key, and voice notes require a Groq key.

---

## CLI

| Command | What it does |
|---------|-------------|
| `synapseforge init [dir]` | Create a project with interactive GUI |
| `synapseforge launch -p <path> -n <name>` | Build a desktop app / portable distribution zip |
| `synapseforge colors [dir]` | Edit project colors live |
| `synapseforge run [dir]` | Start development servers |
| `synapseforge update [dir]` | Update project to latest template (preserves data) |

```mermaid
flowchart LR
    A["pip install synapseForge"] --> B["synapseforge init"]
    B --> C["GUI: name, logo, colors"]
    C --> D["Template + venv + deps"]
    D --> E["Project ready"]
    E --> F["synapseforge run"]
    E --> G["synapseforge launch"]
    E --> I["docker compose up"]
    G --> H["Desktop app / portable zip"]
    I --> J["Docker container"]
```

---

## Architecture

### Backend

FastAPI application with REST/SSE routers. The agent framework lives in `backend/agent/`: AgentLoop with native tool calling, tools registry (native + external + MCP), SQLite sessions, per-agent permissions, skills, RAG (ChromaDB) and long-term memory.

**Native tools**: `read`, `write`, `edit`, `glob`, `grep`, `list_dir`, `webfetch`, `websearch`, `shell`, `task` (sub-agent delegation), `skill`, `reference`, `rag`, `search_memory`, `check_email`, `send_email`, `help`.

### Workflows

Deterministic flows defined as flat YAML files (`~/.config/synapseForge/workflows/<name>.yaml`, one file per workflow). Each workflow is a list of nodes with `id`, `type` (`agent`, `tool`, `rag` or `run`), `step` (integer from 1) and exactly one node with `final: true`. Nodes in the same step run in parallel with a barrier; different steps run sequentially. Agent nodes run in a child session with that agent's own permissions; `run` nodes execute shell commands GitHub-Actions style.

The chat runs in **smart** mode (the agent decides) or with one deterministic workflow selected from the agent info panel. Before running, the backend verifies that every referenced agent, tool and collection exists — if something is missing, it answers with a friendly message instead of executing. Workflows run under least-privilege permissions derived from their own nodes. A dedicated creator (interview + validation + user approval) generates the YAML; custom prompts can live as loose files in `workflows/prompts/`.

### Frontend

React/Vite/TypeScript SPA with Tailwind v4 and shadcn/ui. Multi-page: chat, skill creation, RAG management, docs. SSE streaming, tool call visualization, context window gauge, scheduled tasks, usage and billing, metrics dashboard, Telegram toggle.

### Providers

| Provider | Type | Notes |
|----------|------|-------|
| Ollama | Local | Optional, requires local install; listed only while running |
| Google | Cloud | Gemini models + RAG embeddings; free tier |
| OpenAI-compatible | Cloud | Groq, OpenRouter, OpenAI, DeepSeek, xAI, Together AI, Fireworks AI, Cerebras, Mistral AI, Perplexity, Meta, Moonshot AI, Zhipu AI, Alibaba; free tiers |

Cloud providers are curated in-app: each API key is validated live against its own API and stored encrypted (Fernet) in SQLite, and a provider is listed only while its key is saved. No environment variables needed. Models come from the models.dev catalog cached in SQLite — select provider + model explicitly and press **Apply**.

### Knowledge base (RAG)

ChromaDB with Gemini embeddings (`gemini-embedding-2`) via the Google provider. Upload files and web pages — content is extracted, chunked and indexed for semantic retrieval. Requires a Google API key: without it, the knowledge base stays disabled and everything else runs normally. Long-term memory: every conversation turn is automatically indexed and searchable across sessions via `search_memory`.

### Telegram

Remote control for the agent. Send messages, switch models, create skills/tools, manage scheduled tasks — all through Telegram. The bot bridges to the same chat flow the frontend uses.

### Scheduled tasks

Define tasks (name + prompt + one or more schedules) from the UI or Telegram. Each task can be equipped with tools, skills and model parameters, and its prompt can be refined with the LLM wizard. Activating a task creates a dedicated sub-agent with those permissions; the backend runs it on schedule and notifies via the UI and Telegram.

### Usage and billing

The header has two buttons: **Usage** and **Billing**, with the current month's data.

**Usage** shows the month's consumption: requests, total tokens, spend in USD and the input/output token breakdown, plus per-provider detail and configured limits.

**Billing** shows the month's spend per provider and model, with provider and model filters. Each model shows input and output tokens with their rate and cost, total cost and request count. It also configures spend limits per provider or model: when a limit is reached, requests are blocked until it is raised.

All cloud model activity is tracked: chat, tools, creators, agenda, embeddings and transcriptions. Local models (Ollama) have no cost and are not counted.

---

## Project structure

```plaintext
synapseForge/
├─ synapseforge/              # CLI + tkinter GUIs
├─ pipeline/                  # Init (template) + Launch (forge)
├─ backend/                   # FastAPI + Agent Framework
│  ├─ agent/                  #   AgentLoop, Tools, Sessions, Permissions
│  ├─ routes/                 #   API endpoints
│  └─ telegram/               #   Telegram bot
├─ frontend/                  # React/Vite/TypeScript SPA
├─ template/                  # Project template (used by init)
├─ tests/                     # E2E declarative suite (YAML)
└─ pyproject.toml             # Package config
```

---

## User configuration

```plaintext
~/.config/synapseForge/
├─ skills/            # Installed skills
├─ tools/             # Custom tools (.py)
├─ agents/            # Agent definitions (.md)
├─ knowledge/         # RAG collections (ChromaDB)
├─ mcp.json           # MCP servers
└─ config.yaml        # Router permissions (optional)
```

---

## Testing

Declarative E2E suite in `tests/e2e/`. YAML scenarios drive the real backend — chat via SSE, direct API calls — asserting on contracts and structure.

```bash
python -m tests.e2e.runner                # all scenarios
python -m tests.e2e.runner --only rag     # filter by name
```

---

## Docker

Deploy the app as a container. Two targets are available in `docker-compose.yml`:

- **`app`** — autocontained: builds the frontend and serves it from the backend in a single container.
- **`backend`** — backend only, for separated deployments (e.g. ACI).

```bash
docker compose up --build -d
# App at http://localhost:8000
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

## Support this project

synapseForge is free and open source. If you find it useful, consider supporting its development with a [donation via Mercado Pago](https://link.mercadopago.com.ar/synapseforge).

---

## License

This project is licensed under the terms specified in the [LICENSE](./LICENSE) file.

---

Copyright (c) 2026 SYNAPSE AI SAS

---

*The forge is heating up...*
