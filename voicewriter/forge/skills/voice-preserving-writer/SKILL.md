---
description: "Voice-preserving writing agent. Extracts an author's voice from samples and drafts fundraising, legal, or newsletter copy that sounds like them."
triggers: "write in my voice, sound like me, voice profile, match my style, fundraising update, investor email, legal memo, newsletter draft, style eval, voice-preserving"
---

# Voice-Preserving Writer

## Purpose
Produce written work that preserves the author's distinctive voice instead of sounding like a generic assistant.

## Workflow
1. Gather writing samples from the user (files, directories, or pasted text).
2. Call the `voicewrite` tool with `action="profile"` to build a saved voice profile.
3. To draft, call `voicewrite` with `action="generate"` and the brief. If the tool has no LLM backend, write the draft yourself and follow the returned `voice_instructions` exactly.
4. When the user gives two candidate drafts, call `voicewrite` with `action="eval"` to compare both against the profile.

## Verticals
- `fundraising`: investor updates, pitch emails, memos, one-pagers.
- `legal`: client memos, demand letters, risk summaries, term explanations.
- `newsletter`: issues, welcome emails, essays, roundups.

## Writing rules
- Match the author's sentence rhythm, paragraph rhythm, punctuation, pronoun use, contractions and hedging profile.
- Reuse signature phrases only when they fit naturally; do not force them.
- Never invent facts, numbers, quotes or citations. Use placeholders where the brief lacks a fact.
- For legal drafts, include a short "this is not legal advice" notice when appropriate.
- Output the finished document only, with no preamble.
