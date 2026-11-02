"""Shared helpers for the metrics endpoints package.

Every SQL statement lives as a .sql file under
``backend/agent/agent_db/queries/metrics/<section>/`` — nothing is
hardcoded here. Each endpoint maps 1:1 to its query folder.
"""

from __future__ import annotations

import csv
import io
import os
import sqlite3
import sys
from datetime import datetime
from typing import Any

from fastapi import Response

# ---------------------------------------------------------------------------
# Ensure the project root is in sys.path so absolute imports (backend.*)
# resolve correctly regardless of how the file is invoked.
# ---------------------------------------------------------------------------
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.agent.utils.queries import load_query, with_time

_VALID_RANGES = {"1h", "6h", "1d", "1w", "1m", "all"}


def _normalize_range(time_range: str) -> str:
    """Return a whitelisted time range (default ``1m``).

    Args:
        time_range: Requested range ('1h', '6h', '1d', '1w', '1m', 'all').

    Returns:
        The range if valid, otherwise ``'1m'``.
    """
    return time_range if time_range in _VALID_RANGES else "1m"


def _local_tz() -> Any:
    """Return the server's local timezone (tzinfo).

    Returns:
        The tzinfo of the current local time.
    """
    return datetime.now().astimezone().tzinfo


def _parse_ts(value: Any) -> Any | None:
    """Parse SQLite/ISO timestamps to a local-aware datetime.

    Naive values (no offset) are assumed to be local time; aware values
    are converted to the server's local timezone.

    Args:
        value: Raw timestamp string coming from SQLite.

    Returns:
        Local-timezone-aware datetime, or None when unparseable.
    """
    try:
        if value is None:
            return None
        text = str(value).strip().replace("Z", "+00:00")
        if "T" not in text and " " in text and "+" not in text and text.count(":") >= 2:
            text = text.replace(" ", "T", 1) + "+00:00"
        from datetime import datetime as _dt

        dt = _dt.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_local_tz())
        else:
            dt = dt.astimezone(_local_tz())
        return dt
    except Exception:
        return None


def _cantidad_bins(time_range: str) -> tuple[Any, Any, int]:
    """Return (start, end, bins) in local time for the fixed 12-bar chart.

    Args:
        time_range: Whitelisted range string.

    Returns:
        Tuple of (range start, range end, number of bins).
    """
    try:
        from datetime import timedelta

        now = datetime.now().astimezone()
        if time_range == "1h":
            base = now.replace(second=0, microsecond=0)
            base = base.replace(minute=(base.minute // 5) * 5)
            return base - timedelta(hours=1), base + timedelta(minutes=5), 12
        elif time_range == "6h":
            base = now.replace(second=0, microsecond=0)
            base = base.replace(minute=(base.minute // 30) * 30)
            return base - timedelta(hours=6), base + timedelta(minutes=30), 12
        elif time_range == "1d":
            base = now.replace(minute=0, second=0, microsecond=0)
            return base - timedelta(hours=22), base + timedelta(hours=2), 12
        elif time_range == "1w":
            base = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return base - timedelta(days=6), base + timedelta(days=1), 7
        elif time_range == "1m":
            base = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return base - timedelta(days=29), base + timedelta(days=1), 12
        base = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return base - timedelta(days=364), base + timedelta(days=1), 12
    except Exception:
        from datetime import timedelta

        now = datetime.now().astimezone()
        return now - timedelta(days=6), now + timedelta(days=1), 12


def _bin_label(dt: Any, time_range: str) -> str:
    """Short label shown below the axis line.

    Args:
        dt: Datetime of the bin midpoint.
        time_range: Whitelisted range string.

    Returns:
        Formatted label for the range granularity.
    """
    try:
        if time_range in ("1h", "6h"):
            return dt.strftime("%H:%M")
        if time_range == "1d":
            return dt.strftime("%Hh")
        if time_range == "1w":
            return dt.strftime("%m-%d")
        if time_range == "1m":
            return dt.strftime("%m-%d")
        return dt.strftime("%Y-%m")
    except Exception:
        return ""


def _fill_cantidad_buckets(time_range: str, rows: list) -> list:
    """Bin raw session timestamps into exactly 12 equal bars (fixed width).

    Args:
        time_range: Whitelisted range string.
        rows: Rows from ``metrics/sessions/created_at_list.sql``.

    Returns:
        List of ``{"date": label, "count": n}`` dicts, one per bin.
    """
    try:
        from datetime import timedelta

        start, end, bins = _cantidad_bins(time_range)
        span = (end - start).total_seconds() or 1
        counts = [0] * bins
        labels = [""] * bins
        for i in range(bins):
            b_start = start + (end - start) * i / bins
            b_end = start + (end - start) * (i + 1) / bins
            mid = b_start + (b_end - b_start) / 2
            labels[i] = _bin_label(mid, time_range)
        for r in rows:
            ts = r["ts"] if isinstance(r, dict) else r[0]
            dt = _parse_ts(ts)
            if dt is None:
                continue
            if dt < start or dt >= end:
                continue
            idx = int((dt - start).total_seconds() / span * bins)
            idx = max(0, min(bins - 1, idx))
            counts[idx] += 1
        return [{"date": labels[i], "count": counts[i]} for i in range(bins)]
    except Exception:
        return [{"date": "", "count": 0} for _ in range(12)]


def _fetch_one(conn: sqlite3.Connection, path: str, clause: str, params: tuple) -> Any:
    """Execute a query file with the time clause and return its first cell.

    Args:
        conn: Open SQLite connection.
        path: Query path relative to ``agent_db/queries``.
        clause: Time filter clause (local-time ``strftime`` bound).
        params: Parameters for the clause.

    Returns:
        The first column of the first row (None when no rows).
    """
    sql = with_time(load_query(path), clause)
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _rows_to_csv_response(rows: list, name: str) -> Response:
    """Serialize fetched SQLite rows into a single-line-per-record CSV.

    Newline characters inside string cells (``\\r\\n``, ``\\r``, ``\\n``)
    are replaced by the literal two-character sequence ``\\n`` so every
    record occupies exactly one physical line in the file; the original
    breaks remain visible as text.

    Args:
        rows: Fetched rows (``sqlite3.Row``); the first row provides the
            header names.
        name: Base filename (without extension) for the attachment.

    Returns:
        A ``text/csv`` response with an attachment disposition header.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    if rows:
        header = list(rows[0].keys())
        writer.writerow(header)
        for row in rows:
            cells = []
            for key in header:
                cell = row[key]
                if isinstance(cell, str):
                    cell = (
                        cell.replace("\r\n", "\n")
                        .replace("\r", "\n")
                        .replace("\n", "\\n")
                    )
                cells.append(cell)
            writer.writerow(cells)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
    )


__all__ = [
    "_normalize_range",
    "_local_tz",
    "_parse_ts",
    "_cantidad_bins",
    "_bin_label",
    "_fill_cantidad_buckets",
    "_fetch_one",
    "_rows_to_csv_response",
]
