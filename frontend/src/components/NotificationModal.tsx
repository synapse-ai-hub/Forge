import { useCallback, useEffect, useRef, useState, type ReactElement } from "react";
import { CheckCircle2, Loader2, MessageSquare, X, XCircle } from "lucide-react";
import { Button } from "./ui/button";
import { MarkdownRenderer } from "./chatBlocks";
import notificationService, { type AppNotification } from "../services/notificationService";

interface NotificationModalProps {
  /** Notification to show; `null` keeps the modal closed. */
  notification: AppNotification | null;
  onClose: () => void;
  /** Called with the session created by "Revisar con el agente". */
  onReviewed: (sessionId: string) => void;
}

/**
 * Format the time of a notification for the window title.
 *
 * @param iso - Local time in ISO format.
 * @returns Date and time, or an empty string when the value is not a date.
 */
function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** Movable window with the complete output of a workflow run or scheduled task. */
export function NotificationModal({ notification, onClose, onReviewed }: NotificationModalProps): ReactElement | null {
  const [output, setOutput] = useState("");
  const [loading, setLoading] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const drag = useRef<{ startX: number; startY: number; originX: number; originY: number } | null>(null);

  const id = notification?.id ?? null;

  useEffect(() => {
    if (id === null) return;
    let cancelled = false;
    setOutput("");
    setError(null);
    setOffset({ x: 0, y: 0 });
    setLoading(true);
    notificationService
      .detail(id)
      .then((data) => {
        if (!cancelled) setOutput(data.output);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "No se pudo cargar el resultado.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  useEffect(() => {
    if (id === null) return;
    /**
     * Close the window with Escape.
     *
     * @param e - Key pressed.
     */
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [id, onClose]);

  /**
   * Start dragging the window from its title bar.
   *
   * @param e - Pointer event on the title bar.
   */
  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>): void => {
    if ((e.target as HTMLElement).closest("button")) return;
    drag.current = { startX: e.clientX, startY: e.clientY, originX: offset.x, originY: offset.y };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  /**
   * Move the window while it is dragged.
   *
   * @param e - Pointer event on the title bar.
   */
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>): void => {
    const d = drag.current;
    if (!d) return;
    setOffset({ x: d.originX + e.clientX - d.startX, y: d.originY + e.clientY - d.startY });
  };

  /** Stop dragging the window. */
  const onPointerUp = (): void => {
    drag.current = null;
  };

  /** Open a new conversation with the output as context ("Revisar con el agente"). */
  const review = useCallback(async (): Promise<void> => {
    if (id === null) return;
    setReviewing(true);
    setError(null);
    try {
      const sessionId = await notificationService.review(id);
      onReviewed(sessionId);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo abrir la revisión.");
    } finally {
      setReviewing(false);
    }
  }, [id, onClose, onReviewed]);

  if (!notification) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none">
      <div
        role="dialog"
        aria-label={notification.title}
        className="pointer-events-auto flex flex-col w-[min(720px,calc(100vw-2rem))] max-h-[80vh] min-w-[320px] min-h-[200px] resize overflow-hidden bg-white border border-gray-200 rounded-xl shadow-2xl"
        style={{ transform: `translate(${offset.x}px, ${offset.y}px)` }}
      >
        <div
          className="flex items-center gap-2 px-4 py-3 border-b border-gray-200 cursor-move select-none touch-none"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        >
          {notification.status === "success" ? (
            <CheckCircle2 size={18} className="shrink-0 text-green-600" />
          ) : (
            <XCircle size={18} className="shrink-0 text-red-500" />
          )}
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-app-text truncate">{notification.title}</p>
            <p className="text-xs text-app-text-secondary">
              {formatDate(notification.created_at)}
              {" · "}
              {notification.kind === "schedule" ? "Tarea programada" : "Workflow"}
              {" · "}
              {notification.status === "success" ? "Ejecutado con éxito" : "Falló"}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded p-1 text-app-text-secondary hover:bg-gray-100 hover:text-app-text transition-colors"
            aria-label="Cerrar"
            title="Cerrar"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3">
          {loading ? (
            <p className="flex items-center gap-2 text-sm text-app-text-secondary">
              <Loader2 size={14} className="animate-spin" /> Cargando…
            </p>
          ) : (
            <MarkdownRenderer content={output || notification.message} />
          )}
          {error && <p className="mt-2 text-xs text-red-500 break-words">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 px-4 py-3 border-t border-gray-200">
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cerrar
          </Button>
          <Button size="sm" onClick={review} disabled={reviewing || loading} className="gap-1.5">
            {reviewing ? <Loader2 size={14} className="animate-spin" /> : <MessageSquare size={14} />}
            Revisar con el agente
          </Button>
        </div>
      </div>
    </div>
  );
}
