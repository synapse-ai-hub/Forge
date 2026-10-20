import { API_BASE_URL } from "../config/api";
/** Service for the Telegram toggle (status + enable/disable). */


export interface TelegramStatus {
  enabled: boolean;
}

async function getStatus(): Promise<boolean> {
  const res = await fetch(`${API_BASE_URL}/api/telegram/status`);
  if (!res.ok) throw new Error("Error obteniendo estado de Telegram");
  const data = (await res.json()) as TelegramStatus;
  return data.enabled;
}

async function toggle(enabled: boolean): Promise<boolean> {
  const res = await fetch(`${API_BASE_URL}/api/telegram/toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  if (!res.ok) throw new Error("Error actualizando estado de Telegram");
  const data = (await res.json()) as TelegramStatus;
  return data.enabled;
}

async function getActiveSession(): Promise<string | null> {
  const res = await fetch(`${API_BASE_URL}/api/telegram/active-session`);
  if (!res.ok) throw new Error("Error obteniendo sesión activa");
  const data = (await res.json()) as { session_id: string | null };
  return data.session_id || null;
}

async function setActiveSession(sessionId: string): Promise<void> {
  await fetch(`${API_BASE_URL}/api/telegram/active-session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

const telegramService = { getStatus, toggle, getActiveSession, setActiveSession };

export default telegramService;