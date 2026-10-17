import { useState, useCallback, useEffect, useRef } from "react";
import {
  ChatInterface,
  WELCOME_MESSAGE,
  type ChatInterfaceHandle,
} from "./chat/ChatInterface";
import { HistoryModal } from "./components/HistoryModal";
import { MetricsModal } from "./components/MetricsModal";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "./components/ui/dialog";
import { UsageTab } from "./components/UsageTab";
import { BillingTab } from "./components/BillingTab";
import { SchedulerModal } from "./components/SchedulerModal";
import { SetupScreen } from "./components/SetupScreen";
import { Sidebar } from "./components/Sidebar";
import sessionService, {
  type SessionMessage,
  type ContentBlock,
} from "./services/sessionService";
import configService from "./services/configService";
import telegramService from "./services/telegramService";
import chatService from "./services/chatService";
import type { SchedulerNotification } from "./services/schedulerService";

export type { ContentBlock };

/** Paso ordenado dentro de la tarjeta de un sub-agente (orden exacto de eventos). */
export type SubagentStep =
  | { kind: "reasoning"; content: string }
  | { kind: "text"; content: string }
  | { kind: "tool"; name: string; args: Record<string, any>; result?: any };

export interface SubagentEvent {
  child_session_id: string;
  agent_name: string;
  tool_calls?: Array<{ name: string; args: Record<string, any> }>;
  tool_results?: Array<{ name: string; result: any }>;
  content?: string;
  reasoning?: string;
  /** Pasos en el orden EXACTO en que ocurrieron los eventos (runtime y recarga). */
  steps?: SubagentStep[];
}

export interface Message {
  id: string;
  type: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  reasoning?: string;
  blocks?: ContentBlock[];
  /** Attached files for user messages (shown as chips) */
  files?: Array<{ name: string; size?: number }>;
  /** Legacy – kept for backward compat during streaming */
  toolCalls?: Array<{ tool: string; parameters: Record<string, any> }>;
  toolResults?: Array<{ tool: string; result: any }>;
  subagentEvents?: Record<string, SubagentEvent>;
  /** Turn of the session this answer belongs to (ties it to its feedback). */
  turn?: number;
}

/** Generate a unique ID with safe fallback when crypto is unavailable. */
function generateId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
}

/** Map backend session messages to the frontend Message shape. */
function mapSessionMessages(raw: SessionMessage[]): Message[] {
  return raw.map((m) => ({
    id: m.id,
    type: m.type,
    turn: m.turn_number ?? undefined,
    content: m.type === "user" ? m.content : "",
    reasoning: m.reasoning ?? undefined,
    files: m.files ?? undefined,
    blocks: m.blocks ?? (
      // Fallback for old sessions without blocks: build from toolCalls + toolResults
      m.type === "assistant" && (m.toolCalls || m.content)
        ? buildLegacyBlocks(m.content, m.toolCalls ?? [], m.toolResults ?? [])
        : undefined
    ),
    // Keep legacy fields for backward compat during streaming
    toolCalls: m.toolCalls
      ? m.toolCalls.map((tc) => ({
          tool: tc.name ?? "unknown",
          parameters: tc.args ?? {},
        }))
      : undefined,
    toolResults: m.toolResults
      ? m.toolResults.map((tr) => ({
          tool: tr.tool_name ?? "unknown",
          result: tr.result ?? {},
        }))
      : undefined,
  }));
}

/** Build blocks from the legacy flat toolCalls+toolResults format (old sessions). */
function buildLegacyBlocks(
  content: string,
  toolCalls: Array<{ name: string; args: Record<string, any> }>,
  toolResults: Array<{ tool_name?: string; result: any }>,
): ContentBlock[] {
  const blocks: ContentBlock[] = [];
  if (content) {
    blocks.push({ type: "text", content });
  }
  toolCalls.forEach((tc, i) => {
    const result =
      i < toolResults.length ? toolResults[i].result : undefined;
    blocks.push({
      type: "tool",
      name: tc.name ?? "unknown",
      args: tc.args ?? {},
      result,
    });
  });
  return blocks;
}

function App() {
  const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showSidebarMenu, setShowSidebarMenu] = useState(false);

  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [showMetrics, setShowMetrics] = useState(false);
  const [showUsage, setShowUsage] = useState(false);
  const [showBilling, setShowBilling] = useState(false);
  const [showScheduler, setShowScheduler] = useState(false);
  const [verboseMode, setVerboseMode] = useState<boolean>(
    () => localStorage.getItem("verboseMode") === "true"
  );
  const [telegramEnabled, setTelegramEnabled] = useState(false);
  const [telegramCountdown, setTelegramCountdown] = useState<number | null>(null);
  /* Header bell notifications: one entry per scheduled-task execution. */
  const [notifications, setNotifications] = useState<SchedulerNotification[]>([]);

  const handleClearNotifications = useCallback(() => {
    setNotifications([]);
  }, []);

  /* Initial setup screen: shown on first launch only (until the user saves
   * a valid API key or skips it). Shown even when Ollama is available:
   * nothing runs by default, the user must configure explicitly. */
  const [setupState, setSetupState] = useState<"loading" | "setup" | "ready">("loading");

  const checkSetup = useCallback(async () => {
    try {
      const data = await configService.getSetupCompleted();
      setSetupState(data.completed ? "ready" : "setup");
    } catch {
      // Backend unreachable: show the normal app (it surfaces its own errors).
      setSetupState("ready");
    }
  }, []);

  const handleSetupDone = useCallback(() => {
    configService.markSetupCompleted().catch(() => {});
    setSetupState("ready");
  }, []);

  useEffect(() => {
    checkSetup();
  }, [checkSetup]);

  const initialLoadRef = useRef(true);
  const chatRef = useRef<ChatInterfaceHandle>(null);
  const createWindowRef = useRef<Window | null>(null);

  // Load persisted verbose mode from backend on mount
  useEffect(() => {
    configService.getVerbose().then((vm) => {
      if (!initialLoadRef.current) return; // stale: user already toggled
      initialLoadRef.current = false;
      setVerboseMode(vm);
      localStorage.setItem("verboseMode", String(vm));
    }).catch(() => {
      // Fallback to localStorage value if backend not reachable
      initialLoadRef.current = false;
    });
  }, []);

  // Heartbeat: ping backend every 10s so watchdog knows frontend is alive
  useEffect(() => {
    const API_BASE_URL = import.meta.env.VITE_URL_BASE || "http://localhost:8000";
    const interval = setInterval(() => {
      fetch(`${API_BASE_URL}/api/heartbeat`, { method: "POST", keepalive: true }).catch(() => {});
    }, 10000);
    // Initial ping
    fetch(`${API_BASE_URL}/api/heartbeat`, { method: "POST", keepalive: true }).catch(() => {});
    return () => clearInterval(interval);
  }, []);

  const handleVerboseModeChange = useCallback((val: boolean) => {
    initialLoadRef.current = false;
    setVerboseMode(val);
    localStorage.setItem("verboseMode", String(val));
    configService.setVerbose(val).catch((err) => {
      console.error("Error persistiendo verbose mode:", err);
    });
  }, []);

  // Load persisted Telegram state from backend on mount
  useEffect(() => {
    telegramService
      .getStatus()
      .then(setTelegramEnabled)
      .catch(() => {});
  }, []);

const handleTelegramToggle = useCallback((val: boolean) => {
    if (val) {
      // Enable the backend immediately so the bot starts polling and discards
      // any messages that arrived while it was off. The popup countdown only
      // blocks the user from sending during that discard window.
      setTelegramEnabled(true);
      telegramService.toggle(true).catch((err) => {
        console.error("Error persistiendo Telegram toggle:", err);
      });
      setTelegramCountdown(3);
    } else {
      setTelegramEnabled(false);
      telegramService.toggle(false).catch((err) => {
        console.error("Error persistiendo Telegram toggle:", err);
      });
    }
  }, []);

  // Countdown: only hides the popup when it reaches 0 (backend already enabled).
  useEffect(() => {
    if (telegramCountdown === null) return;
    if (telegramCountdown <= 0) {
      setTelegramCountdown(null);
      return;
    }
    const t = setTimeout(() => {
      setTelegramCountdown((c) => (c === null ? null : c - 1));
    }, 1000);
    return () => clearTimeout(t);
  }, [telegramCountdown]);

  const handleNewChat = useCallback(() => {
    setCurrentSessionId(null);
    setMessages([WELCOME_MESSAGE]);
    setIsStreaming(false);
    setRefreshTrigger((t) => t + 1);
    // Reset the context-window gauge and tokens text to 0 for the new session
    chatRef.current?.setContextInfo({ contextWindow: null, tokensUsed: 0, percent: 0 });
  }, []);

  const handleSessionStart = useCallback((id: string) => {
    setCurrentSessionId(id);
    setRefreshTrigger((t) => t + 1);
    // Sync the new session as active so Telegram knows it (single source of truth)
    telegramService.setActiveSession(id).catch(() => {});
  }, []);

  const handleSelectSession = useCallback(async (id: string) => {
    if (id === currentSessionId) return;
    try {
      const data = await sessionService.getSession(id);
      setCurrentSessionId(id);
      setMessages([WELCOME_MESSAGE, ...mapSessionMessages(data.messages)]);
      setIsStreaming(false);
      // Restore the context-window gauge from the saved session data
      const ctx = data.context;
      if (ctx) {
        chatRef.current?.setContextInfo({
          contextWindow: ctx.context_window ?? null,
          tokensUsed: ctx.prompt_tokens ?? null,
          percent: ctx.percent ?? null,
        });
      }
      // Sync the active session to Telegram (single source of truth in DB)
      telegramService.setActiveSession(id).catch(() => {});
    } catch (err) {
      console.error("Error cargando la sesión:", err);
    }
  }, [currentSessionId]);

  const handleSessionEnd = useCallback(() => {
    setRefreshTrigger((t) => t + 1);
  }, []);

  const handleSessionTitleUpdate = useCallback((id: string, title: string) => {
    setRefreshTrigger((t) => t + 1);
  }, []);

  const handleToggleSidebarMenu = useCallback(() => {
    setShowSidebarMenu((prev) => !prev);
  }, []);

  // Listen to backend events (SSE) so Telegram messages/commands run the
  // exact same chat flow as if the user had typed in the web UI.
  useEffect(() => {
    const API_BASE_URL = import.meta.env.VITE_URL_BASE || "http://localhost:8000";
    const es = new EventSource(`${API_BASE_URL}/api/events`);
    es.onmessage = (ev) => {
      let data: any;
      try {
        data = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (data.type === "telegram_message") {
        const content: string = data.content || "";
        const chatId: string = data.chat_id != null ? String(data.chat_id) : "";
        const sessionId: string | null = data.session_id || null;
        if (content) {
          chatRef.current?.sendMessage(content, chatId, sessionId);
        }
      } else if (data.type === "telegram_command") {
        const command: string = data.command || "";
        if (command === "nueva") {
          handleNewChat();
        } else if (command === "detener") {
          chatService.cancelStream();
          setIsStreaming(false);
        } else if (command === "usar") {
          const sessionId: string | null = data.session_id || null;
          if (sessionId) {
            handleSelectSession(sessionId);
          }
        } else if (command === "borrar") {
          setRefreshTrigger((t) => t + 1);
        }
      } else if (data.type === "session_title") {
        const sessionId: string | null = data.session_id || null;
        const title: string = data.content || "";
        if (sessionId && title) {
          handleSessionTitleUpdate(sessionId, title);
        }
      } else if (data.type === "model_changed") {
        // Broadcast by the backend whenever the persisted model changes
        // (Telegram, the /api/config/models/select endpoint, or any future
        // caller). Dispatch the same CustomEvent the local UI path uses, so
        // every subscriber — gauge (ChatInterface), ConfigTab dropdown,
        // etc. — refreshes in lockstep.
        window.dispatchEvent(new CustomEvent("model-changed"));
      } else if (data.type === "scheduler_run") {
        // A scheduled task finished: push a bell notification and refresh the
        // sidebar so the session created by the task shows up.
        setNotifications((prev) => [
          {
            id: generateId(),
            status: data.status === "success" ? "success" : "error",
            task: data.task || "",
            detail: data.detail || "",
            finishedAt: data.finished_at || "",
          },
          ...prev,
        ]);
        setRefreshTrigger((t) => t + 1);
      } else if (data.type === "telegram_create") {
        // Telegram as remote control ("or"): open/close the same create window
        // (skill.html / rag.html / tool.html) the user would open from the web UI.
        const kind: string = data.kind || "";
        const action: string = data.action || "";
        const base = window.location.origin;
        if (action === "open") {
          const page =
            kind === "rag"
              ? "rag.html"
              : kind === "skill"
                ? "skill.html"
                : kind === "tool"
                  ? "tool.html"
                  : null;
          if (page) {
            if (createWindowRef.current) {
              createWindowRef.current.close();
            }
            createWindowRef.current = window.open(`${base}/${page}`, "_blank", "noopener,noreferrer");
          }
        } else if (action === "close") {
          if (createWindowRef.current) {
            createWindowRef.current.close();
          }
          createWindowRef.current = null;
        }
      }
    };
    es.onerror = () => {
      // EventSource reconnects automatically; nothing to do here.
    };
    return () => es.close();
  }, [handleNewChat, handleSessionTitleUpdate, handleSelectSession]);

  if (setupState === "loading") {
    return <div className="h-screen bg-app-bg" />;
  }

  if (setupState === "setup") {
    return <SetupScreen onDone={handleSetupDone} />;
  }

  return (
    <div className="h-screen bg-app-bg flex">
      <Sidebar
        activeSessionId={currentSessionId}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        refreshTrigger={refreshTrigger}
        verboseMode={verboseMode}
        onVerboseModeChange={handleVerboseModeChange}
      />

      <div className="flex-1 min-w-0">
        <ChatInterface
          ref={chatRef}
          messages={messages}
          setMessages={setMessages}
          isStreaming={isStreaming}
          setIsStreaming={setIsStreaming}
          onShowHistory={() => setShowHistory(true)}
          onToggleSidebar={handleToggleSidebarMenu}
          sessionId={currentSessionId}
          onSessionStart={handleSessionStart}
          onNewChat={handleNewChat}
          onSessionEnd={handleSessionEnd}
          onShowMetrics={() => setShowMetrics(true)}
          onShowUsage={() => setShowUsage(true)}
          onShowBilling={() => setShowBilling(true)}
          onSessionTitleUpdate={handleSessionTitleUpdate}
          verboseMode={verboseMode}
          telegramEnabled={telegramEnabled}
          onTelegramToggle={handleTelegramToggle}
          onShowScheduler={() => setShowScheduler(true)}
          notifications={notifications}
          onClearNotifications={handleClearNotifications}
        />
      </div>

      <HistoryModal
        open={showHistory}
        onClose={() => setShowHistory(false)}
      />

      <MetricsModal
        open={showMetrics}
        onClose={() => setShowMetrics(false)}
      />

      <Dialog open={showUsage} onOpenChange={(o) => { if (!o) setShowUsage(false); }}>
        <DialogContent className="flex h-[620px] max-w-4xl w-[720px] flex-col gap-0 p-0">
          <DialogHeader className="px-6 pt-6 pb-4">
            <DialogTitle>Uso</DialogTitle>
          </DialogHeader>
          <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-6">
            <UsageTab />
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showBilling} onOpenChange={(o) => { if (!o) setShowBilling(false); }}>
        <DialogContent className="flex h-[620px] max-w-4xl w-[720px] flex-col gap-0 p-0">
          <DialogHeader className="px-6 pt-6 pb-4">
            <DialogTitle>Facturación</DialogTitle>
          </DialogHeader>
          <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-6">
            <BillingTab />
          </div>
        </DialogContent>
      </Dialog>

      <SchedulerModal
        open={showScheduler}
        onClose={() => setShowScheduler(false)}
      />

      {/* Popup de activación de Telegram con contador regresivo */}
      {telegramCountdown !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="rounded-2xl bg-white p-6 shadow-xl text-center">
            <div className="text-sm font-semibold text-app-text mb-2">
              Activando Telegram...
            </div>
            <div className="text-5xl font-bold text-app-primary">
              {telegramCountdown}
            </div>
            <div className="text-xs text-app-text-secondary mt-2">
              Esperá para que el bot se sincronice
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
