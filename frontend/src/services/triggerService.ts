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

async function list(): Promise<TriggerItem[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/triggers`);
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
  status: string;
  workflow_run_id: string | null;
  result: string | null;
  started_at: string;
  finished_at: string | null;
}

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

async function listRuns(slug: string): Promise<TriggerRun[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/triggers/${encodeURIComponent(slug)}/runs`);
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

const triggerService = { list, create, rotate, setEnabled, listRuns };

export default triggerService;
