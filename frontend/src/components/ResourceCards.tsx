import { useEffect, useState, type ReactElement } from "react";
import { ChevronDown, ChevronRight, X } from "lucide-react";
import configService, { type ToolInfo } from "../services/configService";
import type { ResourceKind, ResourceSelection } from "../utils/resourceSelection";

interface Option {
  name: string;
  description?: string;
}

interface ParamSchema {
  type?: string;
  description?: string;
}

interface ParamInputProps {
  name: string;
  schema: ParamSchema;
  required: boolean;
  value: unknown;
  onChange: (value: unknown) => void;
}

/**
 * Input for one argument of a tool, according to the type of its parameter.
 *
 * @param props - Name, schema and value of the parameter, and how to change it.
 * @returns The labelled input.
 */
function ParamInput({ name, schema, required, value, onChange }: ParamInputProps): ReactElement {
  const kind = schema.type ?? "string";
  const [text, setText] = useState(value === undefined ? "" : typeof value === "string" ? value : JSON.stringify(value));
  const base =
    "w-full border border-app-border rounded-lg px-2 py-1 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-app-primary-light";

  /**
   * Keep the typed text and tell the parent the value it means (nothing when the field is empty).
   *
   * @param next - Text of the field.
   */
  const change = (next: string): void => {
    setText(next);
    if (next.trim() === "") return onChange(undefined);
    if (kind === "integer" || kind === "number") {
      const parsed = Number(next);
      return onChange(Number.isNaN(parsed) ? undefined : parsed);
    }
    if (kind === "object" || kind === "array") {
      try {
        return onChange(JSON.parse(next));
      } catch {
        return onChange(undefined);
      }
    }
    return onChange(next);
  };

  return (
    <label className="block">
      <span className="text-[11px] font-medium text-app-text">
        {name} <span className="font-normal text-app-text-secondary">({kind}, {required ? "obligatorio" : "opcional"})</span>
      </span>
      {kind === "boolean" ? (
        <select
          value={value === undefined ? "" : String(value)}
          onChange={(e) => onChange(e.target.value === "" ? undefined : e.target.value === "true")}
          className={base}
        >
          <option value="">(sin indicar)</option>
          <option value="true">true</option>
          <option value="false">false</option>
        </select>
      ) : (
        <input
          type={kind === "integer" || kind === "number" ? "number" : "text"}
          value={text}
          onChange={(e) => change(e.target.value)}
          placeholder={kind === "object" || kind === "array" ? "JSON" : "(sin indicar)"}
          className={base}
        />
      )}
      {schema.description && (
        <span className="block text-[11px] text-app-text-secondary mt-0.5">{schema.description}</span>
      )}
    </label>
  );
}

interface ToolCardProps {
  tool: ToolInfo | undefined;
  name: string;
  args: Record<string, unknown>;
  onArgs: (args: Record<string, unknown>) => void;
  onRemove: () => void;
}

/**
 * Card of a picked tool: its description and its parameters, to fill the arguments.
 *
 * @param props - The tool (when it is known), the arguments filled and how to change or remove them.
 * @returns The collapsible card.
 */
function ToolCard({ tool, name, args, onArgs, onRemove }: ToolCardProps): ReactElement {
  const [open, setOpen] = useState(false);
  const properties = (tool?.parameters?.properties ?? {}) as Record<string, ParamSchema>;
  const required = tool?.parameters?.required ?? [];
  const filled = Object.keys(args).length;

  return (
    <div className="rounded-lg border border-app-primary/20 bg-app-primary/5">
      <div className="flex items-center gap-1.5 px-2 py-1">
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="flex flex-1 items-center gap-1.5 text-left text-xs font-medium text-app-text"
          aria-expanded={open}
        >
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          {name}
          {filled > 0 && (
            <span className="rounded-full bg-app-primary/15 px-1.5 text-[10px] text-app-primary">{filled}</span>
          )}
        </button>
        <button
          type="button"
          onClick={onRemove}
          className="rounded-full p-0.5 hover:bg-app-primary/15"
          aria-label={`Quitar ${name}`}
        >
          <X size={12} />
        </button>
      </div>
      {open && (
        <div className="space-y-2 border-t border-app-primary/10 px-3 py-2">
          {tool?.description && <p className="text-[11px] text-app-text-secondary">{tool.description}</p>}
          {Object.keys(properties).length === 0 ? (
            <p className="text-[11px] text-app-text-secondary">Esta tool no tiene parámetros.</p>
          ) : (
            Object.entries(properties).map(([param, schema]) => (
              <ParamInput
                key={param}
                name={param}
                schema={schema}
                required={required.includes(param)}
                value={args[param]}
                onChange={(value) => {
                  const next = { ...args };
                  if (value === undefined) delete next[param];
                  else next[param] = value;
                  onArgs(next);
                }}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

interface PickerProps {
  id: string;
  label: string;
  hint: string;
  options: Option[];
  picked: string[];
  loading: boolean;
  disabled: boolean;
  onChange: (names: string[]) => void;
  renderPicked?: (name: string) => ReactElement;
}

/**
 * Dropdown of the existing resources of one kind; what is picked stays as chips (or as cards).
 *
 * @param props - Label, options, what is picked and how to change it.
 * @returns The picker.
 */
function Picker({ id, label, hint, options, picked, loading, disabled, onChange, renderPicked }: PickerProps): ReactElement {
  const available = options.filter((o) => !picked.includes(o.name));
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-gray-700 mb-1">
        {label} <span className="text-xs text-app-text-secondary">(opcional)</span>
      </label>
      <select
        id={id}
        value=""
        disabled={disabled || loading || available.length === 0}
        onChange={(e) => {
          if (e.target.value) onChange([...picked, e.target.value]);
        }}
        className="w-full border border-app-border rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-app-primary-light focus:border-app-primary disabled:opacity-60"
      >
        <option value="">
          {loading
            ? "Cargando..."
            : options.length === 0
              ? "No hay disponibles"
              : available.length === 0
                ? "Ya seleccionaste todos"
                : "Agregar..."}
        </option>
        {available.map((o) => (
          <option key={o.name} value={o.name} title={o.description}>
            {o.name}
          </option>
        ))}
      </select>
      {picked.length > 0 && (
        <div className={renderPicked ? "mt-2 space-y-1.5" : "flex flex-wrap gap-1.5 mt-2"}>
          {picked.map((name) =>
            renderPicked ? (
              <div key={name}>{renderPicked(name)}</div>
            ) : (
              <span
                key={name}
                className="inline-flex items-center gap-1 rounded-full border border-app-primary/20 bg-app-primary/10 px-2 py-0.5 text-xs text-app-text"
              >
                {name}
                <button
                  type="button"
                  onClick={() => onChange(picked.filter((s) => s !== name))}
                  className="rounded-full p-0.5 hover:bg-app-primary/15"
                  aria-label={`Quitar ${name}`}
                >
                  <X size={12} />
                </button>
              </span>
            ),
          )}
        </div>
      )}
      <p className="text-xs text-app-text-secondary mt-1">{hint}</p>
    </div>
  );
}

interface ResourceCardsProps {
  /** Which kinds of resource the cards offer. */
  kinds: ResourceKind[];
  selection: ResourceSelection;
  onChange: (selection: ResourceSelection) => void;
  /** Prefix of the ids of the dropdowns (there can be several forms in a page). */
  idPrefix: string;
  disabled?: boolean;
  /** Render picked tools as plain chips (no argument cards). */
  hideToolArgs?: boolean;
  /** Intro text; defaults to the creators one (picked = mandatory). */
  intro?: string;
}

/**
 * Permission cards of the creators and of the scheduled tasks: agents, tools (with their parameters),
 * skills and RAG collections. What the user picks is mandatory for the creator, which may add others.
 *
 * @param props - Kinds to offer, what is picked and how to change it.
 * @returns The cards.
 */
export function ResourceCards({ kinds, selection, onChange, idPrefix, disabled = false, hideToolArgs = false, intro }: ResourceCardsProps): ReactElement {
  const [agentes, setAgentes] = useState<Option[]>([]);
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [skills, setSkills] = useState<Option[]>([]);
  const [rag, setRag] = useState<Option[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      kinds.includes("agentes") ? configService.getAgents().catch(() => []) : Promise.resolve([]),
      kinds.includes("tools") ? configService.getTools().catch(() => []) : Promise.resolve([]),
      kinds.includes("skills") ? configService.getSkills().catch(() => []) : Promise.resolve([]),
      kinds.includes("rag") ? configService.listKnowledge().catch(() => []) : Promise.resolve([]),
    ]).then(([a, t, s, k]) => {
      if (cancelled) return;
      setAgentes(a as Option[]);
      setTools(t as ToolInfo[]);
      setSkills(s as Option[]);
      setRag((k as string[]).map((name) => ({ name })));
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
    // The kinds a form offers do not change while it is open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-3">
      <p className="text-xs text-app-text-secondary">
        {intro ??
          "Lo que elijas es obligatorio: el creador lo tiene que usar. Puede sumar otros si lo considera necesario, y si no elegís nada, decide él."}
      </p>
      {kinds.includes("agentes") && (
        <Picker
          id={`${idPrefix}-agentes`}
          label="Agentes"
          hint="Agentes existentes que tiene que usar."
          options={agentes}
          picked={selection.agentes}
          loading={loading}
          disabled={disabled}
          onChange={(names) => onChange({ ...selection, agentes: names })}
        />
      )}
      {kinds.includes("tools") && (
        <Picker
          id={`${idPrefix}-tools`}
          label="Tools"
          hint="Tools existentes que tiene que usar. Abrí cada una para indicar sus argumentos."
          options={tools}
          picked={selection.tools}
          loading={loading}
          disabled={disabled}
          onChange={(names) => {
            const toolArgs = { ...selection.toolArgs };
            for (const name of Object.keys(toolArgs)) if (!names.includes(name)) delete toolArgs[name];
            onChange({ ...selection, tools: names, toolArgs });
          }}
          renderPicked={hideToolArgs ? undefined : (name) => (
            <ToolCard
              tool={tools.find((t) => t.name === name)}
              name={name}
              args={selection.toolArgs[name] ?? {}}
              onArgs={(args) => onChange({ ...selection, toolArgs: { ...selection.toolArgs, [name]: args } })}
              onRemove={() => {
                const toolArgs = { ...selection.toolArgs };
                delete toolArgs[name];
                onChange({ ...selection, tools: selection.tools.filter((t) => t !== name), toolArgs });
              }}
            />
          )}
        />
      )}
      {kinds.includes("skills") && (
        <Picker
          id={`${idPrefix}-skills`}
          label="Skills"
          hint="Skills existentes que tiene que usar."
          options={skills}
          picked={selection.skills}
          loading={loading}
          disabled={disabled}
          onChange={(names) => onChange({ ...selection, skills: names })}
        />
      )}
      {kinds.includes("rag") && (
        <Picker
          id={`${idPrefix}-rag`}
          label="Colecciones RAG"
          hint="Colecciones existentes que tiene que consultar."
          options={rag}
          picked={selection.rag}
          loading={loading}
          disabled={disabled}
          onChange={(names) => onChange({ ...selection, rag: names })}
        />
      )}
    </div>
  );
}
