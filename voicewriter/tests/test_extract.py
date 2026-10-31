"""Tests for rule-based voice feature extraction."""

from voicewriter.extract import build_voice_instructions, extract_features, formality_label, style_markers

SAMPLE = (
    "I've been building this for a while. Honestly, it might be the right call. "
    "The team is strong, the market is clear, and we have real momentum. "
    "You should take a look - really. We could close this quarter, maybe even sooner."
)


def test_extract_features_basic() -> None:
    features = extract_features(SAMPLE)
    assert features["word_count"] > 0
    assert 0.0 <= features["type_token_ratio"] <= 1.0
    assert features["avg_sentence_length"] > 0
    assert 0.0 <= features["formality"] <= 1.0
    assert isinstance(features["signature_phrases"], list)


def test_formality_label_bounds() -> None:
    assert formality_label(0.0) == "casual"
    assert formality_label(0.9) == "formal"
    assert formality_label(0.5) == "conversational"


def test_style_markers_and_instructions() -> None:
    features = extract_features(SAMPLE)
    markers = style_markers(features)
    assert isinstance(markers, list)
    instructions = build_voice_instructions("sample", features, markers)
    assert "## Voice instructions" in instructions
    assert "sample" in instructions
