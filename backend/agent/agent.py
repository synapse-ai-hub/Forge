"""Agent: LLM clients, prompt rendering and the native tools."""

from __future__ import annotations

import sys
import os
import logging
from typing import Any, Dict

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError, TemplateNotFound
from google import genai
from openai import AsyncOpenAI

from backend.agent.utils.error_logger import log_error
from backend.agent.utils.prompt_loader import find_prompt_file, prompt_searchpath
from backend.agent.utils import provider_keys
from backend.agent.tools import Tools
from backend.agent.utils.spend_handler import calculate_cost, record_spend
from backend.agent.llm.tool_calls import ToolCallsMixin
from backend.agent.llm.gemini import GeminiMixin
from backend.agent.llm.completion import CompletionMixin
from backend.agent.llm.decision import DecisionMixin
from backend.agent.llm.streaming import StreamingMixin

logger = logging.getLogger(__name__)

# Marcadores de comentarios usados en este proyecto:
# TODO   : trabajo pendiente, todavía no implementado.
# FIXME  : hay un bug conocido; este código falla o es incorrecto.
# REVIEW : parte del código que debe ser revisada o validada por otra persona.
# NOTE   : aclaración importante sobre decisiones o comportamiento no obvio.
# HACK   : solución provisoria / poco elegante / hardcodeada, usada para salir del paso.
# DEBUG  : código o mensajes usados solo para depuración temporal.
# OK     : bloque probado y estable en las condiciones actuales.
# PROD   : código / config específica de producción; tocar con extremo cuidado.

try:
    # Optional dependency: the LOCAL (Ollama) provider needs the ``ollama``
    # package, but the app must start without it installed.
    from ollama import AsyncClient
except ImportError:
    AsyncClient = None

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path so absolute imports (backend.*)
# resolve correctly regardless of where the file is invoked from.
# ---------------------------------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))

if project_root not in sys.path:
    sys.path.insert(0, project_root)

load_dotenv()


class Agent(
    ToolCallsMixin,
    GeminiMixin,
    CompletionMixin,
    DecisionMixin,
    StreamingMixin,
):
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

        # Decision-model selection (System One API): independent from the
        # chat model above. Set through the ``POST
        # /api/config/models/decision/select`` + ``.../decision/enabled``
        # endpoints; restored from ``config_kv`` at startup. Until the user
        # enables it and picks provider + model, decision calls are
        # gracefully unavailable (callers keep the current flow).
        self.decision_provider: str | None = None
        self.decision_model: str | None = None
        self.decision_enabled: bool = False

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

        # Prompts: templates Jinja de prompts/ (ver ``prompt``). Un error de
        # variable faltante o de sintaxis nunca corta el chat (ver ``prompt``).
        self._prompt_env = Environment(
            loader=FileSystemLoader(prompt_searchpath()),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            autoescape=False,
        )

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

        Example:
            >>> agent.clean('Hello World')
            'HelloWorld'

        Args:
            text: Input text to clean.

        Returns:
            The cleaned text.
        '''
        text = text.replace('\ufeff', '')
        text = text.replace('\u202f', ' ')   # espacio fino -> espacio normal
        text = text.replace('\u2011', '-')   # guion no separable -> guion normal
        text = text.replace('\u2013', '-')   # guion en dash -> guion normal
        text = text.replace('\u2014', '-')   # guion em dash -> guion normal
        text = text.replace(chr(8209), '-')
        text = text.replace('\u200b', '')       
        return text

    def prompt(self, prompt_name: str, **context: Any) -> str:
        """Render a prompt template from the ``prompts/`` tree.

        Reads ``{name}.jinja`` (unique across the scope subfolders of
        ``prompts/``, e.g. ``router/``, ``creadores/``) where
        ``current_dir`` is the directory of this file (``backend/agent/``)
        and renders it with *context*. If the template has a syntax error or
        uses a variable missing from *context*, the error is logged and the
        raw file text is returned, so a bad edit never stops the chat.

        Args:
            prompt_name: Template name (without the ``.jinja`` extension).
            **context: Template variables (e.g. ``tools`` = enabled tool names).

        Returns:
            The rendered prompt as a string.

        Raises:
            FileNotFoundError: If the template file does not exist.
        """
        try:
            return self._prompt_env.get_template(f'{prompt_name}.jinja').render(**context)
        except TemplateNotFound as exc:
            raise FileNotFoundError(f'{current_dir}/prompts/{prompt_name}.jinja') from exc
        except TemplateError as exc:
            log_error(str(exc), source=f'agent.py:prompt({prompt_name})')
            found = find_prompt_file(prompt_name)
            with open(found, 'r', encoding='utf-8') as f:
                return f.read()


if __name__ == '__main__': 
    print('Agent module for LLM interaction and various utilities.')
