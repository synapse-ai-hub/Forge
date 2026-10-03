"""E2E runner: executes declarative YAML scenarios against a live backend.

The "writing bot" pattern from ProspectingAgent, adapted to synapseForge:
each scenario drives the same entry points the frontend uses (the SSE chat
endpoint and the REST API), collects the raw events and asserts on
structure — never on exact model text.

Scenario YAML schema::

    scenario: unique-name
    description: What this scenario verifies.
    cleanup: true                      # delete created sessions at the end
    steps:
      - action: chat                   # the bot writes a message
        message: "Hola"
        session: s1                    # optional session alias (default: main)
        abort_after_events: 3          # optional: close the stream mid-response
        expect:
          done: true                   # [DONE] marker received
          nonempty: true               # final assistant text is not empty
          no_tool_error: true          # no tool_result with status error
          events_include: [chunk]      # event types that must appear
          tools_called_any_of: []      # tool names that must appear (any of)
          parallel_block: true         # 2+ tool_calls before the first tool_result
      - action: request                # direct API call
        method: GET                    # GET (default) | POST | PUT | DELETE
        path: /api/scheduler/tasks
        body: {}                       # optional JSON body
        expect:
          http_status: 200
          json_status: success         # contract ``status`` field
          json_path_exists: data.collections

Run with ``python -m tests.e2e.runner``. A JSON report is written under
``tests/e2e/reports/``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import yaml

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
SESSION_PREFIX = "e2e-"
SSE_DONE = "[DONE]"
DEFAULT_CHAT_TIMEOUT = 180.0


class ScenarioError(Exception):
    """Raised when a scenario file is malformed."""


# ---------------------------------------------------------------------------
# SSE consumption (the writing bot)
# ---------------------------------------------------------------------------


def run_chat_step(base_url: str, step: dict[str, Any], sessions: dict[str, str]) -> dict[str, Any]:
    """Send a chat message and consume the SSE stream like the frontend does.

    Args:
        base_url: Backend base URL.
        step: Chat step definition (``message``, optional ``session``,
            optional ``abort_after_events``).
        sessions: Session alias → session_id map (mutated).

    Returns:
        Observation dict: ``events`` (list of parsed events), ``done``,
        ``aborted``, ``response_text``, ``tool_errors``, ``tools_called``,
        ``http_status``.
    """
    alias = str(step.get("session", "main"))
    session_id = sessions.setdefault(alias, SESSION_PREFIX + uuid.uuid4().hex)

    observation: dict[str, Any] = {
        "events": [],
        "done": False,
        "aborted": False,
        "response_text": "",
        "tool_errors": [],
        "tools_called": [],
        "http_status": None,
    }

    try:
        response = requests.post(
            f"{base_url}/api/chat",
            data={"message": str(step.get("message", "")), "session_id": session_id},
            stream=True,
            timeout=DEFAULT_CHAT_TIMEOUT,
        )
        observation["http_status"] = response.status_code
        if response.status_code != 200:
            return observation

        abort_after = step.get("abort_after_events")
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == SSE_DONE:
                observation["done"] = True
                break
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            observation["events"].append(event)
            event_type = event.get("type")
            content = event.get("content")
            if event_type == "chunk" and isinstance(content, str):
                observation["response_text"] += content
            elif event_type == "tool_call":
                name = (content or {}).get("name", "")
                if name:
                    observation["tools_called"].append(name)
            elif event_type == "tool_result":
                result = (content or {}).get("result") or {}
                if isinstance(result, dict) and result.get("status") == "error":
                    observation["tool_errors"].append(
                        {
                            "name": (content or {}).get("name", ""),
                            "message": result.get("message", ""),
                        }
                    )
            if abort_after is not None and len(observation["events"]) >= int(abort_after):
                observation["aborted"] = True
                break
    finally:
        # Closing the response aborts the stream server-side.
        try:
            response.close()
        except Exception:
            pass
    return observation


def evaluate_chat_expectations(expect: dict[str, Any], obs: dict[str, Any]) -> list[str]:
    """Evaluate a chat step's expectations against the observation.

    Args:
        expect: Expectation block from the YAML step.
        obs: Observation returned by :func:`run_chat_step`.

    Returns:
        List of human-readable failure descriptions (empty = pass).
    """
    failures: list[str] = []
    if expect.get("done") and not obs["done"]:
        failures.append("stream ended without [DONE]")
    if expect.get("nonempty") and not obs["response_text"].strip():
        failures.append("assistant response is empty")
    if expect.get("no_tool_error") and obs["tool_errors"]:
        names = ", ".join(e["name"] or "?" for e in obs["tool_errors"])
        failures.append(f"tool errors reported for: {names}")
    for event_type in expect.get("events_include", []) or []:
        if not any(e.get("type") == event_type for e in obs["events"]):
            failures.append(f"expected event type '{event_type}' not observed")
    wanted_tools = expect.get("tools_called_any_of", []) or []
    if wanted_tools and not any(t in obs["tools_called"] for t in wanted_tools):
        failures.append(
            f"none of the expected tools {wanted_tools} were called "
            f"(called: {obs['tools_called']})"
        )
    if expect.get("parallel_block"):
        # All tool_call events must arrive before the first tool_result:
        # the loop emits every tool_call of a block upfront (in order) and
        # commits results afterwards. A tool_result interleaved between
        # tool_calls means the model used sequential blocks, not one
        # parallel block.
        tc_idx = [i for i, e in enumerate(obs["events"]) if e.get("type") == "tool_call"]
        tr_idx = [i for i, e in enumerate(obs["events"]) if e.get("type") == "tool_result"]
        if len(tc_idx) < 2:
            failures.append(
                f"parallel_block: expected 2+ tool_call events in one block "
                f"(got {len(tc_idx)})"
            )
        elif tr_idx and max(tc_idx) > min(tr_idx):
            failures.append(
                "parallel_block: tool_result interleaved between tool_call "
                "events (calls ran in sequential blocks, not one parallel block)"
            )
    return failures


# ---------------------------------------------------------------------------
# Direct API requests
# ---------------------------------------------------------------------------


def _resolve_json_path(payload: Any, dotted_path: str) -> bool:
    """Return whether a dotted path (e.g. ``data.collections``) exists."""
    return _extract_json_path(payload, dotted_path) is not None


def _extract_json_path(payload: Any, dotted_path: str) -> Any:
    """Resolve a dotted path against a JSON payload (None when missing)."""
    current = payload
    for part in dotted_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _interpolate(value: Any, variables: dict[str, str]) -> Any:
    """Replace ``{alias}`` placeholders in strings (recursively in dicts/lists).

    Args:
        value: Value to interpolate (str, dict, list or scalar).
        variables: Saved values keyed by alias.

    Returns:
        The interpolated value.
    """
    if isinstance(value, str):
        for alias, saved in variables.items():
            value = value.replace("{" + alias + "}", str(saved))
        return value
    if isinstance(value, dict):
        return {k: _interpolate(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v, variables) for v in value]
    return value


def run_request_step(
    base_url: str,
    step: dict[str, Any],
    variables: dict[str, str],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Execute a direct API call and evaluate its expectations.

    Args:
        base_url: Backend base URL.
        step: Request step definition (``method``, ``path``, ``body``,
            ``expect``, ``save``).
        variables: Shared alias → value map (mutated by ``save``).

    Returns:
        Tuple ``(json_payload_or_none, failures)``.
    """
    method = str(step.get("method", "GET")).upper()
    path = _interpolate(str(step.get("path", "")).strip(), variables)
    expect = step.get("expect", {}) or {}
    failures: list[str] = []

    try:
        response = requests.request(
            method,
            f"{base_url}{path}",
            json=_interpolate(step.get("body"), variables),
            timeout=60,
        )
    except requests.RequestException as exc:
        return None, [f"request {method} {path} failed: {exc}"]

    if expect.get("http_status") is not None and response.status_code != int(expect["http_status"]):
        failures.append(f"{method} {path}: HTTP {response.status_code} != {expect['http_status']}")

    payload: Any = None
    try:
        payload = response.json()
    except ValueError:
        if expect.get("json_status") or expect.get("json_path_exists"):
            failures.append(f"{method} {path}: response is not valid JSON")

    if payload is not None:
        if expect.get("json_status") and payload.get("status") != expect["json_status"]:
            failures.append(
                f"{method} {path}: contract status '{payload.get('status')}' != '{expect['json_status']}'"
            )
        for dotted in expect.get("json_path_exists", []) or []:
            if not _resolve_json_path(payload, str(dotted)):
                failures.append(f"{method} {path}: JSON path '{dotted}' not found")

    # Save values for later steps (e.g. an id created here used below).
    for alias, dotted in (step.get("save") or {}).items():
        saved = _extract_json_path(payload, str(dotted)) if payload is not None else None
        if saved is None:
            failures.append(f"{method} {path}: nothing to save at '{dotted}' for '{alias}'")
        else:
            variables[alias] = saved

    return payload, failures


# ---------------------------------------------------------------------------
# Scenario execution
# ---------------------------------------------------------------------------


def load_scenarios(scenarios_dir: Path) -> list[dict[str, Any]]:
    """Load every YAML scenario file from a directory.

    Args:
        scenarios_dir: Directory containing ``*.yaml`` scenario files.

    Returns:
        List of parsed scenario dicts.

    Raises:
        ScenarioError: If a file cannot be parsed or lacks a name.
    """
    scenarios: list[dict[str, Any]] = []
    for path in sorted(scenarios_dir.glob("*.yaml")):
        try:
            documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except yaml.YAMLError as exc:
            raise ScenarioError(f"{path.name}: YAML inválido: {exc}") from exc
        for doc in documents:
            if doc is None:
                continue
            if not isinstance(doc, dict) or not doc.get("scenario"):
                raise ScenarioError(
                    f"{path.name}: falta el campo 'scenario'"
                )
            doc["_file"] = path.name
            scenarios.append(doc)
    return scenarios


def run_scenario(base_url: str, scenario: dict[str, Any]) -> dict[str, Any]:
    """Run one scenario end to end.

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

    # Cleanup: delete sessions created by this scenario.
    if scenario.get("cleanup", True):
        for session_id in sessions.values():
            try:
                requests.delete(f"{base_url}/api/sessions/{session_id}", timeout=30)
            except requests.RequestException:
                pass  # cleanup is best-effort; never affects the verdict

    return {
        "scenario": scenario["scenario"],
        "file": scenario.get("_file", ""),
        "passed": not all_failures,
        "failures": all_failures,
        "steps": step_results,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Parse arguments, run every scenario and print the report.

    Returns:
        Process exit code: 0 when all scenarios pass, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description="synapseForge E2E runner")
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
