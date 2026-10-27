"""Workflows E2E runner: deterministic workflow lifecycle against a live backend.

Follows the same declarative YAML methodology as ``tests.e2e.runner`` (real
endpoints, no mocks) and adds the pieces specific to workflow runs:

- ``run`` action: presses the play button (``POST /api/workflows/{name}/run``),
  waits for the background run to finish and asserts on the run row
  (``GET /api/workflows/runs``) and its notification (``GET /api/notifications``).
- ``verify`` block: asserts a workflow saved by the scenario is listed by
  ``GET /api/workflows``.

Scenario YAML schema (extends the e2e ``request`` action)::

    scenario: unique-name
    description: What this scenario verifies.
    cleanup: true                      # delete the notifications it created (a run opens no session)
    verify:
      workflow: e2e-test-workflow      # must appear in GET /api/workflows
    steps:
      - action: request
        method: POST
        path: /api/config/workflows/save
        body: {name: ..., yaml: ...}
        expect:
          http_status: 200
          json_status: success
      - action: run                    # the play button
        workflow: e2e-run-echo
        timeout: 120                   # seconds to wait for the run to finish
        cancel_after: 1.5              # optional: press cancel after N seconds
        expect:
          http_status: 200             # of the play request (default 200)
          message_contains: ["..."]    # substrings of the play response message
          run_status: success          # success | error | cancelled
          attempts: 3                  # attempt the run ended in
          result_contains: ["..."]     # substrings of the run result
          error_contains: ["..."]      # substrings of the run error text
          notification: true           # a notification exists for the run (false: none)

Run with ``python -m tests.workflows.runner``. A JSON report is written under
``tests/workflows/reports/``.
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
    run_request_step,
)

POLL_SECONDS = 0.5


def _find_run(base_url: str, name: str, run_id: str) -> dict[str, Any] | None:
    """Return the run row of ``run_id`` from the runs listing, if present.

    Args:
        base_url: Base URL of the backend.
        name: Workflow name.
        run_id: Id of the run.

    Returns:
        The run, or ``None`` when it is not listed.
    """
    try:
        response = requests.get(
            f"{base_url}/api/workflows/runs", params={"name": name, "limit": 50}, timeout=30
        )
        for run in (response.json().get("runs") or []):
            if run.get("id") == run_id:
                return run
    except (requests.RequestException, ValueError):
        pass
    return None


def run_play_step(
    base_url: str, step: dict[str, Any], tracked: dict[str, set[str]]
) -> list[str]:
    """Press play on a workflow, wait for it and assert on the run.

    Args:
        base_url: Backend base URL.
        step: ``run`` step definition (see the module docstring).
        tracked: Names of the workflows the scenario ran (mutated, used by the cleanup).

    Returns:
        List of human-readable failure descriptions (empty = pass).
    """
    name = str(step["workflow"])
    expect = step.get("expect", {}) or {}
    failures: list[str] = []

    try:
        response = requests.post(f"{base_url}/api/workflows/{name}/run", timeout=60)
    except requests.RequestException as exc:
        return [f"POST /api/workflows/{name}/run failed: {exc}"]
    expected_http = int(expect.get("http_status", 200))
    if response.status_code != expected_http:
        failures.append(f"play {name}: HTTP {response.status_code} != {expected_http}")
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    message = str(payload.get("message", ""))
    for needle in expect.get("message_contains", []) or []:
        if str(needle) not in message:
            failures.append(f"play {name}: message does not contain '{needle}' (got '{message}')")
    if response.status_code != 200:
        return failures

    data = payload.get("data") or {}
    run_id = str(data.get("run_id", ""))
    tracked["names"].add(name)

    cancel_after = step.get("cancel_after")
    started = time.time()
    deadline = started + float(step.get("timeout", 120))
    cancelled_sent = False
    run: dict[str, Any] | None = None
    while time.time() < deadline:
        if cancel_after is not None and not cancelled_sent and time.time() - started >= float(cancel_after):
            try:
                requests.post(f"{base_url}/api/workflows/runs/{run_id}/cancel", timeout=30)
            except requests.RequestException:
                pass
            cancelled_sent = True
        run = _find_run(base_url, name, run_id)
        if run and run.get("status") != "running":
            break
        time.sleep(POLL_SECONDS)
    if run is None or run.get("status") == "running":
        try:
            requests.post(f"{base_url}/api/workflows/runs/{run_id}/cancel", timeout=30)
        except requests.RequestException:
            pass
        return failures + [f"run {run_id} of {name} did not finish in time"]

    if expect.get("run_status") and run.get("status") != expect["run_status"]:
        failures.append(f"run status '{run.get('status')}' != '{expect['run_status']}'")
    if expect.get("attempts") is not None and run.get("attempt") != int(expect["attempts"]):
        failures.append(f"run attempt {run.get('attempt')} != {expect['attempts']}")
    for needle in expect.get("result_contains", []) or []:
        if str(needle) not in str(run.get("result") or ""):
            failures.append(f"run result does not contain '{needle}'")
    for needle in expect.get("error_contains", []) or []:
        if str(needle) not in str(run.get("error_text") or ""):
            failures.append(f"run error text does not contain '{needle}'")

    if expect.get("notification") is not None:
        try:
            notifications = requests.get(f"{base_url}/api/notifications", timeout=30).json().get(
                "notifications"
            ) or []
        except (requests.RequestException, ValueError):
            notifications = []
        found = [n for n in notifications if n.get("run_id") == run_id]
        if bool(found) != bool(expect["notification"]):
            failures.append(
                f"notification for run {run_id}: expected {bool(expect['notification'])}, found {bool(found)}"
            )
        elif found and expect.get("run_status") in ("success", "error"):
            if found[0].get("status") != expect["run_status"]:
                failures.append(
                    f"notification status '{found[0].get('status')}' != '{expect['run_status']}'"
                )
    return failures


def verify_workflow_listed(base_url: str, expected: dict[str, Any]) -> list[str]:
    """Verify the workflow appears in ``GET /api/workflows``.

    Args:
        base_url: Backend base URL.
        expected: Expected values (``workflow`` name).

    Returns:
        List of failure descriptions (empty = pass).
    """
    try:
        response = requests.get(f"{base_url}/api/workflows", timeout=60)
    except requests.RequestException as exc:
        return [f"GET /api/workflows failed: {exc}"]
    if response.status_code != 200:
        return [f"GET /api/workflows: HTTP {response.status_code} != 200"]
    try:
        payload = response.json()
    except ValueError:
        return ["GET /api/workflows: response is not valid JSON"]
    names = [w.get("name") for w in (payload.get("workflows") or [])]
    name = expected.get("workflow")
    if name and name not in names:
        return [f"workflow '{name}' not found in GET /api/workflows"]
    return []


def cleanup_scenario(base_url: str, tracked: dict[str, set[str]]) -> None:
    """Best-effort removal of what a scenario created (never affects the verdict).

    Args:
        base_url: Base URL of the backend.
        tracked: Workflow names the scenario ran, under ``names``.
    """
    try:
        notifications = requests.get(f"{base_url}/api/notifications", timeout=30).json().get(
            "notifications"
        ) or []
        for notification in notifications:
            if notification.get("workflow_name") in tracked["names"]:
                requests.delete(f"{base_url}/api/notifications/{notification['id']}", timeout=30)
    except (requests.RequestException, ValueError):
        pass


def run_scenario(base_url: str, scenario: dict[str, Any]) -> dict[str, Any]:
    """Run one workflow scenario end to end.

    Args:
        base_url: Backend base URL.
        scenario: Parsed scenario dict.

    Returns:
        Result dict: ``{"scenario", "file", "passed", "failures", "steps"}``.
    """
    variables: dict[str, str] = {}
    tracked: dict[str, set[str]] = {"names": set()}
    step_results: list[dict[str, Any]] = []
    all_failures: list[str] = []

    for index, step in enumerate(scenario.get("steps", []) or [], start=1):
        action = step.get("action")
        entry: dict[str, Any] = {"step": index, "action": action, "failures": []}

        if action == "run":
            entry["failures"] = run_play_step(base_url, step, tracked)
        elif action == "request":
            _, failures = run_request_step(base_url, step, variables)
            entry["failures"] = failures
        else:
            entry["failures"] = [f"unknown action '{action}'"]

        step_results.append(entry)
        all_failures.extend(entry["failures"])

    verify = _interpolate(scenario.get("verify") or {}, variables)
    if verify.get("workflow"):
        verify_failures = verify_workflow_listed(base_url, verify)
        all_failures.extend(verify_failures)
        step_results.append(
            {
                "step": len(step_results) + 1,
                "action": "workflow_verify",
                "failures": verify_failures,
            }
        )

    # There is no DELETE workflow endpoint, so saved test workflows stay on
    # disk under a fixed e2e name (re-runs overwrite them).
    if scenario.get("cleanup", True):
        cleanup_scenario(base_url, tracked)

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
    parser = argparse.ArgumentParser(description="synapseForge workflows E2E runner")
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
