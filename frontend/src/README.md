<p align="center">
  <img src="../../src/logo_empresa.png" alt="Logo" width="150">
</p>

---

<h1 align="center">[Frontend — <nombre>nombre_proyecto</nombre>]</h1>

---

<p align="center">
  <a href="./LICENSE">
    <img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License: Apache 2.0" />
  </a>
</p>

---

<h3 align="center">[Interfaz de usuario React + TypeScript + Vite para el <nombre>nombre_proyecto</nombre>]</h3>

---

## Descripción

Frontend del **<nombre>nombre_proyecto</nombre>**. Aplicación React 19 + TypeScript + Vite que provee la interfaz de chat streaming (SSE), panel de configuración de modelo/proveedor/contexto, gestión de sesiones, creación de skills/tools/agentes, gestión de RAG y visualización de tool calls en tiempo real.

### ✨ Características Principales

- **Chat streaming SSE**: Conversación en tiempo real con Server-Sent Events.
- **Configuración dinámica**: Selección de proveedor (providers cloud curados u Ollama local), modelo y ventana de contexto desde la UI.
- **Gestión de sesiones**: Sidebar con historial, títulos, preview y eliminación.
- **Tool calls visibles**: Colapsables por tool con input/output formateado.
- **Adjuntos**: Arrastrar y soltar archivos; extracción de texto automática.
- **Creación asistida por LLM**: Páginas standalone para crear skills, tools, agentes y workflows.
- **Gestión de RAG**: Página para crear colecciones, subir archivos y agregar URLs.
- **Gauge de contexto**: Indicador de uso de la ventana de contexto en el header.
- **Tareas programadas**: Panel de agenda para programar ejecuciones.
- **Métricas, uso y facturación**: Dashboard de métricas, consumo del mes y límites de gasto por proveedor y modelo.
- **Telegram y MCP**: Toggle del bot de Telegram y panel de servidores MCP con interruptor para activar o desactivar cada uno.
- **Colores del tema**: Variables CSS configurables (`colors.json`), editables en vivo con `synapseforge colors`.

---

## Stack Tecnológico

- **React 19** + **TypeScript 5**
- **Vite 6** (dev server + build multi-page)
- **Tailwind CSS 4** (utilidad-first styling) + **shadcn/ui** sobre **Radix UI**
- **Lucide React** (iconos)
- **Marked** (renderizado markdown en mensajes)
- **DOMPurify** (sanitización XSS del markdown)
- **Mermaid** (diagramas en los mensajes)

---

## Estructura del proyecto

```plaintext
frontend/
├─ public/                     # Assets estáticos (docs.html, colors.json)
├─ src/
│  ├─ assets/                  # Logo, imágenes
│  │  ├─ logo_empresa.png      # Logo de la empresa
│  │  └─ logo_cliente.png      # Logo del cliente
│  ├─ chat/                    # Chat principal
│  │  ├─ ChatInterface.tsx     # Chat (streaming SSE, adjuntos, autoscroll, gauge de contexto)
│  │  ├─ useSessionFeedback.ts # Hook del 👍/👎 de las respuestas de la sesión
│  │  └─ chatMain.tsx          # Entry de la página de chat: carga colors.json → setea CSS vars → render App
│  ├─ skill/                   # Creación de skills
│  │  ├─ SkillInterface.tsx    # Página de creación de skills (setup + chat + overlay)
│  │  └─ skillMain.tsx         # Entry de la skill page (multi-page)
│  ├─ tool/                    # Creación de tools
│  │  ├─ ToolInterface.tsx     # Página de creación de tools
│  │  └─ toolMain.tsx          # Entry de la tool page (multi-page)
│  ├─ agent/                   # Creación de agentes
│  │  ├─ AgentInterface.tsx    # Página de creación de agentes
│  │  └─ agentMain.tsx         # Entry de la agent page (multi-page)
│  ├─ workflow/                # Creación de workflows
│  │  ├─ WorkflowInterface.tsx # Página de creación de workflows (entrevista por chat + editor YAML)
│  │  └─ workflowMain.tsx      # Entry de la workflow page (multi-page)
│  ├─ rag/                     # Gestión de RAG
│  │  ├─ RagInterface.tsx      # Página de gestión de colecciones RAG
│  │  └─ ragMain.tsx           # Entry de la rag page (multi-page)
│  ├─ components/              # Componentes React
│  │  ├─ Sidebar.tsx           # Barra lateral con tabs (sessions, config, agent, create)
│  │  ├─ sessionsTab.tsx       # Lista de sesiones de chat
│  │  ├─ configTab.tsx         # Configuración (proveedor, modelo, modelo de decisión, contexto, verbose, archivos de contexto)
│  │  ├─ agentInfoTab.tsx      # Panel de agentes (tools, skills, agents, mcp, rag, workflows)
│  │  ├─ createTab.tsx         # Creación de skills/tools/agentes/workflows/RAG
│  │  ├─ chatBlocks.tsx        # Componentes compartidos (MessageRow, MarkdownRenderer, ToolCallBlock, ReasoningBlock, FileChip, etc.)
│  │  ├─ ContextGauge.tsx      # Gauge de ventana de contexto
│  │  ├─ UsageTab.tsx          # Consumo del mes por proveedor
│  │  ├─ BillingTab.tsx        # Gasto por proveedor y modelo, y límites de gasto
│  │  ├─ CreateModelSelector.tsx # Selector de modelo para creación
│  │  ├─ HistoryModal.tsx      # Historial de cotizaciones (consulta `/api/quotes/history`)
│  │  ├─ MetricsModal.tsx      # Dashboard de métricas por rango de tiempo
│  │  ├─ SchedulerModal.tsx    # Tareas programadas (agenda)
│  │  ├─ SetupScreen.tsx       # Pantalla inicial de configuración de providers
│  │  ├─ MessageBubble.tsx     # Burbuja de mensaje (legacy)
│  │  ├─ Logo.tsx              # Logo
│  │  └─ ui/                   # shadcn/ui: avatar, button, dialog, input, separator, textarea, collapsible, utils
│  ├─ services/                # Capa de comunicación con API
│  │  ├─ chatService.ts        # Streaming SSE a /api/chat
│  │  ├─ configService.ts      # Providers, models, modelo de decisión, workflows (validar/guardar/generar), MCP, verbose, contexto
│  │  ├─ workflowService.ts    # Workflows: listado con estado, play, cancelar y eliminar
│  │  ├─ notificationService.ts# Notificaciones persistidas de la campanita
│  │  ├─ feedbackService.ts    # 👍/👎 sobre las respuestas (por sesión y turno)
│  │  ├─ sessionService.ts     # Sesiones CRUD
│  │  ├─ contextFilesService.ts# Archivos de contexto CRUD
│  │  ├─ metricsService.ts     # Métricas
│  │  ├─ schedulerService.ts   # Tareas programadas
│  │  ├─ telegramService.ts    # Estado y toggle del bot de Telegram
│  │  └─ quoteHistoryService.ts# Historial de cotizaciones
│  ├─ utils/                   # Utilidades
│  │  ├─ mermaid.ts            # Renderizado de diagramas mermaid
│  │  └─ conversationExport.ts # Exportación de conversaciones a Markdown
│  ├─ App.tsx                  # Componente raíz + estado global
│  ├─ index.css                # Estilos globales + @theme (colores)
│  ├─ createColors.css         # Paleta compartida por las páginas de creación
│  └─ vite-env.d.ts            # Tipos de Vite
├─ index.html                  # Página del chat
├─ skill.html, tool.html, agent.html, workflow.html, rag.html  # Páginas de creación y de RAG
├─ package.json
├─ tsconfig.json
├─ tsconfig.app.json
├─ tsconfig.node.json
├─ vite.config.ts
└─ README.md
```

---

## Instalación

1. **Clonar el repositorio**

```bash
>>> git clone https://github.com/<owner>nombre_owner</owner>/<repo>nombre_repo</repo>.git
>>> cd <repo>nombre_repo</repo>/frontend
```

2. **Instalar dependencias**

```bash
>>> npm install
```

3. **Desarrollo**

```bash
>>> npm run dev
```

Abre `http://localhost:3000`. El frontend llama directamente al backend en `http://localhost:8000` (CORS habilitado para los puertos 3000 y 5173).

4. **Build producción**

```bash
>>> npm run build
```

Output en `dist/`: una página por entrada (`index.html`, `skill.html`, `tool.html`, `agent.html`, `workflow.html` y `rag.html`). El backend sirve `dist/` cuando existe.

---

## Variables de entorno

Crea `.env` en la raíz del proyecto (el `envDir` de Vite apunta a `../`):

```env
VITE_MODE=dev            # "dev" o "prod"
VITE_URL_DEV=http://localhost:8000
VITE_URL_PROD=http://localhost:8000
VITE_URL_BASE=http://localhost:8000
```

Los servicios `chatService`, `configService`, `sessionService`, `contextFilesService` y `quoteHistoryService` usan `VITE_MODE` para elegir entre `VITE_URL_DEV` y `VITE_URL_PROD`. `VITE_URL_BASE` es la base de la API en `metricsService`, `schedulerService`, `telegramService` y en los componentes y páginas que llaman a la API directamente (`App`, uso y facturación, páginas de creación y de RAG). `VITE_MODE=dev` además muestra las pestañas **Agente** y **Crear** del sidebar.

---

## Flujo principal

1. **Carga inicial** → `chat/chatMain.tsx` hace `fetch("/colors.json")` y setea las CSS vars → renderiza `App`.
2. **Setup** → si no está completado, `SetupScreen` pide las API keys de los providers.
3. **Proveedores** → `configService` llama `GET /config/providers` → muestra proveedores disponibles.
4. **Selección modelo** → `GET /config/models?provider=X` → lista modelos; `POST /config/models/select` → persiste en backend (SQLite `config_kv`).
5. **Chat** → `ChatInterface` envía `POST /api/chat` (SSE) → `chatService` parsea eventos → `MessageRow`/`chatBlocks` renderizan bloques (texto, razonamiento, tools, sub-agentes).
6. **Sesiones** → `sessionService` `GET /api/sessions` → `sessionsTab` en sidebar.
7. **Contexto** → `POST /config/context-window` → ajusta `max_turns`; el gauge se actualiza con los eventos `token_counter`.
8. **Archivos de contexto** → `contextFilesService` `GET/POST/DELETE /api/context-files` → `configTab` gestiona subida/eliminación → se inyectan en el system prompt.
9. **Tareas programadas** → `SchedulerModal` usa `schedulerService` para gestionar la agenda.
10. **Telegram** → `telegramService` controla el estado y toggle del bot.

---

## Componentes clave

### `chat/ChatInterface.tsx`
Chat principal. Mantiene el estado de mensajes, streaming SSE a `/api/chat`, autoscroll, adjuntos de archivos, detener generación, heartbeat y shutdown. Renderiza cada mensaje con `MessageRow` y muestra el gauge de contexto en el header. Ante el evento SSE `decision` con `action: "discarded"` muestra un aviso de que el trabajo pendiente anterior fue descartado; un mensaje bloqueado por el guardrail llega como un `chunk` con el aviso del bloqueo.

### `components/chatBlocks.tsx`
Componentes compartidos entre las interfaces de chat y creación:
- `MessageRow` — Fila de mensaje (asistente con avatar + bloques intercalados, usuario con burbuja). Debajo de cada respuesta van los botones Copiar y 👍/👎, con los colores del tema.
- `MarkdownRenderer` — Renderiza markdown a HTML con sanitización DOMPurify.
- `ToolCallBlock` — Tarjeta de tool call con estados y sub-pasos de sub-agentes.
- `ReasoningBlock`, `FileChip`, `FileWarningBanner`, `TypingIndicator`.

### `skill/SkillInterface.tsx`
Página de creación de skills (multi-page). Flujo en dos fases: setup (nombre + descripción) y chat de entrevista con streaming SSE a `/api/create/skill`. Al finalizar muestra un overlay de resultado.

### `tool/ToolInterface.tsx` y `agent/AgentInterface.tsx`
Páginas de creación de tools y agentes, con el mismo patrón de entrevista iterativa vía streaming SSE.

### `workflow/WorkflowInterface.tsx`
Página de creación de workflows (multi-page). Entrevista por chat con streaming SSE a `/api/create/workflow` y editor YAML con generar, validar y guardar (`/api/config/workflows/generate`, `/validate`, `/save`).

### `rag/RagInterface.tsx`
Página de gestión de colecciones RAG: crear colecciones, subir archivos y agregar URLs.

### `Sidebar.tsx`
Barra lateral con tabs: Conversaciones (`sessionsTab`), Configuración (`configTab`), Agente (`agentInfoTab`) y Crear (`createTab`). Agente y Crear solo se muestran con `VITE_MODE=dev`.

### `configTab.tsx`
Configuración: selector de proveedor/modelo, sección de modelo de decisión (habilitar, proveedor, modelo y ficha del catálogo), ventana de contexto, toggle verbose y gestión de archivos de contexto.

### `agentInfoTab.tsx`
Panel de agentes con 6 sub-paneles: Tools, Skills, Agentes, MCP (estado de cada servidor, interruptor para activarlo o desactivarlo y borrado), RAG y Workflows (una tarjeta por workflow con un botón play que lo ejecuta en segundo plano y un botón de eliminar con confirmación, ambos visibles al pasar el mouse; mientras corre muestra "Ejecutando…" con un botón para cancelar y el play queda bloqueado).

### `MetricsModal.tsx`
Dashboard de métricas con filtro de rango de tiempo (`1h`, `6h`, `1d`, `1w`, `1m`, todo) y tarjetas de Sesiones, Mensajes, Uso de herramientas, Modelos, Gasto y Errores. Cada tarjeta muestra sus gráficos, incluida la figura de outliers que renderiza el backend, y permite descargar los datos.

### `UsageTab.tsx` y `BillingTab.tsx`
Se abren desde los botones **Usage** y **Billing** del header. Usage muestra el consumo del mes (requests, tokens y gasto) por proveedor; Billing el gasto por proveedor y modelo, con filtros, y permite configurar límites de gasto.

### `SchedulerModal.tsx`
Panel de tareas programadas (agenda): agregar, editar horario y eliminar tareas. Los permisos de una tarea incluyen los workflows que puede ejecutar.

### `SetupScreen.tsx`
Pantalla inicial de configuración de providers (API keys) que aparece al primer arranque.

### Servicios (`services/`)
Capa fina sobre `fetch`. `chatService` (SSE), `configService` (providers/models/modelo de decisión/workflows/MCP/verbose/contexto), `workflowService` (workflows: listado, play, cancelar y eliminar), `notificationService` (notificaciones de la campanita), `sessionService` (sesiones), `feedbackService` (👍/👎 de las respuestas), `contextFilesService` (archivos de contexto), `metricsService` (métricas), `schedulerService` (tareas programadas), `telegramService` (bot de Telegram), `quoteHistoryService` (historial de cotizaciones).

---

## Estilos y tema

Las variables de color se declaran en `src/index.css` dentro de `@theme {}`. El pipeline `synapseForge init` reemplaza automáticamente los placeholders `<tag>default</tag>` con los valores ingresados o extraídos del logo.

### Variables configurables (definidas por el pipeline)

| Variable | Key de `colors.json` | Uso |
|----------|----------------------|-----|
| `--color-app-primary` | `primary` | Color principal: botón de enviar, barra de actividad, opción seleccionada del menú, enlaces de las respuestas |
| `--color-app-primary-light` | `secondary` | Detalles suaves: anillo de foco de los campos, anillo de la conversación seleccionada, bordes de las tarjetas |
| `--color-app-primary-text` | `primary_text` | Texto e íconos sobre el color principal (flecha de enviar, texto de botones, ícono del avatar) |
| `--color-app-gradient-secondary` | `gradient_secondary` | Color final del degradé de los botones y el avatar |

Además, `usar_gradiente` (toggle) no es una variable CSS: cuando está apagado, `gradient_secondary` se fuerza igual a `primary` para que los degradés se vean lisos.

### Variables fijas (no se modifican en el pipeline)

| Variable | Valor | Uso |
|----------|-------|-----|
| `--color-app-bg` | `#FFFFFF` | Fondo general de la app |
| `--color-app-bg-secondary` | `#F5F5F5` | Fondo secundario |
| `--color-app-bg-tertiary` | `#EBEBEB` | Paneles, tool calls, fondos terciarios |
| `--color-app-text` | `#151515` | Texto principal |
| `--color-app-text-secondary` | `#5C5C5C` | Texto secundario |
| `--color-app-border` | `#D4D4D4` | Bordes generales |
| `--color-app-success` | `#2B7D5B` | Estados de éxito |
| `--color-app-warning` | `#C4903A` | Estados de advertencia |
| `--color-app-error` | `#C2413D` | Estados de error |

**Para cambiar colores manualmente**: editar `src/index.css` → `@theme {}` → recargar, o usar `synapseforge colors` que edita `frontend/public/colors.json` en vivo.

> **Nota**: los placeholders se reemplazan automáticamente al ejecutar `synapseForge init`. Para regenerar los colores desde el logo, ejecutar nuevamente el pipeline.

---

## Scripts disponibles

| Comando | Descripción |
|---------|-------------|
| `npm run dev` | Servidor de desarrollo (HMR) en el puerto 3000 |
| `npm run build` | Chequeo de tipos (`tsc -b`) y build de producción en `dist/` |
| `npm run preview` | Preview del build local |

---

## Licencia

Este proyecto está licenciado bajo los términos especificados en el archivo [LICENSE](./LICENSE) ubicado en la raíz del repositorio.

---

Copyright (c) 2026 <legal>nombre_legal_empresa</legal>

---