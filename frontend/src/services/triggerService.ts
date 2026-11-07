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

const triggerService = { list, create };

export default triggerService;
