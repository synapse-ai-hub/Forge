"""Draft generation in a saved voice profile."""

from __future__ import annotations

import asyncio

from voicewriter import llm as vw_llm
from voicewriter.profile import VoiceProfile
from voicewriter.verticals import get_vertical


def build_generation_prompt(
    profile: VoiceProfile,
    brief: str,
    vertical_name: str,
    format_name: str = "",
    extra: str = "",
) -> tuple[str, str]:
    """Build the system and user prompts for a voice-preserving draft."""
    vertical = get_vertical(vertical_name)
    fmt = format_name.strip() or vertical.get("default_format", "short document")

    system_parts = [
        "You are VoiceWriter, a voice-preserving writing agent.",
        "Write the requested document in the author's exact voice, using the voice "
        "instructions below. Preserve the voice; do not change it into a generic "
        "assistant tone.",
        "",
        profile.voice_instructions,
        "",
        "## Document",
        f"- Format: {fmt}",
        f"- Audience: {vertical.get('audience', 'the reader')}",
        f"- Goal: {vertical.get('goal', 'communicate the brief clearly.')}",
        f"- Guardrails: {vertical.get('guardrails', 'Stay faithful to the brief.')}",
        "",
        "## Rules",
        "- Match the author's sentence rhythm, punctuation, pronoun, contraction and hedging patterns.",
        "- Do not add facts the brief does not support; use placeholders where a fact is missing.",
        "- Output only the finished document, ready to send or publish, with no preamble.",
    ]
    if extra.strip():
        system_parts.append(f"\nAdditional instructions:\n{extra.strip()}")

    system = "\n".join(system_parts)
    user = brief.strip() or "Write the document."
    return system, user


def generate_draft(
    profile: VoiceProfile,
    brief: str,
    vertical_name: str,
    client: vw_llm.LlmClient,
    format_name: str = "",
    extra: str = "",
) -> str:
    system, user = build_generation_prompt(profile, brief, vertical_name, format_name, extra)
    return client.complete(system, user)


async def generate_draft_async(
    profile: VoiceProfile,
    brief: str,
    vertical_name: str,
    client: vw_llm.LlmClient,
    format_name: str = "",
    extra: str = "",
) -> str:
    return await asyncio.to_thread(
        generate_draft, profile, brief, vertical_name, client, format_name, extra
    )
