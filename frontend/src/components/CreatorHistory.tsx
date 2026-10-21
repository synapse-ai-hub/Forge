import { useCallback, useEffect, useState } from "react";
import { MessageSquare, Plus, Trash2 } from "lucide-react";
import creatorHistoryService, {
  type CreatorConversation,
  type CreatorConversationItem,
  type CreatorKind,
} from "../services/creatorHistoryService";

interface CreatorHistoryProps {
  /** Kind of creator whose conversations are listed. */
  kind: CreatorKind;
  /** Conversation open in the page. */
  activeId: string;
  /** Changes when the list has to be loaded again (a request ended). */
  refreshKey: number;
  /** Called with the conversation the user opened. */
  onSelect: (conversation: CreatorConversation) => void;
  /** Called when the user starts a new conversation. */
  onNew: () => void;
  /** Called when the open conversation was deleted. */
  onDeletedActive: () => void;
  /** Disables the list while the creator is streaming. */
  disabled?: boolean;
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("es-AR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function titleOf(item: CreatorConversationItem): string {
  if (item.item_name) return item.item_name;
  const first = (item.first_message || "").trim().replace(/\s+/g, " ");
  return first ? (first.length > 60 ? `${first.slice(0, 57)}…` : first) : "Sin título";
}

/** Sidebar with the conversations of a creator, to reopen them and keep modifying what was created. */
export function CreatorHistory({
  kind,
  activeId,
  refreshKey,
  onSelect,
  onNew,
  onDeletedActive,
  disabled = false,
}: CreatorHistoryProps) {
  const [items, setItems] = useState<CreatorConversationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await creatorHistoryService.list(kind));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cargar el historial.");
    } finally {
      setLoading(false);
    }
  }, [kind]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const open = async (id: string) => {
    if (disabled || busyId) return;
    setBusyId(id);
    try {
      onSelect(await creatorHistoryService.get(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo abrir la conversación.");
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (disabled || busyId || !window.confirm("¿Eliminar esta conversación?")) return;
    setBusyId(id);
    try {
      await creatorHistoryService.remove(id);
      if (id === activeId) onDeletedActive();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo eliminar la conversación.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <aside className="w-64 shrink-0 hidden md:flex flex-col min-h-0 bg-app-bg-secondary border-r border-app-border">
      <div className="p-3 border-b border-app-border bg-white">
        <button
          type="button"
          onClick={onNew}
          disabled={disabled}
          className="w-full flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-white bg-app-primary hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          <Plus size={16} />
          Nueva conversación
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-1.5 min-h-0">
        {error && <div className="text-xs text-red-500 break-words">{error}</div>}
        {loading ? (
          <div className="text-center py-4 text-sm text-app-text-secondary">Cargando...</div>
        ) : items.length === 0 ? (
          <div className="text-center py-4 text-sm text-app-text-secondary">
            No hay conversaciones todavía.
          </div>
        ) : (
          items.map((item) => {
            const isActive = item.creator_id === activeId;
            return (
              <div
                key={item.creator_id}
                onClick={() => open(item.creator_id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    open(item.creator_id);
                  }
                }}
                className={`group w-full text-left p-2.5 rounded-lg border cursor-pointer transition-colors ${
                  isActive
                    ? "ring-2 ring-app-primary-light border-transparent bg-white"
                    : "border-transparent bg-white hover:bg-app-bg-tertiary"
                } ${disabled ? "opacity-60 pointer-events-none" : ""}`}
              >
                <div className="flex items-start gap-2">
                  <MessageSquare size={14} className="mt-0.5 shrink-0 text-app-primary" />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium text-app-text truncate">{titleOf(item)}</div>
                    <div className="text-[11px] text-app-text-secondary mt-0.5">
                      {formatTimestamp(item.updated_at)}
                      {item.status === "error" ? " · falló" : ""}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => remove(item.creator_id, e)}
                    disabled={busyId === item.creator_id}
                    className="shrink-0 rounded p-1 text-app-text-secondary opacity-0 group-hover:opacity-100 hover:bg-red-100 hover:text-app-error transition-all"
                    aria-label="Eliminar conversación"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}

export default CreatorHistory;
