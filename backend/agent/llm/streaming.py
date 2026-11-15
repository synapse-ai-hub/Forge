"""Streaming LLM completion across providers (OpenAI-compatible, Ollama, Google)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any
import asyncio

from google.genai import types

from backend.agent.utils.error_logger import log_error
from backend.agent.utils.model_catalog import translate_reasoning, get_reasoning_streaming_config
from backend.agent.llm.api_type import _resolve_api_type
from backend.agent.llm.gemini import _signature_to_str

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

class StreamingMixin:
    """Streaming completion."""

    async def llm_streaming(self, model: str, prompt: str | None = None,
                             system_content: str = '',
                             messages: list[dict[str, Any]] | None = None,
                             temperature: float = 0,
                             top_p: float = 0.5, max_tokens: int = 3000,
                             cleaned_output: bool = True,
                             tools: list | None = None,
                             stream_cancel_event: asyncio.Event | None = None,
                             provider: str | None = None,
                             reasoning: bool = True,
                             budget_tokens: int | None = None,
                             output: str | None = None,
                             **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
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

            # Audio-capable OpenAI-speech models (e.g. gpt-audio via
            # OpenRouter) REQUIRE the audio modality on every call, even
            # for plain text turns: without it the provider rejects the
            # request ("requires that either input content or output
            # modality contain audio"). The helper below is a no-op ({})
            # for models that are not speech-compatible.
            try:
                from backend.agent.llm.voices import (
                    build_openai_audio_kwargs as _oa_audio_kwargs_s,
                )

                oa_kwargs.update(
                    _oa_audio_kwargs_s(effective_provider, model)
                )
            except (ImportError, AttributeError):
                pass

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
            # Batch mode for OpenAI-style audio: data chunks are buffered
            # and emitted as ONE event when the stream ends (the UI shows
            # typing meanwhile). Mirrors the Gemini audio batching below.
            _oa_audio_parts: list[str] = []
            _oa_audio_transcript: str = ""
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

                    # OpenAI-style audio deltas (chat audio output):
                    # buffer data, emit once at stream end (batch).
                    try:
                        _delta_audio = getattr(delta, "audio", None)
                    except AttributeError:
                        _delta_audio = None
                    if _delta_audio is not None:
                        try:
                            _adata = getattr(_delta_audio, "data", None)
                            if isinstance(_adata, str) and _adata:
                                _oa_audio_parts.append(_adata)
                            _atr = getattr(_delta_audio, "transcript", None)
                            if isinstance(_atr, str) and _atr:
                                _oa_audio_transcript += _atr
                        except (AttributeError, TypeError):
                            pass

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

            # Batch: emit the buffered OpenAI-style audio as ONE event
            # (UI typing ends, single player rendered).
            if _oa_audio_parts:
                try:
                    if _oa_audio_transcript.strip():
                        _oa_text = _oa_audio_transcript.strip()
                        if cleaned_output:
                            _oa_text = self.clean(_oa_text)
                        yield {'type': 'chunk', 'content': _oa_text}
                        await asyncio.sleep(0.01)
                    yield {
                        'type': 'audio',
                        'content': {
                            'b64': "".join(_oa_audio_parts),
                            'mime': 'audio/wav',
                            'model': model,
                        },
                    }
                except (TypeError, ValueError):
                    pass
                _oa_audio_parts = []
                _oa_audio_transcript = ""

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

            def _try_stream(use_think: bool | str = False) -> Any:
                """Create a stream with or without the think flag, or with a specific level.

                Args:
                    use_think: ``True``/``"on"``, ``False``/``"off"``, a level (``"low"``, ``"medium"``,
                        ``"high"``, ``"max"``). Any other value uses the model default.

                Returns:
                    The Ollama stream.
                """
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
                    # Accumulate tool_calls. Ollama sends every call complete
                    # (name + args) and spreads parallel calls over several
                    # chunks: each one is a new call, never a fragment.
                    if chunk.message and chunk.message.tool_calls:
                        for tc in chunk.message.tool_calls:
                            idx = len(accumulated_tool_calls)
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
                            for tc in chunk.message.tool_calls:
                                idx = len(accumulated_tool_calls)
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
            # Free mode: derive Gemini response modalities from the model
            # catalog FIRST. TTS-only models (["audio"]) accept ONLY
            # ["AUDIO"] (requesting TEXT fails with 400) and do NOT
            # support multiturn chat: single user message, no tools.
            _resolved_mods: list[str] | None = None
            _is_tts_only = False
            _out_norm = (output or kwargs.get("output") or stream_format or "")
            _out_norm = _out_norm.strip().lower() if isinstance(_out_norm, str) else ""
            try:
                from backend.agent.utils.model_catalog import get_reasoning_options as _get_caps
                from backend.agent.llm.outputs import (
                    resolve_gemini_response_modalities as _resolve_mods,
                )

                if _out_norm in ("image", "audio", "auto"):
                    _caps = _get_caps((effective_provider or "").strip(), model)
                    _raw_mods = _caps.get("output_modalities") or []
                    _resolved_mods = _resolve_mods(_raw_mods, stream_format)
                    _is_tts_only = _resolved_mods == ["AUDIO"]
                else:
                    # Calls without an output hint (e.g. title generation)
                    # still must not send TEXT/thinking to audio-only models.
                    try:
                        _caps = _get_caps((effective_provider or "").strip(), model)
                        _raw_mods = [str(_m or "").strip().lower() for _m in (_caps.get("output_modalities") or [])]
                        if _raw_mods and all(_m == "audio" for _m in _raw_mods):
                            _resolved_mods = ["AUDIO"]
                            _is_tts_only = True
                    except (ImportError, AttributeError):
                        pass
            except (ImportError, AttributeError, KeyError):
                pass
            contents, system_instruction = self._to_gemini_contents(msgs)
            if _is_tts_only:
                # TTS: single-turn only — last user text, no history/tools.
                try:
                    from google.genai import types as _stypes

                    _last_text = ""
                    for _m in reversed(msgs or []):
                        _c = (_m or {}).get("content", "")
                        if isinstance(_c, str) and _c.strip():
                            _last_text = _c.strip()
                            break
                    contents = [_stypes.Content(
                        role="user",
                        parts=[_stypes.Part.from_text(text=_last_text or "Hola")],
                    )]
                except (ImportError, AttributeError):
                    pass
                system_instruction = None
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
            if gemini_tools and not _is_tts_only:
                config_kwargs['tools'] = gemini_tools
            if stream_format == "json":
                config_kwargs['response_mime_type'] = 'application/json'
            if _resolved_mods is not None:
                config_kwargs["response_modalities"] = _resolved_mods
            if _is_tts_only and stream_format != "json":
                try:
                    from backend.agent.llm.outputs import build_gemini_speech_config as _build_speech

                    config_kwargs["speech_config"] = _build_speech()
                except (ImportError, AttributeError):
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
            if "thinking_config" in reasoning_kwargs and not _is_tts_only:
                config_kwargs["thinking_config"] = reasoning_kwargs["thinking_config"]

            stream = await self.google_client.aio.models.generate_content_stream(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs),
            )

            accumulated_tool_calls: list[dict[str, Any]] = []
            usage_data: dict[str, Any] | None = None
            # Batch mode for media: audio chunks are buffered and
            # emitted as ONE event when the stream ends (the UI shows
            # typing meanwhile). Images already arrive whole.
            pending_audio_parts: list[tuple[str, str]] = []
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
                    # Thinking tokens are billed as output: count them too.
                    usage_data = {
                        'prompt_tokens': chunk.usage_metadata.prompt_token_count or 0,
                        'completion_tokens': (chunk.usage_metadata.candidates_token_count or 0)
                        + (getattr(chunk.usage_metadata, 'thoughts_token_count', None) or 0),
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
                    # Free mode: inline image/audio alongside text in the same turn.
                    # Audio is buffered (batch): ONE event at stream end.
                    inline = getattr(part, "inline_data", None)
                    if inline is not None and getattr(inline, "data", None):
                        try:
                            import base64 as _b64mod

                            raw = inline.data
                            b64 = raw if isinstance(raw, str) else _b64mod.b64encode(bytes(raw)).decode("ascii")
                            mime = getattr(inline, "mime_type", None) or "image/png"
                            if str(mime).lower().startswith("audio/"):
                                pending_audio_parts.append((b64, mime))
                            else:
                                yield {'type': 'image', 'content': {'b64': b64, 'mime': mime, 'model': model}}
                            await asyncio.sleep(0.01)
                        except (ValueError, TypeError, AttributeError):
                            pass

            # After stream finishes, record spend (every call counts, even
            # without usage metadata) and yield usage (if captured).
            # ``total_time`` is always measured client-side (wall-clock),
            # the same way for every provider.
            # Batch: emit the buffered audio as ONE event (UI typing ends,
            # single player rendered).
            if pending_audio_parts:
                try:
                    from backend.agent.llm.outputs import merge_audio_chunks as _merge_audio

                    _merged_b64, _merged_mime = _merge_audio(pending_audio_parts)
                    if _merged_b64:
                        # Live event must be browser-playable: raw l16/pcm
                        # is wrapped in WAV (same as persist time).
                        if "l16" in str(_merged_mime).lower() or "pcm" in str(_merged_mime).lower():
                            try:
                                from backend.agent.llm.outputs import build_wav_data_url as _wav_url_live
                                import base64 as _b64live

                                _wav_bytes = _b64live.b64decode(_merged_b64)
                                _wav_tag = _wav_url_live(bytes(_wav_bytes))
                                _merged_b64 = _wav_tag.split("data:audio/wav;base64,", 1)[1].split('"', 1)[0]
                                _merged_mime = "audio/wav"
                            except (ValueError, TypeError):
                                pass
                        yield {'type': 'audio', 'content': {'b64': _merged_b64, 'mime': _merged_mime, 'model': model}}
                except (ValueError, TypeError):
                    pass
                pending_audio_parts = []
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
