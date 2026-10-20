import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ChangeEvent,
  type FormEvent,
} from "react";
import { flushSync } from "react-dom";
import { Send, Square, Paperclip, Download } from "lucide-react";
import { FileChip, FileWarningBanner, MessageRow } from "../components/chatBlocks";
import { CreateModelSelector } from "../components/CreateModelSelector";
import type { Message, ContentBlock } from "../App";
import { saveFileWithPicker, fetchConversationMarkdown } from "../utils/conversationExport";
import { API_BASE_URL } from "../config/api";

const API = API_BASE_URL + "/api";

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

/** Generate a unique ID with safe fallback when crypto is unavailable. */
function generateId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
}

/** Mensaje de la entrevista enviado al backend (/api/create/skill). */
interface HistorialMsg {
  role: "user" | "assistant";
  content: string;
  files?: Array<{ name: string; size: number }>;
}

export function SkillInterface() {
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

  const [messages, setMessages] = useState<Message[]>([]);
  const historialRef = useRef<HistorialMsg[]>([]);
  const [input, setInput] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [fileWarning, setFileWarning] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [resultMsg, setResultMsg] = useState<string | null>(null);
  const [resultType, setResultType] = useState<"success" | "error" | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [isIterating, setIsIterating] = useState(false);

  /* ---- refs ---- */
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
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
    // Scroll de usuario (rueda): manda aunque haya un scroll programático en curso.
    if (userInteractionRef.current) {
      // Subiendo con la rueda: el autoscroll queda apagado aunque sea mínimo.
      // Bajando: se reactiva recién al llegar al umbral del fondo.
      setAutoScrollEnabled(wheelUpRef.current ? false : nearBottom);
      return;
    }
    // Solo cambiar autoScroll si NO es scroll programático.
    if (!isProgrammaticScrollRef.current) {
      setAutoScrollEnabled(nearBottom);
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

  /* ---- file validation ---- */
  const handleFilesSelected = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
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

  /* ---- validación del nombre (exacto skill.html) ---- */
  const validarNombre = useCallback((val: string): boolean => {
    if (!val) { setNameError(null); return true; }
    if (val.includes(" ")) { setNameError("No debe contener espacios."); return false; }
    if (val !== val.toLowerCase()) { setNameError("Debe estar todo en minúscula."); return false; }
    if (!/^[a-z0-9-]+$/.test(val)) { setNameError("Solo se permiten minúsculas, números y guiones."); return false; }
    setNameError(null);
    return true;
  }, []);

  /* ---- envío al backend (streaming SSE /api/create/skill) ---- */
  const enviar = useCallback(
    async (texto: string, archivos: File[], iterate: boolean = false) => {
      if (isStreaming) return;
      setInput("");
      setFiles([]);
      setChatError(null);

      const userMessage: Message = {
        id: generateId(),
        type: "user",
        content: texto,
        files: archivos.map((f) => ({ name: f.name, size: f.size })),
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

      // Guardar solo nombres para el historial de display
      const fileNames = archivos.map((f) => ({ name: f.name, size: f.size }));
      historialRef.current = [
        ...historialRef.current,
        { role: "user", content: texto, files: fileNames.length ? fileNames : undefined },
      ];

      let accumulatedContent = "";
      let accumulatedReasoning = "";
      let accumulatedBlocks: ContentBlock[] = [];

      /** Helper: agrega/actualiza el último bloque reasoning con el contenido acumulado */
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
        const formData = new FormData();
        formData.append("descripcion", descripcion);
        if (nombre) formData.append("name", nombre);
        formData.append("mensajes", JSON.stringify(historialRef.current));
        if (createModel) formData.append("model", createModel);
        if (createProvider) formData.append("provider", createProvider);
        if (iterate) formData.append("iterate", "true");
        archivos.forEach((f) => formData.append("files", f));

        const resp = await fetch(`${API}/create/skill`, {
          method: "POST",
          body: formData,
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
                  // Normalizar \n en los chunks de reasoning
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
                  // Un nuevo step: el razonamiento siguiente empieza de cero (no acumulado).
                  accumulatedReasoning = "";
                  // flushSync: fuerza el render del bloque con spinner ANTES de que
                  // llegue el resultado (los tools locales son rápidos y React los batch-ea)
                  flushSync(() => {
                    setMessages((prev) =>
                      prev.map((m) => {
                        if (m.id !== assistantId) return m;
                        const tc = Array.isArray(m.toolCalls) ? m.toolCalls : [];
                        return { ...m, blocks: [...accumulatedBlocks], toolCalls: [...tc, validated] };
                      }),
                    );
                  });
                  // Brief delay para que el spinner de la tool sea visible
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

                case "skill_action": {
                  const action = event.content?.action;
                  if (action === "question") {
                    // La entrevista devuelve el control al usuario: finalizar el mensaje y habilitar input
                    historialRef.current = [
                      ...historialRef.current,
                      { role: "assistant", content: accumulatedContent },
                    ];
                    setMessages((prev) =>
                      prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m)),
                    );
                    setIsStreaming(false);
                  } else if (action === "creating") {
                    // Sigue el stream (FASE 2/3): el typing aparece en los lapsos muertos
                    historialRef.current = [
                      ...historialRef.current,
                      { role: "assistant", content: accumulatedContent },
                    ];
                  } else if (action === "iterating") {
                    // Iteración: el LLM va a modificar la creación existente
                    historialRef.current = [
                      ...historialRef.current,
                      { role: "assistant", content: accumulatedContent },
                    ];
                  }
                  break;
                }

                case "skill_result": {
                  const data = event.content || {};
                  setMessages((prev) =>
                    prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m)),
                  );
                  setIsStreaming(false);
                  if (data.status === "success") {
                    const alreadyExists = !!(data.data && data.data.exist === "Sí" && data.data.skill);
                    let msg = data.message || "";
                    if (alreadyExists) {
                      msg = "Ya existe la skill \u00ab" + data.data.skill + "\u00bb. " + (data.data.explicacion || data.message);
                    }
                    setResultType("success");
                    setResultMsg(msg);
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

        // Stream terminado: finalizar el mensaje del asistente (el texto ya se mostró).
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
    [isStreaming, descripcion, nombre, createModel, createProvider, isIterating],
  );

  /* ---- enviar desde el chat ---- */
  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || isStreaming) return;
    const iterate = isIterating;
    setIsIterating(false);
    enviar(text, files, iterate);
  }, [input, files, isStreaming, enviar, isIterating]);

  /* ---- detener streaming ---- */
  const handleCancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
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

  /* ---- setup: submit inicial ---- */
  const handleSetupSubmit = useCallback(
    (e: FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      setSetupError(null);
      const nameVal = nombre.trim();
      const desc = descripcion.trim();
      if (!desc) { setSetupError("Completá la descripción."); return; }
      if (!nameVal) { setSetupError("El nombre es obligatorio."); return; }
      if (!validarNombre(nameVal)) { setSetupError("Corregí el campo Nombre."); return; }
      setSetupDone(true);
      enviar(desc, []);
    },
    [nombre, descripcion, enviar, validarNombre],
  );

  const setupKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const form = (e.target as HTMLElement).closest("form");
        form?.requestSubmit();
      }
    },
    [],
  );

  /* ---- render ---- */
  return (
    <div className="h-screen bg-app-bg flex flex-col overflow-hidden">
      {/* ========== HEADER skill (95px, hardcodeado — no tocar) ========== */}
      <header
        className="flex items-center shrink-0 bg-white px-4 border-b border-gray-200"
        style={{ height: "95px" }}
      >
        {/* Left: empty to balance center */}
        <div className="sm:w-44"></div>

        {/* Center: logo + title */}
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
            <span className="brand-word">synapseForge</span> — Creador de skills
          </span>
        </div>

        {/* Right: empty to balance center */}
        <div className="sm:w-44"></div>
      </header>

      {!setupDone ? (
        /* ========== SETUP FORM ========== */
        <div className="flex-1 flex items-center justify-center p-6 bg-app-bg">
          <div className="w-full max-w-lg bg-white rounded-xl border border-app-border shadow-sm p-6 space-y-5">
            <div className="text-sm text-gray-600">
              Una <strong>skill</strong> es un conjunto de instrucciones que el asistente usa para resolver una tarea específica. Es como un manual de experto: le dice cómo pensar, qué pasos seguir y qué tener en cuenta.
            </div>

            {setupError && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5">
                {setupError}
              </div>
            )}

            {noProviders && (
              <div className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5">
                No hay proveedores configurados. Configur&aacute; una API key en la
                app principal (Configuraci&oacute;n &rarr; Providers) para poder crear skills.
              </div>
            )}

            <form onSubmit={handleSetupSubmit} className="space-y-4">
              <div>
                <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
                  Nombre <span className="text-red-500">*</span>
                </label>
                <input
                  id="name"
                  type="text"
                  value={nombre}
                  onChange={(e) => {
                    setNombre(e.target.value);
                    validarNombre(e.target.value);
                  }}
                  onKeyDown={setupKeyDown}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
                  placeholder="Ej: analisis-competencia"
                />
                <p className="text-xs text-gray-400 mt-1">
                  Solo min&uacute;sculas, n&uacute;meros y guiones. Sin espacios ni may&uacute;sculas.
                </p>
                {nameError && <p className="text-xs text-red-500 mt-1">{nameError}</p>}
              </div>
              <div>
                <label htmlFor="descripcion" className="block text-sm font-medium text-gray-700 mb-1">
                  Describ&iacute; qu&eacute; necesit&aacute;s <span className="text-red-500">*</span>
                </label>
                <textarea
                  id="descripcion"
                  rows={4}
                  value={descripcion}
                  onChange={(e) => setDescripcion(e.target.value)}
                  onKeyDown={setupKeyDown}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent resize-y"
                  placeholder="Ej: Necesito una skill que analice la competencia, compare precios y productos, y genere un informe con fortalezas y debilidades."
                />
              </div>
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
                className="w-full bg-gradient-to-r from-[#4f46e5] to-[#8b5cf6] text-white text-sm font-medium px-5 py-2.5 rounded-lg transition-colors hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Comenzar
              </button>
            </form>
          </div>
        </div>
      ) : (
        /* ========== CHAT ========== */
        <div className="flex-1 flex flex-col min-h-0">
          {/* ========== MESSAGES AREA ========== */}
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

          {/* ========== INPUT AREA ========== */}
          <div
            className="shrink-0 border-t border-app-border bg-white
                       px-3 sm:px-4 py-3 sm:py-4"
          >
            <div className="max-w-full sm:max-w-3xl lg:max-w-4xl mx-auto">
              {resultMsg ? (
                /* Resultado: reemplaza el textarea. El chat sigue scrolleable arriba. */
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
                            const md = await fetchConversationMarkdown(messages, "Conversación - Creador de Skills");
                            await saveFileWithPicker(md, "conversacion-skill", ".md");
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
                            setTimeout(() => scrollToBottom("smooth"), 50);
                          }}
                          className="flex items-center gap-1 bg-app-bg-tertiary text-app-text text-sm font-medium px-4 py-2 rounded-lg hover:bg-app-bg-secondary transition-colors border border-app-border"
                        >
                          Seguir iterando
                        </button>
                      )}
                      <button
                        onClick={() => window.close()}
                        className="bg-gradient-to-r from-[#4f46e5] to-[#8b5cf6] text-white text-sm font-medium px-5 py-2 rounded-lg hover:opacity-90 transition-colors"
                      >
                        Aceptar
                      </button>
                    </div>
                </div>
              ) : (
                <>
              {chatError && (
                <div className="mb-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5">
                  {chatError}
                </div>
              )}

              {fileWarning && (
                <FileWarningBanner
                  message={fileWarning}
                  onDismiss={() => setFileWarning(null)}
                />
              )}

              {files.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-3">
                  {files.map((f, i) => (
                    <FileChip key={`${f.name}-${i}`} file={f} onRemove={() => removeFile(i)} />
                  ))}
                </div>
              )}

              <p className="text-xs text-gray-400 mb-2">
                Podés adjuntar archivos <strong>.md</strong>, <strong>.txt</strong>, <strong>.json</strong>, <strong>.csv</strong>, <strong>.yaml</strong>, <strong>.xml</strong>, <strong>.pdf</strong>, <strong>.docx</strong>, <strong>.xlsx</strong> o <strong>.xls</strong> como material de referencia para la skill.
              </p>

              {/* Hidden file input */}
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".md,.txt,.json,.csv,.yaml,.yml,.xml,.pdf,.docx,.doc,.xlsx,.xls"
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
                  placeholder="Escribí tu consulta..."
                  rows={1}
                  className="w-full resize-none rounded-2xl border border-app-border
                             bg-white
                             text-app-text placeholder:text-app-text-secondary
                             focus:outline-none focus:ring-2 focus:ring-app-primary/30 focus:border-app-primary
                             transition-colors
                             pt-3 sm:pt-4 pb-[52px] sm:pb-[64px] pr-12 sm:pr-12 pl-12 sm:pl-12
                             min-h-[80px] sm:min-h-[100px]"
                  style={{ maxHeight: "220px" }}
                />

                {/* Attach button - bottom left */}
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="absolute bottom-3 left-3 w-7 h-7 sm:w-8 sm:h-8 rounded-full
                             flex items-center justify-center
                             bg-app-primary/10 hover:bg-app-primary/20
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

                {/* Línea de actividad — misma condición que el botón de detener */}
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

export default SkillInterface;
