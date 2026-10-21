import { API_BASE_URL } from "../config/api";
/** Service for the persisted notifications (header bell). */


/** A finished workflow run or scheduled-task execution. */
export interface AppNotification {
  id: number;
  kind: "workflow" | "task";
  /** Workflow name or task name. */
  title: string;
  status: "success" | "error";
  /** Plain-language result or explanation for the user. */
  message: string;
  run_id: string | null;
  session_id: string | null;
  workflow_name: string | null;
  task_id: string | null;
  read: boolean;
  /** Local time, ISO format. */
  created_at: string;
}

async function list(): Promise<AppNotification[]> {
  const res = await fetch(`${API_BASE_URL}/api/notifications`);
  if (!res.ok) throw new Error("Error obteniendo las notificaciones");
  const data = await res.json();
  return (data.notifications || []) as AppNotification[];
}

/** Mark every notification as read (the user opened the bell). */
async function markAllRead(): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/notifications/read`, { method: "POST" });
  if (!res.ok) throw new Error("Error marcando las notificaciones como leídas");
}

async function remove(id: number): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/notifications/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.message || "Error eliminando la notificación");
  }
}

/** Delete every notification ("Limpiar"). */
async function clear(): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/notifications`, { method: "DELETE" });
  if (!res.ok) throw new Error("Error limpiando las notificaciones");
}

/** Complete output behind a notification (the bell only keeps a short text). */
async function detail(id: number): Promise<{ notification: AppNotification; output: string }> {
  const res = await fetch(`${API_BASE_URL}/api/notifications/${id}/detail`);
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.message || "No se pudo cargar el resultado.");
  return { notification: data.notification as AppNotification, output: String(data.output || "") };
}

/** Open a new conversation that already holds the output ("Revisar con el agente"). */
async function review(id: number): Promise<string> {
  const res = await fetch(`${API_BASE_URL}/api/notifications/${id}/review`, { method: "POST" });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.message || "No se pudo abrir la revisión con el agente.");
  return String(data.session_id);
}

const notificationService = { list, markAllRead, remove, clear, detail, review };

export default notificationService;
