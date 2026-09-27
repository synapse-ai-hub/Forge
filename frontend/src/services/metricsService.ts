const API_BASE_URL = import.meta.env.VITE_URL_BASE || "http://localhost:8000";

export interface SessionMetrics {
  total_sessions: number;
  total_messages: number;
  avg_messages_per_session: number;
  total_tokens: number;
  avg_tokens_per_session: number;
  avg_input_tokens_per_session: number;
  avg_output_tokens_per_session: number;
  avg_tokens_per_message: number;
  avg_tokens_per_tool: number;
  total_cost: number;
  avg_cost_per_session: number;
  avg_cost_input_per_session: number;
  avg_cost_output_per_session: number;
  avg_cost_per_message: number;
  avg_cost_per_tool: number;
  avg_cost_per_provider_model: number;
  total_time: number;
  avg_time_per_turn: number;
  avg_time_per_session: number;
  avg_agent_latency: number;
  sessions_by_day: { date: string; count: number }[];
  sessions_over_time: { date: string; count: number }[];
}

export interface ToolMetrics {
  tool_usage: { name: string; count: number; avg_time: number }[];
  total_tool_calls: number;
  avg_time_per_tool_call: number;
  top_subagents: { name: string; count: number }[];
}

export interface ModelMetrics {
  models: { model: string; count: number }[];
  total_model_calls: number;
}

export interface ErrorMetrics {
  total_errors: number;
  errors_by_day: { date: string; count: number }[];
  errors_by_source: { source: string; count: number }[];
}

export interface SessionDetail {
  cantidad: { date: string; count: number }[];
  mensajes_per_session: number[];
  tokens_entrada: number[];
  tokens_salida: number[];
  latencia_per_session: number[];
}

export interface MetricsOverview {
  total_sessions: number;
  total_messages: number;
  avg_messages_per_session: number;
  total_errors: number;
  failed_turns_count: number;
  total_turns_count: number;
  failed_sessions_count: number;
  failure_rate_general: number;
  failure_rate_turns: number;
  failure_rate_sessions: number;
  top_tools: { name: string; count: number }[];
  sessions_by_day: { date: string; count: number }[];
  sessions_over_time: { date: string; count: number }[];
  total_tokens: number;
  avg_tokens_per_session: number;
  avg_input_tokens_per_session: number;
  avg_output_tokens_per_session: number;
  avg_tokens_per_message: number;
  total_cost: number;
  avg_cost_per_session: number;
  avg_cost_input_per_session: number;
  avg_cost_output_per_session: number;
  avg_cost_per_message: number;
  avg_cost_per_provider_model: number;
  total_time: number;
  avg_time_per_turn: number;
  avg_time_per_session: number;
  avg_agent_latency: number;
}

/**
 * Fetch a metrics endpoint and unwrap the unified contract response.
 *
 * Args:
 *   path: API path relative to the base URL (e.g. "/api/metrics/sessions").
 *   errorMessage: Message used when the backend reports an error status.
 *
 * Returns:
 *   The ``data`` payload of the contract response.
 *
 * Throws:
 *   Error: When the HTTP request fails or the backend returns
 *     ``status: "error"``.
 */
async function fetchMetric<T>(path: string, errorMessage: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "GET",
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }
  const result = await response.json();
  if (result.status === "error") {
    throw new Error(result.message || errorMessage);
  }
  return result.data as T;
}

const metricsService = {
  /** Get session-level metrics with optional time range filter. */
  async getSessionMetrics(timeRange?: string): Promise<SessionMetrics> {
    const query = timeRange ? `?time_range=${timeRange}` : "";
    return fetchMetric<SessionMetrics>(
      `/api/metrics/sessions${query}`,
      "Error fetching session metrics",
    );
  },

  /** Get tool usage metrics with optional time range filter. */
  async getToolMetrics(timeRange?: string): Promise<ToolMetrics> {
    const query = timeRange && timeRange !== "all" ? `?time_range=${timeRange}` : "";
    return fetchMetric<ToolMetrics>(
      `/api/metrics/tools${query}`,
      "Error fetching tool metrics",
    );
  },

  /** Get LLM usage metrics grouped by model with optional time range filter. */
  async getModelMetrics(timeRange?: string): Promise<ModelMetrics> {
    const query = timeRange && timeRange !== "all" ? `?time_range=${timeRange}` : "";
    return fetchMetric<ModelMetrics>(
      `/api/metrics/models${query}`,
      "Error fetching model metrics",
    );
  },

  /** Get error metrics with optional time range filter. */
  async getErrorMetrics(timeRange?: string): Promise<ErrorMetrics> {
    const query = timeRange && timeRange !== "all" ? `?time_range=${timeRange}` : "";
    return fetchMetric<ErrorMetrics>(
      `/api/metrics/errors${query}`,
      "Error fetching error metrics",
    );
  },

  /** Get a combined overview of all metrics with optional time range filter. */
  async getOverview(timeRange?: string): Promise<MetricsOverview> {
    const query = timeRange ? `?time_range=${timeRange}` : "";
    return fetchMetric<MetricsOverview>(
      `/api/metrics/overview${query}`,
      "Error fetching metrics overview",
    );
  },

  /** Get per-session distributions for the Sesiones card (from .sql scripts). */
  async getSessionDetail(timeRange?: string): Promise<SessionDetail> {
    const query = timeRange ? `?time_range=${timeRange}` : "";
    return fetchMetric<SessionDetail>(
      `/api/metrics/sessions/detail${query}`,
      "Error fetching session detail",
    );
  },

  /** Render a metric query with synapse_tools.eda.outliers (base64 image). */
  async getOutliersFigure(body: {
    query_file: string;
    value_column: string;
    time_range?: string;
  }): Promise<{ image: string; stats: Record<string, number> }> {
    const response = await fetch(`${API_BASE_URL}/api/metrics/eda/outliers-image`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const result = await response.json();
    if (result.status === "error") {
      throw new Error(result.message || "Error generando figura");
    }
    return result.data as { image: string; stats: Record<string, number> };
  },
};

export default metricsService;
