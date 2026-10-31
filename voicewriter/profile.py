"""Voice profile building and persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from voicewriter import config
from voicewriter.extract import build_voice_instructions, extract_features, style_markers

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".rst", ".tex", ".html"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class VoiceProfile:
    name: str
    vertical: str
    features: dict
    style_markers: list[str]
    voice_instructions: str
    created_at: str
    updated_at: str
    sample_count: int = 0
    sample_words: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "vertical": self.vertical,
            "features": self.features,
            "style_markers": self.style_markers,
            "voice_instructions": self.voice_instructions,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "sample_count": self.sample_count,
            "sample_words": self.sample_words,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VoiceProfile":
        return cls(
            name=data["name"],
            vertical=data.get("vertical", "general"),
            features=data.get("features", {}),
            style_markers=data.get("style_markers", []),
            voice_instructions=data.get("voice_instructions", ""),
            created_at=data.get("created_at", _now()),
            updated_at=data.get("updated_at", _now()),
            sample_count=int(data.get("sample_count", 0)),
            sample_words=int(data.get("sample_words", 0)),
        )


def build_profile(name: str, sample_texts: list[str], vertical: str = "general") -> VoiceProfile:
    """Build a voice profile from one or more sample texts."""
    cleaned = [text.strip() for text in sample_texts if text.strip()]
    combined = "\n\n".join(cleaned)
    features = extract_features(combined)
    markers = style_markers(features)
    now = _now()
    return VoiceProfile(
        name=name,
        vertical=vertical,
        features=features,
        style_markers=markers,
        voice_instructions=build_voice_instructions(name, features, markers),
        created_at=now,
        updated_at=now,
        sample_count=len(cleaned),
        sample_words=features["word_count"],
    )


def _safe_name(name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "-" for char in name.strip())
    return cleaned or "profile"


def _profile_path(name: str) -> Path:
    return config.profiles_dir() / f"{_safe_name(name)}.json"


def save_profile(profile: VoiceProfile) -> Path:
    config.ensure_dirs()
    path = _profile_path(profile.name)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(profile.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def load_profile(name: str) -> VoiceProfile | None:
    path = _profile_path(name)
    if not path.is_file():
        return None
    return VoiceProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))


def list_profiles() -> list[str]:
    config.ensure_dirs()
    return sorted(path.stem for path in config.profiles_dir().glob("*.json"))


def delete_profile(name: str) -> bool:
    path = _profile_path(name)
    if path.is_file():
        path.unlink()
        return True
    return False


def resolve_samples(items: list[str]) -> list[str]:
    """Resolve sample inputs: file paths, directories, or raw text."""
    texts: list[str] = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        path = Path(item).expanduser()
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in TEXT_SUFFIXES:
                    texts.append(child.read_text(encoding="utf-8", errors="replace"))
        elif path.is_file():
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
        else:
            texts.append(item)
    return texts


def resolve_text(value: str) -> str:
    """Resolve a single file path or raw text value."""
    value = value.strip()
    path = Path(value).expanduser()
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    return value
