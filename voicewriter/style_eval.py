"""Style similarity, pairwise evaluation and preference rankings."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

from voicewriter import config
from voicewriter import llm as vw_llm
from voicewriter.extract import extract_features
from voicewriter.profile import VoiceProfile

ELO_START = 1200.0
ELO_K = 32.0
TIE_THRESHOLD = 0.02


def _closeness(a: float, b: float, scale: float) -> float:
    if scale <= 0:
        return 1.0
    return max(0.0, 1.0 - abs(a - b) / scale)


def _rate_closeness(a: float, b: float) -> float:
    return max(0.0, 1.0 - abs(a - b) / max(abs(b), 0.5))


def style_similarity(text: str, profile: VoiceProfile) -> dict:
    """Score how closely a text matches a profile's rule-based voice fingerprint."""
    features = extract_features(text)
    ref = profile.features

    components = {
        "sentence_length": _closeness(features["avg_sentence_length"], ref["avg_sentence_length"], 15.0),
        "type_token_ratio": _closeness(features["type_token_ratio"], ref["type_token_ratio"], 0.5),
        "avg_word_length": _rate_closeness(features["avg_word_length"], ref["avg_word_length"]),
        "formality": _closeness(features["formality"], ref["formality"], 1.0),
        "comma": _closeness(features["comma_per_100"], ref["comma_per_100"], 8.0),
        "em_dash": _closeness(features["em_dash_per_100"], ref["em_dash_per_100"], 3.0),
        "contractions": _closeness(features["contractions_per_100"], ref["contractions_per_100"], 4.0),
        "hedging": _closeness(features["hedging_per_100"], ref["hedging_per_100"], 2.0),
        "first_person": _closeness(features["first_person_per_100"], ref["first_person_per_100"], 8.0),
        "second_person": _closeness(features["second_person_per_100"], ref["second_person_per_100"], 4.0),
    }
    weights = {
        "sentence_length": 0.2,
        "type_token_ratio": 0.1,
        "avg_word_length": 0.1,
        "formality": 0.2,
        "comma": 0.1,
        "em_dash": 0.08,
        "contractions": 0.08,
        "hedging": 0.05,
        "first_person": 0.05,
        "second_person": 0.04,
    }
    score = sum(components[key] * weights[key] for key in components)
    return {"score": round(score, 4), "components": {key: round(value, 4) for key, value in components.items()}}


def pairwise(text_a: str, text_b: str, profile: VoiceProfile) -> dict:
    """Compare two drafts and return the one that better matches the profile."""
    a = style_similarity(text_a, profile)
    b = style_similarity(text_b, profile)
    if abs(a["score"] - b["score"]) < TIE_THRESHOLD:
        winner = "tie"
    elif a["score"] > b["score"]:
        winner = "a"
    else:
        winner = "b"
    return {
        "score_a": a["score"],
        "score_b": b["score"],
        "winner": winner,
        "delta": round(a["score"] - b["score"], 4),
        "components_a": a["components"],
        "components_b": b["components"],
    }


def llm_judge(text_a: str, text_b: str, profile: VoiceProfile, client: vw_llm.LlmClient) -> dict:
    """Use an LLM judge to pick which draft better preserves the voice."""
    system = (
        "You are a style judge. Given a voice profile and two drafts, pick the draft "
        "that better preserves the author's voice. Answer with only one token: A, B or TIE."
    )
    user = (
        f"Voice:\n{profile.voice_instructions}\n\n"
        f"Draft A:\n{text_a}\n\n"
        f"Draft B:\n{text_b}"
    )
    raw = client.complete(system, user).strip().upper()
    if raw.startswith("A"):
        winner = "a"
    elif raw.startswith("B"):
        winner = "b"
    else:
        winner = "tie"
    return {"winner": winner, "raw": raw}


def _expected(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def record_preference(winner: str, loser: str, profile_name: str) -> dict:
    """Append a pairwise preference to the JSONL preference log."""
    config.ensure_dirs()
    entry = {
        "winner": winner,
        "loser": loser,
        "profile": profile_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with config.prefs_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    return entry


def load_preferences(profile_name: str | None = None) -> list[dict]:
    path = config.prefs_path()
    if not path.is_file():
        return []
    preferences: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if profile_name and entry.get("profile") != profile_name:
            continue
        preferences.append(entry)
    return preferences


def rankings(profile_name: str | None = None) -> list[dict]:
    """Compute Elo rankings from recorded pairwise preferences."""
    ratings: dict[str, float] = {}
    matches: Counter = Counter()
    for entry in load_preferences(profile_name):
        winner = entry.get("winner")
        loser = entry.get("loser")
        if not winner or not loser:
            continue
        rating_winner = ratings.setdefault(winner, ELO_START)
        rating_loser = ratings.setdefault(loser, ELO_START)
        expected_winner = _expected(rating_winner, rating_loser)
        expected_loser = _expected(rating_loser, rating_winner)
        ratings[winner] = rating_winner + ELO_K * (1.0 - expected_winner)
        ratings[loser] = rating_loser + ELO_K * (0.0 - expected_loser)
        matches[winner] += 1
        matches[loser] += 1

    return sorted(
        [
            {"name": name, "elo": round(rating, 1), "matches": matches[name]}
            for name, rating in ratings.items()
        ],
        key=lambda item: item["elo"],
        reverse=True,
    )
