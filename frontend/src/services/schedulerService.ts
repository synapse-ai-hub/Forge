/** Service for scheduled tasks (agenda): CRUD + execution history. */

const API_BASE_URL = import.meta.env.VITE_URL_BASE || "http://localhost:8000";

/** Permission entry: "allow" | "deny". */
export type PermissionAction = "allow" | "deny";

/**
 * Tool permissions: flat (``read: "allow"``) or grouped
 * (``workflow: { nightly: "allow" }``).
 */
export type ToolPermissions = Record<string, PermissionAction | Record<string, PermissionAction>>;

/** Schedule slot for additional repetitions. */
export interface ScheduleSlot {
  time: string;
  days: number[];
}

/** Model parameters override for the task's sub-agent. */
export interface TaskParameters {
  temperature?: number;
  top_p?: number;
  max_tokens?: number;
  seed?: number;
  model?: string;
  reasoning_effort?: string;
}

/** Task scheduled to run at given local times on specific weekdays. */
export interface SchedulerTask {
  id: string;
  /** Unique name used as sub-agent identifier. */
  name: string;
  /** What the agent should do when the task fires. */
  prompt: string;
  /** Primary local time in "HH:MM" (24h). */
  time: string;
  /** Primary selected weekdays (0=Sunday ... 6=Saturday). */
  days: number[];
  enabled: boolean;
  /** Additional schedule slots (time + days pairs). */
  repetitions: ScheduleSlot[] | null;
  /** Tool permissions override (null = router default). */
  tool_permissions: ToolPermissions | null;
  /** Skill permissions override (null = router default). */
  skill_permissions: Record<string, PermissionAction> | null;
  /** Model parameters override (null = use defaults). */
  parameters: TaskParameters | null;
  last_run_date: string | null;
  /** Per-slot last-run dates: { "HH:MM_0,1,2": "YYYY-MM-DD" } */
  slot_runs: Record<string, string> | null;
  created_at: string;
  updated_at: string;
}

/** A recorded execution of a scheduled task. */
export interface SchedulerRun {
  id: number;
  task_id: string;
  prompt: string | null;
  name: string | null;
  session_id: string | null;
  status: "success" | "error";
  detail: string | null;
  started_at: string;
  finished_at: string | null;
}

/** Catalog item for permission checkboxes. */
export interface CatalogItem {
  name: string;
  description: string;
}

/** Permissions catalog returned by /scheduler/permissions/catalog. */
export interface PermissionsCatalog {
  tools: CatalogItem[];
  skills: CatalogItem[];
  agents: CatalogItem[];
  workflows: CatalogItem[];
}

async function getTasks(): Promise<SchedulerTask[]> {
  const res = await fetch(`${API_BASE_URL}/api/scheduler/tasks`);
  if (!res.ok) throw new Error("Error obteniendo tareas programadas");
  const data = await res.json();
  return (data.tasks || []) as SchedulerTask[];
}

async function createTask(payload: {
  name: string;
  prompt: string;
  time: string;
  days: number[];
  tool_permissions?: ToolPermissions | null;
  skill_permissions?: Record<string, PermissionAction> | null;
  parameters?: TaskParameters | null;
  repetitions?: ScheduleSlot[] | null;
}): Promise<{ message: string; task: SchedulerTask }> {
  const res = await fetch(`${API_BASE_URL}/api/scheduler/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.message || "Error creando la tarea programada");
  return data;
}

async function updateTask(
  taskId: string,
  payload: Partial<{
    name: string;
    prompt: string;
    time: string;
    days: number[];
    enabled: boolean;
    tool_permissions: ToolPermissions | null;
    skill_permissions: Record<string, PermissionAction> | null;
    parameters: TaskParameters | null;
    repetitions: ScheduleSlot[] | null;
  }>,
): Promise<{ message: string; task: SchedulerTask }> {
  const res = await fetch(`${API_BASE_URL}/api/scheduler/tasks/${taskId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.message || "Error actualizando la tarea programada");
  return data;
}

async function deleteTask(taskId: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/scheduler/tasks/${taskId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.message || "Error eliminando la tarea programada");
  }
}

async function getRuns(): Promise<SchedulerRun[]> {
  const res = await fetch(`${API_BASE_URL}/api/scheduler/runs`);
  if (!res.ok) throw new Error("Error obteniendo ejecuciones de tareas");
  const data = await res.json();
  return (data.runs || []) as SchedulerRun[];
}

async function craftPrompt(prompt: string): Promise<string> {
  const res = await fetch(`${API_BASE_URL}/api/scheduler/craft-prompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok || data?.status === "error") {
    throw new Error(data?.message || "Error mejorando el prompt");
  }
  const refined = data?.data?.prompt;
  if (typeof refined !== "string" || !refined) {
    throw new Error("Respuesta inválida del servidor.");
  }
  return refined;
}

async function getPermissionsCatalog(): Promise<PermissionsCatalog> {
  const res = await fetch(`${API_BASE_URL}/api/scheduler/permissions/catalog`);
  if (!res.ok) throw new Error("Error obteniendo catálogo de permisos");
  const data = await res.json();
  return {
    tools: data.tools || [],
    skills: data.skills || [],
    agents: data.agents || [],
    workflows: data.workflows || [],
  };
}

const schedulerService = {
  getTasks,
  createTask,
  updateTask,
  deleteTask,
  getRuns,
  craftPrompt,
  getPermissionsCatalog,
};

export default schedulerService;
