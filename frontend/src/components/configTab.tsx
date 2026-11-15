import { useState, useEffect, useCallback, useRef } from "react";
import { Settings, Server, Cpu, Database, Globe, Trash2, Upload, KeyRound, Pencil, Check, X } from "lucide-react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Collapsible } from "./ui/collapsible";
import configService from "../services/configService";
import type { ProviderKeyStatus, AdvancedParams, DecisionProvider, VoicesResponse, ModelSearchResult } from "../services/configService";
import contextFilesService, { type ContextFile } from "../services/contextFilesService";
import userMemoryService, { type UserPreference } from "../services/userMemoryService";

interface ConfigTabProps {
  verboseMode: boolean;
  onVerboseModeChange: (val: boolean) => void;
}

const DEFAULT_PARAMS: AdvancedParams = {
  temperature: null,
  top_p: null,
  reasoning: null,
  budget_tokens: null,
  response_format: null,
  output: null,
  voice: null,
  voice_speed: null,
  voice_instructions: null,
  voice_format: null,
};

function paramsEqual(a: AdvancedParams, b: AdvancedParams): boolean {
  return (
    a.temperature === b.temperature &&
    a.top_p === b.top_p &&
    a.reasoning === b.reasoning &&
    a.budget_tokens === b.budget_tokens &&
    a.response_format === b.response_format &&
    a.output === b.output &&
    a.voice === b.voice &&
    a.voice_speed === b.voice_speed &&
    a.voice_instructions === b.voice_instructions &&
    a.voice_format === b.voice_format
  );
}

function buildOutputOptions(
  outputModalities: string[] | null,
  responseFormatSupported: boolean | null,
  modelType: string | null
): Array<{ value: string; label: string }> | null {
  const mods = (outputModalities || []).map((m) => m.toLowerCase());
  const has = (m: string): boolean => mods.includes(m);
  const type = (modelType || "").toLowerCase();
  const multimodal = has("image") || has("audio") || has("video") || type === "image" || type === "speech" || type === "realtime";
  // Multimodales: sin dropdown.
  if (multimodal) {
    return null;
  }
  // Solo texto: Texto (default) y JSON. Nada de Default ni Auto.
  const opts: Array<{ value: string; label: string }> = [{ value: "text", label: "Texto" }];
  if (responseFormatSupported !== false) {
    opts.push({ value: "json", label: "JSON" });
  }
  return opts;
}

export function ConfigTab({ verboseMode, onVerboseModeChange }: ConfigTabProps) {
  const [providers, setProviders] = useState<Array<{ provider: string; label: string }>>([]);
  const [models, setModels] = useState<string[]>([]);
  const [currentModel, setCurrentModel] = useState<string | null>(null);
  const [currentProvider, setCurrentProvider] = useState<string>("");
  const [pendingModel, setPendingModel] = useState<string | null>(null);
  const [selectedProvider, setSelectedProvider] = useState<string>("");
  const [maxTurns, setMaxTurns] = useState<number>(-1);
  const [loading, setLoading] = useState(true);
  const [savingModel, setSavingModel] = useState(false);
  const [savingContext, setSavingContext] = useState(false);

  /* ---- advanced parameters (temperature / top_p / reasoning / response_format) ---- */
  const [pendingParams, setPendingParams] = useState<AdvancedParams>(DEFAULT_PARAMS);
  const [savedParams, setSavedParams] = useState<AdvancedParams>(DEFAULT_PARAMS);
  const [reasoningSupported, setReasoningSupported] = useState<boolean | null>(null);
  const [responseFormatSupported, setResponseFormatSupported] = useState<boolean | null>(null);
  const [reasoningOptions, setReasoningOptions] = useState<Array<{ value: string; label: string }>>([
    { value: "", label: "Default" },
    { value: "yes", label: "Sí" },
    { value: "no", label: "No" },
  ]);
  const [reasoningParam, setReasoningParam] = useState<string | null>(null);
  const [reasoningType, setReasoningType] = useState<string | null>(null);
  const [budgetMin, setBudgetMin] = useState<number | null>(null);
  const [budgetMax, setBudgetMax] = useState<number | null>(null);
  const [contextWindow, setContextWindow] = useState<number | null>(null);
  const [inputLimit, setInputLimit] = useState<number | null>(null);
  const [outputLimit, setOutputLimit] = useState<number | null>(null);
  const [inputModalities, setInputModalities] = useState<string[] | null>(null);
  const [outputModalities, setOutputModalities] = useState<string[] | null>(null);
  const [costInput, setCostInput] = useState<number | null>(null);
  const [costOutput, setCostOutput] = useState<number | null>(null);
  const [modelType, setModelType] = useState<string | null>(null);
  const [outputOptions, setOutputOptions] = useState<Array<{ value: string; label: string }> | null>([
    { value: "text", label: "Texto" },
    { value: "json", label: "JSON" },
  ]);
  /* ---- voice panel (TTS models only; null = hidden) ---- */
  const [voiceOptions, setVoiceOptions] = useState<VoicesResponse | null>(null);
  const [showVoiceInfo, setShowVoiceInfo] = useState(false);
  /* ---- model search filter (text + type, across providers with key) ---- */
  const [modelFilterType, setModelFilterType] = useState("todos");
  const [searchResults, setSearchResults] = useState<ModelSearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [applyMessage, setApplyMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [contextFiles, setContextFiles] = useState<ContextFile[]>([]);
  const [uploadingContext, setUploadingContext] = useState(false);
  const [preferences, setPreferences] = useState<UserPreference[]>([]);
  const [newPreference, setNewPreference] = useState("");
  const [savingPreference, setSavingPreference] = useState(false);
  const [expandedPreferenceId, setExpandedPreferenceId] = useState<string | null>(null);
  const [editingPreferenceId, setEditingPreferenceId] = useState<string | null>(null);
  const [editPreferenceText, setEditPreferenceText] = useState("");
  const [savingEditPreference, setSavingEditPreference] = useState(false);
  const contextFileInputRef = useRef<HTMLInputElement>(null);
  const isFirstLoadRef = useRef(true);

  /* ---- decision model (System One, independent from chat models) ---- */
  const [decisionProviders, setDecisionProviders] = useState<DecisionProvider[]>([]);
  const [decisionEnabled, setDecisionEnabled] = useState(false);
  const [currentDecisionProvider, setCurrentDecisionProvider] = useState<string | null>(null);
  const [currentDecisionModel, setCurrentDecisionModel] = useState<string | null>(null);
  const [pendingDecisionProvider, setPendingDecisionProvider] = useState("");
  const [pendingDecisionModel, setPendingDecisionModel] = useState<string | null>(null);
  const [savingDecision, setSavingDecision] = useState(false);
  const [decisionMessage, setDecisionMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  /* Decision model info (same layout as chat "Info del modelo"). */
  const [decisionContextWindow, setDecisionContextWindow] = useState<number | null>(null);
  const [decisionInputLimit, setDecisionInputLimit] = useState<number | null>(null);
  const [decisionOutputLimit, setDecisionOutputLimit] = useState<number | null>(null);
  const [decisionInputModalities, setDecisionInputModalities] = useState<string[] | null>(null);
  const [decisionOutputModalities, setDecisionOutputModalities] = useState<string[] | null>(null);
  const [decisionCostInput, setDecisionCostInput] = useState<number | null>(null);
  const [decisionCostOutput, setDecisionCostOutput] = useState<number | null>(null);

  const fetchDecisionInfo = useCallback(async (model: string, provider: string) => {
    try {
      const info = await configService.getDecisionCapabilities(model, provider);
      if (info && info.found !== false) {
        setDecisionContextWindow(info.context_window ?? null);
        setDecisionInputLimit(info.input_limit ?? null);
        setDecisionOutputLimit(info.output_limit ?? null);
        setDecisionInputModalities(info.input_modalities ?? null);
        setDecisionOutputModalities(info.output_modalities ?? null);
        setDecisionCostInput(info.cost_input ?? null);
        setDecisionCostOutput(info.cost_output ?? null);
      } else {
        setDecisionContextWindow(null);
        setDecisionInputLimit(null);
        setDecisionOutputLimit(null);
        setDecisionInputModalities(null);
        setDecisionOutputModalities(null);
        setDecisionCostInput(null);
        setDecisionCostOutput(null);
      }
    } catch (err) {
      console.error("Error fetching decision info:", err);
      setDecisionContextWindow(null);
      setDecisionInputLimit(null);
      setDecisionOutputLimit(null);
      setDecisionInputModalities(null);
      setDecisionOutputModalities(null);
      setDecisionCostInput(null);
      setDecisionCostOutput(null);
    }
  }, []);

  /* ---- provider API keys ---- */
  /* Curated providers (mirrors backend PROVIDER_REGISTRY). */
  const KEY_PROVIDER_OPTIONS: Array<{ provider: string; label: string }> = [
    { provider: "groq", label: "Groq" },
    { provider: "google", label: "Google Gemini" },
    { provider: "openrouter", label: "OpenRouter" },
    { provider: "openai", label: "OpenAI" },
    { provider: "deepseek", label: "DeepSeek" },
    { provider: "xai", label: "xAI" },
    { provider: "togetherai", label: "Together AI" },
    { provider: "fireworks-ai", label: "Fireworks AI" },
    { provider: "cerebras", label: "Cerebras" },
    { provider: "mistral", label: "Mistral AI" },
    { provider: "perplexity", label: "Perplexity" },
    { provider: "meta", label: "Meta" },
    { provider: "moonshotai", label: "Moonshot AI" },
    { provider: "zhipuai", label: "ZhipuAI" },
    { provider: "alibaba", label: "Alibaba" },
  ];
  const [providerKeys, setProviderKeys] = useState<ProviderKeyStatus[]>([]);
  const [keyProvider, setKeyProvider] = useState<string>("");
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({});
  const [savingKeyProvider, setSavingKeyProvider] = useState<string | null>(null);
  const [keysError, setKeysError] = useState<string | null>(null);

  /* ---- email accounts (mail + password + optional alias) ---- */
  const [emails, setEmails] = useState<Array<{ alias: string; email: string; provider: string; last_status: string }>>([]);
  const [mailEmail, setMailEmail] = useState<string>("");
  const [mailPassword, setMailPassword] = useState<string>("");
  const [mailAlias, setMailAlias] = useState<string>("");
  const [savingMail, setSavingMail] = useState<boolean>(false);
  const [emailsError, setEmailsError] = useState<string | null>(null);

  /* All key providers in one dropdown: chat + decision-only (same table). */
  const keyOptions: Array<{ provider: string; label: string }> = [
    ...KEY_PROVIDER_OPTIONS,
    ...decisionProviders
      .filter((p) => !KEY_PROVIDER_OPTIONS.some((o) => o.provider === p.provider))
      .map((p) => ({ provider: p.provider, label: `${p.label} (decisión)` })),
  ];

  const loadProviderKeys = useCallback(async () => {
    try {
      const resp = await configService.getProviderKeys();
      const keys = resp.keys || [];
      setProviderKeys(keys);
      // Default the dropdown to the first provider without a key.
      setKeyProvider((prev) => {
        if (prev) return prev;
        const configured = new Set(keys.filter((k) => k.configured).map((k) => k.provider));
        const options =
          keyOptions.length > 0 ? keyOptions : KEY_PROVIDER_OPTIONS;
        return (
          options.find((o) => !configured.has(o.provider))?.provider ||
          options[0].provider
        );
      });
    } catch (err) {
      console.error("Error cargando API keys:", err);
    }
  }, [decisionProviders]);

  useEffect(() => {
    loadProviderKeys();
  }, [loadProviderKeys]);

  const isKeyConfigured = (provider: string) =>
    providerKeys.find((k) => k.provider === provider)?.configured ?? false;

  const handleSaveKey = async (provider: string) => {
    const apiKey = (keyInputs[provider] || "").trim();
    if (!apiKey || savingKeyProvider) return;
    try {
      setKeysError(null);
      setSavingKeyProvider(provider);
      await configService.saveProviderKey(provider, apiKey);
      setKeyInputs((prev) => ({ ...prev, [provider]: "" }));
      await loadProviderKeys();
      // Refresh providers/models so a newly validated provider becomes
      // selectable immediately.
      await load();
    } catch (err) {
      setKeysError(err instanceof Error ? err.message : "Error guardando la API key.");
    } finally {
      setSavingKeyProvider(null);
    }
  };

  const handleDeleteKey = async (provider: string) => {
    if (savingKeyProvider) return;
    try {
      setKeysError(null);
      setSavingKeyProvider(provider);
      await configService.deleteProviderKey(provider);
      await loadProviderKeys();
      // Refresh providers so the removed provider disappears from the list.
      await load();
    } catch (err) {
      setKeysError(err instanceof Error ? err.message : "Error eliminando la API key.");
    } finally {
      setSavingKeyProvider(null);
    }
  };

  const loadEmails = useCallback(async () => {
    try {
      setEmailsError(null);
      const resp = await configService.getEmails();
      setEmails(resp.emails || []);
    } catch (err) {
      console.error("Error cargando mails:", err);
      setEmailsError(err instanceof Error ? err.message : "Error cargando mails.");
    }
  }, []);

  useEffect(() => {
    loadEmails();
  }, [loadEmails]);

  const handleSaveMail = async () => {
    const email = mailEmail.trim().toLowerCase();
    const password = mailPassword;
    const alias = mailAlias.trim();
    if (!email || !password || savingMail) return;
    try {
      setEmailsError(null);
      setSavingMail(true);
      await configService.saveEmail(email, password, alias);
      setMailEmail("");
      setMailPassword("");
      setMailAlias("");
      await loadEmails();
    } catch (err) {
      setEmailsError(err instanceof Error ? err.message : "Error guardando el mail.");
    } finally {
      setSavingMail(false);
    }
  };

  const handleDeleteMail = async (alias: string) => {
    if (savingMail) return;
    try {
      setEmailsError(null);
      setSavingMail(true);
      await configService.deleteEmail(alias);
      await loadEmails();
    } catch (err) {
      setEmailsError(err instanceof Error ? err.message : "Error eliminando el mail.");
    } finally {
      setSavingMail(false);
    }
  };

  const load = useCallback(async (prov?: string) => {
    try {
      setLoading(true);
      const [provResp, m, cw, prm, dec] = await Promise.all([
        configService.getProviders(),
        configService.getModels(prov),
        configService.getContextWindow(),
        configService.getParameters().catch(() => null),
        configService.getDecisionModels().catch(() => null),
      ]);
      setProviders(provResp.providers || []);
      setModels(m.models || []);
      // Set both currentModel and pendingModel to backend's current model.
      // When model changes externally (Telegram, another tab), both stay in sync.
      // User changes dropdown → pendingModel changes → Apply button enables.
      // User clicks Apply → currentModel updated to pendingModel.
      const model = m.model || null;
      // No default: when the backend reports no provider selected, keep the
      // dropdown empty so the user must choose one explicitly.
      const provider = m.provider || "";
      setCurrentModel(model);
      setPendingModel(model);
      // Only set currentProvider on first load (initial mount).
      // On provider change or external model change, keep currentProvider as last applied.
      // This allows the Apply button to enable when user switches provider in UI.
      if (isFirstLoadRef.current) {
        setCurrentProvider(provider);
        isFirstLoadRef.current = false;
      }
      const effective = prov || provider;
      setSelectedProvider(effective);
      setMaxTurns(typeof cw.max_turns === "number" ? cw.max_turns : -1);
      // Fetch reasoning options for the current model so budget/effort UI shows.
      if (model && effective) {
        fetchReasoningOptions(model, effective);
      }
      // Advanced parameters: null = "default" (agent frontmatter value).
      if (prm && prm.status === "success") {
        const p: AdvancedParams = {
          temperature: prm.temperature,
          top_p: prm.top_p,
          reasoning: prm.reasoning,
          budget_tokens: prm.budget_tokens,
          response_format: prm.response_format,
          output: (prm as unknown as { output?: string | null }).output ?? null,
          voice: (prm as unknown as { voice?: string | null }).voice ?? null,
          voice_speed: (prm as unknown as { voice_speed?: number | null }).voice_speed ?? null,
          voice_instructions: (prm as unknown as { voice_instructions?: string | null }).voice_instructions ?? null,
          voice_format: (prm as unknown as { voice_format?: string | null }).voice_format ?? null,
        };
        setPendingParams(p);
        setSavedParams(p);
        setReasoningSupported(prm.reasoning_supported);
        setResponseFormatSupported(prm.response_format_supported);
        setOutputModalities((prm as unknown as { output_modalities?: string[] | null }).output_modalities ?? null);
        setModelType((prm as unknown as { model_type?: string | null }).model_type ?? null);
        setOutputOptions(
          buildOutputOptions(
            (prm as unknown as { output_modalities?: string[] | null }).output_modalities ?? null,
            prm.response_format_supported,
            (prm as unknown as { model_type?: string | null }).model_type ?? null
          )
        );
        // Voice panel: options for the current model (hidden when N/A).
        if (model && effective) {
          try {
            const v = await configService.getVoices(model, effective);
            setVoiceOptions(v && v.status === "success" ? v : null);
          } catch {
            setVoiceOptions(null);
          }
        } else {
          setVoiceOptions(null);
        }
      }
      // Decision section: providers come from the decision_catalog table.
      if (dec && dec.status === "success") {
        setDecisionProviders(dec.providers || []);
        setDecisionEnabled(dec.enabled === true);
        setCurrentDecisionProvider(dec.provider || null);
        setCurrentDecisionModel(dec.model || null);
        setPendingDecisionProvider(dec.provider || "");
        setPendingDecisionModel(dec.model || null);
        if (dec.model && dec.provider) {
          fetchDecisionInfo(dec.model, dec.provider);
        }
      }
    } catch (err) {
      console.error("Error cargando configuración:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Refresh the dropdown + current model when the model is changed
  // elsewhere (Telegram, another tab). The gauge already listens to
  // "model-changed" in ChatInterface to recompute its percentage.
  useEffect(() => {
    const onModelChange = () => load();
    window.addEventListener("model-changed", onModelChange);
    return () => window.removeEventListener("model-changed", onModelChange);
  }, [load]);

  const reloadPreferences = useCallback(() => {
    userMemoryService.list()
      .then((prefs) => setPreferences(prefs || []))
      .catch((err) => console.error("Error cargando preferencias:", err));
  }, []);

  useEffect(() => {
    contextFilesService.list()
      .then((files) => setContextFiles(files || []))
      .catch((err) => console.error("Error cargando archivos de contexto:", err));
    reloadPreferences();
  }, [reloadPreferences]);

  // The agent can save preferences from the chat (approval modal), so the
  // list must refresh when Config regains visibility — not only on mount.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") reloadPreferences();
    };
    window.addEventListener("focus", reloadPreferences);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("focus", reloadPreferences);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [reloadPreferences]);

  const handleProviderChange = (value: string) => {
    setSelectedProvider(value);
    load(value);
  };

  const handleModelChange = (value: string) => {
    setPendingModel(value);
    // Fetch reasoning options for the selected model
    if (value && selectedProvider) {
      fetchReasoningOptions(value, selectedProvider);
    } else {
      // Reset to default options
      setReasoningOptions([
        { value: "", label: "Default" },
        { value: "yes", label: "Sí" },
        { value: "no", label: "No" },
      ]);
      setReasoningSupported(null);
      setResponseFormatSupported(null);
    }
  };

  /* Cross-provider model search: runs when a type filter is selected. */
  useEffect(() => {
    if (modelFilterType === "todos") {
      setSearchResults(null);
      setSearching(false);
      return;
    }
    setSearching(true);
    const timer = setTimeout(async () => {
      try {
        const resp = await configService.searchModels("", modelFilterType);
        setSearchResults(resp && resp.status === "success" ? resp.results || [] : []);
      } catch {
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [modelFilterType]);

  const handleSearchSelect = async (provider: string, modelId: string) => {
    setSelectedProvider(provider);
    await load(provider);
    setPendingModel(modelId);
    fetchReasoningOptions(modelId, provider);
  };

  const fetchReasoningOptions = useCallback(async (model: string, provider: string) => {
    try {
      const response = await configService.getModelCapabilities(model, provider);
      if (response && response.reasoning_options) {
        setReasoningOptions(response.reasoning_options);
        setReasoningSupported(response.reasoning_supported ?? true);
        setResponseFormatSupported(response.response_format_supported ?? null);
        setReasoningParam(response.reasoning_param ?? null);
        setReasoningType(response.reasoning_type ?? null);
        setBudgetMin(response.budget_min ?? null);
        setBudgetMax(response.budget_max ?? null);
        setContextWindow(response.context_window ?? null);
        setInputLimit(response.input_limit ?? null);
        setOutputLimit(response.output_limit ?? null);
        setInputModalities(response.input_modalities ?? null);
        setOutputModalities(response.output_modalities ?? null);
        setModelType(response.model_type ?? null);
        setOutputOptions(
          buildOutputOptions(response.output_modalities ?? null, response.response_format_supported ?? null, response.model_type ?? null)
        );
        setCostInput(response.cost_input ?? null);
        setCostOutput(response.cost_output ?? null);
        try {
          const v = await configService.getVoices(model, provider);
          setVoiceOptions(v && v.status === "success" ? v : null);
        } catch {
          setVoiceOptions(null);
        }
      } else {
        // Fallback to default options
        setReasoningOptions([
          { value: "", label: "Default" },
        ]);
        setReasoningSupported(null);
        setResponseFormatSupported(null);
        setReasoningParam(null);
        setReasoningType(null);
        setContextWindow(null);
        setInputLimit(null);
        setOutputLimit(null);
        setInputModalities(null);
        setOutputModalities(null);
        setModelType(null);
        setVoiceOptions(null);
        setOutputOptions([
          { value: "text", label: "Texto" },
          { value: "json", label: "JSON" },
        ]);
        setCostInput(null);
        setCostOutput(null);
      }
    } catch (err) {
      console.error("Error fetching reasoning options:", err);
      // Fallback to default options
      setReasoningOptions([
        { value: "", label: "Default" },
      ]);
      setReasoningSupported(null);
      setResponseFormatSupported(null);
      setReasoningParam(null);
      setReasoningType(null);
      setContextWindow(null);
      setInputLimit(null);
      setOutputLimit(null);
      setInputModalities(null);
      setOutputModalities(null);
      setModelType(null);
      setVoiceOptions(null);
      setOutputOptions([
        { value: "text", label: "Texto" },
        { value: "json", label: "JSON" },
      ]);
      setCostInput(null);
      setCostOutput(null);
    }
  }, []);

  /* ---- advanced parameter handlers ---- */

  const handleTemperatureDefault = (useDefault: boolean) => {
    setPendingParams((prev) => ({
      ...prev,
      temperature: useDefault ? null : prev.temperature ?? 0,
    }));
  };

  const handleTemperatureChange = (value: number) => {
    setPendingParams((prev) => ({ ...prev, temperature: value }));
  };

  const handleTopPDefault = (useDefault: boolean) => {
    setPendingParams((prev) => ({
      ...prev,
      top_p: useDefault ? null : prev.top_p ?? 0.5,
    }));
  };

  const handleTopPChange = (value: number) => {
    setPendingParams((prev) => ({ ...prev, top_p: value }));
  };

  const handleReasoningChange = (value: string) => {
    // Store the raw value; the backend will interpret it based on reasoning_param
    setPendingParams((prev) => ({
      ...prev,
      reasoning: value === "" ? null : value,
    }));
  };

  const handleResponseFormatChange = (value: string) => {
    setPendingParams((prev) => ({
      ...prev,
      response_format: value === "" ? null : value,
    }));
  };

  const handleOutputChange = (value: string) => {
    setPendingParams((prev) => ({
      ...prev,
      output: value === "" ? null : value,
    }));
  };

  /* ---- voice handlers (TTS models only) ---- */

  const handleVoiceChange = (value: string) => {
    setPendingParams((prev) => ({
      ...prev,
      voice: value === "" ? null : value,
    }));
  };

  const handleVoiceSpeedDefault = (useDefault: boolean) => {
    setPendingParams((prev) => ({
      ...prev,
      voice_speed: useDefault ? null : prev.voice_speed ?? 1,
    }));
  };

  const handleVoiceSpeedChange = (value: number) => {
    setPendingParams((prev) => ({ ...prev, voice_speed: value }));
  };

  const handleVoiceInstructionsChange = (value: string) => {
    setPendingParams((prev) => ({
      ...prev,
      voice_instructions: value === "" ? null : value,
    }));
  };

  const handleVoiceFormatChange = (value: string) => {
    setPendingParams((prev) => ({
      ...prev,
      voice_format: value === "" ? null : value,
    }));
  };

  const handleApplyModel = async () => {
    // Enable if provider, model OR parameters differ from current (not all equal)
    const isSame =
      pendingModel === currentModel &&
      selectedProvider === currentProvider &&
      paramsEqual(pendingParams, savedParams);
    if (!pendingModel || isSame || savingModel) return;
    try {
      setSavingModel(true);
      setApplyMessage(null);
      await configService.selectModel(pendingModel, selectedProvider, pendingParams);
      setCurrentModel(pendingModel);
      setCurrentProvider(selectedProvider);
      setSavedParams(pendingParams);
      window.dispatchEvent(new Event("model-changed"));
      setApplyMessage({ type: "success", text: "Configuración aplicada correctamente." });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error al aplicar la configuración.";
      console.error("Error aplicando configuración:", err);
      setApplyMessage({ type: "error", text: msg });
    } finally {
      setSavingModel(false);
    }
  };

  const handleSelectModel = async (model: string) => {
    try {
      setSavingModel(true);
      setApplyMessage(null);
      await configService.selectModel(model, selectedProvider, savedParams);
      setCurrentModel(model);
      setPendingModel(model);
      window.dispatchEvent(new Event("model-changed"));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error al seleccionar el modelo.";
      console.error("Error seleccionando modelo:", err);
      setApplyMessage({ type: "error", text: msg });
    } finally {
      setSavingModel(false);
    }
  };

  const handleSaveContext = async () => {
    try {
      setSavingContext(true);
      await configService.setContextWindow(maxTurns);
    } catch (err) {
      console.error("Error guardando contexto:", err);
    } finally {
      setSavingContext(false);
    }
  };

  /* ---- decision model handlers (independent from chat models) ---- */
  /* Like chat models: only providers with a stored key are selectable. */
  const configuredDecisionProviders = decisionProviders.filter((p) =>
    providerKeys.some((k) => k.provider === p.provider && k.configured),
  );

  const decisionModelsFor = (provider: string): string[] =>
    decisionProviders.find((p) => p.provider === provider)?.models || [];

  const handleToggleDecision = async (enabled: boolean) => {
    try {
      setDecisionMessage(null);
      await configService.setDecisionEnabled(enabled);
      setDecisionEnabled(enabled);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error al guardar el estado de decisión.";
      console.error("Error guardando estado de decisión:", err);
      setDecisionMessage({ type: "error", text: msg });
    }
  };

  const handleDecisionProviderChange = (value: string) => {
    setPendingDecisionProvider(value);
    const models = decisionModelsFor(value);
    const next = models.length > 0 ? models[0] : null;
    setPendingDecisionModel(next);
    if (next) {
      fetchDecisionInfo(next, value);
    } else {
      setDecisionContextWindow(null);
      setDecisionInputLimit(null);
      setDecisionOutputLimit(null);
      setDecisionInputModalities(null);
      setDecisionOutputModalities(null);
      setDecisionCostInput(null);
      setDecisionCostOutput(null);
    }
  };

  const handleApplyDecision = async () => {
    const isSame =
      pendingDecisionModel === currentDecisionModel &&
      pendingDecisionProvider === (currentDecisionProvider || "");
    if (!decisionEnabled || !pendingDecisionModel || !pendingDecisionProvider || isSame || savingDecision) return;
    try {
      setSavingDecision(true);
      setDecisionMessage(null);
      await configService.selectDecisionModel(pendingDecisionModel, pendingDecisionProvider);
      setCurrentDecisionModel(pendingDecisionModel);
      setCurrentDecisionProvider(pendingDecisionProvider);
      setDecisionMessage({ type: "success", text: "Modelo de decisión aplicado correctamente." });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error al aplicar el modelo de decisión.";
      console.error("Error aplicando modelo de decisión:", err);
      setDecisionMessage({ type: "error", text: msg });
    } finally {
      setSavingDecision(false);
    }
  };

  const handleUploadContextFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      setUploadingContext(true);
      await contextFilesService.upload(file);
      const files = await contextFilesService.list();
      setContextFiles(files || []);
    } catch (err) {
      console.error("Error subiendo archivo de contexto:", err);
    } finally {
      setUploadingContext(false);
      if (e.target) e.target.value = "";
    }
  };

  const handleDeleteContextFile = async (id: number) => {
    try {
      await contextFilesService.delete(id);
      setContextFiles((prev) => prev.filter((f) => f.id !== id));
    } catch (err) {
      console.error("Error eliminando archivo de contexto:", err);
    }
  };

  const handleAddPreference = async () => {
    const text = newPreference.trim();
    if (!text) return;
    try {
      setSavingPreference(true);
      await userMemoryService.add(text);
      const prefs = await userMemoryService.list();
      setPreferences(prefs || []);
      setNewPreference("");
    } catch (err) {
      console.error("Error guardando preferencia:", err);
    } finally {
      setSavingPreference(false);
    }
  };

  const handleDeletePreference = async (id: string) => {
    try {
      await userMemoryService.remove(id);
      setPreferences((prev) => prev.filter((p) => p.id !== id));
    } catch (err) {
      console.error("Error eliminando preferencia:", err);
    }
  };

  const handleStartEditPreference = (id: string, text: string) => {
    setEditingPreferenceId(id);
    setEditPreferenceText(text);
    setExpandedPreferenceId(null);
  };

  const handleCancelEditPreference = () => {
    setEditingPreferenceId(null);
    setEditPreferenceText("");
  };

  const handleSaveEditPreference = async (id: string) => {
    const text = editPreferenceText.trim();
    if (!text) return;
    try {
      setSavingEditPreference(true);
      const updated = await userMemoryService.update(id, text);
      setPreferences((prev) => prev.map((p) => (p.id === id ? { ...p, text: updated.text } : p)));
      setEditingPreferenceId(null);
      setEditPreferenceText("");
    } catch (err) {
      console.error("Error actualizando preferencia:", err);
    } finally {
      setSavingEditPreference(false);
    }
  };

  if (loading) {
    return (
      <div className="p-4 text-sm text-app-text-secondary">Cargando...</div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-5">
      <div>
        <div className="text-xs font-medium text-app-text-secondary">
          Proveedor
        </div>
        <select
          value={selectedProvider}
          onChange={(e) => handleProviderChange(e.target.value)}
          className="mt-1 w-full rounded-lg border border-app-border bg-white px-3 py-2 text-sm text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary-light"
        >
          {selectedProvider === "" && (
            <option value="">Seleccion&aacute; un proveedor</option>
          )}
          {providers.length === 0 ? (
            <option value="">No hay proveedores disponibles</option>
          ) : (
            providers.map((p) => (
              <option key={p.provider} value={p.provider}>
                {p.label}
              </option>
            ))
          )}
        </select>
      </div>

      <div>
        <div className="text-xs font-medium text-app-text-secondary">
          Modelo
        </div>
        <select
          value={pendingModel || ""}
          onChange={(e) => handleModelChange(e.target.value)}
          disabled={savingModel || models.length === 0}
          className="mt-1 w-full rounded-lg border border-app-border bg-white px-3 py-2 text-sm text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary-light"
        >
          {models.length === 0 ? (
            <option value="">No hay modelos disponibles</option>
          ) : (
            models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))
          )}
        </select>
      </div>

      <Collapsible title="Filtrar modelos (todos los proveedores)">
        <div className="mt-1">
          <select
            value={modelFilterType}
            onChange={(e) => setModelFilterType(e.target.value)}
            className="w-full rounded-lg border border-app-border bg-white px-3 py-2 text-sm text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary-light"
          >
            <option value="todos">Todos</option>
            <option value="texto">Texto</option>
            <option value="imagen">Imagen</option>
            <option value="audio">Audio</option>
            <option value="video">Video</option>
            <option value="transcripcion">Transcripción</option>
            <option value="embeddings">Embeddings</option>
              <option value="decision">Decisión</option>
            <option value="rerank">Rerank</option>
          </select>
        </div>
        {searchResults !== null && (
          <div className="mt-1 max-h-48 overflow-y-auto rounded-lg border border-app-border bg-white">
            {searching ? (
              <div className="px-3 py-2 text-sm text-app-text-secondary">Buscando...</div>
            ) : searchResults.length === 0 ? (
              <div className="px-3 py-2 text-sm text-app-text-secondary">Sin resultados</div>
            ) : (
              searchResults.map((r) => (
                <button
                  key={`${r.provider}/${r.model_id}`}
                  type="button"
                  onClick={() => handleSearchSelect(r.provider, r.model_id)}
                  className="block w-full px-3 py-1.5 text-left text-sm text-app-text hover:bg-app-primary-light/20"
                >
                  <span className="font-medium">{r.provider}</span>
                  <span className="text-app-text-secondary"> — {r.model_id}</span>
                </button>
              ))
            )}
          </div>
        )}
      </Collapsible>

      {/* Model info */}
      {(contextWindow !== null || inputLimit !== null || outputLimit !== null || inputModalities !== null || outputModalities !== null || costInput !== null || costOutput !== null) && (
        <Collapsible title="Info del modelo">
          <div className="space-y-1.5">
            {inputModalities !== null && inputModalities.length > 0 && (
              <div className="flex justify-between items-center text-[11px]">
                <span className="text-app-text-secondary">Entrada</span>
                <span className="text-app-primary font-medium">{inputModalities.map(m => m.charAt(0).toUpperCase() + m.slice(1)).join(", ")}</span>
              </div>
            )}
            {outputModalities !== null && outputModalities.length > 0 && (
              <div className="flex justify-between items-center text-[11px]">
                <span className="text-app-text-secondary">Salida</span>
                <span className="text-app-primary font-medium">{outputModalities.map(m => m.charAt(0).toUpperCase() + m.slice(1)).join(", ")}</span>
              </div>
            )}
            {contextWindow !== null && (
              <div className="flex justify-between items-center text-[11px]">
                <span className="text-app-text-secondary">Contexto</span>
                <span className="text-app-primary font-medium">{contextWindow.toLocaleString()} tokens</span>
              </div>
            )}
            {inputLimit !== null && (
              <div className="flex justify-between items-center text-[11px]">
                <span className="text-app-text-secondary">Entrada máx</span>
                <span className="text-app-primary font-medium">{inputLimit.toLocaleString()} tokens</span>
              </div>
            )}
            {outputLimit !== null && (
              <div className="flex justify-between items-center text-[11px]">
                <span className="text-app-text-secondary">Salida máx</span>
                <span className="text-app-primary font-medium">{outputLimit.toLocaleString()} tokens</span>
              </div>
            )}
            {(costInput !== null || costOutput !== null) && (
              <div className="flex justify-between items-center text-[11px]">
                <span className="text-app-text-secondary">Costo</span>
                <span className="text-app-primary font-medium">
                  {costInput !== null && `In $${costInput}`}
                  {costInput !== null && costOutput !== null && " · "}
                  {costOutput !== null && `Out $${costOutput}`}
                  <span className="text-app-text-secondary font-normal"> /M tok</span>
                </span>
              </div>
            )}
          </div>
        </Collapsible>
      )}

{/* Parámetros avanzados */}
      <Collapsible title="Parámetros avanzados">
        <p className="text-[11px] text-app-text-secondary mb-2">
          Se aplican junto con el modelo al presionar "Aplicar". Con "Default" se usan los valores de cada agente.
        </p>
        <div className="space-y-3">
          {/* Temperature */}
          <div>
            <div className="flex items-center justify-between">
              <label className="text-xs text-app-text">Temperature</label>
              <label className="flex items-center gap-1 text-[11px] text-app-text-secondary cursor-pointer">
                <input
                  type="checkbox"
                  checked={pendingParams.temperature === null}
                  onChange={(e) => handleTemperatureDefault(e.target.checked)}
                  className="accent-app-primary"
                />
                Default
              </label>
            </div>
            {pendingParams.temperature !== null && (
              <div className="flex items-center gap-2 mt-1">
                <input
                  type="range"
                  min={0}
                  max={2}
                  step={0.1}
                  value={pendingParams.temperature}
                  onChange={(e) => handleTemperatureChange(Number(e.target.value))}
                  className="flex-1 accent-app-primary"
                />
                <span className="w-9 text-right text-xs text-app-text-secondary tabular-nums">
                  {pendingParams.temperature.toFixed(1)}
                </span>
              </div>
            )}
          </div>

          {/* Top P */}
          <div>
            <div className="flex items-center justify-between">
              <label className="text-xs text-app-text">Top P</label>
              <label className="flex items-center gap-1 text-[11px] text-app-text-secondary cursor-pointer">
                <input
                  type="checkbox"
                  checked={pendingParams.top_p === null}
                  onChange={(e) => handleTopPDefault(e.target.checked)}
                  className="accent-app-primary"
                />
                Default
              </label>
            </div>
            {pendingParams.top_p !== null && (
              <div className="flex items-center gap-2 mt-1">
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={pendingParams.top_p}
                  onChange={(e) => handleTopPChange(Number(e.target.value))}
                  className="flex-1 accent-app-primary"
                />
                <span className="w-9 text-right text-xs text-app-text-secondary tabular-nums">
                  {pendingParams.top_p.toFixed(2)}
                </span>
              </div>
            )}
          </div>

          {/* Reasoning */}
          <div className="flex items-center justify-between">
            <label className="text-xs text-app-text">Reasoning</label>
            <select
              value={
                pendingParams.reasoning === null
                  ? ""
                  : String(pendingParams.reasoning)
              }
              disabled={reasoningSupported === false || reasoningOptions.length === 0}
              title={
                reasoningSupported === false
                  ? "El modelo actual no soporta reasoning."
                  : reasoningOptions.length === 0
                    ? "Seleccioná un modelo para ver opciones de reasoning"
                    : undefined
              }
              onChange={(e) => handleReasoningChange(e.target.value)}
              className={`rounded-lg border border-app-border bg-white px-2 py-1 text-xs text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary-light ${
                reasoningSupported === false || reasoningOptions.length === 0 ? "opacity-50 cursor-not-allowed" : ""
              }`}
            >
              {reasoningOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Salida: solo modelos de texto. Multimodales: sin dropdown. */}
          {outputOptions !== null && (
          <div className="flex items-center justify-between">
            <label className="text-xs text-app-text">Salida</label>
            <select
              value={pendingParams.output ?? pendingParams.response_format ?? "text"}
              onChange={(e) => {
                const v = e.target.value;
                handleOutputChange(v);
                if (v === "json") {
                  handleResponseFormatChange("json");
                } else {
                  handleResponseFormatChange("");
                }
              }}
              title={
                outputModalities && outputModalities.length > 0
                  ? `Salidas del modelo: ${outputModalities.join(", ")}${modelType ? ` (${modelType})` : ""}`
                  : undefined
              }
              className="rounded-lg border border-app-border bg-white px-2 py-1 text-xs text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary-light"
            >
              {outputOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
          )}

          {/* Voz: solo modelos TTS (applicable). Multimodales de imagen/video: sin panel. */}
          {voiceOptions !== null && voiceOptions.applicable && (
          <div className="pt-2 border-t border-app-border space-y-2">
            <label className="block text-xs text-app-text">Voz</label>
            {voiceOptions.fixed_voice ? (
              <span className="block text-[11px] text-app-text-secondary">
                Voz fija del modelo.
              </span>
            ) : (
              <>
                {voiceOptions.voices.length > 0 && (
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <label className="text-xs text-app-text">Voz</label>
                    <div className="flex items-center gap-1">
                      <select
                        value={pendingParams.voice ?? voiceOptions.default_voice ?? voiceOptions.voices[0] ?? ""}
                        onChange={(e) => handleVoiceChange(e.target.value)}
                        className="rounded-lg border border-app-border bg-white px-2 py-1 text-xs text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary-light"
                      >
                        {voiceOptions.voices.map((v) => (
                          <option key={v} value={v}>
                            {v}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={() => setShowVoiceInfo((s) => !s)}
                        title="Ver características de la voz"
                        className="rounded-full border border-app-border px-1.5 py-0.5 text-[11px] text-app-text-secondary hover:bg-app-primary-light/20"
                      >
                        ⓘ
                      </button>
                    </div>
                  </div>
                  {showVoiceInfo && (() => {
                    const effectiveVoice = pendingParams.voice ?? voiceOptions.default_voice ?? voiceOptions.voices[0];
                    const sel = effectiveVoice
                      ? voiceOptions.voice_details?.find((x) => x.name === effectiveVoice)
                      : undefined;
                    if (!sel) {
                      return (
                        <div className="rounded-lg border border-app-border bg-white px-2 py-1 text-[11px] text-app-text-secondary">
                          Elegí una voz para ver sus características.
                        </div>
                      );
                    }
                    const rows: Array<[string, string]> = [
                      ["Estilo", sel.style || ""],
                      ["Género", sel.gender || ""],
                      ["Tono", sel.pitch || ""],
                      ["Acento", sel.accent || ""],
                      ["Persona", sel.persona || ""],
                    ].filter(([, v]) => v !== "") as Array<[string, string]>;
                    return (
                      <div className="rounded-lg border border-app-border bg-white px-2 py-1 text-[11px] text-app-text-secondary space-y-0.5">
                        <div className="font-medium text-app-text">{sel.name}</div>
                        {sel.recommended && <div>Recomendada por el proveedor.</div>}
                        {rows.map(([k, v]) => (
                          <div key={k}>
                            {k}: <span className="text-app-text">{v}</span>
                          </div>
                        ))}
                        {sel.description && <div>{sel.description}</div>}
                      </div>
                    );
                  })()}
                </div>
                )}
                {voiceOptions.supports_speed && (
                <div>
                  <div className="flex items-center justify-between">
                    <label className="text-xs text-app-text">Velocidad</label>
                    <label className="flex items-center gap-1 text-[11px] text-app-text-secondary cursor-pointer">
                      <input
                        type="checkbox"
                        checked={pendingParams.voice_speed === null}
                        onChange={(e) => handleVoiceSpeedDefault(e.target.checked)}
                        className="accent-app-primary"
                      />
                      Default
                    </label>
                  </div>
                  {pendingParams.voice_speed !== null && (
                    <div className="flex items-center gap-2 mt-1">
                      <input
                        type="range"
                        min={0.25}
                        max={4}
                        step={0.05}
                        value={pendingParams.voice_speed}
                        onChange={(e) => handleVoiceSpeedChange(Number(e.target.value))}
                        className="flex-1 accent-app-primary"
                      />
                      <span className="w-9 text-right text-xs text-app-text-secondary tabular-nums">
                        {pendingParams.voice_speed.toFixed(2)}
                      </span>
                    </div>
                  )}
                </div>
                )}
                {voiceOptions.supports_instructions && (
                <div className="space-y-1">
                  <label className="block text-xs text-app-text">Instrucciones de voz</label>
                  <input
                    type="text"
                    value={pendingParams.voice_instructions ?? ""}
                    placeholder="Ej. Habla lento y con calma"
                    onChange={(e) => handleVoiceInstructionsChange(e.target.value)}
                    className="w-full rounded-lg border border-app-border bg-white px-2 py-1 text-xs text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary-light"
                  />
                </div>
                )}
                {voiceOptions.formats.length > 0 && (
                <div className="flex items-center justify-between">
                  <label className="text-xs text-app-text">Formato</label>
                  <select
                    value={pendingParams.voice_format ?? voiceOptions.default_format ?? voiceOptions.formats[0] ?? ""}
                    onChange={(e) => handleVoiceFormatChange(e.target.value)}
                    className="rounded-lg border border-app-border bg-white px-2 py-1 text-xs text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary-light"
                  >
                    {voiceOptions.formats.map((f) => (
                      <option key={f} value={f}>
                        {f}
                      </option>
                    ))}
                  </select>
                </div>
                )}
              </>
            )}
          </div>
          )}

          {/* Budget Tokens (if model uses budget) */}
          {reasoningType === "budget_tokens" && (
            <div className="pt-2 border-t border-app-border space-y-1">
              <label className="block text-xs text-app-text">Presupuesto de tokens</label>
              <span className="block text-[10px] text-app-text-secondary">
                {budgetMin !== null && budgetMax !== null
                  ? `Entre ${budgetMin} y ${budgetMax}`
                  : budgetMin !== null
                    ? `Mín: ${budgetMin}`
                    : budgetMax !== null
                      ? `Máx: ${budgetMax}`
                      : "sin rango"}
              </span>
              <input
                type="number"
                value={pendingParams.budget_tokens ?? ""}
                placeholder="Ej. 1024"
                onChange={(e) => {
                  const val = e.target.value === "" ? null : Number(e.target.value);
                  setPendingParams((prev) => ({ ...prev, budget_tokens: val }));
                }}
                className="w-full rounded-lg border border-app-border bg-white px-2 py-1 text-xs text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary-light"
              />
            </div>
          )}
        </div>
      </Collapsible>

      {/* Single Apply button for model + provider + advanced params */}
      <Button
        onClick={handleApplyModel}
        disabled={
          savingModel ||
          !pendingModel ||
          (pendingModel === currentModel &&
            selectedProvider === currentProvider &&
            paramsEqual(pendingParams, savedParams))
        }
        variant="gradient"
        className="w-full"
      >
        {savingModel ? (
          <>
            <svg
              className="animate-spin -ml-1 mr-2 h-4 w-4"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            Aplicando...
          </>
        ) : (
          "Aplicar"
        )}
      </Button>
      {applyMessage && (
        <div
          className={`text-xs rounded-lg px-3 py-2 border ${
            applyMessage.type === "success"
              ? "text-green-700 bg-green-50 border-green-200"
              : "text-red-600 bg-red-50 border-red-200"
          }`}
        >
          {applyMessage.text}
        </div>
      )}

      {/* Modelo de decisión (System One, independiente del modelo de chat) */}
      <div className="pt-2 border-t border-app-border">
        <div className="flex items-center justify-between py-2">
          <div>
            <div className="text-xs font-medium text-app-text-secondary">
              Modelo de decisión
            </div>
            <p className="text-[11px] text-app-text-secondary mt-1">
              Valida cierres y decisiones con un modelo System One. Si está apagado, el flujo actual no cambia.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={decisionEnabled}
            onClick={() => handleToggleDecision(!decisionEnabled)}
            className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-app-primary-light ${
              decisionEnabled ? "bg-app-primary" : "bg-app-bg-tertiary"
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
                decisionEnabled ? "translate-x-4" : "translate-x-0"
              }`}
            />
          </button>
        </div>

        <div className={decisionEnabled ? "space-y-5" : "opacity-50 pointer-events-none space-y-5"}>
          <div>
            <div className="text-xs font-medium text-app-text-secondary">
              Proveedor de decisión
            </div>
            <select
            value={pendingDecisionProvider}
            onChange={(e) => handleDecisionProviderChange(e.target.value)}
            disabled={!decisionEnabled || savingDecision}
            className="mt-1 w-full rounded-lg border border-app-border bg-white px-3 py-2 text-sm text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary-light"
          >
            {pendingDecisionProvider === "" && (
              <option value="">Seleccion&aacute; un proveedor</option>
            )}
            {configuredDecisionProviders.length === 0 ? (
              <option value="">No hay proveedores disponibles</option>
            ) : (
              configuredDecisionProviders.map((p) => (
                <option key={p.provider} value={p.provider}>
                  {p.label}
                </option>
              ))
            )}
            </select>
          </div>

          <div>
            <div className="text-xs font-medium text-app-text-secondary">
              Modelo de decisión
            </div>
            <select
            value={pendingDecisionModel || ""}
            onChange={(e) => {
              const next = e.target.value || null;
              setPendingDecisionModel(next);
              if (next && pendingDecisionProvider) {
                fetchDecisionInfo(next, pendingDecisionProvider);
              } else {
                setDecisionContextWindow(null);
                setDecisionInputLimit(null);
                setDecisionOutputLimit(null);
                setDecisionInputModalities(null);
                setDecisionOutputModalities(null);
                setDecisionCostInput(null);
                setDecisionCostOutput(null);
              }
            }}
            disabled={!decisionEnabled || savingDecision || decisionModelsFor(pendingDecisionProvider).length === 0}
            className="mt-1 w-full rounded-lg border border-app-border bg-white px-3 py-2 text-sm text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary-light"
          >
            {decisionModelsFor(pendingDecisionProvider).length === 0 ? (
              <option value="">No hay modelos disponibles</option>
            ) : (
              decisionModelsFor(pendingDecisionProvider).map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))
              )}
            </select>
          </div>

          {(decisionContextWindow !== null || decisionInputLimit !== null || decisionOutputLimit !== null || decisionInputModalities !== null || decisionOutputModalities !== null || decisionCostInput !== null || decisionCostOutput !== null) && (
            <Collapsible title="Info del modelo">
              <div className="space-y-1.5">
                {decisionInputModalities !== null && decisionInputModalities.length > 0 && (
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-app-text-secondary">Entrada</span>
                    <span className="text-app-primary font-medium">{decisionInputModalities.map(m => m.charAt(0).toUpperCase() + m.slice(1)).join(", ")}</span>
                  </div>
                )}
                {decisionOutputModalities !== null && decisionOutputModalities.length > 0 && (
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-app-text-secondary">Salida</span>
                    <span className="text-app-primary font-medium">{decisionOutputModalities.map(m => m.charAt(0).toUpperCase() + m.slice(1)).join(", ")}</span>
                  </div>
                )}
                {decisionContextWindow !== null && (
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-app-text-secondary">Contexto</span>
                    <span className="text-app-primary font-medium">{decisionContextWindow.toLocaleString()} tokens</span>
                  </div>
                )}
                {decisionInputLimit !== null && (
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-app-text-secondary">Entrada máx</span>
                    <span className="text-app-primary font-medium">{decisionInputLimit.toLocaleString()} tokens</span>
                  </div>
                )}
                {decisionOutputLimit !== null && (
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-app-text-secondary">Salida máx</span>
                    <span className="text-app-primary font-medium">{decisionOutputLimit.toLocaleString()} tokens</span>
                  </div>
                )}
                {(decisionCostInput !== null || decisionCostOutput !== null) && (
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-app-text-secondary">Costo</span>
                    <span className="text-app-primary font-medium">
                      {decisionCostInput !== null && `In $${decisionCostInput}`}
                      {decisionCostInput !== null && decisionCostOutput !== null && " · "}
                      {decisionCostOutput !== null && `Out $${decisionCostOutput}`}
                      <span className="text-app-text-secondary font-normal"> /M tok</span>
                    </span>
                  </div>
                )}
              </div>
            </Collapsible>
          )}

          {/* Single Apply button for decision provider + model */}
          <Button
            onClick={handleApplyDecision}
            disabled={
              savingDecision ||
              !pendingDecisionModel ||
              !pendingDecisionProvider ||
              (pendingDecisionModel === currentDecisionModel &&
                pendingDecisionProvider === (currentDecisionProvider || ""))
            }
            variant="gradient"
            className="w-full"
          >
            {savingDecision ? (
              <>
                <svg
                  className="animate-spin -ml-1 mr-2 h-4 w-4"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                Aplicando...
              </>
            ) : (
              "Aplicar"
            )}
          </Button>
          {decisionMessage && (
            <div
              className={`text-xs rounded-lg px-3 py-2 border ${
                decisionMessage.type === "success"
                  ? "text-green-700 bg-green-50 border-green-200"
                  : "text-red-600 bg-red-50 border-red-200"
              }`}
            >
              {decisionMessage.text}
            </div>
          )}
        </div>
      </div>

      {/* API keys de providers */}
      <Collapsible title="API keys de proveedores">
        <p className="text-[11px] text-app-text-secondary mb-2">
          Eleg&iacute; un proveedor y guard&aacute; su API key (queda cifrada en la base local). Se valida al guardar y el proveedor queda disponible de inmediato.
        </p>
        {keysError && (
          <div className="mb-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {keysError}
          </div>
        )}
        <div className="rounded-lg border border-app-border bg-white p-2.5 space-y-2">
          <div className="flex items-center justify-between">
            <select
              value={keyProvider}
              onChange={(e) => {
                setKeyProvider(e.target.value);
                setKeysError(null);
              }}
              className="flex-1 min-w-0 truncate rounded-lg border border-app-border bg-white px-2 py-1.5 text-xs text-app-text focus:outline-none focus:ring-2 focus:ring-app-primary-light"
            >
              {keyOptions.map((o) => (
                <option key={o.provider} value={o.provider}>
                  {o.label}{isKeyConfigured(o.provider) ? " ✓" : ""}
                </option>
              ))}
            </select>
            <div className="flex items-center gap-2 ml-2 shrink-0">
              <span
                className={`w-2 h-2 rounded-full ${
                  isKeyConfigured(keyProvider) ? "bg-green-500" : "bg-app-bg-tertiary"
                }`}
                title={isKeyConfigured(keyProvider) ? "API key configurada" : "Sin API key"}
              />
              {isKeyConfigured(keyProvider) && (
                <button
                  type="button"
                  onClick={() => handleDeleteKey(keyProvider)}
                  disabled={savingKeyProvider !== null}
                  className="text-app-text-secondary hover:text-red-500 transition-colors disabled:opacity-50"
                  aria-label="Eliminar API key guardada"
                  title="Eliminar API key guardada"
                >
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          </div>
          <div className="flex gap-1.5">
            <Input
              type="password"
              value={keyInputs[keyProvider] || ""}
              onChange={(e) => setKeyInputs((prev) => ({ ...prev, [keyProvider]: e.target.value }))}
              placeholder={isKeyConfigured(keyProvider) ? "••••••••" : "sk-..."}
              className="flex-1 text-xs"
              autoComplete="off"
            />
            <Button
              onClick={() => handleSaveKey(keyProvider)}
              disabled={savingKeyProvider !== null || !(keyInputs[keyProvider] || "").trim() || !keyProvider}
              variant="gradient"
              className="px-4 text-xs shrink-0"
            >
              {savingKeyProvider === keyProvider
                ? "..."
                : isKeyConfigured(keyProvider)
                  ? "Modificar"
                  : "Guardar"}
            </Button>
          </div>
        </div>
      </Collapsible>

      {/* Cuentas de mail */}
      <Collapsible title="Cuentas de mail">
        <p className="text-[11px] text-app-text-secondary mb-2">
          Carg&aacute; mail + password + alias opcional (ej. forge, personal). Queda cifrado en la base local.
        </p>
        {emailsError && (
          <div className="mb-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {emailsError}
          </div>
        )}
        <div className="space-y-2">
          {emails.map((m) => (
            <div key={m.alias} className="flex items-center justify-between rounded-lg border border-app-border bg-white px-2 py-1.5">
              <div className="min-w-0 flex-1">
                <div className="text-xs text-app-text break-all" title={`${m.alias} — ${m.email}`}>{m.alias} — {m.email}</div>
                <div className="text-[10px] text-app-text-secondary">{m.provider} · {m.last_status}</div>
              </div>
              <button
                type="button"
                onClick={() => handleDeleteMail(m.alias)}
                disabled={savingMail}
                className="text-app-text-secondary hover:text-red-500 transition-colors disabled:opacity-50 ml-2 shrink-0"
                aria-label={`Eliminar ${m.alias}`}
                title={`Eliminar ${m.alias}`}
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          <div className="rounded-lg border border-app-border bg-white p-2.5 space-y-2">
            <Input
              type="email"
              value={mailEmail}
              onChange={(e) => setMailEmail(e.target.value)}
              placeholder="mail@ejemplo.com"
              className="flex-1 text-xs"
              autoComplete="off"
            />
            <Input
              type="password"
              value={mailPassword}
              onChange={(e) => setMailPassword(e.target.value)}
              placeholder="contraseña o app password"
              className="flex-1 text-xs"
              autoComplete="off"
            />
            <div className="flex gap-1.5">
              <Input
                type="text"
                value={mailAlias}
                onChange={(e) => setMailAlias(e.target.value)}
                placeholder="alias opcional (forge, personal)"
                className="flex-1 text-xs"
                autoComplete="off"
              />
              <Button
                onClick={handleSaveMail}
                disabled={savingMail || !mailEmail.trim() || !mailPassword.trim()}
                variant="gradient"
                className="px-4 text-xs shrink-0"
              >
                {savingMail ? "..." : "Guardar"}
              </Button>
            </div>
          </div>
        </div>
      </Collapsible>

      <div>
        <div className="text-xs font-medium text-app-text-secondary">
          Ventana de contexto
        </div>
        <p className="text-[11px] text-app-text-secondary mt-1">
          Controla cuántos turnos de la conversación se recuerdan al responder. -1 = todo el historial.
        </p>
        <div className="flex gap-2 mt-2">
          <Input
            type="number"
            min={-1}
            value={maxTurns}
            onChange={(e) => {
              const v = Number(e.target.value);
              setMaxTurns(Number.isNaN(v) ? -1 : v < -1 ? -1 : v);
            }}
            className="flex-1"
          />
          <Button onClick={handleSaveContext} disabled={savingContext} variant="gradient">
            Guardar
          </Button>
        </div>
      </div>

      <div className="flex items-center justify-between py-2">
        <div>
          <div className="text-xs font-medium text-app-text-secondary">
            Modo verbose
          </div>
          <p className="text-[11px] text-app-text-secondary mt-1">
            Muestra herramientas y sub-agentes en la conversación.
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={verboseMode}
          onClick={() => onVerboseModeChange(!verboseMode)}
          className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-app-primary-light ${
            verboseMode ? "bg-app-primary" : "bg-app-bg-tertiary"
          }`}
        >
          <span
            className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
              verboseMode ? "translate-x-4" : "translate-x-0"
            }`}
          />
        </button>
      </div>

      {/* Instrucciones y documentos */}
      <div className="pt-2">
        <div className="text-xs font-medium text-app-text-secondary">
          Instrucciones y documentos
        </div>
        <p className="text-[11px] text-app-text-secondary mt-1">
          Archivos con instrucciones, reglas de comportamiento, reglas de negocio o información que el agente debe conocer al responder.
        </p>
        <div className="mt-2">
          <button
            type="button"
            onClick={() => contextFileInputRef.current?.click()}
            disabled={uploadingContext}
            className="flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-app-border bg-white px-3 py-4 text-xs text-app-text-secondary hover:border-app-primary/50 hover:text-app-primary transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Upload size={16} />
            <span>{uploadingContext ? "Subiendo..." : "Subir archivos (PDF, Word, TXT)"}</span>
          </button>
          <input
            ref={contextFileInputRef}
            type="file"
            accept=".pdf,.docx,.doc,.txt,.md,.csv,.json,.yaml,.yml,.xml,.py"
            className="hidden"
            onChange={handleUploadContextFile}
          />
        </div>

        {contextFiles.length > 0 && (
          <div className="mt-3 space-y-1">
            {contextFiles.map((f) => (
              <div
                key={f.id}
                className="flex items-center justify-between rounded-md bg-white px-2 py-1.5 text-xs"
              >
                <span className="truncate text-app-text flex-1 min-w-0">{f.filename}</span>
                <button
                  type="button"
                  onClick={() => handleDeleteContextFile(f.id)}
                  className="ml-2 shrink-0 rounded p-0.5 text-app-text-secondary hover:text-red-500 hover:bg-red-50 transition-colors"
                  aria-label="Eliminar archivo de contexto"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Preferencias del usuario */}
      <div className="pt-2">
        <div className="text-xs font-medium text-app-text-secondary">
          Preferencias del usuario
        </div>
        <p className="text-[11px] text-app-text-secondary mt-1">
          Cosas que el agente debe recordar (idioma, tono, formato, empresa, rol). Se inyectan en cada turno.
        </p>
        <div className="mt-2 flex gap-2">
          <Input
            value={newPreference}
            onChange={(e) => setNewPreference(e.target.value)}
            placeholder="Ej: Prefiero respuestas cortas"
            className="flex-1"
            maxLength={500}
          />
          <Button onClick={handleAddPreference} disabled={savingPreference || !newPreference.trim()}>
            {savingPreference ? "Guardando..." : "Agregar"}
          </Button>
        </div>
        {preferences.length > 0 && (
          <div className="mt-3 space-y-1">
            {preferences.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between rounded-md bg-white px-2 py-1.5 text-xs"
              >
                {editingPreferenceId === p.id ? (
                  <div className="flex flex-1 items-center gap-1 min-w-0">
                    <Input
                      value={editPreferenceText}
                      onChange={(e) => setEditPreferenceText(e.target.value)}
                      className="flex-1 text-xs"
                      maxLength={500}
                      autoFocus
                    />
                    <button
                      type="button"
                      onClick={() => void handleSaveEditPreference(p.id)}
                      disabled={savingEditPreference || !editPreferenceText.trim()}
                      className="shrink-0 rounded p-0.5 text-app-text-secondary hover:text-green-600 transition-colors disabled:opacity-40"
                      aria-label="Guardar edición"
                    >
                      <Check size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={handleCancelEditPreference}
                      disabled={savingEditPreference}
                      className="shrink-0 rounded p-0.5 text-app-text-secondary hover:text-app-text transition-colors disabled:opacity-40"
                      aria-label="Cancelar edición"
                    >
                      <X size={14} />
                    </button>
                  </div>
                ) : (
                  <>
                    <span
                      onClick={() => setExpandedPreferenceId((prev) => (prev === p.id ? null : p.id))}
                      title="Click para ver completo"
                      className={`text-app-text flex-1 min-w-0 cursor-pointer ${expandedPreferenceId === p.id ? "whitespace-pre-wrap break-words" : "truncate"}`}
                    >
                      {p.text}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleStartEditPreference(p.id, p.text)}
                      className="ml-2 shrink-0 rounded p-0.5 text-app-text-secondary hover:text-app-primary transition-colors"
                      aria-label="Editar preferencia"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDeletePreference(p.id)}
                      className="ml-1 shrink-0 rounded p-0.5 text-app-text-secondary hover:text-red-500 hover:bg-red-50 transition-colors"
                      aria-label="Eliminar preferencia"
                    >
                      <Trash2 size={14} />
                    </button>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default ConfigTab;