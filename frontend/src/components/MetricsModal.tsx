import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "./ui/dialog";
import { useEffect, useRef, useState } from "react";
import {
  BarChart3,
  MessageSquare,
  Activity,
  AlertCircle,
  RefreshCw,
  Wrench,
  DollarSign,
  Download,
  Cpu,
  GitBranch,
  Hammer,
  ThumbsUp,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import metricsService, {
  type MetricsOverview,
  type SessionMetrics,
  type MessageMetrics,
  type ToolMetrics,
  type ModelMetrics,
  type CostMetrics,
  type ErrorMetrics,
  type WorkflowMetrics,
  type CreatorMetrics,
  type FeedbackMetrics,
} from "../services/metricsService";

interface MetricsModalProps {
  open: boolean;
  onClose: () => void;
}

type TimeRange = "1h" | "6h" | "1d" | "1w" | "1m" | "all";

interface MetricsData {
  overview: MetricsOverview | null;
  sessions: SessionMetrics | null;
  messages: MessageMetrics | null;
  tools: ToolMetrics | null;
  models: ModelMetrics | null;
  costs: CostMetrics | null;
  errors: ErrorMetrics | null;
  workflows: WorkflowMetrics | null;
  creators: CreatorMetrics | null;
  feedback: FeedbackMetrics | null;
}

const EMPTY_METRICS: MetricsData = {
  overview: null,
  sessions: null,
  messages: null,
  tools: null,
  models: null,
  costs: null,
  errors: null,
  workflows: null,
  creators: null,
  feedback: null,
};

const TIME_RANGES: { id: TimeRange; label: string }[] = [
  { id: "1h", label: "1h" },
  { id: "6h", label: "6h" },
  { id: "1d", label: "1d" },
  { id: "1w", label: "1w" },
  { id: "1m", label: "1m" },
  { id: "all", label: "Todo" },
];

function formatNumber(value: number): string {
  return value.toLocaleString("es-AR");
}

/** Tarjeta del sidebar: solo selección, sin despliegue inline. */
function SidebarCard({
  id,
  activeId,
  onSelect,
  title,
  value,
  icon,
  tone = "default",
  onDownload,
}: {
  id: string;
  activeId: string | null;
  onSelect: (id: string) => void;
  title: string;
  value: string;
  icon: React.ReactNode;
  tone?: "default" | "error";
  onDownload?: () => void;
}) {
  const selected = activeId === id;

  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={() => onSelect(id)}
      onKeyDown={(e) => {
        if (e.target !== e.currentTarget) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(id);
        }
      }}
      className={`rounded-xl border transition-all duration-200 cursor-pointer bg-white p-3 shadow-sm hover:shadow-md w-full text-left ${
        selected
          ? "border-[var(--color-app-primary)] ring-2 ring-[var(--color-app-primary)]/20 shadow-md"
          : "border-app-border hover:border-[var(--color-app-primary)]/50"
      }`}
    >
      <div className="flex items-center justify-between text-xs font-medium text-app-text-secondary">
        <div className="flex items-center gap-2">
          <span className="p-1.5 rounded-lg bg-app-bg-secondary text-[var(--color-app-primary)]">
            {icon}
          </span>
          <span className="truncate">{title}</span>
        </div>
        {onDownload && (
          <button
            type="button"
            title="Descargar CSV"
            onClick={(e) => {
              e.stopPropagation();
              onDownload();
            }}
            className="p-1 rounded-md text-app-text-secondary hover:text-app-text hover:bg-app-bg-secondary cursor-pointer"
          >
            <Download size={13} />
          </button>
        )}
      </div>
      <div className="mt-2">
        <div
          className={`text-xl font-bold tracking-tight ${
            tone === "error" ? "text-app-error" : "text-app-text"
          }`}
        >
          {value}
        </div>
      </div>
    </div>
  );
}

/** Subtarjeta clickeable de Sesiones: sin datos, solo selecciona el gráfico central. */
function SubCard({
  id,
  selectedId,
  onSelect,
  title,
}: {
  id: string;
  selectedId: string;
  onSelect: (id: string) => void;
  title: string;
}) {
  const selected = selectedId === id;
  return (
    <button
      type="button"
      onClick={() => onSelect(id)}
      className={`rounded-lg border px-3 py-2 text-xs font-medium text-left transition-all cursor-pointer ${
        selected
          ? "border-[var(--color-app-primary)] bg-white ring-2 ring-[var(--color-app-primary)]/20 text-app-text shadow-sm"
          : "border-app-border bg-white text-app-text-secondary hover:border-[var(--color-app-primary)]/50 hover:text-app-text"
      }`}
    >
      {title}
    </button>
  );
}

/** Barras fijas: siempre 12, mismo ancho, fechas bajo la línea, alto completo. */
function FixedBars({ data }: { data: { date: string; count: number }[] }) {
  const maxCount = Math.max(...data.map((d) => d.count), 1);
  const total = data.reduce((a, b) => a + b.count, 0);
  return (
    <div className="h-full flex flex-col">
      <div className="text-xs font-semibold text-app-text">
        {formatNumber(total)} sesiones
      </div>
      <div className="flex flex-1 min-h-0 gap-2 mt-2">
        <div className="flex flex-col justify-between text-[10px] font-medium text-app-text-secondary py-1 pr-1 text-right">
          <span>{maxCount}</span>
          <span>{Math.round(maxCount / 2)}</span>
          <span>0</span>
        </div>
        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex-1 flex items-end gap-2 rounded-lg border border-app-border bg-white px-3 pt-3">
            {data.map((d, i) => (
              <div
                key={`${d.date}-${i}`}
                className="flex-1 flex flex-col items-center justify-end gap-1 min-w-0 h-full"
                title={`${d.date}: ${formatNumber(d.count)}`}
              >
                <span className="text-[11px] font-bold text-app-text">
                  {d.count > 0 ? d.count : ""}
                </span>
                <div
                  className="w-full rounded-t border"
                  style={{
                    height: d.count > 0 ? `${Math.max((d.count / maxCount) * 100, 10)}%` : "3px",
                    flexGrow: d.count > 0 ? undefined : 0,
                    backgroundColor: d.count > 0 ? "#8b5cf6" : "#e5e7eb",
                    borderColor: d.count > 0 ? "#7c3aed" : "#d1d5db",
                  }}
                />
              </div>
            ))}
          </div>
          <div className="border-t-2 border-app-text mt-0" />
          <div className="flex gap-2 pt-1 overflow-visible" style={{ minHeight: "44px" }}>
            {data.map((d, i) => (
              <div key={`${d.date}-${i}`} className="flex-1 min-w-0 text-right text-[10px] font-medium text-app-text-secondary" style={{ whiteSpace: "nowrap", overflow: "visible" }}>
                <span style={{ display: "inline-block", transform: "rotate(-45deg)", transformOrigin: "top right" }}>{d.date}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Redondea un valor hacia arriba a un número "lindo" para los ticks del eje. */
function niceCeil(v: number): number {
  if (v <= 0) return 1;
  const pow = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / pow;
  const nice = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return nice * pow;
}

/** Barras categóricas horizontales con ejes: nombres a la izquierda, valores abajo. */
function CatBars({
  data,
  valueFormatter = (v) => formatNumber(v),
}: {
  data: { name: string; value: number }[];
  valueFormatter?: (v: number) => string;
}) {
  if (data.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-xs text-app-text-secondary">
        Sin datos para este rango
      </div>
    );
  }
  const maxValue = Math.max(...data.map((d) => d.value), 1);
  const niceMax = niceCeil(maxValue);
  return (
    <div className="h-full flex flex-col pt-2">
      <div className="flex-1 min-h-0 flex flex-col">
        <div className="flex-1 min-h-0 flex">
          <div className="w-48 shrink-0 pr-3 flex flex-col justify-around text-right text-[10px] font-medium text-app-text-secondary">
            {data.map((d, i) => (
              <div key={`${d.name}-${i}`} className="leading-tight break-words" title={d.name}>
                {d.name}
              </div>
            ))}
          </div>
          <div className="flex-1 flex flex-col justify-around gap-1 min-w-0">
            {data.map((d, i) => (
              <div key={`${d.name}-${i}`} className="flex items-center gap-2">
                <div
                  className="h-4 rounded-r border"
                  style={{
                    width: d.value > 0 ? `${Math.max((d.value / niceMax) * 100, 2)}%` : "2px",
                    backgroundColor: d.value > 0 ? "#8b5cf6" : "#e5e7eb",
                    borderColor: d.value > 0 ? "#7c3aed" : "#d1d5db",
                  }}
                />
                <span className="text-[10px] font-bold text-app-text shrink-0">
                  {d.value > 0 ? valueFormatter(d.value) : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
        <div className="flex">
          <div className="w-48 shrink-0" />
          <div className="flex-1 border-t-2 border-app-text mt-1 flex justify-between text-[9px] text-app-text-secondary">
            <span>0</span>
            <span>{valueFormatter(niceMax / 2)}</span>
            <span>{valueFormatter(niceMax)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Barras categóricas con encabezado (título + dropdown de modelo + descarga), siguiendo el formato de HistBox. */
function CatBox({
  title,
  data,
  valueFormatter,
  showModelDropdown,
  models,
  selectedModel,
  onSelectModel,
  showToolDropdown,
  tools,
  selectedTool,
  onSelectTool,
  onDownload,
}: {
  title: string;
  data: { name: string; value: number }[];
  valueFormatter?: (v: number) => string;
  showModelDropdown?: boolean;
  models?: { provider: string; model: string }[];
  selectedModel?: { provider: string; model: string } | null;
  onSelectModel?: (m: { provider: string; model: string } | null) => void;
  showToolDropdown?: boolean;
  tools?: { tool: string }[];
  selectedTool?: string | null;
  onSelectTool?: (t: string | null) => void;
  onDownload?: () => void;
}) {
  return (
    <div className="h-full flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-semibold text-app-text">{title}</div>
        <div className="flex items-center gap-2">
          {showModelDropdown && (
            <select
              value={
                selectedModel
                  ? `${selectedModel.provider}|${selectedModel.model}`
                  : ""
              }
              onChange={(e) => {
                const raw = e.target.value;
                if (!raw) {
                  onSelectModel?.(null);
                  return;
                }
                const [provider, ...rest] = raw.split("|");
                onSelectModel?.({ provider, model: rest.join("|") });
              }}
              className="rounded-md border border-app-border bg-white px-1.5 py-1 text-[10px] font-medium text-app-text-secondary cursor-pointer"
            >
              <option value="">Todos</option>
              {(models ?? []).map((m) => (
                <option
                  key={`${m.provider}|${m.model}`}
                  value={`${m.provider}|${m.model}`}
                >
                  {m.provider} {m.model}
                </option>
              ))}
            </select>
          )}
          {showToolDropdown && (
            <select
              value={selectedTool ?? ""}
              onChange={(e) => {
                onSelectTool?.(e.target.value || null);
              }}
              className="rounded-md border border-app-border bg-white px-1.5 py-1 text-[10px] font-medium text-app-text-secondary cursor-pointer"
            >
              <option value="">Todas</option>
              {(tools ?? []).map((t) => (
                <option key={t.tool} value={t.tool}>
                  {t.tool}
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            title="Descargar JSON"
            onClick={onDownload}
            className="flex items-center gap-1 rounded-md border border-app-border px-2 py-1 text-[10px] font-medium text-app-text-secondary hover:text-app-text hover:bg-app-bg-secondary cursor-pointer"
          >
            <Download size={12} /> JSON
          </button>
        </div>
      </div>
      <div className="flex-1 min-h-0 rounded-lg border border-app-border bg-white p-2">
        <CatBars data={data} valueFormatter={valueFormatter} />
      </div>
    </div>
  );
}

/** Spanish labels for query-folder sections, used in download filenames. */
const DOWNLOAD_SECTION: Record<string, string> = {
  sessions: "sesiones",
  messages: "mensajes",
  tools: "herramientas",
  models: "modelos",
  agent_errors: "errores",
  workflows: "workflows",
  creators: "creadores",
  feedback: "calidad",
};

/** Distribución liviana: bins + stats del backend, render Recharts mismo estilo. */
function HistBox({
  queryFile,
  valueColumn,
  title,
  timeRange,
  percentiles = false,
  model,
  provider,
  models,
  selectedModel,
  onSelectModel,
  filterColumn,
}: {
  queryFile: string;
  valueColumn: string;
  title: string;
  timeRange: string;
  percentiles?: boolean;
  model?: string;
  provider?: string;
  models?: { provider: string; model: string }[];
  selectedModel?: { provider: string; model: string } | null;
  onSelectModel?: (m: { provider: string; model: string } | null) => void;
  filterColumn?: string;
}) {
  type Bin = { label: string; count: number; low?: number; high?: number };
  const [bins, setBins] = useState<Bin[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<Record<string, number | string | number[]> | null>(null);
  const [percentile, setPercentile] = useState<number | null>(null);
  const lastBins = useRef<Bin[] | null>(null);

  const fmtRange = (v: unknown) => {
    if (typeof v !== "number" || !Number.isFinite(v)) return String(v ?? "—");
    return Math.abs(v) >= 1000 || Number.isInteger(v)
      ? Math.round(v).toLocaleString("es-AR")
      : v.toLocaleString("es-AR", { maximumFractionDigits: 2 });
  };

  useEffect(() => {
    let cancelled = false;
    setError(null);
    metricsService
      .getDistributionFigure({
        query_file: queryFile,
        value_column: valueColumn,
        time_range: timeRange,
        ...(percentile !== null ? { percentile } : {}),
        ...(model && provider ? { model, provider } : {}),
        ...(filterColumn ? { filter_column: filterColumn } : {}),
      })
      .then((res) => {
        if (cancelled) return;
        lastBins.current = res.bins;
        setBins(res.bins);
        setStats(res.stats);
      })
      .catch((e) => {
        if (cancelled) return;
        lastBins.current = null;
        setBins([]);
        setStats(null);
        const msg = e instanceof Error ? e.message : "Error";
        setError(/no data/i.test(msg) ? "Sin datos para este rango" : msg);
      });
    return () => {
      cancelled = true;
    };
  }, [queryFile, valueColumn, timeRange, percentile, model, provider, filterColumn]);

  const downloadJson = () => {
    if (!stats) return;
    try {
      const blob = new Blob([JSON.stringify(stats, null, 2)], {
        type: "application/json",
      });
      const href = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = href;
      const folder = queryFile.split("/")[1] ?? "metrica";
      const section = DOWNLOAD_SECTION[folder] ?? folder;
      const base = (queryFile.split("/").pop() ?? valueColumn).replace(/\.sql$/, "");
      const namePart = valueColumn === "value" ? base : valueColumn;
      const suffix = percentile !== null ? `_p${Math.round(percentile * 100)}` : "";
      anchor.download = `${section}_${namePart}${suffix}_${timeRange}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(href);
    } catch (e) {
      console.error(e);
    }
  };

  const shown = bins.length > 0 ? bins : lastBins.current ?? [];
  const fmtStat = (v: unknown) =>
    typeof v === "number" ? v.toLocaleString("es-AR", { maximumFractionDigits: 2 }) : String((v as string) ?? "—");

  return (
    <div className="h-full flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-semibold text-app-text">{title}</div>
        <div className="flex items-center gap-2">
          {models && onSelectModel && (
            <select
              value={
                selectedModel
                  ? `${selectedModel.provider}|${selectedModel.model}`
                  : ""
              }
              onChange={(e) => {
                const raw = e.target.value;
                if (!raw) {
                  onSelectModel(null);
                  return;
                }
                const [provider, ...rest] = raw.split("|");
                onSelectModel({ provider, model: rest.join("|") });
              }}
              className="rounded-md border border-app-border bg-white px-1.5 py-1 text-[10px] font-medium text-app-text-secondary cursor-pointer"
            >
              <option value="">Todos</option>
              {models.map((m) => (
                <option
                  key={`${m.provider}|${m.model}`}
                  value={`${m.provider}|${m.model}`}
                >
                  {m.provider} {m.model}
                </option>
              ))}
            </select>
          )}
          {percentiles && (
            <select
              value={percentile === null ? "" : String(percentile)}
              onChange={(e) =>
                setPercentile(e.target.value === "" ? null : Number(e.target.value))
              }
              className="rounded-md border border-app-border bg-white px-1.5 py-1 text-[10px] font-medium text-app-text-secondary cursor-pointer"
            >
              <option value="">General</option>
              <option value="0.5">p50</option>
              <option value="0.95">p95</option>
              <option value="0.99">p99</option>
            </select>
          )}
          <button
            type="button"
            title="Descargar JSON"
            onClick={downloadJson}
            disabled={!stats}
            className="flex items-center gap-1 rounded-md border border-app-border px-2 py-1 text-[10px] font-medium text-app-text-secondary hover:text-app-text hover:bg-app-bg-secondary disabled:opacity-40 cursor-pointer disabled:cursor-default"
          >
            <Download size={12} /> JSON
          </button>
        </div>
      </div>
      <div className="flex-1 min-h-0 rounded-lg border border-app-border bg-white p-2 flex flex-col">
        {shown.length > 0 ? (
          <>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={shown} margin={{ top: 24, right: 8, left: -12, bottom: 52 }}>
                  <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="label"
                    tick={{ fontSize: 10, fill: "#6b7280", angle: -45, textAnchor: "end" }}
                    tickLine={false}
                    axisLine={{ stroke: "#111827", strokeWidth: 2 }}
                    interval={0}
                    height={48}
                    tickFormatter={(v: string) => fmtRange(v)}
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fontSize: 10, fill: "#6b7280" }}
                    tickLine={false}
                    axisLine={false}
                    width={36}
                    domain={[0, (dataMax: number) => Math.ceil((dataMax || 0) * 1.2 + 1)]}
                  />
                  <Tooltip
                    content={(props: any) => {
                      const active = props?.active as boolean | undefined;
                      const payload = props?.payload as { payload?: { low?: number; high?: number; count?: number } }[] | undefined;
                      if (!active || !payload || payload.length === 0) return null;
                      const p = payload[0]?.payload;
                      const count = p?.count ?? 0;
                      const total = Number(stats?.["Total Data"] ?? 0) || 0;
                      const pct = total > 0 ? Math.round((count / total) * 100) : 0;
                      const lo = typeof p?.low === "number" ? fmtRange(p.low) : "—";
                      const hi = typeof p?.high === "number" ? fmtRange(p.high) : "—";
                      return (
                        <div style={{ fontSize: 11, background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8, padding: "8px 10px" }}>
                          <div style={{ fontWeight: 700 }}>{lo} – {hi}</div>
                          <div>{count} casos ({pct}%)</div>
                        </div>
                      );
                    }}
                  />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={48} isAnimationActive={false}>
                    {shown.map((d, i) => (
                      <Cell key={`cell-${i}`} fill={d.count > 0 ? "#8b5cf6" : "transparent"} stroke={d.count > 0 ? "#7c3aed" : "transparent"} />
                    ))}
                    <LabelList dataKey="count" position="top" dy={-4} style={{ fontSize: 10, fontWeight: 700, fill: "#111827" }} formatter={(v: unknown) => (typeof v === "number" && v > 0 ? String(v) : "")} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            {stats && typeof stats["min"] === "number" && typeof stats["max"] === "number" && (stats["max"] as number) > (stats["min"] as number) && (
              <div className="mt-1 px-1">
                <div className="relative h-8">
                  {(() => {
                    const smin = stats["min"] as number;
                    const smax = stats["max"] as number;
                    const q1 = stats["Q1"] as number;
                    const med = (stats["median"] as number) ?? (stats["Q2"] as number);
                    const q3 = stats["Q3"] as number;
                    const span = smax - smin || 1;
                    const pct = (v: number) => Math.max(0, Math.min(100, ((v - smin) / span) * 100));
                    const outs = Array.isArray(stats["outliers"]) ? (stats["outliers"] as number[]).filter((v) => typeof v === "number" && Number.isFinite(v)).slice(0, 20) : [];
                    return (
                      <>
                        <div className="absolute top-1/2 left-0 right-0 h-[2px] bg-app-border" />
                        <div className="absolute top-1/2 -translate-y-1/2 h-4 rounded border" style={{ left: `${pct(q1)}%`, width: `${Math.max(pct(q3) - pct(q1), 2)}%`, backgroundColor: "#8b5cf6", borderColor: "#7c3aed" }} />
                        <div className="absolute top-1/2 -translate-y-1/2 w-[2px] h-4 bg-white" style={{ left: `calc(${pct(med)}% - 1px)` }} />
                        <div className="absolute top-1/2 -translate-y-1/2 w-[2px] h-3 bg-app-text" style={{ left: `${pct(smin)}%` }} />
                        <div className="absolute top-1/2 -translate-y-1/2 w-[2px] h-3 bg-app-text" style={{ left: `${pct(smax)}%` }} />
                        {outs.map((v, i) => (
                          <div key={`out-${i}`} title={`Atípico: ${fmtRange(v)}`} className="absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-red-500 border border-red-700" style={{ left: `calc(${pct(v)}% - 4px)` }} />
                        ))}
                      </>
                    );
                  })()}
                </div>
              </div>
            )}
            {stats && (
              <div className="mt-2 grid grid-cols-5 gap-x-3 gap-y-1 text-[10px] text-app-text-secondary border-t border-app-border pt-2">
                <span>Min: <span className="font-bold text-app-text">{fmtStat(stats["min"])}</span></span>
                <span>Q1: <span className="font-bold text-app-text">{fmtStat(stats["Q1"])}</span></span>
                <span>Q2: <span className="font-bold text-app-text">{fmtStat(stats["Q2"])}</span></span>
                <span>Q3: <span className="font-bold text-app-text">{fmtStat(stats["Q3"])}</span></span>
                <span>Q4: <span className="font-bold text-app-text">{fmtStat(stats["Q4"])}</span></span>
                <span>Media: <span className="font-bold text-app-text">{fmtStat(stats["mean"])}</span></span>
                <span>Mediana: <span className="font-bold text-app-text">{fmtStat(stats["median"])}</span></span>
                <span>Moda: <span className="font-bold text-app-text">{fmtStat(stats["mode"])}</span></span>
                <span>STD: <span className="font-bold text-app-text">{fmtStat(stats["STD"])}</span></span>
                <span>IQR: <span className="font-bold text-app-text">{fmtStat(stats["IQR"])}</span></span>
                <span>Max: <span className="font-bold text-app-text">{fmtStat(stats["max"])}</span></span>
                <span>Lim sup: <span className="font-bold text-app-text">{fmtStat(stats["Top Limit Outliers"])}</span></span>
                <span>Lim inf: <span className="font-bold text-app-text">{fmtStat(stats["Bottom Limit Outliers"])}</span></span>
                <span>Total: <span className="font-bold text-app-text">{fmtStat(stats["Total Data"])}</span></span>
                <span>Outliers: <span className="font-bold text-app-text">{fmtStat(stats["Outliers Quantity"])}</span></span>
              </div>
            )}
          </>
        ) : error ? (
          <div className="flex-1 flex items-center justify-center text-xs text-app-text-secondary">{error}</div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-xs text-app-text-secondary">Cargando…</div>
        )}
      </div>
    </div>
  );
}

const SESIONES_SUBS = [
  { id: "cantidad", title: "Cantidad de sesiones" },
  { id: "mensajes_total", title: "Total de mensajes" },
  { id: "tokens_entrada", title: "Tokens de entrada" },
  { id: "tokens_salida", title: "Tokens de salida" },
  { id: "latencia_promedio", title: "Latencia promedio por sesión" },
];

const MENSAJES_SUBS = [
  { id: "steps", title: "Steps por mensaje" },
  { id: "tokens_entrada", title: "Tokens de entrada por mensaje" },
  { id: "tokens_salida", title: "Tokens de salida por mensaje" },
  { id: "tiempo", title: "Tiempo por mensaje" },
  { id: "latencia", title: "Latencia por mensaje" },
];

const TOOLS_SUBS = [
  { id: "llamadas", title: "Llamadas por herramienta" },
  { id: "tiempo_distribucion", title: "Tiempo por llamada" },
  { id: "tiempo_promedio", title: "Tiempo promedio por herramienta" },
  { id: "subagentes", title: "Subagentes" },
];

const MODELS_SUBS = [
  { id: "llamadas", title: "Llamadas por modelo" },
  { id: "tokens_entrada", title: "Tokens de entrada" },
  { id: "tokens_salida", title: "Tokens de salida" },
  { id: "llamadas_herramientas", title: "Llamadas a herramientas" },
  { id: "latencia", title: "Latencia" },
];

const COSTS_SUBS = [
  { id: "total", title: "Costo total" },
  { id: "por_sesion", title: "Costo por sesión" },
  { id: "por_turno", title: "Costo por turno" },
];

const ERRORS_SUBS = [
  { id: "por_modelo", title: "Errores por modelo" },
  { id: "por_sesion", title: "Errores por sesión" },
  { id: "por_turno", title: "Errores por turno" },
  { id: "por_herramienta", title: "Errores por herramienta" },
];

const WORKFLOWS_SUBS = [
  { id: "por_workflow", title: "Por workflow" },
  { id: "por_fuente", title: "Por fuente" },
  { id: "por_estado", title: "Por estado" },
  { id: "costo", title: "Costo por corrida" },
  { id: "tiempo", title: "Tiempo por corrida" },
  { id: "tokens", title: "Tokens por corrida" },
];

const CREATORS_SUBS = [
  { id: "por_tipo", title: "Por tipo" },
  { id: "por_estado", title: "Por estado" },
  { id: "costo", title: "Costo por pedido" },
  { id: "tiempo", title: "Tiempo por pedido" },
  { id: "tokens", title: "Tokens por pedido" },
];

const FEEDBACK_SUBS = [
  { id: "por_tipo", title: "Por tipo" },
  { id: "por_modelo", title: "Por modelo" },
];

export function MetricsModal({ open, onClose }: MetricsModalProps) {
  const [timeRange, setTimeRange] = useState<TimeRange>("1m");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<MetricsData>(EMPTY_METRICS);
  const [activeCardId, setActiveCardId] = useState<string | null>(null);
  const [sesionSub, setSesionSub] = useState<string>("cantidad");
  const [mensajeSub, setMensajeSub] = useState<string>("steps");
  const [toolsSub, setToolsSub] = useState<string>("llamadas");
  const [modelsSub, setModelsSub] = useState<string>("llamadas");
  const [costsSub, setCostsSub] = useState<string>("total");
  const [selectedModel, setSelectedModel] = useState<{
    provider: string;
    model: string;
  } | null>(null);
  const [selectedCostModel, setSelectedCostModel] = useState<{
    provider: string;
    model: string;
  } | null>(null);
  const [errorsSub, setErrorsSub] = useState<string>("por_modelo");
  const [selectedErrorModel, setSelectedErrorModel] = useState<{
    provider: string;
    model: string;
  } | null>(null);
  const [selectedErrorTool, setSelectedErrorTool] = useState<string | null>(null);
  const [workflowsSub, setWorkflowsSub] = useState<string>("por_workflow");
  const [creatorsSub, setCreatorsSub] = useState<string>("por_tipo");
  const [feedbackSub, setFeedbackSub] = useState<string>("por_tipo");

  const hasData = metrics.overview !== null || metrics.sessions !== null;

  const loadAll = async () => {
    const firstLoad = !hasData;
    if (firstLoad) setLoading(true);
    else setRefreshing(true);
    setError(null);
    try {
      const [overviewRes, sessionsRes, messagesRes, toolsRes, modelsRes, costsRes, errorsRes, workflowsRes, creatorsRes, feedbackRes] =
        await Promise.allSettled([
          metricsService.getOverview(timeRange),
          metricsService.getSessionMetrics(timeRange),
          metricsService.getMessageMetrics(timeRange),
          metricsService.getToolMetrics(timeRange),
          metricsService.getModelMetrics(timeRange),
          metricsService.getCostMetrics(timeRange),
          metricsService.getErrorMetrics(timeRange),
          metricsService.getWorkflowMetrics(timeRange),
          metricsService.getCreatorMetrics(timeRange),
          metricsService.getFeedbackMetrics(timeRange),
        ]);

      setMetrics({
        overview: overviewRes.status === "fulfilled" ? overviewRes.value : null,
        sessions: sessionsRes.status === "fulfilled" ? sessionsRes.value : null,
        messages: messagesRes.status === "fulfilled" ? messagesRes.value : null,
        tools: toolsRes.status === "fulfilled" ? toolsRes.value : null,
        models: modelsRes.status === "fulfilled" ? modelsRes.value : null,
        costs: costsRes.status === "fulfilled" ? costsRes.value : null,
        errors: errorsRes.status === "fulfilled" ? errorsRes.value : null,
        workflows: workflowsRes.status === "fulfilled" ? workflowsRes.value : null,
        creators: creatorsRes.status === "fulfilled" ? creatorsRes.value : null,
        feedback: feedbackRes.status === "fulfilled" ? feedbackRes.value : null,
      });

      if (
        overviewRes.status === "rejected" &&
        sessionsRes.status === "rejected" &&
        messagesRes.status === "rejected" &&
        toolsRes.status === "rejected" &&
        modelsRes.status === "rejected" &&
        costsRes.status === "rejected" &&
        errorsRes.status === "rejected" &&
        workflowsRes.status === "rejected" &&
        creatorsRes.status === "rejected" &&
        feedbackRes.status === "rejected"
      ) {
        setError("No se pudieron cargar las métricas. Verificá el backend.");
      }
    } catch (err) {
      setError("Error inesperado al cargar métricas.");
      console.error(err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const notifyDownload = (p: Promise<void>) => {
    p.catch((e) => {
      const msg = e instanceof Error ? e.message : String(e);
      console.error(e);
      window.alert(msg);
    });
  };

  const downloadJson = (data: unknown, name: string) => {
    if (!data) return;
    try {
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const href = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = `${name}_${timeRange}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(href);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    if (open) {
      setActiveCardId("sessions");
      setSesionSub("cantidad");
      setMensajeSub("steps");
      setToolsSub("llamadas");
      setModelsSub("llamadas");
      setCostsSub("total");
      setErrorsSub("por_modelo");
      setWorkflowsSub("por_workflow");
      setCreatorsSub("por_tipo");
      setFeedbackSub("por_tipo");
      setSelectedModel(null);
      setSelectedCostModel(null);
      setSelectedErrorModel(null);
      setSelectedErrorTool(null);
    }
  }, [open]);

  useEffect(() => {
    if (open) {
      loadAll();
    }
  }, [open, timeRange]);

  // Reset the model selection if the selected combo is no longer present
  // in any metric with data for the current time range.
  useEffect(() => {
    if (!selectedModel) return;
    const allWithData = [
      ...(metrics.models?.models ?? []),
      ...(metrics.models?.tokens_input ?? []),
      ...(metrics.models?.tokens_output ?? []),
      ...(metrics.models?.tool_calls ?? []),
      ...(metrics.models?.latency_models ?? []),
    ];
    const exists = allWithData.some(
      (m) =>
        m.provider === selectedModel.provider && m.model === selectedModel.model,
    );
    if (!exists) setSelectedModel(null);
  }, [metrics.models, selectedModel]);

  // Each model subcard only offers models with data for that metric,
  // so a failing model without latency/tokens never shows an empty dropdown.
  useEffect(() => {
    setSelectedModel(null);
  }, [modelsSub]);

  const ov = metrics.overview;
  const ses = metrics.sessions;
  const tls = metrics.tools;
  const errs = metrics.errors;
  const mdl = metrics.models;
  const cts = metrics.costs;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="flex h-[920px] max-w-7xl w-[1300px] flex-col gap-0 p-0 overflow-hidden bg-app-bg border border-app-border rounded-xl shadow-2xl">
        <DialogHeader className="px-6 py-4 border-b border-app-border flex flex-row items-center justify-between space-y-0 bg-white">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-app-bg-secondary text-[var(--color-app-primary)]">
              <BarChart3 size={20} />
            </span>
            <div>
              <DialogTitle className="text-base font-bold text-app-text">
                Dashboard Interactivo de Métricas
              </DialogTitle>
              <DialogDescription className="text-xs text-app-text-secondary">
                Seleccioná una tarjeta del sidebar para ver su visualización en el panel central.
              </DialogDescription>
            </div>
          </div>

          <div className="flex items-center gap-1.5 bg-app-bg-secondary p-1 rounded-lg border border-app-border mr-8">
            {TIME_RANGES.map((tr) => (
              <button
                key={tr.id}
                onClick={() => setTimeRange(tr.id)}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-all ${
                  timeRange === tr.id
                    ? "bg-[var(--color-app-primary)] text-white shadow-sm"
                    : "text-app-text-secondary hover:text-app-text hover:bg-app-bg-tertiary"
                }`}
              >
                {tr.label}
              </button>
            ))}
          </div>
        </DialogHeader>

        {/* Content area: sidebar + central */}
        <div className="flex-1 min-h-0 flex bg-app-bg-secondary">
          {loading && !hasData ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 text-sm text-app-text-secondary">
              <RefreshCw size={28} className="animate-spin text-[var(--color-app-primary)]" />
              Cargando métricas y gráficos analíticos...
            </div>
          ) : error && !hasData ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-4 text-sm">
              <AlertCircle size={32} className="text-app-error" />
              <p className="text-app-error">{error}</p>
              <button
                onClick={loadAll}
                className="px-4 py-2 text-xs font-medium rounded-lg bg-[var(--color-app-primary)] text-white hover:opacity-90 transition-opacity"
              >
                Reintentar
              </button>
            </div>
          ) : (
            <>
              {/* Sidebar tarjetas principales */}
              <aside className="w-[300px] shrink-0 border-r border-app-border bg-white overflow-y-auto p-3 space-y-3">
                <SidebarCard
                  id="sessions"
                  activeId={activeCardId}
                  onSelect={(id) => setActiveCardId(id)}
                  title="Sesiones"
                  value={formatNumber(ov?.total_sessions ?? ses?.total_sessions ?? 0)}
                  icon={<MessageSquare size={16} />}
                  onDownload={() => notifyDownload(metricsService.downloadSessionsCsv(timeRange))}
                />
                <SidebarCard
                  id="messages"
                  activeId={activeCardId}
                  onSelect={(id) => setActiveCardId(id)}
                  title="Mensajes"
                  value={formatNumber(ov?.total_messages ?? 0)}
                  icon={<Activity size={16} />}
                  onDownload={() => notifyDownload(metricsService.downloadMessagesCsv(timeRange))}
                />
                <SidebarCard
                  id="tools"
                  activeId={activeCardId}
                  onSelect={(id) => setActiveCardId(id)}
                  title="Uso de herramientas"
                  value={formatNumber(tls?.total_tool_calls ?? 0)}
                  icon={<Wrench size={16} />}
                  onDownload={() => notifyDownload(metricsService.downloadToolsCsv(timeRange))}
                />
                <SidebarCard
                  id="models"
                  activeId={activeCardId}
                  onSelect={(id) => setActiveCardId(id)}
                  title="Modelos"
                  value={formatNumber(mdl?.total_models ?? 0)}
                  icon={<Cpu size={16} />}
                  onDownload={() => notifyDownload(metricsService.downloadModelsCsv(timeRange))}
                />
                <SidebarCard
                  id="spend"
                  activeId={activeCardId}
                  onSelect={(id) => setActiveCardId(id)}
                  title="Gasto"
                  value={`$${(ov?.total_cost ?? 0).toFixed(2)}`}
                  icon={<DollarSign size={16} />}
                  onDownload={() => notifyDownload(metricsService.downloadCostsCsv(timeRange))}
                />
                <SidebarCard
                  id="workflows"
                  activeId={activeCardId}
                  onSelect={(id) => setActiveCardId(id)}
                  title="Workflows"
                  value={formatNumber(metrics.workflows?.total_runs ?? 0)}
                  icon={<GitBranch size={16} />}
                  onDownload={() => notifyDownload(metricsService.downloadWorkflowsCsv(timeRange))}
                />
                <SidebarCard
                  id="creators"
                  activeId={activeCardId}
                  onSelect={(id) => setActiveCardId(id)}
                  title="Creadores"
                  value={formatNumber(metrics.creators?.total_requests ?? 0)}
                  icon={<Hammer size={16} />}
                  onDownload={() => notifyDownload(metricsService.downloadCreatorsCsv(timeRange))}
                />
                <SidebarCard
                  id="feedback"
                  activeId={activeCardId}
                  onSelect={(id) => setActiveCardId(id)}
                  title="Calidad"
                  value={`${(metrics.feedback?.quality_rate ?? 0).toFixed(1)}%`}
                  icon={<ThumbsUp size={16} />}
                  onDownload={() => notifyDownload(metricsService.downloadFeedbackCsv(timeRange))}
                />
                <SidebarCard
                  id="errors"
                  activeId={activeCardId}
                  onSelect={(id) => setActiveCardId(id)}
                  title="Errores"
                  value={formatNumber(errs?.total_errors ?? ov?.total_errors ?? 0)}
                  icon={<AlertCircle size={16} />}
                  tone="error"
                  onDownload={() => notifyDownload(metricsService.downloadErrorsCsv(timeRange))}
                />
              </aside>

              {/* Central visualización */}
              <main className="flex-1 min-w-0 overflow-y-auto p-6">
                {activeCardId === "sessions" && (
                  <div className="space-y-4">
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm relative">
                      {refreshing && (
                        <div className="absolute top-3 right-3 flex items-center gap-1 text-[11px] text-app-text-secondary">
                          <RefreshCw size={12} className="animate-spin" /> Actualizando…
                        </div>
                      )}
                      <div className="text-sm font-bold text-app-text">Sesiones</div>
                      <div className="mt-2 h-[440px]">
                        {sesionSub === "cantidad" && (
                          <FixedBars data={metrics.sessions?.cantidad ?? []} />
                        )}
                        {sesionSub === "mensajes_total" && (
                          <HistBox queryFile="metrics/sessions/messages_per_session.sql" valueColumn="msg_count" title="Total de mensajes por sesión" timeRange={timeRange} />
                        )}
                        {sesionSub === "tokens_entrada" && (
                          <HistBox queryFile="metrics/sessions/input_tokens.sql" valueColumn="input_tokens" title="Tokens de entrada por sesión" timeRange={timeRange} />
                        )}
                        {sesionSub === "tokens_salida" && (
                          <HistBox queryFile="metrics/sessions/output_tokens.sql" valueColumn="output_tokens" title="Tokens de salida por sesión" timeRange={timeRange} />
                        )}
                        {sesionSub === "latencia_promedio" && (
                          <HistBox queryFile="metrics/sessions/latency_per_session.sql" valueColumn="avg_lat" title="Latencia promedio por sesión" timeRange={timeRange} />
                        )}
                      </div>
                    </div>
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm">
                      <div className="flex flex-wrap gap-2">
                        {SESIONES_SUBS.map((s) => (
                          <SubCard key={s.id} id={s.id} selectedId={sesionSub} onSelect={setSesionSub} title={s.title} />
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                {activeCardId === "messages" && (
                  <div className="space-y-4">
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm relative">
                      {refreshing && (
                        <div className="absolute top-3 right-3 flex items-center gap-1 text-[11px] text-app-text-secondary">
                          <RefreshCw size={12} className="animate-spin" /> Actualizando…
                        </div>
                      )}
                      <div className="text-sm font-bold text-app-text">Mensajes</div>
                      <div className="mt-2 h-[440px]">
                        {mensajeSub === "steps" && (
                          <HistBox queryFile="metrics/messages/steps_per_message.sql" valueColumn="steps" title="Steps por mensaje" timeRange={timeRange} />
                        )}
                        {mensajeSub === "tokens_entrada" && (
                          <HistBox queryFile="metrics/messages/input_tokens_per_message.sql" valueColumn="input_tokens" title="Tokens de entrada por mensaje" timeRange={timeRange} />
                        )}
                        {mensajeSub === "tokens_salida" && (
                          <HistBox queryFile="metrics/messages/output_tokens_per_message.sql" valueColumn="output_tokens" title="Tokens de salida por mensaje" timeRange={timeRange} />
                        )}
                        {mensajeSub === "tiempo" && (
                          <HistBox queryFile="metrics/messages/time_per_message.sql" valueColumn="total_time" title="Tiempo por mensaje" timeRange={timeRange} />
                        )}
                        {mensajeSub === "latencia" && (
                          <HistBox queryFile="metrics/messages/latency_per_message.sql" valueColumn="latency" title="Latencia por mensaje" timeRange={timeRange} percentiles />
                        )}
                      </div>
                    </div>
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm">
                      <div className="flex flex-wrap gap-2">
                        {MENSAJES_SUBS.map((s) => (
                          <SubCard key={s.id} id={s.id} selectedId={mensajeSub} onSelect={setMensajeSub} title={s.title} />
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                {activeCardId === "tools" && (
                  <div className="space-y-4">
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm relative">
                      {refreshing && (
                        <div className="absolute top-3 right-3 flex items-center gap-1 text-[11px] text-app-text-secondary">
                          <RefreshCw size={12} className="animate-spin" /> Actualizando…
                        </div>
                      )}
                      <div className="text-sm font-bold text-app-text">Herramientas</div>
                      <div className="mt-1 flex flex-wrap gap-4 text-xs text-app-text-secondary">
                        <span>Total: <span className="font-bold text-app-text">{formatNumber(tls?.total_tool_calls ?? 0)}</span></span>
                        <span>Promedio por llamada: <span className="font-bold text-app-text">{(tls?.avg_time_per_tool_call ?? 0).toFixed(2)}s</span></span>
                      </div>
                      <div className="mt-2 h-[440px]">
                        {toolsSub === "llamadas" && (
                          <CatBox
                            title="Llamadas a herramientas"
                            data={(tls?.tool_usage ?? []).map((t) => ({ name: t.name, value: t.count }))}
                            onDownload={() =>
                              downloadJson(tls?.tool_usage ?? [], "llamadas_herramientas")
                            }
                          />
                        )}
                        {toolsSub === "tiempo_distribucion" && (
                          <HistBox queryFile="metrics/tools/time_per_tool_call.sql" valueColumn="total_time" title="Tiempo por llamada de herramienta" timeRange={timeRange} />
                        )}
                        {toolsSub === "tiempo_promedio" && (
                          <CatBox
                            title="Tiempo promedio por herramienta"
                            data={(tls?.tool_usage ?? []).map((t) => ({ name: t.name, value: t.avg_time }))}
                            valueFormatter={(v) => `${v.toFixed(2)}s`}
                            onDownload={() =>
                              downloadJson(tls?.tool_usage ?? [], "tiempo_promedio")
                            }
                          />
                        )}
                        {toolsSub === "subagentes" && (
                          <CatBox
                            title="Subagentes"
                            data={(tls?.top_subagents ?? []).map((s) => ({ name: s.name, value: s.count }))}
                            onDownload={() =>
                              downloadJson(tls?.top_subagents ?? [], "subagentes")
                            }
                          />
                        )}
                      </div>
                    </div>
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm">
                      <div className="flex flex-wrap gap-2">
                        {TOOLS_SUBS.map((s) => (
                          <SubCard key={s.id} id={s.id} selectedId={toolsSub} onSelect={setToolsSub} title={s.title} />
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                {activeCardId === "models" && (
                  <div className="space-y-4">
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm relative">
                      {refreshing && (
                        <div className="absolute top-3 right-3 flex items-center gap-1 text-[11px] text-app-text-secondary">
                          <RefreshCw size={12} className="animate-spin" /> Actualizando…
                        </div>
                      )}
                      <div className="text-sm font-bold text-app-text">Modelos</div>
                      <div className="mt-1 flex flex-wrap gap-4 text-xs text-app-text-secondary">
                        <span>Total llamadas: <span className="font-bold text-app-text">{formatNumber(mdl?.total_model_calls ?? 0)}</span></span>
                        <span>Modelos: <span className="font-bold text-app-text">{formatNumber(mdl?.total_models ?? 0)}</span></span>
                      </div>
                      <div className="mt-2 h-[440px]">
                        {modelsSub === "llamadas" && (
                          <CatBox
                            title="Llamadas por modelo"
                            data={(mdl?.models ?? [])
                              .filter(
                                (r) =>
                                  !selectedModel ||
                                  (r.provider === selectedModel.provider &&
                                    r.model === selectedModel.model),
                              )
                              .map((r) => ({
                                name: `${r.provider}/${r.model}`,
                                value: r.count,
                              }))}
                            showModelDropdown
                            models={mdl?.models ?? []}
                            selectedModel={selectedModel}
                            onSelectModel={setSelectedModel}
                            onDownload={() =>
                              downloadJson(mdl?.models ?? [], "llamadas_modelo")
                            }
                          />
                        )}
                        {modelsSub === "tokens_entrada" && (
                          <HistBox
                            queryFile="metrics/models/tokens_input_per_turn.sql"
                            valueColumn="value"
                            title="Tokens de entrada"
                            timeRange={timeRange}
                            model={selectedModel?.model}
                            provider={selectedModel?.provider}
                            models={mdl?.tokens_input ?? []}
                            selectedModel={selectedModel}
                            onSelectModel={setSelectedModel}
                          />
                        )}
                        {modelsSub === "tokens_salida" && (
                          <HistBox
                            queryFile="metrics/models/tokens_output_per_turn.sql"
                            valueColumn="value"
                            title="Tokens de salida"
                            timeRange={timeRange}
                            model={selectedModel?.model}
                            provider={selectedModel?.provider}
                            models={mdl?.tokens_output ?? []}
                            selectedModel={selectedModel}
                            onSelectModel={setSelectedModel}
                          />
                        )}
                        {modelsSub === "llamadas_herramientas" && (
                          <CatBox
                            title="Llamadas a herramientas"
                            data={(mdl?.tool_calls ?? [])
                              .filter(
                                (r) =>
                                  !selectedModel ||
                                  (r.provider === selectedModel.provider &&
                                    r.model === selectedModel.model),
                              )
                              .map((r) => ({
                                name: `${r.provider}/${r.model}`,
                                value: r.value,
                              }))}
                            showModelDropdown
                            models={mdl?.tool_calls ?? []}
                            selectedModel={selectedModel}
                            onSelectModel={setSelectedModel}
                            onDownload={() =>
                              downloadJson(mdl?.tool_calls ?? [], "llamadas_herramientas")
                            }
                          />
                        )}
                        {modelsSub === "latencia" && (
                          <HistBox
                            queryFile="metrics/models/latency_per_turn.sql"
                            valueColumn="latency"
                            title="Latencia por turno"
                            timeRange={timeRange}
                            model={selectedModel?.model}
                            provider={selectedModel?.provider}
                            models={mdl?.latency_models ?? []}
                            selectedModel={selectedModel}
                            onSelectModel={setSelectedModel}
                          />
                        )}
                      </div>
                    </div>
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm">
                      <div className="flex flex-wrap gap-2">
                        {MODELS_SUBS.map((s) => (
                          <SubCard key={s.id} id={s.id} selectedId={modelsSub} onSelect={setModelsSub} title={s.title} />
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                {activeCardId === "spend" && (
                  <div className="space-y-4">
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm relative">
                      {refreshing && (
                        <div className="absolute top-3 right-3 flex items-center gap-1 text-[11px] text-app-text-secondary">
                          <RefreshCw size={12} className="animate-spin" /> Actualizando…
                        </div>
                      )}
                      <div className="text-sm font-bold text-app-text">Gasto</div>
                      <div className="mt-1 flex flex-wrap gap-4 text-xs text-app-text-secondary">
                        <span>Total: <span className="font-bold text-app-text">${(cts?.total_cost ?? 0).toFixed(2)}</span></span>
                        <span>Entrada: <span className="font-bold text-app-text">${(cts?.total_input ?? 0).toFixed(2)}</span></span>
                        <span>Salida: <span className="font-bold text-app-text">${(cts?.total_output ?? 0).toFixed(2)}</span></span>
                      </div>
                      <div className="mt-2 h-[440px]">
                        {costsSub === "total" && (
                          <CatBox
                            title="Costo total"
                            data={(cts?.cost_by_model ?? [])
                              .filter((r) => !selectedCostModel || (r.provider === selectedCostModel.provider && r.model === selectedCostModel.model))
                              .map((r) => ({ name: `${r.provider}/${r.model}`, value: r.total }))}
                            valueFormatter={(v) => `$${v.toFixed(2)}`}
                            showModelDropdown
                            models={cts?.cost_by_model ?? []}
                            selectedModel={selectedCostModel}
                            onSelectModel={setSelectedCostModel}
                            onDownload={() =>
                              downloadJson(cts?.cost_by_model ?? [], "costo_total")
                            }
                          />
                        )}
                        {costsSub === "por_sesion" && (
                          <HistBox
                            queryFile="metrics/costs/cost_per_session.sql"
                            valueColumn="value"
                            title="Costo por sesión"
                            timeRange={timeRange}
                            model={selectedCostModel?.model}
                            provider={selectedCostModel?.provider}
                            models={cts?.cost_by_model ?? []}
                            selectedModel={selectedCostModel}
                            onSelectModel={setSelectedCostModel}
                          />
                        )}
                        {costsSub === "por_turno" && (
                          <HistBox
                            queryFile="metrics/costs/cost_per_turn.sql"
                            valueColumn="value"
                            title="Costo por turno"
                            timeRange={timeRange}
                            model={selectedCostModel?.model}
                            provider={selectedCostModel?.provider}
                            models={cts?.cost_by_model ?? []}
                            selectedModel={selectedCostModel}
                            onSelectModel={setSelectedCostModel}
                          />
                        )}
                      </div>
                    </div>
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm">
                      <div className="flex flex-wrap gap-2">
                        {COSTS_SUBS.map((s) => (
                          <SubCard key={s.id} id={s.id} selectedId={costsSub} onSelect={setCostsSub} title={s.title} />
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                {activeCardId === "errors" && (
                  <div className="space-y-4">
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm relative">
                      {refreshing && (
                        <div className="absolute top-3 right-3 flex items-center gap-1 text-[11px] text-app-text-secondary">
                          <RefreshCw size={12} className="animate-spin" /> Actualizando…
                        </div>
                      )}
                      <div className="text-sm font-bold text-app-text">Errores del agente</div>
                      <div className="mt-1 flex flex-wrap gap-4 text-xs text-app-text-secondary">
                        <span>Total: <span className="font-bold text-app-text">{formatNumber(errs?.total_errors ?? 0)}</span></span>
                      </div>
                      <div className="mt-2 h-[440px]">
                        {errorsSub === "por_modelo" && (
                          <CatBox
                            title="Errores por modelo"
                            data={(errs?.errors_by_model ?? [])
                              .filter((r) => !selectedErrorModel || (r.provider === selectedErrorModel.provider && r.model === selectedErrorModel.model))
                              .map((r) => ({ name: `${r.provider}/${r.model}`, value: r.count }))}
                            showModelDropdown
                            models={errs?.errors_by_model ?? []}
                            selectedModel={selectedErrorModel}
                            onSelectModel={setSelectedErrorModel}
                            onDownload={() =>
                              downloadJson(errs?.errors_by_model ?? [], "errores_modelo")
                            }
                          />
                        )}
                        {errorsSub === "por_sesion" && (
                          <HistBox
                            queryFile="metrics/agent_errors/per_session.sql"
                            valueColumn="value"
                            title="Errores por sesión"
                            timeRange={timeRange}
                            model={selectedErrorModel?.model}
                            provider={selectedErrorModel?.provider}
                            models={errs?.errors_by_model ?? []}
                            selectedModel={selectedErrorModel}
                            onSelectModel={setSelectedErrorModel}
                          />
                        )}
                        {errorsSub === "por_turno" && (
                          <HistBox
                            queryFile="metrics/agent_errors/per_turn.sql"
                            valueColumn="value"
                            title="Errores por turno"
                            timeRange={timeRange}
                            model={selectedErrorModel?.model}
                            provider={selectedErrorModel?.provider}
                            models={errs?.errors_by_model ?? []}
                            selectedModel={selectedErrorModel}
                            onSelectModel={setSelectedErrorModel}
                          />
                        )}
                        {errorsSub === "por_herramienta" && (
                          <CatBox
                            title="Errores por herramienta"
                            data={(errs?.errors_by_tool ?? [])
                              .filter((r) => !selectedErrorTool || r.tool === selectedErrorTool)
                              .map((r) => ({ name: r.tool, value: r.count }))}
                            showToolDropdown
                            tools={errs?.errors_by_tool ?? []}
                            selectedTool={selectedErrorTool}
                            onSelectTool={setSelectedErrorTool}
                            onDownload={() =>
                              downloadJson(errs?.errors_by_tool ?? [], "errores_herramienta")
                            }
                          />
                        )}
                      </div>
                    </div>
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm">
                      <div className="flex flex-wrap gap-2">
                        {ERRORS_SUBS.map((s) => (
                          <SubCard key={s.id} id={s.id} selectedId={errorsSub} onSelect={setErrorsSub} title={s.title} />
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                {activeCardId === "workflows" && (
                  <div className="space-y-4">
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm relative">
                      {refreshing && (
                        <div className="absolute top-3 right-3 flex items-center gap-1 text-[11px] text-app-text-secondary">
                          <RefreshCw size={12} className="animate-spin" /> Actualizando…
                        </div>
                      )}
                      <div className="text-sm font-bold text-app-text">Workflows</div>
                      <div className="mt-1 flex flex-wrap gap-4 text-xs text-app-text-secondary">
                        <span>Total corridas: <span className="font-bold text-app-text">{formatNumber(metrics.workflows?.total_runs ?? 0)}</span></span>
                      </div>
                      <div className="mt-2 h-[440px]">
                        {workflowsSub === "por_workflow" && (
                          <CatBox
                            title="Corridas por workflow"
                            data={(metrics.workflows?.by_workflow ?? []).map((r) => ({ name: r.name, value: r.count }))}
                            onDownload={() => downloadJson(metrics.workflows?.by_workflow ?? [], "workflows_por_workflow")}
                          />
                        )}
                        {workflowsSub === "por_fuente" && (
                          <CatBox
                            title="Corridas por fuente"
                            data={(metrics.workflows?.by_source ?? []).map((r) => ({ name: r.name, value: r.count }))}
                            onDownload={() => downloadJson(metrics.workflows?.by_source ?? [], "workflows_por_fuente")}
                          />
                        )}
                        {workflowsSub === "por_estado" && (
                          <CatBox
                            title="Corridas por estado"
                            data={(metrics.workflows?.by_status ?? []).map((r) => ({ name: r.name, value: r.count }))}
                            onDownload={() => downloadJson(metrics.workflows?.by_status ?? [], "workflows_por_estado")}
                          />
                        )}
                        {workflowsSub === "costo" && (
                          <HistBox queryFile="metrics/workflows/cost_per_run.sql" valueColumn="value" title="Costo por corrida" timeRange={timeRange} filterColumn="started_at" />
                        )}
                        {workflowsSub === "tiempo" && (
                          <HistBox queryFile="metrics/workflows/time_per_run.sql" valueColumn="value" title="Tiempo por corrida" timeRange={timeRange} filterColumn="started_at" />
                        )}
                        {workflowsSub === "tokens" && (
                          <HistBox queryFile="metrics/workflows/tokens_per_run.sql" valueColumn="value" title="Tokens por corrida" timeRange={timeRange} filterColumn="started_at" />
                        )}
                      </div>
                    </div>
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm">
                      <div className="flex flex-wrap gap-2">
                        {WORKFLOWS_SUBS.map((s) => (
                          <SubCard key={s.id} id={s.id} selectedId={workflowsSub} onSelect={setWorkflowsSub} title={s.title} />
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                {activeCardId === "creators" && (
                  <div className="space-y-4">
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm relative">
                      {refreshing && (
                        <div className="absolute top-3 right-3 flex items-center gap-1 text-[11px] text-app-text-secondary">
                          <RefreshCw size={12} className="animate-spin" /> Actualizando…
                        </div>
                      )}
                      <div className="text-sm font-bold text-app-text">Creadores</div>
                      <div className="mt-1 flex flex-wrap gap-4 text-xs text-app-text-secondary">
                        <span>Total pedidos: <span className="font-bold text-app-text">{formatNumber(metrics.creators?.total_requests ?? 0)}</span></span>
                      </div>
                      <div className="mt-2 h-[440px]">
                        {creatorsSub === "por_tipo" && (
                          <CatBox
                            title="Pedidos por tipo"
                            data={(metrics.creators?.by_kind ?? []).map((r) => ({ name: r.name, value: r.count }))}
                            onDownload={() => downloadJson(metrics.creators?.by_kind ?? [], "creadores_por_tipo")}
                          />
                        )}
                        {creatorsSub === "por_estado" && (
                          <CatBox
                            title="Pedidos por estado"
                            data={(metrics.creators?.by_status ?? []).map((r) => ({ name: r.name, value: r.count }))}
                            onDownload={() => downloadJson(metrics.creators?.by_status ?? [], "creadores_por_estado")}
                          />
                        )}
                        {creatorsSub === "costo" && (
                          <HistBox queryFile="metrics/creators/cost_per_request.sql" valueColumn="value" title="Costo por pedido" timeRange={timeRange} filterColumn="created_at" />
                        )}
                        {creatorsSub === "tiempo" && (
                          <HistBox queryFile="metrics/creators/time_per_request.sql" valueColumn="value" title="Tiempo por pedido" timeRange={timeRange} filterColumn="created_at" />
                        )}
                        {creatorsSub === "tokens" && (
                          <HistBox queryFile="metrics/creators/tokens_per_request.sql" valueColumn="value" title="Tokens por pedido" timeRange={timeRange} filterColumn="created_at" />
                        )}
                      </div>
                    </div>
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm">
                      <div className="flex flex-wrap gap-2">
                        {CREATORS_SUBS.map((s) => (
                          <SubCard key={s.id} id={s.id} selectedId={creatorsSub} onSelect={setCreatorsSub} title={s.title} />
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                {activeCardId === "feedback" && (
                  <div className="space-y-4">
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm relative">
                      {refreshing && (
                        <div className="absolute top-3 right-3 flex items-center gap-1 text-[11px] text-app-text-secondary">
                          <RefreshCw size={12} className="animate-spin" /> Actualizando…
                        </div>
                      )}
                      <div className="text-sm font-bold text-app-text">Calidad de respuestas</div>
                      <div className="mt-1 flex flex-wrap gap-4 text-xs text-app-text-secondary">
                        <span>Total votos: <span className="font-bold text-app-text">{formatNumber(metrics.feedback?.total ?? 0)}</span></span>
                        <span>Positivos: <span className="font-bold text-app-text">{formatNumber(metrics.feedback?.up ?? 0)}</span></span>
                        <span>Negativos: <span className="font-bold text-app-text">{formatNumber(metrics.feedback?.down ?? 0)}</span></span>
                        <span>Calidad: <span className="font-bold text-app-text">{(metrics.feedback?.quality_rate ?? 0).toFixed(1)}%</span></span>
                      </div>
                      <div className="mt-2 h-[440px]">
                        {feedbackSub === "por_tipo" && (
                          <CatBox
                            title="Votos por tipo"
                            data={(metrics.feedback?.by_type ?? []).map((r) => ({ name: r.name, value: r.count }))}
                            onDownload={() => downloadJson(metrics.feedback?.by_type ?? [], "calidad_por_tipo")}
                          />
                        )}
                        {feedbackSub === "por_modelo" && (
                          <CatBox
                            title="Votos por modelo"
                            data={(metrics.feedback?.by_model ?? []).map((r) => ({ name: `${r.provider}/${r.model} (${r.type})`, value: r.count }))}
                            onDownload={() => downloadJson(metrics.feedback?.by_model ?? [], "calidad_por_modelo")}
                          />
                        )}
                      </div>
                    </div>
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm">
                      <div className="flex flex-wrap gap-2">
                        {FEEDBACK_SUBS.map((s) => (
                          <SubCard key={s.id} id={s.id} selectedId={feedbackSub} onSelect={setFeedbackSub} title={s.title} />
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </main>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-app-border px-6 py-3 bg-white">
          <button
            onClick={loadAll}
            disabled={loading || refreshing}
            className="flex items-center gap-2 px-3.5 py-2 text-xs font-medium rounded-lg border border-app-border text-app-text hover:bg-app-bg-secondary transition-colors shadow-sm"
          >
            <RefreshCw size={14} className={loading || refreshing ? "animate-spin" : ""} />
            Actualizar métricas
          </button>
          <button
            onClick={onClose}
            className="px-5 py-2 text-xs font-medium rounded-lg bg-[var(--color-app-primary)] text-white hover:opacity-90 transition-opacity shadow-sm"
          >
            Cerrar
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default MetricsModal;
