import { useCallback, useEffect, useRef, useState, type ReactElement } from "react";
import configService, { type McpServerStatus } from "../services/configService";
import { ResourceCards } from "./ResourceCards";
import { EMPTY_SELECTION, type ResourceSelection } from "../utils/resourceSelection";

type SaveState = "idle" | "saving" | "saved" | "error";

/**
 * Sidebar "Router" tab: what the router may use, picked from dropdowns.
 *
 * @returns The router configuration panel.
 */
export function RouterTab(): ReactElement {
  const [selection, setSelection] = useState<ResourceSelection>(EMPTY_SELECTION);
  const [source, setSource] = useState<"db" | "floor">("floor");
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [saveError, setSaveError] = useState("");
  const [servers, setServers] = useState<McpServerStatus[]>([]);
  const [toggling, setToggling] = useState<string | null>(null);
  const [toggleError, setToggleError] = useState("");
  const [toolsKey, setToolsKey] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    let cancelled = false;
    configService
      .getRouter()
      .then((data) => {
        if (cancelled) return;
        setSelection({
          agentes: data.selection.agentes ?? [],
          tools: data.selection.tools ?? [],
          toolArgs: {},
          skills: data.selection.skills ?? [],
          rag: data.selection.rag ?? [],
        });
        setSource(data.source);
        setLoaded(true);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : "No se pudo cargar.");
        setLoaded(true);
      });
    configService
      .getMcp()
      .then((data) => {
        if (!cancelled) setServers(data.servers);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
      mounted.current = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  // Serialized saves: PUTs run one after another so a slow request can
  // never overwrite a newer one (last-write-wins in user order).
  const saveChain = useRef(Promise.resolve());

  const save = useCallback((next: ResourceSelection) => {
    setSaveState("saving");
    setSaveError("");
    saveChain.current = saveChain.current
      .then(() =>
        configService.saveRouter({ agentes: next.agentes, tools: next.tools, skills: next.skills, rag: next.rag })
      )
      .then(() => {
        if (!mounted.current) return;
        setSource("db");
        setSaveState("saved");
      })
      .catch((err: unknown) => {
        if (!mounted.current) return;
        setSaveError(err instanceof Error ? err.message : "No se pudo guardar.");
        setSaveState("error");
      });
  }, []);

  const change = useCallback(
    (next: ResourceSelection) => {
      setSelection(next);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => save(next), 800);
    },
    [save]
  );

  const toggleServer = useCallback(
    async (label: string, enabled: boolean) => {
      setToggling(label);
      setToggleError("");
      try {
        await configService.setMcpEnabled(label, enabled);
        const data = await configService.getMcp();
        if (!mounted.current) return;
        setServers(data.servers);
        // The tools dropdown lists what exists: refetch it after the toggle.
        setToolsKey((k) => k + 1);
      } catch (err: unknown) {
        if (!mounted.current) return;
        setToggleError(err instanceof Error ? err.message : "No se pudo cambiar el servidor.");
      } finally {
        if (mounted.current) setToggling(null);
      }
    },
    []
  );

  return (
    <div className="space-y-4 p-3">
      <div>
        <h3 className="text-sm font-semibold text-app-text">Router</h3>
        <p className="text-xs text-app-text-secondary mt-0.5">
          Qué puede usar el router. Se guarda solo y rige desde la próxima respuesta.
        </p>
      </div>

      {!loaded ? (
        <p className="text-xs text-app-text-secondary">Cargando...</p>
      ) : loadError ? (
        <p className="text-xs text-red-500">No se pudo cargar la configuración del router: {loadError}</p>
      ) : (
        <>
          {source !== "db" && (
            <p className="rounded-lg border border-app-border bg-app-bg-tertiary px-2 py-1.5 text-[11px] text-app-text-secondary">
              Todavía no guardaste: el router usa sus herramientas base.
            </p>
          )}
          <ResourceCards
            key={toolsKey}
            kinds={["agentes", "tools", "skills", "rag"]}
            selection={selection}
            onChange={change}
            idPrefix="router"
            includeMcp
            hideToolArgs
            intro="Lo que agregues es lo que el router puede usar. Si lo dejás vacío, usa sus herramientas base."
          />
          <p className="text-[11px] text-app-text-secondary" aria-live="polite">
            {saveState === "saving" && "Guardando..."}
            {saveState === "saved" && "Guardado."}
            {saveState === "error" && `Error: ${saveError}`}
          </p>
        </>
      )}

      <div className="space-y-1.5">
        <h4 className="text-xs font-semibold text-app-text">Servidores MCP</h4>
        <p className="text-[11px] text-app-text-secondary">
          Apagado = sus tools no existen (ni para el router ni para nadie).
        </p>
        {toggleError && (
          <p className="text-[11px] text-red-500" aria-live="polite">
            Error: {toggleError}
          </p>
        )}
        {servers.length === 0 && (
          <p className="text-[11px] text-app-text-secondary">No hay servidores MCP configurados.</p>
        )}
        {servers.length > 0 && (
          <div className="max-h-48 space-y-1.5 overflow-y-auto pr-1">
            {servers.map((server) => (
              <label
                key={server.label}
                className="flex items-center justify-between gap-2 rounded-lg border border-app-border px-2 py-1.5"
              >
                <span className="min-w-0">
                  <span className="block truncate text-xs font-medium text-app-text">{server.label}</span>
                  <span className="block text-[11px] text-app-text-secondary">{server.status}</span>
                </span>
                <input
                  type="checkbox"
                  checked={server.status !== "disabled"}
                  disabled={toggling === server.label}
                  onChange={(e) => toggleServer(server.label, e.target.checked)}
                  aria-label={`${server.label} activado`}
                />
              </label>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default RouterTab;
