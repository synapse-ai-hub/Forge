const API_BASE_URL = import.meta.env.VITE_URL_BASE || "http://localhost:8000";

/**
 * Fetch a URL and save its content as a downloaded file.
 *
 * @param url - URL that returns the file content.
 * @param filename - Name given to the downloaded file.
 * @throws Error - When the HTTP request fails.
 */
async function downloadFile(url: string, filename: string): Promise<void> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }
  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
}

export interface SessionMetrics {
  total_sessions: number;
  cantidad: { date: string; count: number }[];
}

/** One turn row of a per-message metric distribution. */
export interface MessageMetricRow {
  sid: string;
  turn: number | null;
}

/** The five per-message metrics: steps, tokens, time and latency. */
export interface MessageMetrics {
  steps: (MessageMetricRow & { steps: number | null })[];
  input_tokens: (MessageMetricRow & { input_tokens: number | null })[];
  output_tokens: (MessageMetricRow & { output_tokens: number | null })[];
  time: (MessageMetricRow & { total_time: number | null })[];
  latency: (MessageMetricRow & { latency: number | null })[];
}

export interface ToolMetrics {
  tool_usage: { name: string; count: number; avg_time: number }[];
  total_tool_calls: number;
  avg_time_per_tool_call: number;
  top_subagents: { name: string; count: number }[];
}

export interface ModelMetrics {
  models: { provider: string; model: string; count: number }[];
  tokens_input: { provider: string; model: string; value: number }[];
  tokens_output: { provider: string; model: string; value: number }[];
  tool_calls: { provider: string; model: string; value: number }[];
  latency_models: { provider: string; model: string; value: number }[];
  total_model_calls: number;
  total_models: number;
}

export interface ErrorMetrics {
  total_errors: number;
  errors_by_day: { date: string; count: number }[];
  errors_by_source: { source: string; count: number }[];
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

  /** Get the five per-message metrics with optional time range filter. */
  async getMessageMetrics(timeRange?: string): Promise<MessageMetrics> {
    const query = timeRange ? `?time_range=${timeRange}` : "";
    return fetchMetric<MessageMetrics>(
      `/api/metrics/messages${query}`,
      "Error fetching message metrics",
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
    const query = timeRange ? `?time_range=${timeRange}` : "";
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

  /** Render a metric query with synapse_tools.eda.outliers (base64 image). */
  async getOutliersFigure(body: {
    query_file: string;
    value_column: string;
    time_range?: string;
    percentile?: number;
    model?: string;
    provider?: string;
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

  /** Download the sessions table (CSV) for the given time range. */
  async downloadSessionsCsv(timeRange?: string): Promise<void> {
    const range = timeRange || "1m";
    const query = timeRange ? `?time_range=${timeRange}` : "";
    return downloadFile(`${API_BASE_URL}/api/metrics/sessions/export${query}`, `sesiones_${range}.csv`);
  },

  /** Download the messages table (CSV) for the given time range. */
  async downloadMessagesCsv(timeRange?: string): Promise<void> {
    const range = timeRange || "1m";
    const query = timeRange ? `?time_range=${timeRange}` : "";
    return downloadFile(`${API_BASE_URL}/api/metrics/messages/export${query}`, `mensajes_${range}.csv`);
  },

  /** Download the tool calls table (CSV) for the given time range. */
  async downloadToolsCsv(timeRange?: string): Promise<void> {
    const range = timeRange || "1m";
    const query = timeRange ? `?time_range=${timeRange}` : "";
    return downloadFile(`${API_BASE_URL}/api/metrics/tools/export${query}`, `herramientas_${range}.csv`);
  },

  /** Download the assistant model calls table (CSV) for the given time range. */
  async downloadModelsCsv(timeRange?: string): Promise<void> {
    const range = timeRange || "1m";
    const query = timeRange ? `?time_range=${timeRange}` : "";
    return downloadFile(`${API_BASE_URL}/api/metrics/models/export${query}`, `modelos_${range}.csv`);
  },
};

export default metricsService;
