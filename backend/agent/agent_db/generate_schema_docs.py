"""Generate the data dictionary and the DBML diagram of the agent database.

Builds the schema in an in-memory SQLite from ``ddl_setup`` (the single
source of truth) and writes, next to this file:

- ``data_dictionary.md``: what each table is for, what each column holds, and
  its keys, relations and indexes.
- ``schema.dbml``: the same schema in DBML, to open in https://dbdiagram.io/d.

The descriptions are the comments of ``queries/ddl/<table>.sql``: the block of
``--`` lines above ``CREATE TABLE`` says what the table is for, and the
``-- text`` at the end of a column line describes that column. Run it again
whenever the schema or those comments change::

    python -m backend.agent.agent_db.generate_schema_docs
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from backend.agent.ddl_setup import _DDL_SCRIPTS, setup_database

_HERE = Path(__file__).resolve().parent
_DDL_DIR = _HERE / "queries" / "ddl"

_COLUMN_LINE = re.compile(r"^\s+(\w+)\s+[A-Za-z]+[^\n]*?--\s*(.+?)\s*$")


def _read_ddl(table: str) -> list[str]:
    """Read the DDL file of a table.

    Args:
        table: Table name.

    Returns:
        The lines of ``queries/ddl/<table>.sql``, or an empty list when it does not exist.
    """
    path = _DDL_DIR / f"{table}.sql"
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


def _purpose(table: str) -> str:
    """Return the comment block above ``CREATE TABLE`` as one paragraph.

    Args:
        table: Table name.

    Returns:
        The text of the ``--`` lines at the top of the DDL file.
    """
    parts: list[str] = []
    for line in _read_ddl(table):
        if not line.startswith("--"):
            break
        parts.append(line[2:].strip())
    return " ".join(part for part in parts if part)


def _summary(table: str) -> str:
    """Take the first sentence of the purpose of a table.

    Args:
        table: Table name.

    Returns:
        The first sentence of the comment block of its DDL file.
    """
    text = _purpose(table)
    match = re.search(r"\.(\s|$)", text)
    return text[: match.end()].strip() if match else text


def _column_notes(table: str) -> dict[str, str]:
    """Collect the description of each column from the DDL comments.

    Args:
        table: Table name.

    Returns:
        Column name → text of the ``--`` comment at the end of its line.
    """
    notes: dict[str, str] = {}
    for line in _read_ddl(table):
        match = _COLUMN_LINE.match(line)
        if match and not line.lstrip().startswith("--"):
            notes[match.group(1)] = match.group(2)
    return notes


def _tables(conn: sqlite3.Connection) -> list[str]:
    """List the tables of the schema.

    Args:
        conn: Connection to a database with the schema of ``ddl_setup``.

    Returns:
        The table names in the creation order of the DDL scripts.
    """
    present = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    }
    ordered = [Path(name).stem for name in _DDL_SCRIPTS if Path(name).stem in present]
    return ordered + sorted(present - set(ordered))


def _columns(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    """Read the columns of a table.

    Args:
        conn: Connection to a database with the schema.
        table: Table name.

    Returns:
        The ``PRAGMA table_info`` rows.
    """
    return conn.execute(f"PRAGMA table_info({table})").fetchall()


def _foreign_keys(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    """Read the foreign keys of a table.

    Args:
        conn: Connection to a database with the schema.
        table: Table name.

    Returns:
        The ``PRAGMA foreign_key_list`` rows.
    """
    return conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()


def _unique_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Find the columns declared ``UNIQUE`` on their own.

    Args:
        conn: Connection to a database with the schema.
        table: Table name.

    Returns:
        The names of those columns.
    """
    result: set[str] = set()
    for row in conn.execute(f"PRAGMA index_list({table})").fetchall():
        if row["origin"] == "u":
            cols = [c["name"] for c in conn.execute(f"PRAGMA index_info({row['name']})").fetchall()]
            if len(cols) == 1:
                result.add(cols[0])
    return result


def _indexes(conn: sqlite3.Connection, table: str) -> list[tuple[str, bool, list[str]]]:
    """List the indexes created with ``CREATE INDEX``.

    Args:
        conn: Connection to a database with the schema.
        table: Table name.

    Returns:
        One ``(name, unique, columns)`` tuple per index.
    """
    result = []
    for row in conn.execute(f"PRAGMA index_list({table})").fetchall():
        if row["origin"] != "c":
            continue
        cols = [c["name"] for c in conn.execute(f"PRAGMA index_info({row['name']})").fetchall()]
        result.append((row["name"], bool(row["unique"]), cols))
    return result


def _referenced_by(conn: sqlite3.Connection, table: str, tables: list[str]) -> list[str]:
    """Find the foreign keys that point to a table.

    Args:
        conn: Connection to a database with the schema.
        table: Referenced table.
        tables: Every table of the schema.

    Returns:
        ``other_table.column`` for each foreign key that points to ``table``.
    """
    refs = []
    for other in tables:
        for fk in _foreign_keys(conn, other):
            if fk["table"] == table:
                refs.append(f"{other}.{fk['from']}")
    return refs


def _on_delete(fk: sqlite3.Row) -> str:
    """Describe the ``ON DELETE`` action of a foreign key.

    Args:
        fk: Row of ``PRAGMA foreign_key_list``.

    Returns:
        ``no action``, ``cascade`` or ``set null``.
    """
    action = (fk["on_delete"] or "NO ACTION").lower()
    return {"no action": "no action", "cascade": "cascade", "set null": "set null"}.get(action, action)


_NO_RELATION_REASONS = {
    "config_kv": "Independent key/value settings: no entity to relate to.",
    "context_files": "Global context files: they belong to no session.",
    "error_log": (
        "An error must be stored even when its session does not exist (anymore) and it must outlive "
        "the session. With foreign keys enforced, a foreign key on `session_id` would reject it."
    ),
    "external_usage": (
        "The provider is free text (it can be unknown) and the usage is stored even when there is no "
        "session, so `provider` and `session_id` have no foreign key."
    ),
    "creators": (
        "No table holds the creator conversations: they are the group of rows that share `creator_id`, "
        "so there is nothing for that column to reference. The provider is free text (it can be unknown)."
    ),
    "workflow_run_steps": (
        "`run_id` is the group of rows of `workflow_runs` that share it (a run has many rows, so no "
        "column is unique to reference)."
    ),
    "decision_catalog": (
        "Its providers are not necessarily configured, so `provider` has no foreign key to `providers`."
    ),
}
"""Why each table without relations has none (shown in the ER section of the dictionary)."""

_SOFT_REFERENCES = [
    ("error_log.session_id", "`sessions.session_id`"),
    ("error_log.parent_id", "`sessions.session_id`"),
    ("external_usage.session_id", "`sessions.session_id`"),
    ("step_frontier.child_id", "`sessions.session_id` (task) or `workflow_runs.run_id` (workflow)"),
    ("notifications.run_id", "`workflow_runs.run_id`"),
    ("workflow_run_steps.run_id", "`workflow_runs.run_id`"),
]
"""Columns that hold the id of another table but are not declared as foreign keys."""


def _er_diagram(conn: sqlite3.Connection, tables: list[str]) -> list[str]:
    """Draw the tables and their foreign keys as a Mermaid ER diagram.

    Args:
        conn: Connection to a database with the schema.
        tables: Every table of the schema.

    Returns:
        The lines of the fenced ``mermaid`` block.
    """
    lines = ["```mermaid", "erDiagram"]
    relations = []
    for table in tables:
        fks = {fk["from"]: fk for fk in _foreign_keys(conn, table)}
        lines.append(f"    {table} {{")
        for col in _columns(conn, table):
            marks = (["PK"] if col["pk"] else []) + (["FK"] if col["name"] in fks else [])
            if marks:
                lines.append(f"        {(col['type'] or 'TEXT').lower()} {col['name']} {','.join(marks)}")
        lines.append("    }")
        for fk in fks.values():
            required = any(c["name"] == fk["from"] and c["notnull"] for c in _columns(conn, table))
            parent = "||" if required else "|o"
            relations.append(f'    {fk["table"]} {parent}--o{{ {table} : "{fk["from"]}"')
    return lines + relations + ["```"]


def _er_section(conn: sqlite3.Connection, tables: list[str]) -> list[str]:
    """Build the closing section of the dictionary: the ER diagram and the tables without relations.

    Args:
        conn: Connection to a database with the schema.
        tables: Every table of the schema.

    Returns:
        The markdown lines of the section.
    """
    isolated = [
        t for t in tables
        if not _foreign_keys(conn, t) and not _referenced_by(conn, t, tables)
    ]
    out = [
        "", "## Entity-relationship diagram", "",
        "Every table has a primary key. The diagram shows only the key columns (`PK`, `FK`); the "
        "columns of each table are in its section above. The same schema in DBML is in `schema.dbml`.",
        "",
    ]
    out += _er_diagram(conn, tables)
    out += [
        "", "### Tables without foreign keys", "",
        "These tables have a primary key but no foreign key, and no table references them. It is on purpose:",
        "", "| Table | Reason |", "| --- | --- |",
    ]
    for table in isolated:
        out.append(f"| `{table}` | {_NO_RELATION_REASONS.get(table, '-')} |")
    out += [
        "", "### Columns that point to another table without a foreign key", "",
        "| Column | Holds the id of |", "| --- | --- |",
    ]
    out += [f"| `{column}` | {target} |" for column, target in _SOFT_REFERENCES]
    return out


def build_markdown(conn: sqlite3.Connection) -> str:
    """Return the data dictionary as markdown.

    Args:
        conn: Connection to a database with the schema of ``ddl_setup``.

    Returns:
        The markdown text.
    """
    tables = _tables(conn)
    out = [
        "# Data dictionary",
        "",
        "Generated by `generate_schema_docs.py` from the real schema (`ddl_setup`) and the comments of "
        "`queries/ddl/*.sql`. Do not edit by hand: change the comments of the DDL and generate it again.",
        "",
        "## Tables",
        "",
        "| Table | Purpose |",
        "| --- | --- |",
    ]
    for table in tables:
        out.append(f"| [`{table}`](#{table}) | {_summary(table).replace('|', '/') or '-'} |")
    for table in tables:
        notes = _column_notes(table)
        fks = {fk["from"]: fk for fk in _foreign_keys(conn, table)}
        unique = _unique_columns(conn, table)
        pk_cols = [c["name"] for c in _columns(conn, table) if c["pk"]]
        out += ["", f"## {table}", "", _purpose(table) or "(no description)", "",
                "| Column | Type | Null | Default | Key | Description |",
                "| --- | --- | --- | --- | --- | --- |"]
        for col in _columns(conn, table):
            key = []
            if col["pk"]:
                key.append("PK" if len(pk_cols) == 1 else "PK (composite)")
            if col["name"] in fks:
                key.append(f"FK → {fks[col['name']]['table']}.{fks[col['name']]['to']}")
            if col["name"] in unique:
                key.append("unique")
            nullable = "no" if col["notnull"] or col["pk"] else "yes"
            default = f"`{col['dflt_value']}`" if col["dflt_value"] is not None else ""
            description = notes.get(col["name"], "").replace("|", "/")
            out.append(
                f"| `{col['name']}` | {col['type'] or ''} | {nullable} | {default} | {', '.join(key)} | {description} |"
            )
        relations = [
            f"`{fk['from']}` → `{fk['table']}.{fk['to']}` (on delete: {_on_delete(fk)})"
            for fk in _foreign_keys(conn, table)
        ]
        referenced = _referenced_by(conn, table, tables)
        if relations or referenced:
            out += ["", "Relations:"]
            out += [f"- {rel}" for rel in relations]
            if referenced:
                out.append("- Referenced by: " + ", ".join(f"`{ref}`" for ref in referenced))
        indexes = _indexes(conn, table)
        if indexes:
            out += ["", "Indexes: " + ", ".join(
                f"`{name}` ({', '.join(cols)}{', unique' if unique_idx else ''})" for name, unique_idx, cols in indexes
            )]
    out += _er_section(conn, tables)
    return "\n".join(out) + "\n"


def _dbml_type(declared: str) -> str:
    """Convert a declared SQLite type to a DBML type.

    Args:
        declared: Type as declared in the DDL.

    Returns:
        The type in lowercase, ``text`` when it is not declared.
    """
    base = re.sub(r"\(.*\)", "", declared or "").strip().lower()
    return base or "text"


def _dbml_text(text: str) -> str:
    """Escape a text to put it inside single quotes in DBML.

    Args:
        text: Text to escape.

    Returns:
        The escaped text.
    """
    return text.replace("\\", "/").replace("'", "\\'")


def build_dbml(conn: sqlite3.Connection) -> str:
    """Return the schema as DBML (for dbdiagram.io).

    Args:
        conn: Connection to a database with the schema of ``ddl_setup``.

    Returns:
        The DBML text.
    """
    out = ["// Generated by generate_schema_docs.py from the real schema. Do not edit by hand.", ""]
    refs: list[str] = []
    for table in _tables(conn):
        fks = {fk["from"]: fk for fk in _foreign_keys(conn, table)}
        notes = _column_notes(table)
        unique = _unique_columns(conn, table)
        columns = _columns(conn, table)
        pk_cols = [c["name"] for c in columns if c["pk"]]
        out.append(f"Table {table} {{")
        for col in columns:
            attrs = []
            if col["pk"] and len(pk_cols) == 1:
                attrs.append("pk")
                if _dbml_type(col["type"]) == "integer":
                    attrs.append("increment")
            if col["notnull"] and not col["pk"]:
                attrs.append("not null")
            if col["name"] in unique and not col["pk"]:
                attrs.append("unique")
            if col["dflt_value"] is not None:
                default = str(col["dflt_value"])
                attrs.append(f"default: {default}" if re.fullmatch(r"-?\d+(\.\d+)?", default) else f"default: `{default}`")
            if notes.get(col["name"]):
                attrs.append(f"note: '{_dbml_text(notes[col['name']])}'")
            suffix = f" [{', '.join(attrs)}]" if attrs else ""
            out.append(f"  {col['name']} {_dbml_type(col['type'])}{suffix}")
            if col["name"] in fks:
                fk = fks[col["name"]]
                action = _on_delete(fk)
                setting = f" [delete: {action}]" if action != "no action" else ""
                refs.append(f"Ref: {table}.{col['name']} > {fk['table']}.{fk['to']}{setting}")
        indexes = _indexes(conn, table)
        if indexes or len(pk_cols) > 1:
            out += ["", "  indexes {"]
            if len(pk_cols) > 1:
                out.append(f"    ({', '.join(pk_cols)}) [pk]")
            for name, unique_idx, cols in indexes:
                names = cols[0] if len(cols) == 1 else f"({', '.join(cols)})"
                out.append(f"    {names} [name: '{name}'{', unique' if unique_idx else ''}]")
            out.append("  }")
        purpose = _purpose(table)
        if purpose:
            out += ["", f"  Note: '{_dbml_text(purpose)}'"]
        out += ["}", ""]
    return "\n".join(out + refs) + "\n"


def main() -> None:
    """Write ``data_dictionary.md`` and ``schema.dbml`` next to this file."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        setup_database(conn)
        (_HERE / "data_dictionary.md").write_text(build_markdown(conn), encoding="utf-8")
        (_HERE / "schema.dbml").write_text(build_dbml(conn), encoding="utf-8")
    finally:
        conn.close()
    print(f"Written: {_HERE / 'data_dictionary.md'} and {_HERE / 'schema.dbml'}")


if __name__ == "__main__":
    main()
