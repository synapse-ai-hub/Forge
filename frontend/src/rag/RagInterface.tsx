import { useCallback, useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { Database, Plus, Trash2, Upload, Link2, FolderOpen, FileText, Globe } from "lucide-react";
import { configService } from "../services/configService";
import { API_BASE_URL } from "../config/api";
import { Collapsible } from "../components/ui/collapsible";
import { Button } from "../components/ui/button";

const API = API_BASE_URL + "/api";

const ALLOWED_EXTENSIONS = /\.(pdf|txt|md|docx|doc|csv|xlsx|xls|json|xml|yaml|yml|py)$/i;
const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50 MB por archivo

/** Colección tal como la devuelve el backend. */
interface Collection {
  name: string;
  metadata?: Record<string, any> | null;
  count?: number;
}

/** Fuente de una colección: un archivo, una página web u otro origen. */
interface Source {
  kind: "file" | "url" | "other";
  name: string;
  chunks: number;
}

/** Resultado de procesar un archivo o URL. */
interface ProcessedItem {
  filename?: string;
  url?: string;
  chunks?: number;
  error?: string;
}

export function RagInterface() {
  /* ---- state ---- */
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Crear colección
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  // Colección seleccionada
  const [selected, setSelected] = useState<string | null>(null);

  // Fuentes de la colección seleccionada
  const [sources, setSources] = useState<Source[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourcesError, setSourcesError] = useState<string | null>(null);

  // Archivos
  const [files, setFiles] = useState<File[]>([]);
  const [fileWarning, setFileWarning] = useState<string | null>(null);

  // URL
  const [url, setUrl] = useState("");

  // Procesamiento
  const [processing, setProcessing] = useState(false);
  const [resultMsg, setResultMsg] = useState<string | null>(null);
  const [resultType, setResultType] = useState<"success" | "error" | null>(null);

  // Configuración de chunking (aplica a archivos y URLs).
  // Los borradores solo toman efecto al presionar "Aplicar".
  const [chunkDraft, setChunkDraft] = useState("500");
  const [overlapDraft, setOverlapDraft] = useState("60");
  const [appliedChunk, setAppliedChunk] = useState(500);
  const [appliedOverlap, setAppliedOverlap] = useState(60);

  const handleApplyChunking = useCallback(() => {
    const size = Number(chunkDraft);
    const ov = Number(overlapDraft);
    if (!Number.isInteger(size) || size <= 0) {
      setResultType("error");
      setResultMsg("El tamaño de chunk debe ser un entero mayor a 0.");
      return;
    }
    if (!Number.isInteger(ov) || ov < 0) {
      setResultType("error");
      setResultMsg("El overlap debe ser un entero mayor o igual a 0.");
      return;
    }
    setAppliedChunk(size);
    setAppliedOverlap(ov);
    setResultType(null);
    setResultMsg(null);
  }, [chunkDraft, overlapDraft]);

  /* ---- bloqueo: la fuente de conocimiento necesita la clave de Google Gemini ---- */
  const [ragBlocked, setRagBlocked] = useState<boolean | null>(null);
  useEffect(() => {
    let cancelled = false;
    configService
      .getProviderKeys()
      .then((data) => {
        if (cancelled) return;
        const google = (data.keys || []).find((k) => k.provider === "google");
        setRagBlocked(!(google && google.configured));
      })
      .catch(() => {
        if (!cancelled) setRagBlocked(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /* ---- heartbeat (el watchdog del backend mata el server sin heartbeat) ---- */
  useEffect(() => {
    const interval = setInterval(() => {
      fetch(`${API}/heartbeat`, { method: "POST", keepalive: true }).catch(() => {});
    }, 10000);
    fetch(`${API}/heartbeat`, { method: "POST", keepalive: true }).catch(() => {});
    return () => clearInterval(interval);
  }, []);

  /* ---- cargar colecciones ---- */
  const loadCollections = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${API}/rag/collections`);
      const data = await resp.json();
      if (data.status === "success") {
        setCollections(data.data?.collections || []);
      } else {
        setError(data.message || "Error al listar colecciones.");
      }
    } catch (e) {
      setError("Error de conexión: " + ((e as Error)?.message || "Error desconocido"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCollections();
  }, [loadCollections]);

  /* ---- fuentes de la colección seleccionada ----
     Se recargan al cambiar de colección y cada vez que se recarga la lista
     (después de subir, agregar o borrar). */
  useEffect(() => {
    if (!selected) {
      setSources([]);
      setSourcesError(null);
      return;
    }
    let cancelled = false;
    setSourcesLoading(true);
    fetch(`${API}/rag/collections/${encodeURIComponent(selected)}/sources`)
      .then((resp) => resp.json())
      .then((data) => {
        if (cancelled) return;
        if (data.status === "success") {
          setSources(data.data?.sources || []);
          setSourcesError(null);
        } else {
          setSources([]);
          setSourcesError(data.message || "Error al listar las fuentes.");
        }
      })
      .catch((e) => {
        if (cancelled) return;
        setSources([]);
        setSourcesError("Error de conexión: " + ((e as Error)?.message || "Error desconocido"));
      })
      .finally(() => {
        if (!cancelled) setSourcesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected, collections]);

  /* ---- eliminar una fuente ---- */
  const handleDeleteSource = useCallback(
    async (source: Source) => {
      if (!selected) return;
      const label = source.kind === "other" ? "las fuentes sin origen" : `"${source.name}"`;
      if (!window.confirm(`¿Eliminar ${label} (${source.chunks} chunks) de "${selected}"?`)) return;
      try {
        const query = new URLSearchParams({ kind: source.kind, source: source.name });
        const resp = await fetch(
          `${API}/rag/collections/${encodeURIComponent(selected)}/sources?${query.toString()}`,
          { method: "DELETE" },
        );
        const data = await resp.json();
        if (data.status === "success") {
          setResultType("success");
          setResultMsg(data.message || "Fuente eliminada.");
          await loadCollections();
        } else {
          setResultType("error");
          setResultMsg(data.message || "Error al eliminar la fuente.");
        }
      } catch (e) {
        setResultType("error");
        setResultMsg("Error de conexión: " + ((e as Error)?.message || "Error desconocido"));
      }
    },
    [selected, loadCollections],
  );

  /* ---- crear colección ---- */
  const handleCreate = useCallback(
    async (e: FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (ragBlocked) return;
      setCreateError(null);
      const name = newName.trim();
      if (!name) {
        setCreateError("El nombre de la colección es obligatorio.");
        return;
      }
      setCreating(true);
      try {
        const resp = await fetch(`${API}/rag/collections`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, description: newDescription.trim() || null }),
        });
        const data = await resp.json();
        if (data.status === "success") {
          setNewName("");
          setNewDescription("");
          await loadCollections();
          setSelected(name);
        } else {
          setCreateError(data.message || "Error al crear la colección.");
        }
      } catch (e) {
        setCreateError("Error de conexión: " + ((e as Error)?.message || "Error desconocido"));
      } finally {
        setCreating(false);
      }
    },
    [newName, newDescription, loadCollections, ragBlocked],
  );

  /* ---- eliminar colección ---- */
  const handleDelete = useCallback(
    async (name: string) => {
      if (!window.confirm(`¿Eliminar la colección "${name}" y todos sus datos?`)) return;
      try {
        const resp = await fetch(`${API}/rag/collections/${encodeURIComponent(name)}`, {
          method: "DELETE",
        });
        const data = await resp.json();
        if (data.status === "success") {
          if (selected === name) setSelected(null);
          await loadCollections();
        } else {
          setError(data.message || "Error al eliminar la colección.");
        }
      } catch (e) {
        setError("Error de conexión: " + ((e as Error)?.message || "Error desconocido"));
      }
    },
    [selected, loadCollections],
  );

  /* ---- selección de archivos ---- */
  const addFiles = useCallback((incoming: File[]) => {
    const valid: File[] = [];
    let warning: string | null = null;
    for (const f of incoming) {
      if (!ALLOWED_EXTENSIONS.test(f.name)) {
        warning = `Tipo de archivo no soportado: ${f.name}. Permitidos: PDF, TXT, MD, DOCX, DOC, CSV, XLSX, XLS, JSON, XML, YAML, PY.`;
        continue;
      }
      if (f.size > MAX_FILE_SIZE) {
        warning = `Archivo demasiado grande: ${f.name} (máx 50 MB).`;
        continue;
      }
      valid.push(f);
    }
    if (warning) setFileWarning(warning);
    setFiles((prev) => [...prev, ...valid]);
  }, []);

  const handleFilesSelected = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      addFiles(Array.from(e.target.files || []));
      e.target.value = "";
    },
    [addFiles],
  );

  const removeFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  /* ---- auto-dismiss warning ---- */
  useEffect(() => {
    if (!fileWarning) return;
    const timer = setTimeout(() => setFileWarning(null), 6000);
    return () => clearTimeout(timer);
  }, [fileWarning]);

  /* ---- subir archivos ---- */
  const handleUploadFiles = useCallback(async () => {
    if (ragBlocked) return;
    if (!selected || files.length === 0) return;
    setProcessing(true);
    setResultMsg(null);
    setResultType(null);
    try {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      form.append("chunk_size", String(appliedChunk));
      form.append("overlap", String(appliedOverlap));
      const resp = await fetch(`${API}/rag/collections/${encodeURIComponent(selected)}/files`, {
        method: "POST",
        body: form,
      });
      const data = await resp.json();
      if (data.status === "success") {
        const processed: ProcessedItem[] = data.data?.processed || [];
        const errors: ProcessedItem[] = data.data?.errors || [];
        const okCount = processed.length;
        const errCount = errors.length;
        setResultType(errCount > 0 ? "error" : "success");
        setResultMsg(
          errCount > 0
            ? `${okCount} archivo(s) procesado(s), ${errCount} con error.`
            : `${okCount} archivo(s) procesado(s) en "${selected}".`,
        );
        setFiles([]);
        await loadCollections();
      } else {
        setResultType("error");
        setResultMsg(data.message || "Error al subir archivos.");
      }
    } catch (e) {
      setResultType("error");
      setResultMsg("Error de conexión: " + ((e as Error)?.message || "Error desconocido"));
    } finally {
      setProcessing(false);
    }
  }, [selected, files, loadCollections, ragBlocked, appliedChunk, appliedOverlap]);

  /* ---- agregar URL ---- */
  const handleAddUrl = useCallback(async () => {
    if (ragBlocked) return;
    const trimmed = url.trim();
    if (!selected || !trimmed) return;
    setProcessing(true);
    setResultMsg(null);
    setResultType(null);
    try {
      const resp = await fetch(`${API}/rag/collections/${encodeURIComponent(selected)}/urls`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: trimmed, chunk_size: appliedChunk, overlap: appliedOverlap }),
      });
      const data = await resp.json();
      if (data.status === "success") {
        setResultType("success");
        setResultMsg(`Página web agregada a "${selected}" (${data.data?.chunks ?? 0} chunks).`);
        setUrl("");
        await loadCollections();
      } else {
        setResultType("error");
        setResultMsg(data.message || "Error al agregar la URL.");
      }
    } catch (e) {
      setResultType("error");
      setResultMsg("Error de conexión: " + ((e as Error)?.message || "Error desconocido"));
    } finally {
      setProcessing(false);
    }
  }, [selected, url, loadCollections, ragBlocked, appliedChunk, appliedOverlap]);

  /* ---- render ---- */
  return (
    <div className="h-screen bg-app-bg flex flex-col overflow-hidden">
      {/* ========== HEADER (mismo estilo que SkillInterface) ========== */}
      <header
        className="flex items-center shrink-0 bg-white px-4 border-b border-gray-200"
        style={{ height: "95px" }}
      >
        <div className="sm:w-44"></div>
        <div className="flex-1 flex items-center justify-center gap-2 sm:gap-3">
          <img
            src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png"
            alt="Logo"
            className="h-9 sm:h-[95px] w-auto"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
          <span className="text-lg sm:text-2xl font-semibold" style={{ color: "#111827" }}>
            <span className="brand-word">synapseForge</span> — Base de conocimiento
          </span>
        </div>
        <div className="sm:w-44"></div>
      </header>

      <div className="flex-1 flex min-h-0">
        {/* ========== COLUMNA IZQUIERDA: colecciones ========== */}
        <aside className="w-72 shrink-0 border-r border-app-border bg-app-bg-secondary overflow-y-auto p-4 space-y-4">
          <div className="text-sm font-semibold text-app-text flex items-center gap-2">
            <Database size={15} className="text-app-primary" />
            Colecciones
          </div>

          {/* Crear colección */}
          <form onSubmit={handleCreate} className="space-y-2">
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Nombre (minúsculas, guiones)"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
            />
            <input
              type="text"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              placeholder="Descripción (opcional)"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
            />
            {createError && (
              <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {createError}
              </div>
            )}
            <button
              type="submit"
              disabled={creating || ragBlocked === true}
              className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-[#4f46e5] to-[#8b5cf6] text-white text-sm font-medium px-4 py-2 rounded-lg hover:opacity-90 disabled:opacity-50"
            >
              <Plus size={14} />
              {creating ? "Creando..." : "Crear colección"}
            </button>
          </form>

          {/* Lista de colecciones */}
          <div className="space-y-1">
            {loading && <p className="text-xs text-app-text-secondary">Cargando...</p>}
            {!loading && collections.length === 0 && (
              <p className="text-xs text-app-text-secondary">No hay colecciones todavía.</p>
            )}
            {collections.map((c) => (
              <div
                key={c.name}
                className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer border text-sm transition-colors ${
                  selected === c.name
                    ? "bg-app-primary/10 border-app-primary/30 text-app-primary"
                    : "bg-white border-app-border text-app-text hover:bg-app-bg-tertiary"
                }`}
                onClick={() => setSelected(c.name)}
              >
                <FolderOpen size={14} className="shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="truncate font-medium">{c.name}</div>
                  <div className="text-[11px] text-app-text-secondary">
                    {c.count ?? 0} chunk(s)
                  </div>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(c.name);
                  }}
                  className="opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-700"
                  title="Eliminar colección"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </aside>

        {/* ========== COLUMNA DERECHA: detalle de la colección ========== */}
        <main className="flex-1 min-w-0 overflow-y-auto p-6">
          {error && (
            <div className="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5">
              {error}
            </div>
          )}

          {ragBlocked && (
            <div className="mb-4 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 leading-relaxed">
              La <strong>fuente de conocimiento</strong> necesita una clave de{" "}
              <strong>Google Gemini</strong> para funcionar. Pod&eacute;s sacarla gratis en{" "}
              <a
                href="https://aistudio.google.com/apikey"
                target="_blank"
                rel="noopener noreferrer"
                className="text-app-primary underline"
              >
                aistudio.google.com/apikey
              </a>{" "}
              y cargarla en la app principal (Configuraci&oacute;n &rarr; Providers). Mientras no la cargues, esta secci&oacute;n queda deshabilitada.
            </div>
          )}

          {!selected ? (
            <div className="h-full flex items-center justify-center text-sm text-app-text-secondary">
              Seleccioná una colección para agregar contenido, o creá una nueva.
            </div>
          ) : (
            <div className="max-w-2xl mx-auto space-y-6">
              <div>
                <h2 className="text-lg font-semibold text-app-text">{selected}</h2>
                <p className="text-xs text-app-text-secondary">
                  Agregá archivos o páginas web. El contenido se chunkea y se guarda en la colección. Podés ver y eliminar cada fuente abajo.
                </p>
              </div>

              {/* Configuración de chunking (archivos y páginas web) */}
              <Collapsible title="Configuración de chunking">
                <p className="text-[11px] text-app-text-secondary mb-2">
                  Se aplica a archivos y páginas web al presionar "Aplicar". Sin aplicar, se usan los valores por defecto (500 / 60).
                </p>
                <div className="space-y-3">
                  <div>
                    <label className="text-xs text-app-text">Chunk</label>
                    <input
                      type="number"
                      min={1}
                      step={1}
                      value={chunkDraft}
                      onChange={(e) => setChunkDraft(e.target.value)}
                      title="Tamaño de cada fragmento en caracteres. Por defecto 500."
                      className="w-full rounded-lg border border-app-border bg-white px-2 py-1 text-xs text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary-light"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-app-text">Overlap</label>
                    <input
                      type="number"
                      min={0}
                      step={1}
                      value={overlapDraft}
                      onChange={(e) => setOverlapDraft(e.target.value)}
                      title="Caracteres que se repiten entre fragmentos consecutivos para no cortar el contexto. Por defecto 60."
                      className="w-full rounded-lg border border-app-border bg-white px-2 py-1 text-xs text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary-light"
                    />
                  </div>
                  <Button type="button" onClick={handleApplyChunking} variant="gradient" className="w-full">
                    Aplicar
                  </Button>
                </div>
              </Collapsible>

              {resultMsg && (
                <div
                  className={`text-sm rounded-lg px-4 py-2.5 border ${
                    resultType === "error"
                      ? "text-red-600 bg-red-50 border-red-200"
                      : "text-green-800 bg-green-50 border-green-200"
                  }`}
                >
                  {resultMsg}
                </div>
              )}

              {/* Fuentes de la colección */}
              <section className="space-y-2">
                <h3 className="text-sm font-medium text-app-text flex items-center gap-2">
                  <FolderOpen size={14} className="text-app-primary" />
                  Fuentes
                  {!sourcesLoading && (
                    <span className="text-xs font-normal text-app-text-secondary">({sources.length})</span>
                  )}
                </h3>
                {sourcesLoading && <p className="text-xs text-app-text-secondary">Cargando...</p>}
                {sourcesError && (
                  <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                    {sourcesError}
                  </div>
                )}
                {!sourcesLoading && !sourcesError && sources.length === 0 && (
                  <p className="text-xs text-app-text-secondary">
                    Esta colección todavía no tiene fuentes. Agregá archivos o páginas web.
                  </p>
                )}
                {sources.length > 0 && (
                  <ul className="space-y-1">
                    {sources.map((s) => (
                      <li
                        key={`${s.kind}:${s.name}`}
                        className="flex items-center gap-2 px-3 py-1.5 bg-white border border-gray-200 rounded-lg text-sm"
                      >
                        {s.kind === "url" ? (
                          <Globe size={14} className="shrink-0 text-app-primary" />
                        ) : (
                          <FileText size={14} className="shrink-0 text-app-primary" />
                        )}
                        <span className="truncate font-medium text-app-text" title={s.name}>
                          {s.kind === "other" ? "(sin origen)" : s.name}
                        </span>
                        <span className="shrink-0 text-gray-400 text-xs">{s.chunks} chunk(s)</span>
                        <button
                          type="button"
                          onClick={() => handleDeleteSource(s)}
                          className="ml-auto shrink-0 text-red-500 hover:text-red-700"
                          title="Eliminar fuente"
                        >
                          <Trash2 size={14} />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {/* Archivos */}
              <section className="space-y-2">
                <h3 className="text-sm font-medium text-app-text flex items-center gap-2">
                  <Upload size={14} className="text-app-primary" />
                  Archivos
                </h3>
                <label
                  className="block border-2 border-dashed border-gray-300 rounded-lg p-6 text-center cursor-pointer hover:border-indigo-400 transition-colors"
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    addFiles(Array.from(e.dataTransfer.files));
                  }}
                >
                  <p className="text-sm text-gray-500">
                    Arrastrá archivos acá o{" "}
                    <span className="text-indigo-600 font-medium">seleccioná</span>
                  </p>
                  <p className="text-xs text-gray-400 mt-1">PDF, TXT, MD, DOCX, CSV, XLSX, JSON, XML</p>
                  <input
                    type="file"
                    multiple
                    accept=".pdf,.txt,.md,.docx,.csv,.xlsx,.xls,.json,.xml,.yaml,.yml,.py"
                    className="hidden"
                    onChange={handleFilesSelected}
                  />
                </label>

                {fileWarning && (
                  <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                    {fileWarning}
                  </div>
                )}

                {files.length > 0 && (
                  <ul className="space-y-1">
                    {files.map((f, i) => (
                      <li
                        key={`${f.name}-${i}`}
                        className="flex items-center gap-2 px-3 py-1.5 bg-white border border-gray-200 rounded-lg text-sm"
                      >
                        <span className="text-indigo-600 font-medium truncate">{f.name}</span>
                        <span className="text-gray-400 text-xs">({(f.size / 1024).toFixed(1)} KB)</span>
                        <button
                          type="button"
                          onClick={() => removeFile(i)}
                          className="ml-auto text-red-500 hover:text-red-700 text-xs font-medium"
                        >
                          Quitar
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                <button
                  type="button"
                  onClick={handleUploadFiles}
                  disabled={processing || files.length === 0 || ragBlocked === true}
                  className="w-full bg-gradient-to-r from-[#4f46e5] to-[#8b5cf6] text-white text-sm font-medium px-4 py-2 rounded-lg hover:opacity-90 disabled:opacity-50"
                >
                  {processing ? "Procesando..." : "Subir archivos"}
                </button>
              </section>

              {/* Páginas web */}
              <section className="space-y-2">
                <h3 className="text-sm font-medium text-app-text flex items-center gap-2">
                  <Link2 size={14} className="text-app-primary" />
                  Páginas web
                </h3>
                <div className="flex gap-2">
                  <input
                    type="url"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://ejemplo.com/documento"
                    className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
                  />
                  <button
                    type="button"
                    onClick={handleAddUrl}
                    disabled={processing || !url.trim() || ragBlocked === true}
                    className="bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm font-medium px-4 py-2 rounded-lg transition-colors border border-gray-300 disabled:opacity-50"
                  >
                    Agregar
                  </button>
                </div>
              </section>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export default RagInterface;