"""Lightweight distribution data for metrics HistBox (no pandas/matplotlib).

Returns binned histogram + stats computed with sqlite3 + stdlib only,
so the frontend can render with the same style/colors (#8b5cf6).
"""

from __future__ import annotations

import math
import sqlite3
import statistics
from typing import Any

from backend.agent.utils.db import DB_PATH
from backend.agent.utils.queries import (
    MODEL_PLACEHOLDER,
    TIME_PLACEHOLDER,
    load_query,
    time_clause,
)

_VALID_RANGES = {"1h", "6h", "1d", "1w", "1m", "all"}
_N_BINS = 30


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        f = float(value)
        # NaN / inf are not plottable
        if f != f or f in (float("inf"), float("-inf")):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _is_integer_series(vals: list[float]) -> bool:
    try:
        return len(vals) > 0 and all(abs(v - round(v)) < 1e-9 for v in vals)
    except (TypeError, ValueError):
        return False


def render_distribution(
    query_file: str,
    value_column: str,
    time_range: str = "1m",
    placeholder: str = TIME_PLACEHOLDER,
    filter_column: str = "sessions.created_at",
    percentile: float | None = None,
    model_clause: str = "",
    model_params: tuple[Any, ...] = (),
) -> dict[str, Any]:
    """Run a metric query and return binned histogram + stats.

    Args:
        query_file: Script path relative to queries root.
        value_column: Numeric column to bin.
        time_range: One of 1h, 6h, 1d, 1w, 1m, all.
        placeholder: Time filter placeholder in SQL.
        filter_column: Column the time filter applies to.
        percentile: When set (0 < q < 1), bins are capped at that quantile.
        model_clause: Optional SQL for {MODEL_CLAUSE} placeholder.
        model_params: Parameters for model_clause.

    Returns:
        Dict with bins ([{label, count}]) and stats.

    Raises:
        ValueError: If query returns no plottable values.
    """
    if time_range not in _VALID_RANGES:
        time_range = "1m"
    clause, params = time_clause(time_range, filter_column)
    sql = load_query(query_file)
    # Strip comment lines to count placeholders reliably
    code_lines = [line for line in sql.splitlines() if not line.lstrip().startswith("--")]
    code = "\n".join(code_lines)
    time_count = code.count(placeholder)
    code = code.replace(placeholder, clause)
    model_count = code.count(MODEL_PLACEHOLDER)
    code = code.replace(MODEL_PLACEHOLDER, model_clause)
    full_params: tuple[Any, ...] = params * time_count + model_params * model_count

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(code, full_params if full_params else ())
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        raise ValueError("No data for this range")
    if value_column not in rows[0].keys():
        raise ValueError(f"Column {value_column} not in query result")

    values: list[float] = []
    for r in rows:
        f = _to_float(r[value_column])
        if f is not None:
            values.append(f)
    if not values:
        raise ValueError("No data for this range")

    values.sort()
    n = len(values)
    v_min = values[0]
    v_max = values[-1]
    v_mean = statistics.fmean(values)
    v_median = statistics.median(values)
    try:
        modes = statistics.multimode(values)
        v_mode: Any = modes[0] if modes else "No mode"
    except (statistics.StatisticsError, ValueError, TypeError):
        v_mode = "No mode"
    try:
        v_std = statistics.pstdev(values) if n > 1 else 0.0
    except (statistics.StatisticsError, ValueError, TypeError):
        v_std = 0.0
    try:
        qs = statistics.quantiles(values, n=4, method="exclusive") if n >= 4 else [v_min, v_median, v_max]
        q1, _, q3 = qs[0], qs[1] if len(qs) > 1 else v_median, qs[2] if len(qs) > 2 else v_max
    except (statistics.StatisticsError, ValueError, TypeError):
        q1, q3 = v_min, v_max
    q2 = v_median
    q4 = v_max
    iqr = q3 - q1
    tlo = q3 + 1.5 * iqr
    blo = q1 - 1.5 * iqr
    oq = sum(1 for v in values if v > tlo or v < blo)

    # Percentile cap for display bins (stats stay full, like old behavior)
    display = values
    if percentile is not None and 0 < percentile < 1:
        try:
            threshold = statistics.quantiles(values, n=100, method="exclusive")[int(percentile * 100) - 1] if n >= 100 else values[min(n - 1, int(n * percentile))]
            display = [v for v in values if v <= threshold]
        except (statistics.StatisticsError, ValueError, TypeError):
            display = values
    if not display:
        display = values

    # Integer data (tokens, steps, counts) -> always integer bins, 10 bands
    is_int = _is_integer_series(display)
    # Tokens/steps/counts by name are always integers even with float noise
    lname = (value_column or "").lower()
    if any(k in lname for k in ("token", "step", "count", "cnt", "msg_count", "steps", "input_tokens", "output_tokens")):
        is_int = True

    d_min, d_max = display[0], display[-1]
    if d_min == d_max:
        if is_int:
            iv = int(round(d_min))
            bins = [{"label": f"{iv}", "count": len(display), "low": iv, "high": iv}]
        else:
            bins = [{"label": f"{d_min:.4f}".rstrip("0").rstrip("."), "count": len(display), "low": d_min, "high": d_max}]
    else:
        span = d_max - d_min or 1.0
        # Tokens: 10 bands always. Floats: Sturges 5-12.
        try:
            if is_int:
                n_bins = min(10, max(5, math.ceil(math.log2(max(len(display), 2))) + 1))
                # User asked tokens in 10: use 10 when enough data
                if len(display) >= 10:
                    n_bins = 10
            else:
                n_bins = min(12, max(5, math.ceil(math.log2(max(len(display), 2))) + 1))
        except (ValueError, OverflowError, TypeError):
            n_bins = 10 if is_int else 12
        bin_width = span / n_bins
        if is_int:
            decimals = 0
        else:
            try:
                decimals = max(2, min(6, -math.floor(math.log10(bin_width)) + 1)) if bin_width > 0 else 2
            except (ValueError, OverflowError, TypeError):
                decimals = 2
        counts = [0] * n_bins
        for v in display:
            idx = int((v - d_min) / span * n_bins)
            idx = max(0, min(n_bins - 1, idx))
            counts[idx] += 1
        bins = []
        for i, c in enumerate(counts):
            low = d_min + span * i / n_bins
            high = d_min + span * (i + 1) / n_bins
            if is_int:
                label = f"{int(round(low))}"
            else:
                raw = f"{low:.{decimals}f}"
                label = raw.rstrip("0").rstrip(".") if "." in raw else raw
            bins.append({"label": label, "count": c, "low": low, "high": high})

    def _r(x: Any) -> Any:
        try:
            return round(float(x), 4)
        except (TypeError, ValueError):
            return x

    # Outlier values for display (up to 10 smallest + 10 largest beyond limits)
    try:
        lows = sorted([v for v in values if v < blo])[:10] if not (blo < 0 and min(values or [0]) >= 0) else []
        highs = sorted([v for v in values if v > tlo])[-10:]
        outlier_vals = lows + highs
    except (TypeError, ValueError):
        outlier_vals = []

    stats = {
        "min": _r(v_min),
        "max": _r(v_max),
        "mean": _r(v_mean),
        "median": _r(v_median),
        "mode": _r(v_mode) if isinstance(v_mode, (int, float)) else v_mode,
        "Q1": _r(q1),
        "Q2": _r(q2),
        "Q3": _r(q3),
        "Q4": _r(q4),
        "STD": _r(v_std),
        "IQR": _r(iqr),
        "Top Limit Outliers": _r(tlo),
        "Bottom Limit Outliers": "N/A" if blo < 0 else _r(blo),
        "Total Data": n,
        "Outliers Quantity": oq,
        "outliers": [_r(v) for v in outlier_vals],
    }
    return {"bins": bins, "stats": stats}
