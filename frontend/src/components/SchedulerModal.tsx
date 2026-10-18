import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "./ui/dialog";
import {
  AlarmClock,
  Plus,
  Trash2,
  Pencil,
  Clock,
  Check,
  X,
  Sparkles,
  ChevronDown,
  ChevronRight,
  Shield,
  Sliders,
  Repeat,
} from "lucide-react";
import schedulerService, {
  SchedulerTask,
  ScheduleSlot,
  TaskParameters,
  PermissionAction,
  ToolPermissions,
  CatalogItem,
  PermissionsCatalog,
} from "../services/schedulerService";

interface SchedulerModalProps {
  open: boolean;
  onClose: () => void;
}

const WEEKDAY_LABELS = ["D", "L", "M", "X", "J", "V", "S"];
const ALL_DAYS = [0, 1, 2, 3, 4, 5, 6];

/** Read the system timezone (no configuration needed). */
function getSystemTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "—";
  } catch {
    return "—";
  }
}

/** Format "HH:MM" plus the selected days as a human-readable schedule. */
function formatSchedule(time: string, days: number[]): string {
  const sorted = [...days].sort((a, b) => a - b);
  if (sorted.length === 7) return `Todos los días a las ${time}`;
  const labels = sorted.map((d) => WEEKDAY_LABELS[d]).join(" ");
  return `${labels} · ${time}`;
}

/** Toggle a day in a list. */
function toggleDayInList(list: number[], day: number): number[] {
  return list.includes(day) ? list.filter((d) => d !== day) : [...list, day];
}

interface DayPickerProps {
  days: number[];
  onChange: (days: number[]) => void;
  size?: "md" | "sm";
}

/** Weekday selector rendered as a row of round toggle buttons. */
function DayPicker({ days, onChange, size = "md" }: DayPickerProps) {
  const sizeClass = size === "sm" ? "w-6 h-6 text-[10px]" : "w-7 h-7 text-xs";
  return (
    <div className="flex items-center gap-1">
      {WEEKDAY_LABELS.map((label, day) => (
        <button
          key={day}
          type="button"
          onClick={() => onChange(toggleDayInList(days, day))}
          title="Día de la semana"
          className={`${sizeClass} rounded-full font-medium border transition-colors ${
            days.includes(day)
              ? "bg-app-primary text-white border-app-primary"
              : "bg-white text-gray-500 border-gray-300 hover:border-app-primary"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

interface PermissionCheckboxProps {
  name: string;
  description: string;
  checked: boolean;
  onChange: () => void;
}

/** Single permission toggle rendered as a pill checkbox. */
function PermissionCheckbox({ name, description, checked, onChange }: PermissionCheckboxProps) {
  return (
    <label
      className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded-lg border cursor-pointer transition-colors ${
        checked
          ? "bg-app-primary/10 border-app-primary text-app-primary"
          : "bg-white border-gray-300 text-gray-600 hover:border-app-primary"
      }`}
      title={description}
    >
      <input type="checkbox" checked={checked} onChange={onChange} className="sr-only" />
      {name}
    </label>
  );
}

interface CollapsibleSectionProps {
  open: boolean;
  onToggle: () => void;
  icon: ReactNode;
  label: string;
  count?: number;
  children: ReactNode;
}

/** Collapsible header with a chevron and an optional count badge. */
function CollapsibleSection({ open, onToggle, icon, label, count, children }: CollapsibleSectionProps) {
  return (
    <>
      <button
        type="button"
        onClick={onToggle}
        className="flex items-center gap-2 text-xs font-medium text-app-text-secondary hover:text-app-primary transition-colors"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {icon}
        {label}
        {count !== undefined && count > 0 && (
          <span className="bg-app-primary/10 text-app-primary text-[10px] px-1.5 py-0.5 rounded-full">
            {count}
          </span>
        )}
      </button>
      {open && children}
    </>
  );
}

export function SchedulerModal({ open, onClose }: SchedulerModalProps) {
  const [tasks, setTasks] = useState<SchedulerTask[]>([]);
  const [timezone] = useState<string>(getSystemTimezone);

  /* ---- permissions catalog ---- */
  const [catalog, setCatalog] = useState<PermissionsCatalog>({
    tools: [],
    skills: [],
    agents: [],
    workflows: [],
  });

  /* ---- add-task form ---- */
  const [newName, setNewName] = useState("");
  const [newPrompt, setNewPrompt] = useState("");
  const [newTime, setNewTime] = useState("09:00");
  const [newDays, setNewDays] = useState<number[]>(ALL_DAYS);
  const [newToolPerms, setNewToolPerms] = useState<Record<string, PermissionAction>>({});
  const [newSkillPerms, setNewSkillPerms] = useState<Record<string, PermissionAction>>({});
  /* Workflows the task may run through the `workflow` tool (grouped permission). */
  const [newWorkflowPerms, setNewWorkflowPerms] = useState<Record<string, PermissionAction>>({});
  const [newParams, setNewParams] = useState<TaskParameters>({});
  const [newRepetitions, setNewRepetitions] = useState<ScheduleSlot[]>([]);
  const [formError, setFormError] = useState<string | null>(null);

  /* ---- collapsibles state ---- */
  const [showPermissions, setShowPermissions] = useState(false);
  const [showParameters, setShowParameters] = useState(false);
  const [showRepetitions, setShowRepetitions] = useState(false);

  /* ---- inline schedule editing ---- */
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTime, setEditTime] = useState("09:00");
  const [editDays, setEditDays] = useState<number[]>(ALL_DAYS);
  const [editError, setEditError] = useState<string | null>(null);

  /* ---- save feedback ---- */
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  /* ---- prompt crafting ---- */
  const [craftingLoading, setCraftingLoading] = useState(false);
  const [craftError, setCraftError] = useState<string | null>(null);

  /* ---- reload tasks from the backend ---- */
  const reloadTasks = useCallback(async () => {
    try {
      setTasks(await schedulerService.getTasks());
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Error cargando las tareas.");
    }
  }, []);

  /* Load persisted tasks and catalog each time the modal opens */
  useEffect(() => {
    if (open) {
      setSavedMsg(null);
      setSaveError(null);
      setFormError(null);
      setCraftError(null);
      setEditingId(null);
      reloadTasks();
      // Load catalog in background (non-blocking).
      schedulerService.getPermissionsCatalog().then(setCatalog).catch(() => {});
    }
  }, [open, reloadTasks]);

  /* Auto-dismiss the saved confirmation */
  useEffect(() => {
    if (!savedMsg) return;
    const timer = setTimeout(() => setSavedMsg(null), 4000);
    return () => clearTimeout(timer);
  }, [savedMsg]);

  /* ---- global save: validate every task, then confirm ---- */
  const handleSaveAll = useCallback(() => {
    setSaveError(null);
    for (const task of tasks) {
      if (!task.prompt.trim()) {
        setSaveError("Hay tareas sin descripción.");
        return;
      }
      if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(task.time)) {
        setSaveError(`Horario inválido en: "${task.prompt.slice(0, 40)}".`);
        return;
      }
      if (task.days.length === 0) {
        setSaveError(`La tarea "${task.prompt.slice(0, 40)}" no tiene días seleccionados.`);
        return;
      }
    }
    setSavedMsg("Tareas guardadas correctamente.");
  }, [tasks]);

  /* ---- add task ---- */
  const handleAdd = useCallback(async () => {
    setFormError(null);
    const name = newName.trim();
    const prompt = newPrompt.trim();
    if (!name) {
      setFormError("El nombre de la tarea es obligatorio.");
      return;
    }
    if (!/^[a-z0-9][a-z0-9_-]*$/.test(name)) {
      setFormError("El nombre solo puede contener minúsculas, números, guiones y guiones bajos.");
      return;
    }
    if (!prompt) {
      setFormError("La tarea es obligatoria.");
      return;
    }
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(newTime)) {
      setFormError("Horario inválido.");
      return;
    }
    if (newDays.length === 0) {
      setFormError("Seleccioná al menos un día.");
      return;
    }
    try {
      const toolPerms: ToolPermissions = { ...newToolPerms };
      if (Object.keys(newWorkflowPerms).length > 0) {
        toolPerms.workflow = newWorkflowPerms;
      }
      const hasToolPerms = Object.keys(toolPerms).length > 0;
      const hasSkillPerms = Object.keys(newSkillPerms).length > 0;
      await schedulerService.createTask({
        name,
        prompt,
        time: newTime,
        days: [...newDays].sort((a, b) => a - b),
        tool_permissions: hasToolPerms ? toolPerms : null,
        skill_permissions: hasSkillPerms ? newSkillPerms : null,
        parameters: Object.keys(newParams).length > 0 ? newParams : null,
        repetitions: newRepetitions.length > 0 ? newRepetitions : null,
      });
      setNewName("");
      setNewPrompt("");
      setNewTime("09:00");
      setNewDays(ALL_DAYS);
      setNewToolPerms({});
      setNewSkillPerms({});
      setNewWorkflowPerms({});
      setNewParams({});
      setNewRepetitions([]);
      setShowPermissions(false);
      setShowParameters(false);
      setShowRepetitions(false);
      await reloadTasks();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "No se pudo crear la tarea.");
    }
  }, [newName, newPrompt, newTime, newDays, newToolPerms, newSkillPerms, newWorkflowPerms, newParams, newRepetitions, reloadTasks]);

  /* ---- craft prompt via LLM ---- */
  const handleCraftPrompt = useCallback(async () => {
    const raw = newPrompt.trim();
    if (!raw) {
      setCraftError("Escribí una descripción primero.");
      return;
    }
    setCraftingLoading(true);
    setCraftError(null);
    try {
      const refined = await schedulerService.craftPrompt(raw);
      setNewPrompt(refined);
    } catch (err) {
      setCraftError(err instanceof Error ? err.message : "No se pudo mejorar el prompt.");
    } finally {
      setCraftingLoading(false);
    }
  }, [newPrompt]);

  /* ---- delete task ---- */
  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await schedulerService.deleteTask(id);
        if (editingId === id) setEditingId(null);
        await reloadTasks();
      } catch (err) {
        setSaveError(err instanceof Error ? err.message : "No se pudo eliminar la tarea.");
      }
    },
    [editingId, reloadTasks],
  );

  /* ---- edit schedule (inline) ---- */
  const startEdit = useCallback((task: SchedulerTask) => {
    setEditingId(task.id);
    setEditTime(task.time);
    setEditDays(task.days);
    setEditError(null);
  }, []);

  const cancelEdit = useCallback(() => {
    setEditingId(null);
    setEditError(null);
  }, []);

  const saveEdit = useCallback(async () => {
    setEditError(null);
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(editTime)) {
      setEditError("Horario inválido.");
      return;
    }
    if (editDays.length === 0) {
      setEditError("Seleccioná al menos un día.");
      return;
    }
    if (!editingId) return;
    try {
      await schedulerService.updateTask(editingId, {
        time: editTime,
        days: [...editDays].sort((a, b) => a - b),
      });
      setEditingId(null);
      await reloadTasks();
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "No se pudo actualizar la tarea.");
    }
  }, [editTime, editDays, editingId, reloadTasks]);

  /* ---- permission checkbox toggle ---- */
  const togglePermission = useCallback(
    (
      perms: Record<string, PermissionAction>,
      setter: (p: Record<string, PermissionAction>) => void,
      name: string,
    ) => {
      const next = { ...perms };
      if (next[name] === "allow") {
        delete next[name];
      } else {
        next[name] = "allow";
      }
      setter(next);
    },
    [],
  );

  /* ---- repetition slot helpers ---- */
  const addRepetition = useCallback(() => {
    setNewRepetitions((prev) => [...prev, { time: "09:00", days: [...ALL_DAYS] }]);
  }, []);

  const updateRepetition = useCallback(
    (index: number, patch: Partial<ScheduleSlot>) => {
      setNewRepetitions((prev) =>
        prev.map((s, i) => (i === index ? { ...s, ...patch } : s)),
      );
    },
    [],
  );

  const removeRepetition = useCallback((index: number) => {
    setNewRepetitions((prev) => prev.filter((_, i) => i !== index));
  }, []);

  if (!open) return null;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl w-[680px] h-[680px] flex flex-col p-0 gap-0">
        <DialogHeader className="px-6 pt-6 pb-4">
          <DialogTitle className="flex items-center gap-2">
            <AlarmClock size={20} />
            Tareas programadas
          </DialogTitle>
          <DialogDescription>
            Configurá tareas, permisos y horarios para el agente. Zona horaria:{" "}
            <span className="font-medium text-app-text">{timezone}</span>{" "}
            (tomada del sistema).
          </DialogDescription>
        </DialogHeader>

        {/* Body */}
        <div className="flex-1 min-h-0 overflow-y-auto px-6 pb-4 space-y-4">
          {savedMsg && (
            <div className="text-sm rounded-lg px-4 py-2.5 border text-green-800 bg-green-50 border-green-200">
              {savedMsg}
            </div>
          )}

          {saveError && (
            <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5">
              {saveError}
            </div>
          )}

          {/* Task list */}
          {tasks.length === 0 ? (
            <p className="text-sm text-app-text-secondary">
              No hay tareas programadas todavía.
            </p>
          ) : (
            <ul className="space-y-2">
              {tasks.map((task) => (
                <li
                  key={task.id}
                  className="bg-white border border-gray-200 rounded-lg px-4 py-3"
                >
                  {editingId === task.id ? (
                    /* ---- inline schedule editor ---- */
                    <div className="space-y-2">
                      <p className="text-sm font-medium text-app-text">
                        <span className="text-app-primary">{task.name}</span>: {task.prompt}
                      </p>
                      <div className="flex items-center gap-3 flex-wrap">
                        <label className="flex items-center gap-2 text-sm text-app-text-secondary">
                          <Clock size={14} className="text-app-primary" />
                          Hora
                          <input
                            type="time"
                            value={editTime}
                            onChange={(e) => setEditTime(e.target.value)}
                            className="border border-gray-300 rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
                          />
                        </label>
                        <div className="flex items-center gap-1">
                          <DayPicker days={editDays} onChange={setEditDays} />
                        </div>
                      </div>
                      {editError && (
                        <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-1.5">
                          {editError}
                        </div>
                      )}
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={saveEdit}
                          className="flex items-center gap-1.5 bg-gradient-to-r from-app-primary to-app-gradient-secondary text-app-primary-text text-xs font-medium px-3 py-1.5 rounded-lg hover:opacity-90"
                        >
                          <Check size={13} />
                          Guardar horario
                        </button>
                        <button
                          type="button"
                          onClick={cancelEdit}
                          className="flex items-center gap-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 text-xs font-medium px-3 py-1.5 rounded-lg transition-colors border border-gray-300"
                        >
                          <X size={13} />
                          Cancelar
                        </button>
                      </div>
                    </div>
                  ) : (
                    /* ---- task row ---- */
                    <div className="flex items-center gap-3">
                      <Clock size={15} className="shrink-0 text-app-primary" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-app-text truncate">
                          <span className="text-app-primary">{task.name}</span>: {task.prompt}
                        </p>
                        <p className="text-xs text-app-text-secondary">
                          {formatSchedule(task.time, task.days)}
                          {task.repetitions && task.repetitions.length > 0 && (
                            <span className="ml-2 text-app-text-secondary">
                              +{task.repetitions.length} horario{task.repetitions.length > 1 ? "s" : ""}
                            </span>
                          )}
                          {task.tool_permissions && (
                            <span className="ml-2 text-app-text-secondary">
                              <Shield size={10} className="inline" /> tools
                            </span>
                          )}
                          {task.skill_permissions && (
                            <span className="ml-2 text-app-text-secondary">
                              <Shield size={10} className="inline" /> skills
                            </span>
                          )}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => startEdit(task)}
                        className="text-gray-400 hover:text-app-primary shrink-0"
                        title="Editar horario"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(task.id)}
                        className="text-red-500 hover:text-red-700 shrink-0"
                        title="Eliminar tarea"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}

          {/* Add task */}
          <section className="space-y-3 pt-2 border-t border-gray-200">
            <h3 className="text-sm font-medium text-app-text flex items-center gap-2">
              <Plus size={14} className="text-app-primary" />
              Nueva tarea
            </h3>

            {/* Name */}
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Nombre de la tarea (ej.: resumen-diario)"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
            />

            {/* Prompt */}
            <textarea
              value={newPrompt}
              onChange={(e) => setNewPrompt(e.target.value)}
              placeholder="¿Qué tiene que hacer el agente? (ej.: Resumime los mails pendientes)"
              rows={2}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
            />
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleCraftPrompt}
                disabled={craftingLoading || !newPrompt.trim()}
                className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border border-gray-300 bg-white text-app-text-secondary hover:bg-gray-50 hover:text-app-primary disabled:opacity-50 transition-colors"
                title="Mejorar el prompt con IA"
              >
                <Sparkles size={13} className={craftingLoading ? "animate-spin" : ""} />
                {craftingLoading ? "Mejorando..." : "Mejorar prompt"}
              </button>
              {craftError && (
                <span className="text-xs text-red-600">{craftError}</span>
              )}
            </div>

            {/* Primary schedule */}
            <div className="flex items-center gap-3 flex-wrap">
              <label className="flex items-center gap-2 text-sm text-app-text-secondary">
                <Clock size={14} className="text-app-primary" />
                Hora
                <input
                  type="time"
                  value={newTime}
                  onChange={(e) => setNewTime(e.target.value)}
                  className="border border-gray-300 rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
                />
              </label>
              <div className="flex items-center gap-1">
                <DayPicker days={newDays} onChange={setNewDays} />
              </div>
            </div>

            {/* Collapsible: Permissions */}
            <CollapsibleSection
              open={showPermissions}
              onToggle={() => setShowPermissions(!showPermissions)}
              icon={<Shield size={13} />}
              label="Permisos"
              count={Object.keys(newToolPerms).length + Object.keys(newSkillPerms).length + Object.keys(newWorkflowPerms).length}
            >
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 space-y-3">
                {catalog.tools.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-app-text mb-1.5">Tools</p>
                    <div className="flex flex-wrap gap-1.5">
                      {catalog.tools.filter((tool: CatalogItem) => tool.name !== "workflow").map((tool: CatalogItem) => (
                        <PermissionCheckbox
                          key={tool.name}
                          name={tool.name}
                          description={tool.description}
                          checked={newToolPerms[tool.name] === "allow"}
                          onChange={() => togglePermission(newToolPerms, setNewToolPerms, tool.name)}
                        />
                      ))}
                    </div>
                  </div>
                )}
                {catalog.skills.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-app-text mb-1.5">Skills</p>
                    <div className="flex flex-wrap gap-1.5">
                      {catalog.skills.map((skill: CatalogItem) => (
                        <PermissionCheckbox
                          key={skill.name}
                          name={skill.name}
                          description={skill.description}
                          checked={newSkillPerms[skill.name] === "allow"}
                          onChange={() => togglePermission(newSkillPerms, setNewSkillPerms, skill.name)}
                        />
                      ))}
                    </div>
                  </div>
                )}
                {catalog.workflows.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-app-text mb-1.5">Workflows</p>
                    <div className="flex flex-wrap gap-1.5">
                      {catalog.workflows.map((workflow: CatalogItem) => (
                        <PermissionCheckbox
                          key={workflow.name}
                          name={workflow.name}
                          description={workflow.description}
                          checked={newWorkflowPerms[workflow.name] === "allow"}
                          onChange={() => togglePermission(newWorkflowPerms, setNewWorkflowPerms, workflow.name)}
                        />
                      ))}
                    </div>
                  </div>
                )}
                {catalog.tools.length === 0 && catalog.skills.length === 0 && catalog.workflows.length === 0 && (
                  <p className="text-xs text-app-text-secondary">No hay tools, skills ni workflows disponibles.</p>
                )}
              </div>
            </CollapsibleSection>

            {/* Collapsible: Parameters */}
            <CollapsibleSection
              open={showParameters}
              onToggle={() => setShowParameters(!showParameters)}
              icon={<Sliders size={13} />}
              label="Parámetros del modelo"
              count={Object.keys(newParams).length}
            >
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                <div className="grid grid-cols-2 gap-2">
                  <label className="flex flex-col gap-1">
                    <span className="text-[11px] text-app-text-secondary">Temperature</span>
                    <input
                      type="number"
                      min="0"
                      max="2"
                      step="0.1"
                      value={newParams.temperature ?? ""}
                      onChange={(e) =>
                        setNewParams((p) => ({
                          ...p,
                          temperature: e.target.value ? Number(e.target.value) : undefined,
                        }))
                      }
                      placeholder="default"
                      className="border border-gray-300 rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-400"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[11px] text-app-text-secondary">Top P</span>
                    <input
                      type="number"
                      min="0"
                      max="1"
                      step="0.05"
                      value={newParams.top_p ?? ""}
                      onChange={(e) =>
                        setNewParams((p) => ({
                          ...p,
                          top_p: e.target.value ? Number(e.target.value) : undefined,
                        }))
                      }
                      placeholder="default"
                      className="border border-gray-300 rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-400"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[11px] text-app-text-secondary">Max Tokens</span>
                    <input
                      type="number"
                      min="256"
                      max="128000"
                      step="256"
                      value={newParams.max_tokens ?? ""}
                      onChange={(e) =>
                        setNewParams((p) => ({
                          ...p,
                          max_tokens: e.target.value ? Number(e.target.value) : undefined,
                        }))
                      }
                      placeholder="default"
                      className="border border-gray-300 rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-400"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[11px] text-app-text-secondary">Seed</span>
                    <input
                      type="number"
                      min="0"
                      value={newParams.seed ?? ""}
                      onChange={(e) =>
                        setNewParams((p) => ({
                          ...p,
                          seed: e.target.value ? Number(e.target.value) : undefined,
                        }))
                      }
                      placeholder="default"
                      className="border border-gray-300 rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-400"
                    />
                  </label>
                </div>
              </div>
            </CollapsibleSection>

            {/* Collapsible: Additional repetitions */}
            <CollapsibleSection
              open={showRepetitions}
              onToggle={() => setShowRepetitions(!showRepetitions)}
              icon={<Repeat size={13} />}
              label="Horarios adicionales"
              count={newRepetitions.length}
            >
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 space-y-2">
                {newRepetitions.map((slot, idx) => (
                  <div key={idx} className="flex items-center gap-2 flex-wrap">
                    <label className="flex items-center gap-1.5 text-xs text-app-text-secondary">
                      <Clock size={12} className="text-app-primary" />
                      <input
                        type="time"
                        value={slot.time}
                        onChange={(e) => updateRepetition(idx, { time: e.target.value })}
                        className="border border-gray-300 rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-400"
                      />
                    </label>
                    <div className="flex items-center gap-0.5">
                      <DayPicker
                        days={slot.days}
                        onChange={(d) => updateRepetition(idx, { days: d })}
                        size="sm"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => removeRepetition(idx)}
                      className="text-red-500 hover:text-red-700"
                      title="Eliminar horario"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={addRepetition}
                  className="flex items-center gap-1.5 text-xs font-medium text-app-primary hover:text-app-primary/80 transition-colors"
                >
                  <Plus size={12} />
                  Agregar horario
                </button>
              </div>
            </CollapsibleSection>

            {formError && (
              <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-1.5">
                {formError}
              </div>
            )}
            <button
              type="button"
              onClick={handleAdd}
              className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-app-primary to-app-gradient-secondary text-app-primary-text text-sm font-medium px-4 py-2 rounded-lg hover:opacity-90 disabled:opacity-50"
            >
              <Plus size={14} />
              Agregar tarea
            </button>
          </section>
        </div>

        {/* Footer: global save + close */}
        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-gray-200">
          <button
            type="button"
            onClick={handleSaveAll}
            className="flex items-center justify-center gap-2 bg-gradient-to-r from-app-primary to-app-gradient-secondary text-app-primary-text text-sm font-medium px-5 py-2 rounded-lg hover:opacity-90"
          >
            <Check size={15} />
            Guardar
          </button>
          <button
            type="button"
            onClick={onClose}
            className="bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm font-medium px-5 py-2 rounded-lg transition-colors border border-gray-300"
          >
            Cerrar
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default SchedulerModal;
