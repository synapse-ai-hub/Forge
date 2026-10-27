import { useState, useEffect, useCallback, useRef } from "react";
import { Plus, History, Settings, Brain, Trash2, Wrench, SlidersHorizontal } from "lucide-react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import EmpresaLogo from "../assets/logo_empresa.png";
import sessionService, { type ChatSession } from "../services/sessionService";
import contextFilesService, { type ContextFile } from "../services/contextFilesService";
import SessionsTab from "./sessionsTab";
import ConfigTab from "./configTab";
import AgentInfoTab from "./agentInfoTab";
import CreateTab from "./createTab";
import RouterTab from "./RouterTab";

type SidebarTab = "sessions" | "config" | "router" | "agent" | "create";

interface SidebarProps {
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  refreshTrigger: number;
  verboseMode: boolean;
  onVerboseModeChange: (val: boolean) => void;
}

function formatTimestamp(value: string): string {
  try {
    const d = new Date(value);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleString("es-AR", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function tabClass(active: boolean): string {
  return `flex items-center gap-2 px-3 py-2.5 text-xs font-medium transition-colors border-l-2 ${
    active
      ? "border-app-primary text-app-primary bg-app-bg-secondary/50"
      : "border-transparent text-app-text-secondary hover:text-app-text hover:bg-app-bg-tertiary"
  }`;
}

export function Sidebar({
  activeSessionId,
  onSelectSession,
  onNewChat,
  refreshTrigger,
  verboseMode,
  onVerboseModeChange,
}: SidebarProps) {
  const [tab, setTab] = useState<SidebarTab>("sessions");
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [pendingSessions, setPendingSessions] = useState<ChatSession[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Other components (e.g. the "configure a provider" banner in the chat)
  // can request the config tab via this window event.
  useEffect(() => {
    const openConfig = () => setTab("config");
    window.addEventListener("open-config-tab", openConfig);
    return () => window.removeEventListener("open-config-tab", openConfig);
  }, []);

  const loadSessions = useCallback(async () => {
    try {
      setIsLoading(true);
      const data = await sessionService.listSessions();
      setSessions(data);
    } catch (err) {
      console.error("Error cargando sesiones:", err);
      setSessions([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Load sessions on mount
  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // Crear tarjeta pending cuando se inicia una nueva sesión.
  // Si activeSessionId pasa de un valor a null (usuario hace New Chat),
  // limpiar las pending que no se hayan confirmado (siguen en pending).
  useEffect(() => {
    if (activeSessionId) {
      setPendingSessions(prev => {
        if (prev.some(p => p.session_id === activeSessionId)) return prev;
        if (sessions.some(s => s.session_id === activeSessionId)) return prev;
        const now = new Date().toISOString();
        return [{ session_id: activeSessionId, title: "Nueva conversación", preview: "Generando...", created_at: now, updated_at: now, message_count: 0 }, ...prev];
      });
    } else {
      // Usuario hizo New Chat: limpiar pending que no se confirmaron en backend
      setPendingSessions([]);
    }
  }, [activeSessionId]);

  // Refrescar al cambiar a la pestaña sessions
  useEffect(() => {
    if (tab !== "sessions") return;
    sessionService.listSessions()
      .then((data) => {
        setSessions(data);
        setPendingSessions(prev => prev.filter(p => !data.some(s => s.session_id === p.session_id)));
      })
      .catch((err) => console.error("Error refrescando sesiones:", err));
  }, [tab]);

  // Refrescar en silencio cuando cambia refreshTrigger
  useEffect(() => {
    if (tab === "sessions") {
      sessionService.listSessions()
        .then((data) => {
          setSessions(data);
          setPendingSessions(prev => prev.filter(p => !data.some(s => s.session_id === p.session_id)));
        })
        .catch((err) => console.error("Error refrescando sesiones:", err));
    }
  }, [refreshTrigger]);

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm("¿Eliminar esta conversación?")) return;
    try {
      setDeletingId(id);
      // Si es pending (no existe en backend), solo remover local
      const isPending = pendingSessions.some(p => p.session_id === id);
      if (isPending) {
        setPendingSessions(prev => prev.filter(p => p.session_id !== id));
      } else {
        await sessionService.deleteSession(id);
        setSessions((prev) => prev.filter((s) => s.session_id !== id));
      }
      if (activeSessionId === id) {
        onNewChat();
      }
    } catch (err) {
      console.error("Error eliminando sesión:", err);
    } finally {
      setDeletingId(null);
    }
  };

  const isDevOnly = import.meta.env.VITE_MODE === "dev";

  // Menu items
  const menuItems: Array<{ key: SidebarTab; label: string; icon: React.ReactNode; devOnly?: boolean }> = [
    { key: "sessions", label: "Conversaciones", icon: <History size={14} /> },
    { key: "config", label: "Configuración", icon: <Settings size={14} /> },
    { key: "router", label: "Router", icon: <SlidersHorizontal size={14} /> },
    ...(isDevOnly ? [{ key: "agent" as SidebarTab, label: "Agente", icon: <Brain size={14} /> }] : []),
    ...(isDevOnly ? [{ key: "create" as SidebarTab, label: "Crear", icon: <Wrench size={14} /> }] : []),
  ];

  return (
    <aside className="w-64 shrink-0 h-full flex flex-col border-r border-app-border bg-app-bg-secondary">
      {/* Menu header */}
      <header
        className="flex items-center gap-3 px-4 shrink-0 border-b border-app-border bg-white"
        style={{ height: "95px" }}
      >
        <img
          src={EmpresaLogo}
          alt="Logo empresa"
          className="h-14 sm:h-[75px] w-auto"
        />
        <div className="flex flex-col min-w-0">
          <span className="text-base font-semibold text-app-text truncate">
            {/* @ts-ignore */}
            <empresa>nombre_empresa</empresa>
          </span>
          <span className="text-xs text-app-text-secondary truncate leading-tight"><span className="brand-word">synapseForge</span></span>
        </div>
      </header>

      {/* Menu items */}
      <nav className="flex flex-col py-2 border-b border-app-border">
        {menuItems.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setTab(item.key)}
            className={`flex items-center gap-2 px-3 py-2.5 text-xs font-medium transition-colors border-l-2 ${
              tab === item.key
                ? "border-app-primary text-app-primary bg-app-primary/10"
                : "border-transparent text-app-text-secondary hover:text-app-text hover:bg-app-bg-tertiary"
            }`}
          >
            {item.icon}
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      {/* Content area */}
      <div className="flex-1 flex flex-col min-h-0">
        {/* Sessions tab */}
        <div
          className="flex-1 flex flex-col min-h-0"
          style={{ display: tab === "sessions" ? "flex" : "none" }}
        >
          <SessionsTab
            activeSessionId={activeSessionId}
            onSelectSession={onSelectSession}
            onNewChat={onNewChat}
            refreshTrigger={refreshTrigger}
            sessions={[...pendingSessions, ...sessions]}
            isLoading={isLoading}
            deletingId={deletingId}
            handleDelete={handleDelete}
          />
        </div>

        {/* Config tab */}
        <div
          className="flex-1 flex flex-col min-h-0 overflow-y-auto"
          style={{ display: tab === "config" ? "flex" : "none" }}
        >
          <ConfigTab verboseMode={verboseMode} onVerboseModeChange={onVerboseModeChange} />
        </div>

        {/* Router tab */}
        <div
          className="flex-1 flex flex-col min-h-0 overflow-y-auto"
          style={{ display: tab === "router" ? "flex" : "none" }}
        >
          <RouterTab />
        </div>

        {/* Agent info tab (dev only) */}
        {isDevOnly && (
          <div
            className="flex-1 flex flex-col min-h-0 overflow-y-auto"
            style={{ display: tab === "agent" ? "flex" : "none" }}
          >
            <AgentInfoTab />
          </div>
        )}

        {/* Create tab (dev only) */}
        {isDevOnly && (
          <div
            className="flex-1 flex flex-col min-h-0 overflow-y-auto"
            style={{ display: tab === "create" ? "flex" : "none" }}
          >
            <CreateTab />
          </div>
        )}
      </div>
    </aside>
  );
}

export default Sidebar;