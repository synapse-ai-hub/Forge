import sys
import os
import json
import time
import uuid
import base64
import functools
import logging
from datetime import datetime
from dotenv import load_dotenv
from typing import Any, Dict, Generator
import asyncio
try:
    # Optional dependency: the LOCAL (Ollama) provider needs the ``ollama``
    # package, but the app must start without it installed.
    from ollama import AsyncClient
except ImportError:
    AsyncClient = None
from google import genai
from google.genai import types
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path so absolute imports (backend.*)
# resolve correctly regardless of where the file is invoked from.
# ---------------------------------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.agent.utils.error_logger import log_error
from backend.agent.utils import provider_keys
from backend.agent.utils.contract import (
    ContractResponse,
    UsageReport,
    make_error_response,
    make_success_response,
    validate_response,
    zero_usage,
)

from backend.agent.tools import Tools

from backend.agent.utils.model_catalog import translate_reasoning, get_reasoning_streaming_config, get_provider_api_type
from backend.agent.utils.spend_handler import calculate_cost, record_spend

# Marcadores de comentarios usados en este proyecto:
# TODO   : trabajo pendiente, todavía no implementado.
# FIXME  : hay un bug conocido; este código falla o es incorrecto.
# REVIEW : parte del código que debe ser revisada o validada por otra persona.
# NOTE   : aclaración importante sobre decisiones o comportamiento no obvio.
# HACK   : solución provisoria / poco elegante / hardcodeada, usada para salir del paso.
# DEBUG  : código o mensajes usados solo para depuración temporal.
# OK     : bloque probado y estable en las condiciones actuales.
# PROD   : código / config específica de producción; tocar con extremo cuidado.

_LEGACY_API_TYPES: dict[str, str] = {
    "groq": "openai-compatible",
    "openrouter": "openai-compatible",
    "openai": "openai-compatible",
    "deepseek": "openai-compatible",
    "xai": "openai-compatible",
    "togetherai": "openai-compatible",
    "fireworks-ai": "openai-compatible",
    "cerebras": "openai-compatible",
    "mistral": "openai-compatible",
    "perplexity": "openai-compatible",
    "meta": "openai-compatible",
    "moonshotai": "openai-compatible",
    "zhipuai": "openai-compatible",
    "alibaba": "openai-compatible",
    "google": "google",
    "LOCAL": "ollama",
}
"""Fallback name-based API types.

Used only when the local catalog has no rows for the provider (e.g.
sync never ran). Keeps the pre-refactor behavior for the known
providers instead of rejecting them.
"""


def _resolve_api_type(effective_provider: str | None) -> tuple[str, str]:
    """Resolve provider name and API type for LLM dispatch.

    Args:
        effective_provider: Provider name or ``None``.

    Returns:
        Tuple ``(provider, api_type)`` where ``provider`` is the name
        as configured (``""`` when missing) and ``api_type`` is
        ``"openai-compatible"``, ``"google"``, ``"ollama"`` or
        ``"unknown"``.
    """
    provider_u = (effective_provider or "").strip()
    api_type = get_provider_api_type(effective_provider or "")
    if api_type == "unknown":
        api_type = _LEGACY_API_TYPES.get(provider_u, "unknown")
    return provider_u, api_type


load_dotenv()  

def _signature_to_str(signature: Any) -> str | None:
    """Encode a Gemini thought signature (bytes) to a JSON-safe string.

    Args:
        signature: Raw signature from ``part.thought_signature`` (bytes or str).

    Returns:
        Base64 string, the original value if already a string, or ``None``.
    """
    if isinstance(signature, (bytes, bytearray)):
        try:
            return base64.b64encode(bytes(signature)).decode("ascii")
        except Exception as e:
            log_error(str(e), source="agent.py:_signature_to_str")
            return None
    return signature if isinstance(signature, str) else None


def _signature_from_str(value: Any) -> Any:
    """Decode a thought signature previously encoded with
    :func:`_signature_to_str`.

    Args:
        value: Base64 string, raw bytes or ``None``.

    Returns:
        Bytes ready to be sent to the Gemini API, or ``None``.
    """
    if isinstance(value, str):
        try:
            return base64.b64decode(value)
        except Exception as e:
            log_error(str(e), source="agent.py:_signature_from_str")
            return None
    return value if isinstance(value, (bytes, bytearray)) else None


class Agent():
    '''
    Core class for interacting with LLMs (cloud APIs or local Ollama) with
    integrated logging and file management.

    This class centralizes interaction with LLM providers and provides helper
    utilities for cleaning outputs and simple file I/O.

    The provider and model are resolved at runtime (see
    ``backend/agent/utils/model_resolver.py``) and set through the
    ``POST /api/config/models/select`` endpoint; they are not read from
    environment variables. API keys are resolved exclusively from the
    encrypted DB storage (see ``provider_keys``) and are used to build the
    cloud clients.

    ## Attributes:
        - __google_api_key (str): API key for the Google GenAI client.
        - provider (str | None): ``LOCAL`` or any curated cloud provider
          name; set at runtime by the model selection endpoint.
        - _resolved_model (str | None): Currently resolved model identifier.
        - _context_window (int | None): Context window (tokens) of the
          resolved model.
        - _openai_clients (dict): OpenAI-compatible clients, one per
          curated provider with a stored key.
        - google_client (genai.Client | None): Instantiated Google GenAI
          client (only if a Google API key is available).
        - ollama_client (AsyncClient | None): Instantiated Ollama client
          (only if the local service is reachable).
        - usage (tuple | None): Last request usage metrics in the form
          (prompt_tokens, completion_tokens, total_tokens, prompt_time,
          completion_time, total_time).

    ## Notes:
        - For any curated OpenAI-compatible provider:
          requires its API key stored in the DB.
        - For provider ``GOOGLE``: requires a Google API key stored in the DB.
        - For provider ``LOCAL``: requires ``ollama`` installed
          (``pip install ollama``) and the service running.
        - Methods that call the API catch exceptions and print errors rather
          than raising; callers should handle missing return values
          accordingly.

    ## Example:
        >>> import asyncio
        >>> from backend.agent.agent import Agent
        >>> agent = Agent()
        >>> resp, usage = asyncio.run(agent.llm_process("qwen/qwen3.6-27b", "What is the capital of France?"))
        >>> print(resp)
        The capital of France is Paris.
    '''
 
    def __init__(self) -> None:
        '''
        Initialize the Agent.

        Always tries to instantiate the LLM clients (every curated
        OpenAI-compatible provider with a stored key, plus Ollama and
        Google) regardless of availability.  If a client cannot be created (e.g.
        missing API key or Ollama not running), the corresponding attribute
        is set to ``None``.

        ``self.provider`` is initially ``None`` and is set by the
        ``POST /api/config/models/select`` endpoint when the user selects
        a model + provider from the frontend.

        ## Raises:
            - None: Exceptions during client creation are caught and the
              attribute is set to ``None``.
        '''
        super().__init__()

        # Resolve API keys: encrypted DB storage only (no env fallback).
        self.__google_api_key = provider_keys.resolve_api_key('google')
        self.provider: str | None = None
        self._resolved_model: str | None = None
        self._context_window: int | None = None

        # OpenAI-compatible clients, one per curated provider with a stored
        # key (see ``provider_keys.PROVIDER_REGISTRY``). Each one uses
        # ``AsyncOpenAI`` with its own ``base_url``.
        self._openai_clients: dict[str, Any] = {}
        try:
            for _pid, _info in provider_keys.PROVIDER_REGISTRY.items():
                if str(_info.get("api_type") or "") != "openai-compatible":
                    continue
                _pkey = provider_keys.resolve_api_key(_pid)
                _base = str(_info.get("base_url") or "").rstrip("/")
                if _pkey and _base:
                    self._openai_clients[_pid] = AsyncOpenAI(
                        base_url=_base, api_key=_pkey
                    )
        except Exception as e:
            log_error(str(e), source="agent.py:__init__(openai_clients)")
            self._openai_clients = {}

        # Always try to create the remaining clients.  The frontend dropdown
        # will only show providers whose client initialised successfully.
        try:
            # ``ollama`` is an optional dependency: if the package is not
            # installed the LOCAL provider is simply unavailable.
            self.ollama_client = (
                AsyncClient(host='http://localhost:11434')
                if AsyncClient is not None
                else None
            )
        except Exception as e:
            log_error(str(e), source="agent.py:__init__(ollama)")
            self.ollama_client = None
            
        try:
            # Sin key no se construye el cliente: genai.Client(api_key=None)
            # levanta a mitad de __init__ y el objeto a medio construir
            # dispara "Task exception was never retrieved" en aclose()
            # cuando el GC lo reclama (BaseApiClient.__del__).
            self.google_client = (
                genai.Client(api_key=self.__google_api_key)
                if self.__google_api_key
                else None
            )
        except Exception as e:
            log_error(str(e), source="agent.py:__init__(google)")
            self.google_client = None

        self.usage = None

        # Cache de prompts cargados desde archivos (evita lecturas repetitivas)
        self._prompt_cache: Dict[str, str] = {}
        # Ruta al directorio de prompts.
        # En desarrollo: intelligence/prompts/ relativo a la raiz del proyecto.
        # En compilado (PyInstaller): se toma de sys._MEIPASS (embebido con --add-data).
        if getattr(sys, 'frozen', False):
            _base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        else:
            _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            _base = _project_root

        self.tools = Tools()

    def rebuild_provider_client(self, provider: str) -> dict:
        """Rebuild the LLM client for a provider with the current API key.

        Resolves the key from the encrypted DB storage, then re-instantiates
        the client so a key saved at runtime takes effect without restarting
        the app.

        Args:
            provider: Curated provider name (see
                ``provider_keys.PROVIDER_REGISTRY``) or ``LOCAL``.

        Returns:
            Contract response ``{"status": "success"|"error", "message": ...}``.
        """
        provider_u = (provider or "").strip()
        try:
            if provider_u == 'google':
                key = provider_keys.resolve_api_key('google')
                self.__google_api_key = key
                self.google_client = genai.Client(api_key=key) if key else None
            elif provider_u in provider_keys.PROVIDER_REGISTRY:
                info = provider_keys.PROVIDER_REGISTRY[provider_u]
                if str(info.get("api_type") or "") != "openai-compatible":
                    return {"status": "error", "message": f"Provider inválido: '{provider}'."}
                key = provider_keys.resolve_api_key(provider_u)
                base_url = str(info.get("base_url") or "").rstrip("/")
                client = (
                    AsyncOpenAI(base_url=base_url, api_key=key)
                    if key and base_url
                    else None
                )
                self._openai_clients[provider_u] = client
            else:
                return {"status": "error", "message": f"Provider inválido: '{provider}'."}
            return {"status": "success", "message": f"Cliente de {provider_u} actualizado."}
        except Exception as e:
            log_error(str(e), source="agent.py:rebuild_provider_client")
            return {"status": "error", "message": f"Error reconstruyendo el cliente: {e}"}

    def get_openai_client(self, provider: str) -> Any | None:
        """Return the OpenAI-compatible client for a provider, if available.

        Resolves to its ``AsyncOpenAI`` entry in ``_openai_clients``. Returns ``None`` when
        the provider has no stored key (or is not OpenAI-compatible).

        Args:
            provider: Provider name (case-insensitive).

        Returns:
            The client instance, or ``None`` if unavailable.
        """
        try:
            provider_u = (provider or "").strip()
            return self._openai_clients.get(provider_u)
        except Exception as e:
            log_error(str(e), source="agent.py:get_openai_client")
            return None

    @property
    def default_model(self) -> str:
        """Return the resolved model name.

        The model must be selected via ``POST /api/config/models/select``
        (see :mod:`backend.routes.config`). If no model has been selected
        yet, returns an empty string.

        Returns:
            The selected model name string, or empty if not yet selected.
        """
        if self._resolved_model is not None:
            return self._resolved_model
        logger.warning("No model selected yet. Use POST /api/config/models/select to set one.")
        return ''

    def _normalize_tool_calls(self, tool_calls: list[Any] | None) -> list[dict[str, Any]] | None:
        """Normalize raw tool_calls to uniform ``{"id", "name", "args"}``.

        Args:
            tool_calls: Raw tool_calls from the API (OpenAI-compatible or Ollama format).

        Returns:
            Normalized list, or ``None`` if empty.
        """
        if not tool_calls:
            return None
        normalized = []
        for tc in tool_calls:
            entry: dict[str, Any] = {}
            # Gemini style dict built in the GOOGLE branch:
            # {"name", "args", "signature"}.
            if isinstance(tc, dict):
                entry["id"] = f"call_{uuid.uuid4().hex}"
                entry["name"] = tc.get("name") or ""
                args = tc.get("args")
                entry["args"] = args if isinstance(args, dict) else {}
                if tc.get("signature"):
                    entry["thought_signature"] = tc["signature"]
                normalized.append(entry)
                continue
            # Gemini FunctionCall style: name/args directly on the object,
            # no id and no nested function attribute.
            if not hasattr(tc, "function"):
                try:
                    entry["id"] = f"call_{uuid.uuid4().hex}"
                    entry["name"] = tc.name
                except AttributeError as e:
                    log_error(str(e), source="agent.py:_normalize_tool_calls(gemini)")
                    continue
                args = getattr(tc, "args", None)
                entry["args"] = args if isinstance(args, dict) else {}
                normalized.append(entry)
                continue
            try:
                entry["id"] = tc.id
            except AttributeError as e:
                log_error(str(e), source="agent.py:_normalize_tool_calls(id)")
                entry["id"] = ""
            # OpenAI-compatible APIs always provide an id; Ollama may omit it. Generate one so
            # the assistant message and the tool result stay linked.
            if not entry["id"]:
                entry["id"] = f"call_{uuid.uuid4().hex}"
            try:
                entry["name"] = tc.function.name
            except AttributeError as e:
                log_error(str(e), source="agent.py:_normalize_tool_calls(name)")
                continue
            try:
                args_raw = tc.function.arguments
                if isinstance(args_raw, str):
                    entry["args"] = json.loads(args_raw) if args_raw else {}
                elif isinstance(args_raw, dict):
                    entry["args"] = args_raw
                else:
                    entry["args"] = {}
            except (AttributeError, json.JSONDecodeError) as e:
                log_error(str(e), source="agent.py:_normalize_tool_calls(args)")
                entry["args"] = {}
            normalized.append(entry)
        return normalized if normalized else None

    def _to_provider_tool_calls(
        self, tool_calls: list[dict[str, Any]], is_openai_compatible: bool
    ) -> list[dict[str, Any]]:
        """Convert normalized tool_calls to the SDK format each provider expects.

        Normalized tool_calls have the shape
        ``{"id", "name", "args"}``. Both OpenAI-compatible providers
        and Ollama expect the wrapped shape
        ``{"id", "type": "function", "function": {"name", "arguments"}}``,
        but they differ in how ``arguments`` is encoded:

        - **OpenAI-compatible**: ``function.arguments`` must be a **JSON string**.
        - **Ollama**: ``function.arguments`` must be a **dict**.

        Args:
            tool_calls: Normalized list (``{"id", "name", "args"}``) or a
                list that is already in SDK format (has a ``function`` key).
            is_openai_compatible: ``True`` for OpenAI-compatible providers,
                ``False`` for Ollama.

        Returns:
            List of tool_calls in the provider's expected format.
        """
        out: list[dict[str, Any]] = []
        for tc in tool_calls:
           
            # the arguments encoding for the current provider.
            if "function" in tc:
                func = dict(tc["function"])
                args = func.get("arguments")
                if is_openai_compatible and isinstance(args, dict):
                    func["arguments"] = json.dumps(args, ensure_ascii=False)
                elif not is_openai_compatible and isinstance(args, str):
                    try:
                        func["arguments"] = json.loads(args)
                    except (json.JSONDecodeError, TypeError) as e:
                        log_error(str(e), source="agent.py:_to_provider_tool_calls(func_args)")
                out.append(
                    {
                        "id": tc.get("id") or f"call_{uuid.uuid4().hex}",
                        "type": "function",
                        "function": func,
                    }
                )
                continue
            # Normalized format: {"id", "name", "args"}
            tc_id = tc.get("id") or f"call_{uuid.uuid4().hex}"
            args = tc.get("args", {})
            if is_openai_compatible:
                try:
                    func_args = json.dumps(args, ensure_ascii=False)
                except (TypeError, ValueError) as e:
                    log_error(str(e), source="agent.py:_to_provider_tool_calls(func_args)")
                    func_args = json.dumps({}, ensure_ascii=False)
            else:
                func_args = args
            out.append(
                {
                    "id": tc_id,
                    "type": "function",
                    "function": {
                        "name": tc.get("name", ""),
                        "arguments": func_args,
                    }
                }
            )
        return out

    def _sanitize_gemini_schema(self, schema: Any) -> Any:
        """Recursively strip JSON-Schema keys not supported by Gemini.

        Gemini's ``Schema`` only accepts a subset of JSON Schema
        (``type``, ``description``, ``properties``, ``required``, ``items``,
        ``enum``, ``format``). Keys like ``additionalProperties`` or
        ``$schema`` cause 400 errors, so they are removed here.

        Args:
            schema: A JSON Schema dict (or any value).

        Returns:
            The sanitized schema.
        """
        if not isinstance(schema, dict):
            return schema
        allowed = ("type", "description", "properties", "required",
                   "items", "enum", "format")
        out: dict[str, Any] = {}
        for k, v in schema.items():
            if k not in allowed:
                continue
            if k == "properties" and isinstance(v, dict):
                out[k] = {pk: self._sanitize_gemini_schema(pv) for pk, pv in v.items()}
            elif k == "items":
                out[k] = self._sanitize_gemini_schema(v)
            else:
                out[k] = v
        return out

    def _to_gemini_tools(self, tools: list[dict[str, Any]] | None) -> list[Any]:
        """Convert OpenAI-format tool schemas to Gemini ``Tool`` declarations.

        Args:
            tools: Tool definitions in OpenAI format
                (``{"type": "function", "function": {...}}``).

        Returns:
            List with a single ``types.Tool`` holding all function
            declarations, or an empty list when no tools are given.
        """
        if not tools:
            return []
        declarations: list[types.FunctionDeclaration] = []
        for t in tools:
            fn = t.get("function", t)
            params = fn.get("parameters")
            declarations.append(types.FunctionDeclaration(
                name=fn.get("name"),
                description=fn.get("description") or "",
                parameters=self._sanitize_gemini_schema(params) if params else None,
            ))
        return [types.Tool(function_declarations=declarations)]

    def _to_gemini_contents(
        self, msgs: list[dict[str, Any]]
    ) -> tuple[list[types.Content], str | None]:
        """Convert OpenAI-style messages to Gemini ``Content`` objects.

        Mapping rules:

        - ``system`` → accumulated into the returned system instruction.
        - ``user`` → ``role="user"`` with a text part.
        - ``assistant`` with ``tool_calls`` → ``role="model"`` with one
          ``function_call`` part per call (plus its text, if any).
        - ``tool`` → ``role="user"`` with a ``function_response`` part whose
          payload is the parsed JSON of the tool result (or a string wrapper).
        - ``assistant`` plain → ``role="model"`` with a text part.

        Consecutive messages with the same role are merged into a single
        ``Content`` so the history always alternates roles as Gemini requires.

        Args:
            msgs: Messages array in OpenAI format.

        Returns:
            Tuple ``(contents, system_instruction)`` where ``contents`` is
            the list of ``types.Content`` and ``system_instruction`` is the
            concatenated system prompt (or ``None``).
        """
        contents: list[types.Content] = []
        system_instruction: str | None = None
        # Map tool_call_id -> function name so role:"tool" messages without
        # an explicit tool_name can still be linked to their functionCall.
        id_to_name: dict[str, str] = {}

        def _append(role: str, part: types.Part) -> None:
            if contents and contents[-1].role == role:
                contents[-1].parts.append(part)
            else:
                contents.append(types.Content(role=role, parts=[part]))

        for m in msgs:
            role = m.get("role")
            if role == "system":
                text = str(m.get("content") or "")
                system_instruction = (
                    f"{system_instruction}\n\n{text}" if system_instruction else text
                )
                continue

            if role == "tool":
                fn_name = m.get("tool_name") or id_to_name.get(m.get("tool_call_id", ""), "")
                raw = m.get("content")
                # Strip <tool_output> wrapper if present so JSON payloads
                # wrapped in loop.py keep parsing exactly as before.
                # Unwrapped content (creators, old history) is unchanged.
                if isinstance(raw, str) and "<tool_output" in raw and "</tool_output>" in raw:
                    try:
                        start = raw.index(">") + 1
                        end = raw.rindex("</tool_output>")
                        raw = raw[start:end].strip()
                    except (ValueError, AttributeError):
                        pass
                try:
                    payload = json.loads(raw) if isinstance(raw, str) else raw
                except (json.JSONDecodeError, TypeError):
                    payload = {"result": str(raw)}
                if not isinstance(payload, dict):
                    payload = {"result": payload}
                _append("user", types.Part(function_response=types.FunctionResponse(
                    name=fn_name,
                    response=payload,
                )))
                continue

            tcs = m.get("tool_calls")
            if tcs:
                text = m.get("content")
                if text:
                    _append("model", types.Part(text=str(text)))
                for tc in tcs:
                    # Accept both normalized {"id","name","args"} and SDK
                    # wrapped {"id","type","function":{"name","arguments"}}.
                    fn = tc.get("function") if isinstance(tc.get("function"), dict) else tc
                    tc_id = tc.get("id") or ""
                    name = fn.get("name") or ""
                    if tc_id:
                        id_to_name[tc_id] = name
                    args = fn.get("args", fn.get("arguments")) or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    if not isinstance(args, dict):
                        args = {}
                    fc_part = types.Part(function_call=types.FunctionCall(
                        name=name,
                        args=args,
                    ))
                    # Gemini 3.x requires the thought_signature captured from
                    # the original response to be sent back with each
                    # functionCall part when replaying history.
                    sig = _signature_from_str(tc.get("thought_signature"))
                    if sig:
                        fc_part.thought_signature = sig
                    _append("model", fc_part)
                continue

            g_role = "user" if role == "user" else "model"
            _append(g_role, types.Part(text=str(m.get("content") or "")))

        return contents, system_instruction

    def _record_spend(self, provider: str | None, model: str, usage: dict | None) -> None:
        """Record token usage and cost for a completed LLM call.

        Cloud providers only: LOCAL/Ollama has no cost and is never
        recorded. Every cloud call counts — chat, tools, creators, tasks,
        agenda and skills — even when no usage report was captured (the
        request is then counted with zero tokens). Failures are logged and
        swallowed so they never break the calling flow.

        Args:
            provider: The provider name (e.g. ``"OPENAI"``, ``"GOOGLE"``).
            model: The model identifier.
            usage: The usage report dict (``prompt_tokens``, ``completion_tokens``).
        """
        try:
            if (provider or "").strip() == "LOCAL":
                return
            usage = usage or {}
            provider_name = (provider or "unknown").strip()
            prompt_tokens = usage.get("prompt_tokens") or 0
            completion_tokens = usage.get("completion_tokens") or 0
            cost_input, cost_output, _ = calculate_cost(
                provider_name, model, prompt_tokens, completion_tokens
            )
            record_spend(
                provider_name, model, prompt_tokens, completion_tokens,
                cost_input, cost_output,
            )
        except Exception as exc:
            log_error(str(exc), source="agent.py:_record_spend")
            logger.warning("Failed to record spend: %s", exc)

    async def llm_process(self, model: str, prompt: str | None = None,
                          system_content: str | None = None,
                          messages: list[dict[str, Any]] | None = None,
                          temperature: float | None = None,
                          top_p: float | None = None,
                          max_tokens: int | None = None,
                          cleaned_output: bool = True,
                           tools: list | None = None,
                           json_format: bool = False,
                           response_format: str | None = None,
                           reasoning: bool = True,
                           budget_tokens: int | None = None,
                           provider: str | None = None,
                           **kwargs) -> ContractResponse:
        """Send a chat completion and return content + tool_calls.

        Accepts either the classic ``prompt`` + ``system_content`` (backwards
        compatible) OR a full ``messages`` array.  When ``messages`` is provided,
        ``prompt`` and ``system_content`` are ignored.

        Args:
            model: Model name.
            prompt: User prompt (ignored if ``messages`` is set).
            system_content: System instruction (ignored if ``messages`` is set).
            messages: Full messages array (``role``, ``content``, ``tool_calls``, …).
            temperature: Sampling temperature (``None`` = provider default).
            top_p: Nucleus sampling (``None`` = provider default).
            max_tokens: Max output tokens (``None`` = provider default).
            cleaned_output: Apply ``self.clean()`` to text content.
            tools: Tool definitions for function calling.
            json_format: Force JSON output. For OpenAI-compatible providers: adds ``response_format={"type": "json_object"}``.
                         For Ollama: adds ``format="json"`` to the request.
            response_format: Structured-output mode (``"text"``/``"json"``/``None``).
                         ``"json"`` behaves like ``json_format=True`` on every
                         provider (OpenAI-compatible ``response_format``,
                         Ollama ``format="json"``, Gemini
                         ``response_mime_type="application/json"``).
                         ``"text"``/``None`` means plain text (default).
            reasoning: Whether to allow the model to reason (thinking). When
                        ``False``, reasoning is disabled on providers that support
                        it (e.g. Ollama ``think=False``)
                        with a fallback so models that don't support the flag are
                        not broken.
            budget_tokens: Token budget for reasoning (OpenRouter/Gemini).
                        ``None`` means the provider default.
            provider: Optional provider override (any curated provider id,
                        e.g. ``"OPENAI"``, ``"GOOGLE"``, or ``"LOCAL"``).
                       When ``None``, falls back to ``self.provider`` so existing
                       callers keep their current behavior. Pass an explicit value
                       from the agent loop when a sub-agent overrides the provider
                       in its frontmatter.
            **kwargs: Forwarded to the provider client.

        Returns:
            ``ContractResponse`` with:
            - ``data`` — text content (cleaned if requested).
            - ``tool_calls`` — normalized list ``{"id", "name", "args"}`` or ``None``.
            - ``usage`` — token / time report.
        """
        effective_provider = provider if provider is not None else self.provider
        provider_u, api_type = _resolve_api_type(effective_provider)
        try:
            # Wall-clock for unified timing: time-to-first-token and total
            # time are always measured client-side, the same way for every
            # provider (no native provider timing is used).
            _proc_t0 = time.time()
            # --- Build messages ---
            if messages is not None:
                # OpenAI-compatible/LOCAL need SDK-wrapped tool_calls; GOOGLE
                # keeps the normalized form (its converter reads it directly
                # and must preserve extra keys like ``thought_signature``).
                needs_sdk_tc = api_type in ('openai-compatible', 'ollama')
                msgs = []
                for m in messages:
                    m_copy = dict(m)
                    tcs = m_copy.get("tool_calls")
                    if tcs and isinstance(tcs, list) and needs_sdk_tc:
                        m_copy["tool_calls"] = self._to_provider_tool_calls(
                            tcs,
                            api_type == 'openai-compatible',
                        )
                    msgs.append(m_copy)
            else:
                msgs = []
                if system_content:
                    msgs.append({'role': 'system', 'content': system_content})
                msgs.append({'role': 'user', 'content': prompt or ''})

            api_kwargs = {}
            if temperature is not None:
                api_kwargs['temperature'] = temperature
            if top_p is not None:
                api_kwargs['top_p'] = top_p
            if max_tokens is not None:
                api_kwargs['max_tokens'] = max_tokens

            if api_type == 'openai-compatible':
                # ── OpenAI-compatible providers (registry) ──
                client = self._openai_clients.get(provider_u)
                if client is None:
                    return validate_response(make_error_response(
                        message=f"Cliente no disponible para el provider '{effective_provider}': falta la API key."
                    ))
                oa_kwargs = dict(api_kwargs)
                if tools:
                    oa_kwargs["tools"] = tools
                    oa_kwargs["tool_choice"] = "auto"
                if json_format or response_format == "json":
                    oa_kwargs["response_format"] = {"type": "json_object"}

                reasoning_kwargs = translate_reasoning(
                    provider=effective_provider,
                    reasoning_value=reasoning,
                    model_id=model,
                    budget_tokens=budget_tokens,
                )
                if reasoning_kwargs:
                    oa_kwargs.setdefault("extra_body", {}).update(reasoning_kwargs)

                try:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=msgs,
                        **oa_kwargs,
                        **kwargs,
                    )
                except Exception as _ex:
                    if "reasoning" in str(_ex).lower():
                        extra = oa_kwargs.get("extra_body", {})
                        extra.pop("reasoning", None)
                        extra.pop("reasoning_effort", None)
                        extra.pop("reasoning_format", None)
                        response = await client.chat.completions.create(
                            model=model,
                            messages=msgs,
                            **oa_kwargs,
                            **kwargs,
                        )
                    else:
                        raise
                output = response.choices[0].message.content or ""
                raw_tc = response.choices[0].message.tool_calls
                if cleaned_output and output:
                    output = self.clean(output)
                completion_tokens = response.usage.completion_tokens
                prompt_tokens = response.usage.prompt_tokens
                total_tokens = response.usage.total_tokens
                total_time = round(time.time() - _proc_t0, 2)

            elif api_type == 'ollama':
                # ── Ollama (local) ──
                options = {}
                if temperature is not None:
                    options['temperature'] = temperature
                if top_p is not None:
                    options['top_p'] = top_p
                if max_tokens is not None:
                    options['num_predict'] = max_tokens
                for k in ('seed', 'num_ctx', 'top_k', 'min_p', 'repeat_penalty',
                          'frequency_penalty', 'presence_penalty', 'mirostat',
                          'mirostat_tau', 'mirostat_eta', 'typical_p', 'tfs_z',
                          'num_thread', 'num_gpu', 'stop'):
                    if k in kwargs:
                        options[k] = kwargs.pop(k)
                for k in list(kwargs):
                    print(f'[WARN] Ollama no soporta el parámetro "{k}". Será ignorado.', flush=True)
                    kwargs.pop(k)

                chat_kwargs = dict(
                    model=model,
                    messages=msgs,
                    tools=tools if tools else None,
                    format="json" if (json_format or response_format == "json") else None,
                    options=options,
                    keep_alive=-1,
                )
                # Handle reasoning parameter for Ollama
                # reasoning can be: True/False (legacy), or string values:
                # "on"/"off", "low"/"medium"/"high"/"max", "default"
                if reasoning is True or reasoning == "on" or reasoning == "true":
                    response = await self.ollama_client.chat(**chat_kwargs)
                elif reasoning is False or reasoning == "off" or reasoning == "false":
                    # Disable reasoning (think=False). Some models don't support
                    # the think flag; fall back to a request without it.
                    try:
                        response = await self.ollama_client.chat(**chat_kwargs, think=False)
                    except Exception as _ex:
                        if "does not support thinking" in str(_ex):
                            response = await self.ollama_client.chat(**chat_kwargs)
                        else:
                            raise
                elif isinstance(reasoning, str) and reasoning in ("low", "medium", "high", "max"):
                    # GPT-OSS style levels or Qwen max
                    try:
                        response = await self.ollama_client.chat(**chat_kwargs, think=reasoning)
                    except Exception as _ex:
                        # Fallback: try without think parameter
                        response = await self.ollama_client.chat(**chat_kwargs)
                else:
                    # Default: let the model use its default behavior
                    response = await self.ollama_client.chat(**chat_kwargs)
                output = response.message.content or ""
                raw_tc = response.message.tool_calls
                if cleaned_output and output:
                    output = self.clean(output)
                completion_tokens = response.eval_count or 0
                prompt_tokens = response.prompt_eval_count or 0
                total_tokens = (response.eval_count or 0) + (response.prompt_eval_count or 0)
                total_time = round(time.time() - _proc_t0, 2)
            elif api_type == 'google':
                # ── Google Gemini ──
                contents, system_instruction = self._to_gemini_contents(msgs)
                config_kwargs: dict[str, Any] = {}
                if temperature is not None:
                    config_kwargs['temperature'] = temperature
                if top_p is not None:
                    config_kwargs['top_p'] = top_p
                if max_tokens is not None:
                    config_kwargs['max_tokens'] = max_tokens
                if system_instruction:
                    config_kwargs['system_instruction'] = system_instruction
                gemini_tools = self._to_gemini_tools(tools)
                if gemini_tools:
                    config_kwargs['tools'] = gemini_tools
                if response_format == "json":
                    config_kwargs['response_mime_type'] = 'application/json'

                # Use translator for reasoning (Google)
                reasoning_kwargs = translate_reasoning(
                    provider=effective_provider,
                    reasoning_value=reasoning,
                    model_id=model,
                    budget_tokens=budget_tokens,
                )
                if "thinking_config" in reasoning_kwargs:
                    config_kwargs["thinking_config"] = reasoning_kwargs["thinking_config"]

                response = await self.google_client.aio.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(**config_kwargs),
                )

                output = ""
                try:
                    output = response.text or ""
                except ValueError:
                    # No text part (e.g. function-call-only response)
                    output = ""
                raw_tc = []
                candidate = (response.candidates or [None])[0]
                for part in ((candidate.content.parts if candidate and candidate.content else None) or []):
                    fc = getattr(part, "function_call", None)
                    if fc is not None and fc.name:
                        raw_tc.append({
                            "name": fc.name,
                            "args": dict(fc.args or {}),
                            # Gemini 3.x thought signature (lives on the Part);
                            # must be replayed with the functionCall on the
                            # next request. Base64-encoded so it survives JSON
                            # persistence in the session store.
                            "signature": _signature_to_str(getattr(part, "thought_signature", None)),
                        })
                completion_tokens = 0
                prompt_tokens = 0
                total_tokens = 0
                if response.usage_metadata:
                    completion_tokens = response.usage_metadata.candidates_token_count or 0
                    prompt_tokens = response.usage_metadata.prompt_token_count or 0
                    total_tokens = response.usage_metadata.total_token_count or 0
                total_time = round(time.time() - _proc_t0, 2)
            else:
                return validate_response(make_error_response(message=f"PROVIDER inválido: '{effective_provider}'"))

            tool_calls = self._normalize_tool_calls(raw_tc)

            self._record_spend(effective_provider, model, {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'total_time': total_time,
            })

            return validate_response(make_success_response(
                message='Proceso ok.',
                data=output,
                tool_calls=tool_calls,
                usage={
                    'prompt_tokens': prompt_tokens,
                    'completion_tokens': completion_tokens,
                    'total_tokens': total_tokens,
                    'total_time': total_time,
                    # Non-streaming: the first token arrives with the full
                    # response, so latency to first token equals total time.
                    'time_to_first_token': total_time,
                },
            ))
        except Exception as e:
            print(f'Error al procesar con LLM.\n{str(e)}')
            log_error(str(e), source="agent.py:llm")
            # Count the failed request in spend (zero tokens) so the
            # requests counter stays consistent with the messages log.
            try:
                self._record_spend(effective_provider, model, None)
            except Exception:
                pass
            return validate_response(make_error_response(
                message=str(e),
                usage={
                    'prompt_tokens': 0,
                    'completion_tokens': 0,
                    'total_tokens': 0,
                    'total_time': 0,
                },
            ))
     

    async def llm_streaming(self, model: str, prompt: str | None = None,
                             system_content: str = '',
                             messages: list[dict[str, Any]] | None = None,
                             temperature: float = 0,
                             top_p: float = 0.5, max_tokens: int = 3000,
                             cleaned_output: bool = True,
                             tools: list | None = None,
                             stream_cancel_event=None,
                             provider: str | None = None,
                             reasoning: bool = True,
                             budget_tokens: int | None = None,
                             **kwargs):
        """Async generator that streams LLM response chunks.

        Accepts either ``prompt`` + ``system_content`` (backwards compatible)
        OR a full ``messages`` array.  When ``messages`` is provided,
        ``prompt`` and ``system_content`` are ignored.

        During streaming, content chunks are yielded as:

        ``{'type': 'chunk', 'content': str}``

        If ``stream_cancel_event`` is set the generator yields
        ``{'type': 'aborted'}`` and stops.

        Args:
            model: Model name.
            prompt: User prompt (ignored if ``messages`` is set).
            system_content: System instruction (ignored if ``messages`` is set).
            messages: Full messages array.
            temperature: Sampling temperature.
            top_p: Nucleus sampling.
            max_tokens: Max output tokens.
            cleaned_output: Apply ``self.clean()`` to text chunks.
            tools: Tool definitions for function calling.
            stream_cancel_event: Optional event to cancel mid-stream.
provider: Optional provider override (any curated provider id,
                        e.g. ``"OPENAI"``, ``"GOOGLE"``, or ``"LOCAL"``).
                        When ``None``, falls back to ``self.provider`` so existing
                        callers keep their current behavior. Pass an explicit value
                        from the agent loop when a sub-agent overrides the provider
                        in its frontmatter.
            reasoning: Whether to allow the model to reason (thinking). When
                        ``False``, reasoning is disabled on providers that support
                        it (e.g. Ollama skips the ``think=True`` attempt) with a
                        fallback so models that don't support the flag are not
                        broken. Mirrors the handling in :meth:`llm_process`.
            budget_tokens: Token budget for reasoning (OpenRouter/Gemini).
                        ``None`` means the provider default.
            **kwargs: Forwarded to the provider client.

        Yields:
            Streaming event dicts.
        """
        effective_provider = provider if provider is not None else self.provider
        provider_u, api_type = _resolve_api_type(effective_provider)
        # Structured-output mode arrives via **kwargs (loop passes the raw
        # "text"/"json"/None value). Pop it here so the raw string never
        # reaches a provider SDK, and translate it per api_type below.
        stream_format = kwargs.pop("response_format", None)
        if messages is not None:
            # OpenAI-compatible/LOCAL need SDK-wrapped tool_calls; GOOGLE
            # keeps the normalized form (its converter reads it directly
            # and must preserve extra keys like ``thought_signature``).
            needs_sdk_tc = api_type in ('openai-compatible', 'ollama')
            msgs = []
            for m in messages:
                m_copy = dict(m)
                tcs = m_copy.get("tool_calls")
                if tcs and isinstance(tcs, list) and needs_sdk_tc:
                    m_copy["tool_calls"] = self._to_provider_tool_calls(
                        tcs,
                        api_type == 'openai-compatible',
                    )
                msgs.append(m_copy)
        else:
            msgs = []
            if system_content:
                msgs.append({'role': 'system', 'content': system_content})
            msgs.append({'role': 'user', 'content': prompt or ''})

        if api_type == 'openai-compatible':
            client = self._openai_clients.get(provider_u)
            if client is None:
                yield {'type': 'error', 'content': f"Cliente no disponible para el provider '{effective_provider}': falta la API key."}
                return
            oa_kwargs: dict[str, Any] = {
                "model": model,
                "messages": msgs,
                "stream": True,
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens,
                **kwargs,
            }
            if tools:
                oa_kwargs["tools"] = tools
                oa_kwargs["tool_choice"] = "auto"
            if stream_format == "json":
                oa_kwargs["response_format"] = {"type": "json_object"}

            reasoning_kwargs = translate_reasoning(
                provider=effective_provider,
                reasoning_value=reasoning,
                model_id=model,
                budget_tokens=budget_tokens,
            )
            if reasoning_kwargs:
                oa_kwargs.setdefault("extra_body", {}).update(reasoning_kwargs)

            stream_cfg = get_reasoning_streaming_config(effective_provider)
            if stream_cfg:
                oa_kwargs.setdefault("extra_body", {}).update(stream_cfg)
            oa_kwargs["stream_options"] = {"include_usage": True}
            try:
                stream = await client.chat.completions.create(**oa_kwargs)
            except Exception as _ex:
                if "reasoning" in str(_ex).lower():
                    extra = oa_kwargs.get("extra_body", {})
                    extra.pop("reasoning", None)
                    extra.pop("reasoning_effort", None)
                    extra.pop("reasoning_format", None)
                    stream = await client.chat.completions.create(**oa_kwargs)
                else:
                    raise

            accumulated_tool_calls: dict[int, dict[str, str]] = {}
            in_think_tag = False  #  thinking tag state machine
            has_dedicated_thinking = False  # si vimos delta.reasoning, no parseamos  thinking
            usage_data: dict[str, Any] | None = None
            # Time-to-first-token: wall-clock seconds from the request
            # start to the first text chunk yielded below. Measured
            # client-side, so it works for every provider.
            _stream_t0 = time.time()
            _ttft: float | None = None

            # print(f"[DEBUG-STREAM] Starting stream iteration, oa_kwargs keys: {list(oa_kwargs.keys())}")
            async for chunk in stream:
                # print(f"[DEBUG-CHUNK] chunk type={type(chunk).__name__}, choices={len(chunk.choices) if hasattr(chunk, 'choices') and chunk.choices else 0}, usage={getattr(chunk, 'usage', None)}")
                if stream_cancel_event and stream_cancel_event.is_set():
                    self._record_spend(effective_provider, model, usage_data)
                    yield {'type': 'aborted'}
                    return
                # Capturar usage del chunk final (standard OpenAI field).
                if getattr(chunk, 'usage', None):
                    _u = chunk.usage
                    usage_data = {
                        'prompt_tokens': _u.prompt_tokens,
                        'completion_tokens': _u.completion_tokens,
                        'total_tokens': _u.total_tokens,
                    }
                if chunk.choices:
                    delta = chunk.choices[0].delta

                    # Accumulate streaming tool_calls (OpenAI-compatible providers send them incrementally)
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in accumulated_tool_calls:
                                accumulated_tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                            if tc.id:
                                accumulated_tool_calls[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    accumulated_tool_calls[idx]["name"] = tc.function.name
                                if tc.function.arguments:
                                    accumulated_tool_calls[idx]["arguments"] += tc.function.arguments

                    # OpenAI-compatible reasoning (parsed mode)
                    # print(f"[DEBUG-REASONING] delta.reasoning={getattr(delta, 'reasoning', 'MISSING')!r}, delta.content={getattr(delta, 'content', 'MISSING')!r}")
                    if delta and hasattr(delta, 'reasoning') and delta.reasoning:
                        has_dedicated_thinking = True
                        yield {'type': 'reasoning', 'content': delta.reasoning}
                        await asyncio.sleep(0.01)

                    # Stream text content
                    if delta and delta.content:
                        if _ttft is None:
                            _ttft = round(time.time() - _stream_t0, 3)
                        text = delta.content
                        if has_dedicated_thinking:
                            # Ya tenemos reasoning por campo separado, content es solo answer
                            if cleaned_output:
                                text = self.clean(text)
                            yield {'type': 'chunk', 'content': text}
                            await asyncio.sleep(0.01)
                        else:
                            # Fallback: parsear  thinking tags del content
                            rzn, clean_text, in_think_tag = self._process_think_tags(text, in_think_tag)
                            if rzn:
                                yield {'type': 'reasoning', 'content': rzn}
                                await asyncio.sleep(0.01)
                            if clean_text:
                                if cleaned_output:
                                    clean_text = self.clean(clean_text)
                                yield {'type': 'chunk', 'content': clean_text}
                                await asyncio.sleep(0.01)

            # After stream finishes, record spend (every call counts, even
            # without usage metadata) and yield usage (if captured).
            # ``total_time`` is always measured client-side (wall-clock),
            # the same way for every provider.
            if usage_data is not None:
                usage_data['total_time'] = round(time.time() - _stream_t0, 2)
            self._record_spend(effective_provider, model, usage_data)
            if usage_data is not None:
                usage_data['time_to_first_token'] = _ttft
                yield {'type': 'usage', 'content': usage_data}
            if accumulated_tool_calls:
                normalized: list[dict[str, Any]] = []
                for idx in sorted(accumulated_tool_calls.keys()):
                    tc = accumulated_tool_calls[idx]
                    try:
                        args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    except json.JSONDecodeError as ex:
                        log_error(str(ex), source="agent.py:llm_streaming(provider_args)")
                        args = {}
                    normalized.append({
                        "id": tc["id"],
                        "name": tc["name"],
                        "args": args,
                    })
                yield {'type': 'tool_calls_detected', 'content': normalized}
        elif api_type == 'ollama':
            options = {}
            if temperature is not None:
                options['temperature'] = temperature
            if top_p is not None:
                options['top_p'] = top_p
            if max_tokens:
                options['num_predict'] = max_tokens
            for k in ('seed', 'num_ctx', 'top_k', 'min_p', 'repeat_penalty',
                      'frequency_penalty', 'presence_penalty', 'mirostat',
                      'mirostat_tau', 'mirostat_eta', 'typical_p', 'tfs_z',
                      'num_thread', 'num_gpu', 'stop'):
                if k in kwargs:
                    options[k] = kwargs.pop(k)
            # Ollama: intentar con think=True (modelos con thinking), fallback sin el flag.
            # reasoning can be: True/False (legacy), or string values:
            # "on"/"off", "low"/"medium"/"high"/"max", "default"
            chat_kwargs = dict(model=model, messages=msgs, stream=True,
                               tools=tools if tools else None,
                               format="json" if stream_format == "json" else None,
                               options=options, keep_alive=-1)

            def _try_stream(use_think=False):
                """Create a stream with or without the think flag, or with a specific level."""
                if isinstance(use_think, str) and use_think in ("low", "medium", "high", "max"):
                    # String level for GPT-OSS / Qwen max
                    try:
                        return self.ollama_client.chat(**chat_kwargs, think=use_think)
                    except Exception:
                        return self.ollama_client.chat(**chat_kwargs)
                elif use_think is True or use_think == "on" or use_think == "true":
                    return self.ollama_client.chat(**chat_kwargs, think=True)
                elif use_think is False or use_think == "off" or use_think == "false":
                    try:
                        return self.ollama_client.chat(**chat_kwargs, think=False)
                    except Exception:
                        return self.ollama_client.chat(**chat_kwargs)
                else:
                    # Default: let the model decide
                    return self.ollama_client.chat(**chat_kwargs)

            accumulated_tool_calls: dict[int, dict[str, str]] = {}
            in_think_tag = False
            has_dedicated_thinking = False  # si vimos thinking field, no parseamos <think> tags
            stream = None
            usage_data: dict[str, Any] | None = None
            # Time-to-first-token (see OpenAI-compatible path above).
            _stream_t0 = time.time()
            _ttft: float | None = None
            try:
                stream = await _try_stream(use_think=reasoning)
                async for chunk in stream:
                    if stream_cancel_event and stream_cancel_event.is_set():
                        self._record_spend(effective_provider, model, usage_data)
                        yield {'type': 'aborted'}
                        return
                    # Capturar usage del chunk final (done=True)
                    if getattr(chunk, 'done', False):
                        usage_data = {
                            'prompt_tokens': getattr(chunk, 'prompt_eval_count', 0) or 0,
                            'completion_tokens': getattr(chunk, 'eval_count', 0) or 0,
                            'total_tokens': (getattr(chunk, 'prompt_eval_count', 0) or 0) + (getattr(chunk, 'eval_count', 0) or 0),
                        }
                    # Ollama thinking (DeepSeek R1, gemma4, qwen3.5, etc.)
                    if chunk.message and hasattr(chunk.message, 'thinking') and chunk.message.thinking:
                        has_dedicated_thinking = True
                        yield {'type': 'reasoning', 'content': chunk.message.thinking}
                    # Stream text content
                    if chunk.message and chunk.message.content:
                        if _ttft is None:
                            _ttft = round(time.time() - _stream_t0, 3)
                        text = chunk.message.content
                        if has_dedicated_thinking:
                            # Ya tenemos thinking por campo separado, el content es solo answer
                            if cleaned_output:
                                text = self.clean(text)
                            yield {'type': 'chunk', 'content': text}
                        else:
                            # Fallback: parsear  tags del content
                            rzn, clean_text, in_think_tag = self._process_think_tags(text, in_think_tag)
                            if rzn:
                                yield {'type': 'reasoning', 'content': rzn}
                            if clean_text:
                                if cleaned_output:
                                    clean_text = self.clean(clean_text)
                                yield {'type': 'chunk', 'content': clean_text}
                    # Accumulate streaming tool_calls (Ollama sends them in chunks)
                    if chunk.message and chunk.message.tool_calls:
                        for idx, tc in enumerate(chunk.message.tool_calls):
                            if idx not in accumulated_tool_calls:
                                accumulated_tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                            # Ollama ToolCall may not have 'id' attribute
                            tc_id = getattr(tc, 'id', None)
                            if tc_id:
                                accumulated_tool_calls[idx]["id"] = tc_id
                        if tc.function:
                            if tc.function.name:
                                accumulated_tool_calls[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                # Ollama may send arguments as dict or string
                                args = tc.function.arguments
                                if isinstance(args, dict):
                                    args = json.dumps(args, ensure_ascii=False)
                                accumulated_tool_calls[idx]["arguments"] += args
            except Exception as _ex:
                err = str(_ex)
                if "does not support thinking" in err:
                    # Modelo no soporta thinking, reintentar sin el flag
                    accumulated_tool_calls = {}
                    in_think_tag = False
                    has_dedicated_thinking = False
                    stream = await self.ollama_client.chat(**chat_kwargs)
                    async for chunk in stream:
                        if stream_cancel_event and stream_cancel_event.is_set():
                            self._record_spend(effective_provider, model, usage_data)
                            yield {'type': 'aborted'}
                            return
                        # Capturar usage del chunk final (done=True)
                        if getattr(chunk, 'done', False):
                            usage_data = {
                                'prompt_tokens': getattr(chunk, 'prompt_eval_count', 0) or 0,
                                'completion_tokens': getattr(chunk, 'eval_count', 0) or 0,
                                'total_tokens': (getattr(chunk, 'prompt_eval_count', 0) or 0) + (getattr(chunk, 'eval_count', 0) or 0),
                            }
                        if chunk.message and hasattr(chunk.message, 'thinking') and chunk.message.thinking:
                            has_dedicated_thinking = True
                            yield {'type': 'reasoning', 'content': chunk.message.thinking}
                        if chunk.message and chunk.message.content:
                            if _ttft is None:
                                _ttft = round(time.time() - _stream_t0, 3)
                            text = chunk.message.content
                            if has_dedicated_thinking:
                                if cleaned_output:
                                    text = self.clean(text)
                                yield {'type': 'chunk', 'content': text}
                            else:
                                rzn, clean_text, in_think_tag = self._process_think_tags(text, in_think_tag)
                                if rzn:
                                    yield {'type': 'reasoning', 'content': rzn}
                                if clean_text:
                                    if cleaned_output:
                                        clean_text = self.clean(clean_text)
                                    yield {'type': 'chunk', 'content': clean_text}
                        if chunk.message and chunk.message.tool_calls:
                            for idx, tc in enumerate(chunk.message.tool_calls):
                                if idx not in accumulated_tool_calls:
                                    accumulated_tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                                tc_id = getattr(tc, 'id', None)
                                if tc_id:
                                    accumulated_tool_calls[idx]["id"] = tc_id
                                if tc.function:
                                    if tc.function.name:
                                        accumulated_tool_calls[idx]["name"] = tc.function.name
                                    if tc.function.arguments:
                                        args = tc.function.arguments
                                        if isinstance(args, dict):
                                            args = json.dumps(args, ensure_ascii=False)
                                        accumulated_tool_calls[idx]["arguments"] += args
                else:
                    raise

            # After stream finishes, record spend (every call counts, even
            # without usage metadata) and yield usage (if captured).
            # ``total_time`` is always measured client-side (wall-clock),
            # the same way for every provider.
            if usage_data is not None:
                usage_data['total_time'] = round(time.time() - _stream_t0, 2)
            self._record_spend(effective_provider, model, usage_data)
            if usage_data is not None:
                usage_data['time_to_first_token'] = _ttft
                yield {'type': 'usage', 'content': usage_data}
            if accumulated_tool_calls:
                normalized: list[dict[str, Any]] = []
                for idx in sorted(accumulated_tool_calls.keys()):
                    tc = accumulated_tool_calls[idx]
                    try:
                        args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    except json.JSONDecodeError as ex:
                        log_error(str(ex), source="agent.py:llm_streaming(ollama_args)")
                        args = {}
                    normalized.append({
                        "id": tc["id"],
                        "name": tc["name"],
                        "args": args,
                    })
                yield {'type': 'tool_calls_detected', 'content': normalized}

        elif api_type == 'google':
            # ── Google Gemini ──
            contents, system_instruction = self._to_gemini_contents(msgs)
            config_kwargs: dict[str, Any] = {}
            if temperature is not None:
                config_kwargs['temperature'] = temperature
            if top_p is not None:
                config_kwargs['top_p'] = top_p
            if max_tokens:
                config_kwargs['max_output_tokens'] = max_tokens
            if system_instruction:
                config_kwargs['system_instruction'] = system_instruction
            gemini_tools = self._to_gemini_tools(tools)
            if gemini_tools:
                config_kwargs['tools'] = gemini_tools
            if stream_format == "json":
                config_kwargs['response_mime_type'] = 'application/json'

            # Use translator for reasoning (Google)
            reasoning_kwargs = translate_reasoning(
                provider=effective_provider,
                reasoning_value=reasoning,
                model_id=model,
                budget_tokens=budget_tokens,
            )
            if "thinking_config" in reasoning_kwargs:
                config_kwargs["thinking_config"] = reasoning_kwargs["thinking_config"]

            stream = await self.google_client.aio.models.generate_content_stream(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs),
            )

            accumulated_tool_calls: list[dict[str, Any]] = []
            usage_data: dict[str, Any] | None = None
            # Time-to-first-token (see OpenAI-compatible path above).
            _stream_t0 = time.time()
            _ttft: float | None = None

            async for chunk in stream:
                if stream_cancel_event and stream_cancel_event.is_set():
                    self._record_spend(effective_provider, model, usage_data)
                    yield {'type': 'aborted'}
                    return

                # Capture usage from the final chunk
                if chunk.usage_metadata:
                    usage_data = {
                        'prompt_tokens': chunk.usage_metadata.prompt_token_count or 0,
                        'completion_tokens': chunk.usage_metadata.candidates_token_count or 0,
                        'total_tokens': chunk.usage_metadata.total_token_count or 0,
                        'total_time': 0.0,
                    }

                candidate = (chunk.candidates or [None])[0]
                for part in ((candidate.content.parts if candidate and candidate.content else None) or []):
                    # Streaming function calls (Gemini sends them as parts)
                    fc = getattr(part, "function_call", None)
                    if fc is not None and fc.name:
                        args = fc.args if isinstance(fc.args, dict) else {}
                        accumulated_tool_calls.append({
                            "id": f"call_{uuid.uuid4().hex}",
                            "name": fc.name,
                            "args": args,
                            # Gemini 3.x thought signature (lives on the Part);
                            # must be replayed with the functionCall on the
                            # next request. Base64-encoded so it survives JSON
                            # persistence in the session store.
                            "thought_signature": _signature_to_str(getattr(part, "thought_signature", None)),
                        })
                        continue
                    # Stream text content
                    text = getattr(part, "text", None)
                    if text:
                        if _ttft is None:
                            _ttft = round(time.time() - _stream_t0, 3)
                        if cleaned_output:
                            text = self.clean(text)
                        yield {'type': 'chunk', 'content': text}
                        await asyncio.sleep(0.01)

            # After stream finishes, record spend (every call counts, even
            # without usage metadata) and yield usage (if captured).
            # ``total_time`` is always measured client-side (wall-clock),
            # the same way for every provider.
            if usage_data is not None:
                usage_data['total_time'] = round(time.time() - _stream_t0, 2)
            self._record_spend(effective_provider, model, usage_data)
            if usage_data is not None:
                usage_data['time_to_first_token'] = _ttft
                yield {'type': 'usage', 'content': usage_data}
            if accumulated_tool_calls:
                yield {'type': 'tool_calls_detected', 'content': accumulated_tool_calls}
        else:
            yield {'type': 'error', 'content': f"PROVIDER inválido: '{effective_provider}'"}

    
    def _process_think_tags(self, text: str, in_think: bool) -> tuple[str, str, bool]:
        """Parse ``<think>...</think>`` tags from a streaming chunk.

        Some providers (raw mode on some OpenAI-compatible providers, older Ollama models) embed reasoning
        inside ``<think>`` tags in the content field instead of a dedicated
        structured field.  This state-machine parser handles tags that span
        multiple chunks.

        Args:
            text: Incoming chunk text.
            in_think: ``True`` if we are currently inside a ``<think>``
                tag from a previous chunk.

        Returns:
            Tuple of ``(reasoning_part, content_part, still_in_think)``.
            Only one of ``reasoning_part`` / ``content_part`` will be
        non-empty per call.
        """
        # ── state: still inside <think> from previous chunk ──
        if in_think:
            end_idx = text.find("</think>")
            if end_idx == -1:
                return (text, "", True)  # still inside
            # </think> found in this chunk
            before = text[:end_idx]
            after = text[end_idx + len("</think>"):]
            return (before, after, False)

        # ── state: not inside <think> ──
        start_idx = text.find("<think>")
        if start_idx == -1:
            return ("", text, False)  # no tag at all

        before = text[:start_idx]
        after_start = text[start_idx + len("<think>"):]
        end_idx = after_start.find("</think>")
        if end_idx == -1:
            # tag started but not closed → we are now inside
            return (after_start, before, True)

        reasoning = after_start[:end_idx]
        after_close = after_start[end_idx + len("</think>"):]
        return (reasoning, before + after_close, False)

    def clean(self, text:str) -> str:
        '''
        Remove special Unicode characters and formatting artifacts from the provided text.

        The cleaning performed is deliberately conservative: it replaces zero-width and
        non-standard space characters, several dash variants and some invisible markers.

        ## Args:
            - text (str): Input text to clean.

        ## Returns:
            str: Cleaned text.

        ## Example:
            >>> agent.clean('Hello World')
            'HelloWorld'
        '''
        text = text.replace('\ufeff', '')
        text = text.replace('\u202f', ' ')   # espacio fino -> espacio normal
        text = text.replace('\u2011', '-')   # guion no separable -> guion normal
        text = text.replace('\u2013', '-')   # guion en dash -> guion normal
        text = text.replace('\u2014', '-')   # guion em dash -> guion normal
        text = text.replace(chr(8209), '-')
        text = text.replace('\u200b', '')       
        return text
        
    def prompt(self, prompt_name: str) -> str:
        """Load a prompt file from the ``prompts/`` directory.

        Reads ``{current_dir}/prompts/{prompt_name}.md`` where
        ``current_dir`` is the directory of this file (``backend/agent/``).

        Args:
            prompt_name: Prompt file name (without ``.md`` extension).

        Returns:
            The file content as a string.

        Raises:
            FileNotFoundError: If the prompt file does not exist.
        """
        with open(f'{current_dir}/prompts/{prompt_name}.md', 'r', encoding='utf-8') as f:
            prompt = f.read()

        return prompt

    
if __name__ == '__main__': 
    print('Agent module for LLM interaction and various utilities.')