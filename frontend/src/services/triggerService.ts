import { API_BASE_URL } from "../config/api";
/** Service for triggers: list with state and create mapped to a workflow. */

/** A trigger without its secret. */
export interface TriggerItem {
  slug: string;
  workflow_name: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

/** Result of creating a trigger, with the secret shown once. */
export interface TriggerCreated {
  slug: string;
  workflow_name: string;
  secret: string;
}

/** List triggers with pagination. */
async function list(limit: number = 50, offset: number = 0): Promise<TriggerItem[]> {
  try {
    const res = await fetch(
      `${API_BASE_URL}/api/triggers?limit=${limit}&offset=${offset}`
    );
    const data = await res.json().catch(() => null);
    if (!res.ok || data?.status === "error") {
      throw new Error(data?.message || "Error obteniendo los triggers");
    }
    const items = data?.data;
    return (Array.isArray(items) ? items : []) as TriggerItem[];
  } catch (exc) {
    if (exc instanceof Error) throw exc;
    throw new Error("Error obteniendo los triggers");
  }
}

/** A delivery of a trigger for audit. */
export interface TriggerRun {
  event_id: string;
  trigger_slug: string;
  workflow_name: string;
  status: string;
  attempt: number;
  idempotency_key: string | null;
  payload_hash: string | null;
  workflow_run_id: string | null;
  result: string | null;
  error_text: string | null;
  started_at: string;
  finished_at: string | null;
}

/** Create a trigger mapped to a workflow. Returns the secret shown once. */
async function create(slug: string, workflowName: string): Promise<TriggerCreated> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/triggers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug, workflow_name: workflowName }),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok || data?.status === "error" || !data?.data?.slug || !data?.data?.secret) {
      throw new Error(data?.message || "No se pudo crear el trigger.");
    }
    return data.data as TriggerCreated;
  } catch (exc) {
    if (exc instanceof Error) throw exc;
    throw new Error("No se pudo crear el trigger.");
  }
}

/** Rotate the secret of a trigger. Returns the new secret shown once. */
async function rotate(slug: string): Promise<TriggerCreated> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/triggers/${encodeURIComponent(slug)}/rotate`, {
      method: "POST",
    });
    const data = await res.json().catch(() => null);
    if (!res.ok || data?.status === "error" || !data?.data?.secret) {
      throw new Error(data?.message || "No se pudo rotar el secreto.");
    }
    return data.data as TriggerCreated;
  } catch (exc) {
    if (exc instanceof Error) throw exc;
    throw new Error("No se pudo rotar el secreto.");
  }
}

/** Pause or reactivate a trigger. */
async function setEnabled(slug: string, enabled: boolean): Promise<TriggerItem> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/triggers/${encodeURIComponent(slug)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok || data?.status === "error" || !data?.data) {
      throw new Error(data?.message || "No se pudo actualizar el trigger.");
    }
    return data.data as TriggerItem;
  } catch (exc) {
    if (exc instanceof Error) throw exc;
    throw new Error("No se pudo actualizar el trigger.");
  }
}

/** List deliveries of a trigger with pagination. */
async function listRuns(slug: string, limit: number = 50, offset: number = 0): Promise<TriggerRun[]> {
  try {
    const res = await fetch(
      `${API_BASE_URL}/api/triggers/${encodeURIComponent(slug)}/runs?limit=${limit}&offset=${offset}`
    );
    const data = await res.json().catch(() => null);
    if (!res.ok || data?.status === "error") {
      throw new Error(data?.message || "Error obteniendo las entregas");
    }
    const items = data?.data;
    return (Array.isArray(items) ? items : []) as TriggerRun[];
  } catch (exc) {
    if (exc instanceof Error) throw exc;
    throw new Error("Error obteniendo las entregas");
  }
}

/** Delete a trigger with confirmation. */
async function remove(slug: string): Promise<boolean> {
  try {
    const res = await fetch(
      `${API_BASE_URL}/api/triggers/${encodeURIComponent(slug)}?confirm=true`,
      { method: "DELETE" }
    );
    const data = await res.json().catch(() => null);
    if (!res.ok || data?.status === "error") {
      throw new Error(data?.message || "No se pudo borrar el trigger.");
    }
    return true;
  } catch (exc) {
    if (exc instanceof Error) throw exc;
    throw new Error("No se pudo borrar el trigger.");
  }
}

const triggerService = { list, create, rotate, setEnabled, listRuns, remove };

export default triggerService;
