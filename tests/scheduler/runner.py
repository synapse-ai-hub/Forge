"""Scheduler E2E runner: verifies the endpoints of the scheduled tasks (agenda).

Follows the same declarative YAML methodology as ``tests.e2e.runner`` (real
endpoints, no mocks) and adds a scheduler-specific verification: after the
scenario steps run, a ``verify`` block can call ``/api/scheduler/tasks`` and assert that a
task persisted with the expected fields.

Scenario YAML schema::

    scenario: unique-name
    description: What this scenario verifies.
    cleanup: true
    verify:
      task_id: "{task_id}"        # interpolated from a saved step value
      name: test-agenda
      time: "10:30"
      days: [0, 2, 4]
    steps:
      - action: request
        method: POST
        path: /api/scheduler/tasks
        body: {...}
        save:
          task_id: data.task.id
        expect:
          http_status: 200
          json_status: success

Run with ``python -m tests.scheduler.runner``. A JSON report is written under
``tests/scheduler/reports/``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import yaml

from tests.e2e.runner import (
    DEFAULT_BASE_URL,
    _interpolate,
    evaluate_chat_expectations,
    run_chat_step,
    run_request_step,
)


def verify_task_persisted(base_url: str, task_id: str, expected: dict[str, Any]) -> list[str]:
    """Call ``/api/scheduler/tasks`` and verify the task persisted with fields.

    Args:
        base_url: Backend base URL.
        task_id: The task id to look up.
        expected: Expected field values (name, time, days, etc.).

    Returns:
        List of failure descriptions (empty = pass).
    """
    try:
        response = requests.get(f"{base_url}/api/scheduler/tasks", timeout=60)
    except requests.RequestException as exc:
        return [f"GET /api/scheduler/tasks failed: {exc}"]

    if response.status_code != 200:
        return [f"GET /api/scheduler/tasks: HTTP {response.status_code} != 200"]

    try:
        payload = response.json()
    except ValueError:
        return ["GET /api/scheduler/tasks: response is not valid JSON"]

    if payload.get("status") != "success":
        return [f"GET /api/scheduler/tasks: contract status '{payload.get('status')}' != 'success'"]

    tasks = payload.get("tasks") or []
    task = next((t for t in tasks if t.get("id") == task_id), None)
    if task is None:
        return [f"task '{task_id}' not found in /api/scheduler/tasks"]

    failures: list[str] = []
    for field, expected_value in expected.items():
        actual = task.get(field)
        if actual != expected_value:
            failures.append(
                f"task '{task_id}' field '{field}' = {actual!r} != {expected_value!r}"
            )
    return failures


def run_scenario(base_url: str, scenario: dict[str, Any]) -> dict[str, Any]:
    """Run one scheduler scenario end to end.

    Args:
        base_url: Backend base URL.
        scenario: Parsed scenario dict.

    Returns:
        Result dict: ``{"scenario", "file", "passed", "failures", "steps"}``.
    """
    sessions: dict[str, str] = {}
    variables: dict[str, str] = {}
    step_results: list[dict[str, Any]] = []
    all_failures: list[str] = []

    for index, step in enumerate(scenario.get("steps", []) or [], start=1):
        action = step.get("action")
        entry: dict[str, Any] = {"step": index, "action": action, "failures": []}

        if action == "chat":
            obs = run_chat_step(base_url, step, sessions)
            entry["failures"] = evaluate_chat_expectations(step.get("expect", {}) or {}, obs)
        elif action == "request":
            _, failures = run_request_step(base_url, step, variables)
            entry["failures"] = failures
        else:
            entry["failures"] = [f"unknown action '{action}'"]

        step_results.append(entry)
        all_failures.extend(entry["failures"])

    # Scheduler-specific verification: the task created by the scenario must
    # have persisted with the expected fields.
    verify = _interpolate(scenario.get("verify") or {}, variables)
    if verify.get("task_id"):
        task_id = str(verify["task_id"])
        expected = {k: v for k, v in verify.items() if k != "task_id"}
        verify_failures = verify_task_persisted(base_url, task_id, expected)
        all_failures.extend(verify_failures)
        step_results.append(
            {
                "step": len(step_results) + 1,
                "action": "scheduler_verify",
                "failures": verify_failures,
            }
        )

    # Cleanup: delete the task created by this scenario.
    if scenario.get("cleanup", True) and verify.get("task_id"):
        try:
            requests.delete(f"{base_url}/api/scheduler/tasks/{task_id}", timeout=30)
        except requests.RequestException:
            pass  # cleanup is best-effort; never affects the verdict

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

    Raises:
        ValueError: If a file cannot be parsed or lacks a name.
    """
    scenarios: list[dict[str, Any]] = []
    for path in sorted(scenarios_dir.glob("*.yaml")):
        try:
            documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except yaml.YAMLError as exc:
            raise ValueError(f"{path.name}: YAML inválido: {exc}") from exc
        for doc in documents:
            if doc is None:
                continue
            if not isinstance(doc, dict) or not doc.get("scenario"):
                raise ValueError(f"{path.name}: falta el campo 'scenario'")
            doc["_file"] = path.name
            scenarios.append(doc)
    return scenarios


def main() -> int:
    """Parse arguments, run every scenario and print the report.

    Returns:
        Process exit code: 0 when all scenarios pass, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description="synapseForge scheduler E2E runner")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Backend base URL")
    parser.add_argument("--only", default=None, help="Run a single scenario by name")
    args = parser.parse_args()

    scenarios_dir = Path(__file__).parent / "scenarios"
    scenarios = load_scenarios(scenarios_dir)
    if args.only:
        scenarios = [s for s in scenarios if args.only in s["scenario"]]
        if not scenarios:
            print(f"No scenario named '{args.only}'.")
            return 1

    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    results = []
    for scenario in scenarios:
        print(f"\n=== {scenario['scenario']} ({scenario.get('_file', '')}) ===")
        started = time.time()
        result = run_scenario(args.base_url, scenario)
        result["duration_s"] = round(time.time() - started, 1)
        results.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] {result['scenario']} ({result['duration_s']}s)")
        for failure in result["failures"]:
            print(f"  - {failure}")

    passed = sum(1 for r in results if r["passed"])
    summary = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "base_url": args.base_url,
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }
    report_path = reports_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nTotal: {passed}/{len(results)} escenario(s) en verde.")
    print(f"Reporte: {report_path}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())