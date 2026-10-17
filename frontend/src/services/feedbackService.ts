const MODE = import.meta.env.VITE_MODE || "dev";
const API_BASE_URL = MODE === "prod"
  ? (import.meta.env.VITE_URL_PROD || "http://localhost:8000")
  : (import.meta.env.VITE_URL_DEV || "http://localhost:8000");

export type FeedbackType = "up" | "down";

/** Feedback of the answers of a session, keyed by turn number. */
export type SessionFeedback = Record<number, FeedbackType>;

interface FeedbackResponse<T> {
  status: string;
  message?: string;
  data?: T;
}

async function readResponse<T>(response: Response): Promise<FeedbackResponse<T>> {
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }
  const result = (await response.json()) as FeedbackResponse<T>;
  if (result.status === "error") {
    throw new Error(result.message || "Error de feedback");
  }
  return result;
}

const feedbackService = {
  /** Feedback of every answer of a session. */
  async getSessionFeedback(sessionId: string): Promise<SessionFeedback> {
    const response = await fetch(
      `${API_BASE_URL}/api/feedback/${encodeURIComponent(sessionId)}`,
      { method: "GET" },
    );
    const result = await readResponse<Record<string, FeedbackType>>(response);
    const feedback: SessionFeedback = {};
    for (const [turn, type] of Object.entries(result.data ?? {})) {
      feedback[Number(turn)] = type;
    }
    return feedback;
  },

  /** Save the feedback of an answer, or change it if it already has one. */
  async setFeedback(sessionId: string, turn: number, type: FeedbackType): Promise<void> {
    const response = await fetch(
      `${API_BASE_URL}/api/feedback/${encodeURIComponent(sessionId)}/${turn}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback_type: type }),
      },
    );
    await readResponse<undefined>(response);
  },

  /** Remove the feedback of an answer. */
  async clearFeedback(sessionId: string, turn: number): Promise<void> {
    const response = await fetch(
      `${API_BASE_URL}/api/feedback/${encodeURIComponent(sessionId)}/${turn}`,
      { method: "DELETE" },
    );
    await readResponse<undefined>(response);
  },
};

export default feedbackService;
