import { API_BASE_URL } from "../config/api";

export interface StreamEvent {
  type: string;
  content: any;
}

export interface ChatParams {
  message: string;
  files?: File[];
  sessionId?: string | null;
  /** When set, the backend delivers the final answer to this Telegram chat. */
  telegramChatId?: string | null;
}

let activeController: AbortController | null = null;

const chatService = {
  /**
   * Send a message to the chat endpoint with SSE streaming support.
   * Supports file attachments via FormData.
   * Yields parsed SSE events as StreamEvent objects.
   */
  async *sendMessage(params: ChatParams): AsyncGenerator<StreamEvent> {
    const _t0 = performance.now();
    // console.log(`[DEBUG_TIEMPO_SSE] sendMessage started — t=${_t0}`);
    const { message, files, sessionId, telegramChatId } = params;
    const controller = new AbortController();
    activeController = controller;

    const formData = new FormData();
    formData.append("message", message);
    if (sessionId) formData.append("session_id", sessionId);
    if (telegramChatId) formData.append("telegram_chat_id", telegramChatId);
    if (files && files.length > 0) {
      files.forEach((f) => formData.append("files", f));
    }

    const response = await fetch(`${API_BASE_URL}/api/chat`, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });

    // console.log(`[DEBUG_TIEMPO_SSE] sendMessage fetch response received — status=${response.status}, t=${performance.now()}, elapsed=${performance.now() - _t0}`);

    if (!response.ok) {
      const errorBody = await response.text().catch(() => "");
      throw new Error(
        `HTTP ${response.status}: ${errorBody || response.statusText}`
      );
    }

    if (!response.body) {
      throw new Error("Response body is null — streaming not available");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          // console.log(`[DEBUG_TIEMPO_SSE] reader.done — stream closed naturally, t=${performance.now()}`);
          buffer += decoder.decode(); // Flush decoder residual bytes
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (const part of parts) {
          const lines = part.split("\n");
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const data = line.slice(6);
              // [DONE] is a raw marker, not JSON — skip parsing
              if (data === "[DONE]") {
                // console.log(`[DEBUG_TIEMPO_SSE] [DONE] raw marker received, returning generator — t=${performance.now()}, elapsed=${performance.now() - _t0}`);
                yield { type: "done", content: "[DONE]" };
                return;
              }
              try {
                const parsed = JSON.parse(data);
                yield parsed as StreamEvent;
                if (parsed.type === "done" && parsed.content === "[DONE]") {
                  return;
                }
              } catch {
                console.warn("Malformed SSE JSON, skipping:", data);
              }
            }
          }
        }
      }
      // console.log(`[DEBUG_TIEMPO_SSE] sendMessage while loop ended (no more SSE data) — t=${performance.now()}`);
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // console.log(`[DEBUG_TIEMPO_SSE] sendMessage caught AbortError, yielding cancel — t=${performance.now()}`);
        yield { type: "chunk", content: "*Transmisión cancelada.*" };
        return;
      }
      throw err;
    } finally {
      // console.log(`[DEBUG_TIEMPO_SSE] sendMessage finally — reader.releaseLock(), t=${performance.now()}`);
      reader.releaseLock();
      activeController = null;
    }
  },

  /** Cancel an active stream by aborting the underlying fetch request. */
  cancelStream(): void {
    // console.log(`[DEBUG_TIEMPO_SSE] cancelStream called — t=${performance.now()}`);
    if (activeController) {
      // console.log(`[DEBUG_TIEMPO_SSE] cancelStream — aborting controller, t=${performance.now()}`);
      activeController.abort();
      activeController = null;
    } else {
      // console.log(`[DEBUG_TIEMPO_SSE] cancelStream — no activeController, t=${performance.now()}`);
    }
  },

  /** Delete the active conversation for a user in the backend. */
  async deleteConversation(userId: string): Promise<void> {
    const formData = new FormData();

    const response = await fetch(`${API_BASE_URL}/api/chat/delete-conversation`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Failed to delete conversation: ${response.statusText}`);
    }
  },
};

export default chatService;
