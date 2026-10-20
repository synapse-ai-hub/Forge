import { API_BASE_URL } from "../config/api";

export interface ModelsResponse {
  status: string;
  provider: string;
  provider_label?: string;
  models: string[];
  model: string | null;
}

export interface ContextWindowResponse {
  status: string;
  max_turns: number;
  context_window_tokens: number | null;
  vram_gb: number | null;
  ollama_default_context: number | null;
}

export interface ProvidersResponse {
  status: string;
  providers: Array<{ provider: string; label: string }>;
}

export interface SkillInfo {
  name: string;
  description: string;
}

export interface ToolInfo {
  name: string;
  description: string;
}

export interface AgentInfo {
  name: string;
  description: string;
}

export interface McpServerStatus {
  label: string;
  status: "connected" | "failed" | "disabled" | "not_configured";
  transport?: "stdio" | "http" | "sse";
  error?: string;
}

export interface McpListing {
  servers: McpServerStatus[];
  /** Set when mcp.json is not a valid array (the list is empty because of the file). */
  error: string | null;
}

export interface ProviderKeyStatus {
  provider: string;
  configured: boolean;
}

export interface ProviderKeysResponse {
  status: string;
  keys: ProviderKeyStatus[];
}

export interface SetupCompletedResponse {
  status: string;
  completed: boolean;
}

/** Advanced parameters (null = "default": use the agent's frontmatter value). */
export interface AdvancedParams {
  temperature: number | null;
  top_p: number | null;
  reasoning: string | null;
  budget_tokens: number | null;
  response_format: string | null;
}

export interface ParametersResponse {
  status: string;
  temperature: number | null;
  top_p: number | null;
  reasoning: string | null;
  budget_tokens: number | null;
  response_format: string | null;
  model: string | null;
  provider: string;
  /** Whether the current model declaratively supports reasoning (null = unknown). */
  reasoning_supported: boolean | null;
  /** Whether the current model declaratively supports structured output (null = unknown). */
  response_format_supported: boolean | null;
}

export interface ModelCapabilitiesResponse {
  status: string;
  reasoning_supported: boolean | null;
  response_format_supported?: boolean | null;
  reasoning_options: Array<{ value: string; label: string }>;
  reasoning_param: string | null;
  reasoning_type: string | null;
  budget_min: number | null;
  budget_max: number | null;
  context_window: number | null;
  input_limit: number | null;
  output_limit: number | null;
  input_modalities: string[] | null;
  output_modalities: string[] | null;
  cost_input: number | null;
  cost_output: number | null;
}

export interface DecisionProvider {
  provider: string;
  label: string;
  key_url?: string;
  models: string[];
}

export interface DecisionModelsResponse {
  status: string;
  providers: DecisionProvider[];
  provider: string | null;
  model: string | null;
  enabled: boolean;
}

/** Message of a failed response: the backend's ``message``, else the HTTP status (the body may not be JSON). */
async function errorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (data && data.message) return data.message;
  } catch {
    // body is not JSON (e.g. a plain 500)
  }
  return `HTTP ${response.status}`;
}

export const configService = {
  /** List available models and the currently selected one. */
  async getModels(provider?: string): Promise<ModelsResponse> {
    const url = provider
      ? `${API_BASE_URL}/api/config/models?provider=${encodeURIComponent(provider)}`
      : `${API_BASE_URL}/api/config/models`;
    const response = await fetch(url, {
      method: "GET",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  },

  /** Get model capabilities (reasoning options, etc.) for a specific model/provider. */
  async getModelCapabilities(model: string, provider: string): Promise<ModelCapabilitiesResponse> {
    const response = await fetch(
      `${API_BASE_URL}/api/config/models/capabilities?model=${encodeURIComponent(model)}&provider=${encodeURIComponent(provider)}`,
      { method: "GET" }
    );
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  },

  /** Select a model for the running agent, together with the advanced parameters. */
  async selectModel(
    model: string,
    provider: string,
    params?: AdvancedParams
  ): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/api/config/models/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model,
        provider,
        temperature: params ? params.temperature : null,
        top_p: params ? params.top_p : null,
        reasoning: params ? params.reasoning : null,
        budget_tokens: params ? params.budget_tokens : null,
        response_format: params ? params.response_format : null,
      }),
    });
    const result = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(
        (result && result.message) || `HTTP ${response.status}: ${response.statusText}`
      );
    }
    if (result && result.status === "error") {
      throw new Error(result.message || "Error al seleccionar el modelo");
    }
  },

  /** Get the persisted advanced parameters (null = default). */
  async getParameters(): Promise<ParametersResponse> {
    const response = await fetch(`${API_BASE_URL}/api/config/parameters`, {
      method: "GET",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  },

  /** Get the current context-window turn limit. */
  async getContextWindow(): Promise<ContextWindowResponse> {
    const response = await fetch(`${API_BASE_URL}/api/config/context-window`, {
      method: "GET",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  },

  /** Set the context-window turn limit (-1 = all turns). */
  async setContextWindow(maxTurns: number): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/api/config/context-window`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_turns: maxTurns }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const result = await response.json();
    if (result && result.status === "error") {
      throw new Error(result.message || "Error al guardar el contexto");
    }
  },

  /** Get the current verbose-mode flag. */
  async getVerbose(): Promise<boolean> {
    const response = await fetch(`${API_BASE_URL}/api/config/verbose-mode`, {
      method: "GET",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const result = await response.json();
    return result.verbose_mode === true;
  },

  /** Set the verbose-mode flag. */
  async setVerbose(verboseMode: boolean): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/api/config/verbose-mode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ verbose_mode: verboseMode }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const result = await response.json();
    if (result && result.status === "error") {
      throw new Error(result.message || "Error al guardar verbose mode");
    }
  },

  /** List providers that are currently available (curated cloud providers, Ollama, …). */
  async getProviders(): Promise<ProvidersResponse> {
    const response = await fetch(`${API_BASE_URL}/api/config/providers`, {
      method: "GET",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  },

  /** List which providers have an API key configured (no key material). */
  async getProviderKeys(): Promise<ProviderKeysResponse> {
    const response = await fetch(`${API_BASE_URL}/api/config/providers/keys`, {
      method: "GET",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  },

  /** Store (encrypted) the API key for a provider. */
  async saveProviderKey(provider: string, apiKey: string): Promise<void> {
    const response = await fetch(
      `${API_BASE_URL}/api/config/providers/${encodeURIComponent(provider)}/key`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: apiKey }),
      }
    );
    const result = await response.json();
    if (!response.ok || result.status === "error") {
      throw new Error(result.message || `HTTP ${response.status}`);
    }
  },

  /** Remove the stored API key for a provider. */
  async deleteProviderKey(provider: string): Promise<void> {
    const response = await fetch(
      `${API_BASE_URL}/api/config/providers/${encodeURIComponent(provider)}/key`,
      { method: "DELETE" }
    );
    const result = await response.json();
    if (!response.ok || result.status === "error") {
      throw new Error(result.message || `HTTP ${response.status}`);
    }
  },



  /** Whether the initial provider-setup screen was already completed/skipped. */
  async getSetupCompleted(): Promise<SetupCompletedResponse> {
    const response = await fetch(`${API_BASE_URL}/api/config/setup-completed`, {
      method: "GET",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  },

  /** Mark the initial provider-setup screen as completed (or skipped). */
  async markSetupCompleted(): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/api/config/setup-completed`, {
      method: "POST",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
  },

  /** List available skills (name + description). */
  async getSkills(): Promise<SkillInfo[]> {
    const response = await fetch(`${API_BASE_URL}/api/config/skills`, {
      method: "GET",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const data = await response.json();
    return data.skills || [];
  },

  /** List all available tools (native + external, no MCP). */
  async getTools(): Promise<ToolInfo[]> {
    const response = await fetch(`${API_BASE_URL}/api/config/tools`, {
      method: "GET",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const data = await response.json();
    return data.tools || [];
  },

  /** Force rebuild of the tools registry and return updated list. */
  async refresh(): Promise<ToolInfo[]> {
    const response = await fetch(`${API_BASE_URL}/api/config/tools/refresh`, {
      method: "POST",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const data = await response.json();
    return data.tools || [];
  },

  /** List available sub-agents. */
  async getAgents(): Promise<AgentInfo[]> {
    const response = await fetch(`${API_BASE_URL}/api/config/agents`, {
      method: "GET",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const data = await response.json();
    return data.agents || [];
  },

  /** List MCP servers with connection status. */
  async getMcp(): Promise<McpListing> {
    const response = await fetch(`${API_BASE_URL}/api/config/mcp`, {
      method: "GET",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const data = await response.json();
    return { servers: data.servers || [], error: data.error || null };
  },

  /** Switch an MCP server on or off (writes mcp.json and rebuilds the tools registry). */
  async setMcpEnabled(label: string, enabled: boolean): Promise<void> {
    const response = await fetch(
      `${API_BASE_URL}/api/agent/mcp/${encodeURIComponent(label)}/enabled`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      }
    );
    if (!response.ok) {
      throw new Error(await errorMessage(response));
    }
  },

  // ── Delete endpoints ─────────────────────────────────────────────

  /** Delete a skill by name. */
  async deleteSkill(name: string): Promise<void> {
    const response = await fetch(
      `${API_BASE_URL}/api/agent/skills/${encodeURIComponent(name)}`,
      { method: "DELETE" }
    );
    if (!response.ok) {
      throw new Error(await errorMessage(response));
    }
  },

  /** Delete an external tool by name. */
  async deleteTool(name: string): Promise<void> {
    const response = await fetch(
      `${API_BASE_URL}/api/agent/tools/${encodeURIComponent(name)}`,
      { method: "DELETE" }
    );
    if (!response.ok) {
      throw new Error(await errorMessage(response));
    }
  },

  /** Delete an agent by name. */
  async deleteAgent(name: string): Promise<void> {
    const response = await fetch(
      `${API_BASE_URL}/api/agent/agents/${encodeURIComponent(name)}`,
      { method: "DELETE" }
    );
    if (!response.ok) {
      throw new Error(await errorMessage(response));
    }
  },

  /** Delete an MCP server by label. */
  async deleteMcp(label: string): Promise<void> {
    const response = await fetch(
      `${API_BASE_URL}/api/agent/mcp/${encodeURIComponent(label)}`,
      { method: "DELETE" }
    );
    if (!response.ok) {
      throw new Error(await errorMessage(response));
    }
  },

  /** List knowledge collections. */
  async listKnowledge(): Promise<string[]> {
    const response = await fetch(`${API_BASE_URL}/api/agent/knowledge`, {
      method: "GET",
    });
    if (!response.ok) {
      return [];
    }
    const data = await response.json();
    return data.collections || [];
  },

  /** Delete a knowledge collection by name. */
  async deleteKnowledge(collection: string): Promise<void> {
    const response = await fetch(
      `${API_BASE_URL}/api/agent/knowledge/${encodeURIComponent(collection)}`,
      { method: "DELETE" }
    );
    if (!response.ok) {
      throw new Error(await errorMessage(response));
    }
  },

  /** Validate workflow YAML without saving (dry-run). */
  async validateWorkflow(yaml: string): Promise<{ ok: boolean; message: string }> {
    const response = await fetch(`${API_BASE_URL}/api/config/workflows/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ yaml }),
    });
    const data = await response.json();
    return { ok: data.status === "success", message: data.message || "" };
  },

  /** Save workflow YAML (validated server-side). */
  async saveWorkflow(name: string, yaml: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/api/config/workflows/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, yaml }),
    });
    const data = await response.json();
    if (!response.ok || data.status === "error") {
      throw new Error(data.message || `HTTP ${response.status}`);
    }
  },

  /** Generate workflow YAML with the agent from a description. */
  async generateWorkflow(description: string): Promise<{ yaml: string; name: string }> {
    const response = await fetch(`${API_BASE_URL}/api/config/workflows/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description }),
    });
    const data = await response.json();
    if (!response.ok || data.status === "error") {
      throw new Error(data.message || `HTTP ${response.status}`);
    }
    return { yaml: data.data?.yaml || "", name: data.data?.name || "" };
  },

  /** List decision providers (from the decision_catalog table) + current selection. */
  async getDecisionModels(): Promise<DecisionModelsResponse> {
    const response = await fetch(`${API_BASE_URL}/api/config/models/decision`, {
      method: "GET",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  },

  /** Select a decision provider + model (must exist in the decision catalog). */
  async selectDecisionModel(model: string, provider: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/api/config/models/decision/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, provider }),
    });
    const result = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(
        (result && result.message) || `HTTP ${response.status}: ${response.statusText}`
      );
    }
    if (result && result.status === "error") {
      throw new Error(result.message || "Error al seleccionar el modelo de decisión");
    }
  },

  /** Get catalog info for a decision model (same layout as chat model info). */
  async getDecisionCapabilities(model: string, provider: string): Promise<{
    status: string;
    found?: boolean;
    context_window: number | null;
    input_limit: number | null;
    output_limit: number | null;
    input_modalities: string[] | null;
    output_modalities: string[] | null;
    cost_input: number | null;
    cost_output: number | null;
  }> {
    const response = await fetch(
      `${API_BASE_URL}/api/config/models/decision/capabilities?model=${encodeURIComponent(model)}&provider=${encodeURIComponent(provider)}`,
      { method: "GET" }
    );
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  },

  /** Enable or disable the decision section. */
  async setDecisionEnabled(enabled: boolean): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/api/config/models/decision/enabled`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    const result = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(
        (result && result.message) || `HTTP ${response.status}: ${response.statusText}`
      );
    }
    if (result && result.status === "error") {
      throw new Error(result.message || "Error al guardar el estado de decisión");
    }
  },
};

export default configService;
