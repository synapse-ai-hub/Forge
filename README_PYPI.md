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

<h3 align="center">CLI to scaffold and ship full-stack AI agent projects (FastAPI + React/Vite/TS)</h3>

---

## Description

**synapseForge** is a PyPI package that provides a CLI to scaffold full-stack AI agent projects from scratch — backend (FastAPI), frontend (React/Vite/TypeScript), branding (logo, .ico, color palette), dependencies, and a self-contained distribution build.

The generated project includes:

- **Agent Framework**: AgentLoop with native tool calling, tools registry (native + external + MCP), sessions (SQLite WAL), per-agent permissions, skills and sub-agent delegation
- **Multi-provider LLM**: Ollama (local) plus curated cloud providers — 14 OpenAI-compatible (Groq, OpenRouter, OpenAI, DeepSeek, xAI, Together AI, Fireworks AI, Cerebras, Mistral AI, Perplexity, Meta, Moonshot AI, Zhipu AI, Alibaba) + Google (Gemini models and embeddings) — cloud API keys validated live against each provider's API and stored encrypted in SQLite
- **RAG knowledge base**: ChromaDB vector collections with Gemini embeddings (`gemini-embedding-2`) via the Google provider; upload files and web pages, cosine-similarity search
- **LLM-assisted creation**: standalone interfaces to generate skills, tools, agents and workflows through an iterative interview (with real tools enabled), with ephemeral cloud model selection per task
- **Scheduled tasks**: user-defined tasks (name + description + time + weekdays) managed from the header Agenda or via Telegram; each task can be equipped with tools, skills and model parameters, and its prompt refined with the LLM wizard. Activating a task creates a dedicated sub-agent with those permissions; the backend runs it on schedule and notifies the result in the UI bell and on Telegram
- **Telegram bot**: remote control that bridges messages to the agent through the web UI (commands, voice transcription, attachments)
- **Frontend**: chat with SSE streaming, config panel, sessions sidebar, context-window gauge, usage and billing dialogs, metrics dashboard
- **Docker** support and **desktop app mode** (heartbeat watchdog + shutdown endpoint)

---

## Installation

```bash
pip install synapseForge
```

Package dependencies: `Pillow` (.ico generation) — everything else is project-level.

## Requirements

| Tool | Version | Needed for |
|------|---------|------------|
| Python | 3.12+ | `init`, `launch`, `run`, `colors`, `update` |
| Node.js | 20+ | `launch` (frontend build), `run` (dev server) |
| Docker | 20+ | Optional: containerized deployment |

**LLM provider (required):** at least one curated cloud API key is needed to use the app — all curated providers offer free tiers. Keys are loaded from the in-app config panel (**Providers**) on first launch; nothing else has to be installed.

> The **knowledge base** feature specifically requires a **Google** key (free tier works). Without it, that section stays disabled — everything else runs normally. Voice notes on Telegram are transcribed with Groq Whisper and require a Groq key.

**Ollama (optional):** local models are supported but not required. Install Ollama only if you want to run models locally.

---

## Quick Start

### Create a new project

```bash
synapseforge init my-project
cd my-project
```

Interactive GUI pipeline (project data, logos, colors).

### Run in development

```bash
synapseforge run ./my-project
```

Requires the project venv to be activated (`VIRTUAL_ENV`). Starts backend + frontend dev servers and opens the browser. Ctrl+C stops both.

### Build a distributable

```bash
synapseforge launch -p ./my-project -n "MyApp"
```

Builds the frontend, bundles embedded Python and packages everything into a self-contained desktop app / zip ready to deliver. By default the backend ships as `.py` sources; pass `-c` / `--compile` to compile it to `.pyc`. Other options: `--skip-frontend`, `--no-embed`.

Alternatively, deploy the project as a container with the bundled Docker setup (`docker compose up --build -d`), which serves the built frontend from the backend in a single image.

### Update to latest template

```bash
synapseforge update ./my-project
```

Backs up the entire project (including `agent.db` and `config/replace.json`), downloads the latest template, and restores your data. If anything fails, the project is automatically restored from the backup.

### Edit colors at runtime (no rebuild)

```bash
synapseforge colors ./my-project
```

GUI editor for `frontend/public/colors.json`. Refresh the browser (F5) to see changes instantly.

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `synapseforge init [dir]` | Scaffold a project from bundled template (GUI) |
| `synapseforge launch -p <path> -n <exe> [--skip-frontend] [--no-embed] [-c]` | Build self-contained desktop app / distribution zip (`-c` compiles backend to `.pyc`, default ships `.py`) |
| `synapseforge colors [dir]` | Edit `frontend/public/colors.json` via GUI (live reload) |
| `synapseforge run [dir]` | Start uvicorn + npm dev servers, open browser (venv must be active) |
| `synapseforge update [dir]` | Update project to latest template (preserves agent.db, config, colors) |
| `synapseforge --help` | Show global help |

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

synapseForge will always be free and open source. If you find it useful, consider supporting its development with a [donation via Mercado Pago](https://link.mercadopago.com.ar/synapseforge) — your donation goes directly into new features, fixes and better docs for everyone.

---

## License

Apache 2.0

---

Copyright (c) 2026 SYNAPSE AI SAS

---
