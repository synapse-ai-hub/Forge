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


@pytest.fixture()
def frontier_db(tmp_path, monkeypatch):
    """Create an isolated agent DB and patch the helper connection."""
    db_path = str(tmp_path / "agent.db")
    conn = sqlite3.connect(db_path)
    try:
        setup_database(conn)
        conn.commit()
    finally:
        conn.close()

    @contextmanager
    def _fake_db_transaction():
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


def _rows(db_path, state=None):
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


def test_ddl_creates_step_frontier(frontier_db):
    rows = _rows(frontier_db)
    assert rows == []


def test_dispatch_writes_open_rows_with_full_args(frontier_db):
    long_content = "x" * 5000
    frontier_helpers.record_block_dispatch(
        "sess-1",
        1,
        1,
        [
            (0, "write", {"file_path": "a.txt", "content": "hola"}),
            (1, "write", {"file_path": "b.txt", "content": long_content}),
        ],
    )
    rows = _rows(frontier_db, "open")
    assert len(rows) == 2
    assert rows[0]["tool_name"] == "write"
    assert json.loads(rows[0]["tool_args"]) == {"file_path": "a.txt", "content": "hola"}
    # Args are stored complete, never truncated.
    assert json.loads(rows[1]["tool_args"])["content"] == long_content


def test_mark_done_flips_only_matching_row(frontier_db):
    frontier_helpers.record_block_dispatch(
        "sess-1", 1, 1, [(0, "write", {}), (1, "read", {})]
    )
    frontier_helpers.mark_call_done("sess-1", 1, 1, 0)
    assert len(_rows(frontier_db, "open")) == 1
    assert len(_rows(frontier_db, "done")) == 1
    # Unknown row: no-op, never raises.
    frontier_helpers.mark_call_done("sess-1", 1, 1, 99)
    assert len(_rows(frontier_db, "open")) == 1


def test_clear_turn_deletes_only_that_turn(frontier_db):
    frontier_helpers.record_block_dispatch("sess-1", 1, 1, [(0, "write", {})])
    frontier_helpers.record_block_dispatch("sess-1", 2, 1, [(0, "write", {})])
    frontier_helpers.clear_turn("sess-1", 1)
    rows = _rows(frontier_db)
    assert len(rows) == 1
    assert rows[0]["turn_number"] == 2


def test_cut_flow_leaves_open_rows_until_close(frontier_db):
    # Turn 1: block of 2 dispatched, first commits, flow cuts before close.
    frontier_helpers.record_block_dispatch(
        "sess-1", 1, 1, [(0, "write", {"file_path": "a.txt"}), (1, "write", {"file_path": "b.txt"})]
    )
    frontier_helpers.mark_call_done("sess-1", 1, 1, 0)
    # No clear_turn ran: the cut leaves one open row behind.
    pending = _rows(frontier_db, "open")
    assert len(pending) == 1
    assert json.loads(pending[0]["tool_args"]) == {"file_path": "b.txt"}
    # Validated close deletes everything.
    frontier_helpers.clear_turn("sess-1", 1)
    assert _rows(frontier_db) == []
