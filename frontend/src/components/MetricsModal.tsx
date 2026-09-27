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
} from "lucide-react";
import metricsService, {
  type MetricsOverview,
  type SessionMetrics,
  type ToolMetrics,
  type ModelMetrics,
  type ErrorMetrics,
} from "../services/metricsService";

interface MetricsModalProps {
  open: boolean;
  onClose: () => void;
}

type TimeRange = "1h" | "6h" | "1d" | "1w" | "1m" | "all";

interface MetricsData {
  overview: MetricsOverview | null;
  sessions: SessionMetrics | null;
  tools: ToolMetrics | null;
  models: ModelMetrics | null;
  errors: ErrorMetrics | null;
}

const EMPTY_METRICS: MetricsData = {
  overview: null,
  sessions: null,
  tools: null,
  models: null,
  errors: null,
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

function formatSeconds(value: number): string {
  return `${value.toFixed(2)} s`;
}

/** Tarjeta del sidebar: solo selección, sin despliegue inline. */
function SidebarCard({
  id,
  activeId,
  onSelect,
  title,
  value,
  subtitle,
  icon,
  tone = "default",
}: {
  id: string;
  activeId: string | null;
  onSelect: (id: string) => void;
  title: string;
  value: string;
  subtitle?: string;
  icon: React.ReactNode;
  tone?: "default" | "error";
}) {
  const selected = activeId === id;

  return (
    <div
      onClick={() => onSelect(id)}
      className={`rounded-xl border transition-all duration-200 cursor-pointer bg-white p-3 shadow-sm hover:shadow-md w-full text-left ${
        selected
          ? "border-[var(--color-app-primary)] ring-2 ring-[var(--color-app-primary)]/20 shadow-md"
          : "border-app-border hover:border-[var(--color-app-primary)]/50"
      }`}
    >
      <div className="flex items-center gap-2 text-xs font-medium text-app-text-secondary">
        <span className="p-1.5 rounded-lg bg-app-bg-secondary text-[var(--color-app-primary)]">
          {icon}
        </span>
        <span className="truncate">{title}</span>
      </div>
      <div className="mt-2">
        <div
          className={`text-xl font-bold tracking-tight ${
            tone === "error" ? "text-app-error" : "text-app-text"
          }`}
        >
          {value}
        </div>
        {subtitle && (
          <div className="text-[11px] text-app-text-secondary mt-0.5 truncate" title={subtitle}>
            {subtitle}
          </div>
        )}
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
          <div className="flex gap-2 pt-1">
            {data.map((d, i) => (
              <div key={`${d.date}-${i}`} className="flex-1 min-w-0 text-center text-[10px] font-medium text-app-text-secondary truncate">
                {d.date}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Figura exacta de synapse_tools.eda.outliers renderizada en el backend (base64). */
function HistBox({
  queryFile,
  valueColumn,
  title,
  timeRange,
  onStats,
}: {
  queryFile: string;
  valueColumn: string;
  title: string;
  timeRange: string;
  onStats?: (stats: Record<string, number>) => void;
}) {
  const [image, setImage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lastImage = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    metricsService
      .getOutliersFigure({ query_file: queryFile, value_column: valueColumn, time_range: timeRange })
      .then((res) => {
        if (cancelled) return;
        lastImage.current = res.image;
        setImage(res.image);
        if (onStats) onStats(res.stats);
      })
      .catch((e) => {
        if (cancelled) return;
        lastImage.current = null;
        setImage(null);
        const msg = e instanceof Error ? e.message : "Error";
        setError(/no data/i.test(msg) ? "Sin datos para este rango" : msg);
      });
    return () => {
      cancelled = true;
    };
  }, [queryFile, valueColumn, timeRange]);

  const shown = image ?? lastImage.current;

  return (
    <div className="h-full flex flex-col gap-2">
      <div className="text-xs font-semibold text-app-text">{title}</div>
      <div className="flex-1 min-h-0 rounded-lg border border-app-border bg-white p-2 flex items-center justify-center">
        {shown ? (
          <img src={shown} alt={title} className="max-w-full max-h-full object-contain" />
        ) : error ? (
          <div className="text-xs text-app-text-secondary">{error}</div>
        ) : (
          <div className="text-xs text-app-text-secondary">Cargando…</div>
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

export function MetricsModal({ open, onClose }: MetricsModalProps) {
  const [timeRange, setTimeRange] = useState<TimeRange>("1m");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<MetricsData>(EMPTY_METRICS);
  const [activeCardId, setActiveCardId] = useState<string | null>(null);
  const [sesionSub, setSesionSub] = useState<string>("cantidad");
  const [latenciaStats, setLatenciaStats] = useState<Record<string, number>>({});

  const hasData = metrics.overview !== null || metrics.sessions !== null;

  const loadAll = async () => {
    const firstLoad = !hasData;
    if (firstLoad) setLoading(true);
    else setRefreshing(true);
    setError(null);
    try {
      const [overviewRes, sessionsRes, toolsRes, modelsRes, errorsRes] =
        await Promise.allSettled([
          metricsService.getOverview(timeRange),
          metricsService.getSessionMetrics(timeRange),
          metricsService.getToolMetrics(timeRange),
          metricsService.getModelMetrics(timeRange),
          metricsService.getErrorMetrics(timeRange),
        ]);

      setMetrics({
        overview: overviewRes.status === "fulfilled" ? overviewRes.value : null,
        sessions: sessionsRes.status === "fulfilled" ? sessionsRes.value : null,
        tools: toolsRes.status === "fulfilled" ? toolsRes.value : null,
        models: modelsRes.status === "fulfilled" ? modelsRes.value : null,
        errors: errorsRes.status === "fulfilled" ? errorsRes.value : null,
      });

      if (
        overviewRes.status === "rejected" &&
        sessionsRes.status === "rejected" &&
        toolsRes.status === "rejected" &&
        modelsRes.status === "rejected" &&
        errorsRes.status === "rejected"
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

  useEffect(() => {
    if (open) {
      setActiveCardId("sessions");
      setSesionSub("cantidad");
    }
  }, [open]);

  useEffect(() => {
    if (open) {
      loadAll();
    }
  }, [open, timeRange]);

  const ov = metrics.overview;
  const ses = metrics.sessions;
  const tls = metrics.tools;
  const errs = metrics.errors;

  const latenciaAvg = latenciaStats.mean ?? 0;

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
                  subtitle={`Mensajes: ${formatNumber(ov?.total_messages ?? ses?.total_messages ?? 0)}`}
                  icon={<MessageSquare size={16} />}
                />
                <SidebarCard
                  id="messages"
                  activeId={activeCardId}
                  onSelect={(id) => setActiveCardId(id)}
                  title="Mensajes"
                  value={formatNumber(ov?.total_messages ?? ses?.total_messages ?? 0)}
                  subtitle={`Sesiones: ${formatNumber(ov?.total_sessions ?? ses?.total_sessions ?? 0)}`}
                  icon={<Activity size={16} />}
                />
                <SidebarCard
                  id="tools"
                  activeId={activeCardId}
                  onSelect={(id) => setActiveCardId(id)}
                  title="Uso de herramientas"
                  value={formatNumber(tls?.total_tool_calls ?? 0)}
                  subtitle={`Herramientas distintas: ${(tls?.tool_usage?.length ?? ov?.top_tools?.length ?? 0)}`}
                  icon={<Wrench size={16} />}
                />
                <SidebarCard
                  id="spend"
                  activeId={activeCardId}
                  onSelect={(id) => setActiveCardId(id)}
                  title="Gasto"
                  value={`$${(ov?.total_cost ?? 0).toFixed(2)}`}
                  subtitle={`${formatNumber(ov?.total_tokens ?? 0)} tokens`}
                  icon={<DollarSign size={16} />}
                />
                <SidebarCard
                  id="errors"
                  activeId={activeCardId}
                  onSelect={(id) => setActiveCardId(id)}
                  title="Errores"
                  value={formatNumber(errs?.total_errors ?? ov?.total_errors ?? 0)}
                  subtitle={`Fallos: ${ov?.failed_turns_count ?? 0}`}
                  icon={<AlertCircle size={16} />}
                  tone="error"
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
                          <HistBox queryFile="metrics/sessions/latency_per_session.sql" valueColumn="avg_lat" title="Latencia promedio por sesión" timeRange={timeRange} onStats={setLatenciaStats} />
                        )}
                      </div>
                      {sesionSub === "latencia_promedio" && (
                        <div className="mt-2 flex gap-2 text-[11px] text-app-text-secondary">
                          <span className="px-2 py-1 rounded bg-app-bg-secondary border border-app-border">
                            Promedio {formatSeconds(latenciaAvg)}
                          </span>
                        </div>
                      )}
                    </div>
                    <div className="rounded-xl border border-app-border bg-white p-4 shadow-sm">
                      <div className="text-xs font-semibold text-app-text mb-2">Subtarjetas de Sesiones</div>
                      <div className="flex flex-wrap gap-2">
                        {SESIONES_SUBS.map((s) => (
                          <SubCard key={s.id} id={s.id} selectedId={sesionSub} onSelect={setSesionSub} title={s.title} />
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                {activeCardId !== "sessions" && (
                  <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-app-border bg-white p-6 text-xs text-app-text-secondary">
                    Visualización de {activeCardId} pendiente de definición paso a paso.
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
