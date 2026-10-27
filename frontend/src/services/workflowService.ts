import { API_BASE_URL } from "../config/api";
/** Service for workflows: list with state, play, cancel and delete. */


export type WorkflowRunStatus = "running" | "success" | "error" | "cancelled";

/** One execution of a workflow. */
export interface WorkflowRun {
  id: string;
  workflow_name: string;
  source: "play" | "tool" | null;
  status: WorkflowRunStatus;
  attempt: number | null;
  /** Local time, ISO format. */
  started_at: string;
  finished_at: string | null;
  result: string | null;
  /** Plain-language explanation when the run failed. */
  error_text: string | null;
}

/** A workflow with its running state and latest run. */
export interface WorkflowItem {
  name: string;
  description: string;
  running: boolean;
  run_id: string | null;
  last_run: WorkflowRun | null;
}

/** Detail of a run state change pushed by the backend (event bus). */
export interface WorkflowRunEvent {
  run_id: string;
  workflow: string;
  status: WorkflowRunStatus;
  attempt: number | null;
}

async function list(): Promise<WorkflowItem[]> {
  const res = await fetch(`${API_BASE_URL}/api/workflows`);
  if (!res.ok) throw new Error("Error obteniendo los workflows");
  const data = await res.json();
  return (data.workflows || []) as WorkflowItem[];
}

/** Start a run in the background (the play button). */
async function run(name: string): Promise<{ run_id: string }> {
  const res = await fetch(`${API_BASE_URL}/api/workflows/${encodeURIComponent(name)}/run`, {
    method: "POST",
  });
  const data = await res.json().catch(() => null);
  if (!res.ok || data?.status === "error") {
    throw new Error(data?.message || "No se pudo ejecutar el workflow.");
  }
  return data.data;
}

async function cancel(runId: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/workflows/runs/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.message || "No se pudo cancelar la ejecución.");
  }
}

/** Delete a workflow with its runs and notifications. */
async function remove(name: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/workflows/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.message || "No se pudo eliminar el workflow.");
  }
}

const workflowService = { list, run, cancel, remove };

export default workflowService;
