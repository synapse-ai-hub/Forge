# VoiceWriter

A voice-preserving writing agent. It ingests a writer's samples, builds a voice
profile, and produces fundraising, legal, or newsletter drafts that sound like
that writer instead of a generic assistant.

The hard part is style evaluation and preference data, so the prototype ships
three things together:

1. **Voice extraction** — a rule-based fingerprint (rhythm, punctuation,
   pronouns, contractions, hedging, vocabulary, signature phrases).
2. **Style evals** — deterministic pairwise similarity plus an optional LLM judge.
3. **Preference data** — a JSONL preference log with Elo rankings, so better
   voices and better drafts can be ranked over time.

## Layout

```
voicewriter/
├── cli.py           # CLI entry point
├── config.py        # data paths + LLM env config
├── extract.py       # rule-based voice feature extraction
├── generate.py      # draft generation prompts
├── llm.py           # OpenAI-compatible + Ollama clients
├── profile.py       # VoiceProfile build/save/load
├── style_eval.py    # similarity, pairwise, LLM judge, Elo prefs
├── verticals.py     # fundraising / legal / newsletter templates
├── forge/           # Forge skill + external tool
└── tests/
```

## Quick start

Run from the repository root (Python 3.12+):

```bash
# Build a voice profile from files or raw text
python -m voicewriter profile ada --samples samples/*.txt --vertical newsletter

# List and inspect profiles
python -m voicewriter profiles
python -m voicewriter show ada

# Generate a draft (needs an LLM backend)
export VOICEWRITER_LLM_PROVIDER=openai
export VOICEWRITER_LLM_BASE_URL=https://api.openai.com/v1
export VOICEWRITER_LLM_API_KEY=...
export VOICEWRITER_LLM_MODEL=gpt-4o-mini
python -m voicewriter generate ada --brief "Weekly update for 12k subscribers" --vertical newsletter
```

Ollama works too:

```bash
export VOICEWRITER_LLM_PROVIDER=ollama
export VOICEWRITER_LLM_BASE_URL=http://localhost:11434
export VOICEWRITER_LLM_MODEL=llama3.2
```

## Style evals and preference data

Compare two drafts against a profile:

```bash
python -m voicewriter eval ada --a draft1.md --b draft2.md
python -m voicewriter eval ada --a draft1.md --b draft2.md --judge llm
```

Record pairwise preferences and see Elo rankings:

```bash
python -m voicewriter prefs add --profile ada --winner draft2 --loser draft1
python -m voicewriter prefs rank --profile ada
```

The preference log is a JSONL file under `~/.config/voicewriter/preferences.jsonl`
(override with `VOICEWRITER_HOME`).

## Forge integration

VoiceWriter can also run as a Forge skill and external tool:

```bash
python -m voicewriter install-forge
```

This copies the skill (`voice-preserving-writer`) and tool (`voicewrite`) into
`~/.config/synapseForge/`. See `forge/README.md` for the tool actions.

## Tests

```bash
python -m pytest voicewriter/tests -q
```
