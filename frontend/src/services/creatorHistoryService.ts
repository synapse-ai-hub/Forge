import { API_BASE_URL } from "../config/api";
/** Service for the history of the creators (agent, skill, tool and workflow). */

export type CreatorKind = "agent" | "skill" | "tool" | "workflow";

/** One conversation of a creator, as listed in its history sidebar. */
export interface CreatorConversationItem {
  creator_id: string;
  kind: CreatorKind;
  created_at: string;
  updated_at: string;
  /** First message the user wrote (the description). */
  first_message: string | null;
  /** Name of the item that was created or modified, when known. */
  item_name: string | null;
  status: "success" | "error" | "aborted" | null;
}

/** A message rebuilt from the stored rows, ready for the creator page. */
export interface RestoredMessage {
  type: "user" | "assistant";
  content: string;
  blocks?: Array<
    | { type: "text" | "reasoning"; content: string }
    | { type: "tool"; name: string; args: Record<string, unknown>; result?: unknown }
  >;
  toolCalls?: Array<{ tool: string; parameters: Record<string, unknown> }>;
  toolResults?: Array<{ tool: string; result: unknown }>;
}

/** A conversation with everything the page needs to continue it. */
export interface CreatorConversation {
  creator_id: string;
  kind: CreatorKind;
  /** The form of the first request: descripcion, name, parametros, datos, agentes, ... */
  setup: Record<string, unknown>;
  messages: RestoredMessage[];
  /** The `[{role, content}]` rebuilt from the stored turns (display only). */
  historial: Array<{ role: "user" | "assistant"; content: string }>;
  /** How the last request ended, or null. */
  result: {
    status: string | null;
    message: string;
    action: string | null;
    item_name: string | null;
  } | null;
}

/**
 * Generate the id of a new creator conversation.
 *
 * @returns A random id without dashes.
 */
export function newCreatorId(): string {
  const random = globalThis.crypto?.randomUUID?.();
  return (random || `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`).replace(/-/g, "");
}

/**
 * List the conversations of a creator, newest first.
 *
 * @param kind - Creator whose conversations are listed.
 * @returns The conversations, or an empty list when there are none.
 * @throws Error when the request fails.
 */
async function list(kind: CreatorKind): Promise<CreatorConversationItem[]> {
  const res = await fetch(`${API_BASE_URL}/api/create/history?kind=${encodeURIComponent(kind)}`);
  if (!res.ok) throw new Error("Error obteniendo el historial");
  const data = await res.json();
  return (data.conversations || []) as CreatorConversationItem[];
}

/**
 * Load a conversation with everything the page needs to continue it.
 *
 * @param creatorId - Id of the conversation.
 * @returns The stored conversation.
 * @throws Error when it does not exist or the request fails.
 */
async function get(creatorId: string): Promise<CreatorConversation> {
  const res = await fetch(`${API_BASE_URL}/api/create/history/${encodeURIComponent(creatorId)}`);
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.message || "No se pudo abrir la conversación");
  return data.conversation as CreatorConversation;
}

/**
 * Delete a conversation of a creator.
 *
 * @param creatorId - Id of the conversation.
 * @throws Error when it cannot be deleted.
 */
async function remove(creatorId: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/create/history/${encodeURIComponent(creatorId)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.message || "No se pudo eliminar la conversación");
  }
}

const creatorHistoryService = { list, get, remove };

export default creatorHistoryService;
