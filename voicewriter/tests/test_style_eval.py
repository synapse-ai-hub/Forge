"""Tests for style evaluation and preference rankings."""

from voicewriter.profile import build_profile
from voicewriter.style_eval import pairwise, rankings, record_preference

REFERENCE = (
    "I've been at this for a while. It might work. The team is strong and the market is clear. "
    "You should look - really."
)
CLOSE = (
    "I've been at this for years. It could work out. The team is strong and the market is clear. "
    "You should see it - truly."
)
FAR = (
    "This communication hereby notifies the recipient that certain conclusions may be drawn. "
    "Accordingly, the undersigned respectfully requests review."
)


def test_pairwise_prefers_closer_text() -> None:
    profile = build_profile("ref", [REFERENCE])
    result = pairwise(CLOSE, FAR, profile)
    assert result["winner"] == "a"
    assert result["score_a"] > result["score_b"]


def test_rankings_from_preferences(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VOICEWRITER_HOME", str(tmp_path))
    record_preference("draft-b", "draft-a", "ref")
    record_preference("draft-b", "draft-a", "ref")
    rows = rankings("ref")
    assert rows[0]["name"] == "draft-b"
    assert rows[0]["elo"] > rows[1]["elo"]
