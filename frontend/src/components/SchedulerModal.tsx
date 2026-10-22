import { useCallback, useEffect, useState, type ReactElement, type ReactNode } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "./ui/dialog";
import { ResourceCards } from "./ResourceCards";
import { EMPTY_SELECTION, type ResourceSelection } from "../utils/resourceSelection";
import {
  AlarmClock,
  Plus,
  Trash2,
  Pencil,
  Clock,
  Check,
  X,
  ChevronDown,
  ChevronRight,
  Shield,
  Repeat,
  Play,
  Square,
} from "lucide-react";
import schedulerService, {
  SchedulerTask,
  ScheduleSlot,
  NewScheduledTask,
} from "../services/schedulerService";
import workflowService from "../services/workflowService";

interface SchedulerModalProps {
  open: boolean;
  onClose: () => void;
}

const WEEKDAY_LABELS = ["D", "L", "M", "X", "J", "V", "S"];
const ALL_DAYS = [0, 1, 2, 3, 4, 5, 6];
/** Color of a selected day: fixed, it does not depend on the theme of the css. */
const DAY_SELECTED_COLOR = "#4f46e5";

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
          style={
            days.includes(day)
              ? { backgroundColor: DAY_SELECTED_COLOR, borderColor: DAY_SELECTED_COLOR, color: "#ffffff" }
              : { backgroundColor: "#ffffff", borderColor: "#d1d5db", color: "#6b7280" }
          }
          className={`${sizeClass} rounded-full font-medium border transition-colors`}
        >
          {label}
        </button>
      ))}
    </div>
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

/**
 * Agenda: the scheduled tasks (workflows with a schedule). A task is created by the workflow
 * creator (an LLM) with the schedule the user picks; it can be played and cancelled like any workflow.
 *
 * @param props - Whether the modal is open and how to close it.
 * @returns The modal, or ``null`` when it is closed.
 */
export function SchedulerModal({ open, onClose }: SchedulerModalProps): ReactElement | null {
  const [tasks, setTasks] = useState<SchedulerTask[]>([]);
  const [timezone] = useState<string>(getSystemTimezone);
  /* Name of each task that is running now → id of its run (to cancel it). */
  const [running, setRunning] = useState<Record<string, string>>({});
  const [starting, setStarting] = useState<string | null>(null);

  /* ---- add-task form ---- */
  const [newName, setNewName] = useState("");
  const [newPrompt, setNewPrompt] = useState("");
  const [newTime, setNewTime] = useState("09:00");
  const [newDays, setNewDays] = useState<number[]>(ALL_DAYS);
  const [newSelection, setNewSelection] = useState<ResourceSelection>(EMPTY_SELECTION);
  const [newRepetitions, setNewRepetitions] = useState<ScheduleSlot[]>([]);
  const [formError, setFormError] = useState<string | null>(null);
  /* Tasks added with "Agregar tarea": they are created only when "Guardar" is pressed. */
  const [pending, setPending] = useState<NewScheduledTask[]>([]);

  /* ---- collapsibles state ---- */
  const [showResources, setShowResources] = useState(false);
  const [showRepetitions, setShowRepetitions] = useState(false);

  /* ---- inline schedule editing ---- */
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTime, setEditTime] = useState("09:00");
  const [editDays, setEditDays] = useState<number[]>(ALL_DAYS);
  const [editError, setEditError] = useState<string | null>(null);

  /* ---- save feedback ---- */
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  /* Name of the task the creator is writing now, and what it streams. */
  const [creating, setCreating] = useState<string | null>(null);
  const [creatingText, setCreatingText] = useState("");

  /** Load the scheduled tasks from the backend. */
  const reloadTasks = useCallback(async (): Promise<void> => {
    try {
      setTasks(await schedulerService.getTasks());
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Error cargando las tareas.");
    }
  }, []);

  /** Load which tasks are running now. */
  const reloadRunning = useCallback(async (): Promise<void> => {
    try {
      const items = await workflowService.list();
      const next: Record<string, string> = {};
      for (const item of items) {
        if (item.running && item.run_id) next[item.name] = item.run_id;
      }
      setRunning(next);
    } catch {
      /* The state of the runs is only a hint: the list of tasks does not depend on it. */
    }
  }, []);

  /* Load the persisted tasks each time the modal opens */
  useEffect((): void => {
    if (open) {
      setSavedMsg(null);
      setSaveError(null);
      setFormError(null);
      setEditingId(null);
      setPending([]);
      reloadTasks();
      reloadRunning();
    }
  }, [open, reloadTasks, reloadRunning]);

  /* Follow the runs while the modal is open (a run ends on its own). */
  useEffect(() => {
    if (!open) return undefined;
    const timer = setInterval(reloadRunning, 5000);
    return () => clearInterval(timer);
  }, [open, reloadRunning]);

  /* Auto-dismiss the saved confirmation */
  useEffect(() => {
    if (!savedMsg) return undefined;
    const timer = setTimeout(() => setSavedMsg(null), 4000);
    return () => clearTimeout(timer);
  }, [savedMsg]);

  /**
   * Build the task of the form.
   *
   * @returns The task, or ``null`` (with the reason in ``formError``) when a field is invalid.
   */
  const buildFormTask = useCallback((): NewScheduledTask | null => {
    setFormError(null);
    const name = newName.trim();
    const prompt = newPrompt.trim();
    if (!name) {
      setFormError("El nombre de la tarea es obligatorio.");
      return null;
    }
    if (!/^[a-z0-9][a-z0-9_-]*$/.test(name)) {
      setFormError("El nombre solo puede contener minúsculas, números, guiones y guiones bajos.");
      return null;
    }
    if (tasks.some((t) => t.name === name) || pending.some((t) => t.name === name)) {
      setFormError(`Ya hay una tarea con el nombre '${name}'.`);
      return null;
    }
    if (!prompt) {
      setFormError("La tarea es obligatoria.");
      return null;
    }
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(newTime)) {
      setFormError("Horario inválido.");
      return null;
    }
    if (newDays.length === 0) {
      setFormError("Seleccioná al menos un día.");
      return null;
    }
    return {
      name,
      prompt,
      time: newTime,
      days: [...newDays].sort((a, b) => a - b),
      repetitions: newRepetitions.length > 0 ? newRepetitions : null,
      seleccion: newSelection,
    };
  }, [newName, newPrompt, newTime, newDays, newRepetitions, newSelection, tasks, pending]);

  /** Clear the form of the new task. */
  const resetForm = useCallback((): void => {
    setNewName("");
    setNewPrompt("");
    setNewTime("09:00");
    setNewDays(ALL_DAYS);
    setNewSelection(EMPTY_SELECTION);
    setNewRepetitions([]);
    setShowResources(false);
    setShowRepetitions(false);
  }, []);

  /** Add the task of the form to the unsaved list; nothing is created until "Guardar". */
  const handleAdd = useCallback((): void => {
    const task = buildFormTask();
    if (!task) return;
    setPending((prev) => [...prev, task]);
    setSavedMsg(null);
    resetForm();
  }, [buildFormTask, resetForm]);

  /** Create the unsaved tasks, and the one in the form when it has data; the ones that fail stay in the list. */
  const handleSaveAll = useCallback(async (): Promise<void> => {
    setSaveError(null);
    setSavedMsg(null);
    const toCreate = [...pending];
    if (newName.trim() || newPrompt.trim()) {
      const fromForm = buildFormTask();
      if (!fromForm) return;
      toCreate.push(fromForm);
    }
    if (toCreate.length === 0) {
      setSavedMsg("No hay tareas nuevas para guardar.");
      return;
    }
    const failed: NewScheduledTask[] = [];
    let firstError = "";
    for (const task of toCreate) {
      setCreating(task.name);
      setCreatingText("");
      try {
        await schedulerService.createTask(task, setCreatingText);
      } catch (err) {
        failed.push(task);
        if (!firstError) {
          firstError = `${task.name}: ${err instanceof Error ? err.message : "No se pudo crear la tarea."}`;
        }
      }
    }
    setCreating(null);
    setCreatingText("");
    setPending(failed);
    if (failed.length === 0) {
      resetForm();
      setSavedMsg("Tareas creadas correctamente.");
    } else {
      setSaveError(`No se pudieron crear ${failed.length} tarea(s). ${firstError}`);
    }
    await reloadTasks();
  }, [pending, newName, newPrompt, buildFormTask, resetForm, reloadTasks]);

  /**
   * Delete a task with its workflow and runs.
   *
   * @param id - Id of the task.
   */
  const handleDelete = useCallback(
    async (id: string): Promise<void> => {
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

  /**
   * Run a task now, like any workflow.
   *
   * @param name - Name of the task.
   */
  const handlePlay = useCallback(
    async (name: string): Promise<void> => {
      setStarting(name);
      setSaveError(null);
      try {
        await workflowService.run(name);
        await reloadRunning();
      } catch (err) {
        setSaveError(err instanceof Error ? err.message : "No se pudo ejecutar la tarea.");
      } finally {
        setStarting(null);
      }
    },
    [reloadRunning],
  );

  /**
   * Cancel the run of a task that is running.
   *
   * @param name - Name of the task.
   */
  const handleCancel = useCallback(
    async (name: string): Promise<void> => {
      const runId = running[name];
      if (!runId) return;
      try {
        await workflowService.cancel(runId);
        await reloadRunning();
      } catch (err) {
        setSaveError(err instanceof Error ? err.message : "No se pudo cancelar la ejecución.");
      }
    },
    [running, reloadRunning],
  );

  /**
   * Start editing the schedule of a task.
   *
   * @param task - Task to edit.
   */
  const startEdit = useCallback((task: SchedulerTask): void => {
    setEditingId(task.id);
    setEditTime(task.time);
    setEditDays(task.days);
    setEditError(null);
  }, []);

  /** Stop editing the schedule. */
  const cancelEdit = useCallback((): void => {
    setEditingId(null);
    setEditError(null);
  }, []);

  /** Save the new main time and days of the task being edited. */
  const saveEdit = useCallback(async (): Promise<void> => {
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

  /** Add a blank extra schedule to the form. */
  const addRepetition = useCallback((): void => {
    setNewRepetitions((prev) => [...prev, { time: "09:00", days: [...ALL_DAYS] }]);
  }, []);

  /**
   * Change one extra schedule of the form.
   *
   * @param index - Position of the schedule.
   * @param patch - Fields to change.
   */
  const updateRepetition = useCallback(
    (index: number, patch: Partial<ScheduleSlot>): void => {
      setNewRepetitions((prev) =>
        prev.map((s, i) => (i === index ? { ...s, ...patch } : s)),
      );
    },
    [],
  );

  /**
   * Remove one extra schedule of the form.
   *
   * @param index - Position of the schedule.
   */
  const removeRepetition = useCallback((index: number): void => {
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
            Una tarea programada es un workflow con horarios: un modelo lo crea a partir de lo que pidas. Zona horaria:{" "}
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

          {creating && (
            <div className="text-sm rounded-lg px-4 py-2.5 border border-indigo-200 bg-indigo-50 text-app-text">
              <p className="font-medium">Creando «{creating}»…</p>
              {creatingText && (
                <p className="mt-1 text-xs text-app-text-secondary whitespace-pre-wrap max-h-24 overflow-y-auto">
                  {creatingText}
                </p>
              )}
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
                          {!task.enabled && <span className="ml-2">· pausada</span>}
                          {running[task.name] && <span className="ml-2 text-app-primary">· ejecutándose</span>}
                        </p>
                      </div>
                      {running[task.name] ? (
                        <button
                          type="button"
                          onClick={() => handleCancel(task.name)}
                          className="action-btn action-btn--stop shrink-0"
                          title="Cancelar ejecución"
                          aria-label={`Cancelar ${task.name}`}
                        >
                          <Square size={14} fill="currentColor" />
                        </button>
                      ) : (
                        <button
                          type="button"
                          disabled={starting === task.name}
                          onClick={() => handlePlay(task.name)}
                          className="action-btn shrink-0"
                          title="Ejecutar ahora"
                          aria-label={`Ejecutar ${task.name}`}
                        >
                          <Play size={14} fill="currentColor" />
                        </button>
                      )}
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

          {/* Tasks added but not saved yet */}
          {pending.length > 0 && (
            <ul className="space-y-2">
              {pending.map((task, index) => (
                <li
                  key={`pending-${task.name}`}
                  className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex items-center gap-3"
                >
                  <Clock size={15} className="shrink-0 text-amber-600" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-app-text truncate">
                      <span className="text-app-primary">{task.name}</span>: {task.prompt}
                    </p>
                    <p className="text-xs text-app-text-secondary">
                      {formatSchedule(task.time, task.days)} · sin guardar
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setPending((prev) => prev.filter((_, i) => i !== index))}
                    className="text-red-500 hover:text-red-700 shrink-0"
                    title="Quitar de la lista"
                  >
                    <X size={14} />
                  </button>
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
              placeholder="¿Qué tiene que hacer? (ej.: Resumime los mails pendientes)"
              rows={2}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
            />

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

            {/* Collapsible: resources the task has to use */}
            <CollapsibleSection
              open={showResources}
              onToggle={() => setShowResources(!showResources)}
              icon={<Shield size={13} />}
              label="Recursos"
              count={newSelection.agentes.length + newSelection.tools.length + newSelection.rag.length}
            >
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                <ResourceCards
                  kinds={["agentes", "tools", "rag"]}
                  selection={newSelection}
                  onChange={setNewSelection}
                  idPrefix="scheduler"
                />
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
            disabled={creating !== null}
            className="flex items-center justify-center gap-2 bg-gradient-to-r from-app-primary to-app-gradient-secondary text-app-primary-text text-sm font-medium px-5 py-2 rounded-lg hover:opacity-90 disabled:opacity-50"
          >
            <Check size={15} />
            {creating ? "Creando…" : "Guardar"}
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
