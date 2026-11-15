"""Non-streaming LLM completion across providers (OpenAI-compatible, Ollama, Google)."""

from __future__ import annotations

import time
from typing import Any

from google.genai import types

from backend.agent.utils.contract import (
    ContractResponse,
    make_error_response,
    make_success_response,
    validate_response,
)
from backend.agent.utils.model_catalog import translate_reasoning
from backend.agent.llm.decision import _is_model_not_found
from backend.agent.llm.api_type import _resolve_api_type
from backend.agent.llm.gemini import _signature_to_str

class CompletionMixin:
    """Single-shot completion."""

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
                           output: str | None = None,
                           **kwargs: Any) -> ContractResponse:
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
                # Audio-capable OpenAI-speech models (e.g. gpt-audio via
                # OpenRouter) REQUIRE the audio modality on every call, even
                # for plain text turns: without it the provider rejects the
                # request ("requires that either input content or output
                # modality contain audio"). The helper below is a no-op ({})
                # for models that are not speech-compatible.
                try:
                    from backend.agent.llm.voices import (
                        build_openai_audio_kwargs as _oa_audio_kwargs,
                    )

                    oa_kwargs.update(
                        _oa_audio_kwargs(effective_provider, model)
                    )
                except Exception:
                    pass

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
                # Chat-style audio output (OpenAI dialect): base64 wav in
                # ``message.audio.data`` plus an optional transcript. Emit
                # the same ``<audio>`` tag the media extractors expect.
                try:
                    _audio_msg = getattr(
                        response.choices[0].message, "audio", None
                    )
                    if _audio_msg is not None:
                        _adata = getattr(_audio_msg, "data", None)
                        _atr = getattr(_audio_msg, "transcript", None)
                        if isinstance(_atr, str) and _atr.strip():
                            output = f"{_atr.strip()}\n{output or ''}".strip()
                        if isinstance(_adata, str) and _adata.strip():
                            output = (
                                f"{output}\n"
                                f'<audio controls src="data:audio/wav;base64,'
                                f'{_adata.strip()}" style="width:100%;"></audio>'
                            ).strip()
                except Exception:
                    pass
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
                # TTS-only models (["audio"]) accept ONLY ["AUDIO"] and do
                # NOT support multiturn chat: single user message, no tools.
                _resolved_mods_c: list[str] | None = None
                _is_tts_only_c = False
                _out_norm_c = (output or kwargs.get("output") or "")
                _out_norm_c = _out_norm_c.strip().lower() if isinstance(_out_norm_c, str) else ""
                try:
                    from backend.agent.utils.model_catalog import get_reasoning_options as _get_caps_c
                    from backend.agent.llm.outputs import (
                        resolve_gemini_response_modalities as _resolve_mods_c,
                    )

                    if _out_norm_c in ("image", "audio", "auto"):
                        _caps_c = _get_caps_c((effective_provider or "").strip(), model)
                        _raw_mods_c = _caps_c.get("output_modalities") or []
                        _resolved_mods_c = _resolve_mods_c(_raw_mods_c, response_format)
                        _is_tts_only_c = _resolved_mods_c == ["AUDIO"]
                    else:
                        # Calls without an output hint (e.g. title generation)
                        # still must not send TEXT/thinking to audio-only models.
                        try:
                            _caps_c = _get_caps_c((effective_provider or "").strip(), model)
                            _raw_c = [str(_m or "").strip().lower() for _m in (_caps_c.get("output_modalities") or [])]
                            if _raw_c and all(_m == "audio" for _m in _raw_c):
                                _resolved_mods_c = ["AUDIO"]
                                _is_tts_only_c = True
                        except Exception:
                            pass
                except Exception:
                    pass
                contents, system_instruction = self._to_gemini_contents(msgs)
                if _is_tts_only_c:
                    try:
                        from google.genai import types as _stypes_c

                        _last_text_c = ""
                        for _m in reversed(msgs or []):
                            _cc = (_m or {}).get("content", "")
                            if isinstance(_cc, str) and _cc.strip():
                                _last_text_c = _cc.strip()
                                break
                        contents = [_stypes_c.Content(
                            role="user",
                            parts=[_stypes_c.Part.from_text(text=_last_text_c or "Hola")],
                        )]
                    except Exception:
                        pass
                    system_instruction = None
                config_kwargs: dict[str, Any] = {}
                if temperature is not None:
                    config_kwargs['temperature'] = temperature
                if top_p is not None:
                    config_kwargs['top_p'] = top_p
                if max_tokens is not None:
                    config_kwargs['max_output_tokens'] = max_tokens
                if system_instruction:
                    config_kwargs['system_instruction'] = system_instruction
                gemini_tools = self._to_gemini_tools(tools)
                if gemini_tools and not _is_tts_only_c:
                    config_kwargs['tools'] = gemini_tools
                if response_format == "json":
                    config_kwargs['response_mime_type'] = 'application/json'
                if _resolved_mods_c is not None:
                    config_kwargs["response_modalities"] = _resolved_mods_c
                if _is_tts_only_c and response_format != "json":
                    try:
                        from backend.agent.llm.outputs import build_gemini_speech_config as _build_speech_c

                        config_kwargs["speech_config"] = _build_speech_c()
                    except Exception:
                        pass

                # Use translator for reasoning (Google). TTS-only models do
                # NOT support thinking: sending thinking_config fails with
                # 400 "Thinking is not enabled for this model".
                reasoning_kwargs = translate_reasoning(
                    provider=effective_provider,
                    reasoning_value=reasoning,
                    model_id=model,
                    budget_tokens=budget_tokens,
                )
                if "thinking_config" in reasoning_kwargs and not _is_tts_only_c:
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
                    # Free mode: inline image/audio alongside text in the same turn.
                    inline = getattr(part, "inline_data", None)
                    if inline is not None and getattr(inline, "data", None):
                        try:
                            import base64 as _b64mod

                            raw = inline.data
                            b64 = raw if isinstance(raw, str) else _b64mod.b64encode(bytes(raw)).decode("ascii")
                            mime = getattr(inline, "mime_type", None) or "image/png"
                            if str(mime).lower().startswith("audio/"):
                                # Raw PCM (audio/l16) is not browser-playable:
                                # wrap it in a WAV container.
                                if "l16" in str(mime).lower() or "pcm" in str(mime).lower():
                                    try:
                                        from backend.agent.llm.outputs import build_wav_data_url as _wav_url_c

                                        raw_bytes = raw if isinstance(raw, bytes) else _b64mod.b64decode(b64)
                                        output += _wav_url_c(bytes(raw_bytes))
                                    except Exception:
                                        output += f'\n<audio controls src="data:{mime};base64,{b64}" style="width:100%;"></audio>\n'
                                else:
                                    output += f'\n<audio controls src="data:{mime};base64,{b64}" style="width:100%;"></audio>\n'
                            else:
                                output += f'\n<img src="data:{mime};base64,{b64}" alt="Generated image" style="max-width:100%;border-radius:8px;" />\n'
                        except Exception:
                            pass
                completion_tokens = 0
                prompt_tokens = 0
                total_tokens = 0
                if response.usage_metadata:
                    # Thinking tokens are billed as output: count them too.
                    completion_tokens = (response.usage_metadata.candidates_token_count or 0) + (
                        getattr(response.usage_metadata, "thoughts_token_count", None) or 0
                    )
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
            # No log here: the caller logs once with its own source, so each
            # failure lands a single row in error_log instead of two.
            # Count the failed request in spend (zero tokens) so the
            # requests counter stays consistent with the messages log.
            try:
                self._record_spend(effective_provider, model, None)
            except Exception:
                pass
            if _is_model_not_found(str(e)):
                # The configured model does not exist: the technical detail
                # stays in the db log, the caller gets clean text.
                user_message = (
                    f"El modelo configurado '{model}' no existe o no está disponible. "
                    "Revisá la configuración del modelo."
                )
            else:
                user_message = str(e)
            return validate_response(make_error_response(
                message=user_message,
                usage={
                    'prompt_tokens': 0,
                    'completion_tokens': 0,
                    'total_tokens': 0,
                    'total_time': 0,
                },
            ))
