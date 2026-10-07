"""Workflows E2E runner: verifies deterministic workflow lifecycle.

Follows the same declarative YAML methodology as ``tests.e2e.runner`` (real
endpoints, no mocks) and adds workflow-specific pieces:

- ``verify`` block: asserts a workflow saved by the scenario appears in
  ``GET /api/config/workflows/selection`` (``available``) and optionally
  that it is the ``selected`` one.
- ``response_contains`` chat expectation: asserts substrings in the final
  assistant text (used for the friendly missing-refs message). The base
  runner only asserts structure; this extension is local to workflows.

Scenario YAML schema (extends the e2e schema)::

    scenario: unique-name
    description: What this scenario verifies.
    cleanup: true                      # reset selection to smart at the end
    verify:
      workflow: e2e-test-workflow      # must appear in selection.available
      selected: e2e-test-workflow      # optional: must be selection.selected
    steps:
      - action: request
        method: POST
        path: /api/config/workflows/save
        body: {name: ..., yaml: ...}
        expect:
          http_status: 200
          json_status: success
      - action: chat
        message: "..."
        expect:
          done: true
          response_contains: ["No se puede ejecutar"]

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
    evaluate_chat_expectations,
    run_chat_step,
    run_request_step,
)


def evaluate_workflow_expectations(expect: dict[str, Any], obs: dict[str, Any]) -> list[str]:
    """Evaluate chat expectations plus ``response_contains`` substrings.

    Args:
        expect: Expectation block from the YAML step.
        obs: Observation returned by :func:`run_chat_step`.

    Returns:
        List of human-readable failure descriptions (empty = pass).
    """
    failures = evaluate_chat_expectations(expect, obs)
    for wanted in expect.get("response_contains", []) or []:
        try:
            needle = str(wanted)
        except Exception:
            continue
        if needle and needle not in (obs.get("response_text") or ""):
            failures.append(f"response does not contain '{needle}'")
    return failures


def verify_workflow_saved(base_url: str, expected: dict[str, Any]) -> list[str]:
    """Call selection and verify the workflow is listed/selected.

    Args:
        base_url: Backend base URL.
        expected: Expected values (``workflow`` in available, optional
            ``selected`` match).

    Returns:
        List of failure descriptions (empty = pass).
    """
    try:
        response = requests.get(f"{base_url}/api/config/workflows/selection", timeout=60)
    except requests.RequestException as exc:
        return [f"GET /api/config/workflows/selection failed: {exc}"]

    if response.status_code != 200:
        return [f"GET /api/config/workflows/selection: HTTP {response.status_code} != 200"]

    try:
        payload = response.json()
    except ValueError:
        return ["GET /api/config/workflows/selection: response is not valid JSON"]

    if payload.get("status") != "success":
        return [f"GET /api/config/workflows/selection: contract status '{payload.get('status')}' != 'success'"]

    failures: list[str] = []
    data = payload.get("data") or {}
    name = expected.get("workflow")
    if name and name not in (data.get("available") or []):
        failures.append(f"workflow '{name}' not found in selection.available")
    if expected.get("selected") and data.get("selected") != expected["selected"]:
        failures.append(
            f"selection.selected '{data.get('selected')}' != '{expected['selected']}'"
        )
    return failures


def run_scenario(base_url: str, scenario: dict[str, Any]) -> dict[str, Any]:
    """Run one workflow scenario end to end.

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
            entry["failures"] = evaluate_workflow_expectations(step.get("expect", {}) or {}, obs)
        elif action == "request":
            _, failures = run_request_step(base_url, step, variables)
            entry["failures"] = failures
        else:
            entry["failures"] = [f"unknown action '{action}'"]

        step_results.append(entry)
        all_failures.extend(entry["failures"])

    # Workflow-specific verification: the saved workflow must be listed
    # (and optionally selected).
    verify = _interpolate(scenario.get("verify") or {}, variables)
    if verify.get("workflow"):
        verify_failures = verify_workflow_saved(base_url, verify)
        all_failures.extend(verify_failures)
        step_results.append(
            {
                "step": len(step_results) + 1,
                "action": "workflow_verify",
                "failures": verify_failures,
            }
        )

    # Cleanup: delete chat sessions and reset selection to smart. There is
    # no DELETE workflow endpoint, so saved test workflows stay on disk
    # under a fixed e2e name (re-runs overwrite them).
    if scenario.get("cleanup", True):
        for session_id in sessions.values():
            try:
                requests.delete(f"{base_url}/api/sessions/{session_id}", timeout=30)
            except requests.RequestException:
                pass  # cleanup is best-effort; never affects the verdict
        try:
            requests.post(
                f"{base_url}/api/config/workflows/select",
                json={"workflow": "smart"},
                timeout=30,
            )
        except requests.RequestException:
            pass

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
