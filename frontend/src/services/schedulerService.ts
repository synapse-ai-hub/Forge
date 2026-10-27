import { API_BASE_URL } from "../config/api";
import { selectionToRequest, type ResourceSelection } from "../utils/resourceSelection";
/** Service for the scheduled tasks (agenda): workflows with a schedule, their runs and their creation. */

/** Schedule slot: a time of the day and the weekdays it runs. */
export interface ScheduleSlot {
  /** Local time in "HH:MM" (24h). */
  time: string;
  /** Weekdays (0=Sunday ... 6=Saturday). */
  days: number[];
}

/** Scheduled task: a workflow whose YAML has a `schedule` block. */
export interface SchedulerTask {
  /** Name of the workflow (it is also the id of the task). */
  id: string;
  name: string;
  /** What the task does (the description of the workflow). */
  prompt: string;
  /** Local time of the main slot in "HH:MM" (24h). */
  time: string;
  /** Weekdays of the main slot (0=Sunday ... 6=Saturday). */
  days: number[];
  enabled: boolean;
  /** Additional slots. */
  repetitions: ScheduleSlot[] | null;
  created_at: string;
  updated_at: string;
}

/** Data to create a scheduled task. */
export interface NewScheduledTask {
  name: string;
  /** What the task has to do. */
  prompt: string;
  time: string;
  days: number[];
  repetitions: ScheduleSlot[] | null;
  /** What the user picked in the permission cards: the workflow has to use it. */
  seleccion: ResourceSelection;
}

/** An execution of a scheduled task. */
export interface SchedulerRun {
  id: string;
  task_id: string;
  prompt: string | null;
  name: string | null;
  status: "running" | "success" | "error";
  detail: string | null;
  started_at: string;
  finished_at: string | null;
}

/**
 * List the scheduled tasks sorted by time.
 *
 * @returns The tasks, or an empty list when there are none.
 * @throws Error when the request fails.
 */
async function getTasks(): Promise<SchedulerTask[]> {
  const res = await fetch(`${API_BASE_URL}/api/scheduler/tasks`);
  if (!res.ok) throw new Error("Error obteniendo tareas programadas");
  const data = await res.json();
  return (data.tasks || []) as SchedulerTask[];
}

/**
 * Create a scheduled task: the workflow creator (an LLM) writes its YAML with the schedule.
 *
 * @param task - The task to create.
 * @param onProgress - Called with the text the creator streams while it works.
 * @returns The final message of the creator.
 * @throws Error when the creator fails or the request fails.
 */
async function createTask(task: NewScheduledTask, onProgress?: (text: string) => void): Promise<string> {
  const res = await fetch(`${API_BASE_URL}/api/create/workflow`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      descripcion: task.prompt,
      name: task.name,
      ...selectionToRequest(task.seleccion),
      schedule: {
        enabled: true,
        slots: [{ time: task.time, days: task.days }, ...(task.repetitions || [])],
      },
    }),
  });
  if (!res.ok || !res.body) throw new Error("Error creando la tarea programada");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let streamed = "";
  let final: { status: string; message: string } | null = null;
  let failure: string | null = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const event of events) {
      const line = event.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      let payload: { type?: string; content?: unknown };
      try {
        payload = JSON.parse(line.slice(6));
      } catch {
        continue;
      }
      if (payload.type === "chunk" && typeof payload.content === "string") {
        streamed += payload.content;
        onProgress?.(streamed);
      } else if (payload.type === "workflow_result_final") {
        const content = payload.content as { status?: string; message?: string };
        final = { status: content.status ?? "error", message: content.message ?? "" };
      } else if (payload.type === "error") {
        failure = String(payload.content ?? "Error creando la tarea programada");
      }
    }
  }
  if (failure) throw new Error(failure);
  if (!final) throw new Error("El creador terminó sin crear la tarea.");
  if (final.status !== "success") throw new Error(final.message || "No se pudo crear la tarea.");
  return final.message;
}

/**
 * Change the schedule of a task.
 *
 * @param taskId - Id of the task (the name of its workflow).
 * @param payload - New main time and days, additional slots or the enabled flag.
 * @returns The message of the server and the updated task.
 * @throws Error when the schedule is invalid or the request fails.
 */
async function updateTask(
  taskId: string,
  payload: Partial<{
    time: string;
    days: number[];
    enabled: boolean;
    repetitions: ScheduleSlot[] | null;
  }>,
): Promise<{ message: string; task: SchedulerTask }> {
  const res = await fetch(`${API_BASE_URL}/api/scheduler/tasks/${encodeURIComponent(taskId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.message || "Error actualizando la tarea programada");
  return data;
}

/**
 * Delete a task with its workflow, runs and notifications.
 *
 * @param taskId - Id of the task (the name of its workflow).
 * @throws Error when it cannot be deleted.
 */
async function deleteTask(taskId: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/scheduler/tasks/${encodeURIComponent(taskId)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.message || "Error eliminando la tarea programada");
  }
}

/**
 * List the most recent runs started by the scheduler.
 *
 * @returns The runs, newest first.
 * @throws Error when the request fails.
 */
async function getRuns(): Promise<SchedulerRun[]> {
  const res = await fetch(`${API_BASE_URL}/api/scheduler/runs`);
  if (!res.ok) throw new Error("Error obteniendo ejecuciones de tareas");
  const data = await res.json();
  return (data.runs || []) as SchedulerRun[];
}

const schedulerService = {
  getTasks,
  createTask,
  updateTask,
  deleteTask,
  getRuns,
};

export default schedulerService;
