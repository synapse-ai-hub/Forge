/** What the creators and the scheduled tasks receive from the permission cards. */

/** What the user picked in the permission cards. Everything picked is mandatory for the creator. */
export interface ResourceSelection {
  agentes: string[];
  tools: string[];
  /** Arguments the user filled for each picked tool (tool name → argument → value). */
  toolArgs: Record<string, Record<string, unknown>>;
  skills: string[];
  rag: string[];
}

/** Nothing picked: the creator decides. */
export const EMPTY_SELECTION: ResourceSelection = {
  agentes: [],
  tools: [],
  toolArgs: {},
  skills: [],
  rag: [],
};

/** Kind of resource a card list can offer. */
export type ResourceKind = "agentes" | "tools" | "skills" | "rag";

/**
 * Rebuild the selection from the setup stored with a creator conversation.
 *
 * @param setup - The request the conversation started with.
 * @returns The selection it had (empty where it had none).
 */
export function selectionFromSetup(setup: Record<string, unknown>): ResourceSelection {
  const list = (value: unknown): string[] => (Array.isArray(value) ? (value as string[]) : []);
  const args = setup.tool_args;
  return {
    agentes: list(setup.agentes),
    tools: list(setup.tools),
    toolArgs: args && typeof args === "object" ? (args as ResourceSelection["toolArgs"]) : {},
    skills: list(setup.skills),
    rag: list(setup.rag),
  };
}

/**
 * Build the fields of a creator request from a selection.
 *
 * @param selection - What the user picked.
 * @returns ``agentes``, ``tools``, ``tool_args``, ``skills`` and ``rag`` of the request.
 */
export function selectionToRequest(selection: ResourceSelection): {
  agentes: string[];
  tools: string[];
  tool_args: ResourceSelection["toolArgs"];
  skills: string[];
  rag: string[];
} {
  const toolArgs: ResourceSelection["toolArgs"] = {};
  for (const name of selection.tools) {
    if (selection.toolArgs[name] && Object.keys(selection.toolArgs[name]).length > 0) {
      toolArgs[name] = selection.toolArgs[name];
    }
  }
  return {
    agentes: selection.agentes,
    tools: selection.tools,
    tool_args: toolArgs,
    skills: selection.skills,
    rag: selection.rag,
  };
}
