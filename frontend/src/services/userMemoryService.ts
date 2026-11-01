import { API_BASE_URL } from "../config/api";

export interface UserPreference {
  id: string;
  text: string;
  metadata?: Record<string, unknown>;
}

export const userMemoryService = {
  /** List all user preferences. */
  async list(): Promise<UserPreference[]> {
    const res = await fetch(`${API_BASE_URL}/api/user-memory`, {
      method: "GET",
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${txt}`);
    }
    const result = await res.json();
    if (result.status === "error") {
      throw new Error(result.message || "Error al listar preferencias");
    }
    const prefs = result.data?.preferences;
    return Array.isArray(prefs) ? prefs : [];
  },

  /** Add a user preference. */
  async add(text: string): Promise<UserPreference> {
    const res = await fetch(`${API_BASE_URL}/api/user-memory`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${txt}`);
    }
    const result = await res.json();
    if (result.status === "error") {
      throw new Error(result.message || "Error al guardar preferencia");
    }
    return result.data;
  },

  /** Delete a user preference by id. */
  async remove(id: string): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/api/user-memory/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${txt}`);
    }
    const result = await res.json();
    if (result.status === "error") {
      throw new Error(result.message || "Error al eliminar preferencia");
    }
  },
};

export default userMemoryService;
