"""Chunking params: validation of ``_parse_chunk_int`` and ``_resolve_chunking``.

Covers valid inputs, nulls (defaults), non-numeric strings, booleans,
floats and out-of-range values. All rejections must be Spanish messages.
"""

from __future__ import annotations

from backend.routes.rag import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_OVERLAP,
    AddUrlRequest,
    _parse_chunk_int,
    _resolve_chunking,
)


def test_defaults_when_none() -> None:
    """None params fall back to the default chunk size and overlap."""
    assert _resolve_chunking(None, None) == (DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP)


def test_valid_ints() -> None:
    """Integer inputs are accepted as-is."""
    assert _resolve_chunking(1000, 100) == (1000, 100)


def test_valid_numeric_strings() -> None:
    """Numeric strings (Form data) are parsed to int."""
    assert _resolve_chunking("1000", "100") == (1000, 100)
    assert _resolve_chunking("  500  ", "60") == (500, 60)


def test_zero_overlap_allowed() -> None:
    """Overlap 0 is valid."""
    assert _resolve_chunking(500, 0) == (500, 0)


def test_overlap_larger_than_chunk_allowed() -> None:
    """Overlap larger than chunk size does not loop (chunking advances by base)."""
    assert _resolve_chunking(10, 100) == (10, 100)


def test_zero_or_negative_chunk_rejected() -> None:
    """Chunk size <= 0 returns a Spanish error message."""
    assert _resolve_chunking(0, 60) == "El tamaño de chunk debe ser un entero mayor a 0."
    assert _resolve_chunking(-5, 60) == "El tamaño de chunk debe ser un entero mayor a 0."
    assert _resolve_chunking("0", "60") == "El tamaño de chunk debe ser un entero mayor a 0."


def test_negative_overlap_rejected() -> None:
    """Negative overlap returns a Spanish error message."""
    assert _resolve_chunking(500, -1) == "El overlap debe ser un entero mayor o igual a 0."


def test_non_numeric_strings_rejected() -> None:
    """Non-numeric strings return Spanish errors, not exceptions."""
    assert _resolve_chunking("abc", "60") == "El tamaño de chunk debe ser un entero mayor a 0."
    assert _resolve_chunking("12.5", "60") == "El tamaño de chunk debe ser un entero mayor a 0."
    assert _resolve_chunking("", "60") == "El tamaño de chunk debe ser un entero mayor a 0."
    assert _resolve_chunking("500", "xyz") == "El overlap debe ser un entero mayor o igual a 0."


def test_floats_and_bools_rejected() -> None:
    """Floats and bools are not valid integers."""
    assert _resolve_chunking(500.5, 60) == "El tamaño de chunk debe ser un entero mayor a 0."
    assert _resolve_chunking(500, 60.0) == "El overlap debe ser un entero mayor o igual a 0."
    assert _resolve_chunking(True, 60) == "El tamaño de chunk debe ser un entero mayor a 0."


def test_parse_chunk_int_none_returns_default() -> None:
    """None returns the given default."""
    assert _parse_chunk_int(None, 500, "chunk") == 500
    assert _parse_chunk_int(None, 60, "overlap") == 60


def test_add_url_request_defaults() -> None:
    """AddUrlRequest without chunking fields resolves to defaults."""
    req = AddUrlRequest(url="https://example.com/doc")
    assert _resolve_chunking(req.chunk_size, req.overlap) == (DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP)


def test_add_url_request_invalid_json_types() -> None:
    """Float/bool JSON values are rejected with Spanish messages."""
    req = AddUrlRequest(url="https://example.com/doc", chunk_size=12.5, overlap="abc")
    assert _resolve_chunking(req.chunk_size, req.overlap) == (
        "El tamaño de chunk debe ser un entero mayor a 0."
    )
