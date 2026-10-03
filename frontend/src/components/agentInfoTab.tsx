import { useState, useEffect, useCallback } from "react";
import { Wrench, Puzzle, Brain, Server, Cpu, Globe, Database, Trash2, RefreshCw, Workflow } from "lucide-react";
import configService, { type SkillInfo, type ToolInfo, type AgentInfo, type McpServerStatus } from "../services/configService";

type AgentTab = "tools" | "skills" | "agents" | "mcp" | "rag" | "workflows";

export function AgentInfoTab() {
  const [tab, setTab] = useState<AgentTab>("tools");
  const [mcpServers, setMcpServers] = useState<McpServerStatus[]>([]);
  const [mcpLoading, setMcpLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadMcp = useCallback(async () => {
    try {
      setMcpLoading(true);
      const data = await configService.getMcp();
      setMcpServers(data);
    } catch (err) {
      console.error("Error cargando MCP:", err);
    } finally {
      setMcpLoading(false);
    }
  }, []);

  useEffect(() => { loadMcp(); }, [loadMcp]);

  const refreshAll = async () => {
    setRefreshing(true);
    try {
      // Refresh tools registry on backend (external + native + MCP)
      await configService.refresh();
      // Reload MCP server status
      await loadMcp();
      // Force reload of all panels (tools, skills, agents, RAG) via focus event
      window.dispatchEvent(new Event("focus"));
    } catch (err) {
      console.error("Error refrescando:", err);
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Sidebar nav — vertical tabs one below the other */}
      <nav className="flex flex-col py-2 border-b border-app-border bg-app-bg-secondary">
        {([
          { key: "tools" as AgentTab, label: "Tools", icon: <Wrench size={14} /> },
          { key: "skills" as AgentTab, label: "Skills", icon: <Puzzle size={14} /> },
          { key: "agents" as AgentTab, label: "Agentes", icon: <Brain size={14} /> },
          { key: "mcp" as AgentTab, label: "MCP", icon: <Server size={14} /> },
          { key: "rag" as AgentTab, label: "RAG", icon: <Database size={14} /> },
          { key: "workflows" as AgentTab, label: "Workflows", icon: <Workflow size={14} /> },
        ]).map((item) => (
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
        {/* Refresh button at bottom of nav */}
        <button
          type="button"
          onClick={refreshAll}
          disabled={refreshing}
          className="flex items-center justify-center gap-2 px-3 py-2.5 text-xs font-medium transition-colors border-t border-app-border mt-2 hover:bg-app-bg-tertiary disabled:opacity-50"
          title="Refrescar todo (tools, skills, agentes, MCP, RAG)"
        >
          <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
          <span>Actualizar</span>
        </button>
      </nav>

      {/* Content — below the nav tabs (same as Sidebar layout) */}
      <div className="flex-1 overflow-y-auto p-3">
        {tab === "tools" && <ToolsPanel onRefresh={refreshAll} />}
        {tab === "skills" && <SkillsPanel onRefresh={refreshAll} />}
        {tab === "agents" && <AgentsPanel onRefresh={refreshAll} />}
        {tab === "mcp" && <McpPanel servers={mcpServers} loading={mcpLoading} onRefresh={loadMcp} />}
        {tab === "rag" && <RagPanel onRefresh={refreshAll} />}
        {tab === "workflows" && <WorkflowsPanel onRefresh={refreshAll} />}
      </div>
    </div>
  );
}

// ─── Delete button with confirmation ──────────────────────────────

function DeleteBtn({ label, onDelete }: { label: string; onDelete: () => Promise<void> }) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  if (confirming) {
    return (
      <div className="flex items-center gap-1">
        <button
          type="button"
          disabled={deleting}
          onClick={async () => {
            setDeleting(true);
            try {
              await onDelete();
              // Success — confirm stays visible but disabled briefly
              setTimeout(() => { setConfirming(false); setDeleting(false); }, 500);
            } catch {
              setDeleting(false);
              setConfirming(false);
            }
          }}
          className="text-xs bg-red-500 hover:bg-red-600 text-white px-2 py-0.5 rounded disabled:opacity-50"
        >
          {deleting ? "..." : "Sí"}
        </button>
        <button
          type="button"
          onClick={() => setConfirming(false)}
          className="text-xs bg-gray-200 hover:bg-gray-300 text-gray-700 px-2 py-0.5 rounded"
        >
          No
        </button>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setConfirming(true)}
      className="text-app-text-secondary hover:text-red-500 transition-colors shrink-0"
      title={`Eliminar ${label}`}
    >
      <Trash2 size={14} />
    </button>
  );
}

// ─── Tools ────────────────────────────────────────────────────────

function ToolsPanel({ onRefresh }: { onRefresh: () => Promise<void> }) {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const data = await configService.getTools();
      setTools(data);
    } catch (err) {
      console.error("Error cargando tools:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Also reload when window regains focus (e.g., tool created in another tab)
  useEffect(() => {
    const onFocus = () => { setLoading(true); load(); };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [load]);

  if (loading) return <p className="text-sm text-app-text-secondary">Cargando...</p>;

  return (
    <div className="space-y-1">
      <p className="text-[11px] text-app-text-secondary leading-snug mb-2">
        Las herramientas son capacidades que el agente puede invocar para realizar acciones concretas
        (leer archivos, buscar en web, ejecutar comandos). Se activan según los permisos del agente.
      </p>
      {msg && <p className="text-xs text-green-600 mb-1">{msg}</p>}
      {tools.length === 0 ? (
        <p className="text-sm text-app-text-secondary">No hay herramientas disponibles.</p>
      ) : (
        tools.map((t) => (
          <div key={t.name} className="flex items-start justify-between rounded-lg border border-app-primary-light bg-white px-3 py-2">
            <div className="min-w-0 flex-1">
              <span className="text-sm font-medium text-app-text break-words">{t.name}</span>
              {t.description && (
                <p className="text-xs text-app-text-secondary mt-0.5">{t.description}</p>
              )}
            </div>
            <DeleteBtn
              label={t.name}
              onDelete={async () => {
                await configService.deleteTool(t.name);
                setTools((prev) => prev.filter((x) => x.name !== t.name));
                setMsg(`Tool «${t.name}» eliminada.`);
                setTimeout(() => setMsg(""), 3000);
              }}
            />
          </div>
        ))
      )}
    </div>
  );
}

// ─── Skills ───────────────────────────────────────────────────────

function SkillsPanel({ onRefresh }: { onRefresh: () => Promise<void> }) {
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await configService.getSkills();
      setSkills(data);
    } catch (err) {
      console.error("Error cargando skills:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Cargar al montar y recargar cuando la ventana recupera el foco
  // (por si se creó/borró una skill en otra pestaña)
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const onFocus = () => { setLoading(true); load(); };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [load]);

  if (loading) return <p className="text-sm text-app-text-secondary">Cargando...</p>;

  return (
    <div className="space-y-1">
      <p className="text-[11px] text-app-text-secondary leading-snug mb-2">
        Las skills son módulos de conocimiento o comportamiento que el agente puede cargar
        (por ejemplo: documentación, protocols, patrones de análisis). Se cargan desde archivos SKILL.md.
      </p>
      {msg && <p className="text-xs text-green-600 mb-1">{msg}</p>}
      {skills.length === 0 ? (
        <p className="text-sm text-app-text-secondary">No hay skills instaladas.</p>
      ) : (
        skills.map((s) => (
          <div key={s.name} className="flex items-start justify-between rounded-lg border border-app-primary-light bg-white px-3 py-2">
            <div className="min-w-0 flex-1">
              <span className="text-sm font-medium text-app-text break-words">{s.name}</span>
              {s.description && (
                <p className="text-xs text-app-text-secondary mt-0.5">{s.description}</p>
              )}
            </div>
            <DeleteBtn
              label={s.name}
              onDelete={async () => {
                await configService.deleteSkill(s.name);
                setSkills((prev) => prev.filter((x) => x.name !== s.name));
                setMsg(`Skill «${s.name}» eliminada.`);
                setTimeout(() => setMsg(""), 3000);
              }}
            />
          </div>
        ))
      )}
    </div>
  );
}

// ─── Agents ───────────────────────────────────────────────────────

function AgentsPanel({ onRefresh }: { onRefresh: () => Promise<void> }) {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const data = await configService.getAgents();
      setAgents(data);
    } catch (err) {
      console.error("Error cargando agentes:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const onFocus = () => { setLoading(true); load(); };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [load]);

  if (loading) return <p className="text-sm text-app-text-secondary">Cargando...</p>;

  return (
    <div className="space-y-1">
      <p className="text-[11px] text-app-text-secondary leading-snug mb-2">
        Los agentes son asistentes especializados que pueden ser delegados por el agente principal
        para tareas específicas. Cada agente tiene su propio system prompt, herramientas y parámetros.
      </p>
      {msg && <p className="text-xs text-green-600 mb-1">{msg}</p>}
      {agents.length === 0 ? (
        <p className="text-sm text-app-text-secondary">No hay agentes configurados.</p>
      ) : (
        agents.map((a) => (
          <div key={a.name} className="flex items-start justify-between rounded-lg border border-app-primary-light bg-white px-3 py-2">
            <div className="min-w-0 flex-1">
              <span className="text-sm font-medium text-app-text break-words">{a.name}</span>
              {a.description && (
                <p className="text-xs text-app-text-secondary mt-0.5">{a.description}</p>
              )}
            </div>
            <DeleteBtn
              label={a.name}
              onDelete={async () => {
                await configService.deleteAgent(a.name);
                setAgents((prev) => prev.filter((x) => x.name !== a.name));
                setMsg(`Agente «${a.name}» eliminado.`);
                setTimeout(() => setMsg(""), 3000);
              }}
            />
          </div>
        ))
      )}
    </div>
  );
}

// ─── MCP ──────────────────────────────────────────────────────────

function McpPanel({ servers, loading, onRefresh }: { servers: McpServerStatus[]; loading: boolean; onRefresh: () => Promise<void> }) {
  const [msg, setMsg] = useState("");

  if (loading) return <p className="text-sm text-app-text-secondary">Cargando...</p>;

  return (
    <div className="space-y-1">
      <p className="text-[11px] text-app-text-secondary leading-snug mb-2">
        Los servidores MCP (Model Context Protocol) proveen herramientas externas al agente.
        Cada servidor puede exponer múltiples herramientas. Desactivar servidores que no se usan
        ahorra tokens, ya que las descripciones de sus herramientas se inyectan en el contexto.
      </p>
      {msg && <p className="text-xs text-green-600 mb-1">{msg}</p>}
      {servers.length === 0 ? (
        <p className="text-sm text-app-text-secondary">No hay servidores MCP configurados.</p>
      ) : (
        servers.map((s) => (
          <div key={s.label} className="flex items-start justify-between rounded-lg border border-app-primary-light bg-white px-3 py-2">
            <div className="flex flex-col gap-1 min-w-0 flex-1">
              <div className="flex items-center gap-2">
                {s.status === "connected" ? (
                  <Globe size={14} className="shrink-0 text-green-600" />
                ) : (
                  <Database size={14} className="shrink-0 text-app-text-secondary" />
                )}
                <span className="text-sm font-medium text-app-text min-w-0 break-words">{s.label}</span>
              </div>
              <span className={`text-xs px-1.5 py-0.5 rounded font-medium self-start ${
                s.status === "connected"
                  ? "bg-green-100 text-green-700"
                  : s.status === "failed"
                  ? "bg-red-100 text-red-700"
                  : "bg-gray-100 text-gray-500"
              }`}>
                {s.status === "connected" ? "Conectado" : s.status === "failed" ? "Error" : s.status}
              </span>
            </div>
            <DeleteBtn
              label={s.label}
              onDelete={async () => {
                await configService.deleteMcp(s.label);
                await onRefresh();
                setMsg(`Servidor MCP «${s.label}» eliminado.`);
                setTimeout(() => setMsg(""), 3000);
              }}
            />
          </div>
        ))
      )}
    </div>
  );
}

function RagPanel({ onRefresh }: { onRefresh: () => Promise<void> }) {
  const [collections, setCollections] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const data = await configService.listKnowledge();
      setCollections(data);
    } catch {
      setCollections([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const onFocus = () => { setLoading(true); load(); };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [load]);

  if (loading) return <p className="text-sm text-app-text-secondary">Cargando...</p>;

  return (
    <div className="space-y-1">
      <p className="text-[11px] text-app-text-secondary leading-snug mb-2">
        RAG (Retrieval-Augmented Generation) permite al agente buscar información en colecciones
        de documentos propias. Las colecciones se indexan con embeddings y se consultan por similitud.
      </p>
      {msg && <p className="text-xs text-green-600 mb-1">{msg}</p>}
      {collections.length === 0 ? (
        <p className="text-sm text-app-text-secondary">No hay colecciones RAG.</p>
      ) : (
        collections.map((c) => (
          <div key={c} className="flex items-start justify-between rounded-lg border border-app-primary-light bg-white px-3 py-2">
            <span className="text-sm font-medium text-app-text min-w-0 flex-1 break-words">{c}</span>
            <DeleteBtn
              label={c}
              onDelete={async () => {
                await configService.deleteKnowledge(c);
                setCollections((prev) => prev.filter((x) => x !== c));
                setMsg(`Colección «${c}» eliminada.`);
                setTimeout(() => setMsg(""), 3000);
              }}
            />
          </div>
        ))
      )}
    </div>
  );
}

export default AgentInfoTab;

// ─── Workflows ──────────────────────────────────────────────────

function WorkflowsPanel({ onRefresh }: { onRefresh: () => Promise<void> }) {
  const [available, setAvailable] = useState<string[]>(["smart"]);
  const [selected, setSelected] = useState("smart");
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const data = await configService.getWorkflowSelection();
      setAvailable(data.available?.length ? data.available : ["smart"]);
      setSelected(data.selected || "smart");
    } catch (err) {
      console.error("Error cargando workflows:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const onFocus = () => { load(); };
    const onChanged = (e: Event) => {
      const w = (e as CustomEvent).detail?.workflow;
      if (w) setSelected(w);
    };
    window.addEventListener("focus", onFocus);
    window.addEventListener("workflow-changed", onChanged);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("workflow-changed", onChanged);
    };
  }, [load]);

  const choose = async (workflow: string) => {
    setSaving(true);
    try {
      const sel = await configService.selectWorkflow(workflow);
      setSelected(sel);
      setMsg(workflow === "smart" ? "Flujo smart activado." : `Workflow «${workflow}» activado.`);
      setTimeout(() => setMsg(""), 3000);
    } catch (err) {
      console.error("Error seleccionando workflow:", err);
      setMsg("No se pudo activar el workflow.");
      setTimeout(() => setMsg(""), 3000);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <p className="text-sm text-app-text-secondary">Cargando...</p>;

  return (
    <div className="space-y-1">
      <p className="text-[11px] text-app-text-secondary leading-snug mb-2">
        Elegí un solo modo activo: smart (flujo estándar con paralelización) o un workflow
        determinista. La selección persiste y el chat la usa en el próximo mensaje.
        Mismo step corre en paralelo, distinto step es secuencial.
      </p>
      {msg && <p className="text-xs text-green-600 mb-1">{msg}</p>}
      {available.map((w) => (
        <div key={w} className="flex items-start justify-between rounded-lg border border-app-primary-light bg-white px-3 py-2">
          <div className="min-w-0 flex-1">
            <span className="text-sm font-medium text-app-text break-words">
              {w === "smart" ? "Smart (estándar)" : w}
            </span>
            {selected === w && (
              <p className="text-xs text-green-600 mt-0.5">Activo</p>
            )}
          </div>
          {selected !== w && (
            <button
              type="button"
              disabled={saving}
              onClick={() => choose(w)}
              className="text-xs bg-app-primary hover:opacity-90 text-white px-2 py-0.5 rounded disabled:opacity-50"
            >
              Activar
            </button>
          )}
        </div>
      ))}
      <WorkflowCreator onCreated={load} />
    </div>
  );
}

// ─── Workflow creator: visual node editor + agent generation ────

type DraftNode = {
  id: string;
  type: "agent" | "tool" | "rag";
  step: number;
  ref: string;
  prompt: string;
};

function WorkflowCreator({ onCreated }: { onCreated: () => Promise<void> | void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [nodes, setNodes] = useState<DraftNode[]>([]);
  const [yaml, setYaml] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const yamlEscape = (value: string): string => {
    const escaped = value
      .replace(/\\/g, "\\\\")
      .replace(/"/g, '\\"')
      .replace(/\n/g, "\\n")
      .replace(/\r/g, "\\r")
      .replace(/\t/g, "\\t");
    return `"${escaped}"`;
  };

  const syncYaml = (list: DraftNode[], wname: string) => {
    const lines = [
      `name: ${yamlEscape(wname || "mi-workflow")}`,
      `description: ${yamlEscape(description || "Workflow creado en el editor")}`,
      `version: "1"`,
      `retries: 2`,
      `on_failure: continue`,
      `nodes:`,
    ];
    list.forEach((n, i) => {
      lines.push(`  - id: ${yamlEscape(n.id || `nodo${i + 1}`)}`);
      lines.push(`    type: ${n.type}`);
      lines.push(`    step: ${n.step}`);
      if (n.type === "agent") lines.push(`    agent_name: ${yamlEscape(n.ref || "agente")}`);
      if (n.type === "tool") lines.push(`    tool: ${yamlEscape(n.ref || "read")}`);
      if (n.type === "rag") lines.push(`    collection: ${yamlEscape(n.ref || "coleccion")}`);
      if (n.prompt) lines.push(`    prompt: ${yamlEscape(n.prompt)}`);
      if (i === list.length - 1) lines.push(`    final: true`);
    });
    setYaml(lines.join("\n"));
  };

  const addNode = () => {
    const next = [...nodes, { id: `nodo${nodes.length + 1}`, type: "agent" as const, step: 1, ref: "", prompt: "" }];
    setNodes(next);
    syncYaml(next, name);
  };

  const updateNode = (idx: number, patch: Partial<DraftNode>) => {
    const next = nodes.map((n, i) => (i === idx ? { ...n, ...patch } : n));
    setNodes(next);
    syncYaml(next, name);
  };

  const removeNode = (idx: number) => {
    const next = nodes.filter((_, i) => i !== idx);
    setNodes(next);
    syncYaml(next, name);
  };

  const generate = async () => {
    if (!description.trim()) {
      setMsg("Describí el workflow primero.");
      return;
    }
    setBusy(true);
    setMsg("Generando con el agente...");
    try {
      const res = await configService.generateWorkflow(description.trim());
      setYaml(res.yaml);
      if (res.name) setName(res.name);
      setMsg("YAML generado. Revisalo y guardalo.");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "No se pudo generar.");
    } finally {
      setBusy(false);
    }
  };

  const validate = async () => {
    if (!yaml.trim()) {
      setMsg("No hay YAML para validar.");
      return;
    }
    setBusy(true);
    try {
      const res = await configService.validateWorkflow(yaml);
      setMsg(res.message);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Error validando.");
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!name.trim() || !yaml.trim()) {
      setMsg("Nombre y YAML requeridos.");
      return;
    }
    setBusy(true);
    try {
      await configService.saveWorkflow(name.trim(), yaml);
      setMsg(`Workflow «${name.trim()}» guardado.`);
      await onCreated();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "No se pudo guardar.");
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-2 text-xs bg-app-primary hover:opacity-90 text-white px-3 py-1.5 rounded"
      >
        Crear workflow
      </button>
    );
  }

  return (
    <div className="mt-2 rounded-lg border border-app-border bg-app-bg-secondary p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-app-text">Nuevo workflow</span>
        <button type="button" onClick={() => setOpen(false)} className="text-xs text-app-text-secondary hover:text-app-text">
          Cerrar
        </button>
      </div>
      <input
        value={name}
        onChange={(e) => { setName(e.target.value); syncYaml(nodes, e.target.value); }}
        placeholder="nombre-del-workflow"
        className="w-full text-xs px-2 py-1.5 rounded border border-app-border bg-white text-app-text"
      />
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Describí qué debe hacer el workflow..."
        rows={2}
        className="w-full text-xs px-2 py-1.5 rounded border border-app-border bg-white text-app-text"
      />
      <button
        type="button"
        disabled={busy}
        onClick={generate}
        className="text-xs bg-app-primary hover:opacity-90 text-white px-3 py-1.5 rounded disabled:opacity-50"
      >
        {busy ? "Generando..." : "Generar con agente"}
      </button>
      <div className="space-y-1">
        {nodes.map((n, i) => (
          <div key={i} className="rounded border border-app-border bg-white p-2 space-y-1">
            <div className="flex gap-1">
              <input
                value={n.id}
                onChange={(e) => updateNode(i, { id: e.target.value })}
                placeholder="id"
                className="w-1/3 text-xs px-1.5 py-1 rounded border border-app-border"
              />
              <select
                value={n.type}
                onChange={(e) => updateNode(i, { type: e.target.value as DraftNode["type"] })}
                className="w-1/3 text-xs px-1.5 py-1 rounded border border-app-border"
              >
                <option value="agent">agent</option>
                <option value="tool">tool</option>
                <option value="rag">rag</option>
              </select>
              <input
                type="number"
                min={1}
                value={n.step}
                onChange={(e) => updateNode(i, { step: Math.max(1, Number(e.target.value) || 1) })}
                title="Step: mismo step en paralelo, distinto secuencial"
                className="w-1/4 text-xs px-1.5 py-1 rounded border border-app-border"
              />
              <button type="button" onClick={() => removeNode(i)} className="text-xs text-red-500 px-1">
                ✕
              </button>
            </div>
            <input
              value={n.ref}
              onChange={(e) => updateNode(i, { ref: e.target.value })}
              placeholder={n.type === "agent" ? "agent_name" : n.type === "tool" ? "tool" : "collection"}
              className="w-full text-xs px-1.5 py-1 rounded border border-app-border"
            />
            <input
              value={n.prompt}
              onChange={(e) => updateNode(i, { prompt: e.target.value })}
              placeholder="prompt (opcional)"
              className="w-full text-xs px-1.5 py-1 rounded border border-app-border"
            />
          </div>
        ))}
        <button type="button" onClick={addNode} className="text-xs text-app-primary hover:underline">
          + Agregar nodo
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
      {msg && <p className="text-xs text-app-text-secondary">{msg}</p>}
      <div className="flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={validate}
          className="text-xs px-3 py-1.5 rounded border border-app-border hover:bg-app-bg-tertiary disabled:opacity-50"
        >
          Validar
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={save}
          className="text-xs bg-app-primary hover:opacity-90 text-white px-3 py-1.5 rounded disabled:opacity-50"
        >
          Guardar
        </button>
      </div>
    </div>
  );
}
