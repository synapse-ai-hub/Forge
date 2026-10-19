"""Pytest plugin shared by the test folders: writes a ``.log`` with the results.

For every folder listed in :data:`LOGGED_FOLDERS` that ran tests, a file
``tests/<folder>/reports/pytest_<yyyymmdd_HHMMSS>.log`` is written when the
session ends (local time). It holds one line per test with its outcome and
duration, the failure detail of the ones that failed, and the totals.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

LOGGED_FOLDERS = ("workflows", "creators")
"""Folders under ``tests/`` that get a results log."""

_TESTS_DIR = Path(__file__).parent
_results: dict[str, list[dict]] = {}
_started = datetime.now()


def _folder_of(nodeid: str) -> str | None:
    """Return the logged folder a test belongs to, if any."""
    parts = nodeid.replace("\\", "/").split("/")
    if len(parts) >= 2 and parts[0] == "tests" and parts[1] in LOGGED_FOLDERS:
        return parts[1]
    return None


def pytest_runtest_logreport(report) -> None:
    """Collect the outcome of each test (its call, or a setup failure/skip)."""
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        folder = _folder_of(report.nodeid)
        if folder is None:
            return
        _results.setdefault(folder, []).append({
            "nodeid": report.nodeid,
            "outcome": report.outcome.upper() if report.when == "call" else (
                "SKIPPED" if report.outcome == "skipped" else "ERROR"),
            "duration": report.duration,
            "detail": str(report.longrepr) if report.outcome != "passed" else "",
        })


def pytest_sessionfinish(session, exitstatus) -> None:
    """Write one results log per logged folder that ran tests."""
    finished = datetime.now()
    for folder, results in _results.items():
        try:
            reports_dir = _TESTS_DIR / folder / "reports"
            reports_dir.mkdir(exist_ok=True)
            counts: dict[str, int] = {}
            for item in results:
                counts[item["outcome"]] = counts.get(item["outcome"], 0) + 1
            lines = [
                f"Resultados de tests/{folder}",
                f"Inicio: {_started.strftime('%d/%m/%Y %H:%M:%S')}",
                f"Fin:    {finished.strftime('%d/%m/%Y %H:%M:%S')}",
                f"Duración: {(finished - _started).total_seconds():.1f} s",
                "",
            ]
            for item in results:
                lines.append(f"{item['outcome']:<8} {item['duration']:6.2f}s  {item['nodeid']}")
            failed = [item for item in results if item["detail"] and item["outcome"] in ("FAILED", "ERROR")]
            for item in failed:
                lines += ["", "=" * 78, f"{item['outcome']}: {item['nodeid']}", "=" * 78, item["detail"]]
            lines += ["", "Totales: " + ", ".join(f"{n} {k.lower()}" for k, n in sorted(counts.items()))]
            name = f"pytest_{finished.strftime('%Y%m%d_%H%M%S')}.log"
            (reports_dir / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass
