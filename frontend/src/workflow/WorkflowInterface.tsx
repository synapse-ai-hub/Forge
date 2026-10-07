import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type FormEvent,
} from "react";
import { flushSync } from "react-dom";
import { Send, Square, Download } from "lucide-react";
import { MessageRow } from "../components/chatBlocks";
import { CreateModelSelector } from "../components/CreateModelSelector";
import type { Message, ContentBlock } from "../App";
import { saveFileWithPicker, fetchConversationMarkdown } from "../utils/conversationExport";

const API = (import.meta.env.VITE_URL_BASE || "http://localhost:8000") + "/api";

/** Generate a unique ID with safe fallback when crypto is unavailable. */
function generateId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
}

/** Mensaje de la entrevista enviado al backend (/api/create/workflow). */
interface HistorialMsg {
  role: "user" | "assistant";
  content: string;
}

export function WorkflowInterface() {
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
  const [isStreaming, setIsStreaming] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [resultMsg, setResultMsg] = useState<string | null>(null);
  const [resultType, setResultType] = useState<"success" | "error" | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [isIterating, setIsIterating] = useState(false);
  /* ---- editor YAML (validar/guardar, mismos endpoints que el panel) ---- */
  const [yaml, setYaml] = useState("");
  const [yamlMsg, setYamlMsg] = useState<string | null>(null);
  const [yamlBusy, setYamlBusy] = useState(false);

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

  /* ---- heartbeat ---- */
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

  /* ---- validación del nombre ---- */
  const validarNombre = useCallback((val: string): boolean => {
    if (!val) { setNameError(null); return true; }
    if (val.includes(" ")) { setNameError("No debe contener espacios."); return false; }
    if (val !== val.toLowerCase()) { setNameError("Debe estar todo en minúscula."); return false; }
    if (!/^[a-z0-9-_]+$/.test(val)) { setNameError("Solo se permiten minúsculas, números, guiones y guion bajo."); return false; }
    setNameError(null);
    return true;
  }, []);

  /* ---- envío al backend (streaming SSE /api/create/workflow) ---- */
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
        const resp = await fetch(`${API}/create/workflow`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            descripcion,
            name: nombre || null,
            mensajes: historialRef.current,
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

                case "workflow_action": {
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

                case "workflow_result_final": {
                  const data = event.content || {};
                  setMessages((prev) =>
                    prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m)),
                  );
                  setIsStreaming(false);
                  if (data.status === "success") {
                    setResultType("success");
                    setResultMsg(data.message || "Workflow creado exitosamente.");
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
    enviar(text, iterate);
  }, [input, isStreaming, enviar, isIterating]);

  /* ---- detener streaming ---- */
  const handleCancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  /* ---- YAML: generar con agente / validar / guardar ---- */
  const handleGenerateYaml = useCallback(async () => {
    const desc = descripcion.trim();
    if (!desc) { setYamlMsg("Completá la descripción primero."); return; }
    setYamlBusy(true);
    setYamlMsg("Generando con el agente...");
    try {
      const resp = await fetch(`${API}/config/workflows/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: desc }),
      });
      const data = await resp.json().catch(() => null);
      if (!resp.ok || !data || data.status === "error") {
        throw new Error((data && data.message) || `HTTP ${resp.status}`);
      }
      setYaml(data.data?.yaml || "");
      if (data.data?.name && !nombre.trim()) setNombre(data.data.name);
      setYamlMsg("YAML generado. Revisalo y guardalo.");
    } catch (err) {
      setYamlMsg(err instanceof Error ? err.message : "No se pudo generar.");
    } finally {
      setYamlBusy(false);
    }
  }, [descripcion, nombre]);

  const handleValidateYaml = useCallback(async () => {
    if (!yaml.trim()) { setYamlMsg("No hay YAML para validar."); return; }
    setYamlBusy(true);
    try {
      const resp = await fetch(`${API}/config/workflows/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ yaml }),
      });
      const data = await resp.json().catch(() => null);
      setYamlMsg((data && data.message) || (resp.ok ? "Workflow válido." : "YAML inválido."));
    } catch (err) {
      setYamlMsg(err instanceof Error ? err.message : "Error validando.");
    } finally {
      setYamlBusy(false);
    }
  }, [yaml]);

  const handleSaveYaml = useCallback(async () => {
    const nameVal = nombre.trim();
    if (!nameVal || !yaml.trim()) { setYamlMsg("Nombre y YAML requeridos."); return; }
    setYamlBusy(true);
    try {
      const resp = await fetch(`${API}/config/workflows/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: nameVal, yaml }),
      });
      const data = await resp.json().catch(() => null);
      if (!resp.ok || !data || data.status === "error") {
        throw new Error((data && data.message) || `HTTP ${resp.status}`);
      }
      setYamlMsg(`Workflow «${nameVal}» guardado.`);
    } catch (err) {
      setYamlMsg(err instanceof Error ? err.message : "No se pudo guardar.");
    } finally {
      setYamlBusy(false);
    }
  }, [nombre, yaml]);

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
      if (nameVal && !validarNombre(nameVal)) { setSetupError("Corregí el campo Nombre."); return; }
      setSetupDone(true);
      enviar(desc);
    },
    [nombre, descripcion, enviar, validarNombre],
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

  /* ---- render ---- */
  return (
    <div className="h-screen bg-app-bg flex flex-col overflow-hidden">
      {/* ========== HEADER ========== */}
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
            <span className="brand-word">synapseForge</span> — Creador de workflows
          </span>
        </div>

        <div className="sm:w-44"></div>
      </header>

      {!setupDone ? (
        /* ========== SETUP FORM ========== */
        <div className="flex-1 flex items-start justify-center p-6 bg-app-bg overflow-y-auto">
          <div className="w-full max-w-2xl bg-white rounded-xl border border-app-border shadow-sm p-6 space-y-5 my-6">
            <div className="text-sm text-gray-600">
              Un <strong>workflow</strong> es un flujo determinista de nodos (agentes, tools o RAG) que se ejecutan en steps: mismo step en paralelo, distinto step en secuencia. Describí qué tiene que hacer y el agente lo va a diseñar como YAML válido.
            </div>

            {setupError && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5">
                {setupError}
              </div>
            )}

            {noProviders && (
              <div className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5">
                No hay proveedores configurados. Configur&aacute; una API key en la
                app principal (Configuraci&oacute;n &rarr; Providers) para poder crear workflows.
              </div>
            )}

            <form onSubmit={handleSetupSubmit} className="space-y-4">
              <div>
                <label htmlFor="workflow-name" className="block text-sm font-medium text-gray-700 mb-1">
                  Nombre <span className="text-xs text-app-text-secondary">(opcional)</span>
                </label>
                <input
                  id="workflow-name"
                  type="text"
                  value={nombre}
                  onChange={(e) => {
                    setNombre(e.target.value);
                    validarNombre(e.target.value);
                  }}
                  onKeyDown={setupKeyDown}
                  className="w-full border border-app-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-app-primary-light focus:border-app-primary"
                  placeholder="Ej: reporte-diario"
                />
                <p className="text-xs text-app-text-secondary mt-1">
                  Si lo dejás vacío, el LLM infiere un nombre. Si lo escribís, debe tener solo minúsculas, números y guiones.
                </p>
                {nameError && <p className="text-xs text-red-500 mt-1">{nameError}</p>}
              </div>

              <div>
                <label htmlFor="workflow-descripcion" className="block text-sm font-medium text-gray-700 mb-1">
                  ¿Qué tiene que hacer el workflow? <span className="text-red-500">*</span>
                </label>
                <textarea
                  id="workflow-descripcion"
                  rows={4}
                  value={descripcion}
                  onChange={(e) => setDescripcion(e.target.value)}
                  className="w-full border border-app-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-app-primary-light focus:border-app-primary resize-y"
                  placeholder="Ej: Un workflow que busque ventas del día con una tool, las analice con un agente y guarde el resumen. Dos steps: búsqueda y análisis."
                />
                <p className="text-xs text-app-text-secondary mt-1">
                  Describí los pasos, qué agentes/tools usa y cuál es el resultado final. El LLM va a diseñar los nodos y steps.
                </p>
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
                  <MessageRow key={msg.id} message={msg} verboseMode={true} showCopyButton={false} />
                ))}
              </div>
            </div>
          </div>

          <div
            className="shrink-0 border-t border-app-border bg-white
                       px-3 sm:px-4 py-3 sm:py-4"
          >
            <div className="max-w-full sm:max-w-3xl lg:max-w-4xl mx-auto">
              {/* ========== YAML DEL WORKFLOW ========== */}
              <div className="mb-3 rounded-2xl border border-app-border bg-white p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-app-text">YAML del workflow</span>
                  <button
                    type="button"
                    disabled={yamlBusy}
                    onClick={handleGenerateYaml}
                    className="text-xs bg-app-primary hover:opacity-90 text-white px-3 py-1.5 rounded disabled:opacity-50"
                  >
                    {yamlBusy ? "Generando..." : "Generar con agente"}
                  </button>
                </div>
                <textarea
                  value={yaml}
                  onChange={(e) => setYaml(e.target.value)}
                  placeholder="YAML del workflow..."
                  rows={8}
                  spellCheck={false}
                  className="w-full text-[11px] font-mono px-2 py-1.5 rounded border border-app-border bg-white text-app-text"
                />
                {yamlMsg && <p className="text-xs text-app-text-secondary">{yamlMsg}</p>}
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={yamlBusy}
                    onClick={handleValidateYaml}
                    className="text-xs px-3 py-1.5 rounded border border-app-border hover:bg-app-bg-tertiary disabled:opacity-50"
                  >
                    Validar
                  </button>
                  <button
                    type="button"
                    disabled={yamlBusy}
                    onClick={handleSaveYaml}
                    className="text-xs bg-app-primary hover:opacity-90 text-white px-3 py-1.5 rounded disabled:opacity-50"
                  >
                    Guardar
                  </button>
                </div>
              </div>
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
                            const md = await fetchConversationMarkdown(messages, "Conversación - Creador de Workflows");
                            await saveFileWithPicker(md, "conversacion-workflow", ".md");
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
                        className="bg-gradient-to-r from-app-primary to-app-gradient-secondary text-white text-sm font-medium px-5 py-2 rounded-lg hover:opacity-90 transition-colors"
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

export default WorkflowInterface;
