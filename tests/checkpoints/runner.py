"""Checkpoints runner: real chat flow + assertions on the real agent.db.

Reuses the e2e writing bot (:func:`tests.e2e.runner.run_chat_step`) so the
SSE consumption is exactly the same code path the frontend exercises.
After driving the live ``/api/chat`` endpoint, scenarios assert on the
``step_frontier`` table of the backend's own SQLite file — no mocks, no
fixtures, real tracked state.

Scenario YAML schema (superset of the e2e one)::

    scenario: unique-name
    description: What this scenario verifies.
    cleanup: true
    steps:
      - action: chat              # same as e2e (message, session, abort_after_events, expect)
      - action: db_assert         # inspect the real agent.db
        session: cut              # session alias used by the chat steps
        expect:
          total_rows: 0           # exact frontier row count for the session
          open_min: 1             # at least N rows still open
          turn_empty: 2           # no rows left for that turn number

Run with ``python -m tests.checkpoints.runner``. A JSON report is written
under ``tests/checkpoints/reports/``.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import yaml

from tests.e2e.runner import evaluate_chat_expectations, run_chat_step

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO_ROOT / "backend" / "agent" / "agent_db" / "agent.db"

_FRONTIER_COLUMNS = (
    "session_id, turn_number, step, substep, tool_call_id, "
    "tool_name, tool_args, state, child_id"
)


class CheckpointError(Exception):
    """Raised when the backend DB is unreachable or a scenario is malformed."""


def read_frontier(db_path: Path, session_id: str) -> list[dict[str, Any]]:
    """Read every frontier row of a session from the real agent.db.

    Args:
        db_path: Path to the backend SQLite file.
        session_id: Session to inspect.

    Returns:
        List of row dicts ordered by turn, step, substep.

    Raises:
        CheckpointError: If the DB file or table is missing.
    """
    if not db_path.is_file():
        raise CheckpointError(
            f"agent.db not found at {db_path} — run the backend on this machine first."
        )
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        raise CheckpointError(f"cannot open agent.db: {exc}") from exc
    try:
        try:
            cur = conn.execute(
                f"SELECT {_FRONTIER_COLUMNS} FROM step_frontier "
                "WHERE session_id = ? ORDER BY turn_number, step, substep",
                (session_id,),
            )
        except sqlite3.Error as exc:
            raise CheckpointError(f"step_frontier unreadable: {exc}") from exc
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def evaluate_db_expectations(
    expect: dict[str, Any], rows: list[dict[str, Any]]
) -> list[str]:
    """Evaluate a db_assert step against the real frontier rows.

    Args:
        expect: Expectation block (``total_rows``, ``open_min``,
            ``turn_empty``).
        rows: Rows returned by :func:`read_frontier`.

    Returns:
        List of human-readable failure descriptions (empty = pass).
    """
    failures: list[str] = []
    if expect.get("total_rows") is not None and len(rows) != int(expect["total_rows"]):
        failures.append(
            f"frontier has {len(rows)} rows, expected {expect['total_rows']}: "
            + ", ".join(
                f"t{r['turn_number']}s{r['step']}.{r['substep']}:{r['tool_name']}:{r['state']}"
                for r in rows
            )
        )
    if expect.get("open_min") is not None:
        opened = [r for r in rows if r["state"] == "open"]
        if len(opened) < int(expect["open_min"]):
            failures.append(
                f"frontier has {len(opened)} open rows, expected at least "
                f"{expect['open_min']} (total {len(rows)})"
            )
    if expect.get("turn_empty") is not None:
        turn = int(expect["turn_empty"])
        leftovers = [r for r in rows if r["turn_number"] == turn]
        if leftovers:
            failures.append(
                f"turn {turn} still has {len(leftovers)} frontier rows: "
                + ", ".join(
                    f"s{r['step']}.{r['substep']}:{r['tool_name']}:{r['state']}"
                    for r in leftovers
                )
            )
    return failures


def cleanup_frontier(db_path: Path, session_id: str) -> None:
    """Delete test session rows from the real agent.db (best-effort).

    Args:
        db_path: Path to the backend SQLite file.
        session_id: Session whose frontier rows are removed.
    """
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        try:
            conn.execute("DELETE FROM step_frontier WHERE session_id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        pass  # cleanup never affects the verdict


def run_scenario(
    base_url: str, db_path: Path, scenario: dict[str, Any]
) -> dict[str, Any]:
    """Run one checkpoint scenario end to end.

    Args:
        base_url: Backend base URL.
        db_path: Backend SQLite file.
        scenario: Parsed scenario dict.

    Returns:
        Result dict: ``{"scenario", "file", "passed", "failures", "steps"}``.
    """
    sessions: dict[str, str] = {}
    step_results: list[dict[str, Any]] = []
    all_failures: list[str] = []

    for index, step in enumerate(scenario.get("steps", []) or [], start=1):
        action = step.get("action")
        entry: dict[str, Any] = {"step": index, "action": action, "failures": []}

        if action == "chat":
            obs = run_chat_step(base_url, step, sessions)
            entry["failures"] = evaluate_chat_expectations(
                step.get("expect", {}) or {}, obs
            )
            entry["tools_called"] = obs["tools_called"]
            entry["aborted"] = obs["aborted"]
        elif action == "db_assert":
            alias = str(step.get("session", "main"))
            session_id = sessions.get(alias, "")
            if not session_id:
                entry["failures"] = [f"unknown session alias '{alias}'"]
            else:
                try:
                    rows = read_frontier(db_path, session_id)
                    entry["frontier_rows"] = len(rows)
                    entry["failures"] = evaluate_db_expectations(
                        step.get("expect", {}) or {}, rows
                    )
                except CheckpointError as exc:
                    entry["failures"] = [str(exc)]
        else:
            entry["failures"] = [f"unknown action '{action}'"]

        step_results.append(entry)
        all_failures.extend(entry["failures"])

    if scenario.get("cleanup", True):
        for session_id in sessions.values():
            try:
                requests.delete(f"{base_url}/api/sessions/{session_id}", timeout=30)
            except requests.RequestException:
                pass  # cleanup is best-effort; never affects the verdict
            cleanup_frontier(db_path, session_id)

    return {
        "scenario": scenario["scenario"],
        "file": scenario.get("_file", ""),
        "passed": not all_failures,
        "failures": all_failures,
        "steps": step_results,
    }


def load_scenarios(scenarios_dir: Path) -> list[dict[str, Any]]:
    """Load every YAML scenario file from a directory.

    Args:
        scenarios_dir: Directory containing ``*.yaml`` scenario files.

    Returns:
        List of parsed scenario dicts.
    """
    scenarios: list[dict[str, Any]] = []
    for path in sorted(scenarios_dir.glob("*.yaml")):
        documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        for doc in documents:
            if doc is None:
                continue
            if not isinstance(doc, dict) or not doc.get("scenario"):
                raise CheckpointError(f"{path.name}: falta el campo 'scenario'")
            doc["_file"] = path.name
            scenarios.append(doc)
    return scenarios


def main() -> int:
    """Parse arguments, run every scenario and print the report.

    Returns:
        Process exit code: 0 when all scenarios pass, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description="synapseForge checkpoints runner")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Backend base URL")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="agent.db path")
    parser.add_argument("--only", default=None, help="Run a single scenario by name")
    args = parser.parse_args()

    scenarios_dir = Path(__file__).parent / "scenarios"
    try:
        scenarios = load_scenarios(scenarios_dir)
    except (CheckpointError, yaml.YAMLError) as exc:
        print(f"Cannot load scenarios: {exc}")
        return 1
    if args.only:
        scenarios = [s for s in scenarios if args.only in s["scenario"]]
        if not scenarios:
            print(f"No scenario named '{args.only}'.")
            return 1

    db_path = Path(args.db_path)
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    results = []
    for scenario in scenarios:
        print(f"\n=== {scenario['scenario']} ({scenario.get('_file', '')}) ===")
        started = time.time()
        result = run_scenario(args.base_url, db_path, scenario)
        result["duration_s"] = round(time.time() - started, 1)
        results.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] {result['scenario']} ({result['duration_s']}s)")
        for step in result["steps"]:
            detail = ""
            if "tools_called" in step:
                detail = f" tools={step['tools_called']} aborted={step['aborted']}"
            if "frontier_rows" in step:
                detail = f" frontier_rows={step['frontier_rows']}"
            print(f"  step {step['step']} ({step['action']}):{detail}")
        for failure in result["failures"]:
            print(f"  - {failure}")

    passed = sum(1 for r in results if r["passed"])
    summary = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "base_url": args.base_url,
        "db_path": str(db_path),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }
    report_path = reports_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\nTotal: {passed}/{len(results)} escenario(s) en verde.")
    print(f"Reporte: {report_path}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
