import { API_BASE_URL } from "../config/api";

export interface ContextFile {
  id: number;
  filename: string;
  created_at: string;
}

export interface ContextFilesResponse {
  status: string;
  message: string;
  data: {
    files: ContextFile[];
  };
}

export const contextFilesService = {
  /** Upload a file as context. */
  async upload(file: File): Promise<{ id: number; filename: string }> {
    const form = new FormData();
    form.append("file", file);

    const res = await fetch(`${API_BASE_URL}/api/context-files`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${txt}`);
    }
    const result = await res.json();
    if (result.status === "error") {
      throw new Error(result.message || "Error al subir archivo");
    }
    return result.data;
  },

  /** List all uploaded context files. */
  async list(): Promise<ContextFile[]> {
    const res = await fetch(`${API_BASE_URL}/api/context-files`, {
      method: "GET",
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${txt}`);
    }
    const result = await res.json();
    if (result.status === "error") {
      throw new Error(result.message || "Error al listar archivos");
    }
    return result.data.files;
  },

  /** Delete a context file by ID. */
  async delete(id: number): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/api/context-files/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${txt}`);
    }
    const result = await res.json();
    if (result.status === "error") {
      throw new Error(result.message || "Error al eliminar archivo");
    }
  },
};

export default contextFilesService;
