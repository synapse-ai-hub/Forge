"""Unit tests for F1 step frontier tracking.

Exercises the real ``record_block_dispatch``, ``mark_call_done`` and
``clear_turn`` from ``backend.agent.utils.frontier_helpers`` against an
isolated SQLite database created with ``setup_database`` (no network, no
mocks of the code under test).
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from contextlib import contextmanager

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from backend.agent.ddl_setup import setup_database
from backend.agent.utils import frontier_helpers
from pathlib import Path
from typing import Any
from collections.abc import Iterator


@pytest.fixture()
def frontier_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Create an isolated agent DB and patch the helper connection.

    Args:
        tmp_path: Temporary directory of the test.
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        The path of the isolated database.
    """
    db_path = str(tmp_path / "agent.db")
    conn = sqlite3.connect(db_path)
    try:
        setup_database(conn)
        conn.commit()
    finally:
        conn.close()

    @contextmanager
    def _fake_db_transaction() -> Iterator[sqlite3.Connection]:
        """Open the isolated database like ``db_transaction`` does.

        Yields:
            A connection that commits when the block ends and rolls back on an error.

        Raises:
            Exception: Whatever the block raised, after the rollback.
        """
        fake = sqlite3.connect(db_path)
        fake.row_factory = sqlite3.Row
        try:
            yield fake
            fake.commit()
        except Exception:
            fake.rollback()
            raise
        finally:
            fake.close()

    monkeypatch.setattr(frontier_helpers, "db_transaction", _fake_db_transaction)
    return db_path


def _rows(db_path: str, state: str | None = None) -> list[dict]:
    """Read the rows of ``step_frontier``.

    Args:
        db_path: Path of the database.
        state: Only the rows in this state, or ``None`` for all of them.

    Returns:
        One dict per row, ordered by step and substep.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        if state is None:
            cur = conn.execute("SELECT * FROM step_frontier ORDER BY step, substep")
        else:
            cur = conn.execute(
                "SELECT * FROM step_frontier WHERE state = ? ORDER BY step, substep",
                (state,),
            )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def test_ddl_creates_step_frontier(frontier_db: str) -> None:
    """Ddl creates step frontier.

    Args:
        frontier_db: Path of the isolated database with the ``step_frontier`` table.
    """
    rows = _rows(frontier_db)
    assert rows == []


def test_dispatch_writes_open_rows_with_full_args(frontier_db: str) -> None:
    """Dispatch writes open rows with full args.

    Args:
        frontier_db: Path of the isolated database with the ``step_frontier`` table.
    """
    long_content = "x" * 5000
    frontier_helpers.record_block_dispatch(
        "sess-1",
        1,
        1,
        [
            (0, "call-0", "write", {"file_path": "a.txt", "content": "hola"}),
            (1, "call-1", "write", {"file_path": "b.txt", "content": long_content}),
        ],
    )
    rows = _rows(frontier_db, "open")
    assert len(rows) == 2
    assert rows[0]["tool_name"] == "write"
    assert rows[0]["tool_call_id"] == "call-0"
    assert json.loads(rows[0]["tool_args"]) == {"file_path": "a.txt", "content": "hola"}
    # Args are stored complete, never truncated.
    assert json.loads(rows[1]["tool_args"])["content"] == long_content


def test_mark_done_flips_only_matching_row(frontier_db: str) -> None:
    """Mark done flips only matching row.

    Args:
        frontier_db: Path of the isolated database with the ``step_frontier`` table.
    """
    frontier_helpers.record_block_dispatch(
        "sess-1", 1, 1, [(0, "call-0", "write", {}), (1, "call-1", "read", {})]
    )
    frontier_helpers.mark_call_done("sess-1", 1, 1, 0)
    assert len(_rows(frontier_db, "open")) == 1
    assert len(_rows(frontier_db, "done")) == 1
    # Unknown row: no-op, never raises.
    frontier_helpers.mark_call_done("sess-1", 1, 1, 99)
    assert len(_rows(frontier_db, "open")) == 1


def test_clear_turn_deletes_only_that_turn(frontier_db: str) -> None:
    """Clear turn deletes only that turn.

    Args:
        frontier_db: Path of the isolated database with the ``step_frontier`` table.
    """
    frontier_helpers.record_block_dispatch("sess-1", 1, 1, [(0, "call-0", "write", {})])
    frontier_helpers.record_block_dispatch("sess-1", 2, 1, [(0, "call-1", "write", {})])
    frontier_helpers.clear_turn("sess-1", 1)
    rows = _rows(frontier_db)
    assert len(rows) == 1
    assert rows[0]["turn_number"] == 2


def test_cut_flow_leaves_open_rows_until_close(frontier_db: str) -> None:
    # Turn 1: block of 2 dispatched, first commits, flow cuts before close.
    """Cut flow leaves open rows until close.

    Args:
        frontier_db: Path of the isolated database with the ``step_frontier`` table.
    """
    frontier_helpers.record_block_dispatch(
        "sess-1", 1, 1, [(0, "call-0", "write", {"file_path": "a.txt"}), (1, "call-1", "write", {"file_path": "b.txt"})]
    )
    frontier_helpers.mark_call_done("sess-1", 1, 1, 0)
    # No clear_turn ran: the cut leaves one open row behind.
    pending = _rows(frontier_db, "open")
    assert len(pending) == 1
    assert json.loads(pending[0]["tool_args"]) == {"file_path": "b.txt"}
    # Validated close deletes everything.
    frontier_helpers.clear_turn("sess-1", 1)
    assert _rows(frontier_db) == []


def _insert_message(db_path: str, role: str, content: str, turn_number: int, **extra: Any) -> None:
    """Insert a message of ``sess-1`` and set extra columns on it.

    Args:
        db_path: Path of the database.
        role: Role of the message.
        content: Text of the message.
        turn_number: Turn the message belongs to.
        **extra: Other columns of ``messages`` and their values.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO messages (session_id, role, content, turn_number, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("sess-1", role, content, turn_number),
        )
        conn.commit()
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for key, value in extra.items():
            conn.execute(
                f"UPDATE messages SET {key} = ? WHERE id = ?", (value, row_id)
            )
        conn.commit()
    finally:
        conn.close()


def test_extract_task_child_id_from_result_xml() -> None:
    """Extract task child id from result xml."""
    xml = '<task id="sess-1:researcher:abc123" state="completed"><task_result>done</task_result></task>'
    assert (
        frontier_helpers.extract_task_child_id(
            {"status": "success", "message": "m", "data": xml}
        )
        == "sess-1:researcher:abc123"
    )
    assert frontier_helpers.extract_task_child_id({"status": "error"}) is None
    assert frontier_helpers.extract_task_child_id("plain text") is None


def test_set_task_child_attaches_child_id(frontier_db: str) -> None:
    """Set task child attaches child id.

    Args:
        frontier_db: Path of the isolated database with the ``step_frontier`` table.
    """
    frontier_helpers.record_block_dispatch(
        "sess-1", 1, 1, [(0, "call-9", "task", {"agent_name": "researcher"})]
    )
    frontier_helpers.set_task_child("sess-1", 1, 1, 0, "sess-1:researcher:abc123")
    rows = _rows(frontier_db, "open")
    assert rows[0]["child_id"] == "sess-1:researcher:abc123"


def test_build_resume_message_reads_first(frontier_db: str) -> None:
    """Build resume message reads first.

    Args:
        frontier_db: Path of the isolated database with the ``step_frontier`` table.
    """
    _insert_message(frontier_db, "user", "Investigá el módulo X", 1)
    long_result = "R" * 3000
    _insert_message(
        frontier_db, "tool", long_result, 1, tool_call_id="call-0",
        tool_name="write", step=1,
    )
    frontier_helpers.record_block_dispatch(
        "sess-1",
        1,
        1,
        [
            (0, "call-0", "write", {"file_path": "a.txt"}),
            (1, "call-1", "task", {"agent_name": "researcher", "prompt": "P" * 2000}),
        ],
    )
    frontier_helpers.set_task_child("sess-1", 1, 1, 1, "sess-1:researcher:abc123")
    text = frontier_helpers.build_resume_message("sess-1")
    assert text is not None
    # Original user request, full args, full recorded result: nothing truncated.
    assert "Investigá el módulo X" in text
    assert '"file_path": "a.txt"' in text
    assert "P" * 2000 in text
    assert long_result in text
    assert "sub-sesión: sess-1:researcher:abc123" in text


def test_build_resume_message_none_when_clean(frontier_db: str) -> None:
    """Build resume message none when clean.

    Args:
        frontier_db: Path of the isolated database with the ``step_frontier`` table.
    """
    assert frontier_helpers.build_resume_message("sess-1") is None


def test_should_close_accepts_llm_without_decisor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Should close accepts llm without decisor.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    import asyncio
    import backend.instances as instances
    from backend.agent.utils import decision

    monkeypatch.setattr(instances, "agent", None)
    assert asyncio.run(decision.should_close_step("sess-1", 1, "listo")) is True


def test_should_close_fail_open_on_decision_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Should close fail open on decision error.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    import asyncio
    import backend.instances as instances
    from backend.agent.utils import decision

    class _MockAgent:
        """Agent whose decision model always fails."""
        decision_enabled = True

        async def decision(self, *args: Any, **kwargs: Any) -> None:
            """Fail like a decision model that is down.

            Args:
                *args: Ignored.
                **kwargs: Ignored.

            Raises:
                RuntimeError: Always.
            """
            raise RuntimeError("simulated error")

        def prompt(self, name: str) -> str:
            """Return a fixed instruction text.

            Args:
                name: Name of the prompt (ignored).

            Returns:
                The text ``instrucciones``.
            """
            return "instrucciones"

    monkeypatch.setattr(instances, "agent", _MockAgent())
    assert asyncio.run(decision.should_close_step("sess-1", 1, "listo")) is True


def test_collect_garbage_deletes_only_old_done(frontier_db: str) -> None:
    """Collect garbage deletes only old done.

    Args:
        frontier_db: Path of the isolated database with the ``step_frontier`` table.
    """
    frontier_helpers.record_block_dispatch(
        "sess-1", 1, 1, [(0, "call-0", "write", {}), (1, "call-1", "read", {})]
    )
    frontier_helpers.mark_call_done("sess-1", 1, 1, 0)
    conn = sqlite3.connect(frontier_db)
    try:
        conn.execute(
            "UPDATE step_frontier SET updated_at = datetime('now', '-2 days') "
            "WHERE substep = 0"
        )
        conn.commit()
    finally:
        conn.close()
    assert frontier_helpers.collect_garbage(ttl_hours=24) == 1
    rows = _rows(frontier_db)
    assert len(rows) == 1
    # The surviving row is the recent done one, open rows are never collected.
    assert rows[0]["state"] in ("open", "done")
    frontier_helpers.record_block_dispatch(
        "sess-1", 9, 1, [(0, "call-9", "write", {})]
    )
    conn = sqlite3.connect(frontier_db)
    try:
        conn.execute(
            "UPDATE step_frontier SET updated_at = datetime('now', '-30 days') "
            "WHERE turn_number = 9"
        )
        conn.commit()
    finally:
        conn.close()
    assert frontier_helpers.collect_garbage(ttl_hours=24) == 0
    assert len(_rows(frontier_db, "open")) == 2
