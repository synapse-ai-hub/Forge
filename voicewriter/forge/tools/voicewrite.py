"""Build a writer's voice profile from samples and draft or compare text in that voice (fundraising, legal, newsletter)."""

import asyncio

from voicewriter import llm as vw_llm
from voicewriter import profile as vw_profile
from voicewriter import style_eval as vw_eval
from voicewriter.generate import build_generation_prompt


def _zero_usage() -> dict:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "total_time": 0.0,
    }


def _ok(message: str, data: object = None) -> dict:
    return {"status": "success", "message": message, "data": data, "usage": _zero_usage()}


def _err(message: str) -> dict:
    return {"status": "error", "message": message, "data": None, "usage": _zero_usage()}


async def voicewrite(
    action: str,
    profile_name: str = "",
    vertical: str = "general",
    samples: list[str] | None = None,
    brief: str = "",
    format_name: str = "",
    text_a: str = "",
    text_b: str = "",
) -> dict:
    """Build and use a writer's voice profile.

    Args:
        action: One of "profile", "list", "show", "generate", "eval" or "rank".
        profile_name: Voice profile name (used by profile, show, generate and eval).
        vertical: Vertical for the profile or draft: "general", "fundraising", "legal" or "newsletter".
        samples: For action="profile": list of file paths, directories, or raw sample texts.
        brief: For action="generate": the writing brief or topic.
        format_name: For action="generate": document format (e.g. "pitch email", "client memo", "issue").
        text_a: For action="eval": first draft (file path or raw text).
        text_b: For action="eval": second draft (file path or raw text).

    Returns:
        dict with the unified tool contract {status, message, data, usage}.
    """
    action = (action or "").strip().lower()
    profile_name = (profile_name or "").strip()
    vertical = (vertical or "general").strip().lower()

    try:
        if action == "profile":
            if not profile_name:
                return _err("action='profile' requires profile_name.")
            texts = vw_profile.resolve_samples(samples or [])
            if not texts:
                return _err("No usable samples found for the voice profile.")
            profile = vw_profile.build_profile(profile_name, texts, vertical)
            vw_profile.save_profile(profile)
            return _ok(
                f"Voice profile '{profile_name}' built.",
                {
                    "name": profile.name,
                    "vertical": profile.vertical,
                    "sample_count": profile.sample_count,
                    "sample_words": profile.sample_words,
                    "style_markers": profile.style_markers,
                    "voice_instructions": profile.voice_instructions,
                    "features": profile.features,
                },
            )

        if action == "list":
            return _ok("Saved voice profiles.", {"profiles": vw_profile.list_profiles()})

        if action == "show":
            if not profile_name:
                return _err("action='show' requires profile_name.")
            profile = vw_profile.load_profile(profile_name)
            if profile is None:
                return _err(f"Voice profile '{profile_name}' not found.")
            return _ok(f"Voice profile '{profile_name}'.", profile.to_dict())

        if action == "generate":
            if not profile_name:
                return _err("action='generate' requires profile_name.")
            if not brief.strip():
                return _err("action='generate' requires brief.")
            profile = vw_profile.load_profile(profile_name)
            if profile is None:
                return _err(f"Voice profile '{profile_name}' not found.")
            client = vw_llm.from_config()
            if not client.configured:
                return _err(
                    "No LLM backend configured for the voicewrite tool. Set "
                    "VOICEWRITER_LLM_PROVIDER, VOICEWRITER_LLM_BASE_URL and "
                    "VOICEWRITER_LLM_MODEL."
                )
            system, user = build_generation_prompt(profile, brief, vertical, format_name)
            draft = await asyncio.to_thread(client.complete, system, user)
            return _ok(
                f"Generated {vertical} draft in voice '{profile_name}'.",
                {
                    "profile": profile_name,
                    "vertical": vertical,
                    "format": format_name or None,
                    "draft": draft,
                },
            )

        if action == "eval":
            if not profile_name:
                return _err("action='eval' requires profile_name.")
            profile = vw_profile.load_profile(profile_name)
            if profile is None:
                return _err(f"Voice profile '{profile_name}' not found.")
            text_a_resolved = vw_profile.resolve_text(text_a)
            text_b_resolved = vw_profile.resolve_text(text_b)
            if not text_a_resolved.strip() or not text_b_resolved.strip():
                return _err("action='eval' requires non-empty text_a and text_b.")
            result = vw_eval.pairwise(text_a_resolved, text_b_resolved, profile)
            return _ok(f"Style comparison against '{profile_name}'.", result)

        if action == "rank":
            return _ok(
                "Preference rankings.",
                {"rankings": vw_eval.rankings(profile_name or None)},
            )

        return _err("Unknown action. Use 'profile', 'list', 'show', 'generate', 'eval' or 'rank'.")
    except Exception as exc:  # defensive tool boundary
        return _err(f"voicewrite error: {exc}")
