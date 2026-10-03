import { useState, useEffect, useCallback } from "react";
import { DollarSign, RefreshCw, AlertCircle, ChevronDown } from "lucide-react";

const API_BASE_URL = import.meta.env.VITE_URL_BASE || "http://localhost:8000";

interface SpendRecord {
  provider: string;
  model: string;
  requests: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_input: number;
  cost_output: number;
  cost_total: number;
  cost_input_rate: number | null;
  cost_output_rate: number | null;
  updated_at: string;
}

/** Format a catalog rate (USD per million tokens) for display. */
function formatRate(rate: number | null): string {
  if (rate == null) return "s/tarifa";
  return `$${rate.toFixed(3)}/1M`;
}

export function BillingTab() {
  const [providerFilter, setProviderFilter] = useState<string>("");
  const [modelFilter, setModelFilter] = useState<string>("");
  const [spend, setSpend] = useState<SpendRecord[]>([]);
  const [keyProviders, setKeyProviders] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [configProvider, setConfigProvider] = useState<string>("");
  const [configModel, setConfigModel] = useState<string>("");
  const [limitAmount, setLimitAmount] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const providers = Array.from(
    new Set([...spend.map((s) => s.provider), ...keyProviders]),
  ).sort();
  const models = Array.from(
    new Set(spend.filter((s) => s.provider === providerFilter).map((s) => s.model)),
  ).sort();

  const fetchSpend = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const url = new URL(`${API_BASE_URL}/api/spend`);
      if (providerFilter) url.searchParams.set("provider", providerFilter);
      const res = await fetch(url.toString());
      if (!res.ok) throw new Error("Error fetching spend");
      const json = await res.json();
      if (json.status === "error") throw new Error(json.message);
      const records: SpendRecord[] = json.data?.spend || [];
      setSpend(records);
      const keysRes = await fetch(`${API_BASE_URL}/api/config/providers/keys`);
      if (keysRes.ok) {
        const keysJson = await keysRes.json();
        const keys: Array<{ provider: string; configured: boolean }> = keysJson.keys || [];
        setKeyProviders(
          keys.filter((k) => k.configured).map((k) => k.provider),
        );
      }
    } catch (err: any) {
      setError(err.message || "Error inesperado");
    } finally {
      setLoading(false);
    }
  }, [providerFilter]);

  useEffect(() => {
    fetchSpend();
  }, [fetchSpend]);

  const handleApply = async () => {
    if (!configProvider || limitAmount === "") return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const url = new URL(`${API_BASE_URL}/api/billing-config`);
      url.searchParams.set("provider", configProvider);
      if (configModel) url.searchParams.set("model", configModel);
      url.searchParams.set("limit_amount", limitAmount);
      const res = await fetch(url.toString(), { method: "POST" });
      const json = await res.json();
      if (!res.ok || json.status === "error") throw new Error(json.message || "Error al guardar");
      setSaveMsg(`Límite configurado: ${configProvider}${configModel ? ` / ${configModel}` : ""} = $${limitAmount}`);
      setLimitAmount("");
    } catch (err: any) {
      setSaveMsg(err.message || "Error al guardar");
    } finally {
      setSaving(false);
    }
  };

  const filteredSpend = spend.filter((s) => {
    const matchProvider = providerFilter ? s.provider === providerFilter : true;
    const matchModel = modelFilter ? s.model === modelFilter : true;
    return matchProvider && matchModel;
  });

  const totals = filteredSpend.reduce(
    (acc, s) => ({
      requests: acc.requests + (s.requests || 0),
      prompt_tokens: acc.prompt_tokens + (s.prompt_tokens || 0),
      completion_tokens: acc.completion_tokens + (s.completion_tokens || 0),
      cost_input: acc.cost_input + (s.cost_input || 0),
      cost_output: acc.cost_output + (s.cost_output || 0),
      cost_total: acc.cost_total + (s.cost_total || 0),
    }),
    { requests: 0, prompt_tokens: 0, completion_tokens: 0, cost_input: 0, cost_output: 0, cost_total: 0 },
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">
        <button
          onClick={fetchSpend}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-app-text-secondary hover:text-app-primary hover:bg-app-bg-tertiary transition-colors disabled:opacity-50"
          title="Actualizar"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Actualizar
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-app-error">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* View spend dropdowns */}
      <div className="rounded-lg border border-app-border bg-white p-4">
        <h4 className="mb-3 text-sm font-medium text-app-text">Ver gasto</h4>
        <div className="flex gap-3 mb-4">
          <div className="relative">
            <select
              value={providerFilter}
              onChange={(e) => {
                setProviderFilter(e.target.value);
                setModelFilter("");
              }}
              className="appearance-none rounded-md border border-app-border bg-white px-3 py-2 pr-8 text-sm text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary/20"
            >
              <option value="">Todos los proveedores</option>
              {providers.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <ChevronDown size={14} className="pointer-events-none absolute right-2.5 top-2.5 text-app-text-secondary" />
          </div>
          <div className="relative">
            <select
              value={modelFilter}
              onChange={(e) => setModelFilter(e.target.value)}
              disabled={!providerFilter}
              className="appearance-none rounded-md border border-app-border bg-white px-3 py-2 pr-8 text-sm text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary/20 disabled:opacity-50"
            >
              <option value="">Todos los modelos</option>
              {models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
            <ChevronDown size={14} className="pointer-events-none absolute right-2.5 top-2.5 text-app-text-secondary" />
          </div>
        </div>
        <div className="divide-y divide-app-border">
          {filteredSpend.map((s) => (
            <div key={`${s.provider}-${s.model}`} className="py-2.5 text-sm">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <DollarSign size={14} className="text-app-primary" />
                  <span className="font-medium text-app-text">
                    {s.provider} / {s.model}
                  </span>
                </div>
                <span className="text-xs text-app-text-secondary">Req: {s.requests || 0}</span>
              </div>
              <table className="mt-2 w-full text-xs">
                <thead>
                  <tr className="text-left text-app-text-secondary">
                    <th className="py-1 pr-2 font-normal">Concepto</th>
                    <th className="py-1 pr-2 text-right font-normal">Tokens</th>
                    <th className="py-1 pr-2 text-right font-normal">Tarifa /1M</th>
                    <th className="py-1 text-right font-normal">Costo USD</th>
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  <tr className="border-t border-app-border text-app-text-secondary">
                    <td className="py-1 pr-2">Entrada</td>
                    <td className="py-1 pr-2 text-right">{(s.prompt_tokens || 0).toLocaleString()}</td>
                    <td className="py-1 pr-2 text-right">{formatRate(s.cost_input_rate)}</td>
                    <td className="py-1 text-right font-medium text-app-text">
                      ${(s.cost_input || 0).toFixed(2)}
                    </td>
                  </tr>
                  <tr className="border-t border-app-border text-app-text-secondary">
                    <td className="py-1 pr-2">Salida</td>
                    <td className="py-1 pr-2 text-right">{(s.completion_tokens || 0).toLocaleString()}</td>
                    <td className="py-1 pr-2 text-right">{formatRate(s.cost_output_rate)}</td>
                    <td className="py-1 text-right font-medium text-app-text">
                      ${(s.cost_output || 0).toFixed(2)}
                    </td>
                  </tr>
                  <tr className="border-t border-app-border font-medium text-app-text">
                    <td className="py-1 pr-2">Total ({s.requests || 0} req)</td>
                    <td className="py-1 pr-2 text-right">{(s.total_tokens || 0).toLocaleString()}</td>
                    <td className="py-1 pr-2 text-right">—</td>
                    <td className="py-1 text-right">${(s.cost_total || 0).toFixed(2)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          ))}
          {filteredSpend.length === 0 && (
            <div className="py-3 text-xs text-app-text-secondary">Sin registros de gasto (solo se muestran valores &gt; 0)</div>
          )}
          {filteredSpend.length > 0 && (
            <div className="flex items-center justify-between py-2.5 text-sm font-medium text-app-text">
              <span>Total{providerFilter ? ` (${providerFilter})` : ""}</span>
              <div className="flex gap-4 text-xs text-app-text-secondary">
                <span>Req: {totals.requests}</span>
                <span>In: {totals.prompt_tokens.toLocaleString()} (${totals.cost_input.toFixed(2)})</span>
                <span>Out: {totals.completion_tokens.toLocaleString()} (${totals.cost_output.toFixed(2)})</span>
                <span className="font-medium text-app-text">USD: {totals.cost_total.toFixed(2)}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Configuration section */}
      <div className="rounded-lg border border-app-border bg-white p-4">
        <h4 className="mb-3 text-sm font-medium text-app-text">Configurar límite</h4>
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-[140px]">
            <label htmlFor="provider-select" className="mb-1 block text-xs text-app-text-secondary">Proveedor</label>
            <select
              id="provider-select"
              value={configProvider}
              onChange={(e) => setConfigProvider(e.target.value)}
              className="w-full rounded-md border border-app-border bg-white px-3 py-2 text-sm text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary/20"
            >
              <option value="">Seleccionar</option>
              {providers.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1 min-w-[140px]">
            <label htmlFor="model-select" className="mb-1 block text-xs text-app-text-secondary">Modelo (opcional)</label>
            <select
              id="model-select"
              value={configModel}
              onChange={(e) => setConfigModel(e.target.value)}
              disabled={!configProvider}
              className="w-full rounded-md border border-app-border bg-white px-3 py-2 text-sm text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary/20 disabled:opacity-50"
            >
              <option value="">Nivel proveedor</option>
              {Array.from(
                new Set(spend.filter((s) => s.provider === configProvider).map((s) => s.model)),
              ).map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1 min-w-[140px]">
            <label htmlFor="limit-input" className="mb-1 block text-xs text-app-text-secondary">Monto (USD)</label>
            <input
              id="limit-input"
              type="number"
              min={0}
              step={0.01}
              value={limitAmount}
              onChange={(e) => setLimitAmount(e.target.value)}
              placeholder="0.00"
              className="w-full rounded-md border border-app-border bg-white px-3 py-2 text-sm text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary/20"
            />
          </div>
          <button
            onClick={handleApply}
            disabled={saving || !configProvider || limitAmount === ""}
            className="rounded-md bg-app-primary px-4 py-2 text-sm font-medium text-white hover:bg-app-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? "Aplicando..." : "Aplicar"}
          </button>
        </div>
        {saveMsg && (
          <div className={`mt-3 rounded-md px-3 py-2 text-xs ${saveMsg.startsWith("Límite") ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
            {saveMsg}
          </div>
        )}
      </div>
    </div>
  );
}

export default BillingTab;
