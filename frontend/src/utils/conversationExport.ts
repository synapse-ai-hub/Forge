/**
 * Utilities for exporting a conversation (messages) to a Markdown string.
 *
 * The export preserves the full structure visible in the UI: reasoning
 * blocks, text content, tool calls with their arguments and results, and
 * file attachments. Both the modern ``blocks`` format and the legacy
 * ``toolCalls`` / ``toolResults`` format are supported.
 */

import type { Message, ContentBlock, SubagentEvent, SubagentStep } from "../App";
import { API_BASE_URL } from "../config/api";

/**
 * Escape a string so it is safe to embed inside a fenced code block.
 * No-op: code fences are already escaped by the caller.
 */
function escapeCodeBlock(text: string): string {
  return text.replace(/```/g, "\\`\\`\\`");
}

/**
 * Render a single content block to Markdown.
 */
function renderBlock(block: ContentBlock, index: number): string {
  switch (block.type) {
    case "reasoning": {
      const content = block.content?.trim() || "";
      if (!content) return "";
      return `### Razonamiento ${index}\n\n<details>\n<summary>Ver razonamiento</summary>\n\n${content}\n\n</details>\n`;
    }
    case "text": {
      const content = block.content || "";
      if (!content) return "";
      return `${content}\n`;
    }
    case "tool": {
      const name = block.name || "unknown";
      const args = block.args || {};
      const result = block.result;
      const argsStr = Object.keys(args).length > 0
        ? JSON.stringify(args, null, 2)
        : "(sin parámetros)";
      let out = `### Llamada a tool: \`${name}\` ${index}\n\n`;
      out += `**Parámetros:**\n\n\`\`\`json\n${escapeCodeBlock(argsStr)}\n\`\`\`\n\n`;
      if (result !== undefined) {
        const resultStr = typeof result === "string"
          ? result
          : JSON.stringify(result, null, 2);
        out += `**Resultado:**\n\n\`\`\`\n${escapeCodeBlock(resultStr)}\n\`\`\`\n\n`;
      }
      return out;
    }
    default:
      return "";
  }
}

/**
 * Render sub-agent events (for the `task` tool) to Markdown.
 */
function renderSubagentEvents(events: Record<string, SubagentEvent> | undefined): string {
  if (!events) return "";
  let out = "";
  for (const [childId, event] of Object.entries(events)) {
    out += `\n#### Sub-agente: ${event.agent_name} (id: ${childId.slice(0, 8)})\n\n`;
    if (event.content) {
      out += `**Respuesta:** ${event.content}\n\n`;
    }
    if (event.tool_calls && event.tool_calls.length > 0) {
      out += `**Herramientas del sub-agente:**\n\n`;
      event.tool_calls.forEach((tc, i) => {
        out += `- \`${tc.name}\`: ${JSON.stringify(tc.args)}\n`;
      });
      out += "\n";
    }
    if (event.tool_results && event.tool_results.length > 0) {
      out += `**Resultados:**\n\n`;
      event.tool_results.forEach((tr) => {
        const resultStr = typeof tr.result === "string"
          ? tr.result
          : JSON.stringify(tr.result, null, 2);
        out += `- \`${tr.name}\`:\n\`\`\`\n${escapeCodeBlock(resultStr)}\n\`\`\`\n`;
      });
      out += "\n";
    }
    // Steps in exact order
    if (event.steps && event.steps.length > 0) {
      out += `**Pasos (orden exacto):**\n\n`;
      event.steps.forEach((step: SubagentStep, i) => {
        if (step.kind === "reasoning") {
          out += `${i + 1}. **Razonamiento:** ${step.content}\n`;
        } else if (step.kind === "text") {
          out += `${i + 1}. **Texto:** ${step.content}\n`;
        } else if (step.kind === "tool") {
          out += `${i + 1}. **Tool \`${step.name}\`:** ${JSON.stringify(step.args)}\n`;
          if (step.result !== undefined) {
            const resultStr = typeof step.result === "string"
              ? step.result
              : JSON.stringify(step.result, null, 2);
            out += `   - Resultado: \`\`\`\n${escapeCodeBlock(resultStr)}\n\`\`\`\n`;
          }
        }
      });
      out += "\n";
    }
  }
  return out;
}

/**
 * Render a single message to Markdown.
 */
function renderMessage(msg: Message, index: number): string {
  const role = msg.type === "user" ? "Usuario" : "Asistente";
  let out = `---\n\n## Mensaje ${index + 1}: ${role}\n\n`;

  // File attachments (user messages)
  if (msg.type === "user" && msg.files && msg.files.length > 0) {
    out += "**Archivos adjuntos:**\n\n";
    msg.files.forEach((f) => {
      const sizeStr = f.size
        ? ` (${(f.size / 1024).toFixed(0)} KB)`
        : "";
      out += `- ${f.name}${sizeStr}\n`;
    });
    out += "\n";
  }

  // Modern blocks format
  if (msg.blocks && msg.blocks.length > 0) {
    msg.blocks.forEach((block, i) => {
      out += renderBlock(block, i);
    });
  } else if (msg.content) {
    // Fallback: plain content
    out += msg.content + "\n";
  }

  // Legacy toolCalls / toolResults format
  if (msg.type === "assistant" && msg.toolCalls && msg.toolCalls.length > 0) {
    msg.toolCalls.forEach((tc, i) => {
      const result = msg.toolResults?.[i];
      out += `### Llamada a tool: \`${tc.tool}\` ${i}\n\n`;
      const argsStr = Object.keys(tc.parameters).length > 0
        ? JSON.stringify(tc.parameters, null, 2)
        : "(sin parámetros)";
      out += `**Parámetros:**\n\n\`\`\`json\n${escapeCodeBlock(argsStr)}\n\`\`\`\n\n`;
      if (result) {
        const resultStr = typeof result.result === "string"
          ? result.result
          : JSON.stringify(result.result, null, 2);
        out += `**Resultado:**\n\n\`\`\`\n${escapeCodeBlock(resultStr)}\n\`\`\`\n\n`;
      }
    });
  }

  // Sub-agent events
  if (msg.type === "assistant" && msg.subagentEvents) {
    out += renderSubagentEvents(msg.subagentEvents);
  }

  // Reasoning (legacy field)
  if (msg.type === "assistant" && msg.reasoning) {
    out += `### Razonamiento\n\n<details>\n<summary>Ver razonamiento</summary>\n\n${msg.reasoning}\n\n</details>\n`;
  }

  return out;
}

/**
 * Convert a list of messages to a Markdown string representing the full
 * conversation as it appears in the UI (including tool calls, reasoning, etc.).
 *
 * @param messages - The conversation messages.
 * @param title - Optional title for the document.
 * @returns A Markdown string.
 */
export function conversationToMarkdown(
  messages: Message[],
  title: string = "Conversación",
): string {
  const now = new Date().toISOString();
  let md = `# ${title}\n\n`;
  md += `> Exportado el: ${now}\n\n`;

  messages.forEach((msg, i) => {
    md += renderMessage(msg, i);
  });

  return md;
}

/**
 * Fetch the Markdown for a conversation from the backend export endpoint.
 * Both the web UI and the Telegram bot hit this same endpoint so the
 * generated document is identical regardless of the source.
 *
 * @param messages - The conversation messages.
 * @param title - Optional title for the document.
 * @returns The generated Markdown string.
 */
export async function fetchConversationMarkdown(
  messages: Message[],
  title: string = "Conversación",
): Promise<string> {
  const base = API_BASE_URL + "/api";
  const resp = await fetch(`${base}/conversation/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, title }),
  });
  if (!resp.ok) {
    throw new Error(`Error al exportar la conversación (${resp.status})`);
  }
  const data = await resp.json();
  if (data.status !== "success" || !data.data?.markdown) {
    throw new Error("Error al exportar la conversación");
  }
  return data.data.markdown;
}

/**
 * Trigger a file save dialog (Windows file picker) and write the given
 * content to the selected file. Uses the File System Access API when
 * available (Chromium-based browsers), falling back to a download link.
 *
 * @param content - The file content.
 * @param suggestedName - Suggested filename (without extension).
 * @param extension - File extension including the dot (e.g. ".md").
 */
export async function saveFileWithPicker(
  content: string,
  suggestedName: string = "conversacion",
  extension: string = ".md",
): Promise<void> {
  // Try the File System Access API (Chromium / Edge / Chrome)
  const anyWindow = window as any;
  if (anyWindow.showSaveFilePicker) {
    try {
      const opts: any = {
        suggestedName: suggestedName + extension,
        types: [
          {
            description: "Markdown",
            accept: { "text/markdown": [extension] },
          },
        ],
      };
      const handle = await anyWindow.showSaveFilePicker(opts);
      const writable = await handle.createWritable();
      await writable.write(content);
      await writable.close();
      return;
    } catch (e: any) {
      // User cancelled or API failed — fall through to download link
      if (e?.name === "AbortError") return;
    }
  }

  // Fallback: create a download link
  const blob = new Blob([content], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = suggestedName + extension;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
