# Forge integration

VoiceWriter ships as two Forge artifacts:

- **Skill** — `skills/voice-preserving-writer/SKILL.md` teaches the agent the voice-preserving workflow and rules.
- **Tool** — `tools/voicewrite.py` exposes the executable capability as a Forge external tool.

## Install

From the repository root:

```bash
python -m voicewriter install-forge
```

This copies the skill and tool into `~/.config/synapseForge/`. Restart the Forge
backend (or refresh tools) to pick them up.

## Tool actions

| Action | What it does |
|--------|--------------|
| `profile` | Build a saved voice profile from samples. |
| `list` | List saved profiles. |
| `show` | Show a saved profile. |
| `generate` | Draft text in a voice (requires `VOICEWRITER_LLM_*` backend). |
| `eval` | Compare two drafts against a profile (rule-based). |
| `rank` | Show Elo rankings from recorded preferences. |

The `generate` action needs an LLM backend. The profile and eval actions are
fully deterministic and need no API key.
