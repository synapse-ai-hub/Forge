"""Whisper benchmark: Groq vs Local faster-whisper.

Requirements:
    - faster-whisper installed: pip install faster-whisper
    - Groq API key in .env as GROQ_API_KEY
    - Audio files in tests/whisper/data/ (any format: ogg, mp3, wav, etc.)

Usage:
    python tests/whisper/bench.py

Loads all audio files from tests/whisper/data/, runs 3 providers x 5 iterations
per audio, and saves results to tests/whisper/result/<timestamp>.md.
"""

from __future__ import annotations

import io
import os
import sys
import time
import statistics
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Resolve paths relative to this script
_SCRIPT_DIR = Path(__file__).resolve().parent
_DATA_DIR = _SCRIPT_DIR / "data"
_RESULT_DIR = _SCRIPT_DIR / "result"

load_dotenv(_SCRIPT_DIR.parent.parent / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
RUNS = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_audio_bytes(path: Path) -> tuple[bytes, str]:
    """Read an audio file and determine its media type for the Groq API.

    Args:
        path: Audio file.

    Returns:
        ``(bytes, media_type)`` of the file.
    """
    raw = path.read_bytes()

    if raw[:4] == b"OggS":
        media_type = "audio/ogg"
    elif raw[:4] == b"RIFF":
        media_type = "audio/wav"
    elif raw[:4] in (b"\xff\xfb", b"ID3"):
        media_type = "audio/mpeg"
    else:
        ext = path.suffix.lower()
        media_type = {
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".ogg": "audio/ogg",
            ".m4a": "audio/mp4",
            ".flac": "audio/flac",
            ".webm": "audio/webm",
        }.get(ext, "audio/ogg")

    return raw, media_type


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

def bench_local(audio_bytes: bytes) -> tuple[list[float], list[str]]:
    """Benchmark local faster-whisper (base model, CPU, int8).

    Args:
        audio_bytes: Content of the audio file.

    Returns:
        ``(times, texts)`` of every run; both empty when faster-whisper is not installed.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("  [SKIP] faster-whisper not installed")
        return [], []

    print("  Loading local model (base, cpu, int8)...")
    model = WhisperModel("base", device="cpu", compute_type="int8")

    times: list[float] = []
    texts: list[str] = []
    for i in range(RUNS):
        start = time.perf_counter()
        segments, _ = model.transcribe(io.BytesIO(audio_bytes))
        text = " ".join(seg.text for seg in segments)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
        texts.append(text)
        print(f"    Run {i + 1}/{RUNS}: {elapsed:.3f}s")

    return times, texts


def bench_groq(audio_bytes: bytes, media_type: str, model: str) -> tuple[list[float], list[str]]:
    """Benchmark Groq Whisper API.

    Args:
        audio_bytes: Content of the audio file.
        media_type: Media type of the audio.
        model: Groq model to call.

    Returns:
        ``(times, texts)`` of every run; both empty when there is no Groq API key.
    """
    if not GROQ_API_KEY:
        print("  [SKIP] GROQ_API_KEY not in .env")
        return [], []

    import httpx

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}

    times: list[float] = []
    texts: list[str] = []
    for i in range(RUNS):
        start = time.perf_counter()
        resp = httpx.post(
            url,
            headers=headers,
            files={"file": ("audio.ogg", audio_bytes, media_type)},
            data={"model": model, "language": "es"},
            timeout=30.0,
        )
        elapsed = time.perf_counter() - start
        if resp.status_code == 200:
            text = resp.json().get("text", "")
            times.append(elapsed)
            texts.append(text)
            print(f"    Run {i + 1}/{RUNS}: {elapsed:.3f}s")
        else:
            print(f"    Run {i + 1}/{RUNS}: ERROR {resp.status_code}")
            break

    return times, texts


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

def _stats(times: list[float]) -> dict:
    """Compute min, max, avg, median from a list of times.

    Args:
        times: Durations in seconds.

    Returns:
        The four statistics (zeros for an empty list).
    """
    if not times:
        return {"min": 0, "max": 0, "avg": 0, "median": 0}
    return {
        "min": min(times),
        "max": max(times),
        "avg": statistics.mean(times),
        "median": statistics.median(times),
    }


def generate_markdown(
    audio_results: list[dict],
) -> str:
    """Generate the full markdown report.

    Args:
        audio_results: One dict per audio file with its size, media type and the results of each provider.

    Returns:
        The markdown text.
    """
    lines: list[str] = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"# Whisper Benchmark — {ts}\n")
    lines.append(f"- **Runs per test:** {RUNS}")
    lines.append(f"- **Providers:** Local (base, CPU, int8), Groq v3, Groq turbo")
    lines.append(f"- **Audio files:** {len(audio_results)}\n")

    # ── Per-audio detailed results ──────────────────────────────────────
    for ar in audio_results:
        lines.append(f"---\n\n## {ar['filename']}\n")
        lines.append(f"- Size: {ar['size']:,} bytes")
        lines.append(f"- Format: {ar['media_type']}\n")

        for provider_name, data in ar["providers"].items():
            lines.append(f"### {provider_name}\n")
            if not data["times"]:
                lines.append("*Skipped*\n")
                continue

            s = _stats(data["times"])
            lines.append(f"| Metric | Value |")
            lines.append(f"|--------|-------|")
            lines.append(f"| Min | {s['min']:.3f}s |")
            lines.append(f"| Max | {s['max']:.3f}s |")
            lines.append(f"| Avg | {s['avg']:.3f}s |")
            lines.append(f"| Median | {s['median']:.3f}s |")
            lines.append("")

            lines.append("<details>\n<summary>Individual runs</summary>\n")
            for i, (t, txt) in enumerate(zip(data["times"], data["texts"])):
                lines.append(f"**Run {i + 1}** — {t:.3f}s\n")
                lines.append(f"> {txt}\n")
            lines.append("</details>\n")

    # ── Summary table per audio ─────────────────────────────────────────
    lines.append("---\n\n## Summary\n")
    lines.append("| Audio | Provider | Min | Max | Avg | Median |")
    lines.append("|-------|----------|-----|-----|-----|--------|")
    for ar in audio_results:
        for provider_name, data in ar["providers"].items():
            s = _stats(data["times"])
            lines.append(
                f"| {ar['filename']} | {provider_name} "
                f"| {s['min']:.3f}s | {s['max']:.3f}s "
                f"| {s['avg']:.3f}s | {s['median']:.3f}s |"
            )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

PROVIDERS = {
    "Local (base, CPU, int8)": lambda audio_bytes, mt: bench_local(audio_bytes),
    "Groq whisper-large-v3": lambda audio_bytes, mt: bench_groq(audio_bytes, mt, "whisper-large-v3"),
    "Groq whisper-large-v3-turbo": lambda audio_bytes, mt: bench_groq(audio_bytes, mt, "whisper-large-v3-turbo"),
}


def main() -> None:
    """Benchmark every audio file of the data folder and save the markdown report.

    Raises:
        SystemExit: If the data folder does not exist or has no audio files.
    """
    if not _DATA_DIR.exists():
        print(f"Data directory not found: {_DATA_DIR}")
        sys.exit(1)

    audio_files = sorted(
        p for p in _DATA_DIR.iterdir()
        if p.suffix.lower() in (".ogg", ".mp3", ".wav", ".m4a", ".flac", ".webm")
    )

    if not audio_files:
        print(f"No audio files found in {_DATA_DIR}")
        sys.exit(1)

    print(f"Found {len(audio_files)} audio(s) in {_DATA_DIR}\n")

    audio_results: list[dict] = []

    for af in audio_files:
        print(f"--- {af.name} ---")
        audio_bytes, media_type = get_audio_bytes(af)
        providers: dict[str, dict] = {}

        for pname, bench_fn in PROVIDERS.items():
            print(f"  {pname}:")
            times, texts = bench_fn(audio_bytes, media_type)
            providers[pname] = {"times": times, "texts": texts}

        audio_results.append({
            "filename": af.name,
            "size": len(audio_bytes),
            "media_type": media_type,
            "providers": providers,
        })
        print()

    # Save markdown
    _RESULT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = _RESULT_DIR / f"{timestamp}.md"
    md_path.write_text(generate_markdown(audio_results), encoding="utf-8")
    print(f"Results saved to {md_path}")


if __name__ == "__main__":
    main()
