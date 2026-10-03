import { useState, useEffect, useCallback } from "react";
import { TrendingUp, RefreshCw, AlertCircle, DollarSign } from "lucide-react";

const API_BASE_URL = import.meta.env.VITE_URL_BASE || "http://localhost:8000";

export interface UsageData {
  by_provider: {
    provider: string;
    requests: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    cost: number;
  }[];
  totals: {
    requests: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    cost: number;
  };
}

export interface BillingConfig {
  limits: {
    provider: string;
    model: string | null;
    limit_amount: number;
    created_at: string;
    updated_at: string;
  }[];
  count: number;
}

export function useUsageData() {
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [billing, setBilling] = useState<BillingConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchUsage = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [usageRes, billingRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/usage-metrics`),
        fetch(`${API_BASE_URL}/api/billing-config`),
      ]);
      if (!usageRes.ok) throw new Error("Error fetching usage metrics");
      if (!billingRes.ok) throw new Error("Error fetching billing config");
      const usageJson = await usageRes.json();
      const billingJson = await billingRes.json();
      if (usageJson.status === "error") throw new Error(usageJson.message);
      if (billingJson.status === "error") throw new Error(billingJson.message);
      setUsage(usageJson.data as UsageData);
      setBilling(billingJson.data as BillingConfig);
    } catch (err: any) {
      setError(err.message || "Error inesperado");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsage();
  }, [fetchUsage]);

  return { usage, billing, loading, error, refresh: fetchUsage };
}

export function UsageTab() {
  const { usage, billing, loading, error, refresh } = useUsageData();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">
        <button
          onClick={refresh}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-app-text-secondary hover:text-app-primary hover:bg-app-bg-tertiary transition-colors disabled:opacity-50"
          title="Actualizar"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Actualizar
        </button>
      </div>

      {loading && !usage && (
        <div className="flex items-center justify-center gap-2 py-8 text-sm text-app-text-secondary">
          <RefreshCw size={16} className="animate-spin" />
          Cargando uso...
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-app-error">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {usage && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <div className="rounded-lg border border-app-border bg-white p-4">
              <div className="mb-1 flex min-h-8 items-start text-xs text-app-text-secondary">Solicitudes</div>
              <div className="text-xl font-bold text-app-text">{usage.totals.requests}</div>
            </div>
            <div className="rounded-lg border border-app-border bg-white p-4">
              <div className="mb-1 flex min-h-8 items-start text-xs text-app-text-secondary">Tokens totales</div>
              <div className="text-xl font-bold text-app-text">{usage.totals.total_tokens}</div>
            </div>
            <div className="rounded-lg border border-app-border bg-white p-4">
              <div className="mb-1 flex min-h-8 items-start text-xs text-app-text-secondary">Gasto (USD)</div>
              <div className="text-xl font-bold text-app-text">{(usage.totals.cost ?? 0).toFixed(2)}</div>
            </div>
            <div className="rounded-lg border border-app-border bg-white p-4">
              <div className="mb-1 flex min-h-8 items-start text-xs text-app-text-secondary">Prompt tokens</div>
              <div className="text-xl font-bold text-app-text">{usage.totals.prompt_tokens}</div>
            </div>
            <div className="rounded-lg border border-app-border bg-white p-4">
              <div className="mb-1 flex min-h-8 items-start text-xs text-app-text-secondary">Completion tokens</div>
              <div className="text-xl font-bold text-app-text">{usage.totals.completion_tokens}</div>
            </div>
          </div>

          <div className="rounded-lg border border-app-border bg-white p-4">
            <h4 className="mb-3 text-sm font-medium text-app-text">Por proveedor</h4>
            <div className="divide-y divide-app-border">
              {usage.by_provider.map((p) => (
                <div key={p.provider} className="flex items-center justify-between py-2.5 text-sm">
                  <div className="flex items-center gap-2">
                    <TrendingUp size={14} className="text-app-primary" />
                    <span className="font-medium text-app-text">{p.provider}</span>
                  </div>
                  <div className="flex gap-4 text-xs text-app-text-secondary">
                    <span>Req: {p.requests}</span>
                    <span>Tokens: {p.total_tokens}</span>
                    <span>USD: {(p.cost ?? 0).toFixed(2)}</span>
                  </div>
                </div>
              ))}
              {usage.by_provider.length === 0 && (
                <div className="py-3 text-xs text-app-text-secondary">Sin datos de uso</div>
              )}
            </div>
          </div>
        </>
      )}

      {billing && (
        <div className="rounded-lg border border-app-border bg-white p-4">
          <h4 className="mb-3 text-sm font-medium text-app-text">Límites configurados</h4>
          <div className="divide-y divide-app-border">
            {billing.limits.map((l) => (
              <div key={`${l.provider}-${l.model ?? "provider"}`} className="flex items-center justify-between py-2.5 text-sm">
                <div className="flex items-center gap-2">
                  <DollarSign size={14} className="text-app-primary" />
                  <span className="font-medium text-app-text">
                    {l.provider}
                    {l.model ? ` / ${l.model}` : ""}
                  </span>
                </div>
                <span className="text-xs font-semibold text-app-text">${(l.limit_amount ?? 0).toFixed(2)}</span>
              </div>
            ))}
            {billing.limits.length === 0 && (
              <div className="py-3 text-xs text-app-text-secondary">Sin límites configurados</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default UsageTab;
