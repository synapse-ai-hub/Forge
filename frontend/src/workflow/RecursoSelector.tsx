import { X } from "lucide-react";

interface Opcion {
  name: string;
  description?: string;
}

interface RecursoSelectorProps {
  id: string;
  label: string;
  hint: string;
  opciones: Opcion[];
  seleccionados: string[];
  onChange: (value: string[]) => void;
  loading?: boolean;
}

/** Dropdown de recursos existentes; lo elegido queda como chips que se pueden quitar. */
export function RecursoSelector({
  id,
  label,
  hint,
  opciones,
  seleccionados,
  onChange,
  loading = false,
}: RecursoSelectorProps) {
  const disponibles = opciones.filter((o) => !seleccionados.includes(o.name));

  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-gray-700 mb-1">
        {label} <span className="text-xs text-app-text-secondary">(opcional)</span>
      </label>
      <select
        id={id}
        value=""
        disabled={loading || disponibles.length === 0}
        onChange={(e) => {
          if (e.target.value) onChange([...seleccionados, e.target.value]);
        }}
        className="w-full border border-app-border rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-app-primary-light focus:border-app-primary disabled:opacity-60"
      >
        <option value="">
          {loading
            ? "Cargando..."
            : opciones.length === 0
              ? "No hay disponibles"
              : disponibles.length === 0
                ? "Ya seleccionaste todos"
                : "Agregar..."}
        </option>
        {disponibles.map((o) => (
          <option key={o.name} value={o.name} title={o.description}>
            {o.name}
          </option>
        ))}
      </select>
      {seleccionados.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {seleccionados.map((name) => (
            <span
              key={name}
              className="inline-flex items-center gap-1 rounded-full border border-app-primary/20 bg-app-primary/10 px-2 py-0.5 text-xs text-app-text"
            >
              {name}
              <button
                type="button"
                onClick={() => onChange(seleccionados.filter((s) => s !== name))}
                className="rounded-full p-0.5 hover:bg-app-primary/15"
                aria-label={`Quitar ${name}`}
              >
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      )}
      <p className="text-xs text-app-text-secondary mt-1">{hint}</p>
    </div>
  );
}
