"""Generate the data dictionary and the DBML diagram of the agent database.

Builds the schema in an in-memory SQLite from ``ddl_setup`` (the single
source of truth) and writes, next to this file:

- ``data_dictionary.md``: what each table is for, its columns, keys and indexes.
- ``schema.dbml``: the same schema in DBML, to open in https://dbdiagram.io/d.

The purpose of each table is the comment block at the top of its
``queries/ddl/<table>.sql``. Run it again whenever the schema changes::

    python -m backend.agent.agent_db.generate_schema_docs
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from backend.agent.ddl_setup import _DDL_SCRIPTS, setup_database

_HERE = Path(__file__).resolve().parent
_DDL_DIR = _HERE / "queries" / "ddl"


def _purpose(table: str) -> str:
    """Return the comment block at the top of the table's DDL file (without ``--``)."""
    path = _DDL_DIR / f"{table}.sql"
    lines: list[str] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.startswith("--"):
                break
            lines.append(line[2:].strip())
    return " ".join(part for part in lines if part)


def _tables(conn: sqlite3.Connection) -> list[str]:
    """Return the tables in creation order of the DDL scripts."""
    present = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    }
    ordered = [Path(name).stem for name in _DDL_SCRIPTS if Path(name).stem in present]
    return ordered + sorted(present - set(ordered))


def _columns(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return conn.execute(f"PRAGMA table_info({table})").fetchall()


def _foreign_keys(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()


def _indexes(conn: sqlite3.Connection, table: str) -> list[tuple[str, bool, list[str]]]:
    result = []
    for row in conn.execute(f"PRAGMA index_list({table})").fetchall():
        if row["origin"] != "c":
            continue
        cols = [c["name"] for c in conn.execute(f"PRAGMA index_info({row['name']})").fetchall()]
        result.append((row["name"], bool(row["unique"]), cols))
    return result


def _unique_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the columns declared ``UNIQUE`` on their own."""
    result: set[str] = set()
    for row in conn.execute(f"PRAGMA index_list({table})").fetchall():
        if row["origin"] == "u":
            cols = [c["name"] for c in conn.execute(f"PRAGMA index_info({row['name']})").fetchall()]
            if len(cols) == 1:
                result.add(cols[0])
    return result


def build_markdown(conn: sqlite3.Connection) -> str:
    """Return the data dictionary as markdown."""
    out = [
        "# Diccionario de datos",
        "",
        "Generado por `generate_schema_docs.py` a partir del esquema real (`ddl_setup`). "
        "No se edita a mano: se regenera cuando cambia el esquema.",
        "",
        "## Tablas",
        "",
        "| Tabla | Para qué sirve |",
        "| --- | --- |",
    ]
    tables = _tables(conn)
    for table in tables:
        out.append(f"| [`{table}`](#{table}) | {_purpose(table).replace('|', '/') or '-'} |")
    for table in tables:
        out += ["", f"## {table}", "", _purpose(table) or "(sin descripción)", "",
                "| Columna | Tipo | Nulo | Por defecto | Clave |", "| --- | --- | --- | --- | --- |"]
        fks = {fk["from"]: f"{fk['table']}.{fk['to']}" for fk in _foreign_keys(conn, table)}
        for col in _columns(conn, table):
            key = "PK" if col["pk"] else (f"FK → {fks[col['name']]}" if col["name"] in fks else "")
            nullable = "no" if col["notnull"] or col["pk"] else "sí"
            default = f"`{col['dflt_value']}`" if col["dflt_value"] is not None else ""
            out.append(f"| `{col['name']}` | {col['type'] or ''} | {nullable} | {default} | {key} |")
        indexes = _indexes(conn, table)
        if indexes:
            out += ["", "Índices: " + ", ".join(
                f"`{name}` ({', '.join(cols)}{', único' if unique else ''})" for name, unique, cols in indexes
            )]
    return "\n".join(out) + "\n"


def _dbml_type(declared: str) -> str:
    base = re.sub(r"\(.*\)", "", declared or "").strip().lower()
    return base or "text"


def build_dbml(conn: sqlite3.Connection) -> str:
    """Return the schema as DBML (for dbdiagram.io)."""
    out = ["// Generado por generate_schema_docs.py a partir del esquema real. No editar a mano.", ""]
    refs: list[str] = []
    for table in _tables(conn):
        fks = {fk["from"]: fk for fk in _foreign_keys(conn, table)}
        out.append(f"Table {table} {{")
        pk_cols = [c for c in _columns(conn, table) if c["pk"]]
        unique = _unique_columns(conn, table)
        for col in _columns(conn, table):
            attrs = []
            if col["pk"]:
                attrs.append("pk")
                if len(pk_cols) == 1 and _dbml_type(col["type"]) == "integer":
                    attrs.append("increment")
            if col["notnull"] and not col["pk"]:
                attrs.append("not null")
            if col["name"] in unique and not col["pk"]:
                attrs.append("unique")
            if col["dflt_value"] is not None:
                default = str(col["dflt_value"])
                attrs.append(f"default: {default}" if re.fullmatch(r"-?\d+(\.\d+)?", default) else f"default: `{default}`")
            suffix = f" [{', '.join(attrs)}]" if attrs else ""
            out.append(f"  {col['name']} {_dbml_type(col['type'])}{suffix}")
            if col["name"] in fks:
                fk = fks[col["name"]]
                refs.append(f"Ref: {table}.{col['name']} > {fk['table']}.{fk['to']}")
        indexes = _indexes(conn, table)
        if indexes:
            out += ["", "  indexes {"]
            for name, unique, cols in indexes:
                names = cols[0] if len(cols) == 1 else f"({', '.join(cols)})"
                out.append(f"    {names} [name: '{name}'{', unique' if unique else ''}]")
            out.append("  }")
        purpose = _purpose(table).replace("'", "")
        if purpose:
            out += ["", f"  Note: '{purpose}'"]
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
    print(f"Escritos: {_HERE / 'data_dictionary.md'} y {_HERE / 'schema.dbml'}")


if __name__ == "__main__":
    main()
