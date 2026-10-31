"""Tests for voice profile building and persistence."""

from voicewriter.profile import (
    build_profile,
    delete_profile,
    list_profiles,
    load_profile,
    resolve_text,
    save_profile,
)


def test_profile_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VOICEWRITER_HOME", str(tmp_path))
    profile = build_profile("ada", ["Short punchy text. Another short one!"], "newsletter")
    save_profile(profile)

    loaded = load_profile("ada")
    assert loaded is not None
    assert loaded.name == "ada"
    assert loaded.vertical == "newsletter"
    assert loaded.voice_instructions
    assert "ada" in list_profiles()

    delete_profile("ada")
    assert load_profile("ada") is None


def test_resolve_text(tmp_path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("hello world", encoding="utf-8")
    assert resolve_text(str(path)) == "hello world"
    assert resolve_text("raw text") == "raw text"
