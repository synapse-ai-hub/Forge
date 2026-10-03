import { useCallback, useRef, useState, type KeyboardEvent } from "react";
import { configService } from "../services/configService";

/** Providers offered on the initial setup screen.
 *
 * Only the two auxiliary keys live here: Groq (speech-to-text) and Google
 * (embeddings for the knowledge source). LLM providers are configured
 * from the sidebar instead.
 */
const SETUP_PROVIDERS: Array<{ id: string; label: string; hint: string; url: string }> = [
  {
    id: "groq",
    label: "Groq",
    hint: "transcripción de voz",
    url: "https://console.groq.com/keys",
  },
  {
    id: "google",
    label: "Google Gemini",
    hint: "fuente de conocimiento",
    url: "https://aistudio.google.com/apikey",
  },
];

interface SetupScreenProps {
  /** Called after a key is saved or the user skips, so the app can re-check providers. */
  onDone: () => void;
}

/**
 * Initial provider-setup screen (skippable).
 *
 * Shown when no provider is available (no cloud API key stored and Ollama
 * not responding). Uses the same palette and header as the creation
 * interfaces (skill/tool/agent/rag) — NOT the chat palette. The user can
 * configure API keys (validated against each provider before saving) or
 * skip; skipping leaves the app in a blocked state until a provider is
 * configured.
 */
export function SetupScreen({ onDone }: SetupScreenProps) {
  const [step, setStep] = useState<1 | 2>(1);
  /* One input value + status per provider */
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const savedAnyRef = useRef(false);

  const handleSkip = useCallback(() => {
    onDone();
  }, [onDone]);

  const handleSave = useCallback(
    async (providerId: string) => {
      const apiKey = (values[providerId] || "").trim();
      if (!apiKey) return;
      setSaving(providerId);
      setErrors((prev) => ({ ...prev, [providerId]: null }));
      try {
        await configService.saveProviderKey(providerId, apiKey);
        setSavedOk((prev) => ({ ...prev, [providerId]: true }));
        setValues((prev) => ({ ...prev, [providerId]: "" }));
        savedAnyRef.current = true;
      } catch (e) {
        setErrors((prev) => ({
          ...prev,
          [providerId]: (e as Error)?.message || "Error al guardar la clave.",
        }));
      } finally {
        setSaving(null);
      }
    },
    [values],
  );

  const handleContinue = useCallback(() => {
    // Only leave the screen when at least one valid key was saved; otherwise
    // go to the keys step so the user can configure or skip from there.
    if (savedAnyRef.current) {
      onDone();
    } else {
      setStep(2);
    }
  }, [onDone]);

  const setupKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>, providerId: string) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSave(providerId);
      }
    },
    [handleSave],
  );

  return (
    <div className="h-screen bg-app-bg flex flex-col overflow-hidden">
      {/* ========== HEADER creadores (95px, hardcodeado — no tocar) ========== */}
      <header
        className="flex items-center shrink-0 bg-white px-4 border-b border-gray-200"
        style={{ height: "95px" }}
      >
        {/* Left: empty to balance center */}
        <div className="sm:w-44"></div>

        {/* Center: logo + title */}
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
            <span className="brand-word">synapseForge</span> — Configuración inicial
          </span>
        </div>

        {/* Right: empty to balance center */}
        <div className="sm:w-44"></div>
      </header>

      <div className="flex-1 flex items-center justify-center p-6 bg-app-bg overflow-y-auto">
        <div className="w-full max-w-lg bg-white rounded-xl border border-app-border shadow-sm p-6 space-y-5">
          {step === 1 ? (
            /* ========== PASO 1: BIENVENIDA ========== */
            <>
              <div>
                <h2 className="text-xl font-semibold text-app-text mb-2">
                  Bienvenido a <span className="brand-word">synapseForge</span>
                </h2>
                <p className="text-sm text-gray-600 leading-relaxed">
                  Para usar el asistente necesit&aacute;s estas claves auxiliares. Es gratis sacarlas y pod&eacute;s empezar con la capa gratuita de cada una:
                </p>
              </div>

              <ul className="text-sm text-gray-600 space-y-1 list-disc list-inside">
                <li><strong>Groq</strong> — transcripci&oacute;n de voz</li>
                <li><strong>Google Gemini</strong> — fuente de conocimiento</li>
              </ul>

              <div className="text-sm text-gray-600 bg-app-bg-secondary border border-app-border rounded-lg px-4 py-3 leading-relaxed">
                <strong>Importante:</strong> la <strong>fuente de conocimiento</strong> (donde el asistente busca en tus documentos) funciona con Google Gemini. Pod&eacute;s continuar sin esa clave, pero esa funci&oacute;n quedar&aacute; deshabilitada hasta que la cargues.
              </div>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  className="flex-1 bg-gradient-to-r from-[#4f46e5] to-[#8b5cf6] text-white text-sm font-medium px-5 py-2.5 rounded-lg transition-colors hover:opacity-90"
                >
                  Configurar claves
                </button>
                <button
                  type="button"
                  onClick={handleSkip}
                  className="px-5 py-2.5 text-sm font-medium text-app-text-secondary border border-app-border rounded-lg transition-colors hover:bg-app-bg-secondary"
                >
                  Saltar
                </button>
              </div>
            </>
          ) : (
            /* ========== PASO 2: CLAVES ========== */
            <>
              <div>
                <h2 className="text-xl font-semibold text-app-text mb-1">
                  Claves de proveedores
                </h2>
                <p className="text-sm text-gray-600 leading-relaxed">
                  Peg&aacute; las claves que quieras usar. Se validan al guardar: si son v&aacute;lidas, el proveedor queda disponible de inmediato. Con al menos una alcanza para empezar.
                </p>
              </div>

              {SETUP_PROVIDERS.map((p) => (
                <div key={p.id}>
                  <label
                    htmlFor={`setup-key-${p.id}`}
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    {p.label}
                    <span className="text-xs text-app-text-secondary">
                      {" "}— {p.hint}
                    </span>
                  </label>
                  <div className="flex gap-2">
                    <input
                      id={`setup-key-${p.id}`}
                      type="password"
                      value={values[p.id] || ""}
                      onChange={(e) =>
                        setValues((prev) => ({ ...prev, [p.id]: e.target.value }))
                      }
                      onKeyDown={(e) => setupKeyDown(e, p.id)}
                      autoComplete="off"
                      className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
                      placeholder={`API key de ${p.label}`}
                    />
                    <button
                      type="button"
                      disabled={!(values[p.id] || "").trim() || saving === p.id}
                      onClick={() => handleSave(p.id)}
                      className="shrink-0 bg-gradient-to-r from-[#4f46e5] to-[#8b5cf6] text-white text-sm font-medium px-4 rounded-lg transition-colors hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {saving === p.id ? "Validando..." : savedOk[p.id] ? "Guardada" : "Guardar"}
                    </button>
                  </div>
                  {errors[p.id] && (
                    <p className="text-xs text-red-500 mt-1">{errors[p.id]}</p>
                  )}
                  <p className="text-xs text-gray-400 mt-1">
                    Sacala en{" "}
                    <a
                      href={p.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-app-primary underline"
                    >
                      {p.url.replace("https://", "")}
                    </a>
                  </p>
                </div>
              ))}

              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  onClick={handleContinue}
                  className="flex-1 bg-gradient-to-r from-[#4f46e5] to-[#8b5cf6] text-white text-sm font-medium px-5 py-2.5 rounded-lg transition-colors hover:opacity-90"
                >
                  Continuar
                </button>
                <button
                  type="button"
                  onClick={handleSkip}
                  className="px-5 py-2.5 text-sm font-medium text-app-text-secondary border border-app-border rounded-lg transition-colors hover:bg-app-bg-secondary"
                >
                  Saltar
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default SetupScreen;
