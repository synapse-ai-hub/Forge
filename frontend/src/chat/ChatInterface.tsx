import {
  useState,
  useRef,
  useEffect,
  useCallback,
  forwardRef,
  useImperativeHandle,
  type KeyboardEvent,
  type ForwardedRef,
} from "react";
import {
  Send,
  Square,
  Paperclip,
  Search,
  Menu,
  BarChart3,
  TrendingUp,
  DollarSign,
  LogOut,
  BookOpen,
  AlarmClock,
  Bell,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import LogoImage from "../assets/logo_cliente.png";
import chatService from "../services/chatService";
import configService from "../services/configService";
import type { SchedulerNotification } from "../services/schedulerService";
import { Button } from "../components/ui/button";
import { FileChip, FileWarningBanner, MessageRow } from "../components/chatBlocks";
import { ContextGauge } from "../components/ContextGauge";
import type { Message, SubagentEvent, SubagentStep, ContentBlock } from "../App";

/* ------------------------------------------------------------------ */
/*  Exported welcome message for App initialization                   */
/* ------------------------------------------------------------------ */

export const WELCOME_MESSAGE: Message = {
  id: "welcome",
  type: "assistant",
  content: `¡Hola! Soy el **asistente de <tarea>nombre_tarea</tarea> de <cliente>nombre_cliente</cliente>**. 👋


¿En qué puedo ayudarte hoy?`,
};

/* ------------------------------------------------------------------ */
/*  Constants                                                         */
/* ------------------------------------------------------------------ */



const ALLOWED_FILE_TYPES = [
  "text/csv",
  "text/plain",
  "text/markdown",
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
  "application/json",
  "application/xml",
  "text/xml",
];
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB per file
const MAX_FILES = 3;
const MAX_TOTAL_SIZE = 25 * 1024 * 1024; // 25 MB total

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

/** Generate a unique ID with safe fallback when crypto is unavailable. */
function generateId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
}

/* ------------------------------------------------------------------ */
/*  Main Component                                                    */
/* ------------------------------------------------------------------ */

interface ChatInterfaceProps {
  messages: Message[];
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  isStreaming: boolean;
  setIsStreaming: React.Dispatch<React.SetStateAction<boolean>>;
  onShowHistory: () => void;
  sessionId: string | null;
  onSessionStart: (id: string) => void;
  onNewChat: () => void;
  onSessionEnd?: () => void;
  onShowMetrics: () => void;
  onShowUsage?: () => void;
  onShowBilling?: () => void;
  onSessionTitleUpdate?: (sessionId: string, title: string) => void;
  onToggleSidebar?: () => void;
  verboseMode: boolean;
  telegramEnabled: boolean;
  onTelegramToggle: (val: boolean) => void;
  onShowScheduler?: () => void;
  /** Bell notifications: one entry per scheduled-task execution. */
  notifications?: SchedulerNotification[];
  onClearNotifications?: () => void;
}

export interface ChatInterfaceHandle {
  /** Send a message programmatically (used by the Telegram bridge). */
  sendMessage: (
    text: string,
    telegramChatId?: string | null,
    telegramSessionId?: string | null,
  ) => void;
  /** Set the context-window gauge percentage (used on session reload). */
  setContextPercent: (percent: number) => void;
  /** Set the full context info (window, tokens used, percent) on session reload. */
  setContextInfo: (info: {
    contextWindow: number | null;
    tokensUsed: number | null;
    percent: number | null;
  }) => void;
}

export const ChatInterface = forwardRef<ChatInterfaceHandle, ChatInterfaceProps>(
  function ChatInterface(
    {
      messages,
      setMessages,
      isStreaming,
      setIsStreaming,
      onShowHistory,
      sessionId,
      onSessionStart,
      onNewChat,
      onSessionEnd,
      onShowMetrics,
      onShowUsage,
      onShowBilling,
      onSessionTitleUpdate,
      verboseMode,
      telegramEnabled,
      onTelegramToggle,
      onShowScheduler,
      notifications = [],
      onClearNotifications,
    }: ChatInterfaceProps,
    ref: ForwardedRef<ChatInterfaceHandle>,
  ) {
  /* ---- state ---- */
  const [input, setInput] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [fileWarning, setFileWarning] = useState<string | null>(null);
  const [contextPercent, setContextPercent] = useState(0);
  const [contextWindow, setContextWindow] = useState<number | null>(null);
  const [tokensUsed, setTokensUsed] = useState<number | null>(null);
  const [vramGb, setVramGb] = useState<number | null>(null);
  const [ollamaDefaultContext, setOllamaDefaultContext] = useState<number | null>(null);
  const [currentProvider, setCurrentProvider] = useState<string | null>(null);
  /* Bell dropdown: scheduled-task execution notifications. */
  const [showNotifications, setShowNotifications] = useState(false);

  /* ---- refs ---- */
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  /* ---- auto scroll ---- */
  const [autoScrollEnabled, setAutoScrollEnabled] = useState(true);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const userInteractionRef = useRef(false);
  const wheelUpRef = useRef(false);
  const isProgrammaticScrollRef = useRef(false);
  const programmaticScrollTimeoutRef = useRef<number | null>(null);
  const cancelledRef = useRef(false);
  const tokensUsedRef = useRef<number | null>(null);

  const scrollToBraintom = useCallback((behavior: ScrollBehavior = "smooth") => {
    if (messagesContainerRef.current) {
      isProgrammaticScrollRef.current = true;
      messagesContainerRef.current.scrollTo({
        top: messagesContainerRef.current.scrollHeight,
        behavior,
      });
      if (programmaticScrollTimeoutRef.current) {
        clearTimeout(programmaticScrollTimeoutRef.current);
      }
      programmaticScrollTimeoutRef.current = window.setTimeout(() => {
        isProgrammaticScrollRef.current = false;
        programmaticScrollTimeoutRef.current = null;
      }, 350);
    }
  }, []);

  useEffect(() => {
    if (autoScrollEnabled) {
      scrollToBraintom("smooth");
    }
  }, [messages, autoScrollEnabled, scrollToBraintom]);

  // Load the model's context window (in tokens) so the gauge info shows it
  // immediately instead of waiting for the first token_counter event.
  // No polling: it is refreshed only by events (mount, model-changed,
  // session change, token_counter SSE).
  const loadContextWindow = useCallback(() => {
    configService
      .getContextWindow()
      .then((data) => {
        if (cancelledRef.current) return;
        if (data.context_window_tokens != null) {
          setContextWindow(data.context_window_tokens);
          // Recompute percent against the new window using the last known tokensUsed.
          const used = tokensUsedRef.current;
          if (used != null && data.context_window_tokens > 0) {
            setContextPercent((used / data.context_window_tokens) * 100);
          }
        }
        if (data.vram_gb != null) {
          setVramGb(data.vram_gb);
        }
        if (data.ollama_default_context != null) {
          setOllamaDefaultContext(data.ollama_default_context);
        }
      })
      .catch(() => {
        // Silent failure - context window info is optional
      });
  }, []);

  useEffect(() => {
    cancelledRef.current = false;
    loadContextWindow();
    return () => {
      cancelledRef.current = true;
    };
  }, [loadContextWindow]);

  // Keep tokensUsedRef in sync so loadContextWindow can recompute the percent
  // against a freshly-fetched context window when the model changes.
  useEffect(() => {
    tokensUsedRef.current = tokensUsed;
  }, [tokensUsed]);

  // Refresh the gauge when the model changes (event dispatched by ConfigTab).
  useEffect(() => {
    const onModelChange = () => loadContextWindow();
    window.addEventListener("model-changed", onModelChange);
    return () => window.removeEventListener("model-changed", onModelChange);
  }, [loadContextWindow]);

  // Load current provider
  const loadCurrentProvider = useCallback(() => {
    configService
      .getModels()
      .then((data) => {
        if (cancelledRef.current) return;
        setCurrentProvider(data.provider || null);
      })
      .catch(() => {
        if (!cancelledRef.current) setCurrentProvider(null);
      });
  }, []);

  useEffect(() => {
    loadCurrentProvider();
  }, [loadCurrentProvider]);

  useEffect(() => {
    const onModelChange = () => loadCurrentProvider();
    window.addEventListener("model-changed", onModelChange);
    return () => window.removeEventListener("model-changed", onModelChange);
  }, [loadCurrentProvider]);

  /* ---- workflow mode: smart or one deterministic workflow ---- */
  const [workflowSelected, setWorkflowSelected] = useState("smart");
  const [workflowAvailable, setWorkflowAvailable] = useState<string[]>(["smart"]);

  const loadWorkflowSelection = useCallback(() => {
    configService
      .getWorkflowSelection()
      .then((data) => {
        if (cancelledRef.current) return;
        setWorkflowAvailable(data.available?.length ? data.available : ["smart"]);
        setWorkflowSelected(data.selected || "smart");
      })
      .catch(() => {
        if (!cancelledRef.current) {
          setWorkflowAvailable(["smart"]);
          setWorkflowSelected("smart");
        }
      });
  }, []);

  useEffect(() => {
    loadWorkflowSelection();
  }, [loadWorkflowSelection]);

  useEffect(() => {
    const onChanged = (e: Event) => {
      const w = (e as CustomEvent).detail?.workflow;
      if (w) {
        setWorkflowSelected(w);
      } else {
        loadWorkflowSelection();
      }
    };
    window.addEventListener("workflow-changed", onChanged);
    return () => window.removeEventListener("workflow-changed", onChanged);
  }, [loadWorkflowSelection]);

  /* ---- blocked state: no provider/model selected yet ---- */
  const [modelSelected, setModelSelected] = useState<boolean | null>(null);
  const loadModelSelected = useCallback(() => {
    configService
      .getModels()
      .then((data) => {
        if (cancelledRef.current) return;
        setModelSelected(Boolean(data.model));
      })
      .catch(() => {
        if (!cancelledRef.current) setModelSelected(null);
      });
  }, []);

  useEffect(() => {
    loadModelSelected();
  }, [loadModelSelected]);

  useEffect(() => {
    const onModelChange = () => loadModelSelected();
    window.addEventListener("model-changed", onModelChange);
    return () => window.removeEventListener("model-changed", onModelChange);
  }, [loadModelSelected]);

  const chatBlocked = modelSelected === false;

  const handleMessagesScroll = useCallback(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const nearBraintom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
    setShowScrollButton(!nearBraintom);

    // Scroll de usuario (rueda): manda aunque haya un scroll programático en curso.
    if (userInteractionRef.current) {
      // Subiendo con la rueda: el autoscroll queda apagado aunque sea mínimo.
      // Bajando: se reactiva recién al llegar al umbral del fondo.
      setAutoScrollEnabled(wheelUpRef.current ? false : nearBraintom);
      return;
    }
    // Solo cambiar autoScroll si NO es scroll programático.
    if (!isProgrammaticScrollRef.current) {
      setAutoScrollEnabled(nearBraintom);
    }
  }, []);

  const handleMessagesWheel = useCallback((e: { deltaY: number }) => {
    // Marcar interacción de usuario (sincrónico) para que el scroll handler mande.
    userInteractionRef.current = true;
    setTimeout(() => {
      userInteractionRef.current = false;
    }, 300);

    // Subir con la rueda desactiva el autoscroll SIEMPRE (aunque sea mínimo).
    if (e.deltaY < 0) {
      wheelUpRef.current = true;
      setAutoScrollEnabled(false);
    } else {
      // Bajando: el autoscroll se reactiva recién al llegar al fondo.
      wheelUpRef.current = false;
    }
  }, []);

  /* ---- cleanup on unmount ---- */
  useEffect(() => {
    return () => {
      chatService.cancelStream();
      if (programmaticScrollTimeoutRef.current) {
        clearTimeout(programmaticScrollTimeoutRef.current);
        programmaticScrollTimeoutRef.current = null;
      }
    };
  }, []);

  /* ---- shutdown app ---- */
  const handleShutdown = useCallback(async () => {
    if (!window.confirm("¿Cerrar la aplicación completamente?")) return;
    try {
      const API_BASE_URL = import.meta.env.VITE_URL_BASE || "http://localhost:8000";
      await fetch(`${API_BASE_URL}/api/shutdown`, { method: "POST" });
    } catch {
      // Ignore network errors - server is shutting down
    }
    // Close the window (works if opened by window.open or as PWA)
    window.close();
  }, []);

  /* ---- open docs in new tab ---- */
  const handleOpenDocs = useCallback(() => {
    const base = window.location.origin;
    window.open(`${base}/docs.html`, "_blank", "noopener,noreferrer");
  }, []);

  /* ---- auto-resize textarea ---- */
  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = `${Math.min(ta.scrollHeight, 220)}px`;
    }
  }, [input]);

  /* ---- file validation ---- */
  const handleFilesSelected = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selected = Array.from(e.target.files || []);
      const valid: File[] = [];
      let warning: string | null = null;
      let currentTotalSize = files.reduce((sum, f) => sum + f.size, 0);

      for (const f of selected) {
        if (!ALLOWED_FILE_TYPES.includes(f.type) && !f.name.match(/\.(csv|xlsx|xls)$/i)) {
          warning = `Tipo de archivo no soportado: ${f.name}. Permitidos: PDF, DOCX, XLSX, TXT, CSV, JSON, XML.`;
          continue;
        }
        if (f.size > MAX_FILE_SIZE) {
          warning = `Archivo demasiado grande: ${f.name} (máx 10 MB).`;
          continue;
        }
        if (valid.length + files.length >= MAX_FILES) {
          warning = `Máximo ${MAX_FILES} archivos permitidos.`;
          break;
        }
        if (currentTotalSize + f.size > MAX_TOTAL_SIZE) {
          warning = `Tamaño total excede ${MAX_TOTAL_SIZE / (1024 * 1024)} MB.`;
          break;
        }
        valid.push(f);
        currentTotalSize += f.size;
      }
      if (warning) setFileWarning(warning);
      setFiles((prev) => [...prev, ...valid]);
      // Reset input so same file can be picked again
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    [files],
  );

  const removeFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  /* ---- auto-dismiss file warning after 6 seconds ---- */
  useEffect(() => {
    if (!fileWarning) return;
    const timer = setTimeout(() => setFileWarning(null), 6000);
    return () => clearTimeout(timer);
  }, [fileWarning]);

  /* ---- new conversation ---- */
  const handleNewConversation = useCallback(() => {
    chatService.cancelStream();
    setIsStreaming(false);
    setInput("");
    setFiles([]);
    setFileWarning(null);
    onNewChat();
  }, [onNewChat, setIsStreaming]);

  /* ---- send message ---- */
  const sendMessage = useCallback(
    async (
      text: string,
      telegramChatId?: string | null,
      telegramSessionId?: string | null,
    ) => {
      const _t0 = performance.now();
      // console.log(`[DEBUG_TIEMPO_SSE] sendMessage called — t=${_t0}`);
      const trimmed = text.trim();
      if (!trimmed || isStreaming) return;

      // Ensure we have a session id for this conversation
      let activeSessionId = telegramSessionId || sessionId;
      if (!activeSessionId) {
        activeSessionId = generateId();
        onSessionStart(activeSessionId);
      } else if (telegramSessionId && telegramSessionId !== sessionId) {
        // A Telegram message arrived for a different (new) session: select it
        // exactly as the "new conversation" button does.
        onSessionStart(telegramSessionId);
      }

      setInput("");
      const currentFiles = [...files];
      setFiles([]);

      // Add user message with attached files
      const userMessage: Message = {
        id: generateId(),
        type: "user",
        content: trimmed,
        files: currentFiles.map((f) => ({ name: f.name, size: f.size })),
      };
      setMessages((prev) => [...prev, userMessage]);

    // Create assistant placeholder
    const assistantId = generateId();
    // console.log(`[DEBUG_TIEMPO_SSE] assistantId created: ${assistantId} — t=${performance.now()}, elapsed=${performance.now() - _t0}`);
    const assistantMessage: Message = {
      id: assistantId,
      type: "assistant",
      content: "",
      isStreaming: true,
      blocks: [],
      toolCalls: [],
      toolResults: [],
    };
    // console.log(`[DEBUG_TIEMPO_SSE] assistantMessage id: ${assistantMessage.id} — t=${performance.now()}`);
    setMessages((prev) => [...prev, assistantMessage]);
    // Forzar auto-scroll al enviar mensaje (como ProspectingAgent)
    setAutoScrollEnabled(true);
    setIsStreaming(true);

    let accumulatedContent = "";
    let accumulatedReasoning = "";
    let accumulatedBlocks: ContentBlock[] = [];

    /** Helper: agrega/actualiza el último bloque reasoning con el contenido acumulado */
    function updateReasoningBlock(): void {
      const reasonText = accumulatedReasoning.trim();
      if (!reasonText) return;
      const last = accumulatedBlocks[accumulatedBlocks.length - 1];
      if (last && last.type === "reasoning") {
        // Ya hay un bloque reasoning al final, actualizarlo
        last.content = reasonText;
      } else {
        // No hay bloque reasoning al final, agregarlo
        accumulatedBlocks.push({ type: "reasoning", content: reasonText });
      }
    }

    try {
      const eventStream = chatService.sendMessage({
        message: trimmed,
        files: currentFiles,
        sessionId: activeSessionId,
        telegramChatId,
      });

      for await (const event of eventStream) {
        // console.log(`[DEBUG_TIEMPO_SSE] event received type=${event.type} — t=${performance.now()}, elapsed=${performance.now() - _t0}`);
        switch (event.type) {
          case "router_status":
          case "reasoning":
            // Normalizar \n en los chunks de reasoning para evitar que se vean en líneas separadas
            accumulatedReasoning += (event.content || '').replace(/\n+/g, ' ');
            updateReasoningBlock();
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, blocks: [...accumulatedBlocks] } : m,
              ),
            );
            break;

          case "tool_call":
            {
              // Validate tool_call payload before storing (always, even if verbose is off)
              const tcPayload =
                typeof event.content === "object" && event.content !== null
                  ? event.content
                  : typeof event.content === "string"
                    ? (() => {
                        try {
                          return JSON.parse(event.content);
                        } catch {
                          return { tool: event.content, parameters: {} };
                        }
                      })()
                    : { tool: String(event.content), parameters: {} };
              const validated: { tool: string; parameters: Record<string, any> } = {
                tool:
                  typeof tcPayload.name === "string"
                    ? tcPayload.name
                    : "unknown",
                parameters:
                  typeof tcPayload.args === "object" && tcPayload.args !== null
                    ? tcPayload.args
                    : typeof tcPayload.parameters === "object" && tcPayload.parameters !== null
                      ? tcPayload.parameters
                      : {},
              };
              accumulatedBlocks.push({
                type: "tool",
                name: validated.tool,
                args: validated.parameters,
                result: undefined,
              });
              // Un nuevo step: el razonamiento siguiente empieza de cero (no acumulado).
              accumulatedReasoning = "";
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== assistantId) return m;
                  const tc = Array.isArray(m.toolCalls) ? m.toolCalls : [];
                  return { ...m, blocks: [...accumulatedBlocks], toolCalls: [...tc, validated] };
                }),
              );
              // Brief delay to break React 18's automatic batching between tool_call
              // and tool_result. Without this, consecutive setState calls in the same
              // async handler are batched into one render — the tool block appears
              // already with its result filled in, and the spinner is never visible.
              await new Promise(resolve => setTimeout(resolve, 0));
            }
            break;

          case "tool_result":
            if (event.content) {
              const payload =
                typeof event.content === "object" && event.content !== null
                  ? event.content
                  : { name: "unknown", result: event.content };
              const toolName =
                typeof payload.name === "string" ? payload.name : "unknown";
              const toolResultValue =
                "result" in payload ? payload.result : payload;
              // Update accumulatedBlocks
              for (let i = accumulatedBlocks.length - 1; i >= 0; i--) {
                if (accumulatedBlocks[i].type === "tool" && (accumulatedBlocks[i] as any).result === undefined) {
                  accumulatedBlocks[i] = { ...accumulatedBlocks[i], result: toolResultValue } as any;
                  break;
                }
              }
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== assistantId) return m;
                  return {
                    ...m,
                    blocks: [...accumulatedBlocks],
                    toolResults: [
                      ...(Array.isArray(m.toolResults) ? m.toolResults : []),
                      { tool: toolName, result: toolResultValue },
                    ],
                  };
                }),
              );
            }
            break;

          case "subagent_event": {
            const payload =
              typeof event.content === "object" && event.content !== null
                ? event.content
                : {};
            const childId: string = payload.child_session_id || "";
            const agentName: string = payload.agent_name || "";
            const innerEvent: any = payload.event || {};

            if (!childId) break;

            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== assistantId) return m;
                const current = { ...m };
                const events = { ...(current.subagentEvents || {}) };
                if (!events[childId]) {
                  events[childId] = {
                    child_session_id: childId,
                    agent_name: agentName,
                    tool_calls: [],
                    tool_results: [],
                    content: "",
                    reasoning: "",
                    steps: [],
                  };
                }
                const child = events[childId];
                let updatedChild = { ...child };

                switch (innerEvent.type) {
                  case "tool_call":
                    updatedChild.tool_calls = [
                      ...(child.tool_calls || []),
                      {
                        name: innerEvent.content?.name || "unknown",
                        args: innerEvent.content?.args || {},
                      },
                    ];
                    updatedChild.steps = [
                      ...(child.steps || []),
                      {
                        kind: "tool",
                        name: innerEvent.content?.name || "unknown",
                        args: innerEvent.content?.args || {},
                      },
                    ];
                    break;
                  case "tool_result":
                    updatedChild.tool_results = [
                      ...(child.tool_results || []),
                      {
                        name: innerEvent.content?.name || "unknown",
                        result: innerEvent.content?.result || "",
                      },
                    ];
                    {
                      const steps = [...(child.steps || [])];
                      for (let i = steps.length - 1; i >= 0; i--) {
                        const step = steps[i];
                        if (step.kind === "tool" && step.result === undefined) {
                          steps[i] = { ...step, result: innerEvent.content?.result ?? "" };
                          break;
                        }
                      }
                      updatedChild.steps = steps;
                    }
                    break;
                  case "chunk":
                    updatedChild.content = (child.content || "") + (innerEvent.content || "");
                    {
                      const steps = [...(child.steps || [])];
                      const last = steps[steps.length - 1];
                      if (last && last.kind === "text") {
                        steps[steps.length - 1] = { ...last, content: last.content + (innerEvent.content || "") };
                      } else {
                        steps.push({ kind: "text", content: innerEvent.content || "" });
                      }
                      updatedChild.steps = steps;
                    }
                    break;
                  case "reasoning":
                    updatedChild.reasoning = (child.reasoning || "") + (innerEvent.content || "");
                    {
                      const steps = [...(child.steps || [])];
                      const last = steps[steps.length - 1];
                      if (last && last.kind === "reasoning") {
                        steps[steps.length - 1] = { ...last, content: last.content + (innerEvent.content || "") };
                      } else {
                        steps.push({ kind: "reasoning", content: innerEvent.content || "" });
                      }
                      updatedChild.steps = steps;
                    }
                    break;
                }

                return { ...current, subagentEvents: { ...events, [childId]: updatedChild } };
              }),
            );
            break;
          }

          case "session_title":
            if (activeSessionId && typeof event.content === "string") {
              onSessionTitleUpdate?.(activeSessionId, event.content);
            }
            break;

          case "chunk":
            accumulatedContent += event.content;
            {
              const chunk = event.content || "";
              const last = accumulatedBlocks[accumulatedBlocks.length - 1];
              if (last && last.type === "text") {
                accumulatedBlocks[accumulatedBlocks.length - 1] = {
                  ...last,
                  content: last.content + chunk,
                };
              } else {
                accumulatedBlocks.push({ type: "text", content: chunk });
              }
            }
            setMessages((prev) => {
              const matched = prev.some((m) => m.id === assistantId);
              // console.log(`[DEBUG_TIEMPO_SSE] chunk setMessages — assistantId=${assistantId}, matchFound=${matched}, prevLen=${prev.length}, t=${performance.now()}`);
              return prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: accumulatedContent, blocks: [...accumulatedBlocks] }
                  : m,
              );
            });
            break;

          case "token_counter":
            setContextPercent(event.content?.percent ?? 0);
            setContextWindow(event.content?.context_window ?? null);
            setTokensUsed(event.content?.prompt_tokens ?? null);
            if (event.content?.vram_gb != null) setVramGb(event.content.vram_gb);
            if (event.content?.ollama_default_context != null)
              setOllamaDefaultContext(event.content.ollama_default_context);
            break;

          case "usage":
            break;

          case "done":
            // console.log(`[DEBUG_TIEMPO_SSE] done event — assistantId=${assistantId}, t=${performance.now()}`);
            break;

          case "ask_discount":
            if (event.content) {
              const suffix = `\n\n---\n${event.content}\n---\n\n`;
              accumulatedContent += suffix;
              // Also append to last text block in accumulatedBlocks
              const lastBlock = accumulatedBlocks[accumulatedBlocks.length - 1];
              if (lastBlock && lastBlock.type === "text") {
                accumulatedBlocks[accumulatedBlocks.length - 1] = {
                  ...lastBlock,
                  content: lastBlock.content + suffix,
                };
              } else {
                accumulatedBlocks.push({ type: "text", content: suffix });
              }
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: accumulatedContent, blocks: [...accumulatedBlocks] }
                    : m,
                ),
              );
            }
            break;

          default:
            // Intentionally ignore unknown event types for forward compatibility
            break;
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      const errorMsg =
        err instanceof Error ? err.message : "Error desconocido";
      setMessages((prev) =>
        prev.map((m) => {
          if (m.id !== assistantId) return m;
          const blocks = [...(m.blocks || accumulatedBlocks)];
          blocks.push({ type: "text", content: `*Error: ${errorMsg}*` });
          return { ...m, content: `*Error: ${errorMsg}*`, blocks };
        }),
      );
    } finally {
      // console.log(`[DEBUG_TIEMPO_SSE] finally — assistantId=${assistantId}, setIsStreaming(false), t=${performance.now()}, elapsed=${performance.now() - _t0}`);
      setIsStreaming(false);
      setMessages((prev) => {
        const matched = prev.some((m) => m.id === assistantId);
        // console.log(`[DEBUG_TIEMPO_SSE] finally setMessages — assistantId=${assistantId}, matchFound=${matched}, prevLen=${prev.length}, t=${performance.now()}`);
        return prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m));
      });
      onSessionEnd?.();
    }
  }, [isStreaming, files, setMessages, setIsStreaming, sessionId, onSessionStart, verboseMode]);

  /* ---- expose sendMessage to the parent (Telegram bridge) ---- */
  const applyContextPercent = useCallback((percent: number) => {
    setContextPercent(percent);
  }, []);
  const applyContextInfo = useCallback(
    (info: { contextWindow: number | null; tokensUsed: number | null; percent: number | null }) => {
      if (info.contextWindow != null) setContextWindow(info.contextWindow);
      if (info.tokensUsed != null) setTokensUsed(info.tokensUsed);
      setContextPercent(info.percent ?? 0);
    },
    [],
  );
  useImperativeHandle(
    ref,
    () => ({ sendMessage, setContextPercent: applyContextPercent, setContextInfo: applyContextInfo }),
    [sendMessage, applyContextPercent, applyContextInfo],
  );

  /* ---- send button / Enter ---- */
  const handleSend = useCallback(() => {
    if (chatBlocked) return;
    sendMessage(input);
  }, [input, sendMessage, chatBlocked]);

  /* ---- stop streaming ---- */
  const handleCancel = useCallback(() => {
    // console.log(`[DEBUG_TIEMPO_SSE] handleCancel called — t=${performance.now()}`);
    chatService.cancelStream();
  }, []);

  /* ---- keyboard ---- */
  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  /* ---- render ---- */
  return (
    <div className="flex flex-col h-full bg-app-bg transition-colors">
      {/* ========== HEADER (95px) ========== */}
      <header
        className="flex items-center px-6 sm:px-8 shrink-0 border-b border-app-border
                   bg-white"
        style={{ height: "95px" }}
      >
        {/* Left: Ventana de Contexto gauge + info */}
        <div className="flex items-center gap-3 shrink-0 pr-4">
          <div
            className="flex flex-col items-center"
            title="Cuánto espacio de contexto del modelo se está usando"
          >
            <span className="text-sm text-app-text-secondary">
              Ventana de Contexto
            </span>
            <ContextGauge percent={contextPercent} />
          </div>
          <div className="flex flex-col text-xs text-app-text-secondary leading-tight">
            <span>
              Tokens utilizados:{" "}
              <span className="font-medium text-app-text">
                {tokensUsed != null ? tokensUsed.toLocaleString() : "—"}
              </span>
            </span>
          </div>
        </div>

        {/* Center: logo + title */}
        <div className="flex-1 flex items-center justify-center gap-2 sm:gap-3">
          <img
            src={LogoImage}
            alt={"<cliente>nombre_cliente</cliente> Logo"}
            className="h-9 sm:h-[95px] w-auto"
          />
          <h1 className="text-lg sm:text-2xl font-semibold text-app-text">
            {/* @ts-ignore */}
            <nombre>nombre_proyecto</nombre>
          </h1>
        </div>

        {/* Right: workflow mode + Telegram toggle + scheduler + docs + métricas + salir */}
        <div className="flex items-center gap-1 shrink-0">
          {/* Workflow mode — smart o un workflow determinista */}
          <select
            value={workflowSelected}
            onChange={async (e) => {
              const w = e.target.value;
              try {
                const sel = await configService.selectWorkflow(w);
                setWorkflowSelected(sel);
              } catch {
                loadWorkflowSelection();
              }
            }}
            title="Modo: smart o workflow determinista"
            className="h-9 sm:h-10 px-2 text-xs font-medium rounded-md border border-app-border bg-white text-app-text hover:bg-app-bg-tertiary/60 transition-colors max-w-[140px]"
          >
            {workflowAvailable.map((w) => (
              <option key={w} value={w}>
                {w === "smart" ? "Smart" : w}
              </option>
            ))}
          </select>
          {/* Telegram toggle — mismo formato y colores que el toggle de verbose */}
          <button
            type="button"
            role="switch"
            aria-checked={telegramEnabled}
            onClick={() => onTelegramToggle(!telegramEnabled)}
            title={telegramEnabled ? "Telegram activado" : "Telegram desactivado"}
            className="flex items-center gap-2 px-2 h-9 sm:h-10 rounded-md hover:bg-app-bg-tertiary/60 transition-colors"
          >
            <svg
              viewBox="0 0 24 24"
              className="w-6 h-6"
              style={{ color: "#229ED9" }}
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M9.04 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71l-4.14-3.05-1.99 1.93c-.23.23-.42.42-.83.42z" />
            </svg>
            <span
              className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-app-primary-light ${
                telegramEnabled ? "bg-app-primary" : "bg-app-bg-tertiary"
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
                  telegramEnabled ? "translate-x-4" : "translate-x-0"
                }`}
              />
            </span>
          </button>

          {/* Scheduler — mismo formato que Docs/Métricas */}
          <Button
            variant="ghost"
            size="sm"
            onClick={onShowScheduler}
            className="gap-1.5 sm:gap-2 text-sm h-9 sm:h-10"
            title="Tareas programadas"
          >
            <AlarmClock size={16} />
            <span className="hidden sm:inline">Agenda</span>
          </Button>

          {/* Notificaciones de tareas programadas — campanita con badge */}
          <div className="relative">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowNotifications((v) => !v)}
              className="relative gap-1.5 sm:gap-2 text-sm h-9 sm:h-10"
              title="Notificaciones de tareas programadas"
            >
              <Bell size={16} />
              {notifications.length > 0 && (
                <span
                  className={`absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full text-[10px] font-semibold leading-4 text-white ${
                    notifications.some((n) => n.status === "error")
                      ? "bg-red-500"
                      : "bg-app-primary"
                  }`}
                >
                  {notifications.length > 9 ? "9+" : notifications.length}
                </span>
              )}
            </Button>

            {showNotifications && (
              <>
                {/* Click-away overlay */}
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setShowNotifications(false)}
                />
                <div className="absolute right-0 top-full mt-2 z-50 w-80 max-w-[calc(100vw-2rem)] bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden">
                  <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-200">
                    <span className="text-sm font-medium text-app-text">
                      Notificaciones
                    </span>
                    {notifications.length > 0 && onClearNotifications && (
                      <button
                        type="button"
                        onClick={onClearNotifications}
                        className="text-xs text-app-text-secondary hover:text-app-primary transition-colors"
                        title="Limpiar notificaciones"
                      >
                        Limpiar
                      </button>
                    )}
                  </div>
                  <div className="max-h-72 overflow-y-auto">
                    {notifications.length === 0 ? (
                      <p className="text-sm text-app-text-secondary px-4 py-6 text-center">
                        Sin notificaciones todavía.
                      </p>
                    ) : (
                      <ul className="divide-y divide-gray-100">
                        {notifications.map((n) => (
                          <li key={n.id} className="flex gap-2.5 px-4 py-3">
                            {n.status === "success" ? (
                              <CheckCircle2 size={16} className="shrink-0 mt-0.5 text-green-600" />
                            ) : (
                              <XCircle size={16} className="shrink-0 mt-0.5 text-red-500" />
                            )}
                            <div className="min-w-0">
                              <p className="text-sm font-medium text-app-text break-words">
                                {n.task}
                              </p>
                              <p className="text-xs text-app-text-secondary">
                                {n.finishedAt}
                                {" · "}
                                {n.status === "success" ? "Ejecutada con éxito" : "Falló"}
                              </p>
                              {n.detail && (
                                <p className="text-xs text-app-text-secondary mt-1 line-clamp-3 break-words">
                                  {n.detail}
                                </p>
                              )}
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={handleOpenDocs}
            className="gap-1.5 sm:gap-2 text-sm h-9 sm:h-10"
            title="Documentación"
          >
            <BookOpen size={16} />
            <span className="hidden sm:inline">Docs</span>
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={onShowUsage || (() => {})}
            className="gap-1.5 sm:gap-2 text-sm h-9 sm:h-10"
            title="Uso"
          >
            <TrendingUp size={16} />
            <span className="hidden sm:inline">Uso</span>
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={onShowBilling || (() => {})}
            className="gap-1.5 sm:gap-2 text-sm h-9 sm:h-10"
            title="Facturación"
          >
            <DollarSign size={16} />
            <span className="hidden sm:inline">Facturación</span>
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={onShowMetrics}
            className="gap-1.5 sm:gap-2 text-sm h-9 sm:h-10"
          >
            <BarChart3 size={16} />
            <span className="hidden sm:inline">Métricas</span>
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={handleShutdown}
            className="gap-1.5 sm:gap-2 text-sm h-9 sm:h-10 text-app-error hover:bg-red-50 hover:text-app-error"
            title="Cerrar aplicación"
          >
            <LogOut size={16} />
            <span className="hidden sm:inline">Salir</span>
          </Button>
        </div>

      </header>

      {/* ========== MESSAGES AREA ========== */}
      <div className="flex-1 min-h-0 relative">
        {showScrollButton && (
          <div className="absolute left-1/2 transform -translate-x-1/2 z-10" style={{ bottom: '30px' }}>
            <button
              type="button"
              onClick={() => {
                wheelUpRef.current = false;
                setAutoScrollEnabled(true);
                scrollToBraintom("smooth");
              }}
              className="w-10 h-10 rounded-full transition-all duration-200 flex items-center justify-center border border-app-primary/20 bg-app-primary/10 text-app-primary hover:bg-app-primary/20 hover:text-app-primary shadow-sm"
              title="Ir al final"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
              </svg>
            </button>
          </div>
        )}

        <div
          ref={messagesContainerRef}
          onScroll={handleMessagesScroll}
          onWheel={handleMessagesWheel}
          className="h-full overflow-y-auto px-3 sm:px-4 py-4 sm:py-6 pr-3 sm:pr-5"
          style={{
            scrollbarWidth: "thin",
            scrollbarColor: "#d9d7d9 transparent",
          }}
        >
          <div className="relative max-w-full sm:max-w-3xl lg:max-w-4xl mx-auto space-y-4 sm:space-y-6">
            {messages.map((msg) => (
              <MessageRow key={msg.id} message={msg} verboseMode={verboseMode} />
            ))}

            <div ref={messagesEndRef} />
          </div>
        </div>
      </div>

      {/* ========== INPUT AREA ========== */}
      <div
        className="shrink-0 border-t border-app-border bg-white
                   px-3 sm:px-4 py-3 sm:py-4"
      >
        <div className="max-w-full sm:max-w-3xl lg:max-w-4xl mx-auto">
          {/* Blocked banner: no provider/model selected yet (text only) */}
          {chatBlocked && (
            <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5">
              <span className="text-sm text-amber-800">
                Configur&aacute; un proveedor y un modelo para empezar.
              </span>
            </div>
          )}

          {/* File warning banner */}
          {fileWarning && (
            <FileWarningBanner
              message={fileWarning}
              onDismiss={() => setFileWarning(null)}
            />
          )}

          {/* File chips */}
          {files.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-3">
              {files.map((f, i) => (
                <FileChip key={`${f.name}-${i}`} file={f} onRemove={() => removeFile(i)} />
              ))}
            </div>
          )}

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".csv,.xlsx,.xls,.pdf,.docx,.doc,.txt,.md,.json,.xml"
            className="hidden"
            onChange={handleFilesSelected}
          />

          {/* Textarea wrapper with buttons inside */}
          <div className="relative">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={chatBlocked}
              placeholder={
                chatBlocked
                  ? "Configurá un proveedor y un modelo para empezar..."
                  : "Escribí tu consulta..."
              }
              rows={1}
              className="w-full resize-none rounded-2xl border border-app-border
                         bg-white disabled:bg-gray-50 disabled:text-gray-400
                         text-app-text placeholder:text-app-text-secondary
                         focus:outline-none focus:ring-2 focus:ring-app-primary/30 focus:border-app-primary
                         transition-colors
                         pt-3 sm:pt-4 pb-[52px] sm:pb-[64px] pr-12 sm:pr-12 pl-12 sm:pl-12
                         min-h-[80px] sm:min-h-[100px]"
              style={{
                maxHeight: "220px",
              }}
            />

{/* Attach button - bottom left */}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={chatBlocked}
               className="absolute bottom-3 left-3 w-7 h-7 sm:w-8 sm:h-8 rounded-full
                          flex items-center justify-center
                          bg-app-primary/10 hover:bg-app-primary/20 disabled:opacity-40 disabled:cursor-not-allowed
                          text-app-primary transition-all duration-150"
              aria-label="Adjuntar archivos"
            >
              <Paperclip size={16} />
            </button>

            {/* Send / Stop button - bottom right */}
            {isStreaming ? (
              <button
                type="button"
                onClick={handleCancel}
                className="absolute bottom-3 right-3 w-7 h-7 sm:w-8 sm:h-8 rounded-full
                           flex items-center justify-center
                           bg-app-primary/20 hover:bg-app-primary/30
                           text-app-primary
                           hover:opacity-90 active:scale-95
                           transition-all duration-150 shadow-sm"
                aria-label="Detener generación"
              >
                <Square size={14} />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSend}
                disabled={!input.trim() || chatBlocked}
                className="absolute bottom-3 right-3 w-7 h-7 sm:w-8 sm:h-8 rounded-full
                           flex items-center justify-center
                           bg-gradient-to-r from-app-primary to-app-gradient-secondary
                           hover:opacity-90 active:scale-95
                           transition-all duration-150 shadow-sm
                           disabled:opacity-40 disabled:cursor-not-allowed"
                 aria-label="Enviar mensaje"
              >
                 <Send size={14} className="text-app-primary-text" />
              </button>
            )}
          {/* Línea de actividad — misma condición que el botón de detener: desde que se envía hasta que termina el turno.
              Dentro del wrapper relativo del textarea, pegada al borde inferior. */}
          {isStreaming && (
            <div
              className="activity-bar absolute left-0 right-0 pointer-events-none"
              style={{ bottom: "-4px" }}
              aria-hidden="true"
            />
          )}
          </div>
        </div>
      </div>
    </div>
  );
  },
);

