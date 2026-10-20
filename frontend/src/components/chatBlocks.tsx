import {
  useState,
  useRef,
  useEffect,
  useLayoutEffect,
  useCallback,
  useMemo,
  useId,
} from "react";
import {
  Brain,
  User,
  Copy,
  ThumbsUp,
  ThumbsDown,
  ChevronDown,
  Loader2,
  X,
} from "lucide-react";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { renderMermaid } from "../utils/mermaid";
import type { Message, SubagentEvent, SubagentStep } from "../App";
import type { FeedbackType } from "../services/feedbackService";
import { API_BASE_URL } from "../config/api";

/* ------------------------------------------------------------------ */
/*  TypingIndicator                                                   */
/* ------------------------------------------------------------------ */

/** Bouncing-dots typing indicator. */
/**
 * A string result is an error only when it is the tool error payload
 * (`{"error": ...}`, possibly wrapped in `<tool_output>` when reloaded from
 * history). The word "error" inside normal content (a log, a file) is not.
 */
function isErrorText(text: string): boolean {
  const body = text.replace(/^\s*<tool_output[^>]*>\s*/, "");
  return /^\s*\{\s*"error"\s*:/.test(body);
}

function TypingIndicator({ label = "Trabajando..." }: { label?: string }) {
  return (
    <div className="flex items-center gap-1.5 px-1" role="status" aria-label="Escribiendo...">
      <span className="typing-dot h-2 w-2 rounded-full bg-app-primary" />
      <span className="typing-dot h-2 w-2 rounded-full bg-app-primary" />
      <span className="typing-dot h-2 w-2 rounded-full bg-app-primary" />
      <span className="text-xs text-app-text-secondary ml-1">
        {label}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ReasoningBlock                                                    */
/* ------------------------------------------------------------------ */

/** Collapsible reasoning block — cada bloque de razonamiento del LLM, con el mismo estilo de tarjeta que las tools. */
function ReasoningBlock({ content, defaultOpen, isStreaming = false }: { content: string; defaultOpen?: boolean; isStreaming?: boolean }) {
  const [open, setOpen] = useState(defaultOpen ?? false);
  const panelId = `reasoning-${useId()}`;
  const text = content?.trim() || "";

  // Auto-close when streaming ends (open during runtime, closed when done)
  // NOTE: hook must be before any conditional return (Rules of Hooks)
  useEffect(() => {
    if (!isStreaming && open) {
      setOpen(false);
    }
  }, [isStreaming]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!text) return null;
  return (
    <div className="rounded-lg border border-app-border bg-app-bg-tertiary p-2.5">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex w-full items-center justify-between gap-2 text-left text-xs hover:text-app-primary"
      >
        <span className="flex items-center gap-1 text-app-text-secondary">
          <span className="font-medium">Razonamiento</span>
        </span>
        <ChevronDown
          size={14}
          className={`shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div id={panelId} className="mt-2 text-xs text-app-text-secondary">
          <MarkdownRenderer content={text} />
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  FileWarningBanner                                                 */
/* ------------------------------------------------------------------ */

/** Warning banner for rejected files. */
function FileWarningBanner({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss: () => void;
}) {
  return (
    <div
      className="flex items-center gap-2 px-4 py-2 mb-3 rounded-xl text-xs
                 bg-red-50 border border-red-200 text-red-700"
    >
      <span className="flex-1">{message}</span>
      <button
        onClick={onDismiss}
        className="shrink-0 rounded-full p-0.5 hover:bg-red-100 transition-colors"
        aria-label="Cerrar advertencia"
      >
        <X size={14} />
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  FileChip                                                          */
/* ------------------------------------------------------------------ */

/** File chip preview above the textarea. */
function FileChip({
  file,
  onRemove,
}: {
  file: File;
  onRemove: () => void;
}) {
  const sizeLabel =
    file.size < 1024 * 1024
      ? `${(file.size / 1024).toFixed(0)} KB`
      : `${(file.size / (1024 * 1024)).toFixed(1)} MB`;

  return (
    <div
      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs
                 bg-app-primary/10 border border-app-primary/20 text-app-text"
    >
      <span className="truncate max-w-[120px] sm:max-w-[200px]">{file.name}</span>
      <span className="text-app-text-secondary shrink-0">{sizeLabel}</span>
      <button
        onClick={onRemove}
        className="shrink-0 rounded-full p-0.5 hover:bg-app-primary/15 transition-colors"
        aria-label={`Remove ${file.name}`}
      >
        <X size={12} />
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  MarkdownRenderer                                                  */
/* ------------------------------------------------------------------ */

/** Renders markdown content to HTML with XSS sanitization + Mermaid diagrams. */
function MarkdownRenderer({ content }: { content: string }) {
  const sanitized = useMemo(() => {
    if (!content) return null;
    try {
      const html = marked.parse(content, { async: false }) as string;
      return DOMPurify.sanitize(openLinksInNewTab(html), { ADD_ATTR: ["target"] });
    } catch {
      return null;
    }
  }, [content]);

  useLayoutEffect(() => {
    if (sanitized !== null) void renderMermaid();
  }, [sanitized]);

  if (!content || sanitized === null) return <>{content}</>;
  return (
    <div
      className="markdown-content text-sm leading-relaxed text-app-text"
      dangerouslySetInnerHTML={{ __html: sanitized }}
    />
  );
}

/** Agrega target="_blank" rel="noopener noreferrer" a todos los links. */
function openLinksInNewTab(html: string): string {
  return html.replace(/<a\s+href=/g, '<a target="_blank" rel="noopener noreferrer" href=');
}

/* ------------------------------------------------------------------ */
/*  ToolCallBlock                                                     */
/* ------------------------------------------------------------------ */

function ToolCallBlock({
  toolCall,
  result,
  isStreaming = false,
  waitingForChunk = false,
  subagentEvents,
  isLatestTool = true,
  taskIndex = 0,
}: {
  toolCall: { tool: string; parameters?: Record<string, any> };
  result?: { tool: string; result: any };
  isStreaming?: boolean;
  waitingForChunk?: boolean;
  subagentEvents?: Record<string, SubagentEvent>;
  isLatestTool?: boolean;
  /** Índice de esta burbuja entre las burbujas de task (0 = primera). */
  taskIndex?: number;
}) {
  // Abierto por defecto durante streaming (runtime), cerrado por defecto al recargar
  const [open, setOpen] = useState(isStreaming ?? false);
  const [childTools, setChildTools] = useState<Array<{ tool: string; parameters?: Record<string, any>; result?: any }>>([]);
  const [childContentFallback, setChildContentFallback] = useState<string>("");
  const [childStepsFallback, setChildStepsFallback] = useState<SubagentStep[]>([]);
  const fetchedRef = useRef(false);

  // Auto-close when streaming ends (open during runtime, closed when done)
  useEffect(() => {
    if (!isStreaming && open) {
      setOpen(false);
    }
  }, [isStreaming]); // eslint-disable-line react-hooks/exhaustive-deps

  // Determine status: 'calling' | 'success' | 'error'
  const isTask = toolCall.tool === "task";
  const hasResult = !!result;
  // Estado basado en el contrato único {status, message, data, ...} que
  // retornan todas las tools. Para `task` el contrato siempre es "success"
  // (la delegación en sí funcionó); el estado real del sub-agente vive en el
  // XML de `data` (atributo `state`). Para el resto, se usa el `status`
  // autoritativo del contrato. Se conserva un fallback por contenido para
  // resultados legacy que lleguen como string crudo.
  const isError = hasResult && result.result && (
    (isTask && typeof result.result === "object" && result.result !== null && result.result.status === "error") ||
    (isTask && typeof result.result === "object" && result.result !== null && "error" in result.result) ||
    (isTask && typeof result.result === "object" && result.result !== null && typeof result.result.data === "string" && (
      /state="error"/.test(result.result.data) ||
      /<task_result>\s*<\/task_result>/.test(result.result.data) ||
      /Ocurrió un error/.test(result.result.data)
    )) ||
    (!isTask && typeof result.result === "object" && result.result !== null && result.result.status === "error") ||
    (!isTask && typeof result.result === "object" && result.result !== null && "error" in result.result) ||
    (typeof result.result === "string" && isErrorText(result.result))
  );

  // Find matching child session ID from real-time events or result XML.
  // Cada burbuja de task se asocia a SU child session por orden: la N-ésima
  // burbuja usa el N-ésimo child_session_id (el backend emite los eventos en
  // orden exacto). Antes se usaba ids[0], lo que hacía que todas las burbujas
  // mostraran el trabajo de la primera llamada.
  const childSessionId = useMemo(() => {
    // First try to find from real-time events
    if (subagentEvents && isTask) {
      const ids = Object.keys(subagentEvents);
      if (ids.length > 0) return ids[taskIndex];
    }
    // Fall back to parsing from result XML
    if (isTask && hasResult && typeof result?.result === "string") {
      const match = result.result.match(/<task\s+id="([^"]+)"/);
      return match ? match[1] : null;
    }
    return null;
  }, [subagentEvents, isTask, hasResult, result, taskIndex]);

  // Child text content (real-time from chunks, or lazy-fetched on reload).
  // "Respuesta del sub-agente": si existe, el sub-agente terminó con texto.
  const childContent = useMemo(() => {
    if (!childSessionId || !subagentEvents?.[childSessionId]) {
      return childContentFallback || null;
    }
    return subagentEvents[childSessionId].content || null;
  }, [childSessionId, subagentEvents, childContentFallback]);
  const hasChildResponse = !!childContent;

  // Status logic:
  // - If has result: success or error based on content (a finished task must
  //   show its status even while the parent keeps streaming — previously
  //   waitingForChunk took priority and left finished tasks spinning).
  // - If waiting for first chunk: keep calling (spinner) until text arrives
  // - If no result, isStreaming and isLatestTool: calling (spinner)
  // - If no result, isStreaming but NOT latest tool: done (no spinner, closed by newer tool)
  // - If no result and NOT streaming: for task, success only when the
  //   sub-agent produced a response; error when it finished without one
  //   (even if its tools ran). For other tools: error (red, no spinner).
  const status = hasResult
    ? (isError ? "error" : "success")
    : waitingForChunk
      ? "calling"
      : (isStreaming && isLatestTool ? "calling" : (isStreaming ? "done" : (isTask ? (hasChildResponse ? "success" : "error") : "error")));

  // Status colors (done = previous tool closed by a newer one)
  const statusColors = {
    calling: "text-app-text-secondary",
    success: "text-emerald-600",
    error: "text-red-600",
    done: "text-app-text-secondary/50",
  };

  // Build child tools list from real-time events (priority) or lazy fetch
  const realtimeChildTools = useMemo(() => {
    if (!childSessionId || !subagentEvents?.[childSessionId]) return null;
    const child = subagentEvents[childSessionId];
    const tools: Array<{ tool: string; parameters?: Record<string, any>; result?: any }> = [];
    if (child.tool_calls) {
      child.tool_calls.forEach((tc, i) => {
        tools.push({
          tool: tc.name,
          parameters: tc.args,
          result: child.tool_results?.[i]?.result,
        });
      });
    }
    return tools;
  }, [childSessionId, subagentEvents]);

  // Fetch child session tools on demand (when user expands task) - fallback for historical sessions
  const fetchChildTools = useCallback(async () => {
    if (fetchedRef.current || !isTask || !hasResult || realtimeChildTools) return;
    fetchedRef.current = true;

    const resultStr = result?.result;
    if (typeof resultStr !== "string") return;

    const match = resultStr.match(/<task\s+id="([^"]+)"/);
    if (!match) return;

    const childId = match[1];
    try {
      const response = await fetch(`${API_BASE_URL}/api/sessions/${encodeURIComponent(childId)}`);
      const data = await response.json();
      if (data?.data?.messages) {
        const tools: Array<{ tool: string; parameters?: Record<string, any>; result?: any }> = [];
        const textParts: string[] = [];
        const fetchedSteps: SubagentStep[] = [];
        data.data.messages.forEach((msg: any) => {
          if (msg.type !== "assistant") return;
          // New blocks format — los blocks ya vienen en orden exacto desde el backend
          if (msg.blocks) {
            msg.blocks.forEach((b: any) => {
              if (b.type === "tool") {
                tools.push({
                  tool: b.name ?? "unknown",
                  parameters: b.args ?? {},
                  result: b.result,
                });
                fetchedSteps.push({
                  kind: "tool",
                  name: b.name ?? "unknown",
                  args: (b.args ?? {}) as Record<string, any>,
                  result: b.result,
                });
              } else if (b.type === "text" && b.content) {
                textParts.push(b.content);
                fetchedSteps.push({ kind: "text", content: b.content });
              } else if (b.type === "reasoning" && b.content) {
                fetchedSteps.push({ kind: "reasoning", content: b.content });
              }
            });
          }
          // Legacy toolCalls format
          if (msg.toolCalls) {
            msg.toolCalls.forEach((tc: any, i: number) => {
              tools.push({
                tool: tc.name ?? "unknown",
                parameters: tc.args ?? {},
                result: msg.toolResults?.[i]?.result,
              });
              fetchedSteps.push({
                kind: "tool",
                name: tc.name ?? "unknown",
                args: (tc.args ?? {}) as Record<string, any>,
                result: msg.toolResults?.[i]?.result,
              });
            });
          }
        });
        setChildTools(tools);
        if (textParts.length > 0) {
          setChildContentFallback(textParts.join("\n\n"));
        }
        if (fetchedSteps.length > 0) {
          setChildStepsFallback(fetchedSteps);
        }
      }
    } catch {
      // Silently fail - child tools just won't show
    }
  }, [isTask, hasResult, result, realtimeChildTools]);

  const handleToggle = () => {
    const nextOpen = !open;
    setOpen(nextOpen);
    if (nextOpen) {
      fetchChildTools();
    }
  };

  // Determine child tool status.
  // childDone: el sub-agente ya terminó (no streaming). Sin resultado y
  // terminado → error (falló o no devolvió nada); sin resultado y aún
  // trabajando → calling (reloj).
  const getChildStatus = (childResult?: any, childDone = false) => {
    if (!childResult) return childDone ? "error" : "calling";
    if (
      (typeof childResult === "object" && childResult !== null && childResult.status === "error") ||
      (typeof childResult === "string" && isErrorText(childResult))
    ) return "error";
    return "success";
  };

  const childStatusColors = {
    calling: "text-app-text-secondary",
    success: "text-emerald-600",
    error: "text-red-600",
  };

  // Child tools to display: real-time if available, otherwise lazy-fetched
  const displayChildTools = realtimeChildTools ?? childTools;

  // Child steps en el orden EXACTO de eventos: runtime (subagentEvents) o recarga (fallback).
  const childSteps = useMemo<SubagentStep[]>(() => {
    if (childSessionId && subagentEvents?.[childSessionId]?.steps?.length) {
      return subagentEvents[childSessionId].steps as SubagentStep[];
    }
    return childStepsFallback;
  }, [childSessionId, subagentEvents, childStepsFallback]);

  // A tool call is only collapsible if it has something to expand: args,
  // child steps (task) or child tools (legacy fallback). Otherwise (e.g. a
  // bare "help" call with no arguments) it renders as a flat, non-collapsible row.
  const hasExpandableContent =
    (toolCall.parameters && Object.keys(toolCall.parameters).length > 0) ||
    (isTask && childSteps.length > 0) ||
    (isTask && childSteps.length === 0 && displayChildTools.length > 0);

  return (
    <div className="rounded-lg border border-app-border bg-app-bg-tertiary p-2.5">
      <button
        type="button"
        onClick={hasExpandableContent ? handleToggle : undefined}
        className={`flex w-full items-center justify-between gap-2 text-left text-xs ${hasExpandableContent ? "hover:text-app-primary" : "cursor-default"}`}
      >
        <span className={`font-medium ${statusColors[status]}`}>
          {status === "calling" && <Loader2 className="h-4 w-4 animate-spin inline-block mr-1" />}
          {status === "success" && <span className="text-emerald-600">✓ </span>}
          {status === "error" && <span className="text-red-600">✗ </span>}
          🔧 {toolCall.tool}
        </span>
        {hasExpandableContent && (
          <ChevronDown
            size={14}
            className={`shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
          />
        )}
      </button>

      {open && (
        <div className="mt-2 space-y-2">
          {toolCall.parameters && Object.keys(toolCall.parameters).length > 0 && (
            <div>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-app-text-secondary">
                Args
              </div>
              <pre className="overflow-x-auto whitespace-pre-wrap break-words p-2 text-[11px] text-app-text">
                {JSON.stringify(toolCall.parameters, null, 2)}
              </pre>
            </div>
          )}

          {/* Child steps (for task) — orden EXACTO de eventos (runtime y recarga) */}
          {isTask && childSteps.length > 0 && (
            <div className="border-t border-app-border pt-2 space-y-2">
              {childSteps.map((step, i) => {
                if (step.kind === "reasoning") {
                  return <ReasoningBlock key={i} content={step.content} defaultOpen={isStreaming} isStreaming={isStreaming} />;
                }
                if (step.kind === "text") return null;
                const childStatus = getChildStatus(step.result, !isStreaming);
                return (
                  <div key={i} className="ml-3 pl-2 border-l-2 border-app-border space-y-1">
                    <div className="flex items-center gap-1 text-[11px]">
                      <span className={childStatusColors[childStatus]}>
                        {childStatus === "success" && "✓"}
                        {childStatus === "error" && "✗"}
                        {childStatus === "calling" && "⏳"}
                      </span>
                      <span className="font-medium">{step.name}</span>
                    </div>
                    {step.args && Object.keys(step.args).length > 0 && (
                      <pre className="ml-4 overflow-x-auto whitespace-pre-wrap break-words p-1.5 text-[10px] text-app-text">
                        {JSON.stringify(step.args, null, 2)}
                      </pre>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Fallback (sin steps): tools agrupadas, para sesiones legacy */}
          {isTask && childSteps.length === 0 && displayChildTools.length > 0 && (
            <div className="border-t border-app-border pt-2 space-y-2">
              {displayChildTools.length > 0 && (
                <div className="space-y-2">
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-app-text-secondary">
                    Herramientas del sub-agente
                  </div>
                  {displayChildTools.map((ct, i) => {
                    const childStatus = getChildStatus(ct.result, !isStreaming);
                    return (
                      <div key={i} className="ml-3 pl-2 border-l-2 border-app-border space-y-1">
                        <div className="flex items-center gap-1 text-[11px]">
                          <span className={childStatusColors[childStatus]}>
                            {childStatus === "success" && "✓"}
                            {childStatus === "error" && "✗"}
                            {childStatus === "calling" && "⏳"}
                          </span>
                          <span className="font-medium">{ct.tool}</span>
                        </div>
                        {ct.parameters && Object.keys(ct.parameters).length > 0 && (
                          <pre className="ml-4 overflow-x-auto whitespace-pre-wrap break-words p-1.5 text-[10px] text-app-text">
                            {JSON.stringify(ct.parameters, null, 2)}
                          </pre>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  MessageRow                                                        */
/* ------------------------------------------------------------------ */

function MessageRow({
  message,
  verboseMode,
  showCopyButton = true,
  feedback = null,
  onFeedback,
  autoCloseBlocks = false,
}: {
  message: Message;
  verboseMode: boolean;
  showCopyButton?: boolean;
  /** Each tool block closes as soon as it has its result and each reasoning block
   *  as soon as another block follows, instead of all closing at the end of the message. */
  autoCloseBlocks?: boolean;
  /** Thumb the user gave to this answer, if any. */
  feedback?: FeedbackType | null;
  /** Called when a thumb is clicked; without it the thumbs are not shown. */
  onFeedback?: (turn: number, type: FeedbackType) => void;
}) {
  const isAssistant = message.type === "assistant";

  // Determine if the assistant is waiting for its first text chunk (affects spinner logic)
  const hasTextBlock = message.blocks?.some((b) => b.type === "text");
  const waitingForChunk = message.isStreaming && !hasTextBlock;

  // Detección de "lapsos muertos": el stream está activo pero no llega contenido nuevo.
  // El typing aparece cuando no hay actividad reciente (gaps entre razonamiento/tools/respuesta).
  const lastActivityRef = useRef(Date.now());
  const [deadTyping, setDeadTyping] = useState(false);

  useEffect(() => {
    lastActivityRef.current = Date.now();
    setDeadTyping(false);
  }, [message.blocks, message.isStreaming]);

  useEffect(() => {
    if (!message.isStreaming) {
      setDeadTyping(false);
      return;
    }
    const id = setInterval(() => {
      if (Date.now() - lastActivityRef.current > 600) setDeadTyping(true);
    }, 250);
    return () => clearInterval(id);
  }, [message.isStreaming]);

  // Tool en "calling" (spinner activo): el spinner cubre el estado, no se muestra typing
  const lastBlock = message.blocks && message.blocks.length > 0 ? message.blocks[message.blocks.length - 1] : null;
  const isCallingTool = !!lastBlock && lastBlock.type === "tool" && (lastBlock as any).result === undefined && message.isStreaming;

  if (isAssistant) {
    return (
      <div className="flex gap-3 sm:gap-4 items-start">
        {/* Avatar 8x8 mobile → 64x64 desktop */}
        <div className="shrink-0">
          <div
            className="h-4 w-4 sm:h-10 sm:w-10 rounded-xl flex items-center justify-center
                        bg-gradient-to-r from-app-primary to-app-gradient-secondary text-app-primary-text"
          >
            <Brain size={20} className="text-app-primary-text" />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0 pt-1">

          {/* Blocks in order: reasoning ↔ text interleaved with tools */}
          {message.blocks && message.blocks.length > 0 ? (
            <div className="space-y-2">
              {message.blocks.map((block, i) => {
                if (block.type === "reasoning") {
                  if (!verboseMode) return null;
                  return <ReasoningBlock key={i} content={block.content} defaultOpen={message.isStreaming} isStreaming={autoCloseBlocks ? message.isStreaming && i === (message.blocks?.length ?? 0) - 1 : message.isStreaming} />;
                }
                if (block.type === "text") {
                  return (
                    <div key={i}>
                      <MarkdownRenderer content={block.content} />
                    </div>
                  );
                }
                if (block.type === "tool") {
                  if (!verboseMode) return null;
                  // Índice de esta burbuja entre las burbujas de task (para
                  // asociarla a su child session en el orden exacto de eventos).
                  const taskIndex = (message.blocks ?? [])
                    .slice(0, i)
                    .filter((b) => b.type === "tool" && b.name === "task").length;
                  return (
                    <ToolCallBlock
                      key={i}
                      toolCall={{ tool: block.name, parameters: block.args }}
                      result={block.result !== undefined ? { tool: block.name, result: block.result } : undefined}
                      isStreaming={autoCloseBlocks ? message.isStreaming && block.result === undefined : message.isStreaming}
                      waitingForChunk={waitingForChunk}
                      subagentEvents={message.subagentEvents}
                      isLatestTool={i === (message.blocks?.length ?? 0) - 1}
                      taskIndex={taskIndex}
                    />
                  );
                }
                return null;
              })}
            </div>
          ) : (
            /* Fallback for legacy messages without blocks (welcome, very old sessions) */
            <>
              <MarkdownRenderer content={message.content} />
              {/* Tool calls from legacy format */}
              {verboseMode && message.toolCalls && message.toolCalls.length > 0 && (
                <div className="mt-2 space-y-2">
                  {message.toolCalls.map((tc, i) => (
                    <ToolCallBlock
                      key={`${tc.tool}-${i}`}
                      toolCall={tc}
                      result={message.toolResults?.[i]}
                      isStreaming={false}
                      subagentEvents={undefined}
                    />
                  ))}
                </div>
              )}
            </>
          )}

          {/* Copy button (only when there's actual text content) — opcional (skill lo desactiva) */}
          {showCopyButton && message.type === "assistant" && !message.isStreaming && message.id !== "welcome" && (
            (message.content || (message.blocks && message.blocks.some((b) => b.type === "text"))) && (
              <div className="mt-2 flex items-stretch gap-2">
                <button
                  type="button"
                  onClick={() => {
                    const text = message.blocks
                      ? message.blocks.filter((b) => b.type === "text").map((b) => (b as any).content).join("\n\n")
                      : message.content || "";
                    navigator.clipboard?.writeText(text);
                  }}
                  className="inline-flex items-center gap-1 rounded-full border border-app-primary/20 bg-app-primary/10 px-2 py-1 text-[11px] text-app-primary transition-colors hover:bg-app-primary/15"
                >
                  <Copy size={12} />
                  Copiar
                </button>
                {onFeedback && message.turn != null && (
                  <>
                    {(["up", "down"] as const).map((type) => {
                      const selected = feedback === type;
                      const label = type === "up" ? "Buena respuesta" : "Mala respuesta";
                      const Icon = type === "up" ? ThumbsUp : ThumbsDown;
                      // Fixed colors (soft yellow icon on green / red), independent of the theme.
                      // Only the hover is shared with the Copy button; the one given stays
                      // at full strength with a filled icon, the other is dimmed.
                      const tone =
                        type === "up"
                          ? "border-green-600 bg-green-600 hover:bg-green-700"
                          : "border-red-600 bg-red-600 hover:bg-red-700";
                      return (
                        <button
                          key={type}
                          type="button"
                          onClick={() => onFeedback(message.turn as number, type)}
                          aria-label={label}
                          aria-pressed={selected}
                          title={label}
                          className={`inline-flex items-center rounded-full border px-2 py-1 text-[11px] text-[#F2D077] transition-all ${tone} ${
                            selected
                              ? "opacity-100"
                              : "opacity-60 hover:opacity-100"
                          }`}
                        >
                          <Icon size={12} fill={selected ? "currentColor" : "none"} />
                        </button>
                      );
                    })}
                  </>
                )}
              </div>
            )
          )}

          {/* TypingIndicator:
              Verbose OFF — typing while no text block yet (tools are invisible, user needs feedback).
              Verbose ON  — typing en lapsos muertos (sin actividad reciente) y sin tool en calling. */}
          {message.isStreaming && (
            !!message.retryNotice || (
              verboseMode
                ? (!isCallingTool && (!message.blocks || message.blocks.length === 0 || deadTyping))
                : (!message.blocks || !message.blocks.some(b => b.type === "text"))
            )
          ) && <TypingIndicator label={message.retryNotice || undefined} />}
        </div>
      </div>
    );
  }

  /* ---- User message ---- */
  return (
    <div className="flex gap-3 items-start justify-end">
      {/* Bubble */}
      <div
        className={`rounded-2xl border px-4 py-3 max-w-[85%] sm:max-w-[75%] shadow-sm ${
          message.blocked
            ? "border-[#403F3F] bg-[#403F3F] text-red-400"
            : "border-app-border bg-white"
        }`}
      >
        {message.blocked ? (
          <p className="text-sm font-medium">{message.content}</p>
        ) : (
          <MarkdownRenderer content={message.content} />
        )}
      </div>

      {/* Avatar gradient */}
      <div
        className="w-10 h-10 sm:w-10 sm:h-10 rounded-full shrink-0 flex items-center justify-center
                   bg-app-bg-tertiary text-app-text"
      >
        <User size={14} />
      </div>
    </div>
  );
}

export {
  TypingIndicator,
  ReasoningBlock,
  FileWarningBanner,
  FileChip,
  MarkdownRenderer,
  ToolCallBlock,
  MessageRow,
};
