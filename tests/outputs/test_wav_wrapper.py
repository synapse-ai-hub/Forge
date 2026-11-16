"""Tests for build_wav_data_url (playable WAV wrapper for raw PCM)."""
import base64
import struct
import sys

sys.path.insert(0, ".")

from backend.agent.llm.outputs import build_wav_data_url


def _parse_wav(b64: str) -> tuple[bytes, bytes]:
    raw = base64.b64decode(b64)
    return raw[:44], raw[44:]


def test_wav_header_structure():
    pcm = b"\x00\x01" * 100
    tag = build_wav_data_url(pcm)
    assert tag.startswith("\n<audio controls")
    assert "data:audio/wav;base64," in tag
    b64 = tag.split("data:audio/wav;base64,")[1].split('"')[0]
    header, data = _parse_wav(b64)
    assert data == pcm
    assert header[0:4] == b"RIFF"
    assert header[8:12] == b"WAVE"
    assert header[12:16] == b"fmt "
    (channels,) = struct.unpack("<H", header[22:24])
    (rate,) = struct.unpack("<I", header[24:28])
    (bits,) = struct.unpack("<H", header[34:36])
    assert channels == 1
    assert rate == 24000
    assert bits == 16


def test_wav_empty_pcm():
    tag = build_wav_data_url(b"")
    assert "data:audio/wav;base64," in tag
    b64 = tag.split("data:audio/wav;base64,")[1].split('"')[0]
    header, data = _parse_wav(b64)
    assert data == b""
    assert header[0:4] == b"RIFF"
