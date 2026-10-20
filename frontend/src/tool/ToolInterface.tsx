import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ChangeEvent,
  type FormEvent,
  type ReactElement,
} from "react";
import { flushSync } from "react-dom";
import { Send, Square, Plus, Trash2, Download, Play } from "lucide-react";
import { MessageRow } from "../components/chatBlocks";
import { CreateModelSelector } from "../components/CreateModelSelector";
import type { Message, ContentBlock } from "../App";
import { saveFileWithPicker, fetchConversationMarkdown } from "../utils/conversationExport";
import { API_BASE_URL } from "../config/api";

const API = API_BASE_URL + "/api";

/** Generate a unique ID with safe fallback when crypto is unavailable. */
function generateId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
}

/** Mensaje de la entrevista enviado al backend (/api/create/tool). */
interface HistorialMsg {
  role: "user" | "assistant";
  content: string;
}

/** Campo declarado por el usuario en el setup (parámetro o dato externo). */
interface CampoDeclarado {
  name: string;
  type: string;
  description: string;
  required: boolean;
}

const TIPOS_CAMPO = ["string", "number", "boolean", "object", "array"] as const;

export function ToolInterface() {
  /* ---- state ---- */
  const [setupDone, setSetupDone] = useState(false);
  const [nombre, setNombre] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const [setupError, setSetupError] = useState<string | null>(null);
  /* Selección efímera de modelo cloud para esta tarea (no se persiste) */
  const [createModel, setCreateModel] = useState<string | null>(null);
  const [createProvider, setCreateProvider] = useState<string | null>(null);
  /* Sin proveedores cloud configurados: la creación queda bloqueada */
  const [noProviders, setNoProviders] = useState(false);

  // Parámetros y datos externos son opcionales: el LLM los puede inferir.
  const [parametros, setParametros] = useState<CampoDeclarado[]>([]);
  const [datos, setDatos] = useState<CampoDeclarado[]>([]);
  const [parametrosAbierto, setParametrosAbierto] = useState(false);
  const [datosAbierto, setDatosAbierto] = useState(false);

  const [messages, setMessages] = useState<Message[]>([]);
  const historialRef = useRef<HistorialMsg[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [resultMsg, setResultMsg] = useState<string | null>(null);
  const [resultType, setResultType] = useState<"success" | "error" | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [isIterating, setIsIterating] = useState(false);
  /* Sandbox: tool recién creada para testing */
  const [createdToolName, setCreatedToolName] = useState<string | null>(null);
  const [sandboxOpen, setSandboxOpen] = useState(false);
  const [sandboxSchema, setSandboxSchema] = useState<Record<string, { type: string; description?: string; default?: unknown }> | null>(null);
  const [sandboxRequired, setSandboxRequired] = useState<string[]>([]);
  const [sandboxArgs, setSandboxArgs] = useState<Record<string, string>>({});
  const [sandboxResult, setSandboxResult] = useState<string | null>(null);
  const [sandboxLoading, setSandboxLoading] = useState(false);
  const [sandboxError, setSandboxError] = useState<string | null>(null);

  /* ---- refs ---- */
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  /* ---- auto scroll ---- */
  const [autoScrollEnabled, setAutoScrollEnabled] = useState(true);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const userInteractionRef = useRef(false);
  const wheelUpRef = useRef(false);
  const isProgrammaticScrollRef = useRef(false);
  const programmaticScrollTimeoutRef = useRef<number | null>(null);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
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
      scrollToBottom("smooth");
    }
  }, [messages, autoScrollEnabled, scrollToBottom]);

  const handleMessagesScroll = useCallback(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
    setShowScrollButton(!nearBottom);
    if (userInteractionRef.current) {
      setAutoScrollEnabled(wheelUpRef.current ? false : nearBottom);
      return;
    }
    if (!isProgrammaticScrollRef.current) {
      setAutoScrollEnabled(nearBottom);
    }
  }, []);

  const handleMessagesWheel = useCallback((e: { deltaY: number }) => {
    userInteractionRef.current = true;
    setTimeout(() => {
      userInteractionRef.current = false;
    }, 300);

    if (e.deltaY < 0) {
      wheelUpRef.current = true;
      setAutoScrollEnabled(false);
    } else {
      wheelUpRef.current = false;
    }
  }, []);

  /* ---- heartbeat (el watchdog del backend mata el server sin heartbeat) ---- */
  useEffect(() => {
    const interval = setInterval(() => {
      fetch(`${API}/heartbeat`, { method: "POST", keepalive: true }).catch(() => {});
    }, 10000);
    fetch(`${API}/heartbeat`, { method: "POST", keepalive: true }).catch(() => {});
    return () => clearInterval(interval);
  }, []);

  /* ---- auto-resize textarea ---- */
  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = `${Math.min(ta.scrollHeight, 220)}px`;
    }
  }, [input]);

  /* ---- validación del nombre (igual que skill) ---- */
  const validarNombre = useCallback((val: string): boolean => {
    if (!val) { setNameError(null); return true; }
    if (val.includes(" ")) { setNameError("No debe contener espacios."); return false; }
    if (val !== val.toLowerCase()) { setNameError("Debe estar todo en minúscula."); return false; }
    if (!/^[a-z0-9-]+$/.test(val)) { setNameError("Solo se permiten minúsculas, números y guiones."); return false; }
    setNameError(null);
    return true;
  }, []);

  /* ---- edición de parámetros / datos ---- */
  const actualizarCampo = (
    lista: CampoDeclarado[],
    setLista: (v: CampoDeclarado[]) => void,
    index: number,
    campo: keyof CampoDeclarado,
    valor: string | boolean,
  ): void => {
    const nuevo = lista.map((c, i) => (i === index ? { ...c, [campo]: valor } : c));
    setLista(nuevo);
  };

  const agregarCampo = (lista: CampoDeclarado[], setLista: (v: CampoDeclarado[]) => void): void => {
    setLista([...lista, { name: "", type: "string", description: "", required: false }]);
  };

  const quitarCampo = (
    lista: CampoDeclarado[],
    setLista: (v: CampoDeclarado[]) => void,
    index: number,
  ): void => {
    setLista(lista.filter((_, i) => i !== index));
  };

  /* ---- envío al backend (streaming SSE /api/create/tool) ---- */
  const enviar = useCallback(
    async (texto: string, iterate: boolean = false) => {
      if (isStreaming) return;
      setInput("");
      setChatError(null);

      const userMessage: Message = {
        id: generateId(),
        type: "user",
        content: texto,
      };
      const assistantId = generateId();
      const assistantMessage: Message = {
        id: assistantId,
        type: "assistant",
        content: "",
        isStreaming: true,
        blocks: [],
        toolCalls: [],
        toolResults: [],
      };
      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      setAutoScrollEnabled(true);
      setIsStreaming(true);
      setResultMsg(null);
      setResultType(null);

      historialRef.current = [
        ...historialRef.current,
        { role: "user", content: texto },
      ];

      let accumulatedContent = "";
      let accumulatedReasoning = "";
      let accumulatedBlocks: ContentBlock[] = [];

      const updateReasoningBlock = (): void => {
        const reasonText = accumulatedReasoning.trim();
        if (!reasonText) return;
        const last = accumulatedBlocks[accumulatedBlocks.length - 1];
        if (last && last.type === "reasoning") {
          last.content = reasonText;
        } else {
          accumulatedBlocks.push({ type: "reasoning", content: reasonText });
        }
      };

      const abort = new AbortController();
      abortRef.current = abort;

      try {
        const resp = await fetch(`${API}/create/tool`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            descripcion,
            name: nombre || null,
            mensajes: historialRef.current,
            parametros: parametros.filter((p) => p.name.trim()),
            datos: datos.filter((d) => d.name.trim()),
            model: createModel,
            provider: createProvider,
            iterate,
          }),
          signal: abort.signal,
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);

        const reader = resp.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) { buffer += decoder.decode(); break; }
          buffer += decoder.decode(value, { stream: true });

          const parts = buffer.split("\n\n");
          buffer = parts.pop() || "";
          for (const part of parts) {
            const lines = part.split("\n");
            for (const line of lines) {
              if (!line.startsWith("data: ")) continue;
              const data = line.slice(6);
              if (data === "[DONE]") break;
              let event: any;
              try { event = JSON.parse(data); } catch { continue; }

              switch (event.type) {
                case "chunk": {
                  accumulatedContent += event.content || "";
                  const last = accumulatedBlocks[accumulatedBlocks.length - 1];
                  if (last && last.type === "text") {
                    accumulatedBlocks[accumulatedBlocks.length - 1] = {
                      ...last,
                      content: last.content + (event.content || ""),
                    };
                  } else {
                    accumulatedBlocks.push({ type: "text", content: event.content || "" });
                  }
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantId
                        ? { ...m, content: accumulatedContent, blocks: [...accumulatedBlocks] }
                        : m,
                    ),
                  );
                  break;
                }

                case "reasoning": {
                  accumulatedReasoning += (event.content || "").replace(/\n+/g, " ");
                  updateReasoningBlock();
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantId ? { ...m, blocks: [...accumulatedBlocks] } : m,
                    ),
                  );
                  break;
                }

                case "tool_call": {
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
                  accumulatedReasoning = "";
                  flushSync(() => {
                    setMessages((prev) =>
                      prev.map((m) => {
                        if (m.id !== assistantId) return m;
                        const tc = Array.isArray(m.toolCalls) ? m.toolCalls : [];
                        return { ...m, blocks: [...accumulatedBlocks], toolCalls: [...tc, validated] };
                      }),
                    );
                  });
                  await new Promise((resolve) => setTimeout(resolve, 0));
                  break;
                }

                case "tool_result": {
                  if (event.content) {
                    const payload =
                      typeof event.content === "object" && event.content !== null
                        ? event.content
                        : { name: "unknown", result: event.content };
                    const toolName =
                      typeof payload.name === "string" ? payload.name : "unknown";
                    const toolResultValue =
                      "result" in payload ? payload.result : payload;
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
                }

                case "tool_action": {
                  const action = event.content?.action;
                  if (action === "question") {
                    historialRef.current = [
                      ...historialRef.current,
                      { role: "assistant", content: accumulatedContent },
                    ];
                    setMessages((prev) =>
                      prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m)),
                    );
                    setIsStreaming(false);
                  } else if (action === "creating") {
                    historialRef.current = [
                      ...historialRef.current,
                      { role: "assistant", content: accumulatedContent },
                    ];
                  } else if (action === "iterating") {
                    historialRef.current = [
                      ...historialRef.current,
                      { role: "assistant", content: accumulatedContent },
                    ];
                  }
                  break;
                }

                case "tool_result_final": {
                  const data = event.content || {};
                  setMessages((prev) =>
                    prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m)),
                  );
                  setIsStreaming(false);
                  if (data.status === "success") {
                    setResultType("success");
                    setResultMsg(data.message || "Tool creada exitosamente.");
                    const toolName = data.data?.tool || null;
                    if (toolName) setCreatedToolName(toolName);
                  } else {
                    setResultType("error");
                    setResultMsg("Error: " + (data.message || "Error desconocido"));
                  }
                  break;
                }

                case "error":
                  setMessages((prev) =>
                    prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m)),
                  );
                  setResultType("error");
                  setResultMsg(event.content || "Error desconocido");
                  setIsStreaming(false);
                  break;

                case "aborted":
                  setMessages((prev) =>
                    prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m)),
                  );
                  setIsStreaming(false);
                  break;
              }
            }
          }
        }

        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m)),
        );
      } catch (err: unknown) {
        if ((err as Error)?.name === "AbortError") {
          // Cancelado por el usuario: conservar lo generado hasta acá (como ChatInterface).
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m)),
          );
        } else {
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m)),
          );
          setChatError("Error de conexión: " + ((err as Error)?.message || "Error desconocido"));
        }
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [isStreaming, descripcion, nombre, parametros, datos, createModel, createProvider, isIterating],
  );

  /* ---- enviar desde el chat ---- */
  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || isStreaming) return;
    const iterate = isIterating;
    setIsIterating(false);
    enviar(text, iterate);
  }, [input, isStreaming, enviar, isIterating]);

  /* ---- detener streaming ---- */
  const handleCancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  /* ---- sandbox: cargar schema y abrir panel ---- */
  const openSandbox = useCallback(async () => {
    if (!createdToolName) return;
    setSandboxOpen(true);
    setSandboxResult(null);
    setSandboxError(null);
    setSandboxLoading(true);
    setTimeout(() => scrollToBottom("smooth"), 50);
    try {
      const res = await fetch(`${API}/agent/tools/${createdToolName}/schema`);
      const json = await res.json();
      if (json.status === "success" && json.data) {
        setSandboxSchema(json.data.properties || {});
        setSandboxRequired(json.data.required || []);
        // Initialize args with defaults
        const initial: Record<string, string> = {};
        const props = (json.data.properties || {}) as Record<string, { default?: unknown }>;
        for (const [k, v] of Object.entries(props)) {
          initial[k] = v.default != null ? String(v.default) : "";
        }
        setSandboxArgs(initial);
        setTimeout(() => scrollToBottom("smooth"), 50);
      } else {
        setSandboxError(json.message || "No se pudo cargar el schema.");
      }
    } catch (err) {
      setSandboxError(err instanceof Error ? err.message : "Error de conexión.");
    } finally {
      setSandboxLoading(false);
    }
  }, [createdToolName]);

  const runSandbox = useCallback(async () => {
    if (!createdToolName) return;
    setSandboxLoading(true);
    setSandboxResult(null);
    setSandboxError(null);
    try {
      // Parse args: try to infer types from schema
      const parsed: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(sandboxArgs)) {
        const propType = sandboxSchema?.[k]?.type ?? "string";
        const val = v.trim();
        if (val === "") continue;
        if (propType === "integer" || propType === "number") {
          parsed[k] = Number(val);
        } else if (propType === "boolean") {
          parsed[k] = val === "true";
        } else if (propType === "array" || propType === "object") {
          try { parsed[k] = JSON.parse(val); } catch { parsed[k] = val; }
        } else {
          parsed[k] = val;
        }
      }
      const res = await fetch(`${API}/agent/tools/${createdToolName}/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed),
      });
      const json = await res.json();
      if (json.status === "success") {
        setSandboxResult(JSON.stringify(json.data, null, 2));
      } else {
        setSandboxError(json.message || "Error ejecutando la tool.");
      }
    } catch (err) {
      setSandboxError(err instanceof Error ? err.message : "Error de conexión.");
    } finally {
      setSandboxLoading(false);
    }
  }, [createdToolName, sandboxArgs, sandboxSchema, sandboxRequired]);

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

  /* ---- setup: submit inicial ---- */
  const handleSetupSubmit = useCallback(
    (e: FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      setSetupError(null);
      const nameVal = nombre.trim();
      const desc = descripcion.trim();
      if (!desc) { setSetupError("Completá la descripción."); return; }
      // El nombre es opcional: si lo declara, debe cumplir el formato.
      if (nameVal && !validarNombre(nameVal)) { setSetupError("Corregí el campo Nombre."); return; }
      // Validar campos: si tienen texto en name, deben tener descripción.
      for (const p of parametros) {
        if (p.name.trim() && !p.description.trim()) {
          setSetupError(`El parámetro "${p.name}" necesita una descripción.`);
          return;
        }
      }
      for (const d of datos) {
        if (d.name.trim() && !d.description.trim()) {
          setSetupError(`El dato "${d.name}" necesita una descripción.`);
          return;
        }
      }
      setSetupDone(true);
      enviar(desc);
    },
    [nombre, descripcion, enviar, validarNombre, parametros, datos],
  );

  const setupKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        const target = e.target as HTMLElement;
        if (target.tagName === "TEXTAREA") return;
        e.preventDefault();
        const form = target.closest("form");
        form?.requestSubmit();
      }
    },
    [],
  );

  /* ---- editor de campos reutilizable (colapsable, opcional) ---- */
  const renderEditor = (
    titulo: string,
    ayuda: string,
    lista: CampoDeclarado[],
    setLista: (v: CampoDeclarado[]) => void,
    abierto: boolean,
    setAbierto: (v: boolean) => void,
  ): ReactElement => (
    <div className="border border-app-border rounded-lg">
      <button
        type="button"
        onClick={() => setAbierto(!abierto)}
        className="w-full flex items-center justify-between px-3 py-2 text-left"
        aria-expanded={abierto}
      >
        <div className="flex items-center gap-2">
          <Plus
            size={14}
            className={`text-app-primary transition-transform ${abierto ? "rotate-45" : ""}`}
          />
          <span className="text-sm font-medium text-app-text">{titulo}</span>
          <span className="text-xs text-app-text-secondary">(opcional)</span>
        </div>
        <span className="text-xs text-app-text-secondary">
          {lista.length > 0 ? `${lista.length} declarado${lista.length === 1 ? "" : "s"}` : "inferir por el LLM"}
        </span>
      </button>
      {abierto && (
        <div className="px-3 pb-3 space-y-2 border-t border-app-border pt-3">
          <p className="text-xs text-app-text-secondary">{ayuda}</p>
          <div className="space-y-2">
            {lista.map((campo, i) => (
              <div key={i} className="flex flex-wrap gap-2 items-start">
                <input
                  type="text"
                  value={campo.name}
                  onChange={(e) => actualizarCampo(lista, setLista, i, "name", e.target.value)}
                  placeholder="nombre"
                  className="flex-1 min-w-[120px] border border-app-border rounded-lg px-2 py-1.5 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-app-primary-light focus:border-app-primary"
                />
                <select
                  value={campo.type}
                  onChange={(e) => actualizarCampo(lista, setLista, i, "type", e.target.value)}
                  className="border border-app-border rounded-lg px-2 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-app-primary-light focus:border-app-primary"
                >
                  {TIPOS_CAMPO.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
                <input
                  type="text"
                  value={campo.description}
                  onChange={(e) => actualizarCampo(lista, setLista, i, "description", e.target.value)}
                  placeholder="descripción"
                  className="flex-[2] min-w-[180px] border border-app-border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-app-primary-light focus:border-app-primary"
                />
                <label className="flex items-center gap-1 text-xs text-app-text-secondary px-1 py-1.5 select-none">
                  <input
                    type="checkbox"
                    checked={campo.required}
                    onChange={(e) => actualizarCampo(lista, setLista, i, "required", e.target.checked)}
                    className="rounded text-app-primary focus:ring-app-primary-light"
                  />
                  req
                </label>
                <button
                  type="button"
                  onClick={() => quitarCampo(lista, setLista, i)}
                  className="p-1.5 text-app-text-secondary hover:text-red-500 hover:bg-red-50 rounded transition-colors"
                  aria-label="Quitar campo"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={() => agregarCampo(lista, setLista)}
            className="inline-flex items-center gap-1 text-xs text-app-primary hover:text-app-primary-light font-medium"
          >
            <Plus size={12} />
            Agregar campo
          </button>
        </div>
      )}
    </div>
  );

  /* ---- render ---- */
  return (
    <div className="h-screen bg-app-bg flex flex-col overflow-hidden">
      {/* ========== HEADER (95px, hardcodeado — no tocar) ========== */}
      <header
        className="flex items-center shrink-0 bg-white px-4 border-b border-gray-200"
        style={{ height: "95px" }}
      >
        <div className="sm:w-44"></div>

        <div className="flex-1 flex items-center justify-center gap-2 sm:gap-3">
          <img
            src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png"
            alt="Logo"
            className="h-9 sm:h-[95px] w-auto"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
          <span className="text-lg sm:text-2xl font-semibold" style={{ color: "#111827" }}>
            <span className="brand-word">synapseForge</span> — Creador de tools
          </span>
        </div>

        <div className="sm:w-44"></div>
      </header>

      {!setupDone ? (
        /* ========== SETUP FORM ========== */
        <div className="flex-1 flex items-start justify-center p-6 bg-app-bg overflow-y-auto">
          <div className="w-full max-w-2xl bg-white rounded-xl border border-app-border shadow-sm p-6 space-y-5 my-6">
            <div className="text-sm text-gray-600">
              Una <strong>tool externa</strong> es una función que el asistente puede invocar para hacer algo concreto: consultar una API, leer un archivo, mandar un mensaje. Acá la armás paso a paso: le decís qué hace, qué parámetros recibe del LLM y qué datos externos necesita (env vars, secrets, endpoints).
            </div>

            {setupError && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5">
                {setupError}
              </div>
            )}

            {noProviders && (
              <div className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5">
                No hay proveedores configurados. Configur&aacute; una API key en la
                app principal (Configuraci&oacute;n &rarr; Providers) para poder crear tools.
              </div>
            )}

            <form onSubmit={handleSetupSubmit} className="space-y-4">
              <div>
                <label htmlFor="tool-name" className="block text-sm font-medium text-gray-700 mb-1">
                  Nombre <span className="text-xs text-app-text-secondary">(opcional)</span>
                </label>
                <input
                  id="tool-name"
                  type="text"
                  value={nombre}
                  onChange={(e) => {
                    setNombre(e.target.value);
                    validarNombre(e.target.value);
                  }}
                  onKeyDown={setupKeyDown}
                  className="w-full border border-app-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-app-primary-light focus:border-app-primary"
                  placeholder="Ej: consultar-clima"
                />
                <p className="text-xs text-app-text-secondary mt-1">
                  Si lo dejás vacío, el LLM infiere un nombre. Si lo escribís, debe tener solo minúsculas, números y guiones.
                </p>
                {nameError && <p className="text-xs text-red-500 mt-1">{nameError}</p>}
              </div>

              <div>
                <label htmlFor="tool-descripcion" className="block text-sm font-medium text-gray-700 mb-1">
                  ¿Qué tiene que hacer la tool? <span className="text-red-500">*</span>
                </label>
                <textarea
                  id="tool-descripcion"
                  rows={4}
                  value={descripcion}
                  onChange={(e) => setDescripcion(e.target.value)}
                  className="w-full border border-app-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-app-primary-light focus:border-app-primary resize-y"
                  placeholder="Ej: Una tool que reciba una ciudad y devuelva el clima actual usando la API de OpenWeather."
                />
              </div>

              {renderEditor(
                "Parámetros (lo que el LLM le pasa al invocarla)",
                "Cada parámetro es un dato que el modelo completa cuando llama a la tool. Describilo bien para que el LLM sepa qué mandar.",
                parametros,
                setParametros,
                parametrosAbierto,
                setParametrosAbierto,
              )}

              {renderEditor(
                "Datos externos (env vars, secrets, endpoints)",
                "Cosas que la tool lee del entorno: API keys, URLs, configuración fija. NO los valores: solo declaralos para que el agente sepa qué necesita.",
                datos,
                setDatos,
                datosAbierto,
                setDatosAbierto,
              )}

              <CreateModelSelector
                onApply={(m, p) => {
                  setCreateModel(m);
                  setCreateProvider(p);
                }}
                onProvidersChange={(count) => setNoProviders(count === 0)}
              />

              <button
                type="submit"
                disabled={noProviders}
                className="w-full bg-gradient-to-r from-app-primary to-app-gradient-secondary text-white text-sm font-medium px-5 py-2.5 rounded-lg transition-colors hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Comenzar
              </button>
            </form>
          </div>
        </div>
      ) : (
        /* ========== CHAT ========== */
        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex-1 min-h-0 relative">
            {showScrollButton && (
              <div className="absolute left-1/2 transform -translate-x-1/2 z-10" style={{ bottom: "30px" }}>
                <button
                  type="button"
                  onClick={() => {
                    wheelUpRef.current = false;
                    setAutoScrollEnabled(true);
                    scrollToBottom("smooth");
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
                  <MessageRow key={msg.id} message={msg} verboseMode={true} showCopyButton={false} autoCloseBlocks />
                ))}
              </div>
            </div>
          </div>

          <div
            className="shrink-0 border-t border-app-border bg-white
                       px-3 sm:px-4 py-3 sm:py-4"
          >
            <div className="max-w-full sm:max-w-3xl lg:max-w-4xl mx-auto">
              {resultMsg ? (
                <div className="relative rounded-2xl border border-app-border bg-white p-4 sm:p-5 flex flex-col items-center gap-3 text-center">
                  <div
                    className={`w-10 h-10 rounded-full flex items-center justify-center ${
                      resultType === "error" ? "bg-red-100" : "bg-green-100"
                    }`}
                  >
                    {resultType === "error" ? (
                      <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    ) : (
                      <svg className="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </div>
                   <p className="text-sm text-app-text">{resultMsg}</p>
                   {downloadError && (
                     <p className="text-sm text-red-600">{downloadError}</p>
                   )}
                    <div className="flex gap-2">
                      <button
                        onClick={async () => {
                          try {
                            setDownloadError(null);
                            const md = await fetchConversationMarkdown(messages, "Conversación - Creador de Tools");
                            await saveFileWithPicker(md, "conversacion-tool", ".md");
                          } catch (err) {
                            setDownloadError(err instanceof Error ? err.message : "No se pudo descargar la conversación.");
                          }
                        }}
                        className="flex items-center gap-1 bg-app-bg-tertiary text-app-text text-sm font-medium px-4 py-2 rounded-lg hover:bg-app-bg-secondary transition-colors border border-app-border"
                      >
                        <Download size={14} />
                        Descargar conversación
                      </button>
                      {resultType === "success" && (
                        <button
                          onClick={() => {
                            setResultMsg(null);
                            setResultType(null);
                            setIsIterating(true);
                            setCreatedToolName(null);
                            setSandboxOpen(false);
                            setSandboxSchema(null);
                            setSandboxArgs({});
                            setSandboxResult(null);
                            setSandboxError(null);
                            setTimeout(() => scrollToBottom("smooth"), 50);
                          }}
                          className="flex items-center gap-1 bg-app-bg-tertiary text-app-text text-sm font-medium px-4 py-2 rounded-lg hover:bg-app-bg-secondary transition-colors border border-app-border"
                        >
                          Seguir iterando
                        </button>
                      )}
                      {resultType === "success" && createdToolName && (
                        <button
                          onClick={openSandbox}
                          className="flex items-center gap-1 bg-app-bg-tertiary text-app-text text-sm font-medium px-4 py-2 rounded-lg hover:bg-app-bg-secondary transition-colors border border-app-border"
                        >
                          <Play size={14} />
                          Probar
                        </button>
                      )}
                      <button
                        onClick={() => window.close()}
                        className="bg-gradient-to-r from-app-primary to-app-gradient-secondary text-white text-sm font-medium px-5 py-2 rounded-lg hover:opacity-90 transition-colors"
                      >
                        Aceptar
                      </button>
                    </div>

                    {/* Sandbox panel */}
                    {sandboxOpen && (
                      <div className="mt-3 rounded-2xl border border-app-border bg-white p-4 sm:p-5">
                        <div className="flex items-center justify-between mb-3">
                          <h3 className="text-sm font-semibold text-app-text">
                            Sandbox — {createdToolName}
                          </h3>
                          <button
                            onClick={() => setSandboxOpen(false)}
                            className="text-app-text-secondary hover:text-app-text text-xs"
                          >
                            Cerrar
                          </button>
                        </div>

                        {sandboxLoading && (
                          <p className="text-xs text-app-text-secondary animate-pulse">Cargando...</p>
                        )}
                        {sandboxError && (
                          <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-2">
                            {sandboxError}
                          </p>
                        )}

                        {sandboxSchema && !sandboxLoading && (
                          <div className="space-y-2">
                            {Object.entries(sandboxSchema).map(([key, prop]) => (
                              <div key={key}>
                                <label className="block text-xs font-medium text-app-text mb-0.5">
                                  {key}
                                  {sandboxRequired.includes(key) && (
                                    <span className="text-red-500 ml-0.5">*</span>
                                  )}
                                  {prop.description && (
                                    <span className="text-app-text-secondary ml-1">
                                      — {prop.description}
                                    </span>
                                  )}
                                </label>
                                <input
                                  type="text"
                                  value={sandboxArgs[key] ?? ""}
                                  onChange={(e) =>
                                    setSandboxArgs((prev) => ({ ...prev, [key]: e.target.value }))
                                  }
                                  placeholder={prop.type}
                                  className="w-full text-sm rounded-lg border border-app-border px-3 py-1.5
                                             bg-app-bg text-app-text placeholder:text-app-text-secondary
                                             focus:outline-none focus:ring-1 focus:ring-app-primary/30 focus:border-app-primary"
                                />
                              </div>
                            ))}
                            <button
                              onClick={runSandbox}
                              disabled={sandboxLoading}
                              className="mt-2 w-full text-sm font-medium text-white bg-gradient-to-r from-app-primary to-app-gradient-secondary
                                         py-2 rounded-lg hover:opacity-90 transition-colors disabled:opacity-50"
                            >
                              Ejecutar
                            </button>
                          </div>
                        )}

                        {sandboxResult && (
                          <div className="mt-3 rounded-lg bg-app-bg border border-app-border p-3">
                            <p className="text-xs font-medium text-app-text mb-1">Resultado:</p>
                            <pre className="text-xs text-app-text whitespace-pre-wrap break-all overflow-auto max-h-60">
                              {sandboxResult}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}
                </div>
              ) : (
                <>
                  {chatError && (
                    <div className="mb-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5">
                      {chatError}
                    </div>
                  )}

                  <div className="relative">
                    <textarea
                      ref={textareaRef}
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="Escribí tu consulta..."
                      rows={1}
                      className="w-full resize-none rounded-2xl border border-app-border
                                 bg-white
                                 text-app-text placeholder:text-app-text-secondary
                                 focus:outline-none focus:ring-2 focus:ring-app-primary/30 focus:border-app-primary
                                 transition-colors
                                 pt-3 sm:pt-4 pb-[44px] sm:pb-[44px] pr-12 sm:pr-12 pl-4 sm:pl-4
                                 min-h-[80px] sm:min-h-[100px]"
                      style={{ maxHeight: "220px" }}
                    />

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
                        disabled={!input.trim()}
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

                    {isStreaming && (
                      <div
                        className="activity-bar absolute left-0 right-0 pointer-events-none"
                        style={{ bottom: "-4px" }}
                        aria-hidden="true"
                      />
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ToolInterface;