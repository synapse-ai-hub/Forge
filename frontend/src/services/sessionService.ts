const MODE = import.meta.env.VITE_MODE || "dev";
const API_BASE_URL = MODE === "prod"
  ? (import.meta.env.VITE_URL_PROD || "http://localhost:8000")
  : (import.meta.env.VITE_URL_DEV || "http://localhost:8000");

export interface ChatSession {
  session_id: string;
  title: string;
  preview: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface TextBlock {
  type: "text";
  content: string;
}

export interface ReasoningBlock {
  type: "reasoning";
  content: string;
}

export interface ToolBlock {
  type: "tool";
  name: string;
  args: Record<string, any>;
  result?: any;
}

export type ContentBlock = TextBlock | ReasoningBlock | ToolBlock;

export interface SessionMessage {
  id: string;
  type: "user" | "assistant";
  content: string;
  /** Turn of the session the message belongs to. */
  turn_number?: number | null;
  reasoning?: string | null;
  toolCalls?: Array<{ id?: string; name: string; args: Record<string, any> }> | null;
  toolResults?: Array<{ tool_call_id?: string; tool_name: string; result: any }> | null;
  blocks?: ContentBlock[] | null;
  /** Attached files for user messages (shown as chips) */
  files?: Array<{ name: string; size?: number }> | null;
  /** User message the guardrail blocked (its content is the fixed blocked text). */
  blocked?: boolean;
}

export interface SessionContext {
  prompt_tokens: number | null;
  context_window: number | null;
  percent: number | null;
}

export interface SessionMessages {
  session_id: string;
  messages: SessionMessage[];
  context?: SessionContext;
}

export interface SessionListResponse {
  status: string;
  message: string;
  data: ChatSession[];
}

export interface SessionDetailResponse {
  status: string;
  message: string;
  data: SessionMessages;
}

export const sessionService = {
  /** List all chat sessions ordered by most recent activity. */
  async listSessions(): Promise<ChatSession[]> {
    const response = await fetch(`${API_BASE_URL}/api/sessions`, {
      method: "GET",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const result = (await response.json()) as SessionListResponse;
    if (result && result.status === "error") {
      throw new Error(result.message || "Error al obtener las sesiones");
    }
    return Array.isArray(result.data) ? result.data : [];
  },

  /** Load the full message history of a session. */
  async getSession(sessionId: string): Promise<SessionMessages> {
    const response = await fetch(
      `${API_BASE_URL}/api/sessions/${encodeURIComponent(sessionId)}`,
      { method: "GET" },
    );
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const result = (await response.json()) as SessionDetailResponse;
    if (result && result.status === "error") {
      throw new Error(result.message || "Error al obtener la sesión");
    }
    return result.data;
  },

  /** Delete a session and all its messages. */
  async deleteSession(sessionId: string): Promise<void> {
    const response = await fetch(
      `${API_BASE_URL}/api/sessions/${encodeURIComponent(sessionId)}`,
      { method: "DELETE" },
    );
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
  },
};

export default sessionService;
