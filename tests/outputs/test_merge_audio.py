"""Tests for merge_audio_chunks (batch audio assembly)."""
import base64
import sys

sys.path.insert(0, ".")

from backend.agent.llm.outputs import merge_audio_chunks


def test_merge_concatenates_in_order():
    a = base64.b64encode(b"\x00\x01" * 50).decode("ascii")
    b = base64.b64encode(b"\x02\x03" * 50).decode("ascii")
    merged, mime = merge_audio_chunks([(a, "audio/l16;rate=24000"), (b, "audio/l16;rate=24000")])
    assert base64.b64decode(merged) == b"\x00\x01" * 50 + b"\x02\x03" * 50
    assert mime == "audio/l16;rate=24000"


def test_merge_empty_returns_empty():
    assert merge_audio_chunks([]) == ("", "")


def test_merge_single_chunk_roundtrip():
    raw = b"\xff\x00" * 100
    b64 = base64.b64encode(raw).decode("ascii")
    merged, _ = merge_audio_chunks([(b64, "audio/l16")])
    assert base64.b64decode(merged) == raw
