"""Missing decision model (404): detection, clean user message and notification.

Covers the new 404 flow without any LLM call: the shared detector
(``_is_model_not_found``), the ``DecisionMixin.decision`` mapping of a dead
slug to a disabled model, the judge helpers (``_decision_model_not_found``,
``_notify_missing_decision_model``) and ``judge_run`` notifying once and
approving silently when the configured decision model does not exist.
``log_error`` and ``notify`` are stubbed, so no database is touched.
"""

from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import Coroutine
from typing import Any

import pytest

from backend.agent.llm import decision as decision_mod
from backend.agent.llm.decision import (
    DECISION_MODEL_NOT_FOUND_PREFIX,
    DecisionMixin,
    _is_model_not_found,
)
from backend.agent.utils import notifications_helpers, provider_keys
from backend.agent.utils import workflow_judge as judge


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine to completion.

    Args:
        coro: Coroutine to run.

    Returns:
        Its result.
    """
    return asyncio.run(coro)


def _not_found_response() -> dict[str, Any]:
    """Build the contract answer of a decision call with a dead slug.

    Returns:
        A success response with ``available`` False and the marker prefix.
    """
    return {
        "status": "success",
        "message": f"{DECISION_MODEL_NOT_FOUND_PREFIX} 404: model 'dead-slug' not found",
        "data": {"available": False, "answers": None, "model": None, "provider": None},
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_time": 0},
    }


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Error 404: model 'x' not found", True),
        ("404 Not Found", True),
        ("model not found", True),
        ("MODEL NOT FOUND", True),
        ("request failed with status 404", True),
        ("timeout after 30s", False),
        ("rate limit 429 exceeded", False),
        ("connection reset by peer", False),
        ("error 14040", False),
        ("", False),
    ],
)
def test_is_model_not_found(message: str, expected: bool) -> None:
    """Detect 404 / not-found answers and nothing else.

    Args:
        message: Exception text of the failed call.
        expected: Whether it means the model slug does not exist.
    """
    assert _is_model_not_found(message) is expected


def test_is_model_not_found_empty() -> None:
    """Treat a missing message as a generic failure."""
    assert _is_model_not_found(None) is False  # type: ignore[arg-type]


class _DecisionAgent(DecisionMixin):
    """Minimal host for ``DecisionMixin.decision`` without the real agent."""

    def __init__(self) -> None:
        """Configure an enabled decision model with a dead slug."""
        self.decision_enabled = True
        self.decision_provider = "typesafe"
        self.decision_model = "dead-slug"

    def _record_spend(self, *args: Any, **kwargs: Any) -> None:
        """Ignore the spend record.

        Args:
            *args: Positional arguments (ignored).
            **kwargs: Keyword arguments (ignored).
        """


def _install_fake_sdk(monkeypatch: pytest.MonkeyPatch, failure: Exception) -> None:
    """Install a fake ``typesafe_sdk`` whose call raises ``failure``.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        failure: Exception the fake ``system_one`` raises.
    """
    module = types.ModuleType("typesafe_sdk")

    class _Client:
        """Fake async client that always fails the same way."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """Accept any constructor arguments.

            Args:
                *args: Positional arguments (ignored).
                **kwargs: Keyword arguments (ignored).
            """

        async def system_one(self, *args: Any, **kwargs: Any) -> Any:
            """Raise the configured failure.

            Args:
                *args: Positional arguments (ignored).
                **kwargs: Keyword arguments (ignored).

            Raises:
                Exception: The configured failure.
            """
            raise failure

        async def close(self) -> None:
            """Do nothing."""

    module.AsyncTypeSafeClient = _Client
    module.Choice = lambda **kwargs: object()  # noqa: E731
    module.Noul = lambda **kwargs: object()  # noqa: E731
    module.Score = lambda **kwargs: object()  # noqa: E731
    monkeypatch.setitem(sys.modules, "typesafe_sdk", module)
    monkeypatch.setattr(
        provider_keys, "get_decision_provider", lambda provider_id: {"sdk_base_url": "http://x"}
    )
    monkeypatch.setattr(provider_keys, "get_decision_key", lambda provider_id: "k")


def test_decision_maps_missing_model_to_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Map a 404 of the decision call to a disabled model with a marker message."""
    _install_fake_sdk(monkeypatch, Exception("404: model 'dead-slug' not found"))
    logged: list[tuple[str, str]] = []
    monkeypatch.setattr(
        decision_mod, "log_error", lambda message, source="": logged.append((message, source))
    )

    response = _run(_DecisionAgent().decision({"w": "w"}, {"done": {"type": "noul"}}))

    assert response["status"] == "success"
    assert str(response["message"]).startswith(DECISION_MODEL_NOT_FOUND_PREFIX)
    assert (response["data"] or {}).get("available") is False
    assert (response["data"] or {}).get("model") is None
    assert logged and logged[0][0] == "404: model 'dead-slug' not found"


def test_decision_keeps_error_path_for_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the error path when the failure is not a missing model."""
    _install_fake_sdk(monkeypatch, TimeoutError("timeout after 30s"))
    monkeypatch.setattr(decision_mod, "log_error", lambda *args, **kwargs: None)

    response = _run(_DecisionAgent().decision({"w": "w"}, {"done": {"type": "noul"}}))

    assert response["status"] == "error"
    assert response["message"] == "timeout after 30s"


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (_not_found_response(), True),
        ({"status": "error", "message": "boom", "data": {}}, False),
        ({"status": "success", "message": "Decision ok.", "data": {"available": True}}, False),
        (
            {
                "status": "success",
                "message": "Decision model not enabled.",
                "data": {"available": False},
            },
            False,
        ),
        ({"status": "success", "message": "", "data": {"available": False}}, False),
        ({"status": "success", "data": {"available": False}}, False),
        (None, False),
        ("nope", False),
    ],
)
def test_decision_model_not_found(response: Any, expected: bool) -> None:
    """Only match an unavailable model whose message carries the marker.

    Args:
        response: Contract answer of ``Agent.decision``.
        expected: Whether it means the configured slug was not found.
    """
    assert judge._decision_model_not_found(response) is expected


def _stub_notify(monkeypatch: pytest.MonkeyPatch) -> tuple[list[dict[str, Any]], list[Exception]]:
    """Replace ``notify`` with a recorder.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        The recorded calls and the failures ``notify`` should raise per call.
    """
    calls: list[dict[str, Any]] = []
    failures: list[Exception] = []

    async def _fake(**kwargs: Any) -> None:
        """Record the call or raise the next configured failure.

        Args:
            **kwargs: Notification arguments.

        Raises:
            Exception: The next configured failure, when any.
        """
        if failures:
            raise failures.pop(0)
        calls.append(kwargs)

    monkeypatch.setattr(notifications_helpers, "notify", _fake)
    return calls, failures


def test_notify_missing_model_on_play(monkeypatch: pytest.MonkeyPatch) -> None:
    """Notify as a workflow error without a run id on manual plays."""
    calls, _ = _stub_notify(monkeypatch)

    _run(judge._notify_missing_decision_model("wf", "play"))

    assert len(calls) == 1
    assert calls[0]["kind"] == "workflow"
    assert calls[0]["status"] == "error"
    assert "run_id" not in calls[0]
    assert "404" not in calls[0]["message"]
    assert "decisi" in calls[0]["message"]


def test_notify_missing_model_on_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Notify as a schedule error on scheduled runs."""
    calls, _ = _stub_notify(monkeypatch)

    _run(judge._notify_missing_decision_model("wf", "schedule"))

    assert len(calls) == 1
    assert calls[0]["kind"] == "schedule"


@pytest.mark.parametrize("source", ["tool", "other", ""])
def test_notify_missing_model_skips_other_sources(
    monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    """Never notify for tool runs or unknown sources.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        source: Source that must not notify.
    """
    calls, _ = _stub_notify(monkeypatch)

    _run(judge._notify_missing_decision_model("wf", source))

    assert calls == []


def test_notify_missing_model_swallows_notify_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Swallow notification failures: the judge must never break the run."""
    calls, failures = _stub_notify(monkeypatch)
    failures.append(RuntimeError("db down"))
    logged: list[str] = []
    monkeypatch.setattr(judge, "log_error", lambda message, source="": logged.append(message))

    _run(judge._notify_missing_decision_model("wf", "play"))

    assert calls == []
    assert logged == ["db down"]


class _JudgeAgent:
    """Fake agent whose decision model slug does not exist."""

    decision_ready = True
    default_model = None
    provider = None

    def __init__(self, response: dict[str, Any]) -> None:
        """Store the decision answer to return.

        Args:
            response: Contract answer of ``decision``.
        """
        self._response = response

    def prompt(self, name: str, **kwargs: Any) -> str:
        """Return an empty prompt.

        Args:
            name: Prompt name (ignored).
            **kwargs: Extra arguments (ignored).

        Returns:
            An empty string.
        """
        return ""

    async def decision(self, state: Any, questions: Any) -> dict[str, Any]:
        """Return the configured decision answer.

        Args:
            state: Decision state (ignored).
            questions: Decision questions (ignored).

        Returns:
            The configured decision answer.
        """
        return self._response


def test_judge_run_notifies_and_approves_on_missing_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Notify once and approve silently when the decision slug does not exist."""
    calls, _ = _stub_notify(monkeypatch)
    monkeypatch.setattr(judge, "log_error", lambda *args, **kwargs: None)
    agent = _JudgeAgent(_not_found_response())

    ok, reason = _run(
        judge.judge_run(agent, "wf", "run1", "desc", [{"id": "a", "type": "run"}], {"a": "ok"}, "fin")
    )

    assert (ok, reason) == (True, "")
    assert len(calls) == 1
    assert calls[0]["kind"] == "workflow"
    assert calls[0]["workflow_name"] == "wf"


def test_judge_run_skips_notification_for_tool_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approve silently without notifying when the run came from a tool."""
    calls, _ = _stub_notify(monkeypatch)
    monkeypatch.setattr(judge, "log_error", lambda *args, **kwargs: None)
    agent = _JudgeAgent(_not_found_response())

    ok, reason = _run(
        judge.judge_run(
            agent, "wf", "run1", "desc", [{"id": "a", "type": "run"}], {"a": "ok"}, "fin",
            source="tool",
        )
    )

    assert (ok, reason) == (True, "")
    assert calls == []
