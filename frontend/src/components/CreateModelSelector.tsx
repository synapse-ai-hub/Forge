import { useCallback, useEffect, useState } from "react";
import { Check } from "lucide-react";
import { API_BASE_URL } from "../config/api";

const API = API_BASE_URL + "/api";

/** Provider entry returned by GET /api/config/providers. */
interface ProviderEntry {
  provider: string;
  label: string;
}

interface CreateModelSelectorProps {
  /** Called when the user applies a (model, provider) selection. */
  onApply: (model: string, provider: string) => void;
  /** Optional: reports how many cloud providers are available after loading. */
  onProvidersChange?: (count: number) => void;
}

/**
 * Cloud provider/model picker for the creation interfaces.
 *
 * Lists only cloud providers (LOCAL is excluded). The selection is
 * ephemeral — it lives while the tab is open and is sent with each
 * creation request; nothing is persisted.
 */
export function CreateModelSelector({ onApply, onProvidersChange }: CreateModelSelectorProps) {
  const [providers, setProviders] = useState<ProviderEntry[]>([]);
  const [provider, setProvider] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const [applied, setApplied] = useState<{ model: string; provider: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  /* ---- load cloud providers once ---- */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch(`${API}/config/providers`);
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        if (cancelled) return;
        const cloud = (data.providers || []).filter(
          (p: ProviderEntry) => p.provider !== "LOCAL",
        );
        setProviders(cloud);
        onProvidersChange?.(cloud.length);
      } catch {
        if (!cancelled) setError("No se pudieron cargar los proveedores.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /* ---- load models when provider changes ---- */
  useEffect(() => {
    if (!provider) {
      setModels([]);
      setModel("");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch(
          `${API}/config/models?provider=${encodeURIComponent(provider)}`,
        );
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        if (cancelled) return;
        const list: string[] = data.models || [];
        setModels(list);
        setModel(list[0] || "");
      } catch {
        if (!cancelled) setError("No se pudieron cargar los modelos.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [provider]);

  /* ---- apply selection ---- */
  const handleApply = useCallback(() => {
    if (!provider || !model) return;
    setApplied({ model, provider });
    onApply(model, provider);
  }, [provider, model, onApply]);

  const dirty = !applied || applied.model !== model || applied.provider !== provider;

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        Proveedor y modelo <span className="text-xs text-app-text-secondary">(opcional)</span>
      </label>
      <p className="text-xs text-app-text-secondary mb-2">
        Elegí con qué modelo cloud se crea este elemento. Si no aplicás ninguno, se usa el modelo por defecto.
      </p>
      {error && <p className="text-xs text-red-500 mb-2">{error}</p>}
      <div className="flex gap-2">
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          className="flex-1 min-w-0 border border-app-border rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-app-primary-light focus:border-app-primary"
          aria-label="Proveedor"
        >
          <option value="">Seleccioná un proveedor</option>
          {providers.map((p) => (
            <option key={p.provider} value={p.provider}>
              {p.label}
            </option>
          ))}
        </select>
        <select
          value={model}
          onChange={(e) => setModel(e.target.value)}
          disabled={!provider || models.length === 0}
          className="flex-[2] min-w-0 border border-app-border rounded-lg px-3 py-2 text-sm bg-white disabled:bg-gray-50 disabled:text-gray-400 focus:outline-none focus:ring-2 focus:ring-app-primary-light focus:border-app-primary"
          aria-label="Modelo"
        >
          {!provider ? (
            <option value="">—</option>
          ) : models.length === 0 ? (
            <option value="">Sin modelos disponibles</option>
          ) : (
            models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))
          )}
        </select>
        <button
          type="button"
          onClick={handleApply}
          disabled={!provider || !model || !dirty}
          className="shrink-0 flex items-center gap-1 bg-gradient-to-r from-app-primary to-app-gradient-secondary text-white text-sm font-medium px-4 rounded-lg transition-colors hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
          title="Aplicar selección"
        >
          {applied && !dirty ? (
            <>
              <Check size={14} />
              Aplicado
            </>
          ) : (
            "Aplicar"
          )}
        </button>
      </div>
    </div>
  );
}

export default CreateModelSelector;
