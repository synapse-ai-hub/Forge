"""Voice configuration translators for TTS-capable providers.

Each provider SDK exposes voice selection differently:

- ``google`` (``google-genai`` SDK): ``SpeechConfig`` with a prebuilt
  ``voice_name`` (30 voices such as ``Kore`` or ``Aoede``). Speed,
  instructions and format are not configurable. The official docs
  publish a style descriptor per prebuilt voice (e.g. ``Kore`` —
  "Firm"); live ``gender``/``pitch``/``accent``/``persona``/
  ``description`` come from the Extended Voice Library
  (``client.voices.list()``, requires ``google-genai`` >= 2.25),
  cached 24 h in memory with static-style fallback.
- ``openai`` (``openai`` SDK, ``audio.speech.create``): ``voice`` (13
  voices), ``speed`` (0.25-4.0), ``instructions`` (free text, gpt-4o-mini-tts
  and later) and ``response_format`` (mp3/opus/aac/flac/wav/pcm).
  Note: ``tts-1``/``tts-1-hd``/``gpt-4o-mini-tts`` are deprecated by
  OpenAI (shutdown 2027-01-06); none of them is listed by models.dev
  or the OpenRouter API, so the panel only applies to OpenAI models
  when a catalog declares audio output for them.
- Any OpenAI-vendor speech model on an OpenAI-compatible provider
  (e.g. ``"openai/gpt-audio-mini"`` via OpenRouter): same OpenAI voice
  list and validation; Chat Completions calls additionally receive
  ``modalities=["text", "audio"]`` plus ``audio={"voice", "format"}``
  (built by :func:`build_openai_audio_kwargs` from the persisted panel
  settings).
- ``groq`` (Orpheus models via chat completions): the voice is fixed by the
  model itself; there is nothing to configure.
- ``LOCAL``: TTS is not supported.

The frontend voice panel (``GET /api/config/voices``) is driven by
:func:`get_voice_options`; the agent loop validates user choices with
:func:`translate_voice` before calling the provider SDK.
"""

from __future__ import annotations

import time
from typing import Any

# In-memory cache of the Google Extended Voice Library
# (``client.voices.list()``), keyed by lowercased voice name.
# Refreshed at most once per TTL to avoid hitting the API on every
# panel open. Empty dict = not fetched yet or last fetch failed
# (callers fall back to the static style map).
_VOICE_LIBRARY_CACHE: dict[str, dict[str, str]] = {}
_VOICE_LIBRARY_FETCHED_AT: float = 0.0
VOICE_LIBRARY_TTL_SECONDS = 24 * 3600

# OpenAI voices recommended by the official docs (best quality).
OPENAI_RECOMMENDED_VOICES: tuple[str, ...] = ("marin", "cedar")

GOOGLE_PREBUILT_VOICES: tuple[str, ...] = (
    "Achernar",
    "Achird",
    "Algenib",
    "Algieba",
    "Alnilam",
    "Aoede",
    "Autonoe",
    "Callirrhoe",
    "Charon",
    "Despina",
    "Enceladus",
    "Erinome",
    "Fenrir",
    "Gacrux",
    "Iapetus",
    "Kore",
    "Laomedeia",
    "Leda",
    "Orus",
    "Puck",
    "Pulcherrima",
    "Rasalgethi",
    "Sadachbia",
    "Sadaltager",
    "Schedar",
    "Sulafat",
    "Umbriel",
    "Vindemiatrix",
    "Zephyr",
    "Zubenelgenubi",
)

# Style descriptor per prebuilt Google voice, from the official Gemini
# TTS docs ("Voice options" table). No gender metadata is published
# for prebuilt voices.
GOOGLE_VOICE_STYLES: dict[str, str] = {
    "Achernar": "Soft",
    "Achird": "Friendly",
    "Algenib": "Gravelly",
    "Algieba": "Smooth",
    "Alnilam": "Firm",
    "Aoede": "Breezy",
    "Autonoe": "Bright",
    "Callirrhoe": "Easy-going",
    "Charon": "Informative",
    "Despina": "Smooth",
    "Enceladus": "Breathy",
    "Erinome": "Clear",
    "Fenrir": "Excitable",
    "Gacrux": "Mature",
    "Iapetus": "Clear",
    "Kore": "Firm",
    "Laomedeia": "Upbeat",
    "Leda": "Youthful",
    "Orus": "Firm",
    "Puck": "Upbeat",
    "Pulcherrima": "Forward",
    "Rasalgethi": "Informative",
    "Sadachbia": "Lively",
    "Sadaltager": "Knowledgeable",
    "Schedar": "Even",
    "Sulafat": "Warm",
    "Umbriel": "Easy-going",
    "Vindemiatrix": "Gentle",
    "Zephyr": "Bright",
    "Zubenelgenubi": "Casual",
}

OPENAI_VOICES: tuple[str, ...] = (
    "alloy",
    "ash",
    "ballad",
    "cedar",
    "coral",
    "echo",
    "fable",
    "marin",
    "nova",
    "onyx",
    "sage",
    "shimmer",
    "verse",
)

OPENAI_AUDIO_FORMATS: tuple[str, ...] = (
    "mp3",
    "opus",
    "aac",
    "flac",
    "wav",
    "pcm",
)

DEFAULT_GOOGLE_VOICE = "Aoede"
DEFAULT_OPENAI_VOICE = "alloy"
DEFAULT_OPENAI_FORMAT = "mp3"

VOICE_SPEED_MIN = 0.25
VOICE_SPEED_MAX = 4.0


def _fetch_google_voice_library() -> dict[str, dict[str, str]]:
    """Fetch the Google Extended Voice Library metadata (cached).

    Calls ``client.voices.list()`` (requires ``google-genai`` >= 2.25)
    and indexes prebuilt voices by name with their ``gender``, ``pitch``,
    ``accent``, ``persona`` and ``description``. Results are cached in
    memory for ``VOICE_LIBRARY_TTL_SECONDS``.

    Returns:
        Dict mapping lowercased voice name to its metadata. Empty when
        the key is missing, the SDK call fails, or the SDK is too old.
        Never raises.
    """
    global _VOICE_LIBRARY_CACHE, _VOICE_LIBRARY_FETCHED_AT
    try:
        now = time.monotonic()
        if _VOICE_LIBRARY_CACHE and (
            now - _VOICE_LIBRARY_FETCHED_AT < VOICE_LIBRARY_TTL_SECONDS
        ):
            return _VOICE_LIBRARY_CACHE
        from backend.agent.utils.provider_keys import resolve_api_key

        key = resolve_api_key("google")
        if not key:
            return _VOICE_LIBRARY_CACHE
        from google import genai

        # The Voice Library lives under v1beta; the SDK default
        # api_version does not expose it (404).
        client = genai.Client(
            api_key=key, http_options={"api_version": "v1beta"}
        )
        list_fn = getattr(getattr(client, "voices", None), "list", None)
        if not callable(list_fn):
            return _VOICE_LIBRARY_CACHE
        response = None
        found: dict[str, dict[str, str]] = {}
        # The library mixes stored custom voices with prebuilt ones across
        # pages: paginate until every known prebuilt voice is found
        # (or pages run out). Result is cached for 24 h.
        page_token: str | None = None
        for _ in range(10):
            try:
                kwargs: dict[str, Any] = {
                    "type_": ["prebuilt"],
                    "page_size": 1000,
                }
                if page_token:
                    kwargs["page_token"] = page_token
                response = list_fn(**kwargs)
            except Exception:
                break
            for voice in getattr(response, "voices", None) or []:
                try:
                    name = (
                        getattr(voice, "display_name", None)
                        or getattr(voice, "name", None)
                        or ""
                    )
                    name = str(name).strip()
                    if not name:
                        continue
                    meta = {
                        "gender": str(getattr(voice, "gender", None) or "").strip(),
                        "pitch": str(getattr(voice, "pitch", None) or "").strip(),
                        "accent": str(getattr(voice, "accent", None) or "").strip(),
                        "persona": str(getattr(voice, "persona", None) or "").strip(),
                        "description": str(
                            getattr(voice, "description", None) or ""
                        ).strip(),
                    }
                    found[name.lower()] = meta
                    voice_id = str(getattr(voice, "name", None) or "").strip()
                    if voice_id and voice_id.lower() != name.lower():
                        found.setdefault(voice_id.lower(), meta)
                except Exception:
                    continue
            if all(v.lower() in found for v in GOOGLE_PREBUILT_VOICES):
                break
            try:
                page_token = getattr(response, "next_page_token", None) or None
            except Exception:
                page_token = None
            if not page_token:
                break
        if found:
            # Merge (never shrink): a partial refetch keeps prior entries.
            _VOICE_LIBRARY_CACHE = {**_VOICE_LIBRARY_CACHE, **found}
            _VOICE_LIBRARY_FETCHED_AT = now
        return _VOICE_LIBRARY_CACHE
    except Exception:
        return _VOICE_LIBRARY_CACHE


def _audio_capable(provider: str, model: str) -> bool:
    """Check whether a model exposes audio output modalities.

    Args:
        provider: Provider id (e.g. ``"google"``, ``"openai"``).
        model: Model id as stored in the catalog.

    Returns:
        ``True`` when ``"audio"`` is among the catalog output modalities.
    """
    try:
        from backend.agent.utils.model_catalog import get_reasoning_options

        caps = get_reasoning_options((provider or "").strip(), model) or {}
        mods = [str(m or "").strip().lower() for m in (caps.get("output_modalities") or [])]
        return "audio" in mods
    except Exception:
        return False


def _is_openai_speech_compatible(provider: str, model: str) -> bool:
    """Check whether a provider uses OpenAI-style speech parameters.

    Applies to ``provider == "openai"`` and to OpenAI-vendor models
    served through OpenAI-compatible providers (e.g.
    ``"openai/gpt-audio-mini"`` via OpenRouter): both speak the OpenAI
    Chat Completions ``modalities``/``audio`` dialect, so the OpenAI
    voice list (``OPENAI_VOICES``) and the ``translate_voice`` OpenAI
    branch apply. Other vendors (e.g. Groq Orpheus/PlayAI) use their own
    voice vocabulary and keep ``fixed_voice``.

    Args:
        provider: Provider id (e.g. ``"openrouter"``).
        model: Model id as stored in the catalog.

    Returns:
        ``True`` when the model is an OpenAI speech model on an
        OpenAI-compatible provider and exposes audio output modalities.
    """
    try:
        from backend.agent.llm.api_type import _resolve_api_type

        _, api_type = _resolve_api_type(provider)
        if api_type != "openai-compatible":
            return False
        prov = (provider or "").strip().lower()
        mod = (model or "").strip().lower()
        if prov != "openai" and not mod.startswith("openai/"):
            return False
    except Exception:
        return False
    return _audio_capable(provider, model)


def get_voice_options(provider: str, model: str) -> dict[str, Any]:
    """Describe the voice settings a model supports for the voice panel.

    Args:
        provider: Provider id of the currently selected model.
        model: Model id of the currently selected model.

    Returns:
        Dict with ``voices`` (list of names), ``supports_speed``,
        ``supports_instructions``, ``formats`` (list; empty when the model
        has a single fixed output format, e.g. Google TTS always emits
        WAV), ``fixed_voice`` (``True`` when the voice is fixed by the
        model), ``applicable`` (``False`` when the model has no audio
        output), ``default_voice`` (voice used when none is selected),
        ``default_format`` (format used when none is selected, ``None``
        when the model has a single fixed format) and ``voice_details``
        (list of ``{"name", "style", ...}``; Google entries carry the
        static style plus live ``gender``/``pitch``/``accent``/``persona``/
        ``description`` from the Voice Library when available; OpenAI
        entries carry ``recommended`` for the docs-recommended voices).
    """
    prov = (provider or "").strip().lower()
    if not _audio_capable(prov, model):
        return {
            "voices": [],
            "supports_speed": False,
            "supports_instructions": False,
            "formats": [],
            "fixed_voice": False,
            "applicable": False,
            "default_voice": None,
            "default_format": None,
            "voice_details": [],
        }
    if prov == "google":
        library = _fetch_google_voice_library()
        return {
            "voices": list(GOOGLE_PREBUILT_VOICES),
            "supports_speed": False,
            "supports_instructions": False,
            # Google TTS always emits WAV: no format choice to offer.
            "formats": [],
            "fixed_voice": False,
            "applicable": True,
            "default_voice": DEFAULT_GOOGLE_VOICE,
            "default_format": None,
            "voice_details": [
                {
                    "name": v,
                    "style": GOOGLE_VOICE_STYLES.get(v, ""),
                    **library.get(v.lower(), {}),
                }
                for v in GOOGLE_PREBUILT_VOICES
            ],
        }
    if prov == "openai" or _is_openai_speech_compatible(prov, model):
        return {
            "voices": list(OPENAI_VOICES),
            "supports_speed": True,
            "supports_instructions": True,
            "formats": list(OPENAI_AUDIO_FORMATS),
            "fixed_voice": False,
            "applicable": True,
            "default_voice": DEFAULT_OPENAI_VOICE,
            "default_format": DEFAULT_OPENAI_FORMAT,
            "voice_details": [
                {
                    "name": v,
                    "style": "",
                    "recommended": v in OPENAI_RECOMMENDED_VOICES,
                }
                for v in OPENAI_VOICES
            ],
        }
    return {
        "voices": [],
        "supports_speed": False,
        "supports_instructions": False,
        "formats": [],
        "fixed_voice": True,
        "applicable": True,
        "default_voice": None,
        "default_format": None,
        "voice_details": [],
    }


def translate_voice(
    provider: str,
    model: str,
    voice: str | None = None,
    speed: float | None = None,
    instructions: str | None = None,
    audio_format: str | None = None,
) -> dict[str, Any]:
    """Translate generic voice settings to provider SDK arguments.

    Args:
        provider: Provider id (e.g. ``"google"``, ``"openai"``,
            ``"openrouter"`` for OpenAI-compatible speech).
        model: Model id the settings apply to.
        voice: Requested voice name (provider-specific vocabulary).
        speed: Playback speed multiplier (OpenAI-style only).
        instructions: Voice style instructions (OpenAI gpt-4o-mini-tts+).
        audio_format: Output container (OpenAI-style only).

    Returns:
        Contract dict with ``status`` ``"success"``/``"error"``,
        ``message``, ``usage`` and ``data`` holding the SDK arguments.
    """
    from backend.agent.utils.contract import zero_usage

    prov = (provider or "").strip().lower()
    if prov == "local":
        return {
            "status": "error",
            "message": "LOCAL provider does not support TTS voices.",
            "usage": zero_usage(),
            "data": {},
        }
    if not _audio_capable(prov, model):
        return {
            "status": "error",
            "message": f"Model '{model}' does not support audio output.",
            "usage": zero_usage(),
            "data": {},
        }
    if prov == "google":
        name = (voice or "").strip() if isinstance(voice, str) else ""
        name = name or DEFAULT_GOOGLE_VOICE
        if name not in GOOGLE_PREBUILT_VOICES:
            return {
                "status": "error",
                "message": f"Unknown Google voice '{voice}'.",
                "usage": zero_usage(),
                "data": {},
            }
        ignored = [
            k
            for k, v in (
                ("speed", speed),
                ("instructions", instructions),
                ("audio_format", audio_format),
            )
            if v not in (None, "")
        ]
        return {
            "status": "success",
            "message": "ok",
            "usage": zero_usage(),
            "data": {"voice_name": name, "ignored": ignored},
        }
    if prov == "openai" or _is_openai_speech_compatible(prov, model):
        name = voice.strip().lower() if isinstance(voice, str) else ""
        name = name or DEFAULT_OPENAI_VOICE
        if name not in OPENAI_VOICES:
            return {
                "status": "error",
                "message": f"Unknown OpenAI voice '{voice}'.",
                "usage": zero_usage(),
                "data": {},
            }
        try:
            spd = 1.0 if speed is None else float(speed)
        except (TypeError, ValueError):
            return {
                "status": "error",
                "message": (
                    "speed must be a number between "
                    f"{VOICE_SPEED_MIN} and {VOICE_SPEED_MAX}."
                ),
                "usage": zero_usage(),
                "data": {},
            }
        if not (VOICE_SPEED_MIN <= spd <= VOICE_SPEED_MAX):
            return {
                "status": "error",
                "message": (
                    f"speed must be between {VOICE_SPEED_MIN} and {VOICE_SPEED_MAX}."
                ),
                "usage": zero_usage(),
                "data": {},
            }
        fmt = (
            audio_format.strip().lower()
            if isinstance(audio_format, str)
            else ""
        ) or DEFAULT_OPENAI_FORMAT
        if fmt not in OPENAI_AUDIO_FORMATS:
            return {
                "status": "error",
                "message": f"Unknown audio format '{audio_format}'.",
                "usage": zero_usage(),
                "data": {},
            }
        return {
            "status": "success",
            "message": "ok",
            "usage": zero_usage(),
            "data": {
                "voice": name,
                "speed": spd,
                "instructions": (
                    instructions.strip()
                    if isinstance(instructions, str)
                    else ""
                ),
                "response_format": fmt,
            },
        }
    return {
        "status": "success",
        "message": "ok",
        "usage": zero_usage(),
        "data": {"fixed_voice": True, "voice": (model or "").strip()},
    }


def read_stored_voice_settings() -> dict[str, Any]:
    """Read the persisted voice panel settings.

    Same source the voice panel writes (``param_voice``,
    ``param_voice_speed``, ``param_voice_instructions``,
    ``param_voice_format``). ``"Default"``/empty values become ``None``.

    Returns:
        Dict with ``voice``, ``speed``, ``instructions`` and
        ``audio_format`` keys (``None`` when unset).
    """
    settings: dict[str, Any] = {
        "voice": None,
        "speed": None,
        "instructions": None,
        "audio_format": None,
    }
    try:
        from backend.agent.session import SessionManager

        stored = SessionManager()
        raw_voice = stored.get_config("param_voice")
        if isinstance(raw_voice, str) and raw_voice.strip().lower() not in (
            "", "null", "default",
        ):
            settings["voice"] = raw_voice.strip()
        raw_speed = stored.get_config("param_voice_speed")
        if isinstance(raw_speed, str) and raw_speed.strip().lower() not in (
            "", "null", "default",
        ):
            try:
                settings["speed"] = float(raw_speed.strip())
            except (TypeError, ValueError):
                settings["speed"] = None
        raw_instructions = stored.get_config("param_voice_instructions")
        if isinstance(raw_instructions, str) and raw_instructions.strip().lower() not in (
            "", "null", "default",
        ):
            settings["instructions"] = raw_instructions.strip()
        raw_format = stored.get_config("param_voice_format")
        if isinstance(raw_format, str) and raw_format.strip().lower() not in (
            "", "null", "default",
        ):
            settings["audio_format"] = raw_format.strip()
    except Exception:
        pass
    return settings


def build_openai_audio_kwargs(provider: str, model: str) -> dict[str, Any]:
    """Build OpenAI-style ``modalities``/``audio`` SDK kwargs.

    Reads the persisted voice settings, validates them with
    :func:`translate_voice` and returns the Chat Completions arguments
    (``modalities=["text", "audio"]`` plus ``audio={"voice", "format"}``).
    The Chat Completions ``audio`` parameter only accepts ``voice`` and
    ``format`` (speed/instructions belong to other endpoints), so only
    those two travel here.

    Args:
        provider: Provider id (must be OpenAI-speech compatible).
        model: Model id the settings apply to.

    Returns:
        SDK kwargs dict, or ``{}`` when the provider/model is not
        OpenAI-speech compatible or validation fails. A stored voice from
        another vendor's vocabulary (stale panel value after switching
        providers) falls back to the default voice instead of breaking
        the call.
    """
    try:
        if not _is_openai_speech_compatible(provider, model):
            return {}
        stored = read_stored_voice_settings()
        result = translate_voice(
            provider,
            model,
            voice=stored.get("voice"),
            speed=stored.get("speed"),
            instructions=stored.get("instructions"),
            audio_format=stored.get("audio_format"),
        )
        if (not isinstance(result, dict) or result.get("status") != "success") and stored.get("voice"):
            # Stale cross-vendor voice (e.g. a Google voice stored while
            # a Google model was selected): retry with the default voice.
            result = translate_voice(
                provider,
                model,
                voice=None,
                speed=stored.get("speed"),
                instructions=stored.get("instructions"),
                audio_format=stored.get("audio_format"),
            )
        if not isinstance(result, dict) or result.get("status") != "success":
            return {}
        data = result.get("data") or {}
        voice = data.get("voice") or DEFAULT_OPENAI_VOICE
        fmt = data.get("response_format") or DEFAULT_OPENAI_FORMAT
        return {
            "modalities": ["text", "audio"],
            "audio": {"voice": voice, "format": fmt},
        }
    except Exception:
        return {}
