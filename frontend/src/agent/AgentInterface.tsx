import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type FormEvent,
} from "react";
import { flushSync } from "react-dom";
import { Send, Square, Download, ShieldCheck } from "lucide-react";
import { MessageRow } from "../components/chatBlocks";
import { CreateModelSelector } from "../components/CreateModelSelector";
import { ResourceCards } from "../components/ResourceCards";
import {
  EMPTY_SELECTION,
  selectionFromSetup,
  selectionToRequest,
  type ResourceSelection,
} from "../utils/resourceSelection";
import type { Message, ContentBlock } from "../App";
import { saveFileWithPicker, fetchConversationMarkdown } from "../utils/conversationExport";
import { API_BASE_URL } from "../config/api";
import { CreatorHistory } from "../components/CreatorHistory";
import { newCreatorId, type CreatorConversation } from
"../services/creatorHistoryService";
import { useCreatorVerify, VerifyToastBanner } from "../hooks/useCreatorVerify";

const API = API_BASE_URL + "/api";

/** Generate a unique ID with safe fallback when crypto is unavailable. */
function generateId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
}

export function AgentInterface() {
  /* ---- state ---- */
  const [setupDone, setSetupDone] = useState(false);
  const [nombre, setNombre] = useState("");
  const [descripcion, setDescripcion] = useState("");
  /* Recursos que el usuario eligió en las tarjetas de permisos: son obligatorios para el creador */
  const [seleccion, setSeleccion] = useState<ResourceSelection>(EMPTY_SELECTION);
  const [nameError, setNameError] = useState<string | null>(null);
  const [setupError, setSetupError] = useState<string | null>(null);
  /* Selección efímera de modelo cloud para esta tarea (no se persiste) */
  const [createModel, setCreateModel] = useState<string | null>(null);
  const [createProvider, setCreateProvider] = useState<string | null>(null);
  /* Sin proveedores cloud configurados: la creación queda bloqueada */
  const [noProviders, setNoProviders] = useState(false);

  const [messages, setMessages] = useState<Message[]>([]);
  /* Conversation of the creator: the history sidebar reopens it later. */
  const creatorIdRef = useRef<string>(newCreatorId());
  const [historyKey, setHistoryKey] = useState(0);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [resultMsg, setResultMsg] = useState<string | null>(null);
  const [resultType, setResultType] = useState<"success" | "error" | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  /* Shared verification (decision model verdict) for creator pages. */
  const { verifying, verifyToast, verificar } = useCreatorVerify("agent");

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
    if (!/^[a-z0-9-]+$/.test(val)) { setNameError("Solo se permiten minúsculas, números y guiones."); return false; }
    setNameError(null);
    return true;
  }, []);

  /* ---- envío al backend (streaming SSE /api/create/agent) ---- */
  const enviar = useCallback(
    async (texto: string) => {
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
        const resp = await fetch(`${API}/create/agent`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            descripcion,
            name: nombre || null,
            creator_id: creatorIdRef.current,
            model: createModel,
            provider: createProvider,
            ...selectionToRequest(seleccion),
          }),
          signal: abort.signal,
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);

        const reader = resp.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let retryActive = false;

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

              // Transient retry notice (as in ChatInterface): cleared on the next event.
              if (retryActive && event.type !== "retry") {
                retryActive = false;
                setMessages((prev) =>
                  prev.map((m) => (m.id === assistantId ? { ...m, retryNotice: null } : m)),
                );
              }

              switch (event.type) {
                case "retry":
                  retryActive = true;
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantId ? { ...m, retryNotice: String(event.content || "") } : m,
                    ),
                  );
                  break;

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

                case "agent_result_final": {
                  const data = event.content || {};
                  setMessages((prev) =>
                    prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m)),
                  );
                  setIsStreaming(false);
                  if (data.status === "success") {
                    setResultType("success");
                    setResultMsg(data.message || "Agente creado exitosamente.");
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
        setHistoryKey((k) => k + 1);
      }
    },
    [isStreaming, descripcion, nombre, createModel, createProvider, seleccion],
  );

  /* ---- enviar desde el chat ---- */
  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || isStreaming) return;
    enviar(text);
  }, [input, isStreaming, enviar]);

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

  /* ---- historial del creador: empezar una conversación nueva o reabrir una ---- */
  /** Start a new conversation of the creator: stop the stream and clear the page. */
  const resetConversation = useCallback((): void => {
    abortRef.current?.abort();
    creatorIdRef.current = newCreatorId();
    setMessages([]);
    setSetupDone(false);
    setNombre("");
    setDescripcion("");
    setSeleccion(EMPTY_SELECTION);
    setInput("");
    setChatError(null);
    setResultMsg(null);
    setResultType(null);
    setHistoryKey((k) => k + 1);
  }, []);

  /**
   * Reopen a stored conversation of the creator to keep modifying what was created.
   *
   * @param c - Conversation loaded from the history.
   */
  const restoreConversation = useCallback((c: CreatorConversation): void => {
    abortRef.current?.abort();
    const setup = c.setup as Record<string, any>;
    creatorIdRef.current = c.creator_id;
    setNombre(typeof setup.name === "string" ? setup.name : "");
    setDescripcion(typeof setup.descripcion === "string" ? setup.descripcion : "");
    setSeleccion(selectionFromSetup(setup));
    setMessages(c.messages.map((m) => ({ ...m, id: generateId(), isStreaming: false }) as Message));
    const answered = c.result && c.result.action !== "question" ? c.result : null;
    setResultType(answered ? (answered.status === "success" ? "success" : "error") : null);
    setResultMsg(
      answered ? (answered.status === "success" ? answered.message : "Error: " + answered.message) : null,
    );
    setInput("");
    setChatError(null);
    setSetupDone(true);
    setHistoryKey((k) => k + 1);
  }, []);

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
            <span className="brand-word">synapseForge</span> — Creador de agentes
          </span>
        </div>

        <div className="sm:w-44"></div>
      </header>

      <div className="flex flex-1 min-h-0 overflow-hidden">
        <CreatorHistory
          kind="agent"
          activeId={creatorIdRef.current}
          refreshKey={historyKey}
          onSelect={restoreConversation}
          onNew={resetConversation}
          onDeletedActive={resetConversation}
          disabled={isStreaming}
        />
        <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">

      {!setupDone ? (
        /* ========== SETUP FORM ========== */
        <div className="flex-1 flex items-start justify-center p-6 bg-app-bg overflow-y-auto">
          <div className="w-full max-w-2xl bg-white rounded-xl border border-app-border shadow-sm p-6 space-y-5 my-6">
            <div className="text-sm text-gray-600">
              Un <strong>agente especializado</strong> es un asistente de IA con un rol específico, su propio system prompt, modelo y permisos de tools/skills. Los agentes especializados son más efectivos: cargan solo lo necesario, gastan menos contexto y cometen menos errores.
            </div>

            {setupError && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5">
                {setupError}
              </div>
            )}

            {noProviders && (
              <div className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5">
                No hay proveedores configurados. Configur&aacute; una API key en la
                app principal (Configuraci&oacute;n &rarr; Providers) para poder crear agentes.
              </div>
            )}

            <form onSubmit={handleSetupSubmit} className="space-y-4">
              <div>
                <label htmlFor="agent-name" className="block text-sm font-medium text-gray-700 mb-1">
                  Nombre <span className="text-xs text-app-text-secondary">(opcional)</span>
                </label>
                <input
                  id="agent-name"
                  type="text"
                  value={nombre}
                  onChange={(e) => {
                    setNombre(e.target.value);
                    validarNombre(e.target.value);
                  }}
                  onKeyDown={setupKeyDown}
                  className="w-full border border-app-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-app-primary-light focus:border-app-primary"
                  placeholder="Ej: analizador-de-datos"
                />
                <p className="text-xs text-app-text-secondary mt-1">
                  Si lo dejás vacío, el LLM infiere un nombre. Si lo escribís, debe tener solo minúsculas, números y guiones.
                </p>
                {nameError && <p className="text-xs text-red-500 mt-1">{nameError}</p>}
              </div>

              <div>
                <label htmlFor="agent-descripcion" className="block text-sm font-medium text-gray-700 mb-1">
                  ¿Qué tiene que hacer el agente? <span className="text-red-500">*</span>
                </label>
                <textarea
                  id="agent-descripcion"
                  rows={4}
                  value={descripcion}
                  onChange={(e) => setDescripcion(e.target.value)}
                  className="w-full border border-app-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-app-primary-light focus:border-app-primary resize-y"
                  placeholder="Ej: Un agente que analice datos de ventas y genere reportes con gráficos. Solo usa tools de lectura y shell. No modifica archivos."
                />
                <p className="text-xs text-app-text-secondary mt-1">
                  Describí el rol, qué debe hacer y qué NO debe hacer. El LLM va a inferir qué tools y skills necesita.
                </p>
              </div>

              <ResourceCards
                kinds={["agentes", "tools", "skills", "rag"]}
                selection={seleccion}
                onChange={setSeleccion}
                idPrefix="agent"
              />

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
                            const md = await fetchConversationMarkdown(messages, "Conversación - Creador de Agentes");
                            await saveFileWithPicker(md, "conversacion-agente", ".md");
                          } catch (err) {
                            setDownloadError(err instanceof Error ? err.message : "No se pudo descargar la conversación.");
                          }
                        }}
                        className="flex items-center gap-1 bg-app-bg-tertiary text-app-text text-sm font-medium px-4 py-2 rounded-lg hover:bg-app-bg-secondary transition-colors border border-app-border"
                      >
                        <Download size={14} />
                        Descargar conversación
                      </button>
                      <button
                        onClick={() => window.close()}
                        className="bg-gradient-to-r from-app-primary to-app-gradient-secondary text-white text-sm font-medium px-5 py-2 rounded-lg hover:opacity-90 transition-colors"
                      >
                        Aceptar
                      </button>
                    </div>
                </div>
              ) : null}
              <>
                  {chatError && (
                    <div className="mb-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5">
                      {chatError}
                    </div>
                  )}

                  <div className="flex gap-2 mb-2">
                    <button
                      type="button"
                      onClick={() => void verificar(creatorIdRef.current, isStreaming || messages.length === 0)}
                      disabled={verifying || isStreaming || messages.length === 0}
                      title="Verificar si el trabajo cumple con lo pedido"
                      className="flex items-center gap-1 bg-app-bg-tertiary text-app-text text-sm font-medium px-4 py-2 rounded-lg hover:bg-app-bg-secondary transition-colors border border-app-border disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      <ShieldCheck size={14} />
                      {verifying ? "Verificando..." : "Verificar"}
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          setDownloadError(null);
                          const md = await fetchConversationMarkdown(messages, "Conversación - Creador de Agentes");
                          await saveFileWithPicker(md, "conversacion-agente", ".md");
                        } catch (err) {
                          setDownloadError(err instanceof Error ? err.message : "No se pudo descargar la conversación.");
                        }
                      }}
                      className="flex items-center gap-1 bg-app-bg-tertiary text-app-text text-sm font-medium px-4 py-2 rounded-lg hover:bg-app-bg-secondary transition-colors border border-app-border"
                    >
                      <Download size={14} />
                      Descargar conversación
                    </button>
                  </div>
                  {downloadError && (
                    <p className="text-sm text-red-600 mb-2">{downloadError}</p>
                  )}
                  <VerifyToastBanner toast={verifyToast} />

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
            </div>
          </div>
        </div>
      )}
        </div>
      </div>
    </div>
  );
}

export default AgentInterface;
